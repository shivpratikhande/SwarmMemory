"""Single entry point for every contract interaction.

* A `pending` transaction row is committed *before* submission, so the explorer
  shows in-flight transactions.
* The row becomes `confirmed` only after the chain reports a FINAL successful
  outcome; otherwise it becomes `failed` with the error.
* Every row carries the active `network` ("simulated" or "testnet").
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from backend import activity
from backend.blockchain.contract_client import ContractPanic, SignerUnavailable, get_chain
from backend.database.connection import session_scope
from backend.database.models import Transaction, TxStatus
from backend.memory.capsule import new_id


class ChainCallFailed(Exception):
    def __init__(self, tx: Transaction):
        super().__init__(tx.error or "transaction failed")
        self.tx = tx


@dataclass
class TxContext:
    agent_id: str | None = None
    memory_id: str | None = None
    initiated_by: str = "agent"
    scenario_run_id: str | None = None
    message: str | None = None


def _short_err(err: str | None) -> str | None:
    if not err:
        return err
    # unwrap NEAR's FunctionCallError(ExecutionError("Smart contract panicked: ...")) for display
    for marker in ("Smart contract panicked: ", "ExecutionError\": \""):
        if marker in err:
            tail = err.split(marker, 1)[1]
            return tail.split('"')[0].rstrip("\\") or err
    return err[:500]


def execute(
    signer: str,
    method: str,
    args: dict[str, Any],
    *,
    deposit: int = 0,
    gas: int | None = None,
    ctx: TxContext | None = None,
) -> Transaction:
    chain = get_chain()
    ctx = ctx or TxContext()
    tx_id = new_id("tx")
    with session_scope() as db:
        db.add(
            Transaction(
                id=tx_id,
                network=chain.network,
                signer_id=signer,
                receiver_id=chain.contract_id,
                method=method,
                args=args,
                deposit_yocto=Decimal(deposit),
                status=TxStatus.pending,
                agent_id=ctx.agent_id,
                memory_id=ctx.memory_id,
                initiated_by=ctx.initiated_by,
            )
        )

    kwargs: dict[str, Any] = {"deposit": deposit}
    if gas:
        kwargs["gas"] = gas
    try:
        if chain.network == "simulated":
            with session_scope() as db:
                res = chain.call(db, signer, method, args, **kwargs)
        else:
            res = chain.call(None, signer, method, args, **kwargs)  # type: ignore[arg-type]
        error = None if res.success else _short_err(res.error)
    except (SignerUnavailable, ContractPanic) as e:
        res, error = None, str(e)
    except Exception as e:  # network errors, timeouts: the tx may or may not land
        res, error = None, f"{type(e).__name__}: {e}"

    with session_scope() as db:
        tx = db.get(Transaction, tx_id)
        assert tx is not None
        if res is not None:
            tx.tx_hash = res.tx_hash
            tx.block_hash = res.block_hash
            tx.gas_burnt = Decimal(res.gas_burnt or 0)
            tx.return_value = res.return_value
        if res is not None and res.success:
            tx.status = TxStatus.confirmed
            tx.confirmed_at = datetime.now(timezone.utc)
        else:
            tx.status = TxStatus.failed
            tx.error = error
        verb = "confirmed" if tx.status == TxStatus.confirmed else "FAILED"
        activity.record(
            db,
            f"chain.{method}",
            ctx.message or f"{method} {verb}",
            agent_id=ctx.agent_id,
            memory_id=ctx.memory_id,
            tx_id=tx_id,
            onchain=True,
            network=chain.network,
            scenario_run_id=ctx.scenario_run_id,
            data={"status": tx.status.value, "tx_hash": tx.tx_hash, "error": tx.error, "signer": signer},
        )
        db.flush()
        db.expunge(tx)
    if tx.status != TxStatus.confirmed:
        raise ChainCallFailed(tx)
    return tx


def view(method: str, args: dict[str, Any] | None = None) -> Any:
    chain = get_chain()
    if chain.network == "simulated":
        with session_scope() as db:
            return chain.view(db, method, args)
    return chain.view(None, method, args)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- wallet purchases

@dataclass
class WalletPurchaseCheck:
    ok: bool
    reason: str
    tx_hash: str
    signer_id: str | None = None
    deposit: int = 0


def verify_wallet_purchase(tx_hash: str, account_id: str, memory_id: str) -> WalletPurchaseCheck:
    """Independently confirm a browser-signed purchase on-chain. Never trusts the client."""
    chain = get_chain()
    if chain.network != "testnet":
        return WalletPurchaseCheck(False, "wallet purchases are only available in testnet mode", tx_hash)
    out = chain.rpc.get_tx(tx_hash, account_id)  # type: ignore[attr-defined]
    raw_tx = out.raw.get("transaction", {})
    if raw_tx.get("signer_id") != account_id:
        return WalletPurchaseCheck(False, "transaction signer does not match account", tx_hash)
    if raw_tx.get("receiver_id") != chain.contract_id:
        return WalletPurchaseCheck(False, "transaction was not sent to the SwarmMemory contract", tx_hash)
    call = None
    for a in raw_tx.get("actions", []):
        fc = a.get("FunctionCall") if isinstance(a, dict) else None
        if fc and fc.get("method_name") == "purchase_memory":
            call = fc
    if call is None:
        return WalletPurchaseCheck(False, "transaction is not a purchase_memory call", tx_hash)
    try:
        args = json.loads(base64.b64decode(call.get("args", "")))
    except ValueError:
        return WalletPurchaseCheck(False, "unreadable call arguments", tx_hash)
    if args.get("memory_id") != memory_id:
        return WalletPurchaseCheck(False, "transaction purchased a different memory", tx_hash)
    if not out.success:
        return WalletPurchaseCheck(False, f"transaction failed on-chain: {_short_err(out.error)}", tx_hash)
    if not view("has_access", {"memory_id": memory_id, "account_id": account_id}):
        return WalletPurchaseCheck(False, "contract does not report an entitlement", tx_hash)
    return WalletPurchaseCheck(True, "verified on-chain", tx_hash, account_id, int(call.get("deposit", "0")))
