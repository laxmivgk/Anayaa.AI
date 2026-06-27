from app.api.routes.system import _hitl_compile_audit_query


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
