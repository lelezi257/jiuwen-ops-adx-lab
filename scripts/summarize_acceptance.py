#!/usr/bin/env python3
"""Publish selected fields from real receipts; never changes cases or runs models."""
import argparse,json,time,urllib.request
from pathlib import Path

p=argparse.ArgumentParser()
p.add_argument('--case',action='append',required=True,dest='cases')
p.add_argument('--output',required=True)
p.add_argument('--base-url',default='http://127.0.0.1:19780')
a=p.parse_args()
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def read(path):
 with client.open(a.base_url+path,timeout=60) as r:return json.load(r)
def verification(report):
 if not report:return None
 result={k:report.get(k) for k in ['verification_id','release_id','expected_source_sha','expected_image_digest','started_at','finished_at','contract','before','after','passed','old_order_ok','invalid_input_ok']}
 result['windows']=[]
 for w in report['windows']:
  rows=w['requests']
  result['windows'].append({**{k:w[k] for k in ['start','end','counts','passed']},'all_database_rows_match':bool(rows) and all(r.get('database_row')==[r.get('order_id'),2,r.get('total_cents')] and r.get('ok') for r in rows),'failed_requests':sum(not r.get('ok') for r in rows)})
 return result

cases=[]
for cid in a.cases:
 case=read('/api/cases/'+cid);events=read('/api/cases/'+cid+'/events')
 runs={};phase=None;started=None;first_agent=None;effects=[];timeline=[]
 for event in events:
  kind=event['kind'];data=event['data'];at=event['time']
  if kind=='run.request':
   phase=json.loads(data['input']).get('phase');started=at
   if first_agent is None:first_agent=at
  if kind=='state':timeline.append({'at':at,'state':data['state']})
  if kind=='sdk_result':
   rid=data.get('request_id')
   if rid:runs[rid]={'request_id':rid,'session_id':data.get('session_id'),'phase':phase,'started_at':started,'received_at':at,'status':data.get('status'),'exit_code':data.get('exit_code'),'error_code':(data.get('error') or {}).get('code'),'usage':data.get('usage'),'output_json':data.get('output_json')}
  if kind=='host_tool.executed':
   result=data['result'];effect={'at':at,'tool':data['name']}
   if isinstance(result,dict):effect.update({k:result[k] for k in ['evidence_id','test_id','passed','tree_hash','number','url','head_sha','base_sha','path','sha256'] if k in result})
   effects.append(effect)
 stages={}
 for i,state in enumerate(timeline):
  end=timeline[i+1]['at'] if i+1<len(timeline) else case['updated_at']
  stages[state['state']]=round(stages.get(state['state'],0)+max(0,end-state['at']),3)
 usage=[r['usage'] for r in runs.values()]
 totals={k:sum(u[k] for u in usage) if usage and all(isinstance(u,dict) and isinstance(u.get(k),(int,float)) for u in usage) else None for k in ['model_calls','input_tokens','output_tokens','total_tokens','total_cost']}
 first=lambda name:next((e['at'] for e in effects if e['tool']==name),None)
 summary={k:case.get(k) for k in ['id','created_at','updated_at','state','attempt','observed_release','observed_sha','pr','ci','merge','build']}
 trigger=case.get('trigger') or {}
 summary['trigger']={'source':trigger.get('source'),'alerts':[{k:alert.get(k) for k in ['status','labels','startsAt']} for alert in trigger.get('alerts',[])]}
 summary['operator_retry_count']=sum(e['kind']=='state' and isinstance(e['data'].get('detail'),str) and e['data']['detail'].startswith('Operator requested new attempt') for e in events)
 summary['controller_error_count']=sum(e['kind']=='controller_error' for e in events)
 summary['repair_runs']=sum(r['phase']=='repair' for r in runs.values())
 summary['verification_runs']=sum(r['phase']=='verify' for r in runs.values())
 incident=((case.get('deployment') or {}).get('ledger') or {}).get('previous') or {}
 summary['incident_runtime']=({k:incident.get(k) for k in ['release_id','source_sha','image_digest','time']} if incident.get('release_id')==case['observed_release'] else None)
 summary['detection_delay_seconds']=round(case['created_at']-incident['time'],3) if summary['incident_runtime'] and incident.get('time') else None
 summary.update(patch_author='real_model_via_official_jiuwen',first_agent_request_at=first_agent,end_to_end_seconds=round(case['updated_at']-case['created_at'],3),after_model_start_seconds=round(case['updated_at']-first_agent,3) if first_agent else None,diagnostic_first_at=first('query_logs'),pr_first_at=first('create_pull_request'),timeline=timeline,state_seconds=stages,model_runs=list(runs.values()),reported_usage_totals=totals,unknown_usage_fields=[k for k,v in totals.items() if v is None],tool_effects=effects,verification=verification(case.get('verification')),rollback_verification=verification(case.get('rollback_verification')),deployment_runtime=(case.get('deployment') or {}).get('runtime'))
 cases.append(summary)
report={'scope':'controlled_real_model_agent_cases','recorded_at':time.time(),'cases':cases,'passed':all(c['state']=='RESOLVED_FIXED' and c.get('verification',{}).get('passed') for c in cases),'note':'All listed attempts and failures are retained. Not a general AIOps success-rate benchmark. Unknown usage is null, not zero; total_cost is only the model provider/framework reported amount.'}
path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(path),'cases':len(cases),'passed':report['passed']}))
