"""Verification engine: evidence attestation, status/confidence derivation and the
independent-verification lifecycle (PENDING -> VERIFIED / DISPUTED -> EXPIRED).

Confidence is NEVER taken from an LLM. It is derived from independent
verifications and real usage outcomes:

    confidence = (1 + 2*confirmations + helpful) / (3 + 2*(confirmations + disputes) + helpful + unhelpful)

A fresh, unverified capsule therefore starts at 1/3.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import activity
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import RESULT_TO_CHAIN
from backend.database.models import Agent, Memory, MemoryStatus, Verification, VerificationResult
from backend.memory import reputation
from backend.memory.capsule import Claim, new_id, sha256_hex
from backend.sandbox.apis import SANDBOX_APIS, attest_requests

REVERIFY_COOLDOWN = timedelta(seconds=60)
UNHELPFUL_DISPUTE_MIN = 3


class VerificationError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class VerificationEvidence(BaseModel):
    run_id: str = Field(min_length=4, max_length=64)
    requests: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    summary: dict[str, Any]
    logs: list[str] = Field(default_factory=list, max_length=1000)


class VerificationSubmit(BaseModel):
    verification_result: Literal["CONFIRMED", "DISPUTED"]
    verification_evidence: VerificationEvidence
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    notes: str = Field(default="", max_length=2000)


# ----------------------------------------------------------------------------- pure scoring

def measure(claim: Claim, requests: list[dict[str, Any]]) -> float:
    n = len(requests)
    failures = sum(1 for r in requests if not 200 <= int(r["status"]) < 300)
    return failures / n if claim.metric == "failure_rate" else (n - failures) / n


def compute_confidence(confirm: int, dispute: int, helpful: int, unhelpful: int) -> float:
    return (1 + 2 * confirm + helpful) / (3 + 2 * (confirm + dispute) + helpful + unhelpful)


def compute_status(m: Memory, now: datetime | None = None) -> MemoryStatus:
    now = now or datetime.now(timezone.utc)
    if m.confirm_count == 0 and m.dispute_count == 0:
        status = MemoryStatus.PENDING
    elif m.confirm_count > m.dispute_count:
        status = MemoryStatus.VERIFIED
    else:
        status = MemoryStatus.DISPUTED
    # repeated bad outcomes in real use dispute a memory even if a verifier confirmed it
    if m.not_useful_count >= UNHELPFUL_DISPUTE_MIN and m.not_useful_count > 2 * m.useful_count:
        status = MemoryStatus.DISPUTED
    if status == MemoryStatus.VERIFIED and m.last_verified_at and m.last_verified_at + timedelta(hours=m.ttl_hours) < now:
        status = MemoryStatus.EXPIRED
    return status


def rescore(m: Memory) -> None:
    m.confidence_score = compute_confidence(m.confirm_count, m.dispute_count, m.useful_count, m.not_useful_count)
    m.status = compute_status(m)


def expire_stale(db: Session) -> int:
    """Revalidation sweep: VERIFIED memories past their TTL become EXPIRED."""
    now = datetime.now(timezone.utc)
    stale = db.execute(
        select(Memory).where(Memory.status == MemoryStatus.VERIFIED, Memory.last_verified_at.is_not(None))
    ).scalars()
    n = 0
    for m in stale:
        if m.last_verified_at + timedelta(hours=m.ttl_hours) < now:
            m.status = MemoryStatus.EXPIRED
            activity.record(db, "memory.expired", f"Memory {m.memory_id} expired and needs revalidation", memory_id=m.memory_id)
            n += 1
    return n


def check_evidence(claim: Claim, ev: dict[str, Any], evidence_hash: str) -> float:
    """Validate hash + sandbox attestation and return the metric measured from raw evidence."""
    if sha256_hex(ev) != evidence_hash:
        raise VerificationError(422, "evidence_hash does not match the submitted evidence")
    if claim.target not in SANDBOX_APIS:
        raise VerificationError(422, f"claim target {claim.target} is not reproducible in this environment")
    reqs = ev["requests"]
    if len(reqs) < claim.sample_size:
        raise VerificationError(422, f"evidence has {len(reqs)} requests; claim requires {claim.sample_size}")
    ok, why = attest_requests(claim.target, ev["run_id"], reqs)
    if not ok:
        raise VerificationError(422, f"evidence rejected: {why}")
    return measure(claim, reqs)


# ----------------------------------------------------------------------------- lifecycle

def submit(db: Session, verifier: Agent, memory: Memory, body: VerificationSubmit, scenario_run_id: str | None = None) -> Verification:
    if memory.contributor_agent_id == verifier.id:
        raise VerificationError(403, "agents cannot verify their own memory")
    if memory.superseded_by:
        raise VerificationError(409, f"memory superseded by {memory.superseded_by}; verify the latest version")
    claim = Claim.model_validate(memory.claim)
    ev = body.verification_evidence.model_dump()

    prior = db.execute(
        select(Verification).where(Verification.memory_id == memory.memory_id).order_by(Verification.verified_at)
    ).scalars().all()
    used_runs = {memory.evidence.get("run_id")} | {p.verification_evidence.get("run_id") for p in prior}
    if ev["run_id"] in used_runs:
        raise VerificationError(422, "verification must come from a new, independent run (run_id reused)")
    mine = [p for p in prior if p.verifier_agent_id == verifier.id]
    now = datetime.now(timezone.utc)
    if mine and mine[-1].verified_at + REVERIFY_COOLDOWN > now:
        raise VerificationError(429, "verifier must wait 60s before re-verifying this memory")

    observed = check_evidence(claim, ev, body.evidence_hash)
    expected = "CONFIRMED" if claim.holds_for(observed) else "DISPUTED"
    if body.verification_result != expected:
        raise VerificationError(
            422, f"verdict {body.verification_result} contradicts the verifier's own evidence ({claim.metric}={observed:.3f})"
        )

    tx = txs.execute(
        verifier.near_account_id,
        "record_verification",
        {"memory_id": memory.memory_id, "outcome": RESULT_TO_CHAIN[expected], "evidence_hash": body.evidence_hash},
        ctx=txs.TxContext(
            agent_id=verifier.id,
            memory_id=memory.memory_id,
            scenario_run_id=scenario_run_id,
            message=f"{verifier.name} recorded verification of {memory.memory_id} on-chain ({expected})",
        ),
    )

    v = Verification(
        id=new_id("ver"),
        memory_id=memory.memory_id,
        verifier_agent_id=verifier.id,
        verification_result=VerificationResult(expected),
        verification_evidence=ev,
        evidence_hash=body.evidence_hash,
        observed_value=observed,
        notes=body.notes,
        verified_at=now,
        onchain_tx_id=tx.id,
    )
    db.add(v)

    # Tally = latest vote per distinct verifier (history is never overwritten).
    if mine:
        prev = mine[-1].verification_result
        if prev == VerificationResult.CONFIRMED:
            memory.confirm_count -= 1
        else:
            memory.dispute_count -= 1
    if expected == "CONFIRMED":
        memory.confirm_count += 1
    else:
        memory.dispute_count += 1
    memory.verification_count += 1
    memory.last_verified_at = now
    rescore(memory)
    db.flush()

    activity.record(
        db,
        "memory.verified" if expected == "CONFIRMED" else "memory.disputed",
        f"{verifier.name} independently {'confirmed' if expected == 'CONFIRMED' else 'DISPUTED'} memory #{memory.seq} "
        f"({claim.metric} measured {observed:.0%} over {len(ev['requests'])} requests, claimed {claim.observed:.0%})",
        agent_id=verifier.id,
        memory_id=memory.memory_id,
        scenario_run_id=scenario_run_id,
        data={"observed": observed, "claimed": claim.observed, "result": expected, "status": memory.status.value},
    )

    if not mine:  # reputation only for a verifier's first vote on a memory
        reputation.apply(db, verifier, "verification_submitted", memory_id=memory.memory_id, scenario_run_id=scenario_run_id)
        contributor = db.get(Agent, memory.contributor_agent_id)
        assert contributor is not None
        reputation.apply(
            db,
            contributor,
            "memory_confirmed" if expected == "CONFIRMED" else "memory_disputed",
            memory_id=memory.memory_id,
            detail=f"verified by {verifier.id}",
            scenario_run_id=scenario_run_id,
        )
    return v
