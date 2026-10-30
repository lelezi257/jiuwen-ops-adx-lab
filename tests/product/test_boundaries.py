import os,tempfile,unittest
from pathlib import Path
os.environ['LAB_DATA']=tempfile.mkdtemp(prefix='ops-tests-')
os.environ['LAB_WORK_ROOT']=tempfile.mkdtemp(prefix='ops-work-tests-')
os.environ['GITHUB_REPOSITORY']='owner/lab'
os.environ['HOST_REPO']='/lab'
from unittest.mock import patch
from fastapi.testclient import TestClient
from lab import delivery,control
from lab.common import put,get

class ProductBoundaries(unittest.TestCase):
 def test_candidate_paths(self):
  for p in ['apps/order_api/pricing.py','tests/order/test_optional.py']:self.assertTrue(delivery.path_allowed(p))
  for p in ['../../etc/passwd','/apps/order_api/a.py','apps/order_api/../../lab/control.py','.github/workflows/contract.yml','contracts/check_http.py','tests/order/../product/test_x.py']:self.assertFalse(delivery.path_allowed(p),p)
 def test_symlink_cannot_escape(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d);(r/'apps/order_api').mkdir(parents=True);(r/'apps/order_api/leak').symlink_to('/etc')
   with self.assertRaises(Exception):delivery.safe_path(r,'apps/order_api/leak/passwd')
 def test_agent_cannot_reach_merge(self):
  c=TestClient(delivery.app)
  self.assertEqual(c.post('/ops/merge',json={'case_id':'x'}).status_code,403)
 def test_valid_runner_identity_cannot_merge(self):
  c=TestClient(delivery.app)
  with patch('lab.common.secret',side_effect=lambda name:{'runner_token':'runner-secret','control_token':'control-secret'}.get(name,'')):
   self.assertEqual(c.post('/ops/merge',json={'case_id':'x'},headers={'Authorization':'Bearer runner-secret'}).status_code,403)
   with patch('lab.delivery.call',return_value={'cancelled':False}),patch('lab.delivery.pr_status',return_value={'state':'pending'}):
    self.assertEqual(c.post('/ops/merge',json={'case_id':'x'},headers={'Authorization':'Bearer control-secret'}).status_code,409)
 def test_operator_required_for_fault_or_cancel(self):
  c=TestClient(control.app)
  self.assertEqual(c.post('/api/experiment/fault',json={}).status_code,403)
  self.assertEqual(c.post('/api/cases/x/cancel',json={}).status_code,403)
 def test_delayed_result_does_not_reverse_cancellation(self):
  c={'id':'cancel-test','state':'CANCELLED','cancelled':True};put('case',c['id'],c)
  for state in ['CI_PENDING',None]:
   stale={**c,'state':'REPAIRING','cancelled':False};control.save(stale,state)
   self.assertTrue(get('case',c['id'])['cancelled']);self.assertEqual(get('case',c['id'])['state'],'CANCELLED')
 def test_cli_key_is_not_in_committed_template(self):
  text=(Path(__file__).resolve().parents[2]/'config/model.env.example').read_text();self.assertIn('API_KEY=\n',text)
 def test_ci_gate_rejects_non_success_and_changed_code(self):
  head='a'*40;base='b'*40;record={'number':1,'head_sha':head,'base_sha':base}
  pr={'state':'open','head':{'sha':head,'repo':{'full_name':'owner/lab'}},'base':{'sha':base,'ref':'lab-live'},'changed_files':1,'merge_commit_sha':'c'*40}
  for conclusion,job,want in [('failure','failure','failed'),('neutral','neutral','failed'),('skipped','skipped','failed'),('success','skipped','failed'),('success','success','passed')]:
   def github(method,path,body=None):
    if path=='/pulls/1':return pr
    if path.startswith('/pulls/1/files'):return [{'filename':'apps/order_api/pricing.py','status':'modified'}]
    if path=='/actions/workflows/contract.yml':return {'id':7}
    if path.startswith('/actions/workflows/contract.yml/runs'):return {'workflow_runs':[{'id':8,'workflow_id':7,'pull_requests':[{'number':1}],'status':'completed','conclusion':conclusion,'html_url':'https://example.invalid/run'}]}
    if path=='/actions/runs/8/jobs':return {'jobs':[{'name':'contract','conclusion':job}]}
    raise AssertionError(path)
   with self.subTest(conclusion=conclusion,job=job),patch('lab.delivery.get',return_value=record),patch('lab.delivery.gh',side_effect=github),patch('lab.delivery.assert_trusted'):
    self.assertEqual(delivery.pr_status('c')['state'],want)
  for changed in [{**pr,'head':{'sha':'d'*40,'repo':{'full_name':'owner/lab'}}},{**pr,'base':{'sha':'e'*40,'ref':'lab-live'}}]:
   with patch('lab.delivery.get',return_value=record),patch('lab.delivery.gh',return_value=changed):self.assertEqual(delivery.pr_status('c')['state'],'stale')
 def test_retry_invalidates_late_attempt(self):
  c={'id':'retry-test','state':'CANCELLED','cancelled':True,'observed_sha':'b'*40,'attempt_id':'old-attempt','attempt':1};put('case',c['id'],c)
  client=TestClient(control.app)
  with patch('lab.common.secret',side_effect=lambda name:{'runner_token':'runner-secret','control_token':'control-secret'}.get(name,'')),patch('lab.control.call',return_value={'consistent':True,'runtime':{'source_sha':'b'*40}}):
   r=client.post('/api/cases/retry-test/retry',json={},headers={'Authorization':'Bearer control-secret'});self.assertEqual(r.status_code,200);self.assertNotEqual(r.json()['attempt_id'],'old-attempt')
   old=client.post('/internal/cases/retry-test/result',json={'attempt_id':'old-attempt','result':{'status':'completed','exit_code':0}},headers={'Authorization':'Bearer runner-secret'});self.assertEqual(old.status_code,409)

 def test_verification_failure_goes_to_rollback(self):
  c={'id':'verify-error-test','state':'VERIFYING','cancelled':False};put('case',c['id'],c)
  current={'consistent':True,'ledger':{'release_id':'candidate','source_sha':'a'*40,'image_digest':'sha256:abc'}}
  with patch('lab.control.call',side_effect=[current,RuntimeError('Probe transport unavailable')]):control.transition(c)
  saved=get('case',c['id']);self.assertEqual(saved['state'],'ROLLING_BACK');self.assertIn('Probe transport unavailable',saved['failure'])

 def test_model_receipt_accepts_case_bound_test_evidence(self):
  c={'id':'receipt-evidence','state':'REPAIRING','cancelled':False,'phase':'repair','attempt_id':'a'};put('case',c['id'],c)
  receipt={'status':'completed','exit_code':0,'output_json':{'evidence_ids':['ev-'+'a'*16,'test-'+'b'*16],'pr_number':3,'candidate_sha':'c'*40}}
  calls=[]
  def external(base,path,body=None):
   calls.append((path,body))
   if path=='/ops/pr-status':return {'pr':{'number':3,'head_sha':'c'*40}}
   return {'case_id':c['id']}
  with patch('lab.control.call',side_effect=external):control.result(c['id'],{'attempt_id':'a','result':receipt})
  self.assertEqual(get('case',c['id'])['state'],'CI_PENDING');self.assertEqual(get('case',c['id'])['agent_result'],receipt)
  self.assertIn(('/ops/test-evidence',{'case_id':c['id'],'evidence_id':'test-'+'b'*16}),calls)

 def test_duplicate_receipt_cannot_reverse_delivery_progress(self):
  for state in ['CI_PENDING','MERGING','BUILDING','REPAIR_QUEUED']:
   c={'id':'duplicate-receipt','state':state,'cancelled':False,'phase':'repair','attempt_id':'a'};put('case',c['id'],c)
   with patch('lab.control.call') as external:
    answer=control.result(c['id'],{'attempt_id':'a','result':{'status':'completed','exit_code':0}})
    self.assertFalse(answer['recorded']);external.assert_not_called()
   self.assertEqual(get('case',c['id'])['state'],state)

 def test_review_retry_is_read_only_and_requires_exact_verified_release(self):
  base={'id':'review-retry','state':'NEEDS_HUMAN','cancelled':False,'phase':'verify','attempt_id':'old','attempt':2,'merge':{'merge_sha':'a'*40},'verification':{'passed':True,'release_id':'r','expected_source_sha':'a'*40,'expected_image_digest':'sha256:x'}}
  for changed in [False,True]:
   put('case',base['id'],dict(base));current={'consistent':True,'ledger':{'release_id':'r','source_sha':'a'*40,'image_digest':'sha256:other' if changed else 'sha256:x'}}
   with patch('lab.control.call',return_value=current):
    if changed:
     with self.assertRaises(Exception):control.retry(base['id'])
     self.assertEqual(get('case',base['id'])['state'],'NEEDS_HUMAN')
    else:
     answer=control.retry(base['id']);self.assertEqual(answer['state'],'VERIFY_AGENT_QUEUED');self.assertNotEqual(answer['attempt_id'],'old');self.assertEqual(answer['merge'],base['merge'])

 def test_bad_evidence_retains_official_receipt_and_stops(self):
  for evidence in [['ev-'+'a'*16],['test-'+'b'*16],['../../secret']]:
   c={'id':'bad-receipt-evidence','state':'REPAIRING','cancelled':False,'phase':'repair','attempt_id':'a'};put('case',c['id'],c)
   receipt={'status':'completed','exit_code':0,'output_json':{'evidence_ids':evidence}}
   with patch('lab.control.call',side_effect=RuntimeError('Unavailable or wrong evidence')):control.result(c['id'],{'attempt_id':'a','result':receipt})
   saved=get('case',c['id']);self.assertEqual(saved['state'],'NEEDS_HUMAN');self.assertEqual(saved['agent_result'],receipt)

 def test_test_evidence_is_case_bound(self):
  put('test','test-owner',{'test_id':'test-'+'b'*16,'passed':True})
  with patch('lab.delivery.lock'),self.assertRaises(Exception):delivery.ops('test-evidence',{'case_id':'other-case','evidence_id':'test-'+'b'*16})

 def test_sdk_session_binding_is_live_and_cannot_change_within_attempt(self):
  c={'id':'trace-binding','state':'REPAIRING','cancelled':False,'phase':'repair','attempt_id':'a'};put('case',c['id'],c)
  body={'attempt_id':'a','kind':'run.started','sequence':0,'data':{'session_id':'process_cli_actual','request_id':'r'}}
  control.record(c['id'],body)
  self.assertEqual(get('case',c['id'])['sdk_runs']['a']['session_id'],'process_cli_actual')
  with self.assertRaises(Exception):control.record(c['id'],{**body,'sequence':1,'data':{'session_id':'another'}})
  with self.assertRaises(Exception):control.record(c['id'],{**body,'attempt_id':'old'})

 def test_readonly_probe_cannot_claim_repair_success_or_submit_pr(self):
  for pr,state in [(None,'TRACE_PROBE_COMPLETED'),(7,'NEEDS_HUMAN')]:
   c={'id':'probe-result','kind':'trace_probe','state':'TRACE_PROBE_RUNNING','cancelled':False,'phase':'trace_probe','attempt_id':'a'};put('case',c['id'],c)
   receipt={'status':'completed','exit_code':0,'output_json':{'evidence_ids':['ev-'+'a'*16],'pr_number':pr,'candidate_sha':None}}
   with patch('lab.control.call',return_value={'case_id':c['id']}) as external:control.result(c['id'],{'attempt_id':'a','result':receipt})
   self.assertEqual(get('case',c['id'])['state'],state)
   self.assertFalse(any('/ops/' in x.args[1] for x in external.call_args_list))

 def test_readonly_phases_cannot_create_engineering_workspace(self):
  for phase in ['TRACE_PROBE_RUNNING','VERIFY_AGENT_RUNNING']:
   with patch('lab.delivery.case_active',return_value={'state':phase}),patch('lab.delivery.repository') as repository:
    with self.assertRaises(Exception):delivery.tool('create_workspace',{'case_id':'readonly'})
    repository.assert_not_called()

 def test_probe_retry_remains_readonly(self):
  c={'id':'probe-retry','kind':'trace_probe','state':'NEEDS_HUMAN','cancelled':False,'phase':'trace_probe','observed_sha':'a'*40,'attempt_id':'old'};put('case',c['id'],c)
  with patch('lab.control.call',return_value={'consistent':True,'runtime':{'source_sha':'a'*40}}):answer=control.retry(c['id'])
  self.assertEqual(answer['state'],'TRACE_PROBE_QUEUED')
