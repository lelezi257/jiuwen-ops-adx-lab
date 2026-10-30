#!/usr/bin/env python3
"""Publish the immutable execution image and an ADX managed Agent template."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
import urllib.request

root = Path(__file__).resolve().parents[1]
prefix = Path("/opt/ops-adx")
local = root / ".local"
context = ssl.create_default_context(cafile=str(local / "adx-client/public-ca.pem"))
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))


def request(path, token, body=None):
    req = urllib.request.Request("https://127.0.0.1:19443" + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with opener.open(req, timeout=120) as response:
        return json.load(response)


token_file = local / "secrets/adx_tenant_token"
if not token_file.read_text().strip():
    admin = (prefix / "config/secrets/admin-key").read_text().strip()
    credential = request("/api/admin/v1/keys", admin, {"tenantId": "ops-adx-lab", "expiresAtUnixSeconds": 0})
    token_file.write_text(credential["apiKey"])
    token_file.chmod(0o600)
token = token_file.read_text().strip()
image_id = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", "jiuwen-ops-runner:local"], text=True).strip()
tag = "localhost:5000/ops-adx-agent:" + image_id.split(":")[1][:16]
subprocess.run(["docker", "tag", "jiuwen-ops-runner:local", tag], check=True)
subprocess.run(["docker", "push", tag], check=True)
inspect = json.loads(subprocess.check_output(["docker", "image", "inspect", tag]))[0]
digest = next(x for x in inspect["RepoDigests"] if x.startswith("localhost:5000/ops-adx-agent@"))
template = {"name": "ops-order", "image": digest, "isolation_runtime": "runsc",
            "env": {"HOME": "/data/home", "LAB_DATA": "/data", "OPS_CONTROL_URL": "http://172.29.0.2:8080",
                    "JIUWENSWARM_DATA_DIR": "/data/swarm", "JIUWENSWARM_CONFIG_DIR": "/data/swarm/config", "OPS_MODEL_FILE": "/run/ops/model.env"},
            "resources": {"cpu_millis": 1000, "memory_mib": 1536, "cpu_limit_millis": 2000, "memory_limit_mib": 3072},
            "service": [{"protocol": "http", "port": 8080}], "init_timeout_seconds": 120,
            "readiness_probe": {"http_get": {"port": 8080, "path": "/ready"}, "initial_delay_seconds": 1, "period_seconds": 2, "timeout_seconds": 5},
            "mounts": [
                {"type": "bind", "host_path": str(local / "cases") + "/${workspace}", "target": "/data", "options": ["rw"], "create_if_missing": True},
                {"type": "bind", "host_path": str(local / "model.env"), "target": "/run/ops/model.env", "options": ["ro"]}],
            "lifecycle": {"idle_timeout_seconds": 0}}
# Never put model keys or platform credentials into Template/parameters.
publication = request("/api/agent/v2/templates", token, template)
version = publication["template"]["version"]
(local / "evidence/template.json").write_text(json.dumps(publication, ensure_ascii=False, indent=2))
env = local / "runtime.env"
lines = [line for line in env.read_text().splitlines() if not line.startswith("ADX_TEMPLATE_VERSION=")]
env.write_text("\n".join([*lines, "ADX_TEMPLATE_VERSION=" + version]) + "\n")
print("Published pinned Agent template version " + version + "; no Agent Binding or sandbox was precreated.")
