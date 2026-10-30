import hashlib,json,time
from fastapi import FastAPI,Depends,HTTPException
from lab.common import DATA,worker,either,ident,call,init_store,put,get
import httpx
app=FastAPI();init_store()
def evidence(source,query,value,case_id):
 eid=ident('ev');record={'evidence_id':eid,'source':source,'case_id':case_id,'observed_at':time.time(),'query':query,'query_hash':hashlib.sha256(json.dumps(query,sort_keys=True).encode()).hexdigest(),'data':value,'truncated':False}
 raw=json.dumps(record,ensure_ascii=False)
 if len(raw)>48000:record['data']=raw[:44000];record['truncated']=True
 put('evidence',eid,record);return record
@app.get('/health')
def health():return {'ok':True}
@app.post('/tools/{name}',dependencies=[Depends(worker)])
def tool(name:str,args:dict):
 with httpx.Client(timeout=20,trust_env=False) as c:
  if name=='query_metrics':
   query='sum by (path,status) (increase(order_requests_total[2m]))'
   r=c.get('http://prometheus:9090/api/v1/query',params={'query':query});r.raise_for_status();return evidence('prometheus',{'query':query},r.json(),args['case_id'])
  if name=='query_logs':
   end=time.time();start=max(end-900,float(args.get('start',end-300)))
   r=c.get('http://loki:3100/loki/api/v1/query_range',params={'query':'{service="order-api"}','start':str(int(start*1e9)),'end':str(int(end*1e9)),'limit':100,'direction':'backward'});r.raise_for_status();return evidence('loki',{'start':start,'end':end,'limit':100},r.json(),args['case_id'])
  if name=='get_running_release':return evidence('delivery+runtime',{},call('http://delivery:8080','/tools/get_running_release',args,role='runner'),args['case_id'])
  if name=='read_evidence':
   record=get('evidence',args.get('evidence_id',''))
   if not record:raise HTTPException(404,'evidence_not_found')
   return record
 raise HTTPException(404,'unknown_read_tool')
@app.get('/evidence/{eid}',dependencies=[Depends(either)])
def read(eid:str):
 r=get('evidence',eid)
 if not r:raise HTTPException(404,'evidence_not_found')
 return r
