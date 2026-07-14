#!/usr/bin/env bash
# One-time local PostgreSQL setup for Anayaa.AI (no Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_NAME="${POSTGRES_DB:-anayaa}"
DB_USER="${POSTGRES_USER:-anayaa}"
DB_PASSWORD="${POSTGRES_PASSWORD:-anayaa_dev}"
PGHOST="${POSTGRES_HOST:-127.0.0.1}"
PGPORT="${POSTGRES_PORT:-5432}"
CLI_CMD="${ANAYAA_CLI_COMMAND:-./scripts/anayaa}"

echo "Setting up PostgreSQL at ${PGHOST}:${PGPORT} ..."

if ! pg_isready -h "$PGHOST" -p "$PGPORT" >/dev/null 2>&1; then
  echo "ERROR: PostgreSQL is not running on ${PGHOST}:${PGPORT}."
  echo "Start it first, then re-run ${CLI_CMD} setup:"
  echo "  macOS: brew services start postgresql@16"
  echo "  WSL/Linux: sudo service postgresql start"
  exit 1
fi

BOOTSTRAP_USER="${PGUSER:-$(whoami)}"
BOOTSTRAP_PSQL=(psql -h "$PGHOST" -p "$PGPORT" -U "$BOOTSTRAP_USER" -d postgres)

# Prefer the current OS user on macOS/Homebrew, then fall back to the postgres
# OS user used by most apt-based Linux and WSL installs.
if "${BOOTSTRAP_PSQL[@]}" -c "SELECT 1" >/dev/null 2>&1; then
  echo "Bootstrapping PostgreSQL as ${BOOTSTRAP_USER}."
elif command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1 \
  && sudo -u postgres psql -p "$PGPORT" -d postgres -c "SELECT 1" >/dev/null 2>&1; then
  BOOTSTRAP_PSQL=(sudo -u postgres psql -p "$PGPORT" -d postgres)
  echo "Bootstrapping PostgreSQL as postgres."
else
  echo "ERROR: Could not connect to PostgreSQL as a bootstrap user." >&2
  echo "macOS/Homebrew usually works with your current user: ${BOOTSTRAP_USER}" >&2
  echo "WSL/Linux usually needs the postgres OS user: sudo -u postgres psql -d postgres" >&2
  exit 1
fi

"${BOOTSTRAP_PSQL[@]}" -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  -- Idempotent local role creation lets anayaa setup repair password drift
  -- without requiring users to manually drop databases or roles.
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  ELSE
    ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
  END IF;
END
\$\$;

SELECT 'CREATE DATABASE ${DB_NAME} OWNER ${DB_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${DB_NAME}')\\gexec

ALTER DATABASE ${DB_NAME} OWNER TO ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

BOOTSTRAP_DB_PSQL=("${BOOTSTRAP_PSQL[@]}")
for i in "${!BOOTSTRAP_DB_PSQL[@]}"; do
  prev=""
  if [[ "$i" -gt 0 ]]; then
    prev="${BOOTSTRAP_DB_PSQL[$((i - 1))]}"
  fi
  if [[ "${BOOTSTRAP_DB_PSQL[$i]}" == "postgres" && "$prev" == "-d" ]]; then
    BOOTSTRAP_DB_PSQL[$i]="$DB_NAME"
  fi
done

"${BOOTSTRAP_DB_PSQL[@]}" -v ON_ERROR_STOP=1 <<SQL
ALTER SCHEMA public OWNER TO ${DB_USER};
GRANT USAGE, CREATE ON SCHEMA public TO ${DB_USER};
SQL

if ! PGPASSWORD="$DB_PASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" >/dev/null 2>&1; then
  echo "ERROR: Created PostgreSQL role/database, but Anayaa could not log in as ${DB_USER}." >&2
  echo "Try these recovery commands, then re-run ${CLI_CMD} setup:" >&2
  echo "  WSL/Linux: sudo -u postgres psql -d postgres -c \"ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';\"" >&2
  echo "  macOS:     psql -d postgres -c \"ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';\"" >&2
  exit 1
fi

echo "Applying schema from infra/init.sql ..."
if ! PGPASSWORD="$DB_PASSWORD" psql -h "$PGHOST" -p "$PGPORT" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$ROOT/infra/init.sql"; then
  echo "ERROR: Anayaa could log in to PostgreSQL, but schema setup failed." >&2
  echo "Check database ownership and schema access, then re-run ${CLI_CMD} setup:" >&2
  echo "  WSL/Linux: sudo -u postgres psql -d ${DB_NAME} -c \"ALTER SCHEMA public OWNER TO ${DB_USER}; GRANT USAGE, CREATE ON SCHEMA public TO ${DB_USER};\"" >&2
  echo "  macOS:     psql -d ${DB_NAME} -c \"ALTER SCHEMA public OWNER TO ${DB_USER}; GRANT USAGE, CREATE ON SCHEMA public TO ${DB_USER};\"" >&2
  exit 1
fi

echo ""
echo "PostgreSQL ready."
echo "  database: ${DB_NAME}"
echo "  user:     ${DB_USER}"
echo ""
echo "Next:"
echo "  anayaa setup"
echo "  anayaa serve"
