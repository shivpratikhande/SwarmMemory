"""Agent base class and the HTTP client agents use to talk to SwarmMemory.

Agents have no database handle and share no in-process state: everything they
learn from or contribute to the swarm goes through the public API.
"""
from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

LogFn = Callable[[str], Awaitable[None]]


class ApiError(Exception):
    def __init__(self, status: int, detail: Any):
        super().__init__(f"{status}: {detail}")
        self.status = status
        self.detail = detail


class SwarmClient:
    def __init__(self, http: httpx.AsyncClient, agent_id: str, api_key: str, scenario_run_id: str | None = None):
        self.http = http
        self.agent_id = agent_id
        self.headers = {"X-Agent-Id": agent_id, "X-Agent-Key": api_key}
        if scenario_run_id:
            self.headers["X-Scenario-Run"] = scenario_run_id

    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = await self.http.request(method, path, headers={**self.headers, **kw.pop("headers", {})}, **kw)
        if r.status_code >= 400:
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text
            raise ApiError(r.status_code, detail)
        return r.json()

    # --- memory network
    async def search(self, query: str, **kw: Any) -> list[dict]:
        return await self._req("POST", "/memories/search", json={"query": query, **kw})

    async def list_memories(self, **params: Any) -> list[dict]:
        return await self._req("GET", "/memories", params=params)

    async def get_memory(self, memory_id: str) -> dict:
        return await self._req("GET", f"/memories/{memory_id}")

    async def get_onchain_memory(self, memory_id: str) -> dict:
        return await self._req("GET", f"/memories/{memory_id}/onchain")

    async def publish(self, capsule: dict) -> dict:
        return await self._req("POST", "/memories", json=capsule)

    async def verify(self, memory_id: str, body: dict) -> dict:
        return await self._req("POST", f"/memories/{memory_id}/verify", json=body)

    async def purchase(self, memory_id: str) -> dict:
        return await self._req("POST", f"/memories/{memory_id}/purchase", json={})

    async def feedback(self, memory_id: str, helpful: bool, outcome: dict) -> dict:
        return await self._req("POST", f"/memories/{memory_id}/feedback", json={"helpful": helpful, "outcome": outcome})

    # --- controlled test environment
    async def sandbox_apis(self) -> list[dict]:
        return await self._req("GET", "/sandbox/apis")

    async def call_sandbox(self, endpoint: str, run_id: str) -> dict:
        r = await self.http.get(endpoint, headers={"X-Run-Id": run_id})
        return {
            "index": int(r.headers.get("X-Request-Index", -1)),
            "status": r.status_code,
            "latency_ms": int(r.headers.get("X-Simulated-Latency-Ms", 0)),
        }


@dataclass
class AgentContext:
    agent_id: str
    name: str
    role: str
    system_prompt: str
    client: SwarmClient
    log: LogFn
    scenario_run_id: str | None = None
    tx_ids: list[str] = field(default_factory=list)


class BaseAgent:
    role: str = ""
    default_prompt: str = ""

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.api = ctx.client

    async def log(self, msg: str) -> None:
        await self.ctx.log(msg)

    def new_run_id(self, label: str) -> str:
        return f"{self.ctx.agent_id}-{label}-{secrets.token_hex(4)}"

    async def run_requests(self, endpoint: str, n: int, run_id: str) -> list[dict]:
        records = []
        for _ in range(n):
            records.append(await self.api.call_sandbox(endpoint, run_id))
        return records

    async def run(self, task: str, options: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover - abstract
        raise NotImplementedError
