#!/usr/bin/env python3
"""Atomically update the next sandbox's root-owned read-only model file."""
import os
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
if os.geteuid() != 0 or not Path('/etc/jiuwen-ops-adx-lab-owner').exists():
    raise SystemExit('Run as root on the dedicated project VM')
directory = root / '.local/runtime-secrets'
directory.mkdir(mode=0o700, exist_ok=True)
staging = directory / 'model.env.next'
shutil.copyfile(root / '.local/model.env', staging)
os.chown(staging, 0, 0)
staging.chmod(0o600)
staging.replace(directory / 'model.env')
print('Model configuration staged for future sandboxes; active mounts retain their original file')
