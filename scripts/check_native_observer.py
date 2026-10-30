#!/usr/bin/env python3
"""Exercise the real native observer socket and its read-only boundaries.

Run inside native-web with an existing SDK SessionID. Makes no model calls.
"""
import argparse,asyncio,json,os
from pathlib import Path
import httpx
import websockets
p=argparse.ArgumentParser();p.add_argument('session_id');a=p.parse_args()
async def main():
 assert not os.environ.get('API_KEY') and not Path('/run/secrets/github_token').exists()
 assert not Path('/var/run/docker.sock').exists()
 report={'session_id':a.session_id,'checks':{},'native_hints':[]}
 async with websockets.connect('ws://127.0.0.1:8081/ws',origin='http://127.0.0.1:19781') as ws:
  ack=json.loads(await asyncio.wait_for(ws.recv(),10));assert ack.get('event')=='connection.ack'
  async def rpc(method,params):
   await ws.send(json.dumps({'type':'req','id':method,'method':method,'params':params}))
   while True:
    frame=json.loads(await asyncio.wait_for(ws.recv(),15))
    if frame.get('event')=='trace.updated':report['native_hints'].append(frame['payload'])
    if frame.get('type')=='res' and frame.get('id')==method:return frame
  meta=await rpc('session.get_metadata',{'session_id':a.session_id});assert meta['ok'] and meta['payload']['session_id']==a.session_id
  report['checks']['actual_session_metadata']=True
  for method in ['chat.send','config.set','session.delete']:
   response=await rpc(method,{'session_id':a.session_id})
   assert not response['ok'] and response['code']=='OBSERVER_READ_ONLY',response
   report['checks'][method+'_rejected']=True
  bad=await rpc('session.get_metadata',{'session_id':'../../outside'});assert not bad['ok']
  report['checks']['invalid_session_rejected']=True
  until=asyncio.get_running_loop().time()+5
  while not report['native_hints'] and asyncio.get_running_loop().time()<until:
   frame=json.loads(await asyncio.wait_for(ws.recv(),5))
   if frame.get('event')=='trace.updated':report['native_hints'].append(frame['payload'])
 assert report['native_hints'],'No native commit watermark was delivered'
 async with httpx.AsyncClient(trust_env=False) as client:
  url='http://127.0.0.1:8081/api/trajectory/sessions/'+a.session_id+'/subjects'
  r=await client.get(url);r.raise_for_status();subjects=r.json()
  assert any(x['revision']<=subjects['watermark'] and x['store_epoch']==subjects['store_epoch'] for x in report['native_hints'])
  report['checks']['hint_matches_native_store']=True
  bad=await client.get(url+'?after_revision=-1');assert bad.status_code==400
  report['checks']['negative_revision_rejected']=True
  foreign=await client.get(url,headers={'Origin':'https://foreign.invalid'});assert foreign.status_code==403
  report['checks']['foreign_origin_rejected']=True
 try:
  async with websockets.connect('ws://127.0.0.1:8081/ws',origin='https://foreign.invalid'):
   raise AssertionError('Foreign WebSocket was accepted')
 except websockets.exceptions.InvalidStatus as exc:
  assert exc.response.status_code==403
 report['checks']['foreign_websocket_rejected']=True
 report['checks']['observer_has_no_execution_credentials']=True
 report['passed']=True
 print(json.dumps(report,ensure_ascii=False,indent=2))
asyncio.run(main())
