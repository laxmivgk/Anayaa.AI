import unicodedata


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def sanitize_query(text: str, max_length: int = 4000) -> str:
    return normalize_unicode(text.strip())[:max_length]
