import re
from typing import Any

from app.security.ner import person_entity_texts

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]{0,240})\]\((?:https?://|mailto:)[^)]+\)", re.IGNORECASE)
URL_RE = re.compile(r"\b(?:https?://|mailto:)\S+", re.IGNORECASE)
PATIENT_ID_RE = re.compile(r"\b((?:patient|medical record|mrn)\s*id\s*:\s*)[A-Za-z0-9_-]+\b", re.IGNORECASE)
NAME_TOKEN_RE = r"[A-Za-z][A-Za-z'’-]{1,31}"
CAPITALIZED_NAME_TOKEN_RE = r"(?-i:[A-Z])[A-Za-z'’-]{1,31}"
PERSON_NAME_RE = rf"{NAME_TOKEN_RE}(?:\s+{CAPITALIZED_NAME_TOKEN_RE}){{0,2}}"
PERSON_INTERACTION_NAME_RE = re.compile(
    r"\b("
    r"(?:argued|fight|fought|spoke|talked|messaged|called|texted|apologized)\s+"
    r"(?:with|to)\s+"
    r")"
    rf"({PERSON_NAME_RE})"
    r"(?=\b)",
    re.IGNORECASE,
)
PERSON_ACTION_NAME_RE = re.compile(
    r"\b("
    r"(?:meet|met|meeting|see|saw|visit|visited)\s+"
    r")"
    rf"({PERSON_NAME_RE})"
    r"(?=\b)",
    re.IGNORECASE,
)
PERSON_RELATION_TERMS_RE = (
    r"(?:friend|boss|manager|coworker|colleague|partner|spouse|husband|wife|"
    r"parent|mother|mom|father|dad|brother|sister|son|daughter|teacher|neighbor|"
    r"roommate|classmate|mentor|client|customer|employee|teammate|cousin|"
    r"aunt|uncle)"
)
LOCATION_CONTEXT_RE = re.compile(
    r"\b("
    r"(?:in|at|near|from|to)\s+"
    r")"
    r"(chennai|bengaluru|bangalore|mumbai|delhi|hyderabad|pune|kolkata|ahmedabad|"
    r"jaipur|mysuru|mysore|coimbatore|madurai|trichy|kochi|london|paris|tokyo|"
    r"singapore|dubai|toronto|vancouver|sydney|melbourne|boston|chicago|seattle|"
    r"austin|dallas|houston|phoenix|los\s+angeles|san\s+francisco|new\s+york)"
    r"(?=\b)",
    re.IGNORECASE,
)
RELATION_NAME_RE = re.compile(
    r"\b("
    r"(?:(?:my|our|his|her|their)\s+)?"
    r"(?:close\s+)?"
    rf"{PERSON_RELATION_TERMS_RE}"
    r"(?:\s+(?:named|called))?"
    r"\s+)"
    rf"({PERSON_NAME_RE})"
    r"(?=\b)",
    re.IGNORECASE,
)
RELATION_IS_NAME_RE = re.compile(
    r"\b("
    r"(?:(?:my|our|his|her|their)\s+)?"
    r"(?:close\s+)?"
    rf"{PERSON_RELATION_TERMS_RE}"
    r"(?:'s\s+name)?\s+(?:is|was)\s+)"
    rf"({PERSON_NAME_RE})"
    r"(?=\b)",
    re.IGNORECASE,
)
NAME_IS_RELATION_RE = re.compile(
    r"\b"
    rf"({PERSON_NAME_RE})"
    r"(\s+(?:is|was)\s+(?:(?:my|our|his|her|their)\s+)?(?:close\s+)?"
    rf"{PERSON_RELATION_TERMS_RE}"
    r")(?=\b)",
    re.IGNORECASE,
)

RELATION_NAME_FALSE_POSITIVES = {
    "about",
    "after",
    "again",
    "agan",
    "already",
    "also",
    "and",
    "angry",
    "are",
    "as",
    "at",
    "because",
    "before",
    "being",
    "boss",
    "brother",
    "but",
    "by",
    "can",
    "could",
    "did",
    "does",
    "felt",
    "for",
    "friend",
    "from",
    "had",
    "has",
    "have",
    "her",
    "him",
    "if",
    "in",
    "into",
    "is",
    "just",
    "manager",
    "me",
    "my",
    "need",
    "needed",
    "needs",
    "not",
    "now",
    "of",
    "on",
    "or",
    "partner",
    "parent",
    "said",
    "see",
    "should",
    "show",
    "shows",
    "stopped",
    "talking",
    "that",
    "the",
    "than",
    "their",
    "them",
    "then",
    "they",
    "told",
    "to",
    "today",
    "tomorrow",
    "us",
    "was",
    "we",
    "when",
    "who",
    "will",
    "with",
    "would",
    "want",
    "wanted",
    "wants",
    "you",
    "your",
    "yours",
    "yourself",
}
PERSON_ROLE_FOLLOWERS = {
    "ceo",
    "cfo",
    "cto",
    "coo",
    "founder",
    "leader",
    "manager",
    "president",
    "chair",
    "director",
    "executive",
}

USER_VISIBLE_TEXT_KEYS = {
    "draftPathway",
    "failureReason",
    "moralPathway",
    "originalQuery",
    "previousContextQuestion",
    "rewrittenQuery",
    "userMessage",
}
RELATION_MARKER_DISPLAY_RE = re.compile(
    r"\b("
    r"(?:(?:my|your|our|his|her|their)\s+)?"
    r"(?:close\s+)?"
    r"(?:friend|boss|manager|coworker|colleague|partner|spouse|husband|wife|"
    r"parent|mother|mom|father|dad|brother|sister|son|daughter|teacher|neighbor|"
    r"roommate|classmate|mentor|client|customer|employee|teammate|cousin|"
    r"aunt|uncle)"
    r")\s+\[NAME_REDACTED\]",
    re.IGNORECASE,
)
VISIT_USER_MARKER_DISPLAY_RE = re.compile(
    r"\b("
    r"(?:let|allow|allows|allowed|have|has|had|invite|invites|invited|ask|asks|asked)\s+"
    r"(?:her|him|them|your\s+(?:mom|mother|dad|father|parent|friend|partner|spouse))\s+"
    r"(?:meet|see|visit)"
    r")\s+\[NAME_REDACTED\]",
    re.IGNORECASE,
)
ACTION_MARKER_DISPLAY_RE = re.compile(r"\b(meet|met|meeting|see|saw|visit|visited)\s+\[NAME_REDACTED\]", re.IGNORECASE)
SELF_TALK_MARKER_DISPLAY_RE = re.compile(r"\b(yourself|myself|ourselves)\s+\[NAME_REDACTED\]\s+(?=you|that|I|we)\b", re.IGNORECASE)
US_THAT_MARKER_DISPLAY_RE = re.compile(r"\b(us)\s+\[NAME_REDACTED\]\s+(?=[a-z])", re.IGNORECASE)
MARKER_NAME_TAIL_RE = re.compile(
    r"\[NAME_REDACTED\](?:\s+[A-Z][A-Za-z-]*(?:['’][A-Za-z-]+)?){1,2}(?P<possessive>['’]s|['’])?"
)
MARKER_POSSESSIVE_RE = re.compile(r"\[NAME_REDACTED\](?:['’]s|['’])")
REDUNDANT_MARKER_RE = re.compile(r"(?:\s*\[NAME_REDACTED\]){2,}")


def _is_false_positive_name(name: str) -> bool:
    parts = name.split()
    return bool(parts) and all(part.lower() in RELATION_NAME_FALSE_POSITIVES for part in parts)


def _starts_with_false_positive_name(name: str) -> bool:
    parts = name.split()
    return bool(parts) and parts[0].lower() in RELATION_NAME_FALSE_POSITIVES


def _has_role_follower(name: str) -> bool:
    return any(part.lower() in PERSON_ROLE_FOLLOWERS for part in name.split()[1:])


def _name_variants(name: str) -> list[str]:
    variants = [name]
    variants.extend(name.split())
    deduped: list[str] = []
    for variant in variants:
        if variant and not _is_false_positive_name(variant) and not any(item.lower() == variant.lower() for item in deduped):
            deduped.append(variant)
    return deduped


def _redact_relation_name(match: re.Match[str]) -> str:
    name = match.group(2)
    if _is_false_positive_name(name) or _starts_with_false_positive_name(name) or _has_role_follower(name):
        return match.group(0)
    after = match.string[match.end() :]
    next_word = re.match(r"\s+([A-Za-z][A-Za-z'’-]{1,31})\b", after)
    if next_word and next_word.group(1).lower() in PERSON_ROLE_FOLLOWERS:
        return match.group(0)
    return f"{match.group(1)}[NAME_REDACTED]"


def _redact_name_before_relation(match: re.Match[str]) -> str:
    name = match.group(1)
    if _is_false_positive_name(name) or _starts_with_false_positive_name(name) or _has_role_follower(name):
        return match.group(0)
    return f"[NAME_REDACTED]{match.group(2)}"


def _redact_location(match: re.Match[str]) -> str:
    return f"{match.group(1)}[LOCATION_REDACTED]"


def detect_sensitive_names(text: str) -> list[str]:
    """Find relationship/action-linked names in user text so later standalone leaks can be scrubbed."""
    names: list[str] = []
    for name in person_entity_texts(text):
        if _is_false_positive_name(name) or _starts_with_false_positive_name(name) or _has_role_follower(name):
            continue
        for variant in _name_variants(name):
            if not any(existing.lower() == variant.lower() for existing in names):
                names.append(variant)
    for pattern in (PERSON_INTERACTION_NAME_RE, PERSON_ACTION_NAME_RE, RELATION_NAME_RE, RELATION_IS_NAME_RE):
        for match in pattern.finditer(text):
            name = match.group(2).strip()
            if _is_false_positive_name(name) or _starts_with_false_positive_name(name) or _has_role_follower(name):
                continue
            after = match.string[match.end() :]
            next_word = re.match(r"\s+([A-Za-z][A-Za-z'’-]{1,31})\b", after)
            if next_word and next_word.group(1).lower() in PERSON_ROLE_FOLLOWERS:
                continue
            for variant in _name_variants(name):
                if not any(existing.lower() == variant.lower() for existing in names):
                    names.append(variant)
    for match in NAME_IS_RELATION_RE.finditer(text):
        name = match.group(1).strip()
        if _is_false_positive_name(name) or _starts_with_false_positive_name(name) or _has_role_follower(name):
            continue
        for variant in _name_variants(name):
            if not any(existing.lower() == variant.lower() for existing in names):
                names.append(variant)
    return names


def _redact_extra_names(text: str, extra_names: list[str] | None = None) -> str:
    scrubbed = text
    for name in sorted(extra_names or [], key=len, reverse=True):
        if name.lower() in RELATION_NAME_FALSE_POSITIVES:
            continue
        scrubbed = re.sub(
            rf"\b{re.escape(name)}\b(?P<possessive>['’]s|['’])?",
            lambda match: "[NAME_REDACTED]'s" if match.group("possessive") else "[NAME_REDACTED]",
            scrubbed,
            flags=re.IGNORECASE,
        )
    scrubbed = MARKER_NAME_TAIL_RE.sub(
        lambda match: "[NAME_REDACTED]'s" if match.group("possessive") else "[NAME_REDACTED]",
        scrubbed,
    )
    return scrubbed


def scrub_pii(text: str, extra_names: list[str] | None = None) -> str:
    """Redact common direct identifiers before storage, traces, and model-facing workflow state."""
    scrubbed = MARKDOWN_LINK_RE.sub(r"\1", text)
    scrubbed = URL_RE.sub("[URL_REDACTED]", scrubbed)
    scrubbed = EMAIL_RE.sub("[EMAIL_REDACTED]", scrubbed)
    scrubbed = PHONE_RE.sub("[PHONE_REDACTED]", scrubbed)
    scrubbed = SSN_RE.sub("[SSN_REDACTED]", scrubbed)
    scrubbed = PATIENT_ID_RE.sub(r"\1[PATIENT_ID_REDACTED]", scrubbed)
    scrubbed = PERSON_INTERACTION_NAME_RE.sub(_redact_relation_name, scrubbed)
    scrubbed = PERSON_ACTION_NAME_RE.sub(_redact_relation_name, scrubbed)
    scrubbed = RELATION_NAME_RE.sub(_redact_relation_name, scrubbed)
    scrubbed = RELATION_IS_NAME_RE.sub(_redact_relation_name, scrubbed)
    scrubbed = NAME_IS_RELATION_RE.sub(_redact_name_before_relation, scrubbed)
    scrubbed = LOCATION_CONTEXT_RE.sub(_redact_location, scrubbed)
    return _redact_extra_names(scrubbed, extra_names)


def scrub_pii_deep(value: Any, extra_names: list[str] | None = None) -> Any:
    """Recursively scrub PII from JSON-like response payloads before returning them to the UI."""
    if isinstance(value, str):
        return scrub_pii(value, extra_names=extra_names)
    if isinstance(value, list):
        return [scrub_pii_deep(item, extra_names=extra_names) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_pii_deep(item, extra_names=extra_names) for item in value)
    if isinstance(value, dict):
        return {key: scrub_pii_deep(item, extra_names=extra_names) for key, item in value.items()}
    return value


def humanize_redaction_markers(text: str) -> str:
    """Keep final user-facing guidance readable after privacy redaction."""
    cleaned = MARKER_NAME_TAIL_RE.sub(
        lambda match: "[NAME_REDACTED]'s" if match.group("possessive") else "[NAME_REDACTED]",
        text,
    )
    cleaned = MARKER_POSSESSIVE_RE.sub("the other person's", cleaned)
    cleaned = RELATION_MARKER_DISPLAY_RE.sub(r"\1", cleaned)
    cleaned = VISIT_USER_MARKER_DISPLAY_RE.sub(r"\1 you", cleaned)
    cleaned = ACTION_MARKER_DISPLAY_RE.sub(r"\1 them", cleaned)
    cleaned = SELF_TALK_MARKER_DISPLAY_RE.sub(r"\1 that ", cleaned)
    cleaned = US_THAT_MARKER_DISPLAY_RE.sub(r"\1 that ", cleaned)
    cleaned = REDUNDANT_MARKER_RE.sub(" [NAME_REDACTED]", cleaned)
    cleaned = cleaned.replace("[NAME_REDACTED]", "the other person")
    return re.sub(r"\s+", " ", cleaned).replace(" .", ".").replace(" ,", ",").strip()


def scrub_pii_for_display(text: str, extra_names: list[str] | None = None) -> str:
    """Redact direct identifiers, then convert placeholders in final guidance into safe prose."""
    scrubbed = scrub_pii(text, extra_names=extra_names)
    scrubbed = _redact_extra_names(scrubbed, detect_sensitive_names(scrubbed))
    return humanize_redaction_markers(scrubbed)


def scrub_pii_response_deep(value: Any, key: str | None = None, extra_names: list[str] | None = None) -> Any:
    """Recursively scrub API responses, keeping final answer fields readable."""
    if isinstance(value, str):
        scrubbed = scrub_pii(value, extra_names=extra_names)
        if key in USER_VISIBLE_TEXT_KEYS:
            scrubbed = _redact_extra_names(scrubbed, detect_sensitive_names(scrubbed))
            return humanize_redaction_markers(scrubbed)
        return scrubbed
    if isinstance(value, list):
        return [scrub_pii_response_deep(item, key=key, extra_names=extra_names) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_pii_response_deep(item, key=key, extra_names=extra_names) for item in value)
    if isinstance(value, dict):
        return {item_key: scrub_pii_response_deep(item, key=str(item_key), extra_names=extra_names) for item_key, item in value.items()}
    return value
