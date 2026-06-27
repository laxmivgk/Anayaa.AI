import secrets
from typing import Any

from app.auth.passwords import hash_password, verify_password


CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    disabled BOOLEAN NOT NULL DEFAULT FALSE,
    password_reset_hash TEXT,
    password_reset_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""


def normalize_email(email: str) -> str:
    return str(email).strip().lower()


async def ensure_users_table(pg: Any) -> None:
    await pg.execute(CREATE_USERS_TABLE_SQL)
    await pg.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_hash TEXT")
    await pg.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at TIMESTAMPTZ")
    await pg.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")


async def upsert_user(pg: Any, email: str, password: str, disabled: bool = False) -> str:
    normalized_email = normalize_email(email)
    password_hash = hash_password(password)
    await pg.execute(
        """
        INSERT INTO users (email, password_hash, disabled)
        VALUES ($1, $2, $3)
        ON CONFLICT (email) DO UPDATE SET
            password_hash = EXCLUDED.password_hash,
            disabled = EXCLUDED.disabled,
            updated_at = NOW()
        """,
        normalized_email,
        password_hash,
        disabled,
    )
    return normalized_email


async def register_user_if_missing(pg: Any, email: str, password: str) -> str | None:
    normalized_email = normalize_email(email)
    password_hash = hash_password(password)
    row = await pg.fetchrow(
        """
        INSERT INTO users (email, password_hash, disabled)
        VALUES ($1, $2, FALSE)
        ON CONFLICT (email) DO NOTHING
        RETURNING email
        """,
        normalized_email,
        password_hash,
    )
    if not row:
        return None
    return str(row["email"])


async def verify_user_credentials(pg: Any, email: str, password: str) -> str | None:
    normalized_email = normalize_email(email)
    row = await pg.fetchrow(
        """
        SELECT password_hash
        FROM users
        WHERE email = $1 AND disabled = FALSE
        """,
        normalized_email,
    )
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return normalized_email


async def create_password_reset_code(pg: Any, email: str) -> str | None:
    normalized_email = normalize_email(email)
    reset_code = secrets.token_urlsafe(18)
    reset_hash = hash_password(reset_code)
    row = await pg.fetchrow(
        """
        UPDATE users
        SET password_reset_hash = $2,
            password_reset_expires_at = NOW() + INTERVAL '15 minutes',
            updated_at = NOW()
        WHERE email = $1 AND disabled = FALSE
        RETURNING email
        """,
        normalized_email,
        reset_hash,
    )
    if not row:
        return None
    return reset_code


async def reset_user_password(pg: Any, email: str, reset_code: str, new_password: str) -> str | None:
    normalized_email = normalize_email(email)
    row = await pg.fetchrow(
        """
        SELECT password_reset_hash
        FROM users
        WHERE email = $1
            AND disabled = FALSE
            AND password_reset_hash IS NOT NULL
            AND password_reset_expires_at > NOW()
        """,
        normalized_email,
    )
    if not row or not verify_password(reset_code, row["password_reset_hash"]):
        return None

    await pg.execute(
        """
        UPDATE users
        SET password_hash = $2,
            password_reset_hash = NULL,
            password_reset_expires_at = NULL,
            updated_at = NOW()
        WHERE email = $1
        """,
        normalized_email,
        hash_password(new_password),
    )
    return normalized_email
