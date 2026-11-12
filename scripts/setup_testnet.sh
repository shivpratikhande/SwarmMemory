#!/usr/bin/env bash
# Create SwarmMemory testnet accounts, deploy + initialise the contract, and
# write backend/.env.testnet. Requires near-cli-rs (`near`) and cargo-near.
#
#   PREFIX=myteam ./scripts/setup_testnet.sh
#
# Accounts (all funded by the NEAR testnet faucet):
#   $PREFIX-swarm.testnet       contract + owner (reputation oracle)
#   $PREFIX-researcher.testnet  Agent A
#   $PREFIX-verifier.testnet    Agent B
#   $PREFIX-developer.testnet   Agent C
# Keys are saved by the CLI to ~/.near-credentials/testnet/<account>.json and are
# only read by the backend. Nothing is ever sent to the frontend.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${PREFIX:-swarmmem-$(date +%s | tail -c 6)}"
CONTRACT="$PREFIX-swarm.testnet"
CREDS="$HOME/.near-credentials/testnet"
NET="network-config testnet"

create() {
  local acct="$1"
  if [ -f "$CREDS/$acct.json" ]; then
    echo "• $acct already exists locally, skipping"
    return
  fi
  echo "• creating $acct via faucet"
  near account create-account sponsor-by-faucet-service "$acct" \
    autogenerate-new-keypair save-to-legacy-keychain $NET create
  sleep 2
}

echo "== Building contract"
(cd "$ROOT/contract" && cargo near build non-reproducible-wasm)
WASM="$ROOT/contract/target/near/swarm_memory.wasm"

echo "== Creating accounts (prefix: $PREFIX)"
for a in "$CONTRACT" "$PREFIX-researcher.testnet" "$PREFIX-verifier.testnet" "$PREFIX-developer.testnet"; do
  create "$a"
done

echo "== Deploying + initialising $CONTRACT"
near contract deploy "$CONTRACT" use-file "$WASM" \
  with-init-call new json-args "{\"owner_id\":\"$CONTRACT\"}" \
  prepaid-gas '100.0 Tgas' attached-deposit '0 NEAR' \
  $NET sign-with-legacy-keychain send

echo "== Verifying deployment (view call)"
near contract call-function as-read-only "$CONTRACT" get_stats json-args '{}' $NET now

key() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['private_key'])" "$CREDS/$1.json"; }

ENV="$ROOT/backend/.env.testnet"
cat > "$ENV" <<EOF
SWARM_MODE=testnet
DATABASE_URL=postgresql+psycopg://localhost:5432/swarmmemory_testnet
SERVER_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(24))')
NEAR_RPC_URL=https://rpc.testnet.fastnear.com
NEAR_EXPLORER_URL=https://testnet.nearblocks.io
NEAR_CONTRACT_ID=$CONTRACT
NEAR_OWNER_ACCOUNT_ID=$CONTRACT
NEAR_OWNER_PRIVATE_KEY=$(key "$CONTRACT")
NEAR_RESEARCHER_ACCOUNT_ID=$PREFIX-researcher.testnet
NEAR_RESEARCHER_PRIVATE_KEY=$(key "$PREFIX-researcher.testnet")
NEAR_VERIFIER_ACCOUNT_ID=$PREFIX-verifier.testnet
NEAR_VERIFIER_PRIVATE_KEY=$(key "$PREFIX-verifier.testnet")
NEAR_DEVELOPER_ACCOUNT_ID=$PREFIX-developer.testnet
NEAR_DEVELOPER_PRIVATE_KEY=$(key "$PREFIX-developer.testnet")
EOF
chmod 600 "$ENV"
echo
echo "Done. Wrote $ENV (chmod 600, git-ignored)."
echo "Next: createdb swarmmemory_testnet && ./scripts/run_backend.sh testnet"
