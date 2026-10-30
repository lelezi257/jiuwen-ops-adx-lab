#!/usr/bin/env python3
"""Reproducible setup on the dedicated VM; preserve existing state and work."""
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
if os.geteuid() != 0 or not Path('/etc/jiuwen-ops-adx-lab-owner').exists():
    raise SystemExit('Run as root on the dedicated jiuwen-ops-adx-lab VM')
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    with opener.open('http://127.0.0.1:19780/api/overview', timeout=10) as response:
        current = json.load(response)
except (urllib.error.URLError, TimeoutError):
    running = subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=jiuwen-ops-adx-lab', '--filter', 'label=com.docker.compose.service=control'], text=True).strip()
    if running:
        raise SystemExit('Existing control service is running but its task state cannot be read; setup will not restart it')
    current = None
terminal = {'RESOLVED_FIXED', 'RECOVERED_ROLLBACK', 'NEEDS_HUMAN', 'CANCELLED', 'NO_ACTION', 'TRACE_PROBE_COMPLETED', 'DELIVERY_ACCEPTANCE_PASSED'}
if current and (any(c['state'] not in terminal for c in current['cases']) or
                any(o['state'] not in {'SUCCEEDED', 'FAILED', 'INTERRUPTED'} for o in current['operations'])):
    raise SystemExit('Active case or operation found; setup will not rebuild/restart these services')

def run(*args):
    subprocess.run(list(map(str, args)), cwd=root, check=True)

# Minting happens later; Compose needs the local file to exist first.
(root / '.local/secrets/adx_tenant_token').touch(mode=0o600, exist_ok=True)
run('python3', 'scripts/configure_guest_proxy.py')
active = subprocess.run(['systemctl', 'is-active', '--quiet', 'ops-adx-platform']).returncode == 0
if not active:
    run('python3', 'scripts/fetch_infrastructure.py')
    run('python3', 'scripts/install_platform.py', '--release', '.local/infrastructure/adx-release-a88659db',
        '--backend', '.local/infrastructure/backend')
run('python3', 'scripts/configure_network.py', '--install')
# Uses the clean official source build, never another project's local images.
run('python3', 'scripts/build_images.py')
compose = ['docker', 'compose', '--env-file', '.local/lab.env', '--env-file', '.local/runtime.env']
run(*compose, 'up', '-d', '--no-build', 'registry')
run('python3', 'scripts/publish_template.py')
run('bash', 'scripts/lab', 'up')
print('Environment ready. Run the read-only qualification before creating a business fault.')
