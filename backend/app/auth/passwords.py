import base64
import hashlib
import secrets


HASH_SCHEME = "pbkdf2_sha256"
HASH_ITERATIONS = 260_000
SALT_BYTES = 16


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    password_text = str(password)
    if len(password_text.strip()) < 8:
        raise ValueError("Password must be at least 8 characters.")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password_text.encode("utf-8"), salt, HASH_ITERATIONS)
    return f"{HASH_SCHEME}${HASH_ITERATIONS}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = str(stored_hash).split("$", 3)
        if scheme != HASH_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, iterations)
    return secrets.compare_digest(actual, expected)
