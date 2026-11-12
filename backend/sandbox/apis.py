"""Controlled API testing environment (DEMO CONDITIONS — not claims about real services).

API X fails on 8 of every 20 requests; API Y fails on 1 of every 20.
Which positions fail inside each window of 20 is a seeded permutation of the
caller's run id, so:

* every run reproduces the same reliability,
* two independent runs see different request-level traces,
* the outcome of request *i* in run *r* is a pure function -> the backend can
  attest that submitted evidence matches what the sandbox actually served.
"""
from __future__ import annotations

import hashlib
import random
import threading
from dataclasses import dataclass

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

WINDOW = 20


@dataclass(frozen=True)
class SandboxApi:
    name: str
    display_name: str
    failures_per_window: int
    description: str
    base_latency_ms: int


SANDBOX_APIS: dict[str, SandboxApi] = {
    "api-x": SandboxApi("api-x", "API X", 8, "Weather data service (demo)", 180),
    "api-y": SandboxApi("api-y", "API Y", 1, "Weather data service (demo)", 95),
}


def _rng(api: str, run_id: str, window: int) -> random.Random:
    seed = int.from_bytes(hashlib.sha256(f"{api}:{run_id}:{window}".encode()).digest()[:8], "big")
    return random.Random(seed)


def expected_outcome(api: str, run_id: str, index: int) -> tuple[bool, int]:
    """Return (ok, latency_ms) for the index-th request of a run. Pure function."""
    spec = SANDBOX_APIS[api]
    window, pos = divmod(index, WINDOW)
    rng = _rng(api, run_id, window)
    failing = set(rng.sample(range(WINDOW), spec.failures_per_window))
    latency = spec.base_latency_ms + rng.randint(0, 40) + (pos * 7) % 23
    ok = pos not in failing
    if not ok:
        latency += 900  # failures time out slowly
    return ok, latency


class _Counters:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._n: dict[tuple[str, str], int] = {}

    def next(self, api: str, run_id: str) -> int:
        with self._lock:
            k = (api, run_id)
            i = self._n.get(k, 0)
            if i >= 500:
                raise HTTPException(429, "run budget exhausted; start a new run id")
            self._n[k] = i + 1
            return i


counters = _Counters()
router = APIRouter(prefix="/sandbox", tags=["sandbox"])


@router.get("/apis")
def list_apis() -> list[dict]:
    # Reliability is deliberately NOT advertised: agents must discover it.
    return [
        {"name": a.name, "display_name": a.display_name, "description": a.description, "endpoint": f"/sandbox/apis/{a.name}/data"}
        for a in SANDBOX_APIS.values()
    ]


@router.get("/apis/{api}/data")
def call_api(api: str, x_run_id: str = Header(..., min_length=4, max_length=64)) -> JSONResponse:
    if api not in SANDBOX_APIS:
        raise HTTPException(404, "unknown sandbox api")
    i = counters.next(api, x_run_id)
    ok, latency = expected_outcome(api, x_run_id, i)
    headers = {"X-Request-Index": str(i), "X-Simulated-Latency-Ms": str(latency)}
    if not ok:
        return JSONResponse(status_code=503, content={"error": "upstream_unavailable", "request_index": i}, headers=headers)
    return JSONResponse(
        status_code=200,
        content={"request_index": i, "city": "Lisbon", "temp_c": 18 + i % 5, "source": api},
        headers=headers,
    )


def attest_requests(api: str, run_id: str, requests: list[dict]) -> tuple[bool, str]:
    """Check that a list of {index, status} records matches what the sandbox served."""
    if api not in SANDBOX_APIS:
        return False, f"unknown sandbox api {api}"
    seen: set[int] = set()
    for r in requests:
        try:
            idx = int(r["index"])
            status = int(r["status"])
        except (KeyError, TypeError, ValueError):
            return False, "malformed request record"
        if idx in seen:
            return False, f"duplicate request index {idx}"
        seen.add(idx)
        ok, _ = expected_outcome(api, run_id, idx)
        if ok != (200 <= status < 300):
            return False, f"request {idx} status {status} does not match sandbox record"
    return True, "evidence matches sandbox record"
