#!/usr/bin/env python3
"""Observe real Agent cases; never authors patches, fakes tools or SDK results."""
import argparse,json,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--trials',type=int,choices=[1,2,3],default=1);p.add_argument('--deadline-seconds',type=int,default=3600);args=p.parse_args()
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(path,body=None):
 token=(root/'.local/secrets/control_token').read_text().strip()
 request=urllib.request.Request('http://127.0.0.1:19780'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST' if body is not None else 'GET')
 with client.open(request,timeout=650) as r:return json.load(r)
status=api('/api/status')
if not status['runner'].get('model_configured'):raise SystemExit('Model not configured. No fault, patch, PR or model call was made by this command.')
report={'scope':'real_model_agent_acceptance','started_at':time.time(),'requested_trials':args.trials,'trials':[],'errors':[],'passed':False}
path=root/'.local/evidence'/('agent-acceptance-'+str(int(time.time()))+'.json');path.parent.mkdir(parents=True,exist_ok=True)
terminal={'RESOLVED_FIXED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED','NO_ACTION','TRACE_PROBE_COMPLETED'}
try:
 for n in range(args.trials):
  current=api('/api/status')['release']['ledger'];cases=api('/api/cases')
  active=[c for c in cases if c.get('kind')!='engineering_acceptance' and c['state'] not in terminal]
  fresh_reset=not active
  if active:case=active[0]
  else:
   api('/api/experiment/fault',{});case=None;start=time.time()
   while time.time()-start<180:
    candidates=[c for c in api('/api/cases') if c.get('kind')!='engineering_acceptance' and c['state'] not in terminal and c['created_at']>=start-5]
    if candidates:case=candidates[0];break
    time.sleep(2)
   if case is None:raise RuntimeError('Actual Alertmanager event did not arrive')
  cid=case['id'];deadline=time.monotonic()+args.deadline_seconds
  while time.monotonic()<deadline:
   case=api('/api/cases/'+cid);print(f'trial {n+1}: {cid}: '+case['state'],flush=True)
   if case['state'] in terminal:break
   time.sleep(5)
  report['trials'].append({**case,'fresh_reset':fresh_reset})
  if case['state'] not in terminal:raise RuntimeError('Case still active at observation deadline; do not create another fault')
  if case['state']!='RESOLVED_FIXED':report['errors'].append({'case_id':cid,'error':'Real Agent terminal state: '+case['state']})
  elif not case.get('verification',{}).get('passed') or case.get('agent_result',{}).get('status')!='completed':report['errors'].append({'case_id':cid,'error':'Missing actual SDK or business verification evidence'})
 report['passed']=not report['errors']
finally:
 report['finished_at']=time.time();path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence: '+str(path))
if not report['passed']:raise SystemExit(1)
