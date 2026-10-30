#!/usr/bin/env python3
import json,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];action=sys.argv[1]
path='/api/'+action if action in ['investigate','trace-probe'] else '/api/experiment/'+action
request=urllib.request.Request('http://127.0.0.1:19780'+path,data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+(root/'.local/secrets/control_token').read_text().strip()},method='POST')
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=650) as r:print(json.dumps(json.load(r),ensure_ascii=False,indent=2))
