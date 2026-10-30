#!/usr/bin/env python3
"""Dedicated guest only: let Docker use Lima's propagated proxy if present."""
import json,os,subprocess
from pathlib import Path
proxy=os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
if proxy:
 p=Path('/etc/docker/daemon.json');config=json.loads(p.read_text()) if p.exists() else {}
 proxies={'http-proxy':os.getenv('HTTP_PROXY') or os.getenv('http_proxy') or proxy,'https-proxy':proxy,'no-proxy':'localhost,127.0.0.1,::1'}
 if config.get('proxies')!=proxies:
  running=subprocess.check_output(['docker','ps','-q'],text=True).strip()
  if running:raise SystemExit('Proxy change requires a deliberate guest Docker restart; containers are running')
  config['proxies']=proxies;p.write_text(json.dumps(config,indent=2)+'\n');subprocess.run(['systemctl','restart','docker'],check=True)
print('Guest Docker proxy checked; credentials are not printed')
