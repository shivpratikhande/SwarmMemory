from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://localhost:5432/swarmmemory_test")
os.environ["SWARM_MODE"] = "demo"
os.environ["SERVER_SECRET"] = "test-secret-123"

from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.agents.orchestrator import orchestrator  # noqa: E402
from backend.app import create_app  # noqa: E402
from backend.blockchain.contract_client import set_chain  # noqa: E402
from backend.config import get_settings  # noqa: E402
from backend.database.connection import get_engine, reset_engine  # noqa: E402
from backend.sandbox.apis import counters  # noqa: E402

TABLES = [
    "activity_events", "reputation_events", "feedback", "memory_access", "purchases", "verifications",
    "memory_versions", "memories", "transactions", "agent_executions", "scenario_runs", "sim_contract_state", "agents",
]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    url = get_settings().database_url
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")
    reset_engine(url)


@pytest.fixture(autouse=True)
def _clean() -> None:
    with get_engine().begin() as c:
        c.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    set_chain(None)
    counters._n.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def app():
    application = create_app(bootstrap=False)
    orchestrator.http_factory = lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test", timeout=60)
    orchestrator.bootstrap()
    return application


@pytest.fixture
async def client(app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=60) as c:
        yield c
