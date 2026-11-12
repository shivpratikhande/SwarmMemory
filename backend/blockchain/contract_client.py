"""Typed access to the SwarmMemory contract, independent of the backing network.

`get_chain()` returns a `NearChain` (real testnet RPC) in testnet mode and a
`SimChain` in demo mode. Callers never see which one they got except via
`chain.network`, which is stamped onto every stored transaction.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from backend.config import Settings, get_settings

GAS_DEFAULT = 30 * 10**12
GAS_WITHDRAW = 60 * 10**12


class ContractPanic(Exception):
    pass


class SignerUnavailable(Exception):
    pass


@dataclass
class ChainResult:
    tx_hash: str
    success: bool
    return_value: Any
    error: str | None
    block_hash: str | None
    gas_burnt: int
    logs: list[str] = field(default_factory=list)


class Chain(Protocol):
    network: str
    contract_id: str
    owner_id: str

    def call(self, db: Session, signer: str, method: str, args: dict[str, Any], deposit: int = 0, gas: int = GAS_DEFAULT) -> ChainResult: ...
    def view(self, db: Session, method: str, args: dict[str, Any] | None = None) -> Any: ...
    def can_sign(self, account_id: str) -> bool: ...


# ----------------------------------------------------------------------------- demo

class SimChain:
    network = "simulated"

    def __init__(self, settings: Settings):
        from backend.blockchain.simulated import SimulatedContract

        self.contract_id = "swarmmemory.sim"
        self.owner_id = "oracle.swarmmemory.sim"
        self._c = SimulatedContract(owner=self.owner_id, contract_id=self.contract_id)

    def call(self, db: Session, signer: str, method: str, args: dict[str, Any], deposit: int = 0, gas: int = GAS_DEFAULT) -> ChainResult:
        return self._c.call(db, signer, method, args, deposit)

    def view(self, db: Session, method: str, args: dict[str, Any] | None = None) -> Any:
        return self._c.view(db, method, args or {})

    def can_sign(self, account_id: str) -> bool:
        return True


# ----------------------------------------------------------------------------- testnet

class NearChain:
    network = "testnet"

    def __init__(self, settings: Settings):
        from backend.blockchain.near_client import NearRpc

        if not settings.near_contract_id:
            raise RuntimeError("NEAR_CONTRACT_ID is required in testnet mode")
        self.contract_id = settings.near_contract_id
        self.owner_id = settings.near_owner_account_id or settings.near_contract_id
        self.rpc = NearRpc(settings.near_rpc_url, settings.near_tx_timeout_s)
        self._keys = _load_keys(settings)

    def can_sign(self, account_id: str) -> bool:
        return account_id in self._keys

    def call(self, db: Session, signer: str, method: str, args: dict[str, Any], deposit: int = 0, gas: int = GAS_DEFAULT) -> ChainResult:
        from backend.blockchain.near_client import FunctionCall

        key = self._keys.get(signer)
        if key is None:
            raise SignerUnavailable(f"no signing key configured for {signer}")
        out = self.rpc.sign_and_send(key, self.contract_id, [FunctionCall(method, args, gas, deposit)])
        # A Promise-returning method (withdraw) resolves to the callback's value.
        success = out.success and out.return_value is not False
        err = out.error if not out.success else (None if success else "callback reported failure")
        return ChainResult(out.tx_hash, success, out.return_value, err, out.block_hash, out.gas_burnt, out.logs)

    def view(self, db: Session, method: str, args: dict[str, Any] | None = None) -> Any:
        return self.rpc.view(self.contract_id, method, args or {})


def _load_keys(s: Settings) -> dict[str, Any]:
    from backend.blockchain.near_client import KeyPair

    keys: dict[str, KeyPair] = {}
    pairs = [
        (s.near_owner_account_id, s.near_owner_private_key),
        (s.near_researcher_account_id, s.near_researcher_private_key),
        (s.near_verifier_account_id, s.near_verifier_private_key),
        (s.near_developer_account_id, s.near_developer_private_key),
    ]
    for acct, secret in pairs:
        if acct and secret:
            keys[acct] = KeyPair.from_secret(acct, secret)
    if s.near_credentials_dir:
        d = Path(s.near_credentials_dir).expanduser()
        for acct in [a for a, _ in pairs if a and a not in keys]:
            f = d / f"{acct}.json"
            if f.exists():
                data = json.loads(f.read_text())
                keys[acct] = KeyPair.from_secret(acct, data["private_key"])
    return keys


_chain: Chain | None = None


def get_chain() -> Chain:
    global _chain
    if _chain is None:
        s = get_settings()
        _chain = NearChain(s) if s.is_testnet else SimChain(s)
    return _chain


def set_chain(chain: Chain | None) -> None:
    global _chain
    _chain = chain


# ----------------------------------------------------------------------------- helpers

ROLE_TO_CHAIN = {"researcher": "Researcher", "verifier": "Verifier", "developer": "Developer"}
RESULT_TO_CHAIN = {"CONFIRMED": "Confirmed", "DISPUTED": "Disputed"}
