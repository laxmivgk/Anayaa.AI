from app.observability.grounding_contract import apply_grounding_contract, evaluate_grounding_contract


def _citations():
    return [
        {
            "id": "gita-2-47",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "translation": "You have a right to perform your duty, but not to the fruits of action.",
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


def test_grounding_contract_passes_when_final_answer_proves_citation_and_query_grounding():
    result = evaluate_grounding_contract(
        "Is dropshipping a scam if I need money?",
        _citations(),
        "\n".join(
            [
                "One-line summary: Dropshipping is not automatically a scam, but money pressure cannot justify misleading customers.",
                "Reflection: The conflict is between financial need and honest responsibility.",
                "Judgement: Choose transparent selling and fair customer treatment.",
                "Next step: Check fulfillment reliability and refund terms before selling.",
                "Scripture grounding: The Bhagavad Gita points to duty and integrity rather than attachment to profit. Matthew warns that wealth cannot be worth losing the soul.",
            ]
        ),
    )

    assert result["passed"] is True
    assert result["checks"] == {
        "minimumTwoCitations": True,
        "scriptureGroundingSectionPresent": True,
        "citationTermsInScriptureGrounding": True,
        "answerUsesUserTopicTerms": True,
        "noUnsupportedAssumptions": True,
    }
    assert result["citationCount"] == 2
    assert result["groundedCitationCount"] == 2
    assert result["groundedCitationIds"] == ["gita-2-47", "matthew-16-26"]
    assert {"dropshipping", "scam"} <= set(result["matchedQueryTerms"])


def test_grounding_contract_fails_without_two_grounded_citations_or_user_topic_terms():
    result = evaluate_grounding_contract(
        "Is dropshipping a scam?",
        [_citations()[0]],
        "\n".join(
            [
                "One-line summary: This is a broad ethical issue.",
                "Reflection: Stay thoughtful.",
                "Judgement: Be careful.",
                "Next step: Think about it.",
                "Scripture grounding: Be ethical.",
            ]
        ),
    )

    assert result["passed"] is False
    assert "minimumTwoCitations" in result["failedChecks"]
    assert "citationTermsInScriptureGrounding" in result["failedChecks"]
    assert "answerUsesUserTopicTerms" in result["failedChecks"]


def test_grounding_contract_fails_unsupported_assumptions():
    result = evaluate_grounding_contract(
        "Is dropshipping a scam?",
        _citations(),
        "\n".join(
            [
                "One-line summary: Dropshipping is always a scam.",
                "Reflection: You clearly lost money already.",
                "Judgement: Stop immediately.",
                "Next step: Avoid it.",
                "Scripture grounding: The Bhagavad Gita points to duty and integrity. Matthew warns that wealth cannot be worth losing the soul.",
            ]
        ),
    )

    assert result["passed"] is False
    assert result["checks"]["noUnsupportedAssumptions"] is False
    assert result["unsupportedAssumptions"]


def test_grounding_contract_matches_safe_query_term_variants():
    result = evaluate_grounding_contract(
        "How to be disciplined?",
        [
            {
                "id": "gita-2-47",
                "faith": "Hinduism",
                "source": "Bhagavad Gita",
                "translation": "You have a right to perform your duty.",
                "keywords": ["duty", "discipline"],
            },
            {
                "id": "gita-6-5",
                "faith": "Hinduism",
                "source": "Bhagavad Gita",
                "translation": "Let a person lift oneself by oneself.",
                "keywords": ["self-control", "mind"],
            },
        ],
        "\n".join(
            [
                "Summary: You can build discipline by doing one duty steadily.",
                "Reflection: Discipline takes repeated effort.",
                "Judgement: Choose self-control and duty.",
                "Next step: Write one task and protect ten quiet minutes for it.",
                "Scripture grounding: The Bhagavad Gita points to duty and discipline. The Bhagavad Gita also supports self-control of the mind.",
            ]
        ),
    )

    assert result["passed"] is True
    assert result["checks"]["answerUsesUserTopicTerms"] is True
    assert result["matchedQueryTerms"] == ["disciplined"]


def test_apply_grounding_contract_forces_failed_audit_when_contract_fails():
    audit = {
        "scores": {
            "faithfulness": 5,
            "citation_grounding": 5,
            "query_relevance": 5,
            "dharma_alignment": 5,
            "harmlessness": 5,
            "privacy": 5,
        },
        "passed": True,
        "failedDimensions": [],
        "revision_hints": [],
        "auditStatus": "ok",
    }

    updated = apply_grounding_contract(
        audit,
        "Is dropshipping a scam?",
        [_citations()[0]],
        "One-line summary: This is generic.\nScripture grounding: Be ethical.",
    )

    assert updated["passed"] is False
    assert updated["llmJudgePassed"] is True
    assert "grounding_contract" in updated["failedDimensions"]
    assert updated["groundingContract"]["passed"] is False
    assert "LLM score check passed" in updated["rationale"]
    assert updated["revision_hints"]
