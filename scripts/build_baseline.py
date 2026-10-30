#!/usr/bin/env python3
import os,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
config=dict(line.split('=',1) for line in (root/'.local/runtime.env').read_text().splitlines() if line and not line.startswith('#'))
args=['docker','build','-f','deploy/Order.Dockerfile','--build-arg','SOURCE_SHA='+config['LAB_TRUST_SHA'],'-t','jiuwen-adx-order:bootstrap']
for key in ['PYTHON_BASE','PIP_INDEX_URL','UV_INDEX_URL','APT_MIRROR_SITE','HTTP_PROXY','HTTPS_PROXY','NO_PROXY']:
 value=os.getenv(key) or config.get(key)
 if value:args+=['--build-arg',key+'='+value]
subprocess.run([*args,'.'],cwd=root,check=True)
