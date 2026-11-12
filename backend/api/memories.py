from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend import activity
from backend.api.deps import current_agent, optional_agent
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import get_chain
from backend.database.connection import get_db
from backend.database.models import (
    AccessType,
    Agent,
    Memory,
    MemoryCategory,
    MemoryStatus,
    MemoryVersion,
    Purchase,
    Transaction,
    TxStatus,
    Verification,
)
from backend.memory import retrieval, store, verification
from backend.memory.capsule import CapsuleCreate, CapsuleFull, CapsulePublic, new_id, to_full, to_public, yocto_to_near
from backend.memory.retrieval import SearchRequest, SortKey

router = APIRouter(prefix="/memories", tags=["memories"])

ScenarioHeader = Header(default=None, alias="X-Scenario-Run", max_length=40)


def _load(db: Session, memory_id: str, lock: bool = False) -> Memory:
    q = select(Memory).options(selectinload(Memory.contributor)).where(Memory.memory_id == memory_id)
    if lock:
        q = q.with_for_update(of=Memory)
    m = db.execute(q).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "memory not found")
    return m


def _view(db: Session, m: Memory, viewer: Agent | None, similarity: float | None = None) -> CapsulePublic | CapsuleFull:
    if viewer is not None and store.has_access(db, m, viewer):
        return to_full(m, similarity=similarity)
    return to_public(m, has_access=m.access_type == AccessType.free, similarity=similarity)


@router.post("", status_code=201, response_model=CapsulePublic)
def create_memory(
    body: CapsuleCreate,
    agent: Agent = Depends(current_agent),
    db: Session = Depends(get_db),
    scenario: str | None = ScenarioHeader,
) -> CapsulePublic:
    try:
        m = store.create(db, agent, body, scenario_run_id=scenario)
    except store.MemoryError_ as e:
        raise HTTPException(e.status_code, e.detail) from e
    except txs.ChainCallFailed as e:
        db.rollback()
        raise HTTPException(502, f"on-chain registration failed: {e.tx.error}") from e
    db.commit()
    return to_public(_load(db, m.memory_id), has_access=True)


@router.get("", response_model=list[CapsulePublic])
def list_memories(
    category: MemoryCategory | None = None,
    status: list[MemoryStatus] | None = Query(default=None),
    sort: SortKey = "created_at",
    contributor: str | None = None,
    include_superseded: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    viewer: Agent | None = Depends(optional_agent),
    db: Session = Depends(get_db),
) -> list[CapsulePublic]:
    if verification.expire_stale(db):
        db.commit()
    rows = retrieval.list_memories(
        db, category=category, status=status, sort=sort, include_superseded=include_superseded, contributor=contributor, limit=limit, offset=offset
    )
    return [to_public(m, has_access=m.access_type == AccessType.free or (viewer is not None and viewer.id == m.contributor_agent_id)) for m in rows]


@router.post("/search", response_model=list[CapsulePublic])
def search_memories(
    body: SearchRequest,
    viewer: Agent | None = Depends(optional_agent),
    db: Session = Depends(get_db),
    scenario: str | None = ScenarioHeader,
) -> list[CapsulePublic]:
    if verification.expire_stale(db):
        db.commit()
    hits = retrieval.search(db, body)
    out = []
    for m, sim in hits:
        mine = viewer is not None and viewer.id == m.contributor_agent_id
        bought = viewer is not None and not mine and m.access_type == AccessType.paid and db.execute(
            select(Purchase.id).where(Purchase.memory_id == m.memory_id, Purchase.buyer_account_id == viewer.near_account_id, Purchase.network == get_chain().network)
        ).first() is not None
        out.append(to_public(m, has_access=m.access_type == AccessType.free or mine or bought, similarity=sim))
    if viewer is not None:
        activity.record(
            db,
            "memory.search",
            f"{viewer.name} searched collective memory: “{body.query[:80]}” ({len(out)} results)",
            agent_id=viewer.id,
            scenario_run_id=scenario,
            data={"results": [m.memory_id for m in out[:5]]},
        )
        db.commit()
    return out


@router.get("/{memory_id}")
def get_memory(
    memory_id: str,
    viewer: Agent | None = Depends(optional_agent),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    m = _load(db, memory_id)
    view = _view(db, m, viewer)
    if isinstance(view, CapsuleFull) and viewer is not None:
        store.record_access(db, m, viewer)
        db.commit()
    return view.model_dump(mode="json")


@router.get("/{memory_id}/details")
def memory_details(memory_id: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Public lifecycle view: verification history (with verifier evidence), versions, purchases, txs."""
    m = _load(db, memory_id)
    vers = db.execute(
        select(Verification).options(selectinload(Verification.verifier)).where(Verification.memory_id == memory_id).order_by(Verification.verified_at)
    ).scalars().all()
    versions = db.execute(select(MemoryVersion).where(MemoryVersion.memory_id == memory_id).order_by(MemoryVersion.version)).scalars().all()
    lineage = []
    cur: Memory | None = m
    while cur is not None and cur.parent_memory_id:
        cur = db.get(Memory, cur.parent_memory_id)
        if cur:
            lineage.append({"memory_id": cur.memory_id, "version": cur.version, "status": cur.status.value, "created_at": cur.created_at})
    network = get_chain().network
    purchases = db.execute(select(Purchase).where(Purchase.memory_id == memory_id, Purchase.network == network).order_by(Purchase.created_at)).scalars().all()
    txs_rows = db.execute(
        select(Transaction).where(Transaction.memory_id == memory_id, Transaction.network == network).order_by(Transaction.created_at)
    ).scalars().all()
    return {
        "memory": to_public(m).model_dump(mode="json"),
        "verifications": [
            {
                "id": v.id,
                "verifier_agent_id": v.verifier_agent_id,
                "verifier_name": v.verifier.name,
                "verification_result": v.verification_result.value,
                "observed_value": v.observed_value,
                "verification_evidence": v.verification_evidence,
                "evidence_hash": v.evidence_hash,
                "notes": v.notes,
                "verified_at": v.verified_at,
                "onchain_tx_id": v.onchain_tx_id,
            }
            for v in vers
        ],
        "versions": [{"version": v.version, "reason": v.reason, "created_at": v.created_at} for v in versions],
        "lineage": lineage,
        "purchases": [
            {"buyer_account_id": p.buyer_account_id, "buyer_agent_id": p.buyer_agent_id, "price_near": yocto_to_near(p.price_yocto), "tx_id": p.tx_id, "created_at": p.created_at}
            for p in purchases
        ],
        "transactions": [_tx_dict(t) for t in txs_rows],
    }


@router.get("/{memory_id}/onchain")
def memory_onchain(memory_id: str) -> dict[str, Any] | None:
    """Live contract state for this memory (actual contract read)."""
    return txs.view("get_memory", {"memory_id": memory_id})


# ----------------------------------------------------------------------------- verification

@router.post("/{memory_id}/verify", status_code=201)
def verify_memory(
    memory_id: str,
    body: verification.VerificationSubmit,
    agent: Agent = Depends(current_agent),
    db: Session = Depends(get_db),
    scenario: str | None = ScenarioHeader,
) -> dict[str, Any]:
    m = _load(db, memory_id, lock=True)
    try:
        v = verification.submit(db, agent, m, body, scenario_run_id=scenario)
    except verification.VerificationError as e:
        raise HTTPException(e.status_code, e.detail) from e
    except txs.ChainCallFailed as e:
        db.rollback()
        raise HTTPException(502, f"on-chain verification record failed: {e.tx.error}") from e
    db.commit()
    return {
        "id": v.id,
        "memory_id": memory_id,
        "verifier_agent_id": agent.id,
        "verification_result": v.verification_result.value,
        "observed_value": v.observed_value,
        "verified_at": v.verified_at,
        "onchain_tx_id": v.onchain_tx_id,
        "memory_status": m.status.value,
        "confidence_score": m.confidence_score,
    }


# ----------------------------------------------------------------------------- purchase

class WalletProof(BaseModel):
    account_id: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9._\-]+$")
    tx_hash: str = Field(min_length=20, max_length=80, pattern=r"^[1-9A-HJ-NP-Za-km-z]+$")


class PurchaseRequest(BaseModel):
    wallet: WalletProof | None = None


def _tx_dict(t: Transaction) -> dict[str, Any]:
    from backend.api.transactions import tx_to_dict

    return tx_to_dict(t)


@router.post("/{memory_id}/purchase")
def purchase_memory(
    memory_id: str,
    body: PurchaseRequest,
    agent: Agent | None = Depends(optional_agent),
    db: Session = Depends(get_db),
    scenario: str | None = ScenarioHeader,
) -> dict[str, Any]:
    m = _load(db, memory_id)
    if m.access_type == AccessType.free:
        raise HTTPException(400, "memory is free; no purchase needed")
    network = get_chain().network
    contributor = m.contributor
    if body.wallet is not None:
        return _wallet_purchase(db, m, body.wallet, network)
    if agent is None:
        raise HTTPException(401, "agent authentication or a wallet proof is required")
    if agent.id == m.contributor_agent_id:
        raise HTTPException(403, "contributors cannot buy their own memory")
    if m.status == MemoryStatus.DISPUTED:
        raise HTTPException(409, "disputed memories cannot be purchased")
    if db.execute(select(Purchase.id).where(Purchase.memory_id == memory_id, Purchase.buyer_account_id == agent.near_account_id, Purchase.network == network)).first():
        raise HTTPException(409, "already purchased")

    price = int(m.price_yocto)
    try:
        tx = txs.execute(
            agent.near_account_id,
            "purchase_memory",
            {"memory_id": memory_id},
            deposit=price,
            ctx=txs.TxContext(
                agent_id=agent.id,
                memory_id=memory_id,
                scenario_run_id=scenario,
                message=f"{agent.name} paid {yocto_to_near(price)} NEAR for memory #{m.seq}",
            ),
        )
    except txs.ChainCallFailed as e:
        raise HTTPException(402, f"payment failed on-chain: {e.tx.error}") from e

    # Never trust the submission alone: read the entitlement back from the contract.
    if not txs.view("has_access", {"memory_id": memory_id, "account_id": agent.near_account_id}):
        raise HTTPException(502, "payment confirmed but contract reports no entitlement")
    p = Purchase(
        id=new_id("pur"),
        memory_id=memory_id,
        buyer_account_id=agent.near_account_id,
        buyer_agent_id=agent.id,
        seller_agent_id=m.contributor_agent_id,
        price_yocto=Decimal(price),
        network=network,
        tx_id=tx.id,
    )
    db.add(p)
    store.record_access(db, m, agent)
    activity.record(
        db,
        "marketplace.purchase",
        f"{agent.name} purchased access to memory #{m.seq}",
        agent_id=agent.id,
        memory_id=memory_id,
        tx_id=tx.id,
        scenario_run_id=scenario,
    )
    activity.record(
        db,
        "marketplace.reward",
        f"{contributor.name} earned {yocto_to_near(price)} NEAR (claimable on-chain)",
        agent_id=contributor.id,
        memory_id=memory_id,
        tx_id=tx.id,
        scenario_run_id=scenario,
    )
    db.commit()
    return {"tx_id": tx.id, "tx_hash": tx.tx_hash, "network": network, "memory": to_full(_load(db, memory_id)).model_dump(mode="json")}


def _wallet_purchase(db: Session, m: Memory, proof: WalletProof, network: str) -> dict[str, Any]:
    existing = db.execute(select(Transaction).where(Transaction.tx_hash == proof.tx_hash, Transaction.network == network)).scalar_one_or_none()
    if existing is not None and existing.signer_id != proof.account_id:
        raise HTTPException(409, "transaction already claimed by another account")
    try:
        check = txs.verify_wallet_purchase(proof.tx_hash, proof.account_id, m.memory_id)
    except Exception as e:  # noqa: BLE001 - RPC failures
        raise HTTPException(502, f"could not verify transaction on-chain: {e}") from e
    if not check.ok:
        raise HTTPException(402, check.reason)
    if existing is None:
        existing = Transaction(
            id=new_id("tx"),
            network=network,
            tx_hash=proof.tx_hash,
            signer_id=proof.account_id,
            receiver_id=get_chain().contract_id,
            method="purchase_memory",
            args={"memory_id": m.memory_id},
            deposit_yocto=Decimal(check.deposit),
            status=TxStatus.confirmed,
            memory_id=m.memory_id,
            initiated_by="wallet",
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(existing)
        db.flush()
        activity.record(
            db,
            "chain.purchase_memory",
            f"Wallet {proof.account_id} paid for memory #{m.seq} (verified on-chain)",
            memory_id=m.memory_id,
            tx_id=existing.id,
            onchain=True,
            network=network,
            data={"tx_hash": proof.tx_hash},
        )
    if not db.execute(select(Purchase.id).where(Purchase.memory_id == m.memory_id, Purchase.buyer_account_id == proof.account_id, Purchase.network == network)).first():
        db.add(
            Purchase(
                id=new_id("pur"),
                memory_id=m.memory_id,
                buyer_account_id=proof.account_id,
                seller_agent_id=m.contributor_agent_id,
                price_yocto=m.price_yocto,
                network=network,
                tx_id=existing.id,
            )
        )
        m.usage_count += 1
        activity.record(
            db,
            "marketplace.reward",
            f"{m.contributor.name} earned {yocto_to_near(m.price_yocto)} NEAR from a wallet purchase (claimable on-chain)",
            agent_id=m.contributor_agent_id,
            memory_id=m.memory_id,
            tx_id=existing.id,
        )
    db.commit()
    return {"tx_id": existing.id, "tx_hash": proof.tx_hash, "network": network, "memory": to_full(_load(db, m.memory_id)).model_dump(mode="json")}


# ----------------------------------------------------------------------------- feedback

class FeedbackRequest(BaseModel):
    helpful: bool
    outcome: dict[str, Any] = Field(default_factory=dict)


@router.post("/{memory_id}/feedback", status_code=201)
def memory_feedback(
    memory_id: str,
    body: FeedbackRequest,
    agent: Agent = Depends(current_agent),
    db: Session = Depends(get_db),
    scenario: str | None = ScenarioHeader,
) -> dict[str, Any]:
    if len(str(body.outcome)) > 4000:
        raise HTTPException(422, "outcome too large")
    m = _load(db, memory_id, lock=True)
    try:
        store.feedback(db, m, agent, body.helpful, body.outcome, scenario_run_id=scenario)
    except store.MemoryError_ as e:
        raise HTTPException(e.status_code, e.detail) from e
    db.commit()
    return {"memory_id": memory_id, "helpful": body.helpful, "confidence_score": m.confidence_score, "status": m.status.value}
