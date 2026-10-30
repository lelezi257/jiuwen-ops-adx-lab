#!/usr/bin/env python3
"""Read-only evidence collector for one actual baseline/fault/recovery round."""
import argparse,json,time,urllib.request
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('experiment_id');p.add_argument('--deadline',type=int,default=2400);a=p.parse_args()
root=Path(__file__).resolve().parents[1];target=root/'.local/evidence/experience-ui'/('round-'+a.experiment_id+'.json');target.parent.mkdir(parents=True,exist_ok=True)
client=urllib.request.build_opener(urllib.request.ProxyHandler({}));report={'experiment_id':a.experiment_id,'started_at':time.time(),'samples':[],'passed':False};last=None
if target.exists():
 previous=json.loads(target.read_text())
 if previous.get('experiment_id')==a.experiment_id and not previous.get('finished_at'):
  report=previous;report.setdefault('collector_resumed_at',[]).append(time.time())
end=time.monotonic()+a.deadline
while time.monotonic()<end:
 try:
  with client.open('http://127.0.0.1:19780/api/overview',timeout=20) as r:data=json.load(r)
 except Exception as exc:
  report.setdefault('read_errors',[]).append({'at':time.time(),'error':type(exc).__name__});target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');time.sleep(1);continue
 e=next(x for x in data['experiments'] if x['id']==a.experiment_id);c=next((x for x in data['cases'] if x['id']==e.get('case_id')),None);ops=[x for x in data['operations'] if x['experiment_id']==e['id']]
 sample={'at':time.time(),'business':data['business'],'operations':ops,'case':c};report['samples'].append(sample);report['experiment']=e
 signature=(data['business']['state'],tuple((o['action'],o['state'],o['stage']) for o in ops),c['state'] if c else None,tuple(x['session_id'] for x in ((c or {}).get('sdk_runs') or {}).values()))
 if signature!=last:print(json.dumps({'business':signature[0],'operations':signature[1],'case_state':signature[2],'sessions':signature[3]},ensure_ascii=False),flush=True);last=signature
 if c and c['state'] in ['RESOLVED_FIXED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED']:
  report['finished_at']=time.time();report['passed']=bool(c['state']=='RESOLVED_FIXED' and (e.get('baseline') or {}).get('passed') and e.get('fault') and (e.get('recovery') or {}).get('passed'))
  target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence: '+str(target),flush=True)
  if not report['passed']:raise SystemExit('Round did not meet full acceptance')
  break
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');time.sleep(1)
else:raise SystemExit('Observation deadline; real records retained')
