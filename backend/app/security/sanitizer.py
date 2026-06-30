import unicodedata


def normalize_unicode(text: str) -> str:
    """Normalize visually similar Unicode forms before downstream security checks."""
    return unicodedata.normalize("NFKC", text)


def sanitize_query(text: str, max_length: int = 4000) -> str:
    """Apply the first input boundary: trim, normalize, and cap query size."""
    return normalize_unicode(text.strip())[:max_length]
