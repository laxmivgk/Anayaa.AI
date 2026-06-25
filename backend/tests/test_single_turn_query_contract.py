from app.api.routes.query import QueryBody


def test_query_body_does_not_accept_previous_context_for_now():
    assert "previousContext" not in QueryBody.model_fields
    assert "query" in QueryBody.model_fields
    assert "preSynthesisVerification" in QueryBody.model_fields
