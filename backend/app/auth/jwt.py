import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_settings

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def verify_email_format(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


def create_access_token(email: str, session_id: str | None = None) -> tuple[str, str, int]:
    settings = get_settings()
    sid = session_id or str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_exp_minutes)
    payload = {
        "sub": email,
        "email": email,
        "session_id": sid,
        "role": "user",
        "exp": expires,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, sid, settings.jwt_exp_minutes


def decode_access_token(token: str) -> dict | None:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
