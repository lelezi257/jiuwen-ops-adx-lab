"""Controller-owned, case-scoped bridge to existing product/tool contracts."""
from fastapi import Header, HTTPException
from lab import execution_auth
from lab.common import call
from lab.tools import READ, WRITE


def execution_case(case):
    if case.get("phase") != "verify":
        return case
    # A review receives completed delivery facts, not stale repair instructions.
    # The original feedback and all previous runs remain in the controller ledger.
    return {**case, "feedback": {
        "phase": "verify",
        "completed_delivery": {
            "pr": case.get("pr"), "ci": case.get("ci"),
            "merge_sha": (case.get("merge") or {}).get("merge_sha"),
            "build": case.get("build"),
            "deployment": (case.get("deployment") or {}).get("ledger")},
        "output_contract": "pr_number and candidate_sha must be null in this read-only review; null does not mean the completed repair PR is missing. Judge the current verification and actual delivery identities. Do not create another PR."}}


def install(app):
    # Import after control's application and state helpers are defined.
    from lab import control

    def context(authorization):
        claims = execution_auth.verify(authorization)
        case = control.case(claims["case_id"])
        if case.get("attempt_id") != claims["attempt_id"] or case.get("phase") != claims["phase"]:
            raise HTTPException(409, "Execution has been superseded")
        return case, claims

    @app.get("/execution/context")
    def execution_context(authorization: str = Header(default="")):
        case, _ = context(authorization)
        return execution_case(case)

    @app.post("/execution/{action}")
    def report(action: str, body: dict, authorization: str = Header(default="")):
        case, claims = context(authorization)
        if body.get("attempt_id") != claims["attempt_id"]:
            raise HTTPException(403, "Attempt is bound by execution grant")
        if action == "heartbeat":
            return control.heartbeat(case["id"], body)
        if action == "event":
            data = body.get("data") or {}
            if data.get("session_id") and case["state"].endswith("STARTING"):
                control.save(case, {"repair": "REPAIRING", "verify": "VERIFY_AGENT_RUNNING",
                                    "trace_probe": "TRACE_PROBE_RUNNING"}[case["phase"]])
            return control.record(case["id"], body)
        if action == "result":
            return control.result(case["id"], body)
        if action == "cancel":
            return control.cancel(case["id"])
        raise HTTPException(404, "Unknown execution operation")

    @app.post("/execution/tools/{name}")
    def tool(name: str, args: dict, authorization: str = Header(default="")):
        case, claims = context(authorization)
        if case["cancelled"] or case["state"] not in {"REPAIRING", "VERIFY_AGENT_RUNNING", "TRACE_PROBE_RUNNING"}:
            raise HTTPException(409, "Execution no longer permits tool calls")
        allowed = {t["name"] for t in READ + (WRITE if claims["phase"] == "repair" else [])}
        if name not in allowed:
            raise HTTPException(403, "Tool is not allowed in this phase")
        if name == "get_verification_report":
            return case.get("verification")
        base = "http://evidence:8080" if name in {"query_metrics", "query_logs", "read_evidence"} else "http://delivery:8080"
        # The sandbox cannot choose another case. The broker owns the service token.
        return call(base, "/tools/" + name, {**args, "case_id": case["id"]}, role="runner", timeout=420)
