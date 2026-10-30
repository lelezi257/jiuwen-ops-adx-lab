#!/usr/bin/env python3
import json,subprocess,time,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];env=root/'.local/runtime.env'
config=dict(line.split('=',1) for line in env.read_text().splitlines() if line and not line.startswith('#'))
sha=config['LAB_TRUST_SHA'];tag='localhost:5000/jiuwen-adx-order:'+sha
for _ in range(60):
 try:
  urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:5000/v2/',timeout=2).close();break
 except Exception:time.sleep(1)
subprocess.run(['docker','tag','jiuwen-adx-order:bootstrap',tag],check=True)
subprocess.run(['docker','push',tag],check=True)
meta=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]
digest=next(d for d in meta['RepoDigests'] if d.startswith('localhost:5000/jiuwen-adx-order@'))
for _ in range(60):
 try:
  urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:19780/health',timeout=2).close();break
 except Exception:time.sleep(1)
request=urllib.request.Request('http://127.0.0.1:19780/api/experiment/bootstrap',data=json.dumps({'source_sha':sha,'image_digest':digest}).encode(),headers={'Authorization':'Bearer '+(root/'.local/secrets/control_token').read_text().strip(),'Content-Type':'application/json'},method='POST')
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=240) as response:result=json.load(response)
lines=[x for x in env.read_text().splitlines() if not x.startswith('ORDER_IMAGE=')];env.write_text('\n'.join([*lines,'ORDER_IMAGE='+digest])+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
