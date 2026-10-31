"""Durable case dispatch over public ADX managed HTTP, never direct Docker."""
import asyncio
import os
from pathlib import Path
import shutil
from urllib.parse import urlencode

import httpx
from lab.common import DATA, all_objects, get, ident, now, put, secret
from lab.execution_auth import issue

QUEUED = {"REPAIR_QUEUED": "repair", "VERIFY_AGENT_QUEUED": "verify", "TRACE_PROBE_QUEUED": "trace_probe"}
STARTING = {"repair": "REPAIR_STARTING", "verify": "VERIFY_STARTING", "trace_probe": "TRACE_PROBE_STARTING"}
busy = set()


def enabled():
    return bool(os.getenv("ADX_GATEWAY") and os.getenv("ADX_TEMPLATE_VERSION") and secret("adx_tenant_token"))


def target(case):
    binding = case["execution_binding"]
    return "urn:adx:binding:" + ":".join([binding["template"], binding["template_version"], binding["binding_id"]])


def client():
    return httpx.Client(base_url=os.environ["ADX_GATEWAY"], verify=os.getenv("ADX_CA_FILE", "/run/adx/public-ca.pem"),
                        headers={"Authorization": "Bearer " + secret("adx_tenant_token")}, timeout=330, trust_env=False)


def grant_file(aid):
    parent = DATA / "execution-grants"
    parent.mkdir(exist_ok=True, mode=0o700)
    return parent / aid


def reserve(case):
    from lab import control
    phase = QUEUED[case["state"]]
    if not case.get("execution_binding") or case["execution_binding"].get("allocation_state") == "RELEASED":
        incarnation = len(case.get("binding_history", [])) + 1
        case["execution_binding"] = {"incarnation": incarnation, "template": os.getenv("ADX_TEMPLATE", "ops-order"),
                                     "template_version": os.environ["ADX_TEMPLATE_VERSION"],
                                     "binding_id": case["id"] + "-e" + str(incarnation),
                                     "allocation_state": "ALLOCATING", "recording_root_id": case["id"]}
    case.update(phase=phase, attempt=case.get("attempt", 0) + 1, attempt_id=ident("attempt"), lease_at=now())
    case["dispatch"] = {"state": "PENDING", "created_at": now()}
    token = issue(case)
    path = grant_file(case["attempt_id"])
    path.write_text(token)
    path.chmod(0o600)
    control.save(case, STARTING[phase], "ADX 按需分配执行环境；尚未开始模型执行")
    return case


def prepare_directory(case):
    root = Path(os.getenv("OPS_CASES_ROOT", "/cases")) / case["id"]
    root.mkdir(exist_ok=True, mode=0o700)
    config = root / "swarm/config"
    config.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("/app/config/swarm.yaml", config / "config.yaml")
    return root


def binding_path(case):
    binding = case["execution_binding"]
    return "/api/agent/v2/templates/{template}/versions/{template_version}/bindings/{binding_id}".format(**binding)


def submit(cid):
    from lab import control
    case = control.case(cid)
    aid = case["attempt_id"]
    token = grant_file(aid).read_text()
    request = {"case_id": cid, "attempt_id": aid, "phase": case["phase"]}
    prepare_directory(case)
    headers = {"X-OPS-Execution-Grant": "Bearer " + token, "X-ADX-Parameters": urlencode({"workspace": cid})}
    # Authorization is owned by ADX; the business grant is a distinct header.
    with client() as http:
        response = http.post("/agent/http/runs", params={"target": target(case)}, headers=headers, json=request)
        if response.status_code not in {200, 202}:
            raise RuntimeError("ADX admission HTTP " + str(response.status_code))
        receipt = response.json()
        if receipt.get("attempt_id") != aid:
            raise RuntimeError("Execution acceptance identity mismatch")
        observed = http.get(binding_path(case))
        observed.raise_for_status()
        value = observed.json()
        binding = value.get("binding", value)
        eid = (binding.get("current") or {}).get("environment_id")
        if not eid:
            raise RuntimeError("ADX did not return authoritative Environment identity")
    with control.mutex:
        fresh = control.case(cid)
        if fresh.get("attempt_id") != aid:
            return
        fresh["execution_binding"].update(environment_id=eid, allocation_state="READY")
        fresh["dispatch"] = {"state": "ACCEPTED", "accepted_at": now(), "execution_id": aid}
        control.save(fresh)
        control.event(cid, "adx.execution.accepted", {"attempt_id": aid, "binding_id": binding["scope"]["binding_id"], "environment_id": eid})


def recover_pending(cid):
    """Read the same task before deciding if a never-accepted request may be sent."""
    from lab import control
    case = control.case(cid)
    token = grant_file(case["attempt_id"]).read_text()
    with client() as http:
        response = http.get("/agent/http/runs/" + case["attempt_id"], params={"target": target(case)},
                            headers={"X-OPS-Execution-Grant": "Bearer " + token, "X-ADX-Parameters": urlencode({"workspace": cid})})
    if response.status_code == 404:
        submit(cid)
    elif response.status_code == 200:
        with control.mutex:
            case = control.case(cid)
            case["dispatch"] = {"state": "ACCEPTED", "reconciled_at": now(), "execution_id": case["attempt_id"]}
            control.save(case)
    else:
        raise RuntimeError("ADX task outcome remains unknown; reconcile original identity")


def cleanup(cid):
    from lab import control
    case = control.case(cid)
    if not case.get("execution_binding") or case["execution_binding"].get("allocation_state") == "RELEASED":
        return
    # SDK process cleanup is complete before its official receipt reaches host status.
    token = grant_file(case["attempt_id"]).read_text()
    with client() as http:
        response = http.get("/agent/http/runs/" + case["attempt_id"], params={"target": target(case)},
                            headers={"X-OPS-Execution-Grant": "Bearer " + token})
        response.raise_for_status()
        if response.json().get("state") not in {"COMPLETED", "OUTCOME_UNKNOWN"}:
            return
        with httpx.Client(timeout=20, trust_env=False) as native:
            check = native.get("http://native-web:8080/api/ops/recordings-ready/" + cid)
            check.raise_for_status()
            if not check.json().get("ready"):
                return
        with control.mutex:
            case = control.case(cid)
            case["cleanup"] = {"state": "REQUESTED", "requested_at": now()}
            control.save(case)
        deleted = http.delete(binding_path(case))
        if deleted.status_code not in {200, 204, 404}:
            raise RuntimeError("ADX deletion not confirmed")
    with control.mutex:
        case = control.case(cid)
        snapshot = {**case["execution_binding"], "allocation_state": "RELEASED", "released_at": now()}
        case["execution_binding"] = snapshot
        case.setdefault("binding_history", []).append(snapshot)
        case["cleanup"] = {"state": "CONFIRMED", "confirmed_at": now()}
        control.save(case)
        control.event(cid, "adx.environment.released", snapshot)


def release_terminal(cid):
    """Explicit operator reconciliation; never reactivates a failed environment."""
    from fastapi import HTTPException
    from lab import control
    with control.mutex:
        case = control.case(cid)
        if case["state"] not in control.TERMINAL:
            raise HTTPException(409, "Cancel or finish the case before releasing its allocation")
        binding = case.get("execution_binding")
        if not binding or binding.get("allocation_state") == "RELEASED":
            return case
        case["cleanup"] = {"state": "REQUESTED", "requested_at": now(), "reason": "operator terminal reconciliation"}
        control.save(case)
    with client() as http:
        observed = http.get(binding_path(case))
        if observed.status_code == 200:
            value = observed.json().get("binding", observed.json())
            binding["environment_id"] = (value.get("current") or {}).get("environment_id")
        elif observed.status_code != 404:
            observed.raise_for_status()
        response = http.delete(binding_path(case))
        if response.status_code not in {200, 204, 404}:
            raise HTTPException(502, "ADX has not confirmed allocation deletion")
    with control.mutex:
        case = control.case(cid)
        snapshot = {**binding, "allocation_state": "RELEASED", "released_at": now()}
        case["execution_binding"] = snapshot
        case.setdefault("binding_history", []).append(snapshot)
        case["cleanup"] = {"state": "CONFIRMED", "confirmed_at": now(), "reason": "operator terminal reconciliation"}
        control.save(case)
        control.event(cid, "adx.environment.released", snapshot)
        return case


async def work(cid, action):
    from lab import control
    try:
        await asyncio.to_thread(action, cid)
    except Exception as exc:
        with control.mutex:
            case = control.case(cid)
            if case["state"] in control.TERMINAL:
                case["cleanup"] = {"state": "PENDING_RECONCILIATION", "reason": type(exc).__name__}
                control.save(case)
            else:
                case["dispatch"] = {**case.get("dispatch", {}), "state": "OUTCOME_UNKNOWN", "reason": str(exc)[:200]}
                control.save(case, "NEEDS_HUMAN", "ADX admission needs reconciliation; no automatic model replay")
    finally:
        busy.discard(cid)


async def loop():
    from lab import control
    while True:
        if enabled():
            with control.mutex:
                cases = all_objects("case")
                active = sum(c["state"] in control.AGENT_STATES and c["state"] not in QUEUED for c in cases)
                for case in cases:
                    if case["id"] in busy:
                        continue
                    action = None
                    if case["state"] in QUEUED and active < int(os.getenv("OPS_MAX_EXECUTIONS", "1")):
                        reserve(case)
                        active += 1
                        action = submit
                    elif case["state"].endswith("STARTING") and case.get("dispatch", {}).get("state") == "PENDING":
                        action = recover_pending
                    elif case["state"] in {"RESOLVED_FIXED", "TRACE_PROBE_COMPLETED", "RECOVERED_ROLLBACK"} and case.get("execution_binding", {}).get("allocation_state") == "READY":
                        action = cleanup
                    if action:
                        busy.add(case["id"])
                        asyncio.create_task(work(case["id"], action))
        await asyncio.sleep(.5)
