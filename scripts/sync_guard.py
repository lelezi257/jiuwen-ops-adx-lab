#!/usr/bin/env python3
"""Do not replace an existing VM's database identity during a fresh clone sync."""
import hmac,sys,tarfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
existing=root/'.local/secrets/db_password'
if existing.exists():
 with tarfile.open(sys.argv[1]) as archive:
  incoming=archive.extractfile('.local/secrets/db_password').read().strip()
 if not hmac.compare_digest(existing.read_bytes().strip(),incoming):
  raise SystemExit('VM already has a different lab identity. Restore the original .local configuration before syncing; no existing data or credentials were overwritten.')
print('VM configuration identity checked')
