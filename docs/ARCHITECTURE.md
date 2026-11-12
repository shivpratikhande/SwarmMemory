# SwarmMemory — Architecture & Implementation Plan

## 1. Architecture decisions

| Concern | Decision | Why |
|---|---|---|
| Backend | Python 3.12+/3.13, FastAPI, SQLAlchemy 2.0 (sync, psycopg 3), Alembic | Typed, fast to build, sync DB inside threadpool keeps code simple |
| Memory store | PostgreSQL 17 + pgvector (`vector(256)`, cosine HNSW index) | Spec requirement; content/evidence/embeddings stay off-chain |
| Embeddings | Pluggable `Embedder`. Default: deterministic local feature-hashing embedder (unigram+bigram, signed hashing, L2-normalised, 256-d). Optional: any OpenAI-compatible `/embeddings` endpoint via env | Works offline and reproducibly for the demo; no API key needed |
| Agents | Three Python agent classes (`ResearchAgent`, `VerificationAgent`, `DeveloperAgent`) that talk to SwarmMemory **only over HTTP** (`SwarmClient`, httpx) authenticated with a per-agent API key | Satisfies “communicate through the API, not shared variables” |
| Agent auth | `X-Agent-Key = HMAC-SHA256(SERVER_SECRET, agent_id)`; backend derives identity from the key, never from a body field | Prevents spoofing `contributor_agent_id` / self-verification |
| Test environment | Sandbox router `/sandbox/apis/{api-x,api-y}`: deterministic per-run failure schedule — API X fails 8/20, API Y fails 1/20 (seeded permutation per `X-Run-Id`) | Reproducible, real HTTP requests; verifier re-runs with its own run id |
| Verification | Memories carry a structured, machine-checkable `claim` (`metric`, `operator`, `threshold`, `target`, `sample_size`). Verifier re-executes the experiment, computes the metric itself, compares, attaches its own logs + evidence hash | Real independent test, not “LLM judges LLM” |
| Confidence | `(1 + 2·confirm + useful) / (3 + 2·(confirm+dispute) + useful + not_useful)`; never from an LLM | Evidence/outcome-derived, explainable |
| Status | PENDING → VERIFIED / DISPUTED by verification tally; VERIFIED → EXPIRED after category TTL; a new verification revalidates | Spec statuses |
| Reputation | Integer points ledger (`reputation_events`), simple published rules (see README) + mirrored on-chain via owner-only `update_reputation` | Explainable, history preserved |
| Chain | Rust contract, `near-sdk 5.30`, NEAR testnet | Spec |
| Chain client | Own minimal Python NEAR client: JSON-RPC + Borsh transaction serialisation + ed25519 signing (PyNaCl) + `send_tx(wait_until=FINAL)` | Avoids unmaintained py libs; full control over confirmation semantics |
| Modes | `SWARM_MODE=demo` → `SimulatedLedger` (same contract semantics, stored in Postgres, tx ids `sim_…`, network=`simulated`). `SWARM_MODE=testnet` → real RPC. Every tx row stores its `network`; UI only lists rows for the active network and shows a mode badge | Never mix simulated and real txs |
| Paid access | Backend gates `original_observation`/`evidence`/`execution_context`. Agents: backend signs `purchase_memory` with the agent's key, waits for FINAL, then reads `has_access` view before returning content. Wallet users: browser signs via NEAR Wallet Selector, backend verifies the tx outcome **and** `has_access` on-chain before revealing | Never trust frontend payment confirmation |
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, SWR polling (2–3 s) for live status | Spec |

## 2. Folder structure

```
SwarmMemory/
  backend/
    app.py               FastAPI app factory, routers, sandbox
    config.py            env settings
    agents/              researcher, verifier, developer, orchestrator, base, client
    memory/              capsule, extraction, retrieval, verification, reputation, embeddings, confidence
    blockchain/          near_client (RPC+borsh+sign), transaction_service, contract_client, simulated ledger
    api/                 agents, memories, marketplace, verification, dashboard, transactions, sandbox, deps
    database/            models, connection, migrations/ (alembic)
    sandbox/             deterministic API X / API Y
    tests/
  contract/              Rust NEAR contract + unit tests
  frontend/              Next.js dashboard
  scripts/               testnet account setup, deploy, demo runner
  docs/
```

## 3. Phases (each phase = commit(s) + push)

1. Foundation — repo skeleton, DB models + migration, FastAPI app, agent classes, Next.js shell.
2. Collective memory — capsule schema, extraction, embeddings, pgvector search, versioning, expiry.
3. Verification — sandbox APIs, verifier re-execution, history, confidence/status, reputation.
4. NEAR — contract + unit tests, Python RPC client, simulated ledger, transaction service, deploy scripts.
5. Marketplace — listing, paid access gating, on-chain entitlement check, rewards, withdrawals.
6. Frontend — 8 pages (Overview, Swarm, Explorer, Marketplace, Verification, Economy, Transactions, Activity).
7. Integration — scenario runner, end-to-end test, docs.

## 4. Technical risks

- **Testnet accounts / funding**: real mode needs 4 funded testnet accounts (contract owner + 3 agents). Script uses the NEAR CLI faucet sponsor; faucet rate limits may apply.
- **RPC availability**: public `rpc.testnet.near.org` is rate-limited; RPC URL is configurable (FastNEAR default).
- **Finality latency**: each FINAL tx ≈ 2–4 s; the scenario runs as a background job with live status.
- **Wallet-user identity**: a wallet buyer proves purchase by tx hash + on-chain `has_access`; content is revealed for that verified purchase. A full NEP-413 signed-message session is out of MVP scope (documented).
- **Not claimed**: Sybil resistance, trustless verification. Verification is only as independent as the verifier operator.
- **Storage staking**: contract pays its own storage from its balance; the deploy script funds it.
