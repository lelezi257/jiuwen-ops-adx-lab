#!/usr/bin/env python3
"""Download exact lab-built official-source packages; verify before extraction."""
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / 'config/infrastructure.lock.json').read_text())
destination = root / '.local/infrastructure'
destination.mkdir(parents=True, exist_ok=True)
for item in lock['assets']:
    archive = destination / item['name']
    if not archive.exists():
        temporary = archive.with_suffix('.part')
        url = lock['release'].replace('/tag/', '/download/') + '/' + item['name']
        print('Downloading ' + item['name'], flush=True)
        urllib.request.urlretrieve(url, temporary)
        temporary.rename(archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != item['sha256']:
        raise SystemExit('Package digest mismatch: ' + item['name'] + '; preserved for inspection')
    target = destination if item['directory'].startswith('adx-release-') else destination / item['directory']
    target.mkdir(exist_ok=True)
    with tarfile.open(archive) as package:
        # Python 3.12+ data filter rejects traversal, special files and unsafe links.
        for member in package.getmembers():
            (target / member.name).resolve().relative_to(target.resolve())
            if member.issym() or member.islnk():
                link = (target / member.name).parent / member.linkname if member.issym() else target / member.linkname
                link.resolve().relative_to(target.resolve())
            if member.isdev() or member.isfifo():
                raise SystemExit('Unexpected special file in infrastructure package')
        package.extractall(target, filter='data')
    print('Verified and extracted ' + item['name'])
print('Packages ready. Installation is restricted to the dedicated project VM.')
