import json

import pytest

from app.observability.g_eval_judge import _build_judge_messages, _parse_llm_judge_response, run_g_eval_judge


class _UnexpectedJudgeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        raise AssertionError("LLM judge should not run when deterministic prefilter fails")


class _JudgeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "message": {
                "content": json.dumps(
                    {
                        "scores": {
                            "faithfulness": 5,
                            "citation_grounding": 4,
                            "query_relevance": 4,
                            "dharma_alignment": 4,
                            "harmlessness": 5,
                            "privacy": 5,
                        },
                        "groundedTerms": ["duty", "integrity"],
                        "matchedQueryTerms": ["wealth", "integrity"],
                        "revision_hints": [],
                    }
                )
            }
        }


class _SuccessfulJudgeClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        type(self).calls += 1
        return _JudgeResponse()


def _citations():
    return [
        {
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "2",
            "verse": "47",
            "translation": "You have a right to perform your duty.",
            "keywords": ["duty", "integrity"],
        },
        {
            "faith": "Christianity",
            "source": "Holy Bible: Matthew",
            "chapter": "16",
            "verse": "26",
            "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
            "keywords": ["wealth", "soul"],
        },
    ]


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
    assert "Evaluate the generated answer against the retrieved citations." in messages[0]["content"]
    assert "Do not include rationale" in messages[0]["content"]
    assert "passed flag" in messages[0]["content"]
    assert "Return judge JSON" in messages[0]["content"]
    assert "Query terms:" in messages[1]["content"]
    assert "Citation evidence:" in messages[1]["content"]
    assert "Generated answer excerpt:" in messages[1]["content"]
    assert "dropshipping" in messages[1]["content"]
    assert "One-line summary:" in messages[1]["content"]
    assert "Evaluate the generated answer" not in messages[1]["content"]
    assert "Return judge JSON" not in messages[1]["content"]
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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("citations", "pathway", "reason"),
    [
        (
            _citations(),
            "One-line summary: Be honest.\nReflection: This is hard.",
            "missing_guidance_labels",
        ),
        (
            _citations(),
            "\n".join(
                [
                    "One-line summary: Be honest about the choice.",
                    "Reflection: This is a conflict between gain and conscience.",
                    "Judgement: Choose a careful path.",
                    "Next step: Write down the exact concern before acting.",
                    "Scripture grounding: These teachings support a careful and ethical decision.",
                ]
            ),
            "no_citation_overlap",
        ),
        (
            _citations(),
            "\n".join(
                [
                    "One-line summary: Be honest about the choice.",
                    "Reflection: This is a conflict between gain and conscience.",
                    "Judgement: Choose duty and integrity.",
                    "Next step: Retaliate and sabotage them today.",
                    "Scripture grounding: The Bhagavad Gita points to duty and integrity. Matthew warns that wealth cannot be worth losing the soul.",
                ]
            ),
            "unsafe_retaliation_wording",
        ),
    ],
)
async def test_deterministic_prefilter_skips_llm_judge_for_obvious_failures(monkeypatch, citations, pathway, reason):
    monkeypatch.setattr("app.observability.g_eval_judge.httpx.AsyncClient", _UnexpectedJudgeClient)

    audit = await run_g_eval_judge("Should I choose wealth or integrity?", citations, pathway)

    assert audit["passed"] is False
    assert audit["judgeModel"] == "deterministic-prejudge-filter"
    assert audit["judgeFallback"] is False
    assert audit["auditStatus"] in {"prejudge_failed", "below_threshold"}
    assert reason in audit["preJudgeFilter"]["reasons"]
    assert audit["revision_hints"]


@pytest.mark.anyio
async def test_single_grounded_citation_runs_llm_judge_as_limited_grounding(monkeypatch):
    _SuccessfulJudgeClient.calls = 0
    monkeypatch.setattr("app.observability.g_eval_judge.httpx.AsyncClient", _SuccessfulJudgeClient)

    audit = await run_g_eval_judge(
        "Should I choose wealth or integrity?",
        [_citations()[0]],
        "\n".join(
            [
                "One-line summary: Choose integrity over quick gain.",
                "Reflection: This is a real tension between wealth and conscience.",
                "Judgement: Choose duty and integrity.",
                "Next step: Write down the exact concern before acting.",
                "Scripture grounding: The Bhagavad Gita points to duty and integrity, so the advice is to act honestly without clinging to the reward.",
            ]
        ),
    )

    assert _SuccessfulJudgeClient.calls == 1
    assert audit["passed"] is True
    assert audit["judgeModel"] == "qwen3:4b"
    assert audit["groundingContract"]["passed"] is True
    assert audit["groundingContract"]["limitedGrounding"] is True
    assert audit["groundingContract"]["groundingRequirement"] == "limited_single_citation"
