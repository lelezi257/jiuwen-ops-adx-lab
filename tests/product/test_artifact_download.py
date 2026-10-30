import hashlib
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import httpx
from lab.artifact_download import download


class ArtifactDownloadContract(unittest.TestCase):
    def fixture(self, corrupt=False):
        blob = b'actual-test-archive-bytes'
        artifact = {'size_in_bytes': len(blob), 'archive_download_url': 'https://api.github.com/artifact/7/zip',
                    'digest': 'sha256:' + hashlib.sha256(blob).hexdigest()}
        def handle(request):
            if request.url.host == 'api.github.com':
                self.assertEqual(request.headers['authorization'], 'Bearer test-credential')
                return httpx.Response(302, headers={'Location': 'https://example.blob.core.windows.net/archive?signed=private'})
            self.assertNotIn('authorization', request.headers)
            start, end = map(int, request.headers['range'][6:].split('-'))
            value = blob[start:end + 1]
            if corrupt:
                value = b'x' * len(value)
            return httpx.Response(206, content=value, headers={'Content-Range': f'bytes {start}-{end}/{len(blob)}'})
        return blob, artifact, lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handle), **kwargs)

    def test_parallel_ranges_reassemble_exact_artifact_and_do_not_forward_token(self):
        blob, artifact, factory = self.fixture()
        with patch('lab.artifact_download.PART', 5):
            self.assertEqual(download(artifact, 'test-credential', client_factory=factory), blob)

    def test_tampered_archive_is_rejected(self):
        _, artifact, factory = self.fixture(corrupt=True)
        with patch('lab.artifact_download.PART', 5):
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                download(artifact, 'test-credential', client_factory=factory)

    def test_github_credential_cannot_be_sent_to_arbitrary_api(self):
        _, artifact, factory = self.fixture()
        artifact['archive_download_url'] = 'https://untrusted.invalid/zip'
        with self.assertRaisesRegex(ValueError, 'Only the GitHub'):
            download(artifact, 'test-credential', client_factory=factory)

    def test_verified_cache_is_bound_to_the_authoritative_archive_hash(self):
        blob, artifact, _ = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / 'artifact.zip'
            cache.write_bytes(blob)
            def forbidden(**kwargs):
                raise AssertionError('A verified cache hit must not make a network request')
            self.assertEqual(download(artifact, 'test-credential', client_factory=forbidden, cache=cache), blob)
            cache.write_bytes(b'x' * len(blob))
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                download(artifact, 'test-credential', client_factory=forbidden, cache=cache)

    def test_wrong_range_identity_is_rejected_before_archive_use(self):
        _, artifact, _ = self.fixture()
        def handle(request):
            if request.url.host == 'api.github.com':
                return httpx.Response(302, headers={'Location': 'https://example.blob.core.windows.net/archive'})
            return httpx.Response(206, content=b'bad', headers={'Content-Range': 'bytes 0-2/3'})
        with self.assertRaisesRegex(ValueError, 'range response'):
            download(artifact, 'test-credential', client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(handle), **kw))
