"""Memory creation, versioning, access control and usage feedback."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import activity
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import get_chain
from backend.database.models import AccessType, Agent, Feedback, Memory, MemoryAccess, MemoryVersion, Purchase
from backend.memory import reputation
from backend.memory.capsule import CATEGORY_TTL_HOURS, CapsuleCreate, metadata_hash, near_to_yocto, new_id, snapshot
from backend.memory.embeddings import capsule_text, embed
from backend.memory.verification import VerificationError, check_evidence, rescore

DUPLICATE_SIMILARITY = 0.95


class MemoryError_(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _find_duplicate(db: Session, contributor: Agent, data: CapsuleCreate, vec: list[float]) -> Memory | None:
    same_evidence = db.execute(select(Memory).where(Memory.evidence_hash == data.evidence_hash)).scalar_one_or_none()
    if same_evidence:
        return same_evidence
    dist = Memory.embedding.cosine_distance(vec)
    near = db.execute(
        select(Memory, dist.label("d"))
        .where(Memory.contributor_agent_id == contributor.id, Memory.superseded_by.is_(None))
        .order_by(dist)
        .limit(5)
    ).all()
    for m, d in near:
        c = m.claim or {}
        same_claim = (c.get("target"), c.get("metric"), c.get("operator")) == (data.claim.target, data.claim.metric, data.claim.operator)
        if same_claim and 1 - float(d) >= DUPLICATE_SIMILARITY and m.memory_id != data.supersedes:
            return m
    return None


def create(db: Session, contributor: Agent, data: CapsuleCreate, scenario_run_id: str | None = None) -> Memory:
    # 1. the evidence must be real: hash + sandbox attestation + metric recomputation
    try:
        measured = check_evidence(data.claim, data.evidence.model_dump(), data.evidence_hash)
    except VerificationError as e:
        raise MemoryError_(e.status_code, e.detail) from e
    if abs(measured - data.claim.observed) > 1e-6:
        raise MemoryError_(422, f"claim says {data.claim.metric}={data.claim.observed} but evidence shows {measured:.4f}")

    text = capsule_text(data.title, data.description, data.category.value, data.tags, data.claim.model_dump())
    vec = embed(text)

    # 2. duplicates cost reputation and are rejected
    dup = _find_duplicate(db, contributor, data, vec)
    if dup is not None:
        reputation.apply(db, contributor, "duplicate_publication", memory_id=dup.memory_id, detail="duplicate attempt", scenario_run_id=scenario_run_id)
        db.commit()
        raise MemoryError_(409, f"duplicate of existing memory {dup.memory_id}")

    # 3. versioning
    parent: Memory | None = None
    version = 1
    if data.supersedes:
        parent = db.get(Memory, data.supersedes)
        if parent is None:
            raise MemoryError_(404, "superseded memory not found")
        if parent.contributor_agent_id != contributor.id:
            raise MemoryError_(403, "only the contributor can publish a new version")
        if parent.superseded_by:
            raise MemoryError_(409, f"memory already superseded by {parent.superseded_by}")
        version = parent.version + 1

    price = near_to_yocto(data.price_near) if data.access_type == AccessType.paid else 0
    m = Memory(
        memory_id=new_id("mem"),
        title=data.title,
        description=data.description,
        category=data.category,
        original_observation=data.original_observation,
        execution_context=data.execution_context,
        claim=data.claim.model_dump(),
        success_or_failure=data.success_or_failure,
        evidence=data.evidence.model_dump(),
        evidence_hash=data.evidence_hash,
        contributor_agent_id=contributor.id,
        access_type=data.access_type,
        price_yocto=Decimal(price),
        ttl_hours=CATEGORY_TTL_HOURS[data.category],
        version=version,
        parent_memory_id=parent.memory_id if parent else None,
        tags=data.tags,
        embedding=vec,
        confirm_count=0,
        dispute_count=0,
        useful_count=0,
        not_useful_count=0,
        verification_count=0,
        usage_count=0,
    )
    m.metadata_hash = metadata_hash(m)

    # 4. register on-chain first; only a confirmed registration creates the capsule
    tx = txs.execute(
        contributor.near_account_id,
        "publish_memory",
        {
            "memory_id": m.memory_id,
            "evidence_hash": m.evidence_hash,
            "metadata_hash": m.metadata_hash,
            "content_ref": f"swarm://memories/{m.memory_id}",
            "price": str(price),
        },
        ctx=txs.TxContext(
            agent_id=contributor.id,
            memory_id=m.memory_id,
            scenario_run_id=scenario_run_id,
            message=f"{contributor.name} registered memory {m.memory_id} on-chain",
        ),
    )
    m.onchain_tx_id = tx.id
    rescore(m)
    db.add(m)
    db.flush()
    db.refresh(m)
    if parent:
        parent.superseded_by = m.memory_id
    db.add(MemoryVersion(memory_id=m.memory_id, version=version, snapshot=snapshot(m), reason="supersedes " + parent.memory_id if parent else "created"))
    contributor.memories_contributed += 1
    activity.record(
        db,
        "memory.published",
        f"{contributor.name} published memory #{m.seq}: {m.title}",
        agent_id=contributor.id,
        memory_id=m.memory_id,
        scenario_run_id=scenario_run_id,
        data={"category": m.category.value, "price_near": data.price_near, "version": version},
    )
    return m


# ----------------------------------------------------------------------------- access

def has_access(db: Session, m: Memory, agent: Agent | None) -> bool:
    """Free memory, the contributor, or an on-chain entitlement (checked live)."""
    if m.access_type == AccessType.free:
        return True
    if agent is None:
        return False
    if agent.id == m.contributor_agent_id:
        return True
    chain = get_chain()
    paid = db.execute(
        select(Purchase.id).where(
            Purchase.memory_id == m.memory_id, Purchase.buyer_account_id == agent.near_account_id, Purchase.network == chain.network
        )
    ).first()
    if not paid:
        return False
    # The off-chain row is only a hint; the contract is the source of truth.
    return bool(txs.view("has_access", {"memory_id": m.memory_id, "account_id": agent.near_account_id}))


def record_access(db: Session, m: Memory, agent: Agent) -> None:
    if agent.id == m.contributor_agent_id:
        return
    exists = db.execute(select(MemoryAccess.id).where(MemoryAccess.memory_id == m.memory_id, MemoryAccess.agent_id == agent.id)).first()
    if not exists:
        db.add(MemoryAccess(memory_id=m.memory_id, agent_id=agent.id))
        agent.memories_retrieved += 1
        m.usage_count += 1


def feedback(db: Session, m: Memory, agent: Agent, helpful: bool, outcome: dict, scenario_run_id: str | None = None) -> Feedback:
    if agent.id == m.contributor_agent_id:
        raise MemoryError_(403, "contributors cannot rate their own memory")
    used = db.execute(select(MemoryAccess.id).where(MemoryAccess.memory_id == m.memory_id, MemoryAccess.agent_id == agent.id)).first()
    if not used:
        raise MemoryError_(403, "only agents that retrieved this memory can report outcomes")
    if db.execute(select(Feedback.id).where(Feedback.memory_id == m.memory_id, Feedback.agent_id == agent.id)).first():
        raise MemoryError_(409, "outcome already reported for this memory")
    fb = Feedback(memory_id=m.memory_id, agent_id=agent.id, helpful=helpful, outcome=outcome)
    db.add(fb)
    if helpful:
        m.useful_count += 1
    else:
        m.not_useful_count += 1
    rescore(m)
    activity.record(
        db,
        "memory.feedback",
        f"{agent.name} reported memory #{m.seq} {'helped complete the task' if helpful else 'did NOT help'}",
        agent_id=agent.id,
        memory_id=m.memory_id,
        scenario_run_id=scenario_run_id,
        data={"helpful": helpful, **{k: outcome[k] for k in list(outcome)[:6]}},
    )
    contributor = db.get(Agent, m.contributor_agent_id)
    assert contributor is not None
    reputation.apply(db, contributor, "memory_helpful" if helpful else "memory_unhelpful", memory_id=m.memory_id, scenario_run_id=scenario_run_id)
    return fb
