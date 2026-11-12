"""Agent 2 — Verification Agent: independently re-runs the experiment behind a claim.

It never reads the contributor's evidence and never asks a model whether the
claim "sounds right". It executes a fresh run against the claimed endpoint,
measures the claimed metric itself and submits its own evidence.
"""
from __future__ import annotations

from typing import Any

from backend.agents.base import ApiError, BaseAgent
from backend.memory.capsule import sha256_hex

SYSTEM_PROMPT = (
    "You are the Verification Agent of the SwarmMemory network. Find memories awaiting verification, "
    "independently reproduce the original experiment with a fresh run, measure the claimed metric yourself, "
    "and submit CONFIRMED or DISPUTED with your own evidence. Flag outdated or contradictory memories. "
    "Never verify your own memories and never rely on the contributor's evidence or opinion."
)

MIN_SAMPLE = 20


class VerificationAgent(BaseAgent):
    role = "verifier"
    default_prompt = SYSTEM_PROMPT

    async def run(self, task: str, options: dict[str, Any]) -> dict[str, Any]:
        await self.log(f"Task received: {task}")
        if options.get("memory_id"):
            queue = [await self.api.get_memory(options["memory_id"])]
        else:
            queue = await self.api.list_memories(status=["PENDING", "EXPIRED"], sort="created_at", limit=int(options.get("limit", 5)))
        queue = [m for m in queue if m["contributor_agent_id"] != self.ctx.agent_id]
        await self.log(f"{len(queue)} memor{'y' if len(queue) == 1 else 'ies'} to verify")
        results = []
        for mem in queue:
            results.append(await self.verify_one(mem))
        return {"verified": results, "requests_made": sum(r.get("requests", 0) for r in results)}

    async def verify_one(self, mem: dict) -> dict:
        claim = mem["claim"]
        label = f"#{mem['seq']} {mem['memory_id']}"
        if claim.get("kind") != "api_reliability":
            await self.log(f"{label}: claim kind {claim.get('kind')} cannot be reproduced here; skipping")
            return {"memory_id": mem["memory_id"], "skipped": True}
        n = max(MIN_SAMPLE, int(claim["sample_size"]))
        run_id = self.new_run_id("verify")
        await self.log(
            f"{label}: claim '{claim['metric']} {claim['operator']} {claim['threshold']:.2f}' on {claim['target']}; "
            f"re-running {n} independent requests (run {run_id})"
        )
        records = await self.run_requests(claim["endpoint"], n, run_id)
        failures = sum(1 for r in records if not 200 <= r["status"] < 300)
        value = failures / n if claim["metric"] == "failure_rate" else (n - failures) / n
        holds = value >= claim["threshold"] if claim["operator"] == ">=" else value <= claim["threshold"]
        result = "CONFIRMED" if holds else "DISPUTED"
        await self.log(f"{label}: measured {claim['metric']}={value:.0%} (claimed {claim['observed']:.0%}) -> {result}")

        evidence = {
            "run_id": run_id,
            "requests": records,
            "summary": {"metric": claim["metric"], "measured": value, "claimed": claim["observed"], "requests": n, "failures": failures},
            "logs": [f"GET {claim['endpoint']} #{r['index']} -> {r['status']} in {r['latency_ms']}ms" for r in records],
        }
        body = {
            "verification_result": result,
            "verification_evidence": evidence,
            "evidence_hash": sha256_hex(evidence),
            "notes": f"Independent re-run of {n} requests; measured {value:.3f} vs claimed {claim['observed']:.3f}.",
        }
        try:
            v = await self.api.verify(mem["memory_id"], body)
        except ApiError as e:
            await self.log(f"{label}: verification rejected ({e.status}): {e.detail}")
            return {"memory_id": mem["memory_id"], "error": str(e.detail), "requests": n}
        if v.get("onchain_tx_id"):
            self.ctx.tx_ids.append(v["onchain_tx_id"])
        await self.log(f"{label}: verification recorded; memory status now {v['memory_status']}")
        return {"memory_id": mem["memory_id"], "result": result, "measured": value, "status": v["memory_status"], "requests": n}
