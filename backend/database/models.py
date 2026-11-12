"""SQLAlchemy models. Memory content, evidence and embeddings live here (off-chain)."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 256


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class AgentRole(str, enum.Enum):
    researcher = "researcher"
    verifier = "verifier"
    developer = "developer"


class MemoryCategory(str, enum.Enum):
    api_discovery = "api_discovery"
    failed_experiment = "failed_experiment"
    successful_workflow = "successful_workflow"
    deployment_strategy = "deployment_strategy"
    tool_usage = "tool_usage"
    research_discovery = "research_discovery"


class MemoryStatus(str, enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    DISPUTED = "DISPUTED"
    EXPIRED = "EXPIRED"


class VerificationResult(str, enum.Enum):
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"


class AccessType(str, enum.Enum):
    free = "free"
    paid = "paid"


class TxStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[AgentRole] = mapped_column(_enum(AgentRole, "agent_role"))
    system_prompt: Mapped[str] = mapped_column(Text)
    near_account_id: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="idle")
    reputation: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    memories_contributed: Mapped[int] = mapped_column(Integer, default=0)
    memories_retrieved: Mapped[int] = mapped_column(Integer, default=0)
    onchain_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    executions: Mapped[list[AgentExecution]] = relationship(back_populates="agent", order_by="AgentExecution.started_at.desc()")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    task: Mapped[str] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued")  # queued|running|succeeded|failed
    scenario_run_id: Mapped[str | None] = mapped_column(String(40), index=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    logs: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped[Agent] = relationship(back_populates="executions")


class Memory(Base):
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, Identity(), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[MemoryCategory] = mapped_column(_enum(MemoryCategory, "memory_category"))
    original_observation: Mapped[str] = mapped_column(Text)
    execution_context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    claim: Mapped[dict[str, Any]] = mapped_column(JSONB)
    success_or_failure: Mapped[str] = mapped_column(String(16))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_hash: Mapped[str] = mapped_column(String(64))
    contributor_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidence_score: Mapped[float] = mapped_column(Float, default=1 / 3)
    verification_count: Mapped[int] = mapped_column(Integer, default=0)
    confirm_count: Mapped[int] = mapped_column(Integer, default=0)
    dispute_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    useful_count: Mapped[int] = mapped_column(Integer, default=0)
    not_useful_count: Mapped[int] = mapped_column(Integer, default=0)
    access_type: Mapped[AccessType] = mapped_column(_enum(AccessType, "access_type"), default=AccessType.paid)
    price_yocto: Mapped[Decimal] = mapped_column(Numeric(40, 0), default=0)
    status: Mapped[MemoryStatus] = mapped_column(_enum(MemoryStatus, "memory_status"), default=MemoryStatus.PENDING, index=True)
    ttl_hours: Mapped[int] = mapped_column(Integer, default=168)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_memory_id: Mapped[str | None] = mapped_column(ForeignKey("memories.memory_id"))
    superseded_by: Mapped[str | None] = mapped_column(String(40))
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list)
    onchain_tx_id: Mapped[str | None] = mapped_column(String(40))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))

    contributor: Mapped[Agent] = relationship()
    verifications: Mapped[list[Verification]] = relationship(back_populates="memory", order_by="Verification.verified_at")

    __table_args__ = (
        Index(
            "ix_memories_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class MemoryVersion(Base):
    __tablename__ = "memory_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.memory_id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.memory_id"), index=True)
    verifier_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    verification_result: Mapped[VerificationResult] = mapped_column(_enum(VerificationResult, "verification_result"))
    verification_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_hash: Mapped[str] = mapped_column(String(64))
    observed_value: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text, default="")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    onchain_tx_id: Mapped[str | None] = mapped_column(String(40))

    memory: Mapped[Memory] = relationship(back_populates="verifications")
    verifier: Mapped[Agent] = relationship()


class Transaction(Base):
    """Every chain interaction. `network` is 'simulated' or 'testnet' and is never mixed in queries."""

    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    network: Mapped[str] = mapped_column(String(16), index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(80), index=True)
    signer_id: Mapped[str] = mapped_column(String(128))
    receiver_id: Mapped[str] = mapped_column(String(128))
    method: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    deposit_yocto: Mapped[Decimal] = mapped_column(Numeric(40, 0), default=0)
    status: Mapped[TxStatus] = mapped_column(_enum(TxStatus, "tx_status"), default=TxStatus.pending)
    error: Mapped[str | None] = mapped_column(Text)
    return_value: Mapped[Any | None] = mapped_column(JSONB)
    block_hash: Mapped[str | None] = mapped_column(String(80))
    gas_burnt: Mapped[Decimal | None] = mapped_column(Numeric(30, 0))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    memory_id: Mapped[str | None] = mapped_column(String(40), index=True)
    initiated_by: Mapped[str] = mapped_column(String(16), default="agent")  # agent|wallet|system
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Purchase(Base):
    __tablename__ = "purchases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.memory_id"), index=True)
    buyer_account_id: Mapped[str] = mapped_column(String(128), index=True)
    buyer_agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    seller_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    price_yocto: Mapped[Decimal] = mapped_column(Numeric(40, 0))
    network: Mapped[str] = mapped_column(String(16))
    tx_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("memory_id", "buyer_account_id", "network", name="uq_purchase_once"),)


class MemoryAccess(Base):
    """Off-chain record of who retrieved content (free memories, or after entitlement checks)."""

    __tablename__ = "memory_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.memory_id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("memory_id", "agent_id", name="uq_access_once"),)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey("memories.memory_id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    helpful: Mapped[bool] = mapped_column(Boolean)
    outcome: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("memory_id", "agent_id", name="uq_feedback_once"),)


class ReputationEvent(Base):
    __tablename__ = "reputation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text, default="")
    memory_id: Mapped[str | None] = mapped_column(String(40))
    onchain_tx_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(48))
    agent_id: Mapped[str | None] = mapped_column(String(64))
    memory_id: Mapped[str | None] = mapped_column(String(40))
    tx_id: Mapped[str | None] = mapped_column(String(40))
    onchain: Mapped[bool] = mapped_column(Boolean, default=False)
    network: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    scenario_run_id: Mapped[str | None] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SimulatedContractState(Base):
    """DEMO MODE ONLY: persisted state of the simulated SwarmMemory contract."""

    __tablename__ = "sim_contract_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSONB)
    block_height: Mapped[int] = mapped_column(Integer, default=0)


class ScenarioRun(Base):
    """One execution of the end-to-end demonstration scenario."""

    __tablename__ = "scenario_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="running")  # running|succeeded|failed
    network: Mapped[str] = mapped_column(String(16))
    options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    steps: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
