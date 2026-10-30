#!/usr/bin/env python3
"""Publish correlated receipts and native archives, never synthesize trajectories."""
import argparse,hashlib,io,json,time,urllib.request,zipfile
from collections import Counter
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--case',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args()
client=urllib.request.build_opener(urllib.request.ProxyHandler({}));out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
def read(port,path,raw=False):
 with client.open('http://127.0.0.1:'+str(port)+path,timeout=90) as r:data=r.read()
 return data if raw else json.loads(data)
# Check real private values without ever publishing them. Empty template values ignored.
private=[];root=Path(__file__).resolve().parents[1]
for file in (root/'.local/secrets').glob('*'):
 value=file.read_bytes().strip()
 if len(value)>=12:private.append(value)
model=root/'.local/model.env'
if model.exists():
 for line in model.read_text().splitlines():
  if line.startswith('API_KEY='):
   value=line.split('=',1)[1].strip().strip('\"\'')
   if len(value)>=12:private.append(value.encode())
def check(data):
 if any(value in data for value in private):raise SystemExit('Private value found; refusing evidence publication')
report={'collected_at':time.time(),'source':'Original Jiuwen trajectory HTTP API plus official SDK receipts; no business-event-to-span conversion','cases':[]}
for cid in a.case:
 c=read(19780,'/api/cases/'+cid);events=read(19780,'/api/cases/'+cid+'/events')
 row={'case_id':cid,'kind':c.get('kind','incident'),'state':c['state'],'attempt':c['attempt'],'sessions':[]}
 for attempt,run in c.get('sdk_runs',{}).items():
  sid=run['session_id'];subjects=read(19781,'/api/trajectory/sessions/'+sid+'/subjects');native=read(19781,'/api/trajectory/sessions/'+sid+'/archive',raw=True)
  check(native)
  with zipfile.ZipFile(io.BytesIO(native)) as z:
   for entry in z.infolist():check(z.read(entry))
  archive=out.parent/('native-'+cid+'-'+run['phase']+'-'+attempt+'.zip');archive.write_bytes(native)
  names=Counter();trace_ids=set();case_found=False
  for subject in subjects.get('items',[]):
   revision=0
   while True:
    page=read(19781,'/api/trajectory/sessions/'+sid+'/subjects/'+urllib.parse.quote(subject['subject_id'],safe='')+'/records?since_revision='+str(revision)+'&limit=500')
    for record in page.get('records',[]):
     trace_ids.add(record['trace_id']);raw=json.dumps(record,ensure_ascii=False);check(raw.encode());case_found|=cid in raw
     for rs in record.get('otlp',{}).get('resourceSpans',[]):
      for scope in rs.get('scopeSpans',[]):
       for span in scope.get('spans',[]):names[span.get('name','')]+=1
    if not page.get('has_more'):break
    revision=page['next_since_revision']
  receipts=[e['data'] for e in events if e['kind']=='sdk_result' and e['data'].get('session_id')==sid]
  observation=root/'.local/evidence'/('native-trace-'+cid+'.json')
  samples=json.loads(observation.read_text())['samples'] if observation.exists() else []
  live=[{'at':s['time'],'case_state':s['case_state'],'revision':s['sessions'][sid].get('watermark'),'record_count':sum(i['record_count'] for i in s['sessions'][sid].get('subjects',[]))} for s in samples if sid in s['sessions'] and isinstance(s['sessions'][sid].get('watermark'),int)]
  transitions=[]
  for sample in live:
   if not transitions or sample['revision']!=transitions[-1]['revision'] or sample['case_state']!=transitions[-1]['case_state']:transitions.append(sample)
  run_request=next((json.loads(e['data']['input']) for e in events if e['kind']=='run.request' and json.loads(e['data']['input']).get('phase')==run['phase']),None)
  row['sessions'].append({**run,'trace_ids':sorted(trace_ids),'native_subjects':subjects,'native_span_names':dict(names),'native_contains_case_id':case_found,'request_contains_case_id':bool(run_request and run_request['case_id']==cid),'sdk_receipt':{k:receipts[-1].get(k) for k in ['session_id','request_id','status','exit_code','usage','output_json']} if receipts else None,'live_native_revisions':transitions,'archive':archive.name,'archive_sha256':hashlib.sha256(native).hexdigest()})
 report['cases'].append(row)
blob=(json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode();check(blob);out.write_bytes(blob);print(str(out))
