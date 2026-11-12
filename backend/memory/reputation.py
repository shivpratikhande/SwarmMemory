"""Reputation: a simple, explainable points ledger.

Rules (all events are stored with a reason and mirrored on-chain by the
contract owner via `update_reputation`):

| Event                                              | Who          | Points |
|----------------------------------------------------|--------------|--------|
| Memory independently CONFIRMED (per new verifier)  | contributor  | +5     |
| Memory DISPUTED by an independent verifier         | contributor  | -8     |
| Evidence-backed verification submitted             | verifier     | +1     |
| Memory reported helpful by an agent that used it   | contributor  | +3     |
| Memory reported unhelpful by an agent that used it | contributor  | -2     |
| Duplicate publication attempt                      | contributor  | -2     |

Abuse guards: agents cannot verify, buy, or rate their own memories; one
reputation-bearing verification and one feedback per agent per memory; a
verification is only accepted if the backend can attest its raw evidence.
This is *not* Sybil-resistant — one operator could run many agents.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from backend import activity
from backend.blockchain import transaction_service as txs
from backend.blockchain.contract_client import get_chain
from backend.database.models import Agent, ReputationEvent

log = logging.getLogger(__name__)

POINTS = {
    "memory_confirmed": 5,
    "memory_disputed": -8,
    "verification_submitted": 1,
    "memory_helpful": 3,
    "memory_unhelpful": -2,
    "duplicate_publication": -2,
}


def apply(
    db: Session,
    agent: Agent,
    reason: str,
    *,
    memory_id: str | None = None,
    detail: str = "",
    scenario_run_id: str | None = None,
    mirror_onchain: bool = True,
) -> ReputationEvent:
    delta = POINTS[reason]
    agent.reputation += delta
    ev = ReputationEvent(agent_id=agent.id, delta=delta, reason=reason, detail=detail, memory_id=memory_id)
    db.add(ev)
    db.flush()
    activity.record(
        db,
        "reputation",
        f"{agent.name} {'+' if delta > 0 else ''}{delta} reputation ({reason.replace('_', ' ')})",
        agent_id=agent.id,
        memory_id=memory_id,
        scenario_run_id=scenario_run_id,
        data={"delta": delta, "reason": reason, "new_score": agent.reputation},
    )
    if mirror_onchain and agent.onchain_registered:
        chain = get_chain()
        try:
            tx = txs.execute(
                chain.owner_id,
                "update_reputation",
                {"agent_id": agent.near_account_id, "delta": delta, "reason": reason, "memory_id": memory_id},
                ctx=txs.TxContext(
                    agent_id=agent.id,
                    memory_id=memory_id,
                    initiated_by="system",
                    scenario_run_id=scenario_run_id,
                    message=f"Reputation {delta:+d} for {agent.name} recorded on-chain",
                ),
            )
            ev.onchain_tx_id = tx.id
        except txs.ChainCallFailed as e:
            ev.onchain_tx_id = e.tx.id
            log.warning("reputation mirror failed: %s", e)
    return ev
