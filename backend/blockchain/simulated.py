"""DEMO MODE ONLY — a Python mirror of contract/src/lib.rs.

It enforces the same rules (registration, self-verification ban, cooldowns,
price checks, entitlements, pull-payment withdrawals, owner-only reputation) so
the demo behaves like the real contract, but every transaction it produces is
labelled `network="simulated"` and has a `sim_` hash. It is never used in
testnet mode.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.blockchain.contract_client import ChainResult, ContractPanic
from backend.database.models import SimulatedContractState

MAX_PRICE = 5 * 10**24
MAX_REPUTATION_DELTA = 100
REVERIFY_COOLDOWN_NS = 60 * 10**9
STARTING_BALANCE = 10 * 10**24  # simulated wallet balance per account (10 NEAR)
HEX = set("0123456789abcdef")


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ContractPanic(msg)


def _valid_id(s: str) -> bool:
    return 0 < len(s) <= 64 and all(c.islower() or c.isdigit() or c in "_-" for c in s)


def _valid_hash(h: str) -> bool:
    return isinstance(h, str) and len(h) == 64 and set(h) <= HEX


def empty_state(owner: str) -> dict[str, Any]:
    return {
        "owner": owner,
        "agents": {},
        "memories": {},
        "verifications": [],
        "latest": {},
        "entitlements": [],
        "earnings": {},
        "total_earned": {},
        "pending_withdrawals": [],
        "purchases": [],
        "reputation_history": [],
        "total_volume": "0",
        "total_withdrawn": "0",
        "balances": {},
    }


class SimulatedContract:
    def __init__(self, owner: str, contract_id: str):
        self.owner = owner
        self.contract_id = contract_id

    # ---------------------------------------------------------------- plumbing
    def _load(self, db: Session, lock: bool) -> SimulatedContractState:
        q = select(SimulatedContractState).where(SimulatedContractState.id == 1)
        if lock:
            q = q.with_for_update()
        row = db.execute(q).scalar_one_or_none()
        if row is None:
            row = SimulatedContractState(id=1, state=empty_state(self.owner), block_height=1)
            db.add(row)
            db.flush()
        return row

    def view(self, db: Session, method: str, args: dict[str, Any]) -> Any:
        st = self._load(db, lock=False).state
        fn = getattr(self, f"v_{method}", None)
        if fn is None:
            raise ContractPanic(f"MethodNotFound: {method}")
        return fn(st, **args)

    def call(self, db: Session, signer: str, method: str, args: dict[str, Any], deposit: int) -> ChainResult:
        row = self._load(db, lock=True)
        st = copy.deepcopy(row.state)
        st["balances"].setdefault(signer, str(STARTING_BALANCE))
        height = row.block_height + 1
        now = time.time_ns()
        tx_hash = "sim_" + hashlib.sha256(f"{signer}:{method}:{json.dumps(args, sort_keys=True)}:{now}".encode()).hexdigest()[:40]
        block_hash = "simblock_" + hashlib.sha256(str(height).encode()).hexdigest()[:24]
        logs: list[str] = []
        fn = getattr(self, f"m_{method}", None)
        try:
            _require(fn is not None, f"MethodNotFound: {method}")
            bal = int(st["balances"][signer])
            _require(bal >= deposit, "NotEnoughBalance")
            st["balances"][signer] = str(bal - deposit)
            ctx = {"pred": signer, "deposit": deposit, "now": now, "logs": logs}
            value = fn(st, ctx, **args)
        except ContractPanic as e:
            row.block_height = height
            return ChainResult(tx_hash, False, None, f"Smart contract panicked: {e}", block_hash, 0, logs)
        except TypeError as e:  # wrong/missing arguments => deserialization failure on-chain
            row.block_height = height
            return ChainResult(tx_hash, False, None, f"Failed to deserialize input: {e}", block_hash, 0, logs)
        row.state = st
        row.block_height = height
        return ChainResult(tx_hash, True, value, None, block_hash, 2_400_000_000_000, logs)

    @staticmethod
    def _emit(ctx: dict, event: str, data: dict) -> None:
        ctx["logs"].append("EVENT_JSON:" + json.dumps({"standard": "swarmmemory", "version": "1.0.0", "event": event, "data": [data]}))

    def _assert_owner(self, st: dict, ctx: dict) -> None:
        _require(ctx["pred"] == st["owner"], "Only the owner can call this")

    # ---------------------------------------------------------------- change methods
    def m_register_agent(self, st: dict, ctx: dict, role: str) -> dict:
        acct = ctx["pred"]
        _require(role in ("Researcher", "Verifier", "Developer"), "Failed to deserialize input: role")
        _require(acct not in st["agents"], "Agent already registered")
        agent = {"account_id": acct, "role": role, "registered_at": ctx["now"], "reputation": 0, "memories_published": 0, "verifications_submitted": 0}
        st["agents"][acct] = agent
        self._emit(ctx, "agent_registered", {"account_id": acct, "role": role})
        return agent

    def m_publish_memory(self, st: dict, ctx: dict, memory_id: str, evidence_hash: str, metadata_hash: str, content_ref: str, price: str) -> dict:
        acct = ctx["pred"]
        _require(acct in st["agents"], "Only registered agents can publish")
        _require(_valid_id(memory_id), "Invalid memory_id")
        _require(_valid_hash(evidence_hash), "evidence_hash must be 64 lowercase hex chars")
        _require(_valid_hash(metadata_hash), "metadata_hash must be 64 lowercase hex chars")
        _require(len(content_ref) <= 256, "content_ref too long")
        _require(int(price) <= MAX_PRICE, "Price above MVP cap")
        _require(memory_id not in st["memories"], "Memory already registered")
        st["agents"][acct]["memories_published"] += 1
        rec = {
            "memory_id": memory_id, "contributor": acct, "evidence_hash": evidence_hash, "metadata_hash": metadata_hash,
            "content_ref": content_ref, "price": str(int(price)), "created_at": ctx["now"], "status": "Pending",
            "confirmations": 0, "disputes": 0, "purchase_count": 0,
        }
        st["memories"][memory_id] = rec
        self._emit(ctx, "memory_published", {"memory_id": memory_id, "contributor": acct, "price": str(int(price))})
        return rec

    def m_record_verification(self, st: dict, ctx: dict, memory_id: str, outcome: str, evidence_hash: str) -> str:
        v = ctx["pred"]
        _require(v in st["agents"], "Only registered agents can verify")
        _require(_valid_hash(evidence_hash), "evidence_hash must be 64 lowercase hex chars")
        _require(outcome in ("Confirmed", "Disputed"), "Failed to deserialize input: outcome")
        key = f"{memory_id}|{v}"
        prev = st["latest"].get(key)
        if prev:
            _require(ctx["now"] >= prev["at"] + REVERIFY_COOLDOWN_NS, "Verifier must wait before re-verifying this memory")
        m = st["memories"].get(memory_id)
        _require(m is not None, "Unknown memory")
        _require(m["contributor"] != v, "Agents cannot verify their own memory")
        if prev:
            m["confirmations" if prev["outcome"] == "Confirmed" else "disputes"] -= 1
        m["confirmations" if outcome == "Confirmed" else "disputes"] += 1
        m["status"] = "Verified" if m["confirmations"] > m["disputes"] else "Disputed"
        st["verifications"].append({"memory_id": memory_id, "verifier": v, "outcome": outcome, "evidence_hash": evidence_hash, "recorded_at": ctx["now"]})
        st["latest"][key] = {"outcome": outcome, "at": ctx["now"]}
        st["agents"][v]["verifications_submitted"] += 1
        self._emit(ctx, "memory_verified", {"memory_id": memory_id, "verifier": v, "outcome": outcome, "status": m["status"]})
        return m["status"]

    def m_mark_expired(self, st: dict, ctx: dict, memory_id: str) -> None:
        self._assert_owner(st, ctx)
        _require(memory_id in st["memories"], "Unknown memory")
        st["memories"][memory_id]["status"] = "Expired"
        self._emit(ctx, "memory_expired", {"memory_id": memory_id})

    def m_purchase_memory(self, st: dict, ctx: dict, memory_id: str) -> bool:
        buyer, deposit = ctx["pred"], ctx["deposit"]
        m = st["memories"].get(memory_id)
        _require(m is not None, "Unknown memory")
        price = int(m["price"])
        _require(price > 0, "Memory is free; no purchase needed")
        _require(m["contributor"] != buyer, "Contributors cannot buy their own memory")
        _require(m["status"] != "Disputed", "Disputed memories cannot be purchased")
        key = f"{memory_id}|{buyer}"
        _require(key not in st["entitlements"], "Already purchased")
        _require(deposit >= price, "Insufficient payment")
        m["purchase_count"] += 1
        c = m["contributor"]
        st["entitlements"].append(key)
        st["earnings"][c] = str(int(st["earnings"].get(c, "0")) + price)
        st["total_earned"][c] = str(int(st["total_earned"].get(c, "0")) + price)
        st["total_volume"] = str(int(st["total_volume"]) + price)
        st["purchases"].append({"memory_id": memory_id, "buyer": buyer, "contributor": c, "amount": str(price), "purchased_at": ctx["now"]})
        refund = deposit - price
        if refund:
            st["balances"][buyer] = str(int(st["balances"][buyer]) + refund)
        self._emit(ctx, "memory_purchased", {"memory_id": memory_id, "buyer": buyer, "contributor": c, "amount": str(price)})
        return True

    def m_withdraw_rewards(self, st: dict, ctx: dict) -> bool:
        acct = ctx["pred"]
        _require(acct not in st["pending_withdrawals"], "Withdrawal already in progress")
        amount = int(st["earnings"].get(acct, "0"))
        _require(amount > 0, "Nothing to withdraw")
        st["earnings"][acct] = "0"
        # transfer + callback resolve atomically in the simulation (the transfer cannot fail)
        st["balances"][acct] = str(int(st["balances"].get(acct, str(STARTING_BALANCE))) + amount)
        st["total_withdrawn"] = str(int(st["total_withdrawn"]) + amount)
        self._emit(ctx, "rewards_withdrawn", {"account_id": acct, "amount": str(amount)})
        return True

    def m_update_reputation(self, st: dict, ctx: dict, agent_id: str, delta: int, reason: str, memory_id: str | None = None) -> int:
        self._assert_owner(st, ctx)
        _require(delta != 0 and abs(delta) <= MAX_REPUTATION_DELTA, "Invalid delta")
        _require(0 < len(reason) <= 64, "Invalid reason")
        if memory_id is not None:
            _require(memory_id in st["memories"], "Unknown memory")
        a = st["agents"].get(agent_id)
        _require(a is not None, "Unknown agent")
        a["reputation"] += delta
        st["reputation_history"].append({"agent": agent_id, "delta": delta, "new_score": a["reputation"], "reason": reason, "memory_id": memory_id, "recorded_at": ctx["now"]})
        self._emit(ctx, "reputation_updated", {"agent": agent_id, "delta": delta, "new_score": a["reputation"], "reason": reason})
        return a["reputation"]

    # ---------------------------------------------------------------- views
    def v_get_owner(self, st: dict) -> str:
        return st["owner"]

    def v_get_agent(self, st: dict, account_id: str) -> dict | None:
        return st["agents"].get(account_id)

    def v_get_agents(self, st: dict, from_index: int = 0, limit: int = 50) -> list:
        return list(st["agents"].values())[from_index : from_index + min(limit, 100)]

    def v_get_memory(self, st: dict, memory_id: str) -> dict | None:
        return st["memories"].get(memory_id)

    def v_get_memories(self, st: dict, from_index: int = 0, limit: int = 50) -> list:
        return list(st["memories"].values())[from_index : from_index + min(limit, 100)]

    def v_has_access(self, st: dict, memory_id: str, account_id: str) -> bool:
        m = st["memories"].get(memory_id)
        if m is None:
            return False
        if m["contributor"] == account_id or int(m["price"]) == 0:
            return True
        return f"{memory_id}|{account_id}" in st["entitlements"]

    def v_get_verifications(self, st: dict, memory_id: str) -> list:
        return [v for v in st["verifications"] if v["memory_id"] == memory_id]

    def v_get_earnings(self, st: dict, account_id: str) -> str:
        return st["earnings"].get(account_id, "0")

    def v_get_total_earned(self, st: dict, account_id: str) -> str:
        return st["total_earned"].get(account_id, "0")

    def v_is_withdrawal_pending(self, st: dict, account_id: str) -> bool:
        return account_id in st["pending_withdrawals"]

    def v_get_purchases(self, st: dict, from_index: int = 0, limit: int = 50) -> list:
        return st["purchases"][from_index : from_index + min(limit, 100)]

    def v_get_reputation_history(self, st: dict, from_index: int = 0, limit: int = 50) -> list:
        return st["reputation_history"][from_index : from_index + min(limit, 100)]

    def v_get_stats(self, st: dict) -> dict:
        return {
            "agents": len(st["agents"]), "memories": len(st["memories"]), "verifications": len(st["verifications"]),
            "purchases": len(st["purchases"]), "total_volume": st["total_volume"], "total_withdrawn": st["total_withdrawn"],
        }

    def v_get_balance(self, st: dict, account_id: str) -> str:
        """Simulation-only helper: the simulated wallet balance of an account."""
        return st["balances"].get(account_id, str(STARTING_BALANCE))
