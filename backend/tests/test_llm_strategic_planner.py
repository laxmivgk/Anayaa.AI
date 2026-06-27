import json

import pytest

from app.agents.pipeline_errors import ServiceUnavailableError
from app.agents.workflow import (
    _build_planner_messages,
    _planner_candidate_terms,
    _extract_planner_keywords,
    _parse_llm_planner_response,
    _planner_feedback_summary,
    run_strategic_planner,
)


def test_llm_planner_uses_separate_system_and_user_messages():
    messages = _build_planner_messages(
        "is dropshipping a scam?",
        "is dropshipping scamming?",
        "Found 1 total interactive feedback entries: 1 followed dharma matches, 0 strayed boundaries.",
        "Steadfast Devotion Mode Activated",
        {"total": 1, "followed": 1, "strayed": 0},
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "strategic retrieval planner" in messages[0]["content"]
    assert "Do not include reasoning" in messages[0]["content"]
    assert "keywords, toneMsg" in messages[0]["content"]
    assert "Dilemma:" in messages[1]["content"]
    assert "Optimized query: is dropshipping scamming?" in messages[1]["content"]
    assert "Candidate terms:" in messages[1]["content"]
    assert "Feedback stats: total=1, followed=1, strayed=0." in messages[1]["content"]
    assert "Output only the planner JSON object now." in messages[1]["content"]
    assert "sanitizedDilemma" not in messages[1]["content"]
    assert "optimizedQuery" not in messages[1]["content"]
    assert "requiredOutput" not in messages[1]["content"]


def test_planner_feedback_summary_does_not_include_user_email():
    summary, tone_msg, stats = _planner_feedback_summary(
        [
            {
                "user_email": "lakshmi@example.com",
                "status": "FOLLOWED_DHARMA",
            }
        ]
    )

    assert "lakshmi@example.com" not in summary
    assert tone_msg == "Steadfast Devotion Mode Activated"
    assert stats == {"total": 1, "followed": 1, "strayed": 0}


def test_parse_llm_planner_response_uses_only_llm_keywords():
    planner = _parse_llm_planner_response(
        json.dumps(
            {
                "keywords": ["business", "integrity"],
                "toneMsg": "",
            }
        ),
        model="qwen3:4b",
        history_summary="No prior feedback changes tone.",
    )

    assert planner["plannerEngine"] == "Ollama LLM"
    assert planner["plannerModel"] == "qwen3:4b"
    assert planner["keywords"] == ["business", "integrity"]
    assert planner["reasoning"] == "Search scripture using: business, integrity."
    assert planner["historySummary"] == "No prior feedback changes tone."


def test_parse_llm_planner_response_rejects_missing_keywords():
    with pytest.raises(ValueError, match="retrieval keyword"):
        _parse_llm_planner_response(
            json.dumps(
                {
                    "keywords": [],
                    "toneMsg": "",
                }
            ),
            model="qwen3:4b",
        )


def test_surprise_party_query_has_deterministic_planner_keywords():
    keywords = _extract_planner_keywords(
        "I discovered that a close friend's spouse is planning a surprise party, but the friend "
        "is incredibly stressed and suspects their spouse is having an affair. If I tell the truth, "
        "no surprise. If I lie to protect the surprise, I prolong my friend's acute anxiety."
    )

    assert "anxiety" in keywords
    assert "spouse" in keywords
    assert "surprise" in keywords
    assert "affair" in keywords
    assert "truth" in keywords


def test_planner_candidate_terms_add_moral_hints_without_output_fallback():
    candidates = _planner_candidate_terms(
        "How to be disciplined?",
        "How to be disciplined?",
    )

    assert "discipline" in candidates
    assert "self-control" in candidates
    assert "duty" in candidates


@pytest.mark.anyio
async def test_run_strategic_planner_reports_empty_llm_keywords(monkeypatch):
    captured_request = {}

    class FakePg:
        async def fetch(self, *_args, **_kwargs):
            return []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": json.dumps({"keywords": [], "toneMsg": ""})}}

    class FakeAsyncClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **kwargs):
            captured_request.update(kwargs.get("json") or {})
            return FakeResponse()

    monkeypatch.setattr("app.agents.workflow.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(ServiceUnavailableError, match="retrieval keyword"):
        await run_strategic_planner(
            "friend spouse surprise party affair truth lie anxiety",
            "tester@example.com",
            FakePg(),
        )
    assert captured_request["think"] is False
    assert captured_request["options"]["num_predict"] == 160
