"""Short-lived execution grants. Platform and broker keys never enter a sandbox."""
import base64
import hashlib
import hmac
import json
import re
import time

from fastapi import HTTPException
from lab.common import secret


def issue(case, ttl=1800):
    payload = {"case_id": case["id"], "attempt_id": case["attempt_id"],
               "phase": case["phase"], "expires_at": int(time.time()) + ttl}
    key = secret("execution_signing_key")
    if not key:
        raise RuntimeError("Execution signing key is not configured")
    body = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True).encode()).decode().rstrip("=")
    signature = hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def verify(authorization):
    try:
        if not authorization.startswith("Bearer "):
            raise ValueError("missing bearer")
        body, supplied = authorization[7:].split(".")
        key = secret("execution_signing_key")
        expected = hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()
        if not key or not hmac.compare_digest(expected, supplied):
            raise ValueError("invalid signature")
        value = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if value["expires_at"] <= time.time() or value["phase"] not in {"repair", "verify", "trace_probe"}:
            raise ValueError("invalid grant")
        if not all(re.fullmatch(r"[a-z][a-z0-9-]{1,100}", value[k]) for k in ("case_id", "attempt_id")):
            raise ValueError("invalid identity")
        return value
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(403, "Invalid or expired execution grant") from None
