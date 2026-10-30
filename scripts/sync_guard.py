#!/usr/bin/env python3
"""Reject credential changes that could detach existing persistent VM state."""
import hmac
from pathlib import Path
import sys
import tarfile

root = Path(__file__).resolve().parents[1]
with tarfile.open(sys.argv[1]) as archive:
    for name in ('db_password', 'verify_db_password', 'control_token', 'runner_token', 'execution_signing_key'):
        existing = root / '.local/secrets' / name
        if not existing.exists():
            continue
        try:
            incoming = archive.extractfile('.local/secrets/' + name).read().strip()
        except KeyError:
            raise SystemExit('Missing persisted identity in configuration archive: ' + name)
        if not hmac.compare_digest(existing.read_bytes().strip(), incoming):
            raise SystemExit('VM has a different persisted identity (' + name + '); restore its original configuration before syncing. No files were overwritten.')
print('VM configuration identities checked')
