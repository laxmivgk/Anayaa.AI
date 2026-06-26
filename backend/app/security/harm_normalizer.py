"""Normalize revenge-oriented wording into safe guidance intent."""
from __future__ import annotations

import re

SAFE_GUIDANCE_TERMS = ["lawful protection", "documentation", "calm boundaries", "non-escalation"]

REVENGE_FRAMING_RE = re.compile(
    r"\b(?:revenge|vengeance|retaliat\w*|payback|get\s+back\s+at|even\s+the\s+score)\b",
    re.I,
)

ACTIONABLE_HARM_RE = re.compile(
    r"\b(?:spy|spying|sabotage|sabotaging|blackmail|blackmailing|threaten|threatening)\b",
    re.I,
)


def normalize_harmful_framing_text(text: str) -> str:
    """Convert unsafe conflict wording into safer synthesis language."""
    normalized = str(text or "")
    normalized = REVENGE_FRAMING_RE.sub("seek lawful protection and calm boundaries", normalized)
    normalized = ACTIONABLE_HARM_RE.sub("choose lawful documentation and protection", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_harmful_concepts(concepts: list[str]) -> list[str]:
    """Remove unsafe concepts and replace them with safe guidance concepts."""
    normalized: list[str] = []
    replaced_any = False

    for raw_concept in concepts:
        concept = str(raw_concept).strip().lower()
        if not concept:
            continue
        if REVENGE_FRAMING_RE.search(concept) or ACTIONABLE_HARM_RE.search(concept):
            replaced_any = True
            continue
        if concept not in normalized:
            normalized.append(concept)

    if replaced_any:
        for safe_term in SAFE_GUIDANCE_TERMS:
            if safe_term not in normalized:
                normalized.append(safe_term)

    return normalized[:8]
