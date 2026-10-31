#!/usr/bin/env python3
"""Generate the checked-in Compose deployment from a readable service map."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
base={'image':'jiuwen-ops-runtime:local','build':{'context':'.','dockerfile':'deploy/Dockerfile','args':{'HTTP_PROXY':'${HTTP_PROXY:-}','HTTPS_PROXY':'${HTTPS_PROXY:-}','NO_PROXY':'${NO_PROXY:-}','PIP_INDEX_URL':'${PIP_INDEX_URL:-https://pypi.org/simple}','UV_INDEX_URL':'${UV_INDEX_URL:-https://pypi.org/simple}','APT_MIRROR_SITE':'${APT_MIRROR_SITE:-}','PYTHON_BASE':'${PYTHON_BASE:-python:3.11-slim-bookworm}','DOCKER_CLI_IMAGE':'${DOCKER_CLI_IMAGE:-docker:29.1.3-cli}'}},'restart':'unless-stopped','networks':['ops'],'read_only':True,'tmpfs':['/tmp'],'security_opt':['no-new-privileges:true'],'cap_drop':['ALL'],'cap_add':['DAC_OVERRIDE'],'environment':{'LAB_DATA':'/data'},'volumes':[]}
def service(module,volume,secrets=(),networks=('ops',),env=None):
 x={**base,'command':['python','-m','uvicorn','lab.'+module+':app','--host','0.0.0.0','--port','8080'],'volumes':[volume+':/data'],'secrets':list(secrets),'networks':list(networks),'environment':{**base['environment'],**(env or {})}};return x
s={}
s['control']=service('control','control',['control_token','runner_token'],env={'LAB_AUTO_DELIVER':'${LAB_AUTO_DELIVER:-true}','LAB_REPAIR_LIMIT':'${LAB_REPAIR_LIMIT:-2}'})
s['control']['ports']=['127.0.0.1:19780:8080']
s['evidence']=service('evidence','evidence',['runner_token','control_token'])
s['delivery']=service('delivery','delivery',['runner_token','control_token','github_token'],('ops','app'),{'GITHUB_REPOSITORY':'${GITHUB_REPOSITORY}','GITHUB_BRANCH':'${GITHUB_BRANCH:-lab-live}','LAB_TRUST_SHA':'${LAB_TRUST_SHA}','HOST_REPO':'${HOST_REPO}','PYTHON_BASE':'${PYTHON_BASE:-python:3.11-slim-bookworm}','PIP_INDEX_URL':'${PIP_INDEX_URL:-https://pypi.org/simple}','APT_MIRROR_SITE':'${APT_MIRROR_SITE:-}','HTTP_PROXY':'${HTTP_PROXY:-}','HTTPS_PROXY':'${HTTPS_PROXY:-}','NO_PROXY':'${OPS_DELIVERY_NO_PROXY:-localhost,127.0.0.1,control,probe,order-api,pypi.org,files.pythonhosted.org,github.com,api.github.com,.githubusercontent.com,.blob.core.windows.net}'})
s['delivery']['read_only']=False;s['delivery']['volumes']+=['work:/work','/var/run/docker.sock:/var/run/docker.sock'];s['delivery']['cap_drop']=[]
s['runner']=service('runner','runner',['runner_token'])
s['runner'].update(image='jiuwen-ops-runner:local',build={'context':'.','dockerfile':'deploy/Runner.Dockerfile','args':{'HTTP_PROXY':'${HTTP_PROXY:-}','HTTPS_PROXY':'${HTTPS_PROXY:-}','NO_PROXY':'${NO_PROXY:-}','PIP_INDEX_URL':'${PIP_INDEX_URL:-https://pypi.org/simple}','UV_INDEX_URL':'${UV_INDEX_URL:-https://pypi.org/simple}','APT_MIRROR_SITE':'${APT_MIRROR_SITE:-}','PYTHON_BASE':'${PYTHON_BASE:-python:3.11-slim-bookworm}','DOCKER_CLI_IMAGE':'${DOCKER_CLI_IMAGE:-docker:29.1.3-cli}'}},env_file=['.local/model.env'])
s['runner']['volumes']+=['./.local/swarm:/data/swarm/config'];s['runner']['environment']['HOME']='/data/home'
s['runner']['environment'].update({'API_BASE':'${API_BASE:-}','API_KEY':'${API_KEY:-}','MODEL_NAME':'${MODEL_NAME:-}'})
# Model values come ONLY from the per-service env_file, not global Compose env.
for key in ['API_BASE','API_KEY','MODEL_NAME']:s['runner']['environment'].pop(key)
s['runner']['environment'].update({'JIUWENSWARM_DATA_DIR':'/data/swarm','JIUWENSWARM_CONFIG_DIR':'/data/swarm/config'})
s['native-web']=service('native_observer','observer',env={'HOME':'/data/home','JIUWENSWARM_DATA_DIR':'/data/state','LAB_RECORDINGS':'/recordings/swarm','JIUWENSWARM_ENABLE_ORIGIN_CHECK':'1','JIUWENSWARM_WS_ALLOWED_ORIGIN_HOSTS':'127.0.0.1,localhost,none'})
s['native-web'].update(image='jiuwen-ops-observer:local',build={'context':'.','dockerfile':'deploy/Observer.Dockerfile','args':{'NODE_BASE':'${NODE_BASE:-node:22-bookworm-slim}','HTTP_PROXY':'${HTTP_PROXY:-}','HTTPS_PROXY':'${HTTPS_PROXY:-}','NO_PROXY':'${NO_PROXY:-}'}},ports=['127.0.0.1:19781:8080'],command=['python','/app/scripts/start_native_observer.py'])
s['native-web']['volumes']+=['runner:/recordings:ro']
s['probe']=service('probe','probe',['control_token','verify_db_password'],('ops','app'),{'LAB_VERIFY_SECONDS':'${LAB_VERIFY_SECONDS:-5}','LAB_VERIFY_WINDOWS':'${LAB_VERIFY_WINDOWS:-2}','LAB_VERIFY_MIN_REQUESTS':'${LAB_VERIFY_MIN_REQUESTS:-3}'})
s['collector']={**base,'command':['python','-m','lab.collector'],'volumes':['collector:/data','logs:/logs:ro']}
s['db']={'image':'${REGISTRY_MIRROR_PREFIX:-}library/postgres:16.9-alpine','restart':'unless-stopped','networks':['app'],'environment':{'POSTGRES_USER':'orders','POSTGRES_DB':'orders','POSTGRES_PASSWORD_FILE':'/run/secrets/db_password'},'secrets':['db_password','verify_db_password'],'volumes':['postgres:/var/lib/postgresql/data','./deploy/init-db.sh:/docker-entrypoint-initdb.d/10-verifier.sh:ro'],'healthcheck':{'test':['CMD-SHELL','pg_isready -U orders'],'interval':'3s','timeout':'3s','retries':30}}
s['prometheus']={'image':'${REGISTRY_MIRROR_PREFIX:-}prom/prometheus:v3.4.1','restart':'unless-stopped','networks':['ops','app'],'volumes':['./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro','./config/alerts.yml:/etc/prometheus/alerts.yml:ro','prometheus:/prometheus'],'command':['--config.file=/etc/prometheus/prometheus.yml','--storage.tsdb.retention.time=3d']}
s['alertmanager']={'image':'${REGISTRY_MIRROR_PREFIX:-}prom/alertmanager:v0.28.1','restart':'unless-stopped','networks':['ops'],'volumes':['./config/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro'],'secrets':['control_token'],'user':'0:0'}
s['loki']={'image':'${REGISTRY_MIRROR_PREFIX:-}grafana/loki:3.5.1','restart':'unless-stopped','networks':['ops'],'volumes':['./config/loki.yml:/etc/loki/config.yml:ro','loki:/loki'],'command':['-config.file=/etc/loki/config.yml']}
s['registry']={'image':'${REGISTRY_MIRROR_PREFIX:-}library/registry:2.8.3','restart':'unless-stopped','networks':['ops'],'ports':['127.0.0.1:5000:5000'],'volumes':['registry:/var/lib/registry']}
volumes=['control','evidence','delivery','runner','probe','collector','work','postgres','logs','prometheus','loki','registry','observer']
compose={'name':'jiuwen-ops-adx-lab','services':s,'volumes':{v:{} for v in volumes},'networks':{'ops':{},'app':{}},'secrets':{k:{'file':'.local/secrets/'+k} for k in ['control_token','runner_token','db_password','verify_db_password','github_token']}}
# ADX mode: runner is an image build target, never a prestarted service.
s['control']['command']=['python','/app/scripts/start_control.py']
compose['services']['runner']={k:s['runner'][k] for k in ('image','build')}
compose['services']['runner']['profiles']=['build-only']
s['control']['environment'].update(OPS_EXECUTION_BACKEND='adx',OPS_CASES_ROOT='/cases',ADX_GATEWAY='${ADX_GATEWAY:-https://host.docker.internal:19443}',ADX_TEMPLATE='ops-order',ADX_TEMPLATE_VERSION='${ADX_TEMPLATE_VERSION:-}',ADX_CA_FILE='/run/adx/public-ca.pem',OPS_MAX_EXECUTIONS='${OPS_MAX_EXECUTIONS:-1}')
s['control']['volumes']+=['./.local/cases:/cases','./.local/adx-client:/run/adx:ro']
s['control']['secrets']+=['execution_signing_key','adx_tenant_token']
s['control']['extra_hosts']=['host.docker.internal:host-gateway']
s['control']['networks']={'ops':{'ipv4_address':'172.29.0.254'}}
s['native-web']['environment']['LAB_RECORDINGS']='/recordings'
s['native-web']['volumes']=['observer:/data','./.local/cases:/recordings:ro']
compose['networks']['ops']['ipam']={'config':[{'subnet':'172.29.0.0/24'}]}
compose['networks']['app']['ipam']={'config':[{'subnet':'172.30.0.0/24'}]}
for name in ('execution_signing_key','adx_tenant_token'):compose['secrets'][name]={'file':'.local/secrets/'+name}
(root/'compose.yaml').write_text(json.dumps(compose,ensure_ascii=False,indent=2)+'\n')
