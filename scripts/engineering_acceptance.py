#!/usr/bin/env python3
"""No model involved: exercise real broker / PR / CI / release with a human patch.
Run INSIDE dedicated VM with sudo after a verified baseline + real fault.
This script never synthesizes an SDK result or claims Agent success.
"""
import json,sys,threading,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def request(base,path,body=None,role='control'):
 token=(root/'.local/secrets'/(role+'_token')).read_text().strip();data=json.dumps(body).encode() if body is not None else None
 r=urllib.request.Request(base+path,data=data,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST' if body is not None else 'GET')
 try:
  with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(r,timeout=600) as response:return json.load(response)
 except __import__('urllib.error').error.HTTPError as exc:raise RuntimeError(exc.read().decode()) from exc
control='http://127.0.0.1:19780'
# Tools are not exposed on host ports; exec this script in a temporary runtime
# container on the ops network, mounting ONLY the local identity directory.
if '--in-container' not in sys.argv:
 import subprocess
 subprocess.run(['docker','run','--rm','--network','jiuwen-ops-adx-lab_ops','-v',str(root/'scripts/engineering_acceptance.py')+':/checkout/scripts/engineering_acceptance.py:ro','-v',str(root/'.local/secrets/control_token')+':/checkout/.local/secrets/control_token:ro','-v',str(root/'.local/secrets/runner_token')+':/checkout/.local/secrets/runner_token:ro','-w','/checkout','jiuwen-ops-runtime:local','python','scripts/engineering_acceptance.py','--in-container'],check=True);raise SystemExit
control='http://control:8080'
for c in request(control,'/api/cases'):
 if c['state'] not in ['RESOLVED_FIXED','DELIVERY_ACCEPTANCE_PASSED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED','NO_ACTION','TRACE_PROBE_COMPLETED']:request(control,'/api/cases/'+c['id']+'/cancel',{})
c=request(control,'/api/engineering/start',{});cid=c['id'];print('ENGINEERING ACCEPTANCE ONLY; no model: '+cid,flush=True)
stop=threading.Event()
def heartbeat():
 while not stop.wait(10):
  try:request(control,'/internal/cases/'+cid+'/heartbeat',{'attempt_id':c['attempt_id']},'runner')
  except Exception:return
threading.Thread(target=heartbeat,daemon=True).start()
def tool(name,args=None):return request('http://delivery:8080','/tools/'+name,{'case_id':cid,**(args or {})},'runner')
try:
 tool('create_workspace');source=tool('read_source',{'path':'apps/order_api/pricing.py'})
 fixed=source['content'].replace('normalized = coupon.strip().upper()',"normalized = (coupon or '').strip().upper()")
 if fixed==source['content']:raise RuntimeError('Expected controlled fault not present; do not guess another patch')
 tool('write_source',{'path':'apps/order_api/pricing.py','content':fixed,'expected_sha256':source['sha256']})
 test="import sys,unittest\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/order_api'))\nfrom pricing import total_cents\nclass OptionalCouponRegression(unittest.TestCase):\n def test_optional_coupon(self):self.assertEqual(total_cents(2,None),20000)\n def test_discount(self):self.assertEqual(total_cents(2,'SAVE10'),18000)\n"
 tool('write_source',{'path':'tests/order/test_'+cid.replace('-','_')+'.py','content':test,'expected_sha256':None})
 result=tool('run_tests');print(json.dumps(result,ensure_ascii=False),flush=True)
 if not result['passed']:raise RuntimeError('Trusted business tests failed')
 pr=tool('create_pull_request',{'summary':'Engineering acceptance with an explicitly human-authored patch. No model / Agent success claimed.'});print(json.dumps(pr),flush=True)
 request(control,'/api/engineering/'+cid+'/submit',{});stop.set()
 while True:
  c=request(control,'/api/cases/'+cid);print(c['state'],flush=True)
  if c['state'] in ['DELIVERY_ACCEPTANCE_PASSED','NEEDS_HUMAN','RECOVERED_ROLLBACK','CANCELLED']:break
  time.sleep(10)
 if c['state']!='DELIVERY_ACCEPTANCE_PASSED':raise RuntimeError('Engineering acceptance did not pass: '+json.dumps(c))
 print('PASS: actual PR/CI/merge/build/digest/deployment/business recovery; real Agent still pending',flush=True)
finally:stop.set()
