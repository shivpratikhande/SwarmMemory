# SwarmMemory

**A collective memory and knowledge economy for autonomous AI agents, settled on NEAR.**

AI agents learn things the hard way: one agent burns time discovering an API is flaky, and the next agent does it all over again. SwarmMemory lets agents **publish** what they learned as evidence-backed *Memory Capsules*, **independently verify** each other's claims by re-running the experiment, **buy** verified knowledge instead of re-learning it, and **reward** the contributors, with identity, ownership, payments and reputation recorded on NEAR.

> This is a hackathon MVP. It does **not** claim Sybil resistance or trustless verification (see [Limitations](#limitations)).

![SwarmMemory overview](docs/screenshots/overview.png)

**Contents:** [Highlights](#highlights) · [Quick start](#quick-start) · [Screenshots](#screenshots) · [The demo](#the-demo-in-one-paragraph) · [Architecture](#architecture) · [How it works](#how-the-pieces-work) · [Setup](#local-setup) · [Testnet](#near-testnet-deployment) · [API](#api) · [Walkthrough](#demo-walkthrough-about-3-minutes) · [Hackathon](#built-at-near-hackathon) · [Limitations](#limitations)

## Highlights

- **Runs on real NEAR testnet.** The full scenario has been executed against `swarmmem-4e1857-swarm.testnet`. Every transaction is confirmed FINAL and linked to nearblocks.
- **Verification without an LLM.** A verifier re-runs the experiment from the public claim alone. The backend recomputes the verdict from the verifier's own raw evidence and rejects anything that contradicts it.
- **Paid knowledge, checked on-chain.** Content is released only after the contract's `has_access` view confirms the purchase. Wallet purchases are verified by fetching the transaction from RPC.
- **Pull-payment rewards.** Contributors withdraw their earnings. The balance is zeroed and locked before the transfer and restored by a private callback if the transfer fails.
- **Misinformation gets caught.** Turn on *Inject a misleading claim* and watch the swarm dispute it, cut the contributor's reputation and route around it.
- **Tested end to end.** 34 contract unit tests and 31 backend tests, including integration tests where the three agents drive the real API.

| Layer | Stack |
|---|---|
| Smart contract | Rust, near-sdk 5.30 |
| Backend | Python 3.12, FastAPI, SQLAlchemy, Alembic |
| Storage | PostgreSQL + pgvector (semantic search) |
| Chain client | Own JSON-RPC client with Borsh + ed25519 signing |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, shadcn/ui, NEAR Wallet Selector |

## Quick start

Demo mode needs no NEAR accounts. It runs against a local simulator that mirrors the contract's rules.

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env
./scripts/run_backend.sh demo                                         # API on :8000

cd frontend && cp .env.example .env.local && npm install && npm run dev   # UI on http://localhost:3000
```

Open the Overview page and click **Run the live demo**. Requires Python 3.12+, Node 20+ and PostgreSQL 15+ with pgvector (see [Local setup](#local-setup)).

## Screenshots

| | |
|---|---|
| ![Live demo](docs/screenshots/demo.png) | ![Agent swarm](docs/screenshots/agents.png) |
| **Live demo:** the three-agent scenario, step by step | **Agent Swarm:** NEAR identities, reputation, earnings |
| ![Marketplace](docs/screenshots/marketplace.png) | ![Verification](docs/screenshots/verification.png) |
| **Marketplace:** verified knowledge for sale | **Verification Center:** independent re-runs, request by request |
| ![Memory detail](docs/screenshots/memory-detail.png) | ![Dark theme](docs/screenshots/overview-dark.png) |
| **Memory Capsule:** claim, locked evidence, verifications, ledger | **Dark theme** |

---

## The demo in one paragraph

Agent A tests **API X** (20 real HTTP requests to a controlled sandbox), sees 8 failures and publishes a capsule: *"API X fails ≥ 25% of requests"*, registered on-chain with its evidence hash. Agent B never looks at A's evidence. It re-runs 20 requests on a fresh run, measures 40% failures itself, and records **CONFIRMED** on-chain. Agent C gets the task *"find a reliable API without wasting time on failed options"*. It searches collective memory, buys A's verified capsule for 0.01 NEAR, checks the delivered evidence against the on-chain hash, skips API X entirely and smoke-tests **API Y** with 5 requests: **5 requests instead of 40**. The contract credits A's reward, and A withdraws it. With *Inject misleading claim* on, A also publishes a hasty 1-of-5 "API Y is unreliable" claim. B's 20-request re-run measures 5%, the memory is **DISPUTED**, A loses reputation, and C ignores it.

This scenario has been run end-to-end on **real NEAR testnet** against contract `swarmmem-4e1857-swarm.testnet`. Every tx is confirmed FINAL and linked to nearblocks.

---

## Architecture

```mermaid
flowchart LR
  subgraph Agents["Agent swarm (Python, backend/agents)"]
    A["Agent A · Research"]
    B["Agent B · Verification"]
    C["Agent C · Developer"]
  end
  subgraph API["SwarmMemory API (FastAPI)"]
    MEM["Memory engine<br/>capsules · extraction · retrieval"]
    VER["Verification engine<br/>attestation · confidence · status"]
    MKT["Marketplace<br/>entitlement checks"]
    REP["Reputation ledger"]
    TXS["Transaction service<br/>pending → confirmed / failed"]
  end
  SBX["Controlled test env<br/>API X 8/20 fail · API Y 1/20"]
  PG[("PostgreSQL + pgvector<br/>content · evidence · embeddings")]
  subgraph NEAR["NEAR testnet"]
    SC["SwarmMemory contract (Rust)<br/>identity · memory registry · verifications<br/>entitlements · earnings · reputation"]
  end
  UI["Next.js dashboard"] -->|REST| API
  W["NEAR wallet (browser)"] -->|signs purchase_memory| SC
  UI -.wallet tx hash.-> MKT
  A & B & C -->|HTTP + per-agent key| API
  A & B & C -->|real HTTP requests| SBX
  API --> PG
  TXS -->|"signed txs (backend keys), view calls"| SC
  MKT -->|"has_access view, tx status"| SC
```

**On-chain:** agent identities and roles, memory registrations (id, contributor, evidence hash, metadata hash, content ref, price, status), the append-only verification history, purchase entitlements, contributor earnings plus withdrawals, and the reputation history.
**Off-chain:** memory text, raw evidence and logs, embeddings, agent executions.

### Repository layout

```
backend/
  agents/        researcher.py verifier.py developer.py orchestrator.py base.py
  memory/        capsule.py extraction.py retrieval.py verification.py reputation.py store.py embeddings.py
  blockchain/    near_client.py (JSON-RPC + Borsh + ed25519) contract_client.py transaction_service.py simulated.py
  api/           agents.py memories.py marketplace.py verification.py dashboard.py transactions.py deps.py
  database/      models.py connection.py migrations/ (Alembic)
  sandbox/       apis.py (deterministic API X / API Y)
  tests/         unit + simulated-contract + end-to-end integration tests
contract/        Rust NEAR contract (near-sdk 5.30) + 34 unit tests
frontend/        Next.js 16 + Tailwind + shadcn/ui dashboard (8 pages, light and dark themes)
scripts/         setup_testnet.sh  run_backend.sh
docs/            ARCHITECTURE.md (decisions, plan, risks), screenshots/
```

---

## How the pieces work

### Memory Capsules
A capsule is not a chat message. It is a structured experience with a **falsifiable claim**:

```json
{ "kind": "api_reliability", "target": "api-x", "endpoint": "/sandbox/apis/api-x/data",
  "metric": "failure_rate", "operator": ">=", "threshold": 0.25, "observed": 0.40, "sample_size": 20 }
```

plus `original_observation`, `execution_context`, `evidence` (every request: index, status, latency, and logs) and `evidence_hash = sha256(canonical_json(evidence))`. On publish the backend:
1. recomputes the hash,
2. **attests** every request record against the sandbox (outcomes are a pure function of `(api, run_id, index)`, so fabricated evidence is rejected),
3. recomputes the metric and rejects claims their own evidence doesn't support,
4. rejects duplicates (same evidence, or ≥ 0.95 similar with the same claim from the same contributor), which costs 2 reputation points,
5. registers the capsule on-chain (`publish_memory`), and creates it off-chain **only after the tx is confirmed**.

The claim is public, so anyone can re-test it. The observation, execution context and raw evidence are the paid content. Capsules support **versioning** (`supersedes` → `version + 1`, lineage kept) and **expiry**: a VERIFIED capsule becomes EXPIRED after its category TTL (72 h for API discoveries) until it is re-verified.

### Verification (Module C)
`PENDING → VERIFIED | DISPUTED`, `VERIFIED → EXPIRED → (re-verified)`. A verification is a **new, independent run** of the claim's experiment:
- the verifier gets only the public claim. It never reads the contributor's evidence and never asks an LLM;
- the backend rejects reused run ids, samples smaller than the claim, evidence that fails sandbox attestation, and **verdicts that contradict the verifier's own evidence**;
- agents cannot verify their own memories (enforced in the API *and* in the contract);
- history is append-only; the status tally uses each verifier's latest vote; re-verification has a 60 s cooldown.

**Confidence** is derived from outcomes only, never from an LLM:

```
confidence = (1 + 2·confirmations + helpful) / (3 + 2·(confirmations + disputes) + helpful + unhelpful)
```

An unverified capsule starts at 33%. Repeated unhelpful outcomes (≥ 3, and more than twice the helpful ones) dispute a capsule even if a verifier confirmed it.

### Reputation (Module E)

| Event | Who | Points |
|---|---|---|
| Memory independently confirmed (per new verifier) | contributor | **+5** |
| Memory disputed by an independent verifier | contributor | **−8** |
| Evidence-backed verification submitted | verifier | **+1** |
| Memory reported helpful by an agent that used it | contributor | **+3** |
| Memory reported unhelpful | contributor | **−2** |
| Duplicate publication attempt | contributor | **−2** |

Guards: no self-verification, self-purchase or self-rating; one feedback per agent per memory; feedback only from agents that actually retrieved the memory; verification credit only once per verifier per memory. Every event is mirrored on-chain via the owner-only `update_reputation`.

### Marketplace and payments (Module D)
- **Agents** (backend-held keys): the backend signs `purchase_memory` with the buyer agent's key and attached deposit, waits for **FINAL**, then **reads `has_access` from the contract** before returning content.
- **Wallet users** (testnet mode): the browser signs `purchase_memory` through NEAR Wallet Selector (MyNearWallet / Meteor). The backend fetches the tx by hash and checks signer, receiver, method, `memory_id` and success, then checks `has_access` before revealing content. A frontend "success" is never trusted.
- The contract credits the contributor's **claimable earnings** (pull payment). `withdraw_rewards` zeroes the balance and locks the account *before* the transfer. The private callback restores the balance if the transfer fails, and refuses to settle anything that isn't in flight.

### Demo mode vs testnet mode

| | `SWARM_MODE=demo` | `SWARM_MODE=testnet` |
|---|---|---|
| Chain | `SimulatedContract`: a Python mirror of the Rust contract's rules, state in Postgres | Real NEAR testnet RPC |
| Tx hashes | `sim_…`, labelled **SIM** in the UI | Real hashes with nearblocks links |
| Credentials | none needed | 4 testnet accounts |
| Wallet purchases | disabled | enabled |

Every transaction row stores its `network`. The UI only lists the active network and shows a mode badge on every page. The API **refuses to start** on a database that already holds the other network's transactions.

---

## Local setup

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 15+ with **pgvector**, Rust (the toolchain is pinned by `contract/rust-toolchain.toml`), and for testnet: [`cargo-near`](https://github.com/near/cargo-near) and [`near-cli-rs`](https://github.com/near/near-cli-rs).

```bash
# macOS: brew install postgresql@17 pgvector
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp .env.example .env                       # demo mode works with the defaults

./scripts/run_backend.sh demo              # creates DB, runs migrations, starts API on :8000

cd frontend && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
```

Open **Overview → Run the live demo**.

### Tests

```bash
.venv/bin/pytest                           # 31 backend tests (uses database swarmmemory_test)
cd contract && cargo test                  # 34 contract unit tests
cd frontend && npm run lint && npm run build
```

Backend tests cover sandbox determinism and attestation, embeddings, capsule validation, confidence, Borsh/ed25519 signing, contract-rule parity of the simulator, and **integration tests in which the three agents drive the real API**: the full scenario, paid-content gating, forged agent keys, fabricated evidence, duplicates, versioning, verification abuse paths, withdrawals and the network-mixing guard. Contract tests cover registration, publication, verification, payments, permissions and withdrawals (including a failed-transfer callback and a forged callback).

---

## NEAR testnet deployment

```bash
createdb swarmmemory_testnet
PREFIX=myteam ./scripts/setup_testnet.sh
./scripts/run_backend.sh testnet
```

`setup_testnet.sh`:
1. `cargo near build non-reproducible-wasm`
2. creates `PREFIX-swarm`, `PREFIX-researcher`, `PREFIX-verifier` and `PREFIX-developer`.testnet via the faucet (keys in `~/.near-credentials/testnet/`)
3. `near contract deploy PREFIX-swarm.testnet use-file … with-init-call new json-args '{"owner_id":"PREFIX-swarm.testnet"}'`
4. checks the deployment with a `get_stats` view call
5. writes `backend/.env.testnet` (chmod 600, git-ignored)

On startup the backend registers each agent on-chain (`register_agent`, signed by that agent's key) if the contract doesn't know it yet. For the frontend, set `NEXT_PUBLIC_API_URL` to the testnet API. Wallet purchases then appear in the Marketplace.

Manual equivalents:

```bash
near contract call-function as-read-only PREFIX-swarm.testnet get_stats json-args '{}' network-config testnet now
near contract call-function as-transaction PREFIX-swarm.testnet purchase_memory json-args '{"memory_id":"mem_…"}' \
  prepaid-gas '30 Tgas' attached-deposit '0.01 NEAR' sign-as you.testnet network-config testnet sign-with-keychain send
```

### Contract interface

| Method | Kind | Rules |
|---|---|---|
| `new(owner_id)` | init | owner = reputation oracle |
| `register_agent(role)` | change | caller registers once |
| `publish_memory(memory_id, evidence_hash, metadata_hash, content_ref, price)` | change | registered agents; unique id; 64-hex hashes; price ≤ 5 NEAR |
| `record_verification(memory_id, outcome, evidence_hash)` | change | registered, not the contributor; append-only; 60 s re-verify cooldown |
| `purchase_memory(memory_id)` | payable | deposit ≥ price (excess refunded); no self-purchase, duplicate or disputed purchases |
| `withdraw_rewards()` | change → Promise | balance zeroed + lock before transfer; `on_withdraw_complete` (private) restores on failure |
| `update_reputation(agent_id, delta, reason, memory_id?)` | change | owner only; \|delta\| ≤ 100; history kept |
| `mark_expired(memory_id)` | change | owner only |
| `get_agent`, `get_agents`, `get_memory`, `get_memories`, `has_access`, `get_verifications`, `get_earnings`, `get_total_earned`, `get_purchases`, `get_reputation_history`, `get_stats`, `is_withdrawal_pending`, `get_owner` | view | |

Events are emitted as `EVENT_JSON:{"standard":"swarmmemory",…}` logs.

---

## API

| Method | Path | |
|---|---|---|
| POST | `/agents/register` | bind an agent to a NEAR account the backend can sign for, then register it on-chain |
| GET | `/agents`, `/agents/{id}` | identity, stats, executions, memories, reputation, on-chain record |
| POST | `/agents/{id}/execute` | start a background execution (`{task, options}`) |
| POST | `/agents/{id}/withdraw` | the agent withdraws its claimable earnings |
| POST | `/memories` | publish a capsule (agent auth) |
| GET | `/memories`, `/memories/{id}` | list / get (full content only with access) |
| GET | `/memories/{id}/details`, `/memories/{id}/onchain` | lifecycle + verifier evidence; live contract read |
| POST | `/memories/search` | semantic search (pgvector cosine) |
| POST | `/memories/{id}/verify` | submit an independent verification (agent auth) |
| POST | `/memories/{id}/purchase` | agent purchase, or `{wallet:{account_id, tx_hash}}` |
| POST | `/memories/{id}/feedback` | report whether the memory helped (agent auth) |
| GET | `/marketplace`, `/marketplace/purchases` | listings and purchase history |
| GET | `/verification/queue`, `/verification/history`; POST `/verification/run` | Verification Center |
| GET | `/transactions`, `/dashboard/stats`, `/dashboard/activity`, `/dashboard/economy`, `/config` | |
| POST/GET | `/scenario/run`, `/scenario/runs/{id}` | end-to-end demo |
| GET | `/sandbox/apis`, `/sandbox/apis/{api}/data` | controlled test environment |

Agents authenticate with `X-Agent-Id` and `X-Agent-Key`. The key is `HMAC(SERVER_SECRET, agent_id)`, held by the orchestrator, and the backend derives identity from it, never from the request body.

---

## Demo walkthrough (about 3 minutes)

1. **Overview**: point at the mode badge in the top bar (*Demo · simulated chain* or *NEAR testnet*). Scroll to *Live demo*, turn on *Inject a misleading claim* and click **Run scenario** (**Run again** after the first run). Steps turn green live.
2. **Agent Swarm → History**: show the execution logs: A's 20 requests, B's independent re-run, and C's purchase, hash check and 5-request smoke test.
3. **Memory Explorer**: search "which api is unreliable". Open the API X capsule: the public claim, locked evidence, B's verification with its own request grid, and the live on-chain record under *Ledger*.
4. Open the hasty API Y capsule: **DISPUTED**, measured 5% against a claimed 20%, confidence below 33%.
5. **Marketplace**: purchase history with tx links. In testnet mode, connect a wallet and buy a memory yourself.
6. **Economy**: A's claimable reward, then **Withdraw**. Walk through the reputation ranking and rules.
7. **Transactions**: every contract call with status. On testnet, open one in nearblocks.

---

## Security notes

- Every input is validated with Pydantic: lengths, patterns, hash formats, price caps, and claim self-consistency.
- Private keys live only in server env or the keychain. The browser signs its own wallet transactions.
- Paid content is released only after an on-chain `has_access` read. Wallet purchases are verified by fetching the tx from RPC.
- Evidence hashes are recomputed server-side, and sandbox evidence is attested request by request.
- Txs are stored `pending` before submission and marked `confirmed` only on a successful FINAL outcome. Contract panics are stored as `failed` with the decoded reason.
- Duplicate payments are blocked in both the API and the contract. Withdrawals use the checks-effects-interactions pattern with a lock and a restoring callback.

## Built at NEAR Hackathon

- **Built during the hackathon window.** The first commit is 2026-11-12. All code in this repository was written between then and the 2026-11-14 deadline. There is no pre-hackathon baseline.
- **Tracks:** AI Swarms, Agent Economy.
- **Network:** NEAR testnet (contract `swarmmem-4e1857-swarm.testnet`). Demo mode runs the same flow against a local contract simulator with no accounts needed.
- **Libraries:** near-sdk (Rust contract); FastAPI, SQLAlchemy, Alembic, pgvector, PyNaCl (backend); Next.js, React, Tailwind CSS, shadcn/ui, Radix UI, SWR, lucide-react, sonner and NEAR Wallet Selector (frontend). See `backend/requirements.txt`, `contract/Cargo.toml` and `frontend/package.json` for the full lists.
- **AI assistance:** parts of the code and documentation were written with AI coding assistants (Claude Code).
- **License:** [MIT](LICENSE).

## Limitations

- **Not Sybil-resistant.** One operator can run many "independent" agents. Verification is only as independent as the verifier's operator.
- **Not trustless.** The backend attests evidence for the controlled sandbox only. Claims about arbitrary real-world services would need other attestation.
- **Wallet buyer identity.** The account that posts a verified purchase tx hash receives the content in that response. A NEP-413 signed-message session for later re-reads is out of MVP scope.
- **Deterministic agents.** Agents follow evidence-driven policies and carry role and system prompts, but the MVP does not call an LLM. Nothing in the trust path depends on one.
- The contract pays its own storage from its balance.
