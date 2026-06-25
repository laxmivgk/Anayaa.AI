from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, rewrite_malformed_query


def test_who_am_i_rewrites_to_dharma_dilemma():
    result = rewrite_malformed_query("Who am I?")

    assert result["queryRewriteApplied"] is True
    assert "existential_identity_as_dharma_dilemma" in result["queryRewriteRules"]
    assert "identity" in result["rewrittenQuery"]
    assert "soul" in result["rewrittenQuery"]
    assert "duty" in result["rewrittenQuery"]
    assert "authentic path" in result["rewrittenQuery"]
    assert "dharma dilemma" in result["rewrittenQuery"]


def test_any_short_query_is_treated_as_dharma_dilemma_without_lost_original():
    result = rewrite_malformed_query("money")

    assert result["originalQuery"] == "money"
    assert result["queryRewriteApplied"] is True
    assert "assumed_dharma_dilemma" in result["queryRewriteRules"]
    assert "dharma dilemma" in result["rewrittenQuery"]
    assert "money" in result["rewrittenQuery"]
    assert "Without inventing missing facts" in result["rewrittenQuery"]


def test_non_moral_looking_query_is_still_framed_as_dharma_dilemma():
    result = rewrite_malformed_query("weather today")

    assert result["queryRewriteApplied"] is True
    assert "assumed_dharma_dilemma" in result["queryRewriteRules"]
    assert "weather today" in result["rewrittenQuery"]
    assert "wisest, kindest, most truthful" in result["rewrittenQuery"]


def test_existential_identity_rewrite_feeds_planner_keywords():
    rewritten = rewrite_malformed_query("Who am I?")["rewrittenQuery"]
    keywords = _extract_planner_keywords(rewritten)

    assert "identity" in keywords
    assert "purpose" in keywords


def test_identity_retrieval_accepts_self_and_soul_scripture_context():
    reranked = [
        {
            "score": 92,
            "verse": {
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
                "context": "On integrity, soul, identity, and moral value beyond worldly gain.",
                "source": "Holy Bible: Matthew",
                "keywords": ["integrity", "soul", "identity", "morality", "wealth"],
            },
        },
        {
            "score": 88,
            "verse": {
                "translation": "One must elevate oneself by one's own mind, and not degrade oneself.",
                "context": "On self-reliance, mind, growth, and inner responsibility.",
                "source": "Bhagavad Gita",
                "keywords": ["mind", "self-reliance", "growth", "strength"],
            },
        },
    ]

    assert _retrieval_matches_query(rewrite_malformed_query("Who am I?")["rewrittenQuery"], reranked)
