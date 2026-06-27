"""Deterministic grounding contract for final Anayaa answers."""
from __future__ import annotations

import re
from typing import Any

QUERY_STOPWORDS = {
    "about",
    "after",
    "again",
    "asking",
    "because",
    "could",
    "dharma",
    "dilemma",
    "facts",
    "harmful",
    "inventing",
    "kindest",
    "least",
    "missing",
    "provided",
    "situation",
    "their",
    "there",
    "these",
    "those",
    "through",
    "under",
    "understand",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "wisest",
    "should",
    "need",
    "want",
    "feel",
    "help",
}

UNSUPPORTED_ASSUMPTION_PATTERNS = [
    r"\byou (?:already|clearly|definitely) (?:invested|lost|started|failed|know)\b",
    r"\byou must have\b",
    r"\byour (?:partner|friend|manager|customer|family) (?:intended|wanted|planned|hates|knows)\b",
    r"\bthey (?:intended|wanted|planned|hate|know) (?:to|that)\b",
    r"\bguaranteed\b",
    r"\bwill definitely\b",
    r"\balways\b.*\bscam\b",
    r"\bnever\b.*\bethical\b",
    r"\bshopify\b",
    r"\boberlo\b",
    r"\binitial costs?\b",
    r"\blosses\b",
]

TERM_ALIASES = {
    "disciplined": ["discipline", "self-control"],
    "discipline": ["disciplined", "self-control"],
    "scamming": ["scam"],
    "scam": ["scamming"],
    "lying": ["lie", "lied", "truth"],
    "lied": ["lie", "lying", "truth"],
    "stressed": ["stress", "anxiety"],
    "stress": ["stressed", "anxiety"],
    "truthful": ["truth", "honesty"],
}


def _terms_from_text(text: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", str(text or "").lower()):
        if term not in QUERY_STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def _citation_terms(citation: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    values = [
        *(citation.get("keywords") or []),
        citation.get("source", ""),
        citation.get("faith", ""),
        citation.get("translation", ""),
        citation.get("context", ""),
    ]
    for value in values:
        for term in _terms_from_text(str(value)):
            if term not in terms:
                terms.append(term)
    return terms


def _scripture_grounding_section(pathway: str) -> str:
    match = re.search(
        r"(?:^|\n)\s*scripture grounding\s*:\s*(?P<section>.*?)(?=\n\s*(?:one-line summary|summary|reflection|judg(?:e)?ment|next step)\s*:|\Z)",
        str(pathway or ""),
        flags=re.I | re.S,
    )
    return re.sub(r"\s+", " ", match.group("section")).strip().lower() if match else ""


def _unsupported_assumptions(pathway: str) -> list[str]:
    lower = str(pathway or "").lower()
    matches: list[str] = []
    for pattern in UNSUPPORTED_ASSUMPTION_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            matches.append(match.group(0))
    return matches


def evaluate_grounding_contract(query: str, citations: list[dict[str, Any]], pathway: str) -> dict[str, Any]:
    grounding_section = _scripture_grounding_section(pathway)
    pathway_lower = str(pathway or "").lower()
    query_terms = _terms_from_text(query)
    matched_query_terms = [term for term in query_terms if _term_in_text(term, pathway_lower)]

    grounded_terms: list[str] = []
    grounded_citation_ids: list[str] = []
    for index, citation in enumerate(citations):
        citation_id = str(citation.get("id") or citation.get("source") or index)
        citation_matches = [term for term in _citation_terms(citation)[:12] if term in grounding_section]
        if citation_matches:
            grounded_citation_ids.append(citation_id)
        for term in citation_matches:
            if term not in grounded_terms:
                grounded_terms.append(term)

    required_query_matches = 1 if len(query_terms) <= 2 else 2
    unsupported = _unsupported_assumptions(pathway)
    checks = {
        "minimumTwoCitations": len(citations) >= 2,
        "scriptureGroundingSectionPresent": bool(grounding_section),
        "citationTermsInScriptureGrounding": len(grounded_terms) >= 2 and len(grounded_citation_ids) >= 2,
        "answerUsesUserTopicTerms": len(matched_query_terms) >= required_query_matches,
        "noUnsupportedAssumptions": not unsupported,
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "passed": not failed_checks,
        "checks": checks,
        "failedChecks": failed_checks,
        "citationCount": len(citations),
        "groundedCitationCount": len(grounded_citation_ids),
        "groundedCitationIds": grounded_citation_ids[:8],
        "groundedTerms": grounded_terms[:8],
        "matchedQueryTerms": matched_query_terms[:8],
        "unsupportedAssumptions": unsupported[:8],
    }


def _term_in_text(term: str, text: str) -> bool:
    candidates = [term, *TERM_ALIASES.get(term, [])]
    return any(candidate and candidate in text for candidate in candidates)


def apply_grounding_contract(
    audit: dict[str, Any],
    query: str,
    citations: list[dict[str, Any]],
    pathway: str,
) -> dict[str, Any]:
    llm_judge_passed = bool(audit.get("passed", False))
    audit["llmJudgePassed"] = llm_judge_passed
    contract = evaluate_grounding_contract(query, citations, pathway)
    if contract["groundedTerms"]:
        audit["groundedTerms"] = list(dict.fromkeys([*audit.get("groundedTerms", []), *contract["groundedTerms"]]))[:8]
    if contract["groundedCitationIds"]:
        audit["groundedCitationIds"] = list(
            dict.fromkeys([*audit.get("groundedCitationIds", []), *contract["groundedCitationIds"]])
        )[:8]
    if contract["matchedQueryTerms"]:
        audit["matchedQueryTerms"] = list(dict.fromkeys([*audit.get("matchedQueryTerms", []), *contract["matchedQueryTerms"]]))[:8]
    audit["groundingContract"] = contract
    if contract["passed"]:
        return audit

    failed_dimensions = list(dict.fromkeys([*audit.get("failedDimensions", []), "grounding_contract"]))
    revision_hints = list(audit.get("revision_hints", []))
    revision_hints.append(
        "Revise the final answer so Scripture grounding uses at least two retrieved citations, repeats citation terms, stays on the user's topic, and avoids unsupported assumptions."
    )
    rationale = (
        "The LLM score check passed, but the final answer did not connect clearly enough to the retrieved scriptures."
        if llm_judge_passed
        else str(audit.get("rationale") or "").strip()
    )
    audit.update(
        {
            "passed": False,
            "failedDimensions": failed_dimensions,
            "revision_hints": list(dict.fromkeys(revision_hints)),
            "auditStatus": "below_threshold",
            "rationale": rationale or "Grounding contract failed deterministic final-answer checks.",
        }
    )
    return audit
