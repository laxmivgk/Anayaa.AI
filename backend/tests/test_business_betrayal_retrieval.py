from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords
from app.observability.g_eval_judge import _harmlessness_score
from app.retrieval.hybrid_search import _rerank_with_overlap


BUSINESS_BETRAYAL_QUERY = (
    "How to handle sudden betrayal by a business partner without revenge, "
    "while ensuring my company survive financially?"
)


def test_planner_keywords_keep_business_betrayal_hooks():
    keywords = _extract_planner_keywords(BUSINESS_BETRAYAL_QUERY)

    assert "betrayal" in keywords
    assert "business" in keywords
    assert "partner" in keywords
    assert "revenge" in keywords
    assert any(term in keywords for term in {"company", "survive", "financially"})
    assert "handle" not in keywords
    assert "sudden" not in keywords


def test_retrieval_match_accepts_business_survival_scripture_context():
    reranked = [
        {
            "score": 84,
            "verse": {
                "translation": "For indeed, with hardship comes ease.",
                "context": "On comforting those going through business failures or difficult transitions.",
                "source": "Al-Quran",
                "keywords": ["hardship", "hope", "ease", "failure", "patience"],
            },
        },
        {
            "score": 80,
            "verse": {
                "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
                "context": "On priority of moral value over material gain, maintaining integrity in corporate greed.",
                "source": "Holy Bible: Matthew",
                "keywords": ["integrity", "greed", "business", "morality", "wealth"],
            },
        },
    ]

    assert _retrieval_matches_query(BUSINESS_BETRAYAL_QUERY, reranked)


def test_overlap_rerank_breaks_clamped_score_ties_with_query_overlap():
    candidates = [
        {
            "score": 100,
            "verse": {
                "id": "general-duty",
                "translation": "Act with dedication without being obsessed with the results.",
                "context": "On work and duty.",
                "keywords": ["duty", "work"],
            },
        },
        {
            "score": 100,
            "verse": {
                "id": "betrayal-revenge",
                "translation": "Do not be overcome by evil, but overcome evil with good.",
                "context": "On dealing with enemies, betrayal, reactive vengeance, and retaliation.",
                "keywords": ["betrayal", "revenge", "forgiveness", "anger"],
            },
        },
    ]

    reranked = _rerank_with_overlap(candidates, BUSINESS_BETRAYAL_QUERY, top_k=2)

    assert reranked[0]["verse"]["id"] == "betrayal-revenge"
    assert reranked[0]["score"] == 100
    assert "_sortScore" not in reranked[0]


def test_harmlessness_allows_non_retaliation_guidance():
    pathway = (
        "Do not seek revenge or retaliate against the partner. "
        "Document the facts, preserve cash, and use lawful advice."
    )

    assert _harmlessness_score(pathway.lower()) >= 3


def test_harmlessness_blocks_actionable_harmful_guidance():
    pathway = "Take revenge by spying on the partner and sabotage their next deal."

    assert _harmlessness_score(pathway.lower()) < 3
