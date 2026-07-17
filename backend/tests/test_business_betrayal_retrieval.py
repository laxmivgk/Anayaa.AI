from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords
from app.llm.generator import SYNTHESIS_SYSTEM_PROMPT, _build_synthesis_prompt, _synthesis_rejection_reason
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


def test_betrayal_revenge_prompt_keeps_next_step_calm_and_proportionate():
    prompt = _build_synthesis_prompt(
        "Someone I trusted deeply betrayed me and is spreading lies. I feel consumed by anger and hatred. "
        "Should I seek revenge or try to forgive them?",
        [
            {
                "faith": "Christianity",
                "source": "Holy Bible: Romans",
                "chapter": "12",
                "verse": "21",
                "translation": "Do not be overcome by evil, but overcome evil with good.",
                "keywords": ["betrayal", "retaliation", "forgiveness", "anger"],
            },
            {
                "faith": "Islam",
                "source": "Al-Quran",
                "chapter": "5",
                "verse": "8",
                "translation": "Be persistently standing firm in justice.",
                "keywords": ["justice", "truth", "integrity"],
            },
        ],
        "",
    )

    assert "not to retaliate today" in SYNTHESIS_SYSTEM_PROMPT
    assert "Plain explanation questions about anger or judgement are not betrayal/revenge dilemmas" in SYNTHESIS_SYSTEM_PROMPT
    assert "forgiveness can be a later process" in SYNTHESIS_SYSTEM_PROMPT
    assert "do not frame protection as the opposite of forgiveness" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not say the user should choose lawful protection rather than trying to forgive" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not use the phrase lawful protection for ordinary lies or betrayal" in SYNTHESIS_SYSTEM_PROMPT
    assert "speak once calmly when safe" in SYNTHESIS_SYSTEM_PROMPT
    assert "If they do not listen" in SYNTHESIS_SYSTEM_PROMPT
    assert "set a clear boundary" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not make law enforcement or authority escalation the default first step" in SYNTHESIS_SYSTEM_PROMPT
    assert "only if the lies affect safety, work, school, housing, or reputation" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not mention legal action unless" in SYNTHESIS_SYSTEM_PROMPT
    assert "not to retaliate today" not in prompt


def test_betrayal_revenge_summary_accepts_calm_boundary_wording():
    pathway = (
        "Summary: Do not retaliate today; protect yourself with truth and calm boundaries. "
        "Reflection: Anger after betrayal is understandable, but it does not need to choose revenge. "
        "Judgement: The wiser path is non-retaliation, truthful protection, and allowing forgiveness to be a later process. "
        "Next step: Write down what was said, when it happened, who heard it, and any evidence that exists. "
        "Scripture grounding: Romans teaches not to be overcome by evil, but to overcome evil with good. "
        "Dhammapada teaches that hatred is not ended by hatred."
    )

    assert (
        _synthesis_rejection_reason(
            "I trusted one person, now betrayed me and is spreading lies. I feel anger and hatred. "
            "Should I seek revenge or try to forgive them?",
            [
                {
                    "source": "Holy Bible: Romans",
                    "faith": "Christianity",
                    "keywords": ["betrayal", "retaliation", "forgiveness", "anger"],
                },
                {
                    "source": "Dhammapada",
                    "faith": "Buddhism",
                    "keywords": ["hatred", "forgiveness", "compassion"],
                },
            ],
            pathway,
        )
        == ""
    )


def test_betrayal_revenge_summary_accepts_scripture_concept_grounding():
    pathway = (
        "Summary: Do not retaliate today; protect yourself with truth and calm boundaries. "
        "Reflection: Feeling hurt is understandable, but revenge would keep the wound active. "
        "Judgement: The wiser path is truthful protection now, with forgiveness left as a later process. "
        "Next step: Write down what was said, when it happened, who heard it, and any evidence that exists. "
        "Scripture grounding: Romans points toward overcoming evil with good. "
        "The Buddhist teaching points away from returning hostility with more hostility."
    )

    assert (
        _synthesis_rejection_reason(
            "I trusted one person, now betrayed me and is spreading lies. I feel anger and hatred. "
            "Should I seek revenge or try to forgive them?",
            [
                {
                    "id": "c3",
                    "source": "Holy Bible: Romans",
                    "faith": "Christianity",
                    "keywords": ["betrayal", "retaliation", "forgiveness", "anger"],
                },
                {
                    "id": "b2",
                    "source": "Dhammapada",
                    "faith": "Buddhism",
                    "keywords": ["hatred", "forgiveness", "compassion"],
                },
            ],
            pathway,
        )
        == ""
    )


def test_harmlessness_allows_descriptive_retaliated_wording():
    pathway = "Reflection: The partner retaliated after the disagreement, so respond with documentation."

    assert _harmlessness_score(pathway.lower()) >= 3


def test_harmlessness_blocks_actionable_harmful_guidance():
    pathway = "Take revenge by spying on the partner and sabotage their next deal."

    assert _harmlessness_score(pathway.lower()) < 3
