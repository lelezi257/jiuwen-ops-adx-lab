import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("LAB_DATA", tempfile.mkdtemp(prefix="ops-adx-tests-"))
from fastapi.testclient import TestClient
from lab import common, control, execution_auth, execution_host


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
        client = TestClient(control.app)
        with patch("lab.execution_broker.call") as upstream:
            response = client.post("/execution/tools/write_source", json={"case_id": "case-other"},
                                   headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 403)
        upstream.assert_not_called()

    def test_superseded_execution_cannot_use_tools_or_submit_results(self):
        token = execution_auth.issue(self.case)
        common.put("case", self.case["id"], {**self.case, "attempt_id": "attempt-next"})
        response = TestClient(control.app).post("/execution/result", json={"attempt_id": "attempt-first"},
                                              headers={"Authorization": "Bearer " + token})
        self.assertEqual(response.status_code, 409)

    def test_duplicate_submission_starts_sdk_only_once(self):
        body = {"case_id": self.case["id"], "attempt_id": self.case["attempt_id"], "phase": self.case["phase"]}
        with patch("lab.execution_host.ready"), patch("lab.execution_host.authorize", new=AsyncMock(return_value=self.case)), \
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
