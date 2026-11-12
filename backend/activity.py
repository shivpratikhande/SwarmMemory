"""Activity feed helper. Distinguishes on-chain events from off-chain agent activity."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.database.models import ActivityEvent


def record(
    db: Session,
    kind: str,
    message: str,
    *,
    agent_id: str | None = None,
    memory_id: str | None = None,
    tx_id: str | None = None,
    onchain: bool = False,
    network: str | None = None,
    scenario_run_id: str | None = None,
    data: dict[str, Any] | None = None,
) -> ActivityEvent:
    ev = ActivityEvent(
        kind=kind,
        message=message,
        agent_id=agent_id,
        memory_id=memory_id,
        tx_id=tx_id,
        onchain=onchain,
        network=network,
        scenario_run_id=scenario_run_id,
        data=data or {},
    )
    db.add(ev)
    db.flush()
    return ev
