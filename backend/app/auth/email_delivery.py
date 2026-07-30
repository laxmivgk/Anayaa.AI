from __future__ import annotations

from urllib.parse import urlencode

from app.config import Settings


def build_password_reset_link(settings: Settings, email: str, reset_code: str) -> str:
    base_url = settings.password_reset_base_url.rstrip("/")
    query = urlencode({"resetEmail": email, "resetCode": reset_code})
    return f"{base_url}/?{query}"


def deliver_password_reset(email: str, reset_code: str, settings: Settings) -> str:
    reset_link = build_password_reset_link(settings, email, reset_code)

    # Local-first password recovery uses the operator's terminal as the delivery
    # channel. The database stores only reset-token hashes.
    print(f"[anayaa-auth] Password reset code for {email}: {reset_code}", flush=True)
    print(f"[anayaa-auth] Password reset link for {email}: {reset_link}", flush=True)
    return "terminal"
