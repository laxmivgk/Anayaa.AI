"""User-facing citation-grounded reasons for Anayaa guidance."""
from __future__ import annotations

import re
from typing import Any

REASON_STOPWORDS = {
    "about",
    "after",
    "again",
    "because",
    "could",
    "dharma",
    "dilemma",
    "kindest",
    "least",
    "should",
    "their",
    "there",
    "these",
    "those",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


def _compact_terms(values: list[Any], limit: int = 3) -> list[str]:
    terms: list[str] = []
    for value in values:
        for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", str(value or "").lower()):
            if term not in REASON_STOPWORDS and term not in terms:
                terms.append(term)
            if len(terms) >= limit:
                return terms
    return terms


def _citation_label(citation: dict[str, Any]) -> str:
    source = str(citation.get("source") or "Scripture").strip()
    chapter = str(citation.get("chapter") or "").strip()
    verse = str(citation.get("verse") or "").strip()
    location = f" {chapter}:{verse}" if chapter and verse else ""
    return f"{source}{location}"


def _grounded_citation_ids(audit: dict[str, Any] | None) -> set[str]:
    if not audit:
        return set()
    contract = audit.get("groundingContract") or {}
    values = [
        *contract.get("groundedCitationIds", []),
        *audit.get("groundedCitationIds", []),
    ]
    return {str(value) for value in values if str(value).strip()}


def build_guidance_reasons(
    query: str,
    citations: list[dict[str, Any]],
    pathway: str | None = None,
    audit: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return 2-3 concise reasons grounded in retrieved citations."""
    used_ids = _grounded_citation_ids(audit)
    used_citations = [
        citation
        for index, citation in enumerate(citations)
        if not used_ids or str(citation.get("id") or citation.get("source") or index) in used_ids
    ]

    if len(used_citations) < 2:
        return []

    topic_terms = _compact_terms([query], limit=2)
    topic = " and ".join(topic_terms) if topic_terms else "the user's dilemma"
    reasons: list[dict[str, Any]] = []

    for citation in used_citations[:3]:
        themes = _compact_terms(
            [
                *(citation.get("keywords") or []),
                citation.get("translation"),
                citation.get("context"),
            ],
            limit=3,
        )
        theme_text = ", ".join(themes) if themes else "careful action"
        label = _citation_label(citation)
        reasons.append(
            {
                "reason": f"{label} keeps the guidance focused on {theme_text}, so the advice stays tied to {topic}.",
                "citation": label,
                "groundedTerms": themes,
            }
        )

    if len(reasons) < 2 and pathway:
        reasons.append(
            {
                "reason": "The Scripture grounding section connects the advice back to the retrieved passages instead of relying on unsupported claims.",
                "citation": "Scripture grounding",
                "groundedTerms": _compact_terms([pathway], limit=3),
            }
        )
    return reasons[:3]
