"""The demo-mode contract must enforce the same rules as contract/src/lib.rs."""
from __future__ import annotations

import pytest

from backend.blockchain.simulated import SimulatedContract
from backend.database.connection import session_scope

H = "a" * 64
PRICE = 10**22


@pytest.fixture
def c() -> SimulatedContract:
    sim = SimulatedContract(owner="owner.sim", contract_id="swarm.sim")
    with session_scope() as db:
        for acct, role in (("r.sim", "Researcher"), ("v.sim", "Verifier"), ("d.sim", "Developer")):
            assert sim.call(db, acct, "register_agent", {"role": role}, 0).success
        assert sim.call(db, "r.sim", "publish_memory", {"memory_id": "mem_1", "evidence_hash": H, "metadata_hash": H, "content_ref": "", "price": str(PRICE)}, 0).success
    return sim


def call(sim, signer, method, args=None, deposit=0):
    with session_scope() as db:
        return sim.call(db, signer, method, args or {}, deposit)


def view(sim, method, **args):
    with session_scope() as db:
        return sim.view(db, method, args)


def test_duplicate_registration_and_unregistered_publish(c) -> None:
    assert "already registered" in call(c, "r.sim", "register_agent", {"role": "Developer"}).error
    assert "Only registered agents" in call(c, "x.sim", "publish_memory", {"memory_id": "m2", "evidence_hash": H, "metadata_hash": H, "content_ref": "", "price": "1"}).error


def test_self_verification_rejected(c) -> None:
    r = call(c, "r.sim", "record_verification", {"memory_id": "mem_1", "outcome": "Confirmed", "evidence_hash": H})
    assert not r.success and "own memory" in r.error


def test_verification_updates_status(c) -> None:
    assert call(c, "v.sim", "record_verification", {"memory_id": "mem_1", "outcome": "Confirmed", "evidence_hash": H}).return_value == "Verified"
    assert len(view(c, "get_verifications", memory_id="mem_1")) == 1
    assert "wait" in call(c, "v.sim", "record_verification", {"memory_id": "mem_1", "outcome": "Confirmed", "evidence_hash": H}).error


def test_purchase_rules(c) -> None:
    assert "Insufficient payment" in call(c, "d.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE - 1).error
    assert "own memory" in call(c, "r.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE).error
    assert call(c, "d.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE).success
    assert "Already purchased" in call(c, "d.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE).error
    assert view(c, "has_access", memory_id="mem_1", account_id="d.sim") is True
    assert view(c, "get_earnings", account_id="r.sim") == str(PRICE)


def test_failed_call_leaves_state_unchanged(c) -> None:
    before = view(c, "get_balance", account_id="d.sim")
    call(c, "d.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE - 1)
    assert view(c, "get_balance", account_id="d.sim") == before
    assert view(c, "has_access", memory_id="mem_1", account_id="d.sim") is False


def test_withdraw_pull_payment(c) -> None:
    assert "Nothing to withdraw" in call(c, "r.sim", "withdraw_rewards").error
    call(c, "d.sim", "purchase_memory", {"memory_id": "mem_1"}, PRICE)
    bal = int(view(c, "get_balance", account_id="r.sim"))
    assert call(c, "r.sim", "withdraw_rewards").success
    assert view(c, "get_earnings", account_id="r.sim") == "0"
    assert int(view(c, "get_balance", account_id="r.sim")) == bal + PRICE
    assert "Nothing to withdraw" in call(c, "r.sim", "withdraw_rewards").error


def test_reputation_owner_only(c) -> None:
    assert "Only the owner" in call(c, "r.sim", "update_reputation", {"agent_id": "r.sim", "delta": 50, "reason": "x"}).error
    assert call(c, "owner.sim", "update_reputation", {"agent_id": "r.sim", "delta": 5, "reason": "memory_confirmed"}).return_value == 5
    assert "Invalid delta" in call(c, "owner.sim", "update_reputation", {"agent_id": "r.sim", "delta": 500, "reason": "x"}).error
