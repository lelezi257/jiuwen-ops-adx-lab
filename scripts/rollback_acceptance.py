#!/usr/bin/env python3
"""Controlled post-deploy failure for a NO-MODEL engineering acceptance case.
Run alongside engineering_acceptance.py, using its printed engineering case ID.
This stops only the dedicated lab order container after successful deployment.
"""
import argparse,json,subprocess,sys,time,urllib.request,http.client,urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--case-id',required=True);p.add_argument('--deadline-seconds',type=int,default=1800);a=p.parse_args()
client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def api(path):
 with client.open('http://127.0.0.1:19780'+path,timeout=15) as r:return json.load(r)
def docker(args):
 prefix=['limactl','shell','jiuwen-ops-adx-lab','--','sudo','docker'] if sys.platform=='darwin' else ['docker']
 return subprocess.check_output(prefix+args,text=True)
status=api('/api/status')
if status['runner']['model_configured']:raise SystemExit('Use a dedicated no-model engineering test, not an active real Agent experiment')
case=api('/api/cases/'+a.case_id)
if case.get('kind')!='engineering_acceptance':raise SystemExit('Only explicit engineering_acceptance cases are eligible')
path=root/'.local/evidence'/('rollback-'+a.case_id+'.json');path.parent.mkdir(parents=True,exist_ok=True)
report={'scope':'actual_negative_delivery_acceptance','case_id':a.case_id,'model_calls':0,'started_at':time.time(),'passed':False}
# Support resuming the development acceptance that used this generic receipt.
prior=root/'.local/evidence/rollback-injection.json'
if prior.exists():
 receipt=json.loads(prior.read_text())
 if receipt.get('case_id')==a.case_id:report['injection']=receipt
if path.exists():report=json.loads(path.read_text())
deadline=time.monotonic()+a.deadline_seconds;last=None
try:
 while time.monotonic()<deadline:
  try:case=api('/api/cases/'+a.case_id)
  except (urllib.error.URLError,http.client.HTTPException,TimeoutError):time.sleep(1);continue
  if case['state']!=last:print('Negative acceptance: '+case['state'],flush=True);last=case['state']
  if case['state']=='VERIFYING' and 'injection' not in report:
   info=json.loads(docker(['inspect','ops-adx-order-api']))[0]
   source=info['Config']['Labels']['org.opencontainers.image.revision']
   if source!=case['deployment']['runtime']['source_sha']:raise RuntimeError('Actual container differs from the case deployment')
   report['injection']={'fault':'stop deployed order container during VERIFYING','injected_at':time.time(),'container_id':info['Id'],'source_sha':source}
   path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
   docker(['stop','ops-adx-order-api']);print('Real order container stopped; waiting for controller rollback',flush=True)
  if case['state'] in ['RECOVERED_ROLLBACK','NEEDS_HUMAN','DELIVERY_ACCEPTANCE_PASSED','CANCELLED']:
   report['case']=case
   if case['state']!='RECOVERED_ROLLBACK' or not case.get('rollback_verification',{}).get('passed'):raise RuntimeError('Did not recover through independently verified rollback')
   if 'injection' not in report:raise RuntimeError('No controlled fault receipt')
   report['passed']=True;print('PASS: actual failed verification -> actual rollback -> business recovery. Not Agent repair success.');break
  time.sleep(1)
 else:raise RuntimeError('Negative acceptance deadline exceeded')
finally:
 report['finished_at']=time.time();path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print('Evidence: '+str(path))
