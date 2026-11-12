"""Memory Capsule: the unit of collective memory.

A capsule is a structured, evidence-backed experience — never a raw chat message.
It carries a machine-checkable `claim` so that other agents can independently
re-run the experiment instead of trusting the contributor's words.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.database.models import AccessType, Memory, MemoryCategory, MemoryStatus

YOCTO_PER_NEAR = 10**24

# Default revalidation windows per category (hours). API behaviour drifts fastest.
CATEGORY_TTL_HOURS: dict[MemoryCategory, int] = {
    MemoryCategory.api_discovery: 72,
    MemoryCategory.failed_experiment: 72,
    MemoryCategory.tool_usage: 24 * 14,
    MemoryCategory.successful_workflow: 24 * 14,
    MemoryCategory.deployment_strategy: 24 * 30,
    MemoryCategory.research_discovery: 24 * 30,
}

SUPPORTED_CLAIM_KINDS = {"api_reliability"}


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(obj: Any) -> str:
    data = obj if isinstance(obj, (bytes, bytearray)) else canonical_json(obj).encode()
    return hashlib.sha256(data).hexdigest()


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def near_to_yocto(amount: str | float | Decimal) -> int:
    d = Decimal(str(amount))
    if d < 0:
        raise ValueError("negative amount")
    return int(d * YOCTO_PER_NEAR)


def yocto_to_near(amount: int | Decimal) -> str:
    d = Decimal(int(amount)) / Decimal(YOCTO_PER_NEAR)
    return format(d.normalize(), "f")


class Claim(BaseModel):
    """A falsifiable statement that a verifier can reproduce."""

    kind: Literal["api_reliability"] = "api_reliability"
    target: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9\-]+$")
    endpoint: str = Field(min_length=1, max_length=200, pattern=r"^/[A-Za-z0-9/_\-]*$")
    metric: Literal["failure_rate", "success_rate"]
    operator: Literal[">=", "<="]
    threshold: float = Field(ge=0, le=1)
    observed: float = Field(ge=0, le=1)
    sample_size: int = Field(ge=5, le=200)

    def holds_for(self, value: float) -> bool:
        return value >= self.threshold if self.operator == ">=" else value <= self.threshold

    @model_validator(mode="after")
    def _observed_consistent(self) -> Claim:
        if not self.holds_for(self.observed):
            raise ValueError("claim is inconsistent with its own observation")
        return self


class Evidence(BaseModel):
    run_id: str = Field(min_length=1, max_length=64)
    requests: list[dict[str, Any]] = Field(min_length=1, max_length=500)
    summary: dict[str, Any]
    logs: list[str] = Field(default_factory=list, max_length=1000)


class CapsuleCreate(BaseModel):
    title: str = Field(min_length=4, max_length=200)
    description: str = Field(min_length=4, max_length=4000)
    category: MemoryCategory
    original_observation: str = Field(min_length=4, max_length=8000)
    execution_context: dict[str, Any]
    success_or_failure: Literal["success", "failure"]
    claim: Claim
    evidence: Evidence
    evidence_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    access_type: AccessType = AccessType.paid
    price_near: str = Field(default="0.01", pattern=r"^\d+(\.\d{1,24})?$")
    tags: list[str] = Field(default_factory=list, max_length=20)
    supersedes: str | None = Field(default=None, max_length=40)

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return [t.strip().lower()[:32] for t in v if t.strip()]

    @model_validator(mode="after")
    def _check(self) -> CapsuleCreate:
        if sha256_hex(self.evidence.model_dump()) != self.evidence_hash:
            raise ValueError("evidence_hash does not match sha256(canonical_json(evidence))")
        if self.access_type == AccessType.free:
            self.price_near = "0"
        elif near_to_yocto(self.price_near) <= 0:
            raise ValueError("paid memories need a positive price")
        elif near_to_yocto(self.price_near) > near_to_yocto("5"):
            raise ValueError("price above the 5 NEAR MVP cap")
        return self


class CapsulePublic(BaseModel):
    """What anyone can see — enough to judge relevance, not enough to free-ride."""

    memory_id: str
    seq: int
    title: str
    description: str
    category: MemoryCategory
    success_or_failure: str
    contributor_agent_id: str
    contributor_name: str | None = None
    contributor_account: str | None = None
    contributor_reputation: int | None = None
    created_at: datetime
    last_verified_at: datetime | None
    confidence_score: float
    verification_count: int
    confirm_count: int
    dispute_count: int
    usage_count: int
    access_type: AccessType
    price_near: str
    price_yocto: str
    status: MemoryStatus
    evidence_hash: str
    metadata_hash: str
    version: int
    parent_memory_id: str | None
    superseded_by: str | None
    tags: list[str]
    claim: dict[str, Any]
    onchain_tx_id: str | None
    has_access: bool = False
    similarity: float | None = None


class CapsuleFull(CapsulePublic):
    original_observation: str
    execution_context: dict[str, Any]
    evidence: dict[str, Any]


def metadata_hash(m: Memory) -> str:
    """Hash of the public metadata registered on-chain (content reference)."""
    return sha256_hex(
        {
            "memory_id": m.memory_id,
            "title": m.title,
            "category": m.category.value,
            "contributor": m.contributor_agent_id,
            "claim": m.claim,
            "evidence_hash": m.evidence_hash,
            "version": m.version,
        }
    )


def to_public(m: Memory, *, has_access: bool = False, similarity: float | None = None) -> CapsulePublic:
    c = m.claim or {}
    return CapsulePublic(
        memory_id=m.memory_id,
        seq=m.seq,
        title=m.title,
        description=m.description,
        category=m.category,
        success_or_failure=m.success_or_failure,
        contributor_agent_id=m.contributor_agent_id,
        contributor_name=m.contributor.name if m.contributor else None,
        contributor_account=m.contributor.near_account_id if m.contributor else None,
        contributor_reputation=m.contributor.reputation if m.contributor else None,
        created_at=m.created_at,
        last_verified_at=m.last_verified_at,
        confidence_score=round(m.confidence_score, 4),
        verification_count=m.verification_count,
        confirm_count=m.confirm_count,
        dispute_count=m.dispute_count,
        usage_count=m.usage_count,
        access_type=m.access_type,
        price_near=yocto_to_near(m.price_yocto),
        price_yocto=str(int(m.price_yocto)),
        status=m.status,
        evidence_hash=m.evidence_hash,
        metadata_hash=m.metadata_hash,
        version=m.version,
        parent_memory_id=m.parent_memory_id,
        superseded_by=m.superseded_by,
        tags=m.tags or [],
        # The falsifiable claim is public so any agent can independently re-test it;
        # the observation, execution context and raw evidence/logs are what is paid for.
        claim=c,
        onchain_tx_id=m.onchain_tx_id,
        has_access=has_access,
        similarity=similarity,
    )


def to_full(m: Memory, *, similarity: float | None = None) -> CapsuleFull:
    pub = to_public(m, has_access=True, similarity=similarity)
    return CapsuleFull(
        **pub.model_dump(),
        original_observation=m.original_observation,
        execution_context=m.execution_context,
        evidence=m.evidence,
    )


def snapshot(m: Memory) -> dict[str, Any]:
    return json.loads(canonical_json(to_full(m).model_dump()))
