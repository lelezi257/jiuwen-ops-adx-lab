"""Durable operator actions and business evidence, separate from Agent execution."""
import asyncio,threading,time
from fastapi import HTTPException
from lab.common import all_objects,call,get,ident,now,put

DELIVERY='http://delivery:8080';PROBE='http://probe:8080'
lock=threading.RLock()
DONE={'SUCCEEDED','FAILED','INTERRUPTED'}
TERMINAL_CASES={'RESOLVED_FIXED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED','NO_ACTION','DELIVERY_ACCEPTANCE_PASSED','TRACE_PROBE_COMPLETED'}

def contract_summary(report):
 if not report:return None
 examples=[]
 for path in ['no_coupon','coupon']:
  row=next((r for w in report.get('windows',[]) for r in w['requests'] if r.get('path')==path),None)
  if row:examples.append({k:row.get(k) for k in ['path','status','order_id','total_cents','expected_total_cents','database_row','ok']})
 return {**{k:report.get(k) for k in ['verification_id','release_id','expected_source_sha','expected_image_digest','started_at','finished_at','passed','old_order_ok','invalid_input_ok','contract']},'examples':examples,'windows':[{'start':w['start'],'end':w['end'],'counts':w['counts'],'passed':w['passed'],'failed_requests':sum(not r.get('ok') for r in w['requests']),'database_rows_match':bool(w['requests']) and all(r.get('ok') and r.get('database_row')==[r.get('order_id'),2,r.get('total_cents')] for r in w['requests'])} for w in report.get('windows',[])]}

def update_round(eid,**fields):
 with lock:
  item=get('experiment',eid);item.update(fields);item['updated_at']=now();put('experiment',eid,item);return item

def rounds():return sorted(all_objects('experiment'),key=lambda x:x['created_at'],reverse=True)
def case_summary(c):return {**{k:c.get(k) for k in ['id','kind','created_at','updated_at','state','phase','attempt','attempt_id','observed_release','observed_sha','pr','experiment_id']},'sdk_runs':c.get('sdk_runs') or {}}

def attach_case(c):
 for e in rounds():
  if e.get('fault_release')==c.get('observed_release'):
   update_round(e['id'],case_id=c['id']);return

def record_recovery(c,report):
 if not report.get('passed'):return
 for e in rounds():
  if e.get('case_id')==c['id'] or e.get('fault_release')==c.get('observed_release'):
   update_round(e['id'],case_id=c['id'],recovery=contract_summary(report));return

def submit(action):
 if action not in ['baseline','fault']:raise HTTPException(400,'只支持验证正常基线或制造真实故障')
 with lock:
  if any(o['state'] not in DONE for o in all_objects('operation')):raise HTTPException(409,'已有实验操作正在执行，请等待其结束')
  if any(c['state'] not in TERMINAL_CASES for c in all_objects('case')):raise HTTPException(409,'已有事件正在处理，请等待完成后再开始新一轮实验')
  e=next((x for x in rounds() if (x.get('baseline') or {}).get('passed') and not x.get('fault_operation')),None) if action=='fault' else None
  if not e:
   eid=ident('experiment');e={'id':eid,'created_at':now(),'updated_at':now(),'baseline':None,'fault':None,'recovery':None};put('experiment',eid,e)
  oid=ident('operation');o={'id':oid,'action':action,'experiment_id':e['id'],'state':'QUEUED','stage':'QUEUED','created_at':now(),'updated_at':now()};put('operation',oid,o)
  update_round(e['id'],**{action+'_operation':oid});return operation_summary(o)

def set_operation(oid,**fields):
 with lock:
  o=get('operation',oid);o.update(fields);o['updated_at']=now();put('operation',oid,o);return o

def run_operation(oid):
 with lock:
  o=get('operation',oid)
  if o['state']!='QUEUED':return
  started=now()
  set_operation(oid,state='RUNNING',stage='VERIFYING_BASELINE' if o['action']=='baseline' else 'PUBLISHING_FAULT',started_at=started)
 eid=o['experiment_id']
 try:
  if o['action']=='baseline':
   cur=call(DELIVERY,'/ops/register',{})
   report=call(PROBE,'/baseline',{**{k:cur['ledger'][k] for k in ['release_id','source_sha','image_digest']},'progress_key':oid},timeout=90)
   update_round(eid,baseline=contract_summary(report))
   if not report['passed']:raise RuntimeError('真实业务基线验证未通过，请查看下单、金额和数据库检查结果')
   result=call(DELIVERY,'/ops/mark-good',{'verification_id':report['verification_id']})
   set_operation(oid,state='SUCCEEDED',stage='BASELINE_PASSED',result=result,verification=contract_summary(report),finished_at=now())
  else:
   cur=call(DELIVERY,'/ops/current',{})
   e=get('experiment',eid)
   baseline=e.get('baseline')
   if baseline and any(cur.get('ledger',{}).get(k)!=baseline.get(r) for k,r in [('release_id','release_id'),('source_sha','expected_source_sha'),('image_digest','expected_image_digest')]):raise RuntimeError('运行版本已在基线验证后发生变化，请重新验证正常基线，再制造故障')
   # Older CLI clients may start at fault. Reuse only a real, matching prior
   # contract report; never invent a baseline from a ready/running container.
   if not baseline:
    good=cur.get('known_good') or {}
    if good.get('verification_id'):
     previous=call(PROBE,'/reports/'+good['verification_id'])
     if previous and previous.get('passed') and all(cur['ledger'].get(k)==previous.get(r) for k,r in [('release_id','release_id'),('source_sha','expected_source_sha'),('image_digest','expected_image_digest')]):update_round(eid,baseline={**contract_summary(previous),'reused_previous_verified_baseline':True})
   result=call(DELIVERY,'/ops/fault',{},timeout=600);release=result['ledger']['release_id']
   update_round(eid,fault_release=release,fault_source_sha=result['ledger']['source_sha'],fault_published_at=now())
   set_operation(oid,stage='CONFIRMING_FAULT',result=result)
   deadline=time.monotonic()+40;found=None
   while time.monotonic()<deadline:
    rows=call(PROBE,'/observations?release_id='+release)
    found=next((r for r in rows if r['version_stable'] and r.get('version',{}).get('release_id')==release and r.get('version',{}).get('source_sha')==result['ledger']['source_sha'] and r['observed_at']>=started and any(q.get('path')=='no_coupon' and q.get('status')==500 for q in r['requests'])),None)
    if found:break
    time.sleep(.3)
   if not found:raise RuntimeError('故障版本已发布，但尚未取得该版本普通下单返回 500 的真实证据；请查看业务检测与事件，不能据此宣布故障已复现')
   update_round(eid,fault=found)
   for c in all_objects('case'):
    if c.get('observed_release')==release:
     attach_case(c)
     if c.get('verification',{}).get('passed'):record_recovery(c,c['verification'])
   set_operation(oid,state='SUCCEEDED',stage='FAULT_CONFIRMED',observation=found,finished_at=now())
 except Exception as exc:
  set_operation(oid,state='FAILED',error=str(exc)[:1000],next_step='查看技术详情和关联事件，确认当前业务与版本后再操作；已发生的发布和修复记录均保留。',finished_at=now())

def operation_summary(o):
 item={k:v for k,v in o.items() if k!='result'}
 if o['state']=='RUNNING' and o['action']=='baseline':
  try:item['progress']=call(PROBE,'/progress/'+o['id'],timeout=2)
  except Exception:item['progress_unavailable']=True
 return item

def business():
 try:
  observation=call(PROBE,'/observations/latest',timeout=3)
  if not observation:return {'state':'UNKNOWN','reason':'等待首次真实下单和数据库检测'}
  if now()-observation['observed_at']>12:return {**observation,'state':'UNKNOWN','reason':'业务检测已过期，等待新的实际采样','stale':True}
  return observation
 except Exception:return {'state':'UNKNOWN','reason':'暂时无法读取业务检测，不能判断业务正常'}

def overview():
 return {'business':business(),'experiments':rounds(),'operations':[operation_summary(o) for o in sorted(all_objects('operation'),key=lambda x:x['created_at'],reverse=True)[:12]],'cases':[case_summary(c) for c in sorted(all_objects('case'),key=lambda x:x['created_at'],reverse=True)]}

def interrupt_unfinished():
 for o in all_objects('operation'):
  if o['state'] not in DONE:set_operation(o['id'],state='INTERRUPTED',error='服务重启，操作结果需要核查；没有自动重放故障发布。',next_step='查看当前业务检测、关联事件和技术详情。')

async def worker():
 while True:
  for o in all_objects('operation'):
   if o['state']=='QUEUED':await asyncio.to_thread(run_operation,o['id'])
  await asyncio.sleep(.5)

def legacy(action):
 op=submit(action);run_operation(op['id']);o=get('operation',op['id'])
 while o['state'] not in DONE:
  time.sleep(.5);o=get('operation',op['id'])
 if o['state']!='SUCCEEDED':raise HTTPException(409,o.get('error','操作未完成'))
 return {**o['result'],'operation_id':o['id'],'experiment_id':o['experiment_id']}
