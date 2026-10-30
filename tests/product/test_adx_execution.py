import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LAB_DATA", tempfile.mkdtemp(prefix="ops-adx-tests-"))
from fastapi.testclient import TestClient
from lab import common, control, execution_auth, execution_host
from lab.broker_app import create_app
from lab.execution_broker import execution_case


class AdxExecutionBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.data = patch("lab.common.DATA", Path(self.temp.name))
        self.data.start()
        common.init_store()
        self.key = patch("lab.execution_auth.secret", return_value="test-only-signing-key")
        self.key.start()
        self.case = {"id": "case-abc", "attempt_id": "attempt-first", "attempt": 1,
                     "phase": "verify", "state": "VERIFY_AGENT_RUNNING", "cancelled": False}
        common.put("case", self.case["id"], self.case)

    def tearDown(self):
        self.key.stop()
        self.data.stop()
        self.temp.cleanup()

    def test_grant_cannot_be_tampered_or_used_after_expiry(self):
        grant = execution_auth.issue(self.case)
        self.assertEqual(execution_auth.verify("Bearer " + grant)["case_id"], self.case["id"])
        for value in (grant + "x", execution_auth.issue(self.case, ttl=-1)):
            with self.assertRaises(Exception):
                execution_auth.verify("Bearer " + value)

    def test_readonly_execution_cannot_write_even_if_sandbox_requests_it(self):
        token = execution_auth.issue(self.case)
        client = TestClient(create_app())
        with patch("lab.execution_broker.call") as upstream:
            response = client.post("/execution/tools/write_source", json={"case_id": "case-other"},
                                   headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_superseded_execution_cannot_use_tools_or_submit_results(self):
        token = execution_auth.issue(self.case)
        common.put("case", self.case["id"], {**self.case, "attempt_id": "attempt-next"})
        response = TestClient(create_app()).post("/execution/result", json={"attempt_id": "attempt-first"},
                                              headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 409)

    def test_duplicate_submission_starts_sdk_only_once(self):
        body = {"case_id": self.case["id"], "attempt_id": self.case["attempt_id"], "phase": self.case["phase"]}
        with patch.dict(os.environ, {"OPS_CASE_ID": self.case["id"]}), patch("lab.execution_host.ready"), patch("lab.execution_host.authorize", new=AsyncMock(return_value=self.case)), \
                patch("lab.execution_host.execute", new=AsyncMock()) as execute:
            client = TestClient(execution_host.app)
            first = client.post("/runs", json=body, headers={"X-OPS-Execution-Grant": "Bearer scoped"})
            second = client.post("/runs", json=body, headers={"X-OPS-Execution-Grant": "Bearer scoped"})
            conflict = client.post("/runs", json={**body, "other": True}, headers={"X-OPS-Execution-Grant": "Bearer scoped"})
        self.assertEqual((first.status_code, second.status_code, conflict.status_code), (202, 202, 409))
        self.assertEqual(execute.call_count, 1)

    def test_control_legacy_claim_is_disabled_in_adx_mode(self):
        with patch.dict(os.environ, {"OPS_EXECUTION_BACKEND": "adx"}):
            with self.assertRaises(Exception):
                control.claim({})

    def test_broker_does_not_expose_workbench_or_other_cases(self):
        client = TestClient(create_app())
        for path in ("/api/cases", "/api/status", "/api/cases/case-other", "/openapi.json"):
            self.assertEqual(client.get(path).status_code, 404)

    def test_valid_grant_cannot_be_used_in_a_different_case_sandbox(self):
        with patch.dict(os.environ, {"OPS_CASE_ID": "case-other"}):
            with self.assertRaises(Exception):
                execution_host.require_owned_case(self.case)

    def test_broker_overwrites_caller_supplied_case_with_grant_owner(self):
        token = execution_auth.issue(self.case)
        with patch("lab.execution_broker.call", return_value={"ok": True}) as upstream:
            response = TestClient(create_app()).post("/execution/tools/query_metrics", json={"case_id": "case-other"},
                                                   headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(upstream.call_args.args[2]["case_id"], self.case["id"])

    def test_operator_release_does_not_delete_an_active_execution(self):
        from lab.adx_dispatch import release_terminal
        with patch("lab.adx_dispatch.client") as platform:
            with self.assertRaises(Exception):
                release_terminal(self.case["id"])
        platform.assert_not_called()

    def test_delivery_reconciliation_requires_exact_original_open_pr(self):
        current = {**self.case, "state": "NEEDS_HUMAN", "phase": "repair", "observed_sha": "source-a",
                   "pr": {"number": 7, "head_sha": "candidate-a"}}
        common.put("case", current["id"], current)
        runtime = {"consistent": True, "runtime": {"source_sha": "source-a"}}
        for checked in ({"state": "merged", "pr": current["pr"]},
                        {"state": "passed", "pr": {"number": 7, "head_sha": "candidate-b"}}):
            with patch("lab.control.call", side_effect=[runtime, checked]):
                with self.assertRaises(Exception):
                    control.resume_delivery(current["id"])
            self.assertEqual(common.get("case", current["id"])["state"], "NEEDS_HUMAN")

    def test_delivery_reconciliation_resumes_without_replaying_agent(self):
        current = {**self.case, "state": "NEEDS_HUMAN", "phase": "repair", "observed_sha": "source-a",
                   "pr": {"number": 7, "head_sha": "candidate-a"}}
        common.put("case", current["id"], current)
        runtime = {"consistent": True, "runtime": {"source_sha": "source-a"}}
        checked = {"state": "passed", "pr": current["pr"], "run_id": 11}
        with patch("lab.control.call", side_effect=[runtime, checked]):
            result = control.resume_delivery(current["id"])
        self.assertEqual(result["state"], "READY_TO_MERGE")
        self.assertEqual(result["attempt_id"], current["attempt_id"])
        self.assertEqual(result["attempt"], current["attempt"])

    def test_retry_cannot_race_an_uncertain_resource_release(self):
        current = {**self.case, "state": "NEEDS_HUMAN", "cleanup": {"state": "REQUESTED"}}
        common.put("case", current["id"], current)
        with patch("lab.control.call") as upstream:
            with self.assertRaises(Exception):
                control.retry(current["id"])
        upstream.assert_not_called()

    def test_release_reserves_cleanup_before_platform_delete(self):
        from lab.adx_dispatch import release_terminal
        import httpx
        current = {**self.case, "state": "NEEDS_HUMAN", "execution_binding": {
            "template": "ops-order", "template_version": "1", "binding_id": "case-abc-e1", "allocation_state": "READY"}}
        common.put("case", current["id"], current)
        def delete(*args):
            self.assertEqual(common.get("case", current["id"])["cleanup"]["state"], "REQUESTED")
            with self.assertRaises(Exception):
                control.retry(current["id"])
            return httpx.Response(200)
        with patch("lab.adx_dispatch.client") as platform:
            platform.return_value.__enter__.return_value.get.return_value = httpx.Response(404)
            platform.return_value.__enter__.return_value.delete.side_effect = delete
            result = release_terminal(current["id"])
        self.assertEqual(result["execution_binding"]["allocation_state"], "RELEASED")

    def test_review_context_uses_completed_delivery_without_stale_repair_feedback(self):
        original = {**self.case, "feedback": {"previous_result": "old repair had no PR"},
                    "pr": {"number": 7}, "merge": {"merge_sha": "actual-merge"},
                    "ci": {"state": "passed"}, "build": {"state": "ready"},
                    "deployment": {"ledger": {"source_sha": "actual-merge"}}}
        value = execution_case(original)
        self.assertEqual(value["feedback"]["completed_delivery"]["pr"]["number"], 7)
        self.assertEqual(value["feedback"]["completed_delivery"]["merge_sha"], "actual-merge")
        self.assertNotIn("previous_result", value["feedback"])
        self.assertEqual(original["feedback"], {"previous_result": "old repair had no PR"})

    def test_historical_run_identity_comes_from_its_actual_acceptance_not_current_environment(self):
        current = {**self.case, "execution_binding": {"binding_id": "case-e2", "environment_id": "new-env"},
                   "sdk_runs": {"attempt-old": {"session_id": "old-session"}}}
        common.put("case", current["id"], current)
        control.event(current["id"], "adx.execution.accepted", {
            "attempt_id": "attempt-old", "binding_id": "case-e1", "environment_id": "old-env"})
        value = control.case(current["id"])
        self.assertEqual(value["sdk_runs"]["attempt-old"]["environment_id"], "old-env")
        self.assertEqual(value["sdk_runs"]["attempt-old"]["binding_id"], "case-e1")
