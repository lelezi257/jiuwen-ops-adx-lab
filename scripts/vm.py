#!/usr/bin/env python3
"""Create only the dedicated lab VM. No host directory mounts."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
name='jiuwen-ops-adx-lab'
config=json.loads((root/'deploy/lima.yaml').read_text())
image=os.environ.get('LAB_VM_IMAGE')
if image:
 p=Path(image).resolve()
 config['images']=[{'location':p.as_uri(),'arch':'aarch64','digest':'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()}]
local=root/'.local';local.mkdir(exist_ok=True)
path=local/'lima.generated.yaml';path.write_text(json.dumps(config,indent=2))
existing=subprocess.run(['limactl','list','--json'],capture_output=True,text=True,check=True)
names=[json.loads(x)['name'] for x in existing.stdout.splitlines() if x.strip()]
if name not in names:
 subprocess.run(['limactl','create','--tty=false','--name='+name,str(path)],check=True)
subprocess.run(['limactl','start','--tty=false',name],check=True)
print('VM ready: '+name+'; next: scripts/lab vm-sync')
