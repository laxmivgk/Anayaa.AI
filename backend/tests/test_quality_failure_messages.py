from app.agents.pipeline_messages import build_quality_failure_user_message


def test_harmlessness_failure_explains_no_human_override():
    message = build_quality_failure_user_message(
        {
            "scores": {"harmlessness": 2, "faithfulness": 4},
            "failedDimensions": ["harmlessness"],
            "revision_hints": ["Remove advice that could cause harm or retaliation."],
        },
        min_score=3,
    )

    assert message == (
        "Anayaa generated a draft, but it cannot be shown as final guidance because the safety review flagged "
        "possible harmful or retaliatory advice. Use The Interactive Guidance to review the proposed concepts "
        "and scriptures, remove any revenge or retaliation framing, and compile guidance again around lawful "
        "protection, documentation, calm boundaries, and non-retaliation."
    )


def test_quality_failure_points_to_interactive_regeneration():
    message = build_quality_failure_user_message(
        {
            "scores": {"citation_grounding": 2, "faithfulness": 4},
            "failedDimensions": ["citation_grounding"],
        },
        min_score=3,
    )

<<<<<<< HEAD
    assert "The Interactive Guidance" in message
    assert "try again later" not in message


def test_grounding_contract_failure_uses_user_facing_copy():
    message = build_quality_failure_user_message(
        {
            "scores": {
                "faithfulness": 5,
                "citation_grounding": 5,
                "query_relevance": 5,
                "dharma_alignment": 5,
                "harmlessness": 5,
                "privacy": 5,
            },
            "failedDimensions": ["grounding_contract"],
            "revision_hints": [
                "Revise the final answer so Scripture grounding uses at least two retrieved citations, repeats citation terms, stays on the user's topic, and avoids unsupported assumptions."
            ],
        },
        min_score=3,
    )

    assert "retrieved scripture passages" in message
    assert "grounding contract" not in message.lower()
    assert "Revise the final answer" not in message
=======
    assert "Use The Interactive Guidance" in message
    assert "try again later" not in message
>>>>>>> origin/main
