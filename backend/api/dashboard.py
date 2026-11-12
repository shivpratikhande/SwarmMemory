from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.agents.orchestrator import orchestrator
from backend.api.agents import agent_to_dict
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import get_chain
from backend.config import get_settings
from backend.database.connection import get_db
from backend.database.models import ActivityEvent, Agent, Memory, MemoryStatus, Purchase, ReputationEvent, ScenarioRun, Transaction, TxStatus
from backend.memory.capsule import yocto_to_near

router = APIRouter(tags=["dashboard"])


@router.get("/config")
def config() -> dict[str, Any]:
    s = get_settings()
    chain = get_chain()
    return {
        "mode": s.swarm_mode,
        "network": chain.network,
        "contract_id": chain.contract_id,
        "owner_id": chain.owner_id,
        "near_network_id": s.near_network_id if s.is_testnet else None,
        "rpc_url": s.near_rpc_url if s.is_testnet else None,
        "explorer_url": s.near_explorer_url if s.is_testnet else None,
        "wallet_purchases_enabled": s.is_testnet,
    }


@router.get("/dashboard/stats")
def stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    network = get_chain().network
    by_status = dict(db.execute(select(Memory.status, func.count()).group_by(Memory.status)).all())
    purchases = db.execute(select(func.count(), func.coalesce(func.sum(Purchase.price_yocto), 0)).where(Purchase.network == network)).one()
    tx_counts = dict(db.execute(select(Transaction.status, func.count()).where(Transaction.network == network).group_by(Transaction.status)).all())
    try:
        chain_stats = txs.view("get_stats")
    except Exception as e:  # noqa: BLE001
        chain_stats = {"error": str(e)}
    return {
        "network": network,
        "agents": db.execute(select(func.count()).select_from(Agent)).scalar_one(),
        "memories": sum(by_status.values()),
        "verified": by_status.get(MemoryStatus.VERIFIED, 0),
        "disputed": by_status.get(MemoryStatus.DISPUTED, 0),
        "pending": by_status.get(MemoryStatus.PENDING, 0),
        "expired": by_status.get(MemoryStatus.EXPIRED, 0),
        "purchases": purchases[0],
        "near_distributed": yocto_to_near(purchases[1]),
        "transactions": {k.value: v for k, v in tx_counts.items()},
        "chain": chain_stats,
    }


@router.get("/dashboard/activity")
def activity_feed(
    limit: int = Query(default=60, ge=1, le=300),
    scenario_run_id: str | None = None,
    onchain: bool | None = None,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    network = get_chain().network
    q = select(ActivityEvent).where(or_(ActivityEvent.network.is_(None), ActivityEvent.network == network))
    q = q.where(ActivityEvent.kind != "memory.search") if scenario_run_id is None else q
    if scenario_run_id:
        q = q.where(ActivityEvent.scenario_run_id == scenario_run_id)
    if onchain is not None:
        q = q.where(ActivityEvent.onchain == onchain)
    rows = db.execute(q.order_by(ActivityEvent.id.desc()).limit(limit)).scalars().all()
    tx_ids = [r.tx_id for r in rows if r.tx_id]
    tx = {t.id: t for t in db.execute(select(Transaction).where(Transaction.id.in_(tx_ids))).scalars()} if tx_ids else {}
    from backend.api.transactions import explorer_url

    return [
        {
            "id": r.id,
            "kind": r.kind,
            "message": r.message,
            "agent_id": r.agent_id,
            "memory_id": r.memory_id,
            "tx_id": r.tx_id,
            "tx_hash": tx[r.tx_id].tx_hash if r.tx_id in tx else None,
            "tx_status": tx[r.tx_id].status.value if r.tx_id in tx else None,
            "explorer_url": explorer_url(tx[r.tx_id]) if r.tx_id in tx else None,
            "onchain": r.onchain,
            "network": r.network,
            "data": r.data,
            "scenario_run_id": r.scenario_run_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/dashboard/economy")
def economy(db: Session = Depends(get_db)) -> dict[str, Any]:
    network = get_chain().network
    agents = db.execute(select(Agent).order_by(Agent.reputation.desc())).scalars().all()
    rows = []
    for a in agents:
        d = agent_to_dict(a, db)
        try:
            d["claimable_near"] = yocto_to_near(int(txs.view("get_earnings", {"account_id": a.near_account_id})))
            d["total_earned_onchain_near"] = yocto_to_near(int(txs.view("get_total_earned", {"account_id": a.near_account_id})))
            if network == "simulated":
                d["wallet_balance_near"] = yocto_to_near(int(txs.view("get_balance", {"account_id": a.near_account_id})))
        except Exception as e:  # noqa: BLE001
            d["chain_error"] = str(e)
        rows.append(d)
    rep = db.execute(select(ReputationEvent).order_by(ReputationEvent.created_at.desc()).limit(50)).scalars().all()
    volume = db.execute(
        select(func.coalesce(func.sum(Transaction.deposit_yocto), 0)).where(Transaction.network == network, Transaction.status == TxStatus.confirmed)
    ).scalar_one()
    return {
        "network": network,
        "agents": rows,
        "reputation_events": [
            {"agent_id": r.agent_id, "delta": r.delta, "reason": r.reason, "memory_id": r.memory_id, "onchain_tx_id": r.onchain_tx_id, "created_at": r.created_at}
            for r in rep
        ],
        "total_value_moved_near": yocto_to_near(volume),
    }


class ScenarioRequest(BaseModel):
    inject_misleading: bool = False
    price_near: str = "0.01"


def run_to_dict(r: ScenarioRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "status": r.status,
        "network": r.network,
        "options": r.options,
        "steps": r.steps,
        "summary": r.summary,
        "error": r.error,
        "started_at": r.started_at,
        "finished_at": r.finished_at,
    }


@router.post("/scenario/run", status_code=202)
async def run_scenario(body: ScenarioRequest) -> dict[str, Any]:
    return {"run_id": orchestrator.start_scenario(body.model_dump())}


@router.get("/scenario/runs")
def scenario_runs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(select(ScenarioRun).order_by(ScenarioRun.started_at.desc()).limit(20)).scalars().all()
    return [run_to_dict(r) for r in rows]


@router.get("/scenario/runs/{run_id}")
def scenario_run(run_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    r = db.get(ScenarioRun, run_id)
    if r is None:
        raise HTTPException(404, "scenario run not found")
    return run_to_dict(r)
