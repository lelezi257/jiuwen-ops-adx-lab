"""ADX-launched HTTP host. All model execution remains in official Process SDK."""
import asyncio
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Header, HTTPException
from lab.common import DATA, all_objects, get, init_store, now, put
from lab.execution_context import grant

CONTROL = os.getenv("OPS_CONTROL_URL", "http://172.29.0.2:8080")
lock = asyncio.Lock()
tasks = set()
capabilities = None
startup_error = None


def load_model():
    path = Path(os.getenv("OPS_MODEL_FILE", "/run/ops/model.env"))
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip().isidentifier():
                os.environ[key.strip()] = value.strip().strip("\"").strip("'")


async def authorize(value):
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.get(CONTROL + "/execution/context", headers={"Authorization": value})
        if response.status_code != 200:
            raise HTTPException(response.status_code, "Execution grant rejected by broker")
        return response.json()


async def execute(case, token):
    from lab import runner
    aid = case["attempt_id"]
    identity = grant.set(token)
    try:
        item = get("execution", aid)
        put("execution", aid, {**item, "state": "RUNNING", "started_at": now()})
        await runner.execute(case)
        receipt = DATA / "reports" / aid / "official-result.json"
        actual = json.loads(receipt.read_text()) if receipt.exists() else None
        put("execution", aid, {**get("execution", aid), "state": "COMPLETED" if actual else "OUTCOME_UNKNOWN",
                               "finished_at": now(), "official_receipt": actual})
    except Exception as exc:
        put("execution", aid, {**get("execution", aid), "state": "OUTCOME_UNKNOWN",
                               "error": type(exc).__name__, "finished_at": now()})
    finally:
        grant.reset(identity)


@asynccontextmanager
async def lifespan(app):
    global capabilities, startup_error
    load_model()
    init_store()
    # A restart must never silently replay a model or tool side effect.
    for item in all_objects("execution"):
        if item["state"] in {"ACCEPTED", "RUNNING"}:
            put("execution", item["attempt_id"], {**item, "state": "OUTCOME_UNKNOWN"})
    try:
        from lab import runner
        runner.CONTROL = CONTROL
        capabilities = await runner.client().query("protocol.capabilities", deadline_seconds=90)
        if capabilities.get("status") != "completed" or not all(
            capabilities["data"]["features"].get(k) for k in ("host_tools", "structured_output", "empty_tools", "max_turns", "cancel")
        ):
            raise RuntimeError("Official SDK capabilities unavailable")
        if not runner.configured():
            raise RuntimeError("Model configuration missing")
    except Exception as exc:
        startup_error = type(exc).__name__
    yield
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)


@app.get("/ready")
def ready():
    if startup_error or capabilities is None:
        raise HTTPException(503, startup_error or "SDK capability check pending")
    return {"ok": True, "engine": "official Process SDK → Swarm Runtime → Core", "fake_model": False}


@app.post("/runs", status_code=202)
async def accept(body: dict, authorization: str = Header(default="", alias="X-OPS-Execution-Grant")):
    ready()
    case = await authorize(authorization)
    if any(body.get(k) != case.get(k if k != "case_id" else "id") for k in ("case_id", "attempt_id", "phase")):
        raise HTTPException(403, "Execution identity does not match grant")
    if case["cancelled"]:
        raise HTTPException(409, "Case is cancelled")
    aid = case["attempt_id"]
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    async with lock:
        prior = get("execution", aid)
        if prior:
            if prior["request_digest"] != digest:
                raise HTTPException(409, "Same execution identity with different request")
            return prior
        if any(x["state"] in {"ACCEPTED", "RUNNING"} for x in all_objects("execution")):
            raise HTTPException(409, "Another execution is active in this case environment")
        item = {"case_id": case["id"], "attempt_id": aid, "phase": case["phase"],
                "state": "ACCEPTED", "request_digest": digest, "accepted_at": now()}
        put("execution", aid, item)
        task = asyncio.create_task(execute(case, authorization[7:]))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return item


@app.get("/runs/{aid}")
async def status(aid: str, authorization: str = Header(default="", alias="X-OPS-Execution-Grant")):
    case = await authorize(authorization)
    if case["attempt_id"] != aid:
        raise HTTPException(403, "Execution identity does not match grant")
    item = get("execution", aid)
    if not item:
        raise HTTPException(404, "Execution was not accepted")
    return item


@app.post("/runs/{aid}/cancel")
async def cancel(aid: str, authorization: str = Header(default="", alias="X-OPS-Execution-Grant")):
    case = await authorize(authorization)
    if case["attempt_id"] != aid:
        raise HTTPException(403, "Execution identity does not match grant")
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        response = await client.post(CONTROL + "/execution/cancel", json={"attempt_id": aid},
                                     headers={"Authorization": authorization})
        response.raise_for_status()
    return {"cancel_requested": True, "attempt_id": aid, "process_exit_confirmed": False}
