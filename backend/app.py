"""SwarmMemory API — FastAPI application factory."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from backend.agents.orchestrator import orchestrator
from backend.api import agents, dashboard, marketplace, memories, transactions, verification
from backend.blockchain.contract_client import get_chain
from backend.config import get_settings
from backend.database.connection import session_scope
from backend.database.models import Transaction
from backend.sandbox import apis as sandbox

log = logging.getLogger("swarmmemory")


class ModeMismatch(RuntimeError):
    pass


def assert_single_network() -> None:
    """Refuse to run a database that already holds transactions from the other network."""
    network = get_chain().network
    with session_scope() as db:
        other = db.execute(select(Transaction.network).where(Transaction.network != network).limit(1)).scalar_one_or_none()
    if other:
        raise ModeMismatch(
            f"database contains '{other}' transactions but SWARM_MODE runs on '{network}'. "
            "Use a separate DATABASE_URL per mode so simulated and real transactions never mix."
        )


def create_app(bootstrap: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if bootstrap:
            await asyncio.to_thread(assert_single_network)
            await asyncio.to_thread(orchestrator.bootstrap)
        yield

    app = FastAPI(title="SwarmMemory", version="0.1.0", description="Collective memory network for AI agents", lifespan=lifespan)
    s = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for r in (agents.router, memories.router, marketplace.router, verification.router, dashboard.router, transactions.router, sandbox.router):
        app.include_router(r)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": s.swarm_mode}

    return app


app = create_app()
