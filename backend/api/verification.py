from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.agents.orchestrator import orchestrator
from backend.database.connection import get_db
from backend.database.models import Memory, MemoryStatus, Verification
from backend.memory.capsule import to_public
from backend.memory.verification import expire_stale

router = APIRouter(prefix="/verification", tags=["verification"])


class TriggerRequest(BaseModel):
    memory_id: str | None = Field(default=None, max_length=40)
    verifier_agent_id: str = Field(default="agent-b-verifier", max_length=64)


@router.get("/queue")
def queue(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    if expire_stale(db):
        db.commit()
    rows = db.execute(
        select(Memory)
        .options(selectinload(Memory.contributor))
        .where(Memory.status.in_([MemoryStatus.PENDING, MemoryStatus.EXPIRED]), Memory.superseded_by.is_(None))
        .order_by(Memory.created_at)
    ).scalars().all()
    return [to_public(m).model_dump(mode="json") for m in rows]


@router.get("/history")
def history(result: str | None = Query(default=None, pattern="^(CONFIRMED|DISPUTED)$"), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    q = select(Verification).options(selectinload(Verification.verifier), selectinload(Verification.memory))
    if result:
        q = q.where(Verification.verification_result == result)
    rows = db.execute(q.order_by(Verification.verified_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": v.id,
            "memory_id": v.memory_id,
            "memory_seq": v.memory.seq,
            "memory_title": v.memory.title,
            "memory_status": v.memory.status.value,
            "claim": v.memory.claim,
            "verifier_agent_id": v.verifier_agent_id,
            "verifier_name": v.verifier.name,
            "verification_result": v.verification_result.value,
            "observed_value": v.observed_value,
            "evidence_hash": v.evidence_hash,
            "verification_evidence": v.verification_evidence,
            "notes": v.notes,
            "verified_at": v.verified_at,
            "onchain_tx_id": v.onchain_tx_id,
        }
        for v in rows
    ]


@router.post("/run", status_code=202)
async def run_verification(body: TriggerRequest) -> dict[str, Any]:
    """Trigger the verification agent (optionally for one memory)."""
    opts = {"memory_id": body.memory_id} if body.memory_id else {}
    task = f"Independently reproduce the experiment behind memory {body.memory_id}." if body.memory_id else None
    exe_id = orchestrator.start(body.verifier_agent_id, task, opts)
    return {"execution_id": exe_id, "agent_id": body.verifier_agent_id}
