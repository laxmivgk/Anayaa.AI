#!/usr/bin/env bash
# One-time local PostgreSQL setup for Anayaa.AI (no Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${POSTGRES_DB:-anayaa}"
DB_USER="${POSTGRES_USER:-anayaa}"
DB_PASSWORD="${POSTGRES_PASSWORD:-anayaa_dev}"
PGHOST="${POSTGRES_HOST:-127.0.0.1}"
PGPORT="${POSTGRES_PORT:-5432}"

echo "Setting up PostgreSQL at ${PGHOST}:${PGPORT} ..."

if ! pg_isready -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1; then
  echo "ERROR: PostgreSQL is not running on ${PGHOST}:${PGPORT}."
  echo "Start it first, e.g. brew services start postgresql@16"
  exit 1
fi

# Use current OS user for bootstrap (works on Homebrew Postgres on macOS)
BOOTSTRAP_USER="${PGUSER:-$(whoami)}"

psql -h "$PGHOST" -p "$PGPORT" -U "$BOOTSTRAP_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\\gexec

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "Applying schema from infra/init.sql ..."
PGPASSWORD="$DB_PASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$ROOT/infra/init.sql"

echo ""
echo "PostgreSQL ready."
echo "  database: ${DB_NAME}"
echo "  user:     ${DB_USER}"
echo ""
echo "Next:"
echo "  1. Set POSTGRES_ENABLED=true in backend/.env"
echo "  2. cd backend && python scripts/seed_milvus.py"
