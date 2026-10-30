#!/usr/bin/env python3
"""Run inside official-framework runner image. Never substitutes model output."""
import asyncio,json,os,sys,time
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lab.runner import client,configured,redact
async def main():
 report={'scope':'official_sdk_qualification','time':time.time(),'real_model_qualified':False}
 cli=client();cap=await cli.query('protocol.capabilities',deadline_seconds=90)
 assert cap['status']=='completed' and cap['data']['features']['host_tools'];report['capabilities']=cap
 modes=await cli.query('mode.list',deadline_seconds=120)
 assert modes['status']=='completed',modes
 report['runtime_modes']=modes
 invalid=await cli.run({'input':'Invalid limits must fail before model execution','max_turns':0},deadline_seconds=90)
 assert invalid['status']=='failed' and invalid['exit_code']==2,invalid
 report['invalid_request']=invalid
 if '--discovery-only' not in sys.argv:
  if not configured():raise SystemExit('Configure .local/model.env first. No model request was sent; no fake fallback.')
  calls=[];events=[];workspace=Path('/data/qualification');workspace.mkdir(parents=True,exist_ok=True)
  async def tool(event):
   assert event['event_type']=='host_tool.requested' and event['payload']['name']=='get_live_order_version'
   async with httpx.AsyncClient(timeout=20,trust_env=False) as c:
    r=await c.get('http://control:8080/api/status');r.raise_for_status();release=r.json()['release']
   assert release['consistent'];result={'source_sha':release['runtime']['source_sha'],'release_id':release['runtime']['release_id']};calls.append(result);return result
  async def event(e):events.append(e)
  request={'input':'Call get_live_order_version, then return the exact source_sha you observed and observed=true. Do not invent values.','agent':{'name':'ops-sdk-qualification','instructions':'Use the declared host tool. Final response must be only the JSON object required by output_schema.','tools':['get_live_order_version']},'host_tools':[{'name':'get_live_order_version','description':'Read actual running order container version through control service','input_schema':{'type':'object','properties':{},'additionalProperties':False}}],'permissions':{'tools':{'get_live_order_version':'allow'}},'workspace':{'cwd':str(workspace)},'max_turns':8,'timeout_seconds':180,'output_schema':{'type':'object','properties':{'source_sha':{'type':'string'},'observed':{'type':'boolean'}},'required':['source_sha','observed'],'additionalProperties':False}}
  if os.getenv('LAB_MAX_BUDGET_USD'):request['max_budget_usd']=float(os.environ['LAB_MAX_BUDGET_USD'])
  result=await cli.run(request,on_event=event,on_tool_call=tool,deadline_seconds=300)
  assert result['status']=='completed' and result['exit_code']==0 and calls,result
  assert result['output_json']=={'source_sha':calls[-1]['source_sha'],'observed':True},result
  report.update(real_model_qualified=True,tool_effects=calls,result=result,events=events)
  if '--lifecycle' in sys.argv:
   cancel=asyncio.Event()
   async def tool_and_cancel(e):
    result=await tool(e);cancel.set();return result
   cancelled=await cli.run(request,on_tool_call=tool_and_cancel,cancel=cancel,deadline_seconds=300)
   assert cancelled['status']=='cancelled' and cancelled['exit_code']==130,cancelled
   report['cancelled_run']=cancelled
 output=Path('/data/qualification');output.mkdir(parents=True,exist_ok=True)
 (output/'report.json').write_text(json.dumps(redact(report),ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(redact(report),ensure_ascii=False,indent=2))
asyncio.run(main())
