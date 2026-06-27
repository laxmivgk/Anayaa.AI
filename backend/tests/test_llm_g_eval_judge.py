import json

from app.observability.g_eval_judge import _build_judge_messages, _parse_llm_judge_response


def test_llm_judge_uses_separate_system_and_user_messages():
    messages = _build_judge_messages(
        "is dropshipping a scam?",
        [
            {
                "faith": "Christianity",
                "source": "Holy Bible: Matthew",
                "chapter": "16",
                "verse": "26",
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
                "keywords": ["integrity", "business"],
            }
        ],
        "One-line summary: Dropshipping is not automatically a scam.",
        3,
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "independent evaluation judge" in messages[0]["content"]
    assert "Do not include rationale" in messages[0]["content"]
    assert "passed flag" in messages[0]["content"]
    assert "Query terms:" in messages[1]["content"]
    assert "Citation evidence:" in messages[1]["content"]
    assert "Generated answer excerpt:" in messages[1]["content"]
    assert "dropshipping" in messages[1]["content"]
    assert "One-line summary:" in messages[1]["content"]
    assert "userQuery" not in messages[1]["content"]
    assert "scoreScale" not in messages[1]["content"]


def test_parse_llm_judge_response_normalizes_scores_and_passed_flag():
    audit = _parse_llm_judge_response(
        json.dumps(
            {
                "scores": {
                    "faithfulness": 5,
                    "citation_grounding": 4,
                    "query_relevance": 4,
                    "dharma_alignment": 3,
                    "harmlessness": 5,
                    "privacy": 5,
                },
                "groundedTerms": ["integrity", "business"],
                "matchedQueryTerms": ["dropshipping", "scam"],
                "revision_hints": [],
            }
        ),
        min_score=3,
        model="qwen3:4b",
    )

    assert audit["passed"] is True
    assert audit["judgeModel"] == "qwen3:4b"
    assert audit["auditStatus"] == "ok"
    assert audit["failedDimensions"] == []
    assert audit["groundedTerms"] == ["integrity", "business"]
    assert audit["rationale"] == "LLM judge passed."


def test_parse_llm_judge_response_does_not_trust_incorrect_passed_flag():
    audit = _parse_llm_judge_response(
        json.dumps(
            {
                "scores": {
                    "faithfulness": 5,
                    "citation_grounding": 2,
                    "query_relevance": 4,
                    "dharma_alignment": 4,
                    "harmlessness": 5,
                    "privacy": 5,
                },
            }
        ),
        min_score=3,
        model="qwen3:4b",
    )

    assert audit["passed"] is False
    assert audit["auditStatus"] == "below_threshold"
    assert audit["failedDimensions"] == ["citation_grounding"]
    assert audit["revision_hints"]
