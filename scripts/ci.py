#!/usr/bin/env python3
"""Run candidate in disposable containers. No candidate Python runs on host."""
import argparse,json,os,secrets,subprocess,tempfile,time,uuid
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--candidate',default='.');p.add_argument('--trusted',default='.');p.add_argument('--oracle-host-path');p.add_argument('--candidate-volume');a=p.parse_args()
candidate=Path(a.candidate).resolve();trusted=Path(a.trusted).resolve();tag='lab-test-'+uuid.uuid4().hex[:10];net=tag;password=secrets.token_hex(20)
deadline=time.monotonic()+240
def run(argv,**kw):
 limit=kw.pop('timeout',180)
 return subprocess.run(argv,check=True,timeout=max(.1,min(limit,deadline-time.monotonic())),**kw)
try:
 run(['docker','network','create','--internal',net],stdout=subprocess.DEVNULL)
 options=[]
 for key in ['PYTHON_BASE','PIP_INDEX_URL','APT_MIRROR_SITE','HTTP_PROXY','HTTPS_PROXY','NO_PROXY']:
  if os.getenv(key):options+=['--build-arg',key+'='+os.environ[key]]
 run(['docker','build',*options,'-f',str(trusted/'deploy/Order.Dockerfile'),'-t',tag,str(candidate)])
 with tempfile.TemporaryDirectory() as temp:
  secret=Path(temp)/'password';secret.write_text(password);secret.chmod(0o644)
  run(['docker','run','-d','--memory','512m','--cpus','1','--pids-limit','128','--name',tag+'-db','--network',net,'--network-alias','db','-e','POSTGRES_USER=orders','-e','POSTGRES_DB=orders','-e','POSTGRES_PASSWORD='+password,'postgres:16.9-alpine'],stdout=subprocess.DEVNULL)
  for _ in range(40):
   if time.monotonic()>=deadline:raise TimeoutError('Candidate test deadline')
   r=subprocess.run(['docker','exec',tag+'-db','pg_isready','-U','orders','-t','1'],capture_output=True,timeout=5)
   if r.returncode==0:break
   time.sleep(1)
  run(['docker','run','-d','--memory','256m','--cpus','1','--pids-limit','128','--name',tag+'-app','--network',net,'--network-alias','candidate','--read-only','--tmpfs','/tmp','--tmpfs','/logs','-e','DB_PASSWORD='+password,tag],stdout=subprocess.DEVNULL)
  # Oracle code comes from the trusted checkout, mounted read-only.
  for _ in range(40):
   if time.monotonic()>=deadline:raise TimeoutError('Candidate test deadline')
   r=subprocess.run(['docker','exec',tag+'-app','python','-c',"import urllib.request;urllib.request.urlopen('http://localhost:8080/health',timeout=2)"],capture_output=True,timeout=5)
   if r.returncode==0:break
   time.sleep(1)
  run(['docker','run','--rm','--name',tag+'-oracle','--memory','256m','--cpus','1','--pids-limit','128','--network',net,'--read-only','--tmpfs','/tmp','-e','CONTRACT_DB_PASSWORD='+password,'--mount',f"type=bind,src={a.oracle_host_path or str(trusted/'contracts')},dst=/oracle,readonly",tag,'python','/oracle/check_http.py','http://candidate:8080'])
  mount='type=volume,src='+a.candidate_volume+',dst=/work,readonly' if a.candidate_volume else f'type=bind,src={candidate},dst=/candidate,readonly'
  cwd=str(candidate) if a.candidate_volume else '/candidate'
  run(['docker','run','--rm','--name',tag+'-unit','--memory','256m','--cpus','1','--pids-limit','128','--network','none','--read-only','--tmpfs','/tmp','--mount',mount,'-w',cwd,tag,'python','-m','unittest','discover','-s','tests/order','-v'],timeout=60)
finally:
 for name in [tag+'-app',tag+'-db',tag+'-oracle',tag+'-unit']:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
 subprocess.run(['docker','network','rm',net],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
 subprocess.run(['docker','image','rm',tag],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
