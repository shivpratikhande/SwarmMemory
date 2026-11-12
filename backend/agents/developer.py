"""Agent 3 — Developer Agent: consults collective memory before doing any work.

Decision procedure:
1. Search the memory network for experiences relevant to the task.
2. Ignore DISPUTED memories; treat EXPIRED ones as stale; prefer VERIFIED.
3. Buy access to relevant paid memories, then check the evidence hash locally
   against the hash registered on-chain before trusting the content.
4. Exclude services a verified memory shows to be unreliable; adopt a service a
   verified memory shows to be reliable.
5. Only run (small) experiments for what memory did not answer.
6. Report whether each memory helped.
"""
from __future__ import annotations

from typing import Any

from backend.agents.base import ApiError, BaseAgent
from backend.memory.capsule import sha256_hex

SYSTEM_PROMPT = (
    "You are the Developer Agent of the SwarmMemory network. Before executing a task, search collective "
    "memory. Use verified experiences instead of repeating experiments others already ran; buy access when "
    "the evidence is worth it and check its integrity against the on-chain hash. Only experiment where memory "
    "is silent, and report honestly whether each memory helped."
)

FULL_EXPERIMENT = 20
SMOKE_TEST = 5
MIN_RELEVANCE = 0.12


class DeveloperAgent(BaseAgent):
    role = "developer"
    default_prompt = SYSTEM_PROMPT

    async def run(self, task: str, options: dict[str, Any]) -> dict[str, Any]:
        await self.log(f"Task received: {task}")
        apis = {a["name"]: a for a in await self.api.sandbox_apis()}
        baseline = FULL_EXPERIMENT * len(apis)

        hits = await self.api.search(task + " api reliability", limit=10) if not options.get("skip_memory") else []
        await self.log(f"Collective memory search returned {len(hits)} candidate memories")
        avoid: dict[str, str] = {}
        prefer: dict[str, str] = {}
        used: list[dict] = []
        skipped: list[dict] = []
        requests_made = 0

        for m in hits:
            claim = m.get("claim") or {}
            tag = f"#{m['seq']} '{m['title']}'"
            if (m.get("similarity") or 0) < MIN_RELEVANCE or claim.get("kind") != "api_reliability" or claim.get("target") not in apis:
                continue
            if m["status"] == "DISPUTED":
                await self.log(f"Skipping {tag}: DISPUTED by independent verification")
                skipped.append({"memory_id": m["memory_id"], "reason": "disputed"})
                continue
            if m["status"] != "VERIFIED":
                await self.log(f"Skipping {tag}: status {m['status']} (not independently verified)")
                skipped.append({"memory_id": m["memory_id"], "reason": m["status"].lower()})
                continue
            if claim["target"] in avoid or claim["target"] in prefer:
                continue

            full = await self._acquire(m)
            if full is None:
                continue
            used.append({"memory_id": m["memory_id"], "seq": m["seq"], "target": claim["target"], "price_near": m["price_near"]})
            unreliable = claim["metric"] == "failure_rate" and claim["operator"] == ">="
            if unreliable:
                avoid[claim["target"]] = m["memory_id"]
                await self.log(f"Memory {tag}: {claim['target']} failure rate {claim['observed']:.0%} -> excluding it without re-testing")
            else:
                prefer[claim["target"]] = m["memory_id"]
                await self.log(f"Memory {tag}: {claim['target']} success rate {claim['observed']:.0%} -> preferred")

        candidates = [a for a in apis if a not in avoid]
        chosen, tested = None, {}
        for name in sorted(candidates, key=lambda a: a not in prefer):
            n = SMOKE_TEST if (prefer or avoid) else FULL_EXPERIMENT
            run_id = self.new_run_id(f"check-{name}")
            await self.log(f"{'Smoke-testing' if n == SMOKE_TEST else 'Fully testing'} {apis[name]['display_name']} with {n} requests")
            recs = await self.run_requests(apis[name]["endpoint"], n, run_id)
            requests_made += n
            ok = sum(1 for r in recs if 200 <= r["status"] < 300) / n
            tested[name] = ok
            await self.log(f"{apis[name]['display_name']}: {ok:.0%} success in this check")
            if ok >= 0.8 and (prefer or avoid):
                chosen = name
                break
        if chosen is None and tested:
            chosen = max(tested, key=lambda k: tested[k])

        await self.log(
            f"Chose {apis[chosen]['display_name'] if chosen else 'nothing'}; made {requests_made} requests vs "
            f"{baseline} for a from-scratch evaluation (saved {baseline - requests_made})"
        )
        for u in used:
            helpful = chosen is not None and (u["target"] in avoid and chosen != u["target"] or u["target"] == chosen)
            try:
                await self.api.feedback(u["memory_id"], helpful, {"chosen_api": chosen, "requests_saved": baseline - requests_made})
                await self.log(f"Reported memory #{u['seq']} as {'helpful' if helpful else 'not helpful'}")
            except ApiError as e:
                await self.log(f"Feedback for #{u['seq']} not recorded ({e.status}): {e.detail}")

        return {
            "chosen_api": chosen,
            "avoided_apis": avoid,
            "memories_used": used,
            "memories_skipped": skipped,
            "requests_made": requests_made,
            "baseline_requests": baseline,
            "requests_saved": baseline - requests_made,
            "smoke_test_success": tested,
        }

    async def _acquire(self, m: dict) -> dict | None:
        tag = f"#{m['seq']}"
        if not m.get("has_access"):
            await self.log(f"Purchasing access to memory {tag} for {m['price_near']} NEAR")
            try:
                res = await self.api.purchase(m["memory_id"])
            except ApiError as e:
                await self.log(f"Purchase of {tag} failed ({e.status}): {e.detail}")
                return None
            if res.get("tx_id"):
                self.ctx.tx_ids.append(res["tx_id"])
            await self.log(f"Purchase confirmed on-chain (tx {res.get('tx_hash')})")
            full = res["memory"]
        else:
            full = await self.api.get_memory(m["memory_id"])
        # integrity: local hash of the delivered evidence must match the hash registered on-chain
        chain = await self.api.get_onchain_memory(m["memory_id"])
        local = sha256_hex(full["evidence"])
        if not chain or chain.get("evidence_hash") != local:
            await self.log(f"Evidence for {tag} does NOT match the on-chain hash; discarding it")
            return None
        await self.log(f"Evidence for {tag} matches on-chain hash {local[:12]}…")
        return full
