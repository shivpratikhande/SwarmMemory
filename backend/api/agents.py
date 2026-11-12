from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import activity
from backend.agents.orchestrator import AGENT_CLASSES, orchestrator
from backend.api.deps import agent_api_key
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import get_chain
from backend.database.connection import get_db
from backend.database.models import Agent, AgentExecution, AgentRole, Memory, Purchase, ReputationEvent
from backend.memory.capsule import yocto_to_near

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRegister(BaseModel):
    id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9\-]+$")
    name: str = Field(min_length=2, max_length=120)
    role: AgentRole
    near_account_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9._\-]+$")
    system_prompt: str | None = Field(default=None, max_length=4000)


class ExecuteRequest(BaseModel):
    task: str | None = Field(default=None, max_length=2000)
    options: dict[str, Any] = Field(default_factory=dict)


def agent_to_dict(a: Agent, db: Session) -> dict[str, Any]:
    network = get_chain().network
    spent = db.execute(select(func.coalesce(func.sum(Purchase.price_yocto), 0)).where(Purchase.buyer_agent_id == a.id, Purchase.network == network)).scalar_one()
    earned = db.execute(select(func.coalesce(func.sum(Purchase.price_yocto), 0)).where(Purchase.seller_agent_id == a.id, Purchase.network == network)).scalar_one()
    return {
        "id": a.id,
        "name": a.name,
        "role": a.role.value,
        "system_prompt": a.system_prompt,
        "near_account_id": a.near_account_id,
        "network": network,
        "status": a.status,
        "reputation": a.reputation,
        "tasks_completed": a.tasks_completed,
        "memories_contributed": a.memories_contributed,
        "memories_retrieved": a.memories_retrieved,
        "onchain_registered": a.onchain_registered,
        "spent_near": yocto_to_near(spent),
        "earned_near": yocto_to_near(earned),
        "created_at": a.created_at,
    }


def exe_to_dict(e: AgentExecution) -> dict[str, Any]:
    return {
        "id": e.id,
        "agent_id": e.agent_id,
        "task": e.task,
        "task_type": e.task_type,
        "status": e.status,
        "scenario_run_id": e.scenario_run_id,
        "result": e.result,
        "logs": e.logs,
        "error": e.error,
        "started_at": e.started_at,
        "finished_at": e.finished_at,
    }


@router.post("/register", status_code=201)
def register_agent(body: AgentRegister, db: Session = Depends(get_db)) -> dict[str, Any]:
    if db.get(Agent, body.id) is not None:
        raise HTTPException(409, "agent id already exists")
    if db.execute(select(Agent.id).where(Agent.near_account_id == body.near_account_id)).first():
        raise HTTPException(409, "NEAR account already bound to an agent")
    chain = get_chain()
    if not chain.can_sign(body.near_account_id):
        raise HTTPException(400, f"backend holds no signing key for {body.near_account_id}; add it to the server environment first")
    a = Agent(
        id=body.id,
        name=body.name,
        role=body.role,
        system_prompt=body.system_prompt or AGENT_CLASSES[body.role.value].default_prompt,
        near_account_id=body.near_account_id,
        reputation=0,
        tasks_completed=0,
        memories_contributed=0,
        memories_retrieved=0,
    )
    db.add(a)
    activity.record(db, "agent.created", f"{a.name} joined the swarm as {a.role.value}", agent_id=a.id)
    db.commit()
    tx = orchestrator.ensure_onchain(a.id)
    db.refresh(a)
    out = agent_to_dict(a, db)
    out["api_key"] = agent_api_key(a.id)  # shown once; derived from the server secret
    out["registration_tx_id"] = tx.id if tx else None
    return out


@router.get("")
def list_agents(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    return [agent_to_dict(a, db) for a in db.execute(select(Agent).order_by(Agent.created_at)).scalars()]


@router.get("/{agent_id}")
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    a = db.get(Agent, agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    out = agent_to_dict(a, db)
    out["executions"] = [
        exe_to_dict(e)
        for e in db.execute(select(AgentExecution).where(AgentExecution.agent_id == agent_id).order_by(AgentExecution.started_at.desc()).limit(25)).scalars()
    ]
    out["memories"] = [
        {"memory_id": m.memory_id, "seq": m.seq, "title": m.title, "status": m.status.value, "confidence_score": m.confidence_score, "created_at": m.created_at}
        for m in db.execute(select(Memory).where(Memory.contributor_agent_id == agent_id).order_by(Memory.created_at.desc())).scalars()
    ]
    out["reputation_events"] = [
        {"delta": r.delta, "reason": r.reason, "memory_id": r.memory_id, "onchain_tx_id": r.onchain_tx_id, "created_at": r.created_at}
        for r in db.execute(select(ReputationEvent).where(ReputationEvent.agent_id == agent_id).order_by(ReputationEvent.created_at.desc()).limit(50)).scalars()
    ]
    try:
        out["onchain"] = txs.view("get_agent", {"account_id": a.near_account_id})
    except Exception as e:  # noqa: BLE001
        out["onchain"] = {"error": str(e)}
    return out


@router.post("/{agent_id}/execute", status_code=202)
async def execute_agent(agent_id: str, body: ExecuteRequest) -> dict[str, Any]:
    try:
        exe_id = orchestrator.start(agent_id, body.task, body.options)
    except KeyError as e:
        raise HTTPException(404, "agent not found") from e
    return {"execution_id": exe_id, "status": "queued"}


@router.get("/{agent_id}/executions/{execution_id}")
def get_execution(agent_id: str, execution_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    e = db.get(AgentExecution, execution_id)
    if e is None or e.agent_id != agent_id:
        raise HTTPException(404, "execution not found")
    return exe_to_dict(e)


@router.post("/{agent_id}/withdraw")
def withdraw(agent_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """The agent withdraws its claimable on-chain earnings (signed with its own key)."""
    a = db.get(Agent, agent_id)
    if a is None:
        raise HTTPException(404, "agent not found")
    claimable = int(txs.view("get_earnings", {"account_id": a.near_account_id}))
    if claimable <= 0:
        raise HTTPException(409, "nothing to withdraw")
    try:
        tx = txs.execute(
            a.near_account_id,
            "withdraw_rewards",
            {},
            gas=60 * 10**12,
            ctx=txs.TxContext(agent_id=a.id, message=f"{a.name} withdrew {yocto_to_near(claimable)} NEAR of earned rewards"),
        )
    except txs.ChainCallFailed as e:
        raise HTTPException(502, f"withdrawal failed: {e.tx.error}") from e
    return {"tx_id": tx.id, "tx_hash": tx.tx_hash, "amount_near": yocto_to_near(claimable)}
