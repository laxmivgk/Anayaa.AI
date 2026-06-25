from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, rewrite_malformed_query
from app.llm.generator import (
    _build_grounded_fallback_summary,
    _business_integrity_answer_drifted,
    _build_synthesis_prompt,
    _is_summary_relevant,
    _query_focus_terms,
)


TYPO_QUERY = "Is dropshhipping scamming"


def test_dropshipping_typo_is_normalized_before_dharma_frame():
    result = rewrite_malformed_query(TYPO_QUERY)

    assert "dropshipping" in result["rewrittenQuery"]
    assert "dropshhipping" not in result["rewrittenQuery"]
    assert "drops+h+ipping" in result["queryRewriteRules"]


def test_dropshipping_query_focus_ignores_internal_dharma_frame_words():
    rewritten = rewrite_malformed_query(TYPO_QUERY)["rewrittenQuery"]

    assert _query_focus_terms(rewritten)[:2] == ["dropshipping", "scamming"]


def test_dropshipping_keywords_and_retrieval_match_business_integrity_context():
    rewritten = rewrite_malformed_query(TYPO_QUERY)["rewrittenQuery"]
    keywords = _extract_planner_keywords(rewritten)
    reranked = [
        {
            "score": 90,
            "verse": {
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
                "context": "On integrity in business, wealth, honesty, and avoiding scams.",
                "source": "Holy Bible: Matthew",
                "keywords": ["integrity", "business", "morality", "wealth"],
            },
        }
    ]

    assert "dropshipping" in keywords
    assert "scamming" in keywords
    assert _retrieval_matches_query(rewritten, reranked)


def test_dropshipping_answer_relevance_accepts_business_integrity_response():
    rewritten = rewrite_malformed_query(TYPO_QUERY)["rewrittenQuery"]
    pathway = (
        "One-line summary: Dropshipping is not automatically scamming, but it becomes wrong when it hides risk, "
        "misleads customers, or sells without responsibility.\n"
        "Reflection: The business question is about honesty and trust.\n"
        "Judgement: Choose transparent selling over quick profit.\n"
        "Next step: Check supplier reliability, shipping times, refund terms, and customer disclosures before selling.\n"
        "Scripture grounding: The retrieved scriptures point toward integrity and business morality."
    )

    assert _is_summary_relevant(rewritten, [{"keywords": ["integrity", "business", "wealth"]}], pathway)


def test_dropshipping_fallback_is_business_specific_without_focus_phrase():
    rewritten = rewrite_malformed_query(TYPO_QUERY)["rewrittenQuery"]
    summary = _build_grounded_fallback_summary(
        rewritten,
        [{"keywords": ["integrity", "business", "wealth"]}],
    )

    assert "Focus on the real question" not in summary
    assert "business-integrity question" in summary
    assert "supplier reliability" in summary
    assert "customer disclosures" in summary


def test_dropshipping_prompt_blocks_unsupported_business_assumptions():
    rewritten = rewrite_malformed_query(TYPO_QUERY)["rewrittenQuery"]
    prompt = _build_synthesis_prompt(
        rewritten,
        [
            {
                "faith": "Christianity",
                "source": "Holy Bible: Matthew",
                "chapter": "16",
                "verse": "26",
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
            }
        ],
        "",
    )

    assert "not automatically scamming" in prompt
    assert "Do not assume the user has invested money" in prompt
    assert "Do not name specific commercial platforms" in prompt


def test_dropshipping_drift_guard_catches_invented_investment_and_platforms():
    pathway = (
        "Reflection: You might be feeling uncertain after investing time and money into dropshipping.\n"
        "Judgement: Consider benefits and drawbacks before commitments.\n"
        "Next step: Record losses and research Shopify or Oberlo.\n"
        "Scripture grounding: Matthew warns against material gain."
    )

    assert _business_integrity_answer_drifted(pathway)


def test_dropshipping_drift_guard_accepts_direct_dharma_answer():
    pathway = (
        "One-line summary: Dropshipping is not automatically scamming, but it becomes wrong when it misleads customers.\n"
        "Reflection: The business question is about honesty and trust.\n"
        "Judgement: Choose transparent selling and accountability.\n"
        "Next step: Check supplier reliability, shipping times, refund terms, and customer disclosures before selling.\n"
        "Scripture grounding: The retrieved scriptures point toward integrity and business morality."
    )

    assert not _business_integrity_answer_drifted(pathway)
