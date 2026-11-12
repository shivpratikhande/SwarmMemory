#!/usr/bin/env bash
# Run migrations and start the API.  ./scripts/run_backend.sh [demo|testnet]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-demo}"
cd "$ROOT"
if [ "$MODE" = "testnet" ]; then
  [ -f backend/.env.testnet ] || { echo "backend/.env.testnet missing — run scripts/setup_testnet.sh"; exit 1; }
  set -a; source backend/.env.testnet; set +a
else
  [ -f .env ] && { set -a; source .env; set +a; }
  export SWARM_MODE=demo
fi
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://localhost:5432/swarmmemory}"
DB_NAME="${DATABASE_URL##*/}"
createdb "$DB_NAME" 2>/dev/null || true
psql -q -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector" >/dev/null
(cd backend && ../.venv/bin/alembic -c alembic.ini upgrade head)
exec .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port "${PORT:-8000}"
