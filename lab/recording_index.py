"""Read-only official roots; stable per-case readers, never global rebinding."""
import asyncio
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from lab.recording_reader import initialize, read
from pathlib import Path

from gateway.common.protocol_ids import validate_session_id
from jiuwenswarm.observability.config import TrajectoryStoreSettings
from jiuwenswarm.server.trajectory.host import TrajectoryHost


class RecordingIndex:
    def __init__(self, recordings, state):
        self.root = Path(recordings)
        self.state = Path(state)
        self.sessions = self.state / "agent/sessions"
        self.sessions.mkdir(parents=True, exist_ok=True)
        self.owners = {}
        self.hosts = {}
        self.blobs = {}
        self.paths = {}
        self.readers = OrderedDict()

    def refresh(self):
        for directory in self.root.glob("*/swarm/agent/sessions/*"):
            if not directory.is_dir():
                continue
            sid = directory.name
            try:
                validate_session_id(sid)
            except ValueError:
                continue
            resolved = directory.resolve()
            resolved.relative_to(self.root.resolve())
            root = directory.parents[2]
            if sid in self.owners and self.owners[sid] != root:
                raise RuntimeError("Session identity collision across case recording roots")
            self.owners[sid] = root
            self.paths[sid] = directory

    async def read(self, operation, sid, params=None):
        if not self.exists(sid):
            raise ValueError("Official Session recording is not available")
        root = self.owners[sid]
        if root not in self.readers:
            # The official lifecycle guard rejects per-Session symlinks.
            # A fixed, per-case sessions DIRECTORY link preserves real children
            # and lets the official module write its own logs outside recordings.
            facade = self.state / "readers" / root.parent.name
            (facade / "agent").mkdir(parents=True, exist_ok=True)
            sessions = facade / "agent/sessions"
            if sessions.is_symlink():
                if sessions.resolve() != (root / "agent/sessions").resolve():
                    raise RuntimeError("Per-case reader root changed")
            elif not sessions.exists():
                sessions.symlink_to(root / "agent/sessions", target_is_directory=True)
            self.readers[root] = ProcessPoolExecutor(max_workers=1,
                mp_context=multiprocessing.get_context("spawn"), initializer=initialize, initargs=(str(facade),))
        self.readers.move_to_end(root)
        while len(self.readers) > 3:
            _, stale = self.readers.popitem(last=False)
            stale.shutdown(wait=False)
        return await asyncio.get_running_loop().run_in_executor(self.readers[root], read, operation, sid, params or {})

    def close(self):
        for pool in self.readers.values():
            pool.shutdown(wait=False)
        self.readers.clear()

    def exists(self, sid):
        validate_session_id(sid)
        self.refresh()
        return sid in self.owners

    def host(self, sid):
        if not self.exists(sid):
            raise ValueError("Official Session recording is not available")
        root = self.owners[sid]
        if root not in self.hosts:
            settings = TrajectoryStoreSettings(enabled=True, database_path=root / ".trace/sessions",
                                               retention_days=7, queue_size=4096, batch_size=128, flush_interval_ms=500)
            self.hosts[root] = TrajectoryHost(settings)
        return self.hosts[root]

    async def call(self, method, params, user_id=None):
        sid = params.get("session_id")
        host = self.host(sid) if sid else self.blobs.get(params.get("blob_id"))
        if host is None:
            return False, {"error": "Unknown official recording identity", "code": "NOT_FOUND", "status": 404}
        ok, payload = await host.call(method, params, user_id)
        if ok and isinstance(payload, dict) and payload.get("blob_id"):
            self.blobs[payload["blob_id"]] = host
        return ok, payload
