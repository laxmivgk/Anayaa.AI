import pytest

from app.agents.pipeline_messages import (
    build_planner_unavailable_response,
    build_retrieval_unavailable_response,
    build_synthesizer_unavailable_response,
)
from app.observability.g_eval_judge import run_g_eval_judge


def test_planner_unavailable_response_is_explicit():
    result = build_planner_unavailable_response(
        dilemma="Should I tell the truth?",
        request_id="req_test",
        optimizer={"compressedQuery": "truth dilemma", "compressionMetrics": {"ratio": 1.0}},
        eco_breakdown=[],
        power_metrics={},
        detail="planner model missing",
    )

    assert result["status"] == "planner_unavailable"
    assert result["failureReason"] == "planner_service_unavailable"
    assert result["plannerError"] == "planner model missing"
    assert result["moralPathway"] is None
    assert result["retrievalViaMcp"] is False
    assert "planner is unavailable" in result["userMessage"].lower()


def test_retrieval_unavailable_response_remains_explicit():
    result = build_retrieval_unavailable_response(
        dilemma="Should I tell the truth?",
        request_id="req_test",
        keywords=["truth"],
        optimizer={"compressedQuery": "truth dilemma"},
        planner={"reasoning": "Use truth scriptures."},
        retrieval={"mcp": True, "hybridSource": None, "candidates": [], "reranked": []},
        eco_breakdown=[],
        power_metrics={},
        detail="Milvus connection failed",
    )

    assert result["status"] == "retrieval_unavailable"
    assert result["failureReason"] == "scripture_retrieval_service_unavailable"
    assert result["retrievalError"] == "Milvus connection failed"
    assert result["moralPathway"] is None
    assert result["retrievalViaMcp"] is True
    assert "retrieval service is unavailable" in result["userMessage"].lower()


def test_synthesizer_unavailable_response_is_explicit():
    result = build_synthesizer_unavailable_response(
        payload={
            "dilemma": "Should I tell the truth?",
            "keywords": ["truth", "anxiety"],
            "citations": [{"id": "verse-1", "source": "Test"}],
            "retrievalViaMcp": True,
        },
        request_id="req_test",
        eco_breakdown=[],
        power_metrics={},
        detail="generated answer rejected: prompt_like_response",
    )

    assert result["status"] == "synthesizer_unavailable"
    assert result["failureReason"] == "synthesizer_service_unavailable"
    assert result["synthesizerError"] == "generated answer rejected: prompt_like_response"
    assert result["moralPathway"] is None
    assert result["citations"] == [{"id": "verse-1", "source": "Test"}]
    assert "no fallback answer" in result["userMessage"].lower()


def test_synthesizer_rejected_response_is_quality_review_not_unavailable():
    result = build_synthesizer_unavailable_response(
        payload={
            "dilemma": "Should I tell the truth?",
            "keywords": ["truth", "anxiety"],
            "citations": [{"id": "verse-1", "source": "Test"}],
            "retrievalViaMcp": True,
        },
        request_id="req_test",
        eco_breakdown=[],
        power_metrics={},
        detail="LLM synthesis rejected: summary_not_relevant_to_query",
        user_message=(
            "Anayaa generated a draft, but it cannot be shown as final guidance because it drifted from your question "
            "or was not grounded enough in the retrieved scriptures."
        ),
        status="quality_threshold_not_met",
        failure_reason="summary_not_relevant_to_query",
    )

    assert result["status"] == "quality_threshold_not_met"
    assert result["failureReason"] == "summary_not_relevant_to_query"
    assert "unavailable" not in result["userMessage"].lower()
    assert "drifted from your question" in result["userMessage"]


@pytest.mark.anyio
async def test_judge_unavailable_marks_fallback_clearly(monkeypatch):
    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def post(self, *args, **kwargs):
            raise RuntimeError("ollama judge offline")

    monkeypatch.setattr("app.observability.g_eval_judge.httpx.AsyncClient", FailingAsyncClient)

    citations = [
        {
            "id": "gita-2-47",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "translation": "You have a right to perform your duty.",
            "keywords": ["duty", "integrity"],
        },
        {
            "id": "matthew-16-26",
            "faith": "Christianity",
            "source": "Holy Bible: Matthew",
            "translation": "What good is it to gain the world but lose the soul?",
            "keywords": ["wealth", "soul"],
        },
    ]
    pathway = "\n".join(
        [
            "One-line summary: Dropshipping is not automatically a scam, but it must be honest.",
            "Reflection: The pressure is about money and integrity.",
            "Judgement: Choose truthful selling over quick gain.",
            "Next step: Check customer disclosures and refund terms.",
            "Scripture grounding: The Bhagavad Gita points to duty and integrity. Matthew warns that wealth cannot be worth losing the soul.",
        ]
    )

    audit = await run_g_eval_judge("Is dropshipping a scam?", citations, pathway)

    assert audit["judgeFallback"] is True
    assert audit["judgeFailureReason"] == "llm_judge_unavailable"
    assert audit["llmJudgeError"] == "ollama judge offline"
    assert audit["judgeModel"].endswith("-fallback")
    assert audit["auditStatus"].startswith("fallback_")
    assert "groundingContract" in audit
