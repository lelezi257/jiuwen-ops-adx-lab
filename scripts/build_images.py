#!/usr/bin/env python3
"""Clean builds by default; optional local dependency cache with explicit proof."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--reuse-framework-cache", action="store_true")
args = parser.parse_args()
compose = ["docker", "compose", "--env-file", ".local/lab.env", "--env-file", ".local/runtime.env", "-f", "compose.yaml"]
if args.reuse_framework_cache:
    expected = json.loads((root / "config/framework.lock.json").read_text())
    checked = {}
    for image in ("jiuwen-ops-runner:framework-cache", "jiuwen-ops-observer:frontend-cache"):
        actual = json.loads(subprocess.check_output(["docker", "run", "--rm", "--network", "none", "--entrypoint", "cat", image,
                                                    "/app/config/framework.lock.json"], cwd=root))
        if actual != expected:
            raise SystemExit("Cached SDK source lock does not match; use clean build")
        checked[image] = subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", image], text=True).strip()
    checked["jiuwen-ops-runtime:framework-cache"] = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", "jiuwen-ops-runtime:framework-cache"], text=True).strip()
    override = {"services": {name: {"build": {"dockerfile": path}} for name, path in (
        ("control", "deploy/Runtime.cached.Dockerfile"), ("runner", "deploy/Runner.cached.Dockerfile"),
        ("native-web", "deploy/Observer.cached.Dockerfile"))}}
    path = root / ".local/compose-cache.json"
    path.write_text(json.dumps(override))
    (root / ".local/evidence/build-cache.json").write_text(json.dumps({
        "base_images": checked, "framework_lock_sha256": hashlib.sha256((root / "config/framework.lock.json").read_bytes()).hexdigest(),
        "application_code": "all lab/scripts/web code replaced by this repository", "qualification": False}, indent=2))
    compose += ["-f", str(path)]
subprocess.run([*compose, "build", "control", "runner"], cwd=root, check=True)
subprocess.run([*compose, "build", "native-web"], cwd=root, check=True)
