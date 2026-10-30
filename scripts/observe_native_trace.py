#!/usr/bin/env python3
"""Collect live native HTTP watermarks alongside one actual product case.

Read-only. Does not create tasks, manufacture spans, or declare UI acceptance.
"""
import argparse,json,time,urllib.request,urllib.error
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('case_id');p.add_argument('--deadline',type=int,default=2400);a=p.parse_args()
root=Path(__file__).resolve().parents[1];client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
path=root/'.local/evidence'/('native-trace-'+a.case_id+'.json');path.parent.mkdir(parents=True,exist_ok=True)
report={'case_id':a.case_id,'source':'official native trajectory HTTP read API; SDK case events are only correlation','started_at':time.time(),'samples':[],'sessions':{},'ui_acceptance':'requires separate real browser observation'}
def get(port,path):
 with client.open('http://127.0.0.1:'+str(port)+path,timeout=12) as r:return json.load(r)
terminal={'RESOLVED_FIXED','RECOVERED_ROLLBACK','NEEDS_HUMAN','CANCELLED','NO_ACTION','TRACE_PROBE_COMPLETED'}
end=time.monotonic()+a.deadline;last=None
while time.monotonic()<end:
 c=get(19780,'/api/cases/'+a.case_id)
 sample={'time':time.time(),'case_state':c['state'],'sessions':{}}
 for attempt,run in c.get('sdk_runs',{}).items():
  sid=run['session_id'];report['sessions'][sid]=run
  try:
   subjects=get(19781,'/api/trajectory/sessions/'+sid+'/subjects?after_revision=0')
   row={'watermark':subjects.get('watermark'),'store_epoch':subjects.get('store_epoch'),'subjects':subjects.get('items',[])}
   sample['sessions'][sid]=row
  except Exception as exc:sample['sessions'][sid]={'read_error':str(exc)[:250]}
 report['samples'].append(sample);report['latest_case']=c
 path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 summary=(c['state'],tuple((s,x.get('watermark')) for s,x in sample['sessions'].items()))
 if summary!=last:print(json.dumps({'case_id':a.case_id,'state':c['state'],'native':dict(summary[1])}),flush=True);last=summary
 if c['state'] in terminal:
  report['finished_at']=time.time();report['terminal_state']=c['state']
  for sid in report['sessions']:
   try:report['sessions'][sid]['subjects_final']=get(19781,'/api/trajectory/sessions/'+sid+'/subjects?after_revision=0')
   except Exception as exc:report['sessions'][sid]['error']=str(exc)[:250]
  path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');break
 time.sleep(1)
else:raise SystemExit('Observation deadline; facts retained in '+str(path))
print('Evidence saved: '+str(path),flush=True)
