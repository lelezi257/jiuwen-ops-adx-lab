import os,tempfile,time,unittest
os.environ.setdefault("LAB_DATA",tempfile.mkdtemp(prefix="ops-experience-tests-"))
from pathlib import Path
from unittest.mock import patch
from lab import common,experience

class OperatorEvidenceBoundaries(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.data=patch('lab.common.DATA',Path(self.temp.name));self.data.start();common.init_store()
 def tearDown(self):self.data.stop();self.temp.cleanup()
 def test_accepting_action_is_not_business_success(self):
  with patch('lab.experience.call') as network:
   op=experience.submit('baseline');network.assert_not_called()
  self.assertEqual(op['state'],'QUEUED');self.assertIsNone(common.get('experiment',op['experiment_id'])['baseline'])
 def test_failed_business_baseline_never_marks_good(self):
  op=experience.submit('baseline');current={'ledger':{'release_id':'r','source_sha':'a','image_digest':'d'}}
  with patch('lab.experience.call',side_effect=[current,{'verification_id':'v','passed':False,'windows':[]}]) as network:experience.run_operation(op['id'])
  self.assertEqual(common.get('operation',op['id'])['state'],'FAILED');self.assertFalse(common.get('experiment',op['experiment_id'])['baseline']['passed']);self.assertEqual(network.call_count,2)
 def test_published_container_is_not_reproduced_fault(self):
  op=experience.submit('fault');published={'consistent':True,'ledger':{'release_id':'fault-r','source_sha':'bad'}}
  with patch('lab.experience.call',side_effect=[{},published]),patch('lab.experience.time.monotonic',side_effect=[0,41]):experience.run_operation(op['id'])
  result=common.get('operation',op['id']);self.assertEqual(result['state'],'FAILED');self.assertEqual(result['result'],published);self.assertIsNone(common.get('experiment',op['experiment_id'])['fault'])
 def test_wrong_release_500_is_not_fault_evidence(self):
  op=experience.submit('fault');published={'ledger':{'release_id':'fault-r','source_sha':'bad'}}
  wrong={'observation_id':'obs','observed_at':time.time()+1,'version_stable':True,'version':{'release_id':'other','source_sha':'bad'},'requests':[{'path':'no_coupon','status':500}]}
  with patch('lab.experience.call',side_effect=[{},published,[wrong]]),patch('lab.experience.time.monotonic',side_effect=[0,1,41]),patch('lab.experience.time.sleep'):experience.run_operation(op['id'])
  self.assertEqual(common.get('operation',op['id'])['state'],'FAILED');self.assertIsNone(common.get('experiment',op['experiment_id'])['fault'])
 def test_real_fault_anchor_survives_recovery_and_links_case(self):
  op=experience.submit('fault');published={'ledger':{'release_id':'fault-r','source_sha':'bad'}}
  evidence={'observation_id':'obs','observed_at':time.time()+1,'version_stable':True,'version':{'release_id':'fault-r','source_sha':'bad'},'requests':[{'path':'no_coupon','status':500}]}
  c={'id':'case-real','state':'REPAIRING','observed_release':'fault-r','sdk_runs':{'a':{'session_id':'s1'}}};common.put('case',c['id'],c)
  with patch('lab.experience.call',side_effect=[{},published,[evidence]]):experience.run_operation(op['id'])
  self.assertEqual(common.get('operation',op['id'])['stage'],'FAULT_CONFIRMED')
  experience.record_recovery(c,{'passed':True,'verification_id':'v','release_id':'fixed-r','windows':[]})
  e=common.get('experiment',op['experiment_id']);self.assertEqual(e['fault'],evidence);self.assertEqual(e['case_id'],c['id']);self.assertTrue(e['recovery']['passed']);self.assertEqual(common.get('case',c['id'])['sdk_runs'],c['sdk_runs'])
 def test_stale_observation_does_not_show_current_healthy(self):
  old={'state':'HEALTHY','observed_at':time.time()-30,'observation_id':'old'}
  with patch('lab.experience.call',return_value=old):result=experience.business()
  self.assertEqual(result['state'],'UNKNOWN');self.assertTrue(result['stale'])
 def test_restart_retains_publication_fact_without_replay(self):
  op={'id':'op','state':'RUNNING','result':{'ledger':{'release_id':'published'}}};common.put('operation','op',op)
  with patch('lab.experience.call') as network:experience.interrupt_unfinished();network.assert_not_called()
  result=common.get('operation','op');self.assertEqual(result['state'],'INTERRUPTED');self.assertEqual(result['result'],op['result'])
 def test_active_case_or_action_prevents_duplicate_fault(self):
  op=experience.submit('baseline')
  with self.assertRaises(Exception):experience.submit('fault')
  common.put('operation',op['id'],{**common.get('operation',op['id']),'state':'SUCCEEDED'});common.put('case','active',{'state':'VERIFY_AGENT_RUNNING'})
  with self.assertRaises(Exception):experience.submit('fault')
 def test_two_true_sessions_are_preserved_as_two_runs(self):
  runs={'repair-attempt':{'session_id':'sdk-first','phase':'repair'},'verify-attempt':{'session_id':'sdk-second','phase':'verify'}}
  result=experience.case_summary({'id':'case','sdk_runs':runs});self.assertEqual(result['sdk_runs'],runs)
 def test_changed_baseline_identity_stops_before_fault_publication(self):
  baseline=experience.submit('baseline');experience.set_operation(baseline['id'],state='SUCCEEDED');experience.update_round(baseline['experiment_id'],baseline={'passed':True,'release_id':'r','expected_source_sha':'old','expected_image_digest':'d'})
  op=experience.submit('fault')
  with patch('lab.experience.call',return_value={'ledger':{'release_id':'r','source_sha':'changed','image_digest':'d'}}) as network:experience.run_operation(op['id'])
  self.assertEqual(network.call_count,1);self.assertEqual(common.get('operation',op['id'])['state'],'FAILED')
 def test_agent_claim_does_not_wait_for_fault_display_confirmation(self):
  from lab import control
  common.put('operation','waiting-for-observation',{'id':'waiting-for-observation','state':'RUNNING','stage':'CONFIRMING_FAULT'})
  common.put('case','ready-agent',{'id':'ready-agent','state':'REPAIR_QUEUED','cancelled':False,'attempt':0})
  claimed=control.claim({});self.assertEqual(claimed['id'],'ready-agent');self.assertEqual(claimed['state'],'REPAIRING');self.assertEqual(claimed['phase'],'repair')
 def test_queued_case_has_empty_session_mapping_until_sdk_starts(self):
  self.assertEqual(experience.case_summary({'id':'queued','state':'REPAIR_QUEUED'})['sdk_runs'],{})

 def test_quick_baseline_checks_both_paths_twice_without_waiting(self):
  from lab import probe
  from unittest.mock import MagicMock
  version={'release_id':'r','source_sha':'a','image_digest':'d'}
  for failed in (False,True):
   client=MagicMock();client.get.return_value.status_code=200;client.get.return_value.json.side_effect=lambda:version if client.get.call_args.args[0].endswith('/version') else {'total_cents':20000}
   client.post.return_value.status_code=422
   def sampled(coupon):return {'path':'coupon' if coupon else 'no_coupon','ok':not failed,'status':500 if failed else 200}
   with self.subTest(failed=failed),patch('lab.probe.httpx.Client') as factory,patch('lab.probe.sample',side_effect=sampled) as sample,patch('lab.probe.time.sleep') as sleep:
    factory.return_value.__enter__.return_value=client
    common.put('baseline','old_order',{'id':'old','total_cents':20000})
    report=probe.baseline(version)
    self.assertEqual(report['passed'],not failed)
    self.assertEqual(report['windows'][0]['counts'],{'coupon':2,'no_coupon':2})
    self.assertEqual(sample.call_count,4);sleep.assert_not_called()
 def test_recovery_endpoint_does_not_accept_baseline_shortcut(self):
  from lab import probe
  args={'quick_baseline':True,'seconds':0,'windows':1}
  with patch('lab.probe.verify_contract',return_value={}) as contract:
   probe.verify(args);contract.assert_called_once_with(args)
