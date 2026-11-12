"""Semantic retrieval over memory capsules (pgvector cosine distance)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from backend.database.models import Memory, MemoryCategory, MemoryStatus
from backend.memory.embeddings import embed


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)
    category: MemoryCategory | None = None
    status: list[MemoryStatus] | None = None
    min_similarity: float = Field(default=0.0, ge=0, le=1)
    include_superseded: bool = False


SortKey = Literal["created_at", "confidence", "usage", "verifications", "price"]


def _filters(q: Select, category: MemoryCategory | None, status: list[MemoryStatus] | None, include_superseded: bool) -> Select:
    if category:
        q = q.where(Memory.category == category)
    if status:
        q = q.where(Memory.status.in_(status))
    if not include_superseded:
        q = q.where(Memory.superseded_by.is_(None))
    return q


def search(db: Session, req: SearchRequest) -> list[tuple[Memory, float]]:
    vec = embed(req.query)
    dist = Memory.embedding.cosine_distance(vec).label("distance")
    q = select(Memory, dist).options(selectinload(Memory.contributor))
    q = _filters(q, req.category, req.status, req.include_superseded).order_by(dist).limit(req.limit)
    out: list[tuple[Memory, float]] = []
    for m, d in db.execute(q).all():
        sim = max(0.0, 1.0 - float(d))
        if sim >= req.min_similarity:
            out.append((m, round(sim, 4)))
    return out


def list_memories(
    db: Session,
    *,
    category: MemoryCategory | None = None,
    status: list[MemoryStatus] | None = None,
    sort: SortKey = "created_at",
    include_superseded: bool = False,
    contributor: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Memory]:
    order = {
        "created_at": Memory.created_at.desc(),
        "confidence": Memory.confidence_score.desc(),
        "usage": Memory.usage_count.desc(),
        "verifications": Memory.verification_count.desc(),
        "price": Memory.price_yocto.asc(),
    }[sort]
    q = select(Memory).options(selectinload(Memory.contributor))
    q = _filters(q, category, status, include_superseded)
    if contributor:
        q = q.where(Memory.contributor_agent_id == contributor)
    return list(db.execute(q.order_by(order, Memory.seq.desc()).limit(limit).offset(offset)).scalars())
