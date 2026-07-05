from app.api.routes.system import (
    _hitl_compile_audit_query,
    _hitl_compile_synthesis_tone,
    _should_retry_hitl_compile,
)


def test_hitl_compile_audit_query_keeps_original_dilemma_before_selected_concepts():
    query = _hitl_compile_audit_query(
        "How one can be disciplined?",
        ["self-control", "duty", "habit"],
    )

    assert query.startswith("How one can be disciplined?")
    assert "Selected concepts: self-control, duty, habit" in query


def test_hitl_compile_audit_query_dedupes_concepts_already_in_dilemma():
    query = _hitl_compile_audit_query(
        "How one can be disciplined?",
        ["disciplined", "discipline", "discipline"],
    )

    assert query == "How one can be disciplined?"


def test_hitl_compile_audit_query_normalizes_harmful_framing():
    query = _hitl_compile_audit_query(
        "How do I retaliate without revenge?",
        ["retaliate", "documentation"],
    )

    assert "retaliate" not in query.lower()
    assert "revenge" not in query.lower()
    assert "lawful protection" in query
    assert "documentation" in query


def test_hitl_compile_synthesis_tone_carries_selected_concepts_and_citation_requirement():
    tone = _hitl_compile_synthesis_tone("Calm", ["trust", "confidentiality"])

    assert "Calm" in tone
    assert "trust, confidentiality" in tone
    assert "name at least two selected scripture sources exactly" in tone


def test_hitl_compile_retry_targets_grounding_failures_with_two_citations():
    audit = {
        "passed": False,
        "failedDimensions": ["grounding_contract"],
        "groundingContract": {"failedChecks": ["citationTermsInScriptureGrounding"]},
    }
    citations = [{"id": "a"}, {"id": "b"}]

    assert _should_retry_hitl_compile(audit, citations) is True


def test_hitl_compile_retry_targets_faithfulness_failures_with_two_citations():
    audit = {
        "passed": False,
        "scores": {"faithfulness": 2, "citation_grounding": 4},
        "minScore": 3,
        "failedDimensions": [],
    }
    citations = [{"id": "a"}, {"id": "b"}]

    assert _should_retry_hitl_compile(audit, citations) is True


def test_hitl_compile_retry_does_not_override_safety_or_single_citation_failures():
    safety_audit = {"passed": False, "failedDimensions": ["harmlessness"]}
    grounding_audit = {"passed": False, "failedDimensions": ["citation_grounding"]}

    assert _should_retry_hitl_compile(safety_audit, [{"id": "a"}, {"id": "b"}]) is False
    assert _should_retry_hitl_compile(grounding_audit, [{"id": "a"}]) is False
