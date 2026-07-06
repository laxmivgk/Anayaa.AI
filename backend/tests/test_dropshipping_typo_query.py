from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, rewrite_malformed_query
from app.llm.generator import (
    _business_integrity_answer_drifted,
    _build_synthesis_prompt,
    _is_business_integrity_dilemma,
    _is_summary_relevant,
    _query_focus_terms,
    _synthesis_rejection_reason,
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
        "Scripture grounding: Matthew supports guidance rooted in integrity and business morality."
    )

    assert _is_summary_relevant(rewritten, [{"keywords": ["integrity", "business", "wealth"]}], pathway)


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


def test_general_business_integrity_prompt_does_not_force_dropshipping_terms():
    dilemma = (
        "I feel tempted to cut ethical corners at my business because my competitors are getting incredibly wealthy "
        "doing so. Should I pursue wealth at all costs or maintain my integrity?"
    )
    prompt = _build_synthesis_prompt(
        dilemma,
        [
            {
                "faith": "Christianity",
                "source": "Holy Bible: Matthew",
                "chapter": "16",
                "verse": "26",
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
                "keywords": ["integrity", "greed", "business", "wealth"],
            }
        ],
        "",
    )

    assert _is_business_integrity_dilemma(dilemma)
    assert "wealth-versus-integrity conflict" in prompt
    assert "pursuing wealth is not wrong by itself" in prompt
    assert "answer directly whether the business model is automatically wrong" not in prompt
    assert "not automatically scamming" not in prompt


def test_general_business_integrity_answer_is_not_rejected_for_missing_dropshipping():
    dilemma = (
        "I feel tempted to cut ethical corners at my business because my competitors are getting incredibly wealthy "
        "doing so. Should I pursue wealth at all costs or maintain my integrity?"
    )
    citations = [
        {
            "source": "Holy Bible: Matthew",
            "keywords": ["integrity", "greed", "business", "wealth"],
        },
        {
            "source": "Isha Upanishad",
            "keywords": ["greed", "wealth", "honesty"],
        },
    ]
    pathway = (
        "One-line summary: Pursue wealth only in ways that protect your integrity.\n"
        "Reflection: The pressure is about business, competitors, wealth, and ethical corners.\n"
        "Judgement: Maintaining integrity is wiser than copying dishonest competitors.\n"
        "Next step: Name the exact corner you feel tempted to cut, then write an honest alternative.\n"
        "Scripture grounding: Holy Bible: Matthew warns that wealth is not worth losing integrity. "
        "Isha Upanishad cautions against greed and points toward honest enjoyment."
    )

    assert _synthesis_rejection_reason(dilemma, citations, pathway) == ""


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
        "Scripture grounding: Matthew supports guidance rooted in integrity and business morality."
    )

    assert not _business_integrity_answer_drifted(pathway)
