import re
from typing import Any

from app.config import get_settings

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


def _citation_grounding_score(citations: list[dict[str, Any]], pathway_lower: str) -> tuple[int, list[str]]:
    """Score whether the answer appears grounded in retrieved citation content."""
    if not citations:
        return 0, []

    matched_terms: list[str] = []
    for citation in citations:
        candidate_terms = [
            *(citation.get("keywords") or []),
            citation.get("source", ""),
            citation.get("faith", ""),
        ]
        for raw_term in candidate_terms:
            term = str(raw_term).strip().lower()
            if len(term) >= 4 and term in pathway_lower and term not in matched_terms:
                matched_terms.append(term)

    if len(matched_terms) >= 3:
        return 5, matched_terms
    if len(matched_terms) >= 2:
        return 4, matched_terms
    if len(matched_terms) == 1:
        return 3, matched_terms
    return 2, matched_terms


def _query_relevance_score(query: str, pathway_lower: str) -> tuple[int, list[str]]:
    terms: list[str] = []
    for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", query.lower()):
        if term not in QUERY_STOPWORDS and term not in terms:
            terms.append(term)

    if not terms:
        return 3, []

    matched_terms = [term for term in terms if term in pathway_lower]
    required_matches = 1 if len(terms) <= 2 else 2
    if len(matched_terms) >= max(3, required_matches):
        return 5, matched_terms
    if len(matched_terms) >= required_matches:
        return 4, matched_terms
    if len(matched_terms) == 1 and required_matches == 1:
        return 3, matched_terms
    return 2, matched_terms


def _harmlessness_score(pathway_lower: str) -> int:
    harmful_patterns = [
        r"\brevenge\b",
        r"\bretaliate\b",
        r"\bretaliating\b",
        r"\bretaliation\b",
        r"\bspy\b",
        r"\bspying\b",
        r"\bsabotage\b",
        r"\bsabotaging\b",
        r"\bblackmail\b",
        r"\bblackmailing\b",
        r"\bthreaten\b",
        r"\bthreatening\b",
    ]
    safety_cues = {
        "avoid",
        "do not",
        "don't",
        "never",
        "not",
        "non-retaliation",
        "refuse",
        "without",
        "instead of",
        "rather than",
        "lawful",
        "ethical",
        "document",
        "legal",
    }

    sentences = re.split(r"[.!?\n]+", pathway_lower)
    for sentence in sentences:
        if not any(re.search(pattern, sentence) for pattern in harmful_patterns):
            continue
        if any(cue in sentence for cue in safety_cues):
            continue
        return 2
    return 4


def run_g_eval_judge(query: str, citations: list[dict[str, Any]], pathway: str) -> dict[str, Any]:
    citation_text = " ".join(c.get("translation", "") for c in citations).lower()
    pathway_lower = pathway.lower()

    faithfulness = 3
    if citations:
        overlap = sum(1 for c in citations if any(k in pathway_lower for k in c.get("keywords", [])[:2]))
        faithfulness = min(5, 3 + overlap)

    dharma = 4 if any(w in pathway_lower for w in ["compassion", "duty", "peace", "justice", "harmony"]) else 3
    harmlessness = _harmlessness_score(pathway_lower)
    privacy = 4 if "[email_redacted]" not in pathway_lower else 5
    grounding, grounded_terms = _citation_grounding_score(citations, pathway_lower)
    query_relevance, matched_query_terms = _query_relevance_score(query, pathway_lower)

    scores = {
        "faithfulness": faithfulness,
        "citation_grounding": grounding,
        "query_relevance": query_relevance,
        "dharma_alignment": dharma,
        "harmlessness": harmlessness,
        "privacy": privacy,
    }
    min_score = get_settings().audit_min_score
    passed = all(v >= min_score for v in scores.values())
    failed_dims = [name for name, value in scores.items() if value < min_score]

    if not citations:
        passed = False
        failed_dims.append("context_grounding")
        rationale = "No retrieved scripture citations were available to ground the response."
    elif grounding < min_score:
        passed = False
        if "citation_grounding" not in failed_dims:
            failed_dims.append("citation_grounding")
        rationale = "Response did not include enough overlap with retrieved citation concepts to be considered grounded."
    elif query_relevance < min_score:
        passed = False
        if "query_relevance" not in failed_dims:
            failed_dims.append("query_relevance")
        rationale = "Response did not stay close enough to the user's actual dilemma."
    elif passed:
        rationale = "Local G-Eval judge verified citation alignment and Dharma-safe tone."
    else:
        rationale = (
            f"Response did not meet the minimum audit score of {min_score}/5 "
            f"for: {', '.join(f.replace('_', ' ') for f in failed_dims)}."
        )

    revision_hints: list[str] = []
    if not passed:
        if "faithfulness" in failed_dims or "context_grounding" in failed_dims or "citation_grounding" in failed_dims:
            revision_hints.append("Ground each step explicitly in the retrieved scripture citations.")
        if "query_relevance" in failed_dims:
            revision_hints.append("Rewrite the summary around the user's exact dilemma and reuse the important user-topic words.")
        if "harmlessness" in failed_dims:
            revision_hints.append("Remove advice that could cause harm or retaliation.")
        if "dharma_alignment" in failed_dims:
            revision_hints.append("Emphasize compassion, duty, and peaceful resolution.")
        if "privacy" in failed_dims:
            revision_hints.append("Avoid exposing personal identifiers in the guidance.")

    return {
        "scores": scores,
        "passed": passed,
        "minScore": min_score,
        "failedDimensions": failed_dims,
        "groundedTerms": grounded_terms,
        "matchedQueryTerms": matched_query_terms,
        "rationale": rationale,
        "revision_hints": revision_hints,
        "judgeModel": "local-g-eval-heuristic",
        "auditStatus": "ok" if passed else "below_threshold",
    }
