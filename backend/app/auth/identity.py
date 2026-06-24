from app.auth.jwt import verify_email_format


def verify_identity(email: str) -> tuple[bool, str | None]:
    normalized = email.strip().lower()
    if not verify_email_format(normalized):
        return False, "Invalid email format."
    return True, None
