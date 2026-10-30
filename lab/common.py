import hmac,json,os,sqlite3,time,uuid
from contextlib import contextmanager
from pathlib import Path
import httpx
from fastapi import Header,HTTPException

DATA=Path(os.getenv('LAB_DATA','/data'));DATA.mkdir(parents=True,exist_ok=True)
def ident(prefix):return prefix+'-'+uuid.uuid4().hex[:16]
def now():return time.time()
def secret(name):
 p=Path('/run/secrets')/name
 return p.read_text().strip() if p.exists() else ''
def authorize(value,role):
 expected=secret(role+'_token')
 if not expected or not hmac.compare_digest(value or '', 'Bearer '+expected):raise HTTPException(403,'Invalid service identity')
def operator(authorization:str=Header(default='')):authorize(authorization,'control')
def worker(authorization:str=Header(default='')):authorize(authorization,'runner')
def either(authorization:str=Header(default='')):
 if not any(secret(r+'_token') and hmac.compare_digest(authorization,'Bearer '+secret(r+'_token')) for r in ['control','runner']):raise HTTPException(403,'Invalid service identity')
def headers(role):return {'Authorization':'Bearer '+secret(role+'_token')}
def call(base,path,body=None,role='control',timeout=45):
 with httpx.Client(timeout=timeout,trust_env=False) as c:
  r=c.get(base+path,headers=headers(role)) if body is None else c.post(base+path,json=body,headers=headers(role))
  if r.status_code>=400:raise RuntimeError(f'{base}{path}: HTTP {r.status_code}: {r.text[:800]}')
  return r.json()
@contextmanager
def db(name='state'):
 c=sqlite3.connect(DATA/(name+'.sqlite'),timeout=30,isolation_level=None);c.row_factory=sqlite3.Row
 c.execute('PRAGMA journal_mode=WAL');c.execute('BEGIN IMMEDIATE')
 try:yield c;c.commit()
 except BaseException:c.rollback();raise
 finally:c.close()
def init_store():
 with db() as c:c.execute('CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,body TEXT,PRIMARY KEY(kind,id))')
def put(kind,key,value):
 with db() as c:c.execute('INSERT OR REPLACE INTO objects VALUES(?,?,?)',(kind,key,json.dumps(value,ensure_ascii=False)))
def get(kind,key,default=None):
 with db() as c:r=c.execute('SELECT body FROM objects WHERE kind=? AND id=?',(kind,key)).fetchone()
 return json.loads(r[0]) if r else default
def all_objects(kind):
 with db() as c:r=c.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid',(kind,)).fetchall()
 return [json.loads(x[0]) for x in r]
def require_sha(value):
 import re
 if not re.fullmatch('[0-9a-f]{40}',value or ''):raise HTTPException(400,'Expected a full commit SHA')
 return value
