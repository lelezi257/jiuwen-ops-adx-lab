"""Trusted engineering broker. Runner routes cannot merge/deploy."""
import base64,hashlib,io,json,os,re,shutil,subprocess,tarfile,threading,time,zipfile
from pathlib import Path
import httpx
from fastapi import FastAPI,Depends,HTTPException
from lab.common import *
app=FastAPI();init_store();lock=threading.RLock()
REPO=os.environ['GITHUB_REPOSITORY'];BRANCH=os.getenv('GITHUB_BRANCH','lab-live');REMOTE='https://github.com/'+REPO+'.git';WORK_ROOT=Path(os.getenv('LAB_WORK_ROOT','/work'));CACHE=WORK_ROOT/'repository';WORK=WORK_ROOT/'candidates';WORK.mkdir(parents=True,exist_ok=True)
HOST_REPO=os.environ['HOST_REPO'];IMAGE='localhost:5000/jiuwen-adx-order';CONTAINER='ops-adx-order-api'
ALLOWED=('apps/order_api/','tests/order/')
TRUSTED=['.github/workflows/contract.yml','.github/workflows/build.yml','deploy/Order.Dockerfile','contracts/check_http.py','scripts/ci.py']
def cmd(argv,cwd=None,timeout=120,check=True):
 env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_CONFIG_COUNT':'1','GIT_CONFIG_KEY_0':'credential.helper','GIT_CONFIG_VALUE_0':'!python /app/lab/git_credential.py'}
 try:r=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
 except subprocess.TimeoutExpired:
  raise HTTPException(504,f'{argv[0]} exceeded its {timeout}s deadline; inspect build/network evidence before retrying. No success receipt was recorded.')
 if check and r.returncode:raise RuntimeError(f'{argv[0]} failed ({r.returncode}): '+r.stderr[-1500:])
 return r.stdout.strip()
def build_options():
 out=[]
 for key in ['PYTHON_BASE','PIP_INDEX_URL','APT_MIRROR_SITE','HTTP_PROXY','HTTPS_PROXY','NO_PROXY']:
  if os.getenv(key):out+=['--build-arg',key+'='+os.environ[key]]
 return out
def gh(method,path,body=None):
 token=secret('github_token')
 if not token:raise HTTPException(409,'GitHub credential not configured')
 with httpx.Client(timeout=httpx.Timeout(20,connect=10)) as c:
  for attempt in range(2):
   try:
    r=c.request(method,'https://api.github.com/repos/'+REPO+path,json=body,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    break
   except httpx.TransportError as exc:
    # Read retry cannot repeat a merge/dispatch/PR write. Unknown writes stop.
    if method!='GET' or attempt:
     raise HTTPException(502,'GitHub transport '+type(exc).__name__+'; reconcile existing effects before retrying a write')
    time.sleep(.5)
  if r.status_code>=400:raise RuntimeError('GitHub '+path+': HTTP '+str(r.status_code)+' '+r.text[:500])
  return r.json() if r.content else {}
def repository(required=()):
 if not CACHE.exists():cmd(['git','clone','--no-checkout',REMOTE,str(CACHE)],timeout=180)
 for sha in required:require_sha(sha)
 if not required or any(subprocess.run(['git','cat-file','-e',sha+'^{commit}'],cwd=CACHE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode for sha in required):
  cmd(['git','fetch','origin','--prune'],CACHE,180)
 return CACHE

def inspect():
 r=json.loads(cmd(['docker','inspect',CONTAINER]))[0];image=json.loads(cmd(['docker','image','inspect',r['Image']]))[0]
 return {'container_id':r['Id'],'image_id':r['Image'],'repo_digests':image.get('RepoDigests',[]),'source_sha':image['Config'].get('Labels',{}).get('org.opencontainers.image.revision'),'running':r['State']['Running'],'release_id':next((x.split('=',1)[1] for x in r['Config']['Env'] if x.startswith('RELEASE_ID=')),None)}
def current():
 fact=inspect();ledger=get('release','current')
 return {'runtime':fact,'ledger':ledger,'known_good':get('release','good'),'consistent':bool(ledger and fact['source_sha']==ledger['source_sha'] and fact['release_id']==ledger['release_id'] and ledger['image_digest'] in fact['repo_digests'])}
def case_active(cid):
 c=call('http://control:8080','/internal/cases/'+cid,role='runner')
 if c.get('cancelled') or c['state'] not in ['REPAIRING','INVESTIGATING','VERIFY_AGENT_RUNNING','TRACE_PROBE_RUNNING']:raise HTTPException(409,'Case does not allow agent tools')
 return c

def workspace(cid):
 w=get('workspace',cid)
 if not w:raise HTTPException(404,'Call create_workspace first')
 return w,Path(w['path'])
def path_allowed(path):
 return isinstance(path,str) and path.startswith(ALLOWED) and '..' not in Path(path).parts and not Path(path).is_absolute() and '\\' not in path

def safe_path(root,path):
 if not path_allowed(path):raise HTTPException(403,'Only business source and new regression tests are writable/readable')
 target=(root/path).resolve()
 if not target.is_relative_to(root.resolve()):raise HTTPException(403,'Path escaped workspace')
 return target

def check_changes(root,base):
 changes=cmd(['git','diff','--name-status',base],root).splitlines()
 if len(changes)>20:raise HTTPException(403,'Too many files')
 for row in changes:
  status,path=row.split('\t',1)
  if not path_allowed(path) or status not in ['A','M'] or (path.startswith('tests/') and status!='A'):raise HTTPException(403,'Candidate changed a protected path')
  if (root/path).is_symlink():raise HTTPException(403,'Symlink not allowed')
  if (root/path).stat().st_size>150000:raise HTTPException(403,'File too large')
 return changes

def assert_trusted(sha):
 trust=os.environ['LAB_TRUST_SHA'];require_sha(trust);root=repository(required=(sha,trust))
 for path in TRUSTED:
  if cmd(['git','rev-parse',sha+':'+path],root)!=cmd(['git','rev-parse',trust+':'+path],root):raise HTTPException(409,'Trusted CI/build definition changed: '+path)

@app.get('/health')
def health():return {'ok':True,'github_configured':bool(secret('github_token')),'repository':REPO,'trust_sha':os.getenv('LAB_TRUST_SHA')}

@app.post('/tools/{name}',dependencies=[Depends(worker)])
def tool(name:str,args:dict):
 cid=args.get('case_id','');c=case_active(cid)
 if c['state'] in ['VERIFY_AGENT_RUNNING','TRACE_PROBE_RUNNING'] and name not in ['get_running_release','get_release_diff']:raise HTTPException(403,'This Agent phase is read-only')
 with lock:
  if name=='get_running_release':return current()
  if name=='get_release_diff':
   a=get('release','good');b=current()['runtime']['source_sha'];base=a['source_sha'] if a else b
   root=repository(required=(base,b,c['observed_sha']))
   result={'base_sha':base,'running_sha':b,'diff':cmd(['git','diff',base,b,'--','apps/order_api'],root)[:30000]}
   if c.get('phase')=='verify':result['deployed_repair']={'incident_sha':c['observed_sha'],'deployed_sha':b,'diff':cmd(['git','diff',c['observed_sha'],b,'--','apps/order_api','tests/order'],root)[:30000]}
   return result
  if name=='create_workspace':
   if get('workspace',cid):return get('workspace',cid)
   root=repository();base=require_sha(c['observed_sha']);assert_trusted(base)
   branch_head=gh('GET','/branches/'+BRANCH)['commit']['sha']
   if base!=branch_head:raise HTTPException(409,'Running source differs from experiment branch; re-investigate')
   path=WORK/cid;cmd(['git','clone','--no-hardlinks',str(root),str(path)])
   cmd(['git','remote','set-url','origin',REMOTE],path);cmd(['git','checkout','-b','ops/'+cid,base],path)
   cmd(['git','config','user.name','Jiuwen Ops Lab'],path);cmd(['git','config','user.email','ops-lab@users.noreply.github.com'],path)
   w={'case_id':cid,'path':str(path),'base_sha':base,'branch':'ops/'+cid,'repository':REPO};put('workspace',cid,w);return w
  w,root=workspace(cid)
  if name=='list_source':return {'files':cmd(['git','ls-files','apps/order_api','tests/order'],root).splitlines(),'workspace_id':cid}
  if name=='read_source':
   path=safe_path(root,args['path']);return {'path':args['path'],'content':path.read_text()[:40000],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
  if name=='write_source':
   path=safe_path(root,args['path']);text=args['content']
   if len(text)>150000:raise HTTPException(413,'File too large')
   if args['path'].startswith('tests/') and cmd(['git','ls-tree',w['base_sha'],'--',args['path']],root):raise HTTPException(403,'Historical tests are immutable; add a new test file')
   old_hash=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
   if args.get('expected_sha256')!=old_hash:raise HTTPException(409,'File changed; read again before writing')
   path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);cmd(['git','add','--',args['path']],root);check_changes(root,w['base_sha']);return {'path':args['path'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
  if name=='get_diff':return {'base_sha':w['base_sha'],'diff':cmd(['git','diff',w['base_sha']],root)[:50000]}
  if name=='run_tests':
   check_changes(root,w['base_sha']);run_id=ident('test')
   argv=['python','/app/scripts/ci.py','--candidate',str(root),'--trusted','/app','--oracle-host-path',HOST_REPO+'/contracts','--candidate-volume','jiuwen-ops-adx-lab_work']
   result=subprocess.run(argv,capture_output=True,text=True,timeout=360)
   output=re.sub(r"((?:POSTGRES|CONTRACT_DB|DB)_PASSWORD=)[^\s'\"]+",r'\1[REDACTED]',result.stdout+result.stderr)
   rec={'test_id':run_id,'passed':result.returncode==0,'output':output[-45000:],'tree_hash':cmd(['git','write-tree'],root)};put('test',cid,rec);return rec
  if name=='create_pull_request':
   check_changes(root,w['base_sha']);test=get('test',cid)
   if not test or not test['passed'] or test['tree_hash']!=cmd(['git','write-tree'],root):raise HTTPException(409,'Passing tests required for exact candidate tree')
   if not any(x.startswith('A\ttests/order/') for x in check_changes(root,w['base_sha'])):raise HTTPException(409,'Add a regression test')
   if cmd(['git','status','--porcelain'],root):cmd(['git','commit','-m','Fix order regression for '+cid],root)
   sha=cmd(['git','rev-parse','HEAD'],root);existing=get('pr',cid)
   cmd(['git','push','origin','HEAD:refs/heads/'+w['branch']],root,180)
   if existing:
    pr=gh('GET','/pulls/'+str(existing['number']))
   else:
    candidates=gh('GET','/pulls?state=open&head='+REPO.split('/')[0]+':'+w['branch'])
    attribution='Human-authored engineering acceptance (model_calls=0; not Agent qualification)' if c.get('kind')=='engineering_acceptance' else 'Real-model repair'
    pr=candidates[0] if candidates else gh('POST','/pulls',{'head':w['branch'],'base':BRANCH,'title':'[Ops Lab] Order recovery '+cid,'body':attribution+' for `'+cid+'`.\n\n'+str(args.get('summary',''))[:5000]})
   rec={'number':pr['number'],'url':pr['html_url'],'head_sha':sha,'base_sha':w['base_sha'],'case_id':cid};put('pr',cid,rec);return rec
 raise HTTPException(404,'Unknown agent tool')


def pr_status(cid):
 rec=get('pr',cid)
 if not rec:raise HTTPException(404,'No broker-created PR')
 pr=gh('GET','/pulls/'+str(rec['number']))
 if pr.get('merged'):return {'state':'merged','merge_sha':pr['merge_commit_sha'],'pr':rec}
 if pr['state']!='open' or pr['head']['sha']!=rec['head_sha'] or pr['base']['sha']!=rec['base_sha'] or pr['base']['ref']!=BRANCH or pr['head']['repo']['full_name']!=REPO:return {'state':'stale','pr':rec}
 files=gh('GET','/pulls/'+str(rec['number'])+'/files?per_page=100')
 if len(files)!=pr['changed_files'] or any(not path_allowed(x['filename']) or x['status'] not in ['modified','added'] or (x['filename'].startswith('tests/') and x['status']!='added') for x in files):raise HTTPException(403,'PR scope invalid')
 assert_trusted(rec['base_sha'])
 workflow=gh('GET','/actions/workflows/contract.yml')
 runs=gh('GET','/actions/workflows/contract.yml/runs?event=pull_request&head_sha='+rec['head_sha'])['workflow_runs']
 runs=[r for r in runs if r['workflow_id']==workflow['id'] and any(p['number']==rec['number'] for p in r['pull_requests'])]
 if not runs:return {'state':'pending','pr':rec}
 run=max(runs,key=lambda x:x['id'])
 if run['status']!='completed':return {'state':'pending','run_id':run['id'],'pr':rec}
 jobs=gh('GET',f"/actions/runs/{run['id']}/jobs")['jobs'];passed=run['conclusion']=='success' and any(j['name']=='contract' and j['conclusion']=='success' for j in jobs)
 return {'state':'passed' if passed else 'failed','run_id':run['id'],'run_url':run['html_url'],'test_merge_sha':pr.get('merge_commit_sha'),'pr':rec}


def deploy(image,sha,release_id,expected):
 require_sha(sha)
 if not re.fullmatch(r'localhost:5000/jiuwen-adx-order@sha256:[0-9a-f]{64}',image):raise HTTPException(400,'Only immutable local registry image digest is allowed')
 old=current() if get('release','current') else None
 if old and (not old['consistent'] or old['ledger']['release_id']!=expected):raise HTTPException(409,'Release compare-and-swap failed')
 cmd(['docker','pull',image],timeout=180)
 metadata=json.loads(cmd(['docker','image','inspect',image]))[0]
 if metadata['Config'].get('Labels',{}).get('org.opencontainers.image.revision')!=sha:raise HTTPException(409,'Image source label mismatch')
 op={'release_id':release_id,'source_sha':sha,'image_digest':image,'previous':old['ledger'] if old else None,'state':'deploying','time':now()};put('release',release_id,op)
 cmd(['docker','rm','-f',CONTAINER],check=False)
 cmd(['docker','run','-d','--name',CONTAINER,'--restart','unless-stopped','--network','jiuwen-ops-adx-lab_app','--network-alias','order-api','--read-only','--tmpfs','/tmp','--mount','type=volume,src=jiuwen-ops-adx-lab_logs,dst=/logs','--mount','type=bind,src='+HOST_REPO+'/.local/secrets/db_password,dst=/run/secrets/db_password,readonly','-p','127.0.0.1:19080:8080','-e','RELEASE_ID='+release_id,'-e','IMAGE_DIGEST='+image,image])
 put('release','current',op)
 for _ in range(60):
  try:
   with httpx.Client(timeout=3,trust_env=False) as c:
    r=c.get('http://order-api:8080/health');r.raise_for_status();v=r.json()
   if v['source_sha']==sha and v['release_id']==release_id:
    op['state']='ready';put('release',release_id,op);put('release','current',op);return current()
  except Exception:pass
  time.sleep(1)
 op['state']='failed';put('release',release_id,op);put('release','current',op);raise RuntimeError('New release did not become ready')

@app.post('/ops/{name}',dependencies=[Depends(operator)])
def ops(name:str,args:dict):
 if name=='current':return current()
 with lock:
  if name=='current':return current()
  if name=='bootstrap':
   if get('release','current'):
    cur=current()
    if cur['consistent']:return cur
    raise HTTPException(409,'Existing release requires reconciliation')
   if args['source_sha']!=os.environ['LAB_TRUST_SHA']:raise HTTPException(409,'Bootstrap must use the selected trusted source')
   return deploy(args['image_digest'],args['source_sha'],'release-baseline',None)
  if name=='pr-status':return pr_status(args['case_id'])
  if name=='test-evidence':
   rec=get('test',args['case_id'])
   if not rec or rec['test_id']!=args.get('evidence_id'):raise HTTPException(404,'Test evidence does not belong to this case/current candidate')
   return {**rec,'case_id':args['case_id'],'source':'independent_business_tests'}
  if name=='merge':
   cid=args['case_id'];c=call('http://control:8080','/internal/cases/'+cid,role='runner')
   if c['cancelled']:raise HTTPException(409,'Cancelled')
   status=pr_status(cid)
   if status['state']=='merged':
    if not get('merge-intent',cid):raise HTTPException(409,'Merge was not authorized by this controller')
    put('merge',cid,status);return status
   if status['state']!='passed':raise HTTPException(409,'Exact candidate trusted CI has not passed')
   pr=status['pr'];put('merge-intent',cid,status);rec=gh('PUT',f"/pulls/{pr['number']}/merge",{'sha':pr['head_sha'],'merge_method':'merge','commit_title':'Verified order repair '+cid})
   if not rec.get('merged'):raise HTTPException(409,'Merge refused')
   result={'state':'merged','merge_sha':rec['sha'],'pr':pr,'checked':status};put('merge',cid,result)
   parents=gh('GET','/commits/'+rec['sha'])['parents']
   if not parents or parents[0]['sha']!=pr['base_sha']:raise HTTPException(409,'Merge happened on a changed base; retain merge fact and stop before deployment')
   return result
  if name=='build':
   cid=args['case_id'];merge=get('merge',cid)
   if not merge:raise HTTPException(409,'Merge ledger required')
   sha=merge['merge_sha'];assert_trusted(sha);assert_trusted(gh('GET','/branches/main')['commit']['sha']);rec=get('build',cid)
   if rec and rec['state'] in ['ready','failed']:return rec
   if not rec:
    rec={'source_sha':sha,'dispatched_at':now(),'state':'dispatching'};put('build',cid,rec)
    gh('POST','/actions/workflows/build.yml/dispatches',{'ref':'main','inputs':{'source_sha':sha}});rec['state']='pending';put('build',cid,rec)
   runs=gh('GET','/actions/workflows/build.yml/runs?event=workflow_dispatch')['workflow_runs']
   selected=[x for x in runs if x['display_title']=='Build order '+sha]
   if not selected:return rec
   run=max(selected,key=lambda x:x['id']);rec.update(run_id=run['id'],run_url=run['html_url'])
   if run['status']!='completed':return rec
   if run['conclusion']!='success':rec['state']='failed';put('build',cid,rec);return rec
   arch='arm64' if os.uname().machine=='aarch64' else 'amd64'
   artifacts=gh('GET',f"/actions/runs/{run['id']}/artifacts")['artifacts'];artifact=next((x for x in artifacts if x['name']=='order-'+arch and not x['expired']),None)
   if not artifact:raise HTTPException(409,'Matching architecture artifact missing')
   from lab.artifact_download import download
   blob=download(artifact,secret('github_token'),cache=DATA/'artifact-cache'/(str(artifact['id'])+'.zip'))
   with zipfile.ZipFile(io.BytesIO(blob)) as z:
    provenance=json.loads(z.read('provenance.json'));tar=z.read('image.tar')
   if str(provenance.get('run_id'))!=str(run['id']) or provenance['source_sha']!=sha or provenance['architecture']!=arch or hashlib.sha256(tar).hexdigest()!=provenance['archive_sha256']:raise HTTPException(409,'Artifact provenance mismatch')
   target=DATA/('image-'+cid+'.tar');target.write_bytes(tar)
   try:
    cmd(['docker','load','-i',str(target)],timeout=180);tag=IMAGE+':'+sha;cmd(['docker','tag','order-build:'+sha,tag]);cmd(['docker','push',tag],timeout=180)
    image=json.loads(cmd(['docker','image','inspect',tag]))[0];digest=next(x for x in image['RepoDigests'] if x.startswith(IMAGE+'@'))
   finally:target.unlink(missing_ok=True)
   rec.update(state='ready',image_digest=digest,artifact_id=artifact['id'],provenance=provenance);put('build',cid,rec);return rec
  if name=='deploy':
   cid=args['case_id'];b=get('build',cid)
   case=call('http://control:8080','/internal/cases/'+cid,role='runner')
   if case['cancelled']:raise HTTPException(409,'Cancelled')
   already=current()
   if already['consistent'] and already['ledger']['release_id']=='release-'+cid:return already
   if not b or b['state']!='ready':raise HTTPException(409,'Verified build required')
   return deploy(b['image_digest'],b['source_sha'],'release-'+cid,args['expected_release'])
  if name=='rollback':
   good=get('release','good')
   if not good:raise HTTPException(409,'No known-good release')
   return deploy(good['image_digest'],good['source_sha'],ident('rollback'),args['expected_release'])
  if name=='mark-good':
   cur=current();report=call('http://probe:8080','/reports/'+args['verification_id'])
   if not report or not report['passed'] or report['release_id']!=cur['ledger']['release_id'] or not cur['consistent']:raise HTTPException(409,'Independent verification for current release required')
   put('release','good',{**cur['ledger'],'verification_id':args['verification_id'],'verified_at':now()});return current()
  if name=='register':
   fact=inspect();image=next((x for x in fact['repo_digests'] if x.startswith(IMAGE+'@')),None)
   if not image:raise HTTPException(409,'Bootstrap image must be pushed to local registry first')
   rec={'release_id':fact['release_id'],'source_sha':fact['source_sha'],'image_digest':image,'state':'ready','time':now()};put('release','current',rec);return current()
  if name=='fault':
   active=call('http://control:8080','/api/cases')
   if any(x['state'] not in ['DELIVERY_ACCEPTANCE_PASSED','RESOLVED_FIXED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED','NO_ACTION','TRACE_PROBE_COMPLETED'] for x in active):raise HTTPException(409,'Finish/cancel the current experiment first')
   good=get('release','good')
   if not good:raise HTTPException(409,'Verify and mark a healthy baseline first')
   root=repository();branch=gh('GET','/branches/'+BRANCH)['commit']['sha'] if args.get('branch_exists') else None
   if branch is None:
    try:branch=gh('GET','/git/ref/heads/'+BRANCH)['object']['sha']
    except RuntimeError:branch=os.environ['LAB_TRUST_SHA']
   path=WORK/ident('fault');cmd(['git','clone',str(root),str(path)]);cmd(['git','remote','set-url','origin',REMOTE],path);cmd(['git','checkout','-b','fault',branch],path)
   cmd(['git','config','user.name','Jiuwen Ops Lab'],path);cmd(['git','config','user.email','ops-lab@users.noreply.github.com'],path)
   # A fresh business fixture for every trial, preserving Git history. This is
   # operator-owned experiment setup, never a model-visible repair fallback.
   cmd(['git','restore','--source='+os.environ['LAB_TRUST_SHA'],'--staged','--worktree','--','apps/order_api','tests/order'],path)
   if cmd(['git','status','--porcelain'],path):cmd(['git','commit','-m','Experiment: restore trusted healthy business baseline'],path)
   file=path/'apps/order_api/pricing.py';source=file.read_text();old="normalized = (coupon or '').strip().upper()"
   if old not in source:raise HTTPException(409,'Baseline pricing changed; reset/review experiment explicitly')
   file.write_text(source.replace(old,'normalized = coupon.strip().upper()'))
   cmd(['git','config','user.name','Jiuwen Ops Lab'],path);cmd(['git','config','user.email','ops-lab@users.noreply.github.com'],path);cmd(['git','add','apps/order_api/pricing.py'],path);cmd(['git','commit','-m','Experiment: introduce optional coupon regression'],path)
   sha=cmd(['git','rev-parse','HEAD'],path);cmd(['git','push','origin','HEAD:refs/heads/'+BRANCH],path,180)
   tag=IMAGE+':'+sha;cmd(['docker','build',*build_options(),'-f','/app/deploy/Order.Dockerfile','--build-arg','SOURCE_SHA='+sha,'-t',tag,str(path)],timeout=300);cmd(['docker','push',tag],timeout=180)
   digest=next(x for x in json.loads(cmd(['docker','image','inspect',tag]))[0]['RepoDigests'] if x.startswith(IMAGE+'@'))
   return deploy(digest,sha,ident('fault-release'),current()['ledger']['release_id'])
 raise HTTPException(404,'Unknown controller operation')
