#!/usr/bin/env python3
"""Fail closed before changing files or restarting an existing project VM."""
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

TERMINAL = {'RESOLVED_FIXED', 'RECOVERED_ROLLBACK', 'NEEDS_HUMAN', 'CANCELLED', 'NO_ACTION', 'TRACE_PROBE_COMPLETED', 'DELIVERY_ACCEPTANCE_PASSED'}


def ensure_idle():
    if not Path('/etc/jiuwen-ops-adx-lab-owner').exists():
        raise SystemExit('Use the dedicated jiuwen-ops-adx-lab VM')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:19780/api/overview', timeout=10) as response:
            current = json.load(response)
    except (urllib.error.URLError, TimeoutError):
        running = subprocess.check_output(['docker', 'ps', '-q', '--filter', 'label=com.docker.compose.project=jiuwen-ops-adx-lab', '--filter', 'label=com.docker.compose.service=control'], text=True).strip()
        if running:
            raise SystemExit('Existing control service is running but task state cannot be read; no changes are permitted')
        return
    if any(c['state'] not in TERMINAL for c in current['cases']) or any(o['state'] not in {'SUCCEEDED', 'FAILED', 'INTERRUPTED'} for o in current['operations']):
        raise SystemExit('Active case or operation found; no source/configuration sync or service restart is permitted')
    print('No active case or operation; history and volumes remain untouched')


if __name__ == '__main__':
    ensure_idle()
