"""Agent 1 — Research Agent: runs experiments, extracts reusable experiences, publishes capsules."""
from __future__ import annotations

from typing import Any

from backend.agents.base import ApiError, BaseAgent
from backend.memory.extraction import Experiment, extract, extract_hasty_failure_claim

SYSTEM_PROMPT = (
    "You are the Research Agent of the SwarmMemory network. Execute research tasks by running real, "
    "reproducible experiments against services. Record every request outcome as evidence. Turn results "
    "into falsifiable Memory Capsules (metric, operator, threshold, sample size) and publish them so other "
    "agents never have to repeat the experiment. Never publish a conclusion your evidence does not support."
)

DEFAULT_SAMPLE = 20


class ResearchAgent(BaseAgent):
    role = "researcher"
    default_prompt = SYSTEM_PROMPT

    async def _experiment(self, task: str, api: dict, n: int, label: str) -> Experiment:
        run_id = self.new_run_id(label)
        await self.log(f"Testing {api['display_name']} with {n} requests (run {run_id})")
        records = await self.run_requests(api["endpoint"], n, run_id)
        fails = sum(1 for r in records if r["status"] >= 400)
        await self.log(f"{api['display_name']}: {fails}/{n} failed ({fails / n:.0%})")
        logs = [f"GET {api['endpoint']} #{r['index']} -> {r['status']} in {r['latency_ms']}ms" for r in records]
        return Experiment(task, api["name"], api["display_name"], api["endpoint"], run_id, records, logs, self.ctx.agent_id)

    async def run(self, task: str, options: dict[str, Any]) -> dict[str, Any]:
        await self.log(f"Task received: {task}")
        apis = await self.api.sandbox_apis()
        wanted = options.get("apis")
        targets = [a for a in apis if wanted is None or a["name"] in wanted]
        if targets:
            await self.log(f"Candidate services: {', '.join(a['display_name'] for a in targets)}")
        n = int(options.get("sample_size", DEFAULT_SAMPLE))
        price = str(options.get("price_near", "0.01"))
        findings, published = [], []

        for api in targets:
            exp = await self._experiment(task, api, n, api["name"])
            findings.append(exp.summary())
            capsule = extract(exp, price_near=price)
            if capsule is None:
                await self.log(f"{api['display_name']}: inconclusive result, nothing worth publishing")
                continue
            published.append(await self._publish(capsule))

        hasty = options.get("hasty_claim_api")
        if hasty:  # demo injection: over-generalise from a 5-request spot check
            api = next(a for a in apis if a["name"] == hasty)
            await self.log(f"[demo injection] Spot-checking {api['display_name']} with only 5 requests")
            for attempt in range(40):
                exp = await self._experiment(task, api, 5, f"quick{attempt}")
                if exp.failures:
                    published.append(await self._publish(extract_hasty_failure_claim(exp, price_near=price)))
                    break

        best = max(findings, key=lambda f: f["success_rate"]) if findings else None
        return {
            "findings": findings,
            "published_memories": [p for p in published if p],
            "recommendation": best["api"] if best else None,
            "requests_made": sum(f["requests"] for f in findings),
        }

    async def _publish(self, capsule: dict) -> str | None:
        try:
            mem = await self.api.publish(capsule)
        except ApiError as e:
            await self.log(f"Publish rejected ({e.status}): {e.detail}")
            return None
        await self.log(f"Published memory #{mem['seq']} {mem['memory_id']}: {mem['title']} (status {mem['status']})")
        if mem.get("onchain_tx_id"):
            self.ctx.tx_ids.append(mem["onchain_tx_id"])
        return mem["memory_id"]
