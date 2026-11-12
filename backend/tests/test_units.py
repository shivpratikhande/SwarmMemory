"""Unit tests: sandbox determinism, embeddings, capsule validation, scoring, NEAR signing."""
from __future__ import annotations

import base64
import hashlib

import base58
import pytest
from nacl.signing import SigningKey, VerifyKey
from pydantic import ValidationError

from backend.blockchain.near_client import FunctionCall, KeyPair, parse_outcome, serialize_transaction
from backend.memory.capsule import CapsuleCreate, Claim, near_to_yocto, sha256_hex, yocto_to_near
from backend.memory.embeddings import local_embed
from backend.memory.verification import compute_confidence
from backend.sandbox.apis import WINDOW, attest_requests, expected_outcome


# ---------------------------------------------------------------- sandbox

@pytest.mark.parametrize("api,fails", [("api-x", 8), ("api-y", 1)])
def test_sandbox_failure_rate_is_exact_per_window(api: str, fails: int) -> None:
    for run in ("r1", "r2", "abc-123"):
        for window in range(3):
            outcomes = [expected_outcome(api, run, window * WINDOW + i)[0] for i in range(WINDOW)]
            assert outcomes.count(False) == fails


def test_sandbox_runs_differ_but_reproduce() -> None:
    a = [expected_outcome("api-x", "run-a", i)[0] for i in range(20)]
    b = [expected_outcome("api-x", "run-b", i)[0] for i in range(20)]
    assert a == [expected_outcome("api-x", "run-a", i)[0] for i in range(20)]
    assert a != b


def test_attestation_detects_tampered_evidence() -> None:
    reqs = [{"index": i, "status": 200 if expected_outcome("api-x", "run1", i)[0] else 503} for i in range(20)]
    assert attest_requests("api-x", "run1", reqs)[0]
    flipped = [dict(r) for r in reqs]
    first_fail = next(r for r in flipped if r["status"] == 503)
    first_fail["status"] = 200
    ok, why = attest_requests("api-x", "run1", flipped)
    assert not ok and "does not match" in why
    assert not attest_requests("api-x", "run1", reqs + [reqs[0]])[0]  # duplicate index


# ---------------------------------------------------------------- embeddings

def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_embeddings_are_normalised_and_semantic() -> None:
    q = local_embed("find a reliable api service for a developer application", 256)
    near = local_embed("API X experiences frequent request failures reliability api discovery", 256)
    far = local_embed("deployment strategy for kubernetes blue green rollout", 256)
    assert abs(_cos(q, q) - 1) < 1e-9
    assert _cos(q, near) > _cos(q, far)
    assert local_embed("same text", 256) == local_embed("same text", 256)


# ---------------------------------------------------------------- capsule validation

def _capsule(**over):
    ev = {"run_id": "run-1", "requests": [{"index": 0, "status": 503}], "summary": {}, "logs": []}
    base = dict(
        title="API X fails",
        description="desc here",
        category="api_discovery",
        original_observation="observed failures",
        execution_context={},
        success_or_failure="failure",
        claim=dict(kind="api_reliability", target="api-x", endpoint="/sandbox/apis/api-x/data", metric="failure_rate", operator=">=", threshold=0.25, observed=0.4, sample_size=20),
        evidence=ev,
        evidence_hash=sha256_hex(ev),
    )
    base.update(over)
    return base


def test_capsule_accepts_consistent_payload() -> None:
    c = CapsuleCreate.model_validate(_capsule())
    assert c.price_near == "0.01"


def test_capsule_rejects_hash_mismatch() -> None:
    with pytest.raises(ValidationError, match="evidence_hash"):
        CapsuleCreate.model_validate(_capsule(evidence_hash="0" * 64))


def test_claim_must_hold_for_its_own_observation() -> None:
    with pytest.raises(ValidationError, match="inconsistent"):
        Claim(target="api-x", endpoint="/x", metric="failure_rate", operator=">=", threshold=0.5, observed=0.4, sample_size=20)


def test_capsule_price_rules() -> None:
    with pytest.raises(ValidationError, match="positive price"):
        CapsuleCreate.model_validate(_capsule(price_near="0"))
    with pytest.raises(ValidationError, match="cap"):
        CapsuleCreate.model_validate(_capsule(price_near="6"))
    assert CapsuleCreate.model_validate(_capsule(access_type="free", price_near="3")).price_near == "0"


def test_near_unit_conversion() -> None:
    assert near_to_yocto("0.01") == 10**22
    assert yocto_to_near(10**22) == "0.01"
    assert yocto_to_near(0) == "0"


# ---------------------------------------------------------------- scoring

def test_confidence_is_evidence_derived() -> None:
    assert compute_confidence(0, 0, 0, 0) == pytest.approx(1 / 3)
    assert compute_confidence(1, 0, 0, 0) > compute_confidence(0, 0, 0, 0)
    assert compute_confidence(1, 0, 1, 0) > compute_confidence(1, 0, 0, 0)
    assert compute_confidence(0, 1, 0, 0) < compute_confidence(0, 0, 0, 0)
    assert compute_confidence(1, 0, 0, 3) < compute_confidence(1, 0, 0, 0)


# ---------------------------------------------------------------- NEAR transaction signing

def test_function_call_borsh_layout() -> None:
    fc = FunctionCall("purchase_memory", {"memory_id": "m"}, gas=30 * 10**12, deposit=10**22)
    b = fc.borsh()
    assert b[0] == 2  # Action::FunctionCall
    name_len = int.from_bytes(b[1:5], "little")
    assert b[5 : 5 + name_len] == b"purchase_memory"
    off = 5 + name_len
    args_len = int.from_bytes(b[off : off + 4], "little")
    assert b[off + 4 : off + 4 + args_len] == b'{"memory_id":"m"}'
    off += 4 + args_len
    assert int.from_bytes(b[off : off + 8], "little") == 30 * 10**12
    assert int.from_bytes(b[off + 8 : off + 24], "little") == 10**22
    assert len(b) == off + 24


def test_transaction_signature_verifies() -> None:
    sk = SigningKey.generate()
    secret = "ed25519:" + base58.b58encode(bytes(sk) + bytes(sk.verify_key)).decode()
    kp = KeyPair.from_secret("alice.testnet", secret)
    assert kp.public_key_bytes == bytes(sk.verify_key)
    tx = serialize_transaction("alice.testnet", kp.public_key_bytes, 7, "swarm.testnet", b"\x01" * 32, [FunctionCall("m", {})])
    assert tx[:4] == (13).to_bytes(4, "little") and tx[4:17] == b"alice.testnet"
    assert tx[17] == 0 and tx[18:50] == kp.public_key_bytes
    assert int.from_bytes(tx[50:58], "little") == 7
    digest = hashlib.sha256(tx).digest()
    VerifyKey(kp.public_key_bytes).verify(digest, kp.sign(digest))


def test_parse_outcome_success_and_failure() -> None:
    ok = parse_outcome({
        "status": {"SuccessValue": base64.b64encode(b"true").decode()},
        "transaction": {"hash": "H", "signer_id": "a", "receiver_id": "c"},
        "transaction_outcome": {"block_hash": "B", "outcome": {"gas_burnt": 5}},
        "receipts_outcome": [{"outcome": {"logs": ["EVENT_JSON:{}"], "gas_burnt": 7}}],
    })
    assert ok.success and ok.return_value is True and ok.gas_burnt == 12 and ok.logs == ["EVENT_JSON:{}"]
    bad = parse_outcome({"status": {"Failure": {"ActionError": {"kind": {"FunctionCallError": {"ExecutionError": "Smart contract panicked: Insufficient payment"}}}}}, "transaction": {}, "transaction_outcome": {}, "receipts_outcome": []})
    assert not bad.success and "Insufficient payment" in bad.error
