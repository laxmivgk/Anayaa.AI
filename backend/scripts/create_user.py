#!/usr/bin/env python3
"""Create or update an Anayaa login user in PostgreSQL."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth.identity import verify_identity
from app.auth.users import ensure_users_table, upsert_user
from app.config import get_settings
from app.memory.postgres import PostgresPool


def read_password(args: argparse.Namespace) -> str:
    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise SystemExit("Passwords did not match.")
    if len(password.strip()) < 8:
        raise SystemExit("Password must be at least 8 characters.")
    return password


async def create_user(args: argparse.Namespace) -> None:
    os.chdir(ROOT)
    email = args.email.strip().lower()
    ok, err = verify_identity(email)
    if not ok:
        raise SystemExit(err or "Invalid email.")

    password = read_password(args)
    settings = get_settings()
    pg = PostgresPool(settings.postgres_dsn)
    await pg.connect()
    try:
        await ensure_users_table(pg)
        saved_email = await upsert_user(pg, email, password, disabled=args.disabled)
    finally:
        await pg.close()
    print(f"Anayaa login user saved: {saved_email}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or update an Anayaa login user.")
    parser.add_argument("--email", required=True, help="User email address.")
    parser.add_argument("--password", help="Password. Omit to enter it securely without echo.")
    parser.add_argument("--disabled", action="store_true", help="Create or update the user as disabled.")
    return parser.parse_args()


def main() -> None:
    asyncio.run(create_user(parse_args()))


if __name__ == "__main__":
    main()
