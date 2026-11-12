from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_db
from backend.database.models import Agent


def agent_api_key(agent_id: str) -> str:
    """Per-agent API key derived from the server secret. Held only by the orchestrator."""
    mac = hmac.new(get_settings().server_secret.encode(), f"agent:{agent_id}".encode(), hashlib.sha256).hexdigest()
    return f"sk_{mac[:48]}"


def _resolve(db: Session, agent_id: str | None, key: str | None) -> Agent | None:
    if not agent_id or not key:
        return None
    if not hmac.compare_digest(agent_api_key(agent_id), key):
        raise HTTPException(401, "invalid agent credentials")
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(401, "unknown agent")
    return agent


def current_agent(
    db: Session = Depends(get_db),
    x_agent_id: str | None = Header(default=None, max_length=64),
    x_agent_key: str | None = Header(default=None, max_length=80),
) -> Agent:
    agent = _resolve(db, x_agent_id, x_agent_key)
    if agent is None:
        raise HTTPException(401, "agent authentication required (X-Agent-Id / X-Agent-Key)")
    return agent


def optional_agent(
    db: Session = Depends(get_db),
    x_agent_id: str | None = Header(default=None, max_length=64),
    x_agent_key: str | None = Header(default=None, max_length=80),
) -> Agent | None:
    return _resolve(db, x_agent_id, x_agent_key)
