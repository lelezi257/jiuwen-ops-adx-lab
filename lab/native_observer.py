"""Read-only transport for the UNMODIFIED, pinned Jiuwen native WebUI.

The SDK owns all execution. Native Core -> native SQLite -> native reader ->
native HTTP -> native frontend. This adapter only selects existing sessions and
notifies their committed watermarks; it cannot execute, edit or configure agents.
"""
import asyncio,json,logging,os
import httpx
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,WebSocket,Request,HTTPException
from gateway.common.security.ws_origin import is_allowed_browser_origin
from gateway.channel_manager.base import RobotMessageRouter
from gateway.channel_manager.web.web_connect import WebChannel,WebChannelConfig
from gateway.channel_manager.web.web_channel_app import _serve_channel_websocket
from gateway.channel_manager.web.trajectory_http import attach_trajectory_routes
from gateway.common.protocol_ids import validate_session_id
from jiuwenswarm.observability.config import TrajectoryStoreSettings
from jiuwenswarm.server.trajectory.host import TrajectoryHost
from jiuwenswarm.server.runtime.session.session_metadata import get_session_metadata_async
from jiuwenswarm.server.runtime.session.session_info import to_session_info
from jiuwenswarm.server.control.history_service import load_history_query,stream_history_records

log=logging.getLogger(__name__)
ROOT=Path(os.environ.get('JIUWENSWARM_DATA_DIR','/observer/state'))
RECORDINGS=Path(os.environ.get('LAB_RECORDINGS','/recordings/swarm'))
from lab.recording_index import RecordingIndex
index=RecordingIndex(RECORDINGS,ROOT)

async def metadata(sid,user_id=None):
 validate_session_id(sid)
 if not index.exists(sid):raise ValueError('Official Session not found')
 return await index.read('metadata',sid)

class ReadOnlyChannel(WebChannel):
 async def _handle_raw_message(self,ws,raw,query):
  req={}
  try:
   req=json.loads(raw)
   if not isinstance(req,dict) or req.get('type')!='req' or not isinstance(req.get('id'),str):raise ValueError('Invalid request')
   method=req.get('method');params=req.get('params') or {}
   if not isinstance(params,dict):raise ValueError('Invalid params')
   if method not in READ_METHODS:
    log.info('Read-only observer rejected RPC %s',method)
    await self.send_response(ws,req['id'],ok=False,error='Read-only SDK observer: this operation is not available',code='OBSERVER_READ_ONLY');return
   sid=params.get('session_id')
   if sid:
    validate_session_id(sid)
    if not index.exists(sid):raise ValueError('SDK session not found')
    ws._observer_sid=sid
   value=await dispatch(method,params,ws,req['id'])
   await self.send_response(ws,req['id'],ok=True,payload=value)
  except Exception as exc:
   log.warning('Observer RPC %s failed: %s',req.get('method') if isinstance(req,dict) else '',exc)
   await self.send_response(ws,req.get('id','') if isinstance(req,dict) else '',ok=False,error=str(exc)[:300],code='OBSERVER_READ_ERROR')

READ_METHODS={'config.get','models.list','session.list','session.get_metadata','session.switch','history.get'}
channel=ReadOnlyChannel(WebChannelConfig(enabled=True,host='0.0.0.0',port=8081,path='/ws'),RobotMessageRouter())

async def dispatch(method,p,ws,req_id):
 if method=='config.get':
  return {'setup_guide_enabled':False,'trajectory_ui_diagnosis_enabled':True,'rsi_enabled':False,'a2ui_enabled':False,'multi_model_collaboration_enabled':False,'preferred_language':'zh','observer_read_only':True}
 if method=='models.list':return {'models':[],'active_model':None}
 if method=='session.list':
  items=[]
  index.refresh()
  for path in sorted(index.paths.values(),key=lambda x:x.stat().st_mtime,reverse=True):
   if not path.is_dir():continue
   try:
    item=await metadata(path.name)
    if item and (not p.get('work_mode') or item.get('work_mode')==p['work_mode']):items.append(to_session_info(item))
   except Exception:log.debug('Unreadable session %s',path.name,exc_info=True)
  offset=max(0,int(p.get('offset',0)));limit=min(100,max(1,int(p.get('limit',20))))
  return {'sessions':items[offset:offset+limit],'total':len(items),'offset':offset,'limit':limit}
 sid=p.get('session_id')
 if not sid:raise ValueError('session_id required')
 if method=='session.get_metadata':return await metadata(sid)
 if method=='session.switch':return {'session_id':sid,**(await metadata(sid))}
 if method=='history.get':
  batch=await index.read('history',sid,p)
  if batch is None:raise ValueError('Durable history not available yet; retry when writer commits')
  common={k:v for k,v in batch.items() if k!='messages'}
  common.update(session_id=sid,cursor=p.get('cursor'),request_id=req_id)
  for sequence,record in enumerate(stream_history_records(batch.get('messages',[]),use_split=True)):
   await channel.send_event(ws,'history.message',{**common,'message':record},seq=sequence,stream_id=req_id)
  await channel.send_event(ws,'history.message',{**common,'status':'done'},stream_id=req_id)
  return {'session_id':sid,'streamed':True}
 raise ValueError('Unsupported read')

async def connected(ws):
 await channel.send_event(ws,'connection.ack',{'protocol_version':'1.0','transport':'web','observer_read_only':True})
channel.on_connect(connected)

async def watch():
 seen={}
 while True:
  for ws in list(channel.clients):
   sid=getattr(ws,'_observer_sid',None)
   if not sid:continue
   try:
    owned=index.host(sid)
    reader=owned.reader_for(owned.settings)
    items,epoch,watermark=await reader.list_subjects(sid,after_revision=0)
    frames=await reader.get_stream_frames(sid,since_frame_seq=0,limit=1)
    frame_seq=(frames or {}).get('frame_seq',0)
    if not isinstance(frame_seq,int):frame_seq=(frames or {}).get('last_frame_seq',0)
    stamp=(epoch,watermark,frame_seq)
    if seen.get((id(ws),sid))==stamp:continue
    seen[(id(ws),sid)]=stamp
    for item in items:
     page=await reader.get_subject_records(sid,item['subject_id'],since_revision=0,limit=1)
     records=(page or {}).get('records',[])
     if not records:continue
     trace_id=records[0].get('trace_id')
     if not trace_id:continue
     await channel.send_event(ws,'trace.updated',{'session_id':sid,'trace_id':trace_id,'revision':watermark,'frame_seq':frame_seq,'store_epoch':epoch})
   except Exception:log.debug('Native watermark read failed for %s',sid,exc_info=True)
  active={id(ws) for ws in channel.clients};seen={k:v for k,v in seen.items() if k[0] in active}
  await asyncio.sleep(.5)

@asynccontextmanager
async def lifespan(app):
 task=asyncio.create_task(watch())
 try:yield
 finally:
  task.cancel();index.close()
app=FastAPI(lifespan=lifespan)
attach_trajectory_routes(app,channel,metadata_loader=metadata,fetch=index.call)
@app.get('/api/ops/state')
async def ops_state(request:Request):
 origin=request.headers.get('origin')
 if origin and not is_allowed_browser_origin(origin):raise HTTPException(403,'Origin not allowed')
 async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
  response=await client.get('http://control:8080/api/overview');response.raise_for_status();return response.json()
@app.get('/api/ops/session-ready/{sid}')
async def session_ready(sid:str):
 validate_session_id(sid)
 if not index.exists(sid):return {'ready':False,'session_id':sid}
 item=await metadata(sid)
 return {'ready':bool(item),'session_id':sid}
@app.websocket('/ws')
async def websocket(ws:WebSocket):await _serve_channel_websocket(channel,ws)
@app.get('/health')
def health():return {'ok':True,'role':'native-webui-read-only-sdk-observer','native_frontend':'32d75d7d3a0b466412ee64d77c29460297515119','execution_backend':False,'recordings_read_only':True}

@app.get('/api/ops/recordings-ready/{cid}')
async def recordings_ready(cid:str):
 async with httpx.AsyncClient(timeout=10,trust_env=False) as client:
  response=await client.get('http://control:8080/api/cases/'+cid)
  response.raise_for_status();case=response.json()
 runs=list((case.get('sdk_runs') or {}).values());checks=[]
 for run in runs:
  sid=run['session_id']
  if not index.exists(sid):return {'ready':False,'sessions':checks}
  if index.owners[sid].parent.name!=cid:raise HTTPException(409,'Session belongs to another case recording root')
  item=await metadata(sid);owned=index.host(sid)
  subjects,epoch,revision=await owned.reader_for(owned.settings).list_subjects(sid,after_revision=0)
  checks.append({'session_id':sid,'metadata':bool(item),'subjects':len(subjects),'revision':revision,'store_epoch':epoch})
 return {'ready':bool(checks) and all(x['metadata'] and x['subjects']>0 and x['revision']>0 for x in checks),'sessions':checks}
