from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, rewrite_malformed_query
from app.llm.generator import _build_synthesis_prompt


JOB_CHOICE_QUERY = (
    "while looking for a job can I look for a job which fulfills our needs "
    "or select a job just randomly?"
)


def test_job_choice_query_is_not_treated_as_follow_up():
    result = rewrite_malformed_query(JOB_CHOICE_QUERY, previous_context={"question": "Who am I?"})

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]


def test_job_choice_query_preserves_livelihood_keywords_after_dharma_frame():
    rewritten = rewrite_malformed_query(JOB_CHOICE_QUERY)["rewrittenQuery"]
    keywords = _extract_planner_keywords(rewritten)

    assert "job" in keywords
    assert "needs" in keywords
    assert "randomly" in keywords
    assert "asking" not in keywords
    assert "provided" not in keywords


def test_job_choice_retrieval_accepts_duty_and_career_scriptures():
    rewritten = rewrite_malformed_query(JOB_CHOICE_QUERY)["rewrittenQuery"]
    reranked = [
        {
            "score": 90,
            "verse": {
                "translation": (
                    "You have a right to perform your prescribed duties, but you are not entitled "
                    "to the fruits of your actions."
                ),
                "context": "On decision paralysis, anxiety about outcomes, and working with dedication.",
                "source": "Bhagavad Gita",
                "keywords": ["duty", "karma", "work", "career", "choice"],
            },
        },
        {
            "score": 88,
            "verse": {
                "translation": "One must elevate oneself by one's own mind, and not degrade oneself.",
                "context": "On self-reliance and responsibility.",
                "source": "Bhagavad Gita",
                "keywords": ["mind", "responsibility", "growth"],
            },
        },
    ]

    assert _retrieval_matches_query(rewritten, reranked)


def test_job_choice_synthesis_prompt_does_not_expose_internal_dharma_frame():
    rewritten = rewrite_malformed_query(JOB_CHOICE_QUERY)["rewrittenQuery"]
    prompt = _build_synthesis_prompt(
        rewritten,
        [
            {
                "faith": "Hinduism",
                "source": "Bhagavad Gita",
                "chapter": "2",
                "verse": "47",
                "translation": "You have a right to perform your prescribed duties.",
            }
        ],
        "",
    )

    dilemma_section = prompt.split("Dilemma:\n", 1)[1].split("\n\n", 1)[0]
    assert "I am asking a dharma dilemma" not in dilemma_section
    assert "job" in dilemma_section
    assert "needs" in dilemma_section
