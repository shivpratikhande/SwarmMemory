"""Integration tests: the agents drive the real API (ASGI) against the demo chain."""
from __future__ import annotations

import pytest

from backend.agents.orchestrator import orchestrator
from backend.api.deps import agent_api_key
from backend.app import ModeMismatch, assert_single_network
from backend.database.connection import session_scope
from backend.database.models import Transaction, TxStatus
from backend.memory.capsule import sha256_hex
from backend.sandbox.apis import expected_outcome

pytestmark = pytest.mark.anyio

A, B, C = "agent-a-researcher", "agent-b-verifier", "agent-c-developer"


def auth(agent_id: str) -> dict[str, str]:
    return {"X-Agent-Id": agent_id, "X-Agent-Key": agent_api_key(agent_id)}


async def run(agent_id: str, task: str | None = None, **options) -> dict:
    exe = orchestrator.start(agent_id, task, options)
    await orchestrator.wait(exe)
    with session_scope() as db:
        from backend.database.models import AgentExecution

        e = db.get(AgentExecution, exe)
        assert e.status == "succeeded", (e.error, e.logs)
        return e.result


def evidence_for(api: str, run_id: str, n: int, start: int = 0) -> dict:
    reqs = []
    for i in range(start, start + n):
        ok, lat = expected_outcome(api, run_id, i)
        reqs.append({"index": i, "status": 200 if ok else 503, "latency_ms": lat})
    return {"run_id": run_id, "requests": reqs, "summary": {}, "logs": []}


def capsule_payload(ev: dict, observed: float, **over) -> dict:
    p = {
        "title": "API X experiences frequent request failures",
        "description": "API X failed often",
        "category": "api_discovery",
        "original_observation": "observed",
        "execution_context": {"task": "t"},
        "success_or_failure": "failure",
        "claim": {"kind": "api_reliability", "target": "api-x", "endpoint": "/sandbox/apis/api-x/data", "metric": "failure_rate", "operator": ">=", "threshold": 0.25, "observed": observed, "sample_size": len(ev["requests"])},
        "evidence": ev,
        "evidence_hash": sha256_hex(ev),
    }
    p.update(over)
    return p


# ---------------------------------------------------------------- full scenario

async def test_end_to_end_scenario(client) -> None:
    run_id = orchestrator.start_scenario({"inject_misleading": True})
    await orchestrator.wait(run_id)
    r = (await client.get(f"/scenario/runs/{run_id}")).json()
    assert r["status"] == "succeeded", r
    s = r["summary"]
    assert s["chosen_api"] == "api-y"
    assert "api-x" in s["avoided_apis"]
    assert s["requests_made"] < s["baseline_requests"]
    assert s["agent_a_claimable_near"] == "0.01"
    assert len(s["published_memories"]) == 2

    mems = {m["memory_id"]: m for m in (await client.get("/memories")).json()}
    x_mem, hasty = s["published_memories"]
    assert mems[x_mem]["status"] == "VERIFIED"
    assert mems[x_mem]["usage_count"] == 1
    assert mems[hasty]["status"] == "DISPUTED"
    assert mems[x_mem]["confidence_score"] > 1 / 3 > mems[hasty]["confidence_score"]

    details = (await client.get(f"/memories/{x_mem}/details")).json()
    assert details["verifications"][0]["verifier_agent_id"] == B
    assert details["verifications"][0]["verification_result"] == "CONFIRMED"
    assert len(details["purchases"]) == 1

    onchain = (await client.get(f"/memories/{x_mem}/onchain")).json()
    assert onchain["status"] == "Verified" and onchain["purchase_count"] == 1

    agents = {a["id"]: a for a in (await client.get("/agents")).json()}
    # +5 confirm, -8 dispute, +3 helpful
    assert agents[A]["reputation"] == 0 and agents[B]["reputation"] == 2
    assert agents[C]["memories_retrieved"] == 1 and agents[C]["spent_near"] == "0.01"

    stats = (await client.get("/dashboard/stats")).json()
    assert stats["verified"] == 1 and stats["disputed"] == 1 and stats["purchases"] == 1
    assert stats["near_distributed"] == "0.01"
    assert stats["transactions"].get("failed", 0) == 0

    txs = (await client.get("/transactions")).json()
    methods = {t["method"] for t in txs}
    assert {"register_agent", "publish_memory", "record_verification", "purchase_memory", "update_reputation"} <= methods
    assert all(t["network"] == "simulated" and t["simulated"] and t["explorer_url"] is None for t in txs)

    feed = (await client.get(f"/dashboard/activity?scenario_run_id={run_id}&limit=200")).json()
    assert any(e["onchain"] for e in feed) and any(not e["onchain"] for e in feed)

    # withdrawal of the earned reward
    w = await client.post(f"/agents/{A}/withdraw")
    assert w.status_code == 200 and w.json()["amount_near"] == "0.01"
    assert (await client.post(f"/agents/{A}/withdraw")).status_code == 409


# ---------------------------------------------------------------- access control

async def test_paid_content_is_gated_until_onchain_purchase(client) -> None:
    await run(A, apis=["api-x"])
    mid = (await client.get("/memories")).json()[0]["memory_id"]

    anon = (await client.get(f"/memories/{mid}")).json()
    assert "evidence" not in anon and "original_observation" not in anon and anon["claim"]["target"] == "api-x"
    other = (await client.get(f"/memories/{mid}", headers=auth(C))).json()
    assert "evidence" not in other
    own = (await client.get(f"/memories/{mid}", headers=auth(A))).json()
    assert "evidence" in own

    # a forged key cannot impersonate an agent
    assert (await client.get(f"/memories/{mid}", headers={"X-Agent-Id": C, "X-Agent-Key": "sk_forged"})).status_code == 401

    bought = await client.post(f"/memories/{mid}/purchase", json={}, headers=auth(C))
    assert bought.status_code == 200, bought.text
    assert sha256_hex(bought.json()["memory"]["evidence"]) == bought.json()["memory"]["evidence_hash"]
    assert "evidence" in (await client.get(f"/memories/{mid}", headers=auth(C))).json()
    assert (await client.post(f"/memories/{mid}/purchase", json={}, headers=auth(C))).status_code == 409
    assert (await client.post(f"/memories/{mid}/purchase", json={}, headers=auth(A))).status_code == 403
    assert (await client.post(f"/memories/{mid}/purchase", json={})).status_code == 401
    # wallet proofs are only accepted in testnet mode
    w = await client.post(f"/memories/{mid}/purchase", json={"wallet": {"account_id": "bob.testnet", "tx_hash": "4" * 44}})
    assert w.status_code == 402


async def test_feedback_requires_access_and_is_once(client) -> None:
    await run(A, apis=["api-x"])
    mid = (await client.get("/memories")).json()[0]["memory_id"]
    assert (await client.post(f"/memories/{mid}/feedback", json={"helpful": True}, headers=auth(C))).status_code == 403
    assert (await client.post(f"/memories/{mid}/feedback", json={"helpful": True}, headers=auth(A))).status_code == 403
    await client.post(f"/memories/{mid}/purchase", json={}, headers=auth(C))
    assert (await client.post(f"/memories/{mid}/feedback", json={"helpful": True}, headers=auth(C))).status_code == 201
    assert (await client.post(f"/memories/{mid}/feedback", json={"helpful": True}, headers=auth(C))).status_code == 409


# ---------------------------------------------------------------- publication integrity

async def test_fabricated_evidence_is_rejected(client) -> None:
    ev = evidence_for("api-y", "fake-run", 20)
    for r in ev["requests"][:8]:
        r["status"] = 503  # pretend API Y failed a lot — the sandbox never served that
    observed = sum(r["status"] == 503 for r in ev["requests"]) / 20
    claim = {**capsule_payload(ev, observed)["claim"], "target": "api-y", "endpoint": "/sandbox/apis/api-y/data"}
    resp = await client.post("/memories", json=capsule_payload(ev, observed, claim=claim), headers=auth(A))
    assert resp.status_code == 422 and "does not match sandbox record" in resp.text


async def test_claim_must_match_measured_evidence(client) -> None:
    ev = evidence_for("api-x", "honest-run", 20)
    resp = await client.post("/memories", json=capsule_payload(ev, 0.5), headers=auth(A))
    assert resp.status_code == 422 and "evidence shows 0.4" in resp.text


async def test_duplicate_publication_rejected_and_penalised(client) -> None:
    ev = evidence_for("api-x", "dup-run", 20)
    assert (await client.post("/memories", json=capsule_payload(ev, 0.4), headers=auth(A))).status_code == 201
    again = await client.post("/memories", json=capsule_payload(ev, 0.4), headers=auth(A))
    assert again.status_code == 409
    ev2 = evidence_for("api-x", "dup-run-2", 20)
    near_copy = await client.post("/memories", json=capsule_payload(ev2, 0.4), headers=auth(A))
    assert near_copy.status_code == 409
    a = (await client.get(f"/agents/{A}")).json()
    assert a["reputation"] == -4


async def test_new_version_supersedes(client) -> None:
    ev = evidence_for("api-x", "v1-run", 20)
    v1 = (await client.post("/memories", json=capsule_payload(ev, 0.4), headers=auth(A))).json()
    ev2 = evidence_for("api-x", "v2-run", 20)
    v2 = await client.post("/memories", json=capsule_payload(ev2, 0.4, supersedes=v1["memory_id"]), headers=auth(A))
    assert v2.status_code == 201 and v2.json()["version"] == 2
    listed = {m["memory_id"] for m in (await client.get("/memories")).json()}
    assert v1["memory_id"] not in listed and v2.json()["memory_id"] in listed
    assert (await client.post("/memories", json=capsule_payload(evidence_for("api-x", "v3", 20), 0.4, supersedes=v1["memory_id"]), headers=auth(A))).status_code == 409


# ---------------------------------------------------------------- verification integrity

async def test_verification_rules(client) -> None:
    ev = evidence_for("api-x", "orig-run", 20)
    mid = (await client.post("/memories", json=capsule_payload(ev, 0.4), headers=auth(A))).json()["memory_id"]

    def body(e: dict, result: str) -> dict:
        return {"verification_result": result, "verification_evidence": e, "evidence_hash": sha256_hex(e)}

    own = evidence_for("api-x", "self-run", 20)
    assert (await client.post(f"/memories/{mid}/verify", json=body(own, "CONFIRMED"), headers=auth(A))).status_code == 403
    assert (await client.post(f"/memories/{mid}/verify", json=body(ev, "CONFIRMED"), headers=auth(B))).status_code == 422  # reused run
    lying = evidence_for("api-x", "ver-run", 20)
    r = await client.post(f"/memories/{mid}/verify", json=body(lying, "DISPUTED"), headers=auth(B))
    assert r.status_code == 422 and "contradicts" in r.text
    small = evidence_for("api-x", "small-run", 10)
    assert (await client.post(f"/memories/{mid}/verify", json=body(small, "CONFIRMED"), headers=auth(B))).status_code == 422
    ok = await client.post(f"/memories/{mid}/verify", json=body(lying, "CONFIRMED"), headers=auth(B))
    assert ok.status_code == 201 and ok.json()["memory_status"] == "VERIFIED"
    again = evidence_for("api-x", "ver-run-2", 20)
    assert (await client.post(f"/memories/{mid}/verify", json=body(again, "CONFIRMED"), headers=auth(B))).status_code == 429


async def test_developer_without_memory_runs_full_experiment(client) -> None:
    res = await run(C)
    assert res["memories_used"] == [] and res["requests_made"] == res["baseline_requests"]
    assert res["chosen_api"] == "api-y"


async def test_mode_guard_blocks_mixed_networks(client) -> None:
    with session_scope() as db:
        db.add(Transaction(id="tx_x", network="testnet", signer_id="a", receiver_id="c", method="m", args={}, status=TxStatus.confirmed))
    with pytest.raises(ModeMismatch):
        assert_single_network()
