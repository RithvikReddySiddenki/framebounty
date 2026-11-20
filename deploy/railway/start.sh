#!/bin/bash
# Container entrypoint for the hosted demo backend (see Dockerfile for why the
# API and worker share one container). Fails fast: if either process exits,
# the container exits so Railway's restart policy brings both back together.
set -euo pipefail

# Railway's Postgres plugin provides postgres:// or postgresql:// URLs; the app
# deliberately requires the psycopg driver URL (framebounty/db.py).
case "${DATABASE_URL:-}" in
  postgres://*)   DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgres://}" ;;
  postgresql://*) DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgresql://}" ;;
esac
export DATABASE_URL

# Absolute path so API and worker resolve the same directory regardless of cwd.
export STORAGE_ROOT="${STORAGE_ROOT:-/data/media}"
mkdir -p "$STORAGE_ROOT"

# Idempotent: applies only migrations newer than the database's current head.
alembic -c /app/services/api/alembic.ini upgrade head

python -m framebounty.worker &
uvicorn framebounty.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --forwarded-allow-ips='*' &

wait -n
echo "A backend process exited; stopping container so it restarts cleanly." >&2
exit 1
