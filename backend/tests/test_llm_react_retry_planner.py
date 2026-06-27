import json

import pytest

from app.agents.adk_workflow import (
    _build_retry_planner_messages,
    _parse_retry_plan_response,
    _react_reason_impl,
)


def test_retry_planner_uses_separate_system_and_user_messages():
    messages = _build_retry_planner_messages(
        {
            "reactLoopLimit": 2,
            "keywords": ["dropshipping", "scam"],
            "contextSufficient": True,
            "auditScores": {
                "failedDimensions": ["citation_grounding"],
                "revision_hints": ["Ground the response in retrieved citations."],
                "matchedQueryTerms": ["dropshipping"],
                "groundedTerms": ["business"],
            },
        },
        "is dropshipping a scam?",
        2,
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "retry planner" in messages[0]["content"]
    assert "Do not include reasoning" in messages[0]["content"]
    assert "action, retryQuery, focusKeywords" in messages[0]["content"]
    payload = json.loads(messages[1]["content"])
    assert payload["dilemma"] == "is dropshipping a scam?"
    assert payload["failedDimensions"] == ["citation_grounding"]
    assert "Return only valid compact JSON" not in messages[1]["content"]


def test_parse_retry_plan_response_accepts_retry_plan():
    plan = _parse_retry_plan_response(
        json.dumps(
            {
                "action": "retry",
                "retryQuery": "is dropshipping a scam business integrity honesty",
                "focusKeywords": ["business", "integrity", "honesty"],
            }
        )
    )

    assert plan["action"] == "retry"
    assert plan["retryQuery"].startswith("is dropshipping")
    assert plan["focusKeywords"] == ["business", "integrity", "honesty"]
    assert plan["reason"] == "Retry with focused retrieval."


def test_parse_retry_plan_response_rejects_retry_without_query():
    with pytest.raises(ValueError, match="retryQuery"):
        _parse_retry_plan_response(
            json.dumps(
                {
                    "action": "retry",
                    "focusKeywords": ["business"],
                }
            )
        )


@pytest.mark.anyio
async def test_retry_planner_failure_finalizes_without_deterministic_fallback(monkeypatch):
    async def fail_retry_plan(*_args, **_kwargs):
        raise RuntimeError("retry planner offline")

    class FakeCtx:
        state = {"request_id": "req_test", "dilemma": "is dropshipping a scam?"}

    monkeypatch.setattr("app.agents.adk_workflow._plan_react_retry_with_llm", fail_retry_plan)

    result = await _react_reason_impl(
        FakeCtx(),
        {
            "dilemma": "is dropshipping a scam?",
            "reactTurn": 1,
            "keywords": ["dropshipping", "scam"],
            "contextSufficient": False,
            "reactLoopLog": [],
        },
    )

    assert result["skipRetryRetrieval"] is True
    assert result["reactRetryPlanError"] == "retry planner offline"
    assert result["reactSearchQuery"] == "is dropshipping a scam?"
    assert "deterministic retry fallback" in result["reactReasoning"]
