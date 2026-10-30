"""Bounded parallel reads of the exact GitHub artifact, with byte/hash checks."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import httpx
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

PART = 4 * 1024 * 1024


def validate(blob, artifact):
    if len(blob) != artifact['size_in_bytes']:
        raise ValueError('Artifact archive size mismatch')
    expected = artifact.get('digest')
    actual = 'sha256:' + hashlib.sha256(blob).hexdigest()
    if expected and expected != actual:
        raise ValueError('GitHub artifact archive digest mismatch')
    return blob


def download(artifact, token, *, client_factory=httpx.Client, cache=None):
    size = artifact['size_in_bytes']
    if not isinstance(size, int) or not 0 < size <= 512 * 1024 * 1024:
        raise ValueError('Artifact size is outside the lab download contract')
    url = artifact['archive_download_url']
    if urlsplit(url).scheme != 'https' or urlsplit(url).hostname != 'api.github.com':
        raise ValueError('Only the GitHub artifact API may receive the GitHub credential')
    if cache and Path(cache).exists():
        if not artifact.get('digest'):
            raise ValueError('Cached artifact requires an authoritative GitHub archive digest')
        return validate(Path(cache).read_bytes(), artifact)
    with client_factory(timeout=30, follow_redirects=False) as client:
        response = client.get(url, headers={'Authorization': 'Bearer ' + token})
        if response.status_code not in (302, 307):
            raise RuntimeError('GitHub artifact redirect was not accepted: HTTP ' + str(response.status_code))
        location = response.headers['location']
        host = urlsplit(location).hostname or ''
        if urlsplit(location).scheme != 'https' or not (host.endswith('.blob.core.windows.net') or host.endswith('.githubusercontent.com')):
            raise ValueError('Unexpected artifact storage destination; no credential forwarded')
        # The signed storage URL is a credential: never log it or include it in errors.
        def part(bounds):
            start, end = bounds
            for attempt in range(2):
                try:
                    with client.stream('GET', location, headers={'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}) as value:
                        if value.status_code != 206 or value.headers.get('content-range') != f'bytes {start}-{end}/{size}':
                            raise ValueError('Artifact byte range response did not match the requested identity')
                        data = value.read()
                    if len(data) != end - start + 1:
                        raise ValueError('Artifact range was incomplete')
                    return data
                except httpx.TransportError as exc:
                    if attempt:
                        raise RuntimeError('Artifact read transport failed: ' + type(exc).__name__) from None
            raise RuntimeError('Artifact read did not complete')
        ranges = [(start, min(size - 1, start + PART - 1)) for start in range(0, size, PART)]
        with ThreadPoolExecutor(max_workers=min(16, len(ranges))) as workers:
            blob = b''.join(workers.map(part, ranges))
    validate(blob, artifact)
    if cache and artifact.get('digest'):
        destination = Path(cache)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as staging:
            staging.write(blob)
        Path(staging.name).replace(destination)
    return blob
