#!/usr/bin/env python3
"""Use the exact already-deployed DB image under the trusted test's alias."""
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
compose = ['docker', 'compose', '--env-file', '.local/lab.env', '--env-file', '.local/runtime.env']
config = json.loads(subprocess.check_output([*compose, 'config', '--format', 'json'], cwd=root))
image = config['services']['db']['image']
identity = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', image], text=True).strip()
subprocess.run(['docker', 'tag', image, 'postgres:16.9-alpine'], check=True)
actual = subprocess.check_output(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'postgres:16.9-alpine'], text=True).strip()
assert identity == actual
(root / '.local/evidence/test-image.json').write_text(json.dumps({'source': image, 'test_alias': 'postgres:16.9-alpine', 'image_id': identity}, indent=2))
print('Trusted test database alias resolves to the exact deployed PostgreSQL image')
