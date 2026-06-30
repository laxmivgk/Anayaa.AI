from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, rewrite_malformed_query


def test_parent_child_worry_query_gets_generic_competing_duty_frame():
    result = rewrite_malformed_query("Should I worry about my parents or my kids?")

    assert result["originalQuery"] == "Should I worry about my parents or my kids?"
    assert result["queryRewriteApplied"] is True
    assert "terse_competing_duty_as_dharma_dilemma" in result["queryRewriteRules"]
    assert "parents or my kids" in result["rewrittenQuery"]
    assert "competing duties" in result["rewrittenQuery"]
    assert "Without assuming missing facts" in result["rewrittenQuery"]
    assert "who needs help most" in result["rewrittenQuery"]


def test_terse_competing_duty_examples_use_same_rewrite_rule():
    examples = [
        "parents or kids?",
        "job or family?",
        "truth or peace?",
        "help friend or protect myself?",
    ]

    for query in examples:
        result = rewrite_malformed_query(query)

        assert result["queryRewriteApplied"] is True
        assert "terse_competing_duty_as_dharma_dilemma" in result["queryRewriteRules"]
        assert query.strip(" ?") in result["rewrittenQuery"]
        assert "competing duties, relationships, values, needs, or responsibilities" in result["rewrittenQuery"]


def test_terse_competing_duty_query_feeds_planner_keywords():
    rewritten = rewrite_malformed_query("Should I worry about my parents or my kids?")["rewrittenQuery"]
    keywords = _extract_planner_keywords(rewritten)

    assert "parents" in keywords
    assert "kids" in keywords
    assert "duty" in keywords


def test_terse_competing_duty_retrieval_accepts_related_context():
    rewritten = rewrite_malformed_query("parents or kids?")["rewrittenQuery"]
    reranked = [
        {
            "score": 91,
            "verse": {
                "translation": "Let your father and your mother be glad.",
                "context": "On respect, gratitude, and responsibility toward parents and elders.",
                "source": "Proverbs",
                "keywords": ["parents", "respect", "gratitude", "responsibility"],
            },
        },
        {
            "score": 89,
            "verse": {
                "translation": "Children are entrusted to the care and protection of the family.",
                "context": "On compassion, duty, protection, and care for children and dependents.",
                "source": "Family ethics corpus",
                "keywords": ["children", "care", "duty", "compassion", "protection"],
            },
        },
    ]

    assert _retrieval_matches_query(rewritten, reranked)
