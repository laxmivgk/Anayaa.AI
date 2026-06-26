from app.llm.generator import _build_grounded_fallback_summary
from app.security.harm_normalizer import (
    SAFE_GUIDANCE_TERMS,
    normalize_harmful_concepts,
    normalize_harmful_framing_text,
)


def test_harmful_framing_text_is_normalized_for_synthesis():
    normalized = normalize_harmful_framing_text(
        "How do I retaliate against a partner without revenge?"
    )

    assert "retaliate" not in normalized.lower()
    assert "revenge" not in normalized.lower()
    assert "lawful protection" in normalized
    assert "calm boundaries" in normalized


def test_harmful_concepts_are_replaced_with_safe_guidance_terms():
    concepts = normalize_harmful_concepts(["business", "retaliate", "revenge", "documentation"])

    assert "retaliate" not in concepts
    assert "revenge" not in concepts
    assert "business" in concepts
    assert "documentation" in concepts
    assert all(term in concepts for term in SAFE_GUIDANCE_TERMS[:2])


def test_grounded_fallback_does_not_reinsert_retaliation_wording():
    normalized = normalize_harmful_framing_text(
        "I want guidance because my partner may retaliate against my company."
    )
    summary = _build_grounded_fallback_summary(
        normalized,
        [{"keywords": ["integrity", "business", "protection"]}],
    )

    assert "retaliate" not in summary.lower()
    assert "retaliation" not in summary.lower()
    assert "harmful escalation" in summary
