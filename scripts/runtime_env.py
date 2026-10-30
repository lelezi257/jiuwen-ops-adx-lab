#!/usr/bin/env python3
import re,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];sha=sys.argv[1]
assert re.fullmatch('[0-9a-f]{40}',sha)
(root/'.local/evidence').mkdir(parents=True,exist_ok=True)
p=root/'.local/runtime.env';lines=p.read_text().splitlines() if p.exists() else []
lines=[x for x in lines if not x.startswith(('HOST_REPO=','LAB_TRUST_SHA='))]
p.write_text('\n'.join(['HOST_REPO='+str(root),'LAB_TRUST_SHA='+sha,*lines])+'\n');p.chmod(0o600)
