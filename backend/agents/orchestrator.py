"""Agent orchestration service.

* Bootstraps the three demo agents (DB identity + on-chain `register_agent`).
* Runs agent executions as background asyncio tasks; agents reach SwarmMemory
  only through HTTP (`SwarmClient`), authenticated with their own API key.
* Persists execution status/logs and drives the end-to-end demo scenario.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from backend import activity
from backend.agents.base import AgentContext, BaseAgent, SwarmClient
from backend.agents.developer import DeveloperAgent
from backend.agents.researcher import ResearchAgent
from backend.agents.verifier import VerificationAgent
from backend.api.deps import agent_api_key
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import ROLE_TO_CHAIN, get_chain
from backend.config import get_settings
from backend.database.connection import session_scope
from backend.database.models import Agent, AgentExecution, AgentRole, ScenarioRun, Transaction
from backend.memory.capsule import new_id, yocto_to_near

log = logging.getLogger(__name__)

AGENT_CLASSES: dict[str, type[BaseAgent]] = {
    "researcher": ResearchAgent,
    "verifier": VerificationAgent,
    "developer": DeveloperAgent,
}

DEFAULT_TASKS = {
    "researcher": "Find a reliable API service for a developer application.",
    "verifier": "Independently verify memories awaiting verification.",
    "developer": "Find a reliable API without wasting time on previously failed options.",
}

DEFAULT_AGENTS = [
    ("agent-a-researcher", "Agent A · Researcher", AgentRole.researcher),
    ("agent-b-verifier", "Agent B · Verifier", AgentRole.verifier),
    ("agent-c-developer", "Agent C · Developer", AgentRole.developer),
]


def _default_account(role: AgentRole) -> str:
    s = get_settings()
    if s.is_testnet:
        acct = {
            AgentRole.researcher: s.near_researcher_account_id,
            AgentRole.verifier: s.near_verifier_account_id,
            AgentRole.developer: s.near_developer_account_id,
        }[role]
        if not acct:
            raise RuntimeError(f"NEAR_{role.value.upper()}_ACCOUNT_ID is required in testnet mode")
        return acct
    return f"{role.value}.swarmmemory.sim"


HttpFactory = Callable[[], httpx.AsyncClient]


def _default_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=get_settings().api_base_url, timeout=httpx.Timeout(180))


class Orchestrator:
    def __init__(self) -> None:
        self.http_factory: HttpFactory = _default_http
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------ bootstrap
    def bootstrap(self) -> None:
        with session_scope() as db:
            for agent_id, name, role in DEFAULT_AGENTS:
                acct = _default_account(role)
                a = db.get(Agent, agent_id)
                if a is None:
                    a = Agent(
                        id=agent_id,
                        name=name,
                        role=role,
                        system_prompt=AGENT_CLASSES[role.value].default_prompt,
                        near_account_id=acct,
                        reputation=0,
                        tasks_completed=0,
                        memories_contributed=0,
                        memories_retrieved=0,
                    )
                    db.add(a)
                    db.flush()
                    activity.record(db, "agent.created", f"{name} joined the swarm as {role.value}", agent_id=agent_id)
                elif a.near_account_id != acct:
                    log.warning("agent %s is bound to %s, config says %s; keeping DB identity", agent_id, a.near_account_id, acct)
        for agent_id, _, _ in DEFAULT_AGENTS:
            self.ensure_onchain(agent_id)

    def ensure_onchain(self, agent_id: str) -> Transaction | None:
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            assert a is not None
            if a.onchain_registered:
                return None
            acct, role, name = a.near_account_id, a.role, a.name
        try:
            existing = txs.view("get_agent", {"account_id": acct})
        except Exception as e:  # noqa: BLE001 - chain may be unreachable at boot
            log.warning("cannot read agent %s on-chain: %s", acct, e)
            return None
        tx = None
        if existing is None:
            try:
                tx = txs.execute(
                    acct,
                    "register_agent",
                    {"role": ROLE_TO_CHAIN[role.value]},
                    ctx=txs.TxContext(agent_id=agent_id, message=f"{name} registered its identity on-chain ({acct})"),
                )
            except txs.ChainCallFailed as e:
                log.warning("on-chain registration failed for %s: %s", acct, e)
                return e.tx
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            assert a is not None
            a.onchain_registered = True
        return tx

    # ------------------------------------------------------------------ executions
    def start(self, agent_id: str, task: str | None, options: dict[str, Any] | None = None, scenario_run_id: str | None = None) -> str:
        with session_scope() as db:
            a = db.get(Agent, agent_id)
            if a is None:
                raise KeyError(agent_id)
            exe = AgentExecution(
                id=new_id("exe"),
                agent_id=agent_id,
                task=task or DEFAULT_TASKS[a.role.value],
                task_type=a.role.value,
                status="queued",
                scenario_run_id=scenario_run_id,
                logs=[],
                result=None,
            )
            db.add(exe)
            exe_id = exe.id
        self._tasks[exe_id] = asyncio.create_task(self._run(exe_id, options or {}))
        return exe_id

    async def wait(self, exe_id: str) -> None:
        t = self._tasks.get(exe_id)
        if t:
            await t

    async def _append_log(self, exe_id: str, msg: str) -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")

        def _write() -> None:
            with session_scope() as db:
                e = db.get(AgentExecution, exe_id, with_for_update=True)
                if e is not None:
                    e.logs = [*e.logs, {"ts": ts, "msg": msg}]

        await asyncio.to_thread(_write)

    async def _run(self, exe_id: str, options: dict[str, Any]) -> None:
        def _begin() -> tuple[str, str, str, str, str, str | None]:
            with session_scope() as db:
                e = db.get(AgentExecution, exe_id)
                assert e is not None
                a = db.get(Agent, e.agent_id)
                assert a is not None
                e.status = "running"
                a.status = "running"
                activity.record(db, "agent.task_started", f"{a.name} started: {e.task}", agent_id=a.id, scenario_run_id=e.scenario_run_id)
                return a.id, a.name, a.role.value, a.system_prompt, e.task, e.scenario_run_id

        agent_id, name, role, prompt, task, scenario = await asyncio.to_thread(_begin)
        status, result, error = "succeeded", None, None
        ctx = None
        try:
            async with self.http_factory() as http:
                client = SwarmClient(http, agent_id, agent_api_key(agent_id), scenario)
                ctx = AgentContext(agent_id, name, role, prompt, client, lambda m: self._append_log(exe_id, m), scenario)
                result = await AGENT_CLASSES[role](ctx).run(task, options)
                result["tx_ids"] = ctx.tx_ids
        except Exception as e:  # noqa: BLE001 - surface any failure on the execution record
            log.exception("execution %s failed", exe_id)
            status, error = "failed", f"{type(e).__name__}: {e}"
            await self._append_log(exe_id, f"ERROR {error}")

        def _finish() -> None:
            with session_scope() as db:
                e = db.get(AgentExecution, exe_id)
                a = db.get(Agent, agent_id)
                assert e is not None and a is not None
                e.status, e.result, e.error = status, result, error
                e.finished_at = datetime.now(timezone.utc)
                a.status = "idle" if status == "succeeded" else "error"
                if status == "succeeded":
                    a.tasks_completed += 1
                activity.record(
                    db,
                    "agent.task_completed" if status == "succeeded" else "agent.task_failed",
                    f"{a.name} {'completed' if status == 'succeeded' else 'FAILED'}: {e.task}",
                    agent_id=a.id,
                    scenario_run_id=e.scenario_run_id,
                    data={"execution_id": exe_id},
                )

        await asyncio.to_thread(_finish)

    # ------------------------------------------------------------------ scenario
    def start_scenario(self, options: dict[str, Any]) -> str:
        run_id = new_id("run")
        with session_scope() as db:
            db.add(ScenarioRun(id=run_id, status="running", network=get_chain().network, options=options, steps=[]))
            activity.record(db, "scenario.started", "End-to-end demonstration scenario started", scenario_run_id=run_id)
        self._tasks[run_id] = asyncio.create_task(self._scenario(run_id, options))
        return run_id

    async def _step(self, run_id: str, title: str, agent_id: str, task: str, options: dict[str, Any]) -> dict[str, Any]:
        def _add(step: dict) -> None:
            with session_scope() as db:
                r = db.get(ScenarioRun, run_id, with_for_update=True)
                assert r is not None
                steps = [s for s in r.steps if s["title"] != step["title"]]
                r.steps = [*steps, step]

        started = datetime.now(timezone.utc).isoformat()
        exe_id = self.start(agent_id, task, options, scenario_run_id=run_id)
        await asyncio.to_thread(_add, {"title": title, "agent_id": agent_id, "execution_id": exe_id, "status": "running", "started_at": started})
        await self.wait(exe_id)

        def _read() -> dict[str, Any]:
            with session_scope() as db:
                e = db.get(AgentExecution, exe_id)
                assert e is not None
                return {"status": e.status, "result": e.result, "error": e.error}

        out = await asyncio.to_thread(_read)
        await asyncio.to_thread(
            _add,
            {
                "title": title,
                "agent_id": agent_id,
                "execution_id": exe_id,
                "status": out["status"],
                "started_at": started,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "result": out["result"],
                "error": out["error"],
            },
        )
        if out["status"] != "succeeded":
            raise RuntimeError(f"step '{title}' failed: {out['error']}")
        return out["result"] or {}

    async def _scenario(self, run_id: str, options: dict[str, Any]) -> None:
        summary: dict[str, Any] = {}
        status, error = "succeeded", None
        try:
            r1 = await self._step(
                run_id,
                "1-2 · Agent A tests API X and publishes a Memory Capsule",
                "agent-a-researcher",
                DEFAULT_TASKS["researcher"],
                {"apis": ["api-x"], "price_near": options.get("price_near", get_settings().default_memory_price_near)},
            )
            published = list(r1.get("published_memories", []))
            if options.get("inject_misleading"):
                r1b = await self._step(
                    run_id,
                    "Injected · Agent A publishes a hasty claim about API Y",
                    "agent-a-researcher",
                    "Quick reliability spot-check of API Y.",
                    {"apis": [], "hasty_claim_api": "api-y", "price_near": options.get("price_near", "0.01")},
                )
                published += r1b.get("published_memories", [])
            if not published:
                raise RuntimeError("researcher published nothing")
            for mid in published:
                await self._step(
                    run_id,
                    f"3 · Agent B independently verifies {mid}",
                    "agent-b-verifier",
                    f"Independently reproduce the experiment behind memory {mid}.",
                    {"memory_id": mid},
                )
            r3 = await self._step(
                run_id,
                "4-7 · Agent C searches memory, purchases access and picks an API",
                "agent-c-developer",
                DEFAULT_TASKS["developer"],
                {},
            )
            summary = {
                "published_memories": published,
                "chosen_api": r3.get("chosen_api"),
                "avoided_apis": r3.get("avoided_apis"),
                "requests_saved": r3.get("requests_saved"),
                "requests_made": r3.get("requests_made"),
                "baseline_requests": r3.get("baseline_requests"),
            }
            with session_scope() as db:
                a = db.get(Agent, "agent-a-researcher")
                assert a is not None
                summary["agent_a_claimable_near"] = yocto_to_near(int(txs.view("get_earnings", {"account_id": a.near_account_id})))
        except Exception as e:  # noqa: BLE001
            log.exception("scenario %s failed", run_id)
            status, error = "failed", str(e)

        def _finish() -> None:
            with session_scope() as db:
                r = db.get(ScenarioRun, run_id)
                assert r is not None
                r.status, r.summary, r.error = status, summary, error
                r.finished_at = datetime.now(timezone.utc)
                activity.record(
                    db,
                    "scenario.finished",
                    "Scenario completed: Agent C avoided API X using Agent A's verified memory"
                    if status == "succeeded" and summary.get("chosen_api") == "api-y"
                    else f"Scenario {status}" + (f": {error}" if error else ""),
                    scenario_run_id=run_id,
                    data=summary,
                )

        await asyncio.to_thread(_finish)


orchestrator = Orchestrator()

