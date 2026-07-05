from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.api.routes.auth import LoginBody, PasswordResetConfirmBody, PasswordResetRequestBody
from app.auth.email_delivery import (
    PasswordResetDeliveryUnavailable,
    build_password_reset_link,
    deliver_password_reset,
)
from app.auth.passwords import hash_password, verify_password
from app.auth.users import (
    create_password_reset_code,
    normalize_email,
    register_user_if_missing,
    reset_user_password,
    upsert_user,
    verify_user_credentials,
)
from app.auth.jwt import user_history_key
from app.config import Settings, get_settings


class FakeUserPg:
    def __init__(self):
        self.users: dict[str, dict[str, object]] = {}

    async def execute(self, query: str, *args):
        if "INSERT INTO users" in query:
            email, password_hash, disabled = args
            self.users[email] = {
                "password_hash": password_hash,
                "disabled": disabled,
                "password_reset_hash": None,
                "password_reset_expires_at": None,
            }
        elif "UPDATE users" in query and "SET password_hash" in query:
            email, password_hash = args
            self.users[email]["password_hash"] = password_hash
            self.users[email]["password_reset_hash"] = None
            self.users[email]["password_reset_expires_at"] = None
        return "OK"

    async def fetchrow(self, query: str, *args):
        if "INSERT INTO users" in query:
            email, password_hash = args
            if email in self.users:
                return None
            self.users[email] = {
                "password_hash": password_hash,
                "disabled": False,
                "password_reset_hash": None,
                "password_reset_expires_at": None,
            }
            return {"email": email}
        if "UPDATE users" in query and "password_reset_hash" in query:
            email, reset_hash = args
            user = self.users.get(email)
            if not user or user["disabled"]:
                return None
            user["password_reset_hash"] = reset_hash
            user["password_reset_expires_at"] = datetime.now(timezone.utc) + timedelta(minutes=15)
            return {"email": email}
        if "SELECT password_reset_hash" in query:
            email = args[0]
            user = self.users.get(email)
            expires_at = user and user.get("password_reset_expires_at")
            if (
                not user
                or user["disabled"]
                or not user.get("password_reset_hash")
                or not expires_at
                or expires_at <= datetime.now(timezone.utc)
            ):
                return None
            return {"password_reset_hash": user["password_reset_hash"]}
        email = args[0]
        user = self.users.get(email)
        if not user or user["disabled"]:
            return None
        return {"password_hash": user["password_hash"]}

def test_login_body_requires_password():
    with pytest.raises(ValidationError):
        LoginBody(email="tester@example.com")


def test_password_reset_bodies_require_expected_fields():
    with pytest.raises(ValidationError):
        PasswordResetRequestBody()
    with pytest.raises(ValidationError):
        PasswordResetConfirmBody(email="tester@example.com", resetCode="code")


def test_password_hash_verification():
    stored_hash = hash_password("local-password")

    assert stored_hash != "local-password"
    assert verify_password("local-password", stored_hash) is True
    assert verify_password("wrong-password", stored_hash) is False


def test_password_hash_rejects_short_password():
    with pytest.raises(ValueError, match="at least 8"):
        hash_password("short")


def test_normalize_email():
    assert normalize_email(" Tester@Example.com ") == "tester@example.com"


def test_user_history_key_is_stable_and_pseudonymous(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "history-key-test-secret-value-1234567890")
    get_settings.cache_clear()
    try:
        first = user_history_key("Tester@Example.com")
        second = user_history_key(" tester@example.com ")
        other = user_history_key("other@example.com")
    finally:
        get_settings.cache_clear()

    assert first == second
    assert first != other
    assert "tester" not in first
    assert "example" not in first
    assert len(first) == 32


@pytest.mark.anyio
async def test_user_specific_credentials_are_verified_against_database():
    pg = FakeUserPg()
    saved_email = await upsert_user(pg, " Tester@Example.com ", "local-password")

    assert saved_email == "tester@example.com"
    assert await verify_user_credentials(pg, "tester@example.com", "local-password") == "tester@example.com"
    assert await verify_user_credentials(pg, "tester@example.com", "wrong-password") is None
    assert await verify_user_credentials(pg, "unknown@example.com", "local-password") is None


@pytest.mark.anyio
async def test_disabled_users_cannot_login():
    pg = FakeUserPg()
    await upsert_user(pg, "tester@example.com", "local-password", disabled=True)

    assert await verify_user_credentials(pg, "tester@example.com", "local-password") is None


@pytest.mark.anyio
async def test_new_email_can_register_with_own_password():
    pg = FakeUserPg()

    saved_email = await register_user_if_missing(pg, " New@Example.com ", "local-password")

    assert saved_email == "new@example.com"
    assert await verify_user_credentials(pg, "new@example.com", "local-password") == "new@example.com"


@pytest.mark.anyio
async def test_new_email_registration_does_not_overwrite_existing_user():
    pg = FakeUserPg()
    await upsert_user(pg, "existing@example.com", "local-password")

    assert await register_user_if_missing(pg, "existing@example.com", "new-password") is None
    assert await verify_user_credentials(pg, "existing@example.com", "local-password") == "existing@example.com"
    assert await verify_user_credentials(pg, "existing@example.com", "new-password") is None


@pytest.mark.anyio
async def test_additional_new_email_can_register_after_users_exist():
    pg = FakeUserPg()
    await upsert_user(pg, "existing@example.com", "local-password")

    assert await register_user_if_missing(pg, "second@example.com", "second-password") == "second@example.com"
    assert await verify_user_credentials(pg, "second@example.com", "second-password") == "second@example.com"


@pytest.mark.anyio
async def test_password_reset_changes_existing_user_password():
    pg = FakeUserPg()
    await upsert_user(pg, "tester@example.com", "local-password")

    reset_code = await create_password_reset_code(pg, "tester@example.com")

    assert reset_code
    assert await reset_user_password(pg, "tester@example.com", reset_code, "new-password") == "tester@example.com"
    assert await verify_user_credentials(pg, "tester@example.com", "local-password") is None
    assert await verify_user_credentials(pg, "tester@example.com", "new-password") == "tester@example.com"


@pytest.mark.anyio
async def test_password_reset_rejects_unknown_or_invalid_code():
    pg = FakeUserPg()
    await upsert_user(pg, "tester@example.com", "local-password")

    assert await create_password_reset_code(pg, "unknown@example.com") is None
    assert await reset_user_password(pg, "tester@example.com", "wrong-code", "new-password") is None


@pytest.mark.anyio
async def test_password_reset_rejects_expired_code():
    pg = FakeUserPg()
    await upsert_user(pg, "tester@example.com", "local-password")
    reset_code = await create_password_reset_code(pg, "tester@example.com")
    pg.users["tester@example.com"]["password_reset_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)

    assert await reset_user_password(pg, "tester@example.com", reset_code or "", "new-password") is None


def test_settings_ignores_legacy_login_user_env():
    settings = Settings(
        JWT_SECRET="x" * 32,
        ANAYAA_LOGIN_USERS="legacy@example.com=legacy-password",
    )

    assert not hasattr(settings, "login_users")


def test_password_reset_link_contains_email_and_server_side_token():
    settings = Settings(
        JWT_SECRET="x" * 32,
        password_reset_base_url="https://anayaa.example.com",
    )

    link = build_password_reset_link(settings, "tester@example.com", "reset-token")

    assert link == "https://anayaa.example.com/?resetEmail=tester%40example.com&resetCode=reset-token"


def test_production_password_reset_requires_email_delivery():
    settings = Settings(
        JWT_SECRET="x" * 32,
        app_env="production",
        smtp_host="",
        smtp_from="",
    )

    with pytest.raises(PasswordResetDeliveryUnavailable):
        deliver_password_reset("tester@example.com", "reset-token", settings)


def test_local_password_reset_can_fall_back_to_terminal(capsys):
    settings = Settings(
        JWT_SECRET="x" * 32,
        app_env="local",
        smtp_host="",
        smtp_from="",
    )

    assert deliver_password_reset("tester@example.com", "reset-token", settings) == "terminal"

    output = capsys.readouterr().out
    assert "Password reset code for tester@example.com: reset-token" in output
    assert "resetEmail=tester%40example.com" in output


def test_local_password_reset_falls_back_to_terminal_when_smtp_unavailable(monkeypatch, capsys):
    class UnavailableSmtp:
        def __init__(self, *args, **kwargs):
            raise OSError("mail catcher is not running")

    monkeypatch.setattr("app.auth.email_delivery.smtplib.SMTP", UnavailableSmtp)
    settings = Settings(
        JWT_SECRET="x" * 32,
        app_env="local",
        smtp_host="127.0.0.1",
        smtp_port=1025,
        smtp_from="no-reply@anayaa.local",
        smtp_starttls=False,
    )

    assert deliver_password_reset("tester@example.com", "reset-token", settings) == "terminal"

    output = capsys.readouterr().out
    assert "Password reset code for tester@example.com: reset-token" in output


def test_password_reset_email_delivery_uses_smtp(monkeypatch):
    sent_messages = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False
            self.logged_in = None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            self.started_tls = True

        def login(self, username, password):
            self.logged_in = (username, password)

        def send_message(self, message):
            sent_messages.append((self, message))

    monkeypatch.setattr("app.auth.email_delivery.smtplib.SMTP", FakeSmtp)
    settings = Settings(
        JWT_SECRET="x" * 32,
        smtp_host="smtp.example.com",
        smtp_port=2525,
        smtp_from="no-reply@anayaa.example.com",
        smtp_username="mailer",
        smtp_password="secret",
        smtp_starttls=True,
        password_reset_base_url="https://anayaa.example.com",
    )

    assert deliver_password_reset("tester@example.com", "reset-token", settings) == "email"

    smtp, message = sent_messages[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 2525
    assert smtp.started_tls is True
    assert smtp.logged_in == ("mailer", "secret")
    assert message["To"] == "tester@example.com"
    assert message["From"] == "no-reply@anayaa.example.com"
    assert "reset-token" in message.get_content()
    assert "https://anayaa.example.com/?resetEmail=tester%40example.com&resetCode=reset-token" in message.get_content()
