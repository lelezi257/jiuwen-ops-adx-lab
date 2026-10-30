#!/usr/bin/env python3
"""Wait for actual HTTP readiness, CLI discovery and consistent running release."""
import json,time,urllib.request
client=urllib.request.build_opener(urllib.request.ProxyHandler({}));deadline=time.monotonic()+120;last='starting'
while time.monotonic()<deadline:
 try:
  with client.open('http://127.0.0.1:19780/api/status',timeout=10) as r:status=json.load(r)
  if all(status.get(x,{}).get('ok') for x in ['runner','delivery','evidence']) and status.get('release',{}).get('consistent'):
   with client.open('http://127.0.0.1:19781/',timeout=10) as native:
    if native.status!=200:raise RuntimeError('Native frontend not ready')
   print('Ready: http://127.0.0.1:19780 ; native WebUI http://127.0.0.1:19781 ; runner='+status['runner']['state']);break
  last='Components or release identity are not ready'
 except Exception as exc:last=type(exc).__name__
 time.sleep(1)
else:raise SystemExit('Readiness deadline exceeded: '+last+'; inspect scripts/lab logs')
