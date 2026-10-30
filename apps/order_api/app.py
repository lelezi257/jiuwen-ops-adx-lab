import hashlib,json,logging,os,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from logging.handlers import RotatingFileHandler
import psycopg
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel,Field
from prometheus_client import Counter,Histogram,generate_latest
from pricing import total_cents

password=os.getenv('DB_PASSWORD') or Path(os.getenv('DB_PASSWORD_FILE','/run/secrets/db_password')).read_text().strip()
DSN=f"host={os.getenv('DB_HOST','db')} dbname=orders user=orders password={password}"
requests=Counter('order_requests_total','HTTP requests',['path','status','release_id'])
latency=Histogram('order_request_seconds','HTTP request duration',['path'])
log=logging.getLogger('order');log.setLevel(logging.INFO)
Path('/logs').mkdir(exist_ok=True)
handler=RotatingFileHandler('/logs/order.jsonl',maxBytes=10_000_000,backupCount=2);handler.setFormatter(logging.Formatter('%(message)s'));log.addHandler(handler)
@asynccontextmanager
async def lifespan(app):
 with psycopg.connect(DSN) as c:c.execute('CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, request_key TEXT UNIQUE, payload_hash TEXT NOT NULL, quantity INTEGER NOT NULL, coupon TEXT, total_cents INTEGER NOT NULL, created_at DOUBLE PRECISION NOT NULL)')
 yield
app=FastAPI(lifespan=lifespan)
@app.middleware('http')
async def record(request:Request,call_next):
 start=time.time();status=500;error=None
 try:
  response=await call_next(request);status=response.status_code;return response
 except Exception as exc:
  error=type(exc).__name__+': '+str(exc);raise
 finally:
  path=request.url.path;path='/orders/{id}' if path.startswith('/orders/') else path
  if path not in ['/metrics','/health']:
   requests.labels(path,str(status),os.getenv('RELEASE_ID','bootstrap')).inc();latency.labels(path).observe(time.time()-start)
   log.info(json.dumps({'time':time.time(),'service':'order-api','path':path,'status':status,'duration_ms':round((time.time()-start)*1000,2),'error':error,'source_sha':os.getenv('SOURCE_SHA','unknown'),'release_id':os.getenv('RELEASE_ID','bootstrap')},ensure_ascii=False))
class Order(BaseModel):
 quantity:int=Field(ge=1,le=100)
 coupon:str|None=Field(default=None,max_length=64)
 request_key:str=Field(min_length=1,max_length=100)
@app.get('/health')
def health():
 with psycopg.connect(DSN) as c:c.execute('SELECT 1')
 return {'ok':True,'source_sha':os.getenv('SOURCE_SHA','unknown'),'release_id':os.getenv('RELEASE_ID','bootstrap')}
@app.get('/version')
def version():return {'source_sha':os.getenv('SOURCE_SHA','unknown'),'release_id':os.getenv('RELEASE_ID','bootstrap'),'image_digest':os.getenv('IMAGE_DIGEST','unregistered')}
@app.get('/metrics',response_class=PlainTextResponse)
def metrics():return generate_latest().decode()
@app.post('/orders')
def create(order:Order):
 try:amount=total_cents(order.quantity,order.coupon)
 except ValueError as exc:raise HTTPException(422,str(exc))
 payload_hash=hashlib.sha256(json.dumps([order.quantity,order.coupon]).encode()).hexdigest()
 with psycopg.connect(DSN) as c:
  oid=uuid.uuid4().hex
  c.execute('INSERT INTO orders VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(request_key) DO NOTHING',(oid,order.request_key,payload_hash,order.quantity,order.coupon,amount,time.time()))
  row=c.execute('SELECT id,payload_hash,total_cents FROM orders WHERE request_key=%s',(order.request_key,)).fetchone()
  if row[1]!=payload_hash:raise HTTPException(409,'request_key_payload_conflict')
 return {'id':row[0],'total_cents':row[2]}
@app.get('/orders/{oid}')
def read(oid:str):
 with psycopg.connect(DSN) as c:r=c.execute('SELECT id,quantity,coupon,total_cents FROM orders WHERE id=%s',(oid,)).fetchone()
 if not r:raise HTTPException(404,'order_not_found')
 return dict(zip(['id','quantity','coupon','total_cents'],r))
