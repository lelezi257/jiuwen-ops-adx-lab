#!/usr/bin/env python3
"""Apply the dedicated VM's narrow sandbox -> execution broker route."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
if os.geteuid() != 0 or not Path('/etc/jiuwen-ops-adx-lab-owner').exists():
    raise SystemExit('Only the dedicated jiuwen-ops-adx-lab VM is supported')
for module in ('br_netfilter', 'erofs'):
    subprocess.run(['modprobe', module], check=True)
for setting in ('net.ipv4.ip_forward=1', 'net.bridge.bridge-nf-call-iptables=1', 'net.bridge.bridge-nf-call-ip6tables=1'):
    subprocess.run(['sysctl', '-q', '-w', setting], check=True)
# Docker 28+ also blocks direct routing in raw PREROUTING. This one exception
# still passes through sandboxd's full per-sandbox ACL and the filter table.
for table, chain in (('raw', 'PREROUTING'), ('filter', 'DOCKER-USER')):
    rule = ['-s', '10.88.0.0/22', '-d', '172.29.0.254/32', '-p', 'tcp', '--dport', '8082', '-j', 'ACCEPT']
    base = ['iptables', '-t', table]
    if subprocess.run([*base, '-C', chain, *rule], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run([*base, '-I', chain, '1', *rule], check=True)
# Docker's FORWARD default is DROP. Permit the public interface only after
# sandboxd's earlier ACL rules have validated this flow; preserve return state.
for rule in (
    ['-s', '10.88.0.0/22', '-o', 'eth0', '-j', 'ACCEPT'],
    ['-d', '10.88.0.0/22', '-i', 'eth0', '-m', 'conntrack', '--ctstate', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'],
):
    if subprocess.run(['iptables', '-C', 'DOCKER-USER', *rule], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        subprocess.run(['iptables', '-I', 'DOCKER-USER', '1', *rule], check=True)
if '--install' in sys.argv:
    Path('/etc/modules-load.d/ops-adx.conf').write_text('br_netfilter\nerofs\n')
    Path('/etc/sysctl.d/90-ops-adx.conf').write_text('net.ipv4.ip_forward=1\nnet.bridge.bridge-nf-call-iptables=1\nnet.bridge.bridge-nf-call-ip6tables=1\n')
    Path('/etc/systemd/system/ops-adx-network.service').write_text(
        '[Unit]\nDescription=Ops ADX sandbox broker route\nAfter=docker.service network-online.target\nRequires=docker.service\nBefore=ops-adx-platform.service\n'
        '[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/python3 ' + str(root / 'scripts/configure_network.py') + '\n'
        '[Install]\nWantedBy=multi-user.target\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', 'ops-adx-network'], check=True, stdout=subprocess.DEVNULL)
print('Narrow broker route applied; sandboxd ACL remains enabled')
