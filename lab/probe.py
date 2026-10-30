"""Independent real HTTP / PostgreSQL-backed order verification."""
import asyncio,os,time,uuid
from contextlib import asynccontextmanager
import httpx,psycopg
from lab.common import secret
from fastapi import FastAPI,Depends
from lab.common import DATA,operator,put,get,init_store,ident
BASE='http://order-api:8080';init_store()
DSN='host=db dbname=orders user=verifier password='+secret('verify_db_password')
def sample_request(c,coupon):
 payload={'quantity':2,'request_key':'probe-'+uuid.uuid4().hex}
 if coupon is not None:payload['coupon']=coupon
 start=time.time();r=c.post(BASE+'/orders',json=payload);result={'path':'coupon' if coupon else 'no_coupon','status':r.status_code,'elapsed_ms':round((time.time()-start)*1000,2),'ok':False,'expected_total_cents':18000 if coupon else 20000}
 if r.status_code!=200:result['response_excerpt']=r.text[:400]
 if r.status_code==200:
  row=r.json();read=c.get(BASE+'/orders/'+row['id']);want=18000 if coupon else 20000
  result.update(order_id=row['id'],total_cents=row.get('total_cents'),persisted=read.json() if read.status_code==200 else None)
  with psycopg.connect(DSN) as database:
   stored=database.execute('SELECT id,quantity,total_cents FROM orders WHERE id=%s',(row['id'],)).fetchone()
  result['database_row']=list(stored) if stored else None
  result['ok']=bool(stored and stored[1]==2 and stored[2]==want) and row.get('total_cents')==want and read.status_code==200 and read.json().get('total_cents')==want and read.json().get('quantity')==2
  if result['ok'] and not get('baseline','old_order'):put('baseline','old_order',{'id':row['id'],'total_cents':want})
 return result
def sample(coupon):
 # A failed ASGI request can close its keepalive connection. Isolate paths so
 # an expected 500 cannot suppress the next healthy-path observation.
 with httpx.Client(timeout=8,trust_env=False) as c:return sample_request(c,coupon)
async def traffic():
 while True:
  try:
   def cycle():
    started=time.time();rows=[];before=None;after=None
    try:
     with httpx.Client(timeout=8,trust_env=False) as c:before=c.get(BASE+'/version').json()
     for coupon in [None,'SAVE10']:
      try:rows.append(sample(coupon))
      except Exception as exc:rows.append({'path':'coupon' if coupon else 'no_coupon','ok':False,'error':type(exc).__name__})
     with httpx.Client(timeout=8,trust_env=False) as c:after=c.get(BASE+'/version').json()
    except Exception as exc:rows.append({'ok':False,'error':type(exc).__name__})
    stable=bool(before and before==after)
    state=('HEALTHY' if len(rows)==2 and all(r['ok'] for r in rows) else 'UNHEALTHY') if stable else 'UNKNOWN'
    observation={'observation_id':ident('observation'),'started_at':started,'observed_at':time.time(),'state':state,'version':after,'version_before':before,'version_stable':stable,'requests':rows,'source':'real HTTP orders + readback + PostgreSQL SELECT'}
    previous=get('observation','latest') or {}
    # Keep the first observation of each real health/release transition, even
    # when automatic recovery completes before the browser next polls.
    if state!=previous.get('state') or after!=previous.get('version'):put('health-evidence',observation['observation_id'],observation)
    put('observation','latest',observation)
   await asyncio.to_thread(cycle)
  except Exception:pass
  await asyncio.sleep(1)
@asynccontextmanager
async def lifespan(app):
 task=asyncio.create_task(traffic());yield;task.cancel()
app=FastAPI(lifespan=lifespan)
@app.get('/health')
def health():return {'ok':True}
@app.get('/observations',dependencies=[Depends(operator)])
def observations(release_id:str=''):
 from lab.common import all_objects
 rows=all_objects('health-evidence');latest=get('observation','latest')
 if latest:rows.append(latest)
 return sorted((r for r in rows if not release_id or (r.get('version') or {}).get('release_id')==release_id),key=lambda r:r['observed_at'])
@app.get('/observations/latest',dependencies=[Depends(operator)])
def latest_observation():return get('observation','latest')
@app.get('/progress/{key}',dependencies=[Depends(operator)])
def progress(key:str):return get('verification-progress',key)
@app.get('/reports/{key}',dependencies=[Depends(operator)])
def report(key:str):return get('report',key)
@app.post('/verify',dependencies=[Depends(operator)])
def verify(args:dict):
 return verify_contract(args)
@app.post('/baseline',dependencies=[Depends(operator)])
def baseline(args:dict):
 return verify_contract(args,quick_baseline=True)
def verify_contract(args:dict,quick_baseline=False):
 seconds=int(os.getenv('LAB_VERIFY_SECONDS','60'));windows=int(os.getenv('LAB_VERIFY_WINDOWS','2'));minimum=int(os.getenv('LAB_VERIFY_MIN_REQUESTS','30'))
 if quick_baseline:seconds,windows,minimum=0,1,2
 # No caller-supplied shortcuts to the trusted recovery contract.
 report={'verification_id':ident('verify'),'release_id':args['release_id'],'expected_source_sha':args['source_sha'],'expected_image_digest':args['image_digest'],'started_at':time.time(),'windows':[],'passed':True,'contract':{'seconds':seconds,'windows':windows,'minimum_per_path':minimum}}
 if quick_baseline:report['contract'].update(mode='quick_baseline',rounds=2)
 key=args.get('progress_key') or report['verification_id']
 def publish(window,rows):
  put('verification-progress',key,{'verification_id':report['verification_id'],'started_at':report['started_at'],'observed_at':time.time(),'window':window,'windows':windows,'seconds_per_window':seconds,'elapsed_seconds':round(time.time()-report['started_at'],1),'counts':{p:sum(r.get('path')==p for r in rows) for p in ['coupon','no_coupon']},'failed_requests':sum(not r['ok'] for r in rows),'completed_windows':len(report['windows']),'finished':False})
 publish(1,[])
 with httpx.Client(timeout=8,trust_env=False) as c:
  report['before']=c.get(BASE+'/version').json()
  for n in range(windows):
   start=time.time();rows=[]
   while (len(rows)<4 if quick_baseline else time.time()-start<seconds):
    for coupon in [None,'SAVE10']:
     try:rows.append(sample(coupon))
     except Exception as exc:rows.append({'path':'coupon' if coupon else 'no_coupon','ok':False,'error':type(exc).__name__})
    publish(n+1,rows)
    if not quick_baseline:time.sleep(.5)
   counts={p:sum(r['path']==p for r in rows) for p in ['coupon','no_coupon']}
   passed=all(r['ok'] for r in rows) and all(v>=minimum for v in counts.values())
   report['windows'].append({'start':start,'end':time.time(),'counts':counts,'passed':passed,'requests':rows});report['passed'] &= passed
  old=get('baseline','old_order');old_response=c.get(BASE+'/orders/'+old['id']) if old else None
  report['old_order_ok']=bool(old_response is not None and old_response.status_code==200 and old_response.json().get('total_cents')==old['total_cents'])
  bad=c.post(BASE+'/orders',json={'quantity':0,'request_key':uuid.uuid4().hex});bad_coupon=c.post(BASE+'/orders',json={'quantity':2,'coupon':'NOT_VALID','request_key':uuid.uuid4().hex})
  report['invalid_input_ok']=bad.status_code==422 and bad_coupon.status_code==422
  report['after']=c.get(BASE+'/version').json();report['passed'] &= report['old_order_ok'] and report['invalid_input_ok'] and report['before']==report['after'] and report['after'].get('release_id')==args['release_id'] and report['after'].get('source_sha')==args['source_sha'] and report['after'].get('image_digest')==args['image_digest']
 report['finished_at']=time.time();put('report',report['verification_id'],report)
 last=get('verification-progress',key);put('verification-progress',key,{**last,'finished':True,'passed':bool(report['passed']),'observed_at':time.time()})
 return report
