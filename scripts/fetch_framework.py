#!/usr/bin/env python3
"""Fetch immutable official source archives; never use another user's config."""
import hashlib,json,shutil,tarfile,tempfile,tomllib,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];vendor=root/'vendor';vendor.mkdir(exist_ok=True)
lock=json.loads((root/'config/framework.lock.json').read_text());manifest={}
for key,entry in lock.items():
 target=vendor/key
 if not target.exists():
  url=entry['repository'].replace('https://github.com/','https://codeload.github.com/')+'/tar.gz/'+entry['commit']
  with tempfile.TemporaryDirectory() as tmp:
   archive=Path(tmp)/'source.tar.gz';urllib.request.urlretrieve(url,archive)
   with tarfile.open(archive) as tar:
    for item in tar.getmembers():
     if item.name.startswith('/') or '..' in Path(item.name).parts or item.issym() or item.islnk():raise RuntimeError('Unsafe source archive member')
    tar.extractall(Path(tmp)/'unpack',filter='data')
   src=next((Path(tmp)/'unpack').iterdir());shutil.move(str(src),target)
   entry={**entry,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
 manifest[key]=entry
# Install upstream code unchanged with --no-deps. Resolve its declared non-git
# dependencies separately; replace only transport for the pinned Git projects.
projects=[vendor/'core',vendor/'protocol/openjiuwen-protocol',vendor/'a4p/A4P',vendor/'router/intelli_router',vendor/'swarm',vendor/'swarm/sdks/python']
requirements=[]
for project in projects:
 data=tomllib.loads((project/'pyproject.toml').read_text())
 requirements += [d for d in data['project'].get('dependencies',[]) if 'git+' not in d]
(vendor/'requirements-framework.txt').write_text('\n'.join(sorted(set(requirements)))+'\n')
(vendor/'projects.json').write_text(json.dumps([str(p.relative_to(root)) for p in projects]))
(vendor/'source-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print('Fetched official pinned sources, wrote dependency transport manifest')
