#!/usr/bin/env python3
"""Create local-only configuration and identities; never print credentials."""
import os,secrets,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];local=r/'.local';local.mkdir(exist_ok=True);local.chmod(0o700)
for d in ['secrets','swarm','evidence']:
 (local/d).mkdir(exist_ok=True);(local/d).chmod(0o700)
for name in ['control_token','runner_token','db_password','verify_db_password']:
 p=local/'secrets'/name
 if not p.exists():p.write_text(secrets.token_hex(32)+'\n')
 p.chmod(0o644 if name in ['db_password','verify_db_password'] else 0o600)
for name in ['model','lab']:
 p=local/(name+'.env')
 if not p.exists():shutil.copyfile(r/'config'/(name+'.env.example'),p)
 p.chmod(0o600)
p=local/'secrets/github_token'
if not p.exists():p.write_text('')
p.chmod(0o600)
config=local/'swarm/config.yaml'
if not config.exists():shutil.copyfile(r/'config/swarm.yaml',config)
if '--github' in __import__('sys').argv:
 result=subprocess.run(['gh','auth','token'],capture_output=True,text=True,check=True)
 p.write_text(result.stdout.strip()+'\n');p.chmod(0o600)
print('Local-only templates and identities ready. No credentials printed.')
