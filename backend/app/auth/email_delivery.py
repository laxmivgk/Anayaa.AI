from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import urlencode

from app.config import Settings


class PasswordResetDeliveryUnavailable(RuntimeError):
    pass


def smtp_configured(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


def password_reset_delivery_configured(settings: Settings) -> bool:
    # Local beta can print reset links to the terminal, but production must have
    # SMTP configured so reset secrets are not exposed in server logs.
    return smtp_configured(settings) or settings.app_env.lower() != "production"


def build_password_reset_link(settings: Settings, email: str, reset_code: str) -> str:
    base_url = settings.password_reset_base_url.rstrip("/")
    query = urlencode({"resetEmail": email, "resetCode": reset_code})
    return f"{base_url}/?{query}"


def deliver_password_reset(email: str, reset_code: str, settings: Settings) -> str:
    reset_link = build_password_reset_link(settings, email, reset_code)
    message = (
        "Anayaa.AI password reset\n\n"
        "Use this one-time reset code within 15 minutes:\n\n"
        f"{reset_code}\n\n"
        "Or open this reset link and choose a new password:\n\n"
        f"{reset_link}\n\n"
        "If you did not request this, you can ignore this message."
    )

    if smtp_configured(settings):
        try:
            _send_smtp(
                settings=settings,
                to_email=email,
                subject="Reset your Anayaa.AI password",
                body=message,
            )
            return "email"
        except PasswordResetDeliveryUnavailable:
            if settings.app_env.lower() == "production":
                raise

    if settings.app_env.lower() == "production":
        raise PasswordResetDeliveryUnavailable(
            "Password reset email delivery is not configured for production."
        )

    # Terminal delivery is intentionally restricted to local mode. The database
    # stores only reset-token hashes; this print is the local operator channel.
    print(f"[anayaa-auth] Password reset code for {email}: {reset_code}", flush=True)
    print(f"[anayaa-auth] Password reset link for {email}: {reset_link}", flush=True)
    return "terminal"


def _send_smtp(settings: Settings, to_email: str, subject: str, body: str) -> None:
    email = EmailMessage()
    email["From"] = settings.smtp_from
    email["To"] = to_email
    email["Subject"] = subject
    email.set_content(body)

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                _authenticate_and_send(smtp, settings, email)
            return

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            _authenticate_and_send(smtp, settings, email)
    except OSError as exc:
        raise PasswordResetDeliveryUnavailable("Could not send password reset email.") from exc
    except smtplib.SMTPException as exc:
        raise PasswordResetDeliveryUnavailable("Could not send password reset email.") from exc


def _authenticate_and_send(smtp, settings: Settings, email: EmailMessage) -> None:
    if settings.smtp_username:
        smtp.login(settings.smtp_username, settings.smtp_password)
    smtp.send_message(email)
