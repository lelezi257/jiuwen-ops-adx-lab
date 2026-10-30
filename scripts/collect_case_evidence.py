#!/usr/bin/env python3
"""Collect actual case, SDK and native-store evidence without running an Agent."""
import argparse
import json
from pathlib import Path
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('case_id')
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

def read(url):
    with client.open(url, timeout=45) as response:
        return json.load(response)

base = 'http://127.0.0.1:19780/api/cases/' + args.case_id
case = read(base)
events = read(base + '/events')
receipts = [{k: e['data'].get(k) for k in ('session_id', 'request_id', 'status', 'exit_code', 'error', 'usage')}
            for e in events if e['kind'] == 'sdk_result']
tools = [{'name': e['data']['name'], 'call_id': e['data']['call_id'],
          'evidence_id': (e['data'].get('result') or {}).get('evidence_id')}
         for e in events if e['kind'] == 'host_tool.executed']
recordings = read('http://127.0.0.1:19781/api/ops/recordings-ready/' + args.case_id)
subjects = {r['session_id']: read('http://127.0.0.1:19781/api/trajectory/sessions/' + r['session_id'] + '/subjects')
            for r in (case.get('sdk_runs') or {}).values()}
report = {'case': case, 'sdk_receipts': receipts, 'tools': tools, 'recordings': recordings,
          'native_subjects': subjects, 'timeline': [{'time': e['time'], 'kind': e['kind'], 'data': e['data']}
          for e in events if e['kind'] in {'state', 'adx.execution.accepted', 'adx.environment.released'}]}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'state': case['state'], 'sdk_sessions': len(subjects), 'recordings_ready': recordings['ready'],
                  'cleanup': case.get('cleanup'), 'output': str(args.output)}, ensure_ascii=False))
