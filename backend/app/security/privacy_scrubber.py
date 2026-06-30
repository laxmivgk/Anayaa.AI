import re
from typing import Any

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def scrub_pii(text: str) -> str:
    """Redact common direct identifiers before storage, traces, and model-facing workflow state."""
    scrubbed = EMAIL_RE.sub("[EMAIL_REDACTED]", text)
    scrubbed = PHONE_RE.sub("[PHONE_REDACTED]", scrubbed)
    scrubbed = SSN_RE.sub("[SSN_REDACTED]", scrubbed)
    return scrubbed


def scrub_pii_deep(value: Any) -> Any:
    """Recursively scrub PII from JSON-like response payloads before returning them to the UI."""
    if isinstance(value, str):
        return scrub_pii(value)
    if isinstance(value, list):
        return [scrub_pii_deep(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_pii_deep(item) for item in value)
    if isinstance(value, dict):
        return {key: scrub_pii_deep(item) for key, item in value.items()}
    return value
