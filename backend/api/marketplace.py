from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from backend.blockchain.contract_client import get_chain
from backend.database.connection import get_db
from backend.database.models import Memory, MemoryCategory, MemoryStatus, Purchase
from backend.memory.capsule import to_public, yocto_to_near

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("")
def marketplace(
    category: MemoryCategory | None = None,
    status: list[MemoryStatus] | None = Query(default=None),
    sort: str = Query(default="confidence", pattern="^(confidence|price|usage|created_at)$"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    network = get_chain().network
    q = select(Memory).options(selectinload(Memory.contributor)).where(Memory.superseded_by.is_(None))
    if category:
        q = q.where(Memory.category == category)
    if status:
        q = q.where(Memory.status.in_(status))
    order = {"confidence": Memory.confidence_score.desc(), "price": Memory.price_yocto.asc(), "usage": Memory.usage_count.desc(), "created_at": Memory.created_at.desc()}[sort]
    rows = db.execute(q.order_by(order, Memory.seq.desc())).scalars().all()
    counts = dict(
        db.execute(select(Purchase.memory_id, func.count()).where(Purchase.network == network).group_by(Purchase.memory_id)).all()
    )
    revenue = dict(
        db.execute(select(Purchase.memory_id, func.sum(Purchase.price_yocto)).where(Purchase.network == network).group_by(Purchase.memory_id)).all()
    )
    out = []
    for m in rows:
        d = to_public(m).model_dump(mode="json")
        d["purchase_count"] = counts.get(m.memory_id, 0)
        d["revenue_near"] = yocto_to_near(revenue.get(m.memory_id, 0) or 0)
        d["purchasable"] = m.status != MemoryStatus.DISPUTED and int(m.price_yocto) > 0
        out.append(d)
    return out


@router.get("/purchases")
def purchases(limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    network = get_chain().network
    rows = db.execute(select(Purchase).where(Purchase.network == network).order_by(Purchase.created_at.desc()).limit(limit)).scalars().all()
    return [
        {
            "id": p.id,
            "memory_id": p.memory_id,
            "buyer_account_id": p.buyer_account_id,
            "buyer_agent_id": p.buyer_agent_id,
            "seller_agent_id": p.seller_agent_id,
            "price_near": yocto_to_near(p.price_yocto),
            "tx_id": p.tx_id,
            "network": p.network,
            "created_at": p.created_at,
        }
        for p in rows
    ]
