"""Minimal NEAR JSON-RPC client with local transaction signing.

Implements just what SwarmMemory needs:
* view calls (`query` / `call_function`) for contract state reads,
* signing a FunctionCall transaction (Borsh serialisation + ed25519),
* `send_tx` with `wait_until=FINAL`, falling back to polling `tx` on timeout,
* fetching a transaction outcome by hash (used to verify wallet purchases).

Private keys are only ever read from server-side configuration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import base58
import httpx
from nacl.signing import SigningKey

ED25519 = 0
ACTION_FUNCTION_CALL = 2
DEFAULT_GAS = 30 * 10**12


class NearRpcError(Exception):
    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.data = data


class TxTimeout(NearRpcError):
    pass


# --------------------------------------------------------------------------- borsh

def _u8(v: int) -> bytes:
    return struct.pack("<B", v)


def _u32(v: int) -> bytes:
    return struct.pack("<I", v)


def _u64(v: int) -> bytes:
    return struct.pack("<Q", v)


def _u128(v: int) -> bytes:
    return v.to_bytes(16, "little")


def _string(s: str) -> bytes:
    b = s.encode()
    return _u32(len(b)) + b


def _bytes(b: bytes) -> bytes:
    return _u32(len(b)) + b


@dataclass(frozen=True)
class FunctionCall:
    method_name: str
    args: dict[str, Any]
    gas: int = DEFAULT_GAS
    deposit: int = 0

    def args_bytes(self) -> bytes:
        return json.dumps(self.args, separators=(",", ":")).encode()

    def borsh(self) -> bytes:
        return (
            _u8(ACTION_FUNCTION_CALL)
            + _string(self.method_name)
            + _bytes(self.args_bytes())
            + _u64(self.gas)
            + _u128(self.deposit)
        )


def serialize_transaction(
    signer_id: str, public_key: bytes, nonce: int, receiver_id: str, block_hash: bytes, actions: list[FunctionCall]
) -> bytes:
    out = _string(signer_id) + _u8(ED25519) + public_key + _u64(nonce) + _string(receiver_id) + block_hash
    out += _u32(len(actions)) + b"".join(a.borsh() for a in actions)
    return out


# --------------------------------------------------------------------------- keys

@dataclass
class KeyPair:
    account_id: str
    signing_key: SigningKey

    @classmethod
    def from_secret(cls, account_id: str, secret: str) -> KeyPair:
        if not secret.startswith("ed25519:"):
            raise ValueError("only ed25519 keys are supported")
        raw = base58.b58decode(secret.split(":", 1)[1])
        if len(raw) not in (32, 64):
            raise ValueError("unexpected ed25519 secret length")
        return cls(account_id=account_id, signing_key=SigningKey(raw[:32]))

    @property
    def public_key_bytes(self) -> bytes:
        return bytes(self.signing_key.verify_key)

    @property
    def public_key(self) -> str:
        return "ed25519:" + base58.b58encode(self.public_key_bytes).decode()

    def sign(self, msg: bytes) -> bytes:
        return self.signing_key.sign(msg).signature


# --------------------------------------------------------------------------- rpc

@dataclass
class TxOutcome:
    tx_hash: str
    signer_id: str
    receiver_id: str
    success: bool
    return_value: Any
    error: str | None
    block_hash: str | None
    gas_burnt: int
    logs: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _decode_success_value(v: str | None) -> Any:
    if not v:
        return None
    data = base64.b64decode(v)
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return data.hex()


def parse_outcome(result: dict[str, Any]) -> TxOutcome:
    tx = result.get("transaction", {})
    status = result.get("status", {})
    tx_out = result.get("transaction_outcome", {})
    receipts = result.get("receipts_outcome", [])
    logs: list[str] = []
    gas = int(tx_out.get("outcome", {}).get("gas_burnt", 0))
    for r in receipts:
        logs.extend(r.get("outcome", {}).get("logs", []))
        gas += int(r.get("outcome", {}).get("gas_burnt", 0))
    if isinstance(status, dict) and "SuccessValue" in status:
        success, value, error = True, _decode_success_value(status["SuccessValue"]), None
    elif isinstance(status, dict) and "Failure" in status:
        success, value, error = False, None, json.dumps(status["Failure"])[:2000]
    else:
        success, value, error = False, None, f"unexpected status: {status}"
    return TxOutcome(
        tx_hash=tx.get("hash", ""),
        signer_id=tx.get("signer_id", ""),
        receiver_id=tx.get("receiver_id", ""),
        success=success,
        return_value=value,
        error=error,
        block_hash=tx_out.get("block_hash"),
        gas_burnt=gas,
        logs=logs,
        raw=result,
    )


class NearRpc:
    def __init__(self, rpc_url: str, timeout_s: float = 60.0):
        self.rpc_url = rpc_url
        self.timeout_s = timeout_s
        self._http = httpx.Client(timeout=httpx.Timeout(timeout_s + 10))
        self._nonce_lock: dict[str, threading.Lock] = {}
        self._nonces: dict[tuple[str, str], int] = {}
        self._guard = threading.Lock()

    def call(self, method: str, params: Any) -> Any:
        payload = {"jsonrpc": "2.0", "id": "swarm", "method": method, "params": params}
        for attempt in range(4):
            r = self._http.post(self.rpc_url, json=payload)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(0.5 * (2**attempt))
                continue
            r.raise_for_status()
            body = r.json()
            if "error" in body:
                err = body["error"]
                name = (err.get("cause") or {}).get("name") or err.get("name") or ""
                if name == "TIMEOUT_ERROR":
                    raise TxTimeout("rpc timeout", err)
                raise NearRpcError(f"{method}: {err.get('message')} {name} {json.dumps(err.get('data'))[:400]}", err)
            return body["result"]
        raise NearRpcError(f"{method}: RPC unavailable after retries")

    # ---- reads
    def view(self, contract_id: str, method: str, args: dict[str, Any] | None = None) -> Any:
        res = self.call(
            "query",
            {
                "request_type": "call_function",
                "finality": "final",
                "account_id": contract_id,
                "method_name": method,
                "args_base64": base64.b64encode(json.dumps(args or {}).encode()).decode(),
            },
        )
        raw = bytes(res["result"])
        return json.loads(raw) if raw else None

    def view_account(self, account_id: str) -> dict[str, Any]:
        return self.call("query", {"request_type": "view_account", "finality": "final", "account_id": account_id})

    def status(self) -> dict[str, Any]:
        return self.call("status", [])

    # ---- writes
    def _signer_lock(self, account_id: str) -> threading.Lock:
        with self._guard:
            return self._nonce_lock.setdefault(account_id, threading.Lock())

    def sign_and_send(self, key: KeyPair, receiver_id: str, actions: list[FunctionCall]) -> TxOutcome:
        """Sign a transaction, submit it and block until it is FINAL (or raise)."""
        with self._signer_lock(key.account_id):
            ak = self.call(
                "query",
                {
                    "request_type": "view_access_key",
                    "finality": "final",
                    "account_id": key.account_id,
                    "public_key": key.public_key,
                },
            )
            cache_key = (key.account_id, key.public_key)
            nonce = max(int(ak["nonce"]), self._nonces.get(cache_key, 0)) + 1
            self._nonces[cache_key] = nonce
            block_hash = base58.b58decode(ak["block_hash"])
            tx_bytes = serialize_transaction(key.account_id, key.public_key_bytes, nonce, receiver_id, block_hash, actions)
            digest = hashlib.sha256(tx_bytes).digest()
            signed = tx_bytes + _u8(ED25519) + key.sign(digest)
            tx_hash = base58.b58encode(digest).decode()

        try:
            result = self.call(
                "send_tx",
                {"signed_tx_base64": base64.b64encode(signed).decode(), "wait_until": "FINAL"},
            )
        except TxTimeout:
            result = self.wait_for_tx(tx_hash, key.account_id)
        out = parse_outcome(result)
        out.tx_hash = out.tx_hash or tx_hash
        return out

    def wait_for_tx(self, tx_hash: str, sender_id: str, deadline_s: float | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + (deadline_s or self.timeout_s)
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self.call("tx", {"tx_hash": tx_hash, "sender_account_id": sender_id, "wait_until": "FINAL"})
            except NearRpcError as e:  # UNKNOWN_TRANSACTION while propagating, or timeout
                last = e
                time.sleep(1.5)
        raise TxTimeout(f"transaction {tx_hash} not final before deadline: {last}")

    def get_tx(self, tx_hash: str, sender_id: str) -> TxOutcome:
        return parse_outcome(self.wait_for_tx(tx_hash, sender_id, deadline_s=20))
