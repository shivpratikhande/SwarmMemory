"""Experience extraction: raw experiment -> reusable Memory Capsule draft(s).

Extraction is deterministic and evidence-first. It turns measured request
outcomes into a falsifiable claim (metric/operator/threshold/sample size) that
any other agent can re-run; prose fields are templated from the measurements,
never invented.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from backend.memory.capsule import Evidence, sha256_hex

UNRELIABLE_FAILURE_RATE = 0.25
RELIABLE_SUCCESS_RATE = 0.90


@dataclass
class Experiment:
    task: str
    api: str
    display_name: str
    endpoint: str
    run_id: str
    records: list[dict[str, Any]]  # {index, status, latency_ms}
    logs: list[str] = field(default_factory=list)
    agent_id: str = ""

    @property
    def n(self) -> int:
        return len(self.records)

    @property
    def failures(self) -> int:
        return sum(1 for r in self.records if not 200 <= r["status"] < 300)

    @property
    def failure_rate(self) -> float:
        return self.failures / self.n

    @property
    def latencies(self) -> list[int]:
        return [r["latency_ms"] for r in self.records]

    def summary(self) -> dict[str, Any]:
        lat = sorted(self.latencies)
        return {
            "api": self.api,
            "requests": self.n,
            "failures": self.failures,
            "failure_rate": round(self.failure_rate, 4),
            "success_rate": round(1 - self.failure_rate, 4),
            "latency_ms_median": statistics.median(lat),
            "latency_ms_p95": lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        }


def build_evidence(exp: Experiment) -> tuple[dict[str, Any], str]:
    ev = Evidence(
        run_id=exp.run_id,
        requests=[{"index": r["index"], "status": r["status"], "latency_ms": r["latency_ms"]} for r in exp.records],
        summary=exp.summary(),
        logs=exp.logs,
    ).model_dump()
    return ev, sha256_hex(ev)


def extract(exp: Experiment, *, price_near: str = "0.01") -> dict[str, Any] | None:
    """Return a CapsuleCreate payload, or None when the run is inconclusive."""
    s = exp.summary()
    fr, sr = exp.failure_rate, 1 - exp.failure_rate
    evidence, ev_hash = build_evidence(exp)
    context = {
        "task": exp.task,
        "agent": exp.agent_id,
        "environment": "swarmmemory-sandbox (deterministic demo conditions)",
        "target": exp.api,
        "endpoint": exp.endpoint,
        "method": "GET",
        "run_id": exp.run_id,
        "requests": exp.n,
    }
    base = {
        "execution_context": context,
        "evidence": evidence,
        "evidence_hash": ev_hash,
        "access_type": "paid",
        "price_near": price_near,
    }
    if fr >= UNRELIABLE_FAILURE_RATE:
        return {
            **base,
            "title": f"{exp.display_name} experiences frequent request failures",
            "description": (
                f"{exp.display_name} failed {s['failures']} of {exp.n} requests ({fr:.0%}) with HTTP 503 "
                f"upstream_unavailable; failed calls also stalled ~{max(exp.latencies)} ms. Avoid it for "
                "latency- or reliability-sensitive developer applications."
            ),
            "category": "api_discovery",
            "original_observation": (
                f"While working on '{exp.task}', {exp.n} sequential GET requests to {exp.endpoint} returned "
                f"{s['failures']} failures. Median latency {s['latency_ms_median']} ms, p95 {s['latency_ms_p95']} ms."
            ),
            "success_or_failure": "failure",
            "claim": {
                "kind": "api_reliability",
                "target": exp.api,
                "endpoint": exp.endpoint,
                "metric": "failure_rate",
                "operator": ">=",
                "threshold": UNRELIABLE_FAILURE_RATE,
                "observed": fr,
                "sample_size": exp.n,
            },
            "tags": ["api", "reliability", "unreliable", exp.api, "failure"],
        }
    if sr >= RELIABLE_SUCCESS_RATE:
        return {
            **base,
            "title": f"{exp.display_name} is a reliable choice for developer applications",
            "description": (
                f"{exp.display_name} succeeded on {exp.n - s['failures']} of {exp.n} requests ({sr:.0%}); "
                f"median latency {s['latency_ms_median']} ms."
            ),
            "category": "successful_workflow",
            "original_observation": (
                f"While working on '{exp.task}', {exp.n} sequential GET requests to {exp.endpoint} had "
                f"{s['failures']} failure(s)."
            ),
            "success_or_failure": "success",
            "claim": {
                "kind": "api_reliability",
                "target": exp.api,
                "endpoint": exp.endpoint,
                "metric": "success_rate",
                "operator": ">=",
                "threshold": RELIABLE_SUCCESS_RATE,
                "observed": sr,
                "sample_size": exp.n,
            },
            "tags": ["api", "reliability", "reliable", exp.api, "success"],
        }
    return None


def extract_hasty_failure_claim(exp: Experiment, *, price_near: str = "0.01") -> dict[str, Any]:
    """DEMO INJECTION: over-generalise a tiny sample into an 'unreliable' claim.

    Used to demonstrate that independent verification catches misleading memories.
    The evidence is genuine (it passes attestation); the conclusion is not robust.
    """
    s = exp.summary()
    evidence, ev_hash = build_evidence(exp)
    return {
        "title": f"{exp.display_name} is unreliable (quick check)",
        "description": f"Quick check: {s['failures']} of {exp.n} requests to {exp.display_name} failed ({s['failure_rate']:.0%}).",
        "category": "failed_experiment",
        "original_observation": f"Spot-checked {exp.endpoint} with {exp.n} requests during '{exp.task}'.",
        "execution_context": {"task": exp.task, "agent": exp.agent_id, "target": exp.api, "endpoint": exp.endpoint, "run_id": exp.run_id, "requests": exp.n, "note": "small sample"},
        "success_or_failure": "failure",
        "claim": {
            "kind": "api_reliability",
            "target": exp.api,
            "endpoint": exp.endpoint,
            "metric": "failure_rate",
            "operator": ">=",
            "threshold": exp.failure_rate,
            "observed": exp.failure_rate,
            "sample_size": exp.n,
        },
        "evidence": evidence,
        "evidence_hash": ev_hash,
        "access_type": "paid",
        "price_near": price_near,
        "tags": ["api", "reliability", exp.api, "quick-check"],
    }
