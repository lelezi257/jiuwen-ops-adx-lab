"""Read-only official recording roots; stable per-Session links, never global rebinding."""
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
            link = self.sessions / sid
            if link.is_symlink():
                if link.resolve() != resolved:
                    raise RuntimeError("Session recording link changed")
            elif not link.exists():
                link.symlink_to(directory, target_is_directory=True)

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
