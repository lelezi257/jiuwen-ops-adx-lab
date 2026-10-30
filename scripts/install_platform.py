#!/usr/bin/env python3
"""Install pinned, verified artifacts on this project's dedicated VM only."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path("/opt/ops-adx")
CONFIG = PREFIX / "config"
BACKEND = Path("/opt/jiuwen-ops-adx-backend")


def run(*args):
    subprocess.run(list(map(str, args)), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def protected(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(value)
    path.chmod(0o600)


def certificates():
    tls = CONFIG / "tls"
    tls.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (tls / "ca.pem").exists():
        return
    run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", tls / "ca.key",
        "-out", tls / "ca.pem", "-days", "90", "-subj", "/CN=Ops ADX Lab private CA")
    ext = tls / "extensions.cnf"
    ext.write_text("basicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\n"
                   "extendedKeyUsage=serverAuth,clientAuth\n"
                   "subjectAltName=DNS:adx.internal,DNS:localhost,DNS:host.docker.internal,IP:127.0.0.1,IP:172.17.0.1,IP:172.29.0.1\n")
    for name in ("coordinator", "node-1", "apiserver", "ingress", "ingress-public"):
        run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", tls / (name + ".key"),
            "-out", tls / (name + ".csr"), "-subj", "/CN=Ops ADX " + name)
        run("openssl", "x509", "-req", "-in", tls / (name + ".csr"), "-CA", tls / "ca.pem",
            "-CAkey", tls / "ca.key", "-CAcreateserial", "-out", tls / (name + ".pem"),
            "-days", "90", "-extfile", ext)
        run("openssl", "x509", "-in", tls / (name + ".pem"), "-outform", "DER", "-out", tls / (name + ".der"))
        (tls / (name + ".key")).chmod(0o600)
    (tls / "ca.key").chmod(0o600)
    shutil.copyfile(tls / "ca.pem", tls / "public-ca.pem")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not Path("/etc/jiuwen-ops-adx-lab-owner").exists():
        raise SystemExit("Run only as root on the dedicated jiuwen-ops-adx-lab VM")
    # Never overwrite a running project's execution state.
    if subprocess.run(["systemctl", "is-active", "--quiet", "ops-adx-platform"]).returncode == 0:
        raise SystemExit("Platform is already active; inspect it rather than reinstalling")
    run("bash", args.release / "install.sh", "--prefix", PREFIX, "--bin-dir", PREFIX / "bin")
    shutil.copytree(args.backend, BACKEND, dirs_exist_ok=True)
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    certificates()
    for path in (CONFIG / "secrets/admin-key", PREFIX / "data/runtime-control-key"):
        if not path.exists():
            protected(path, secrets.token_hex(32))
    # The bridge is a service address, not an assignable sandbox. Keep every
    # assignable .2-.254 address isolated, but explicitly allow bridge DNS.
    sandbox_ranges = [str(n) for n in ipaddress.summarize_address_range(
        ipaddress.IPv4Address("10.88.0.2"), ipaddress.IPv4Address("10.88.3.255"))]
    network = {"sandbox_cidrs": sandbox_ranges, "internal_cidrs": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"],
               "public_egress": True, "egress_allow": [
                   {"cidr": "172.29.0.2/32", "protocol": "tcp", "ports": {"first": 8080, "last": 8080}},
                   *[{"cidr": "10.88.0.1/32", "protocol": proto, "ports": {"first": 53, "last": 53}}
                     for proto in ("tcp", "udp")]]}
    protected(CONFIG / "agent.json", json.dumps({"timeout_seconds": 120, "embedded": {
        "redis_url": "redis://127.0.0.1:6379/", "namespace": "ops-adx-agent", "sandbox_network": network}}, indent=2))
    deployment = yaml.safe_load((ROOT / "config/adx-deployment.example.yaml").read_text().replace("/opt/adx", str(PREFIX)))
    deployment["namespace"] = "ops-adx-platform"
    for service in deployment["services"]:
        if service["role"] == "adxlet":
            service["config"]["sandboxd_socket"] = "/run/jiuwen-ops-adx-sandboxd/sandboxd.sock"
            service["config"]["runtime_control"]["advertised_address"] = "http://10.88.0.1:19003"
        if service["role"] == "apiserver":
            service.setdefault("env", {})["ADX_AGENT_CONFIG"] = str(CONFIG / "agent.json")
        if service["role"] == "ingress":
            service["env"]["ADX_DATA_PLANE_INGRESS_TLS_BIND"] = "0.0.0.0:19443"
            service["env"]["ADX_DATA_PLANE_INGRESS_ALLOWED_CLIENT_CIDRS"] = "127.0.0.1/32,172.29.0.0/24,172.17.0.0/16"
            service["env"]["ADX_AGENT_CONFIG"] = str(CONFIG / "agent.json")
    deployment["runtime_profile"]["rootfs"]["runtime_class"] = "runsc"
    protected(CONFIG / "deployment.yaml", yaml.safe_dump(deployment, sort_keys=False))
    backend_config = Path("/etc/jiuwen-ops-adx-backend")
    backend_config.mkdir(mode=0o700, exist_ok=True)
    for name in ("sandboxd-minimal.toml", "oss.json", "registry.json", "oss_auths.json", "registry_auths.json"):
        shutil.copyfile(BACKEND / name, backend_config / name)
    for directory in ("/var/lib/jiuwen-ops-adx", "/run/jiuwen-ops-adx-sandboxd"):
        Path(directory).mkdir(parents=True, exist_ok=True)
    run("modprobe", "br_netfilter")
    run("modprobe", "erofs")
    run("sysctl", "-w", "net.ipv4.ip_forward=1", "net.bridge.bridge-nf-call-iptables=1", "net.bridge.bridge-nf-call-ip6tables=1")
    units = {
        "ops-adx-sandboxd": "[Unit]\nDescription=Ops ADX pinned sandboxd\nAfter=network-online.target\n[Service]\nType=simple\nExecStart=" + str(BACKEND / "sandboxd") + " -config /etc/jiuwen-ops-adx-backend/sandboxd-minimal.toml -socket /run/jiuwen-ops-adx-sandboxd/sandboxd.sock -log-file /var/log/jiuwen-ops-adx-sandboxd.log\nRestart=on-failure\nDelegate=yes\nLimitNOFILE=1048576\n[Install]\nWantedBy=multi-user.target\n",
        "ops-adx-platform": "[Unit]\nDescription=Ops ADX platform supervisor\nAfter=network-online.target ops-adx-sandboxd.service\n[Service]\nType=simple\nExecStart=" + str(PREFIX / "current/bin/adxctl") + " -c " + str(CONFIG / "deployment.yaml") + " run\nRestart=on-failure\nDelegate=yes\nTimeoutStopSec=120\n[Install]\nWantedBy=multi-user.target\n"
    }
    for name, value in units.items():
        Path("/etc/systemd/system/" + name + ".service").write_text(value)
    run(PREFIX / "current/bin/adxctl", "-c", CONFIG / "deployment.yaml", "validate")
    run("systemctl", "daemon-reload")
    run("systemctl", "enable", "--now", "ops-adx-sandboxd", "ops-adx-platform")
    client = ROOT / ".local/adx-client"
    client.mkdir(mode=0o700, exist_ok=True)
    shutil.copyfile(CONFIG / "tls/public-ca.pem", client / "public-ca.pem")
    print("Pinned ADX services installed and started; application/SDK qualification is still required. No credentials printed.")


if __name__ == "__main__":
    main()
