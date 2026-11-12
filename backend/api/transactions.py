from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.blockchain.contract_client import get_chain
from backend.config import get_settings
from backend.database.connection import get_db
from backend.database.models import Transaction, TxStatus
from backend.memory.capsule import yocto_to_near

router = APIRouter(prefix="/transactions", tags=["transactions"])


def explorer_url(t: Transaction) -> str | None:
    if t.network != "testnet" or not t.tx_hash:
        return None
    return f"{get_settings().near_explorer_url.rstrip('/')}/txns/{t.tx_hash}"


def tx_to_dict(t: Transaction) -> dict[str, Any]:
    return {
        "id": t.id,
        "network": t.network,
        "simulated": t.network == "simulated",
        "tx_hash": t.tx_hash,
        "explorer_url": explorer_url(t),
        "signer_id": t.signer_id,
        "receiver_id": t.receiver_id,
        "method": t.method,
        "args": t.args,
        "deposit_near": yocto_to_near(t.deposit_yocto or 0),
        "status": t.status.value,
        "error": t.error,
        "return_value": t.return_value,
        "block_hash": t.block_hash,
        "gas_burnt": str(int(t.gas_burnt)) if t.gas_burnt is not None else None,
        "agent_id": t.agent_id,
        "memory_id": t.memory_id,
        "initiated_by": t.initiated_by,
        "created_at": t.created_at,
        "confirmed_at": t.confirmed_at,
    }


@router.get("")
def list_transactions(
    method: str | None = None,
    status: TxStatus | None = None,
    agent_id: str | None = None,
    memory_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    # Only the active network is ever listed: simulated and real txs never mix.
    q = select(Transaction).where(Transaction.network == get_chain().network)
    if method:
        q = q.where(Transaction.method == method)
    if status:
        q = q.where(Transaction.status == status)
    if agent_id:
        q = q.where(Transaction.agent_id == agent_id)
    if memory_id:
        q = q.where(Transaction.memory_id == memory_id)
    rows = db.execute(q.order_by(Transaction.created_at.desc()).limit(limit)).scalars().all()
    return [tx_to_dict(t) for t in rows]


@router.get("/{tx_id}")
def get_transaction(tx_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    t = db.get(Transaction, tx_id)
    if t is None or t.network != get_chain().network:
        raise HTTPException(404, "transaction not found")
    return tx_to_dict(t)
