from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords, _planner_candidate_terms, rewrite_malformed_query
from app.api.routes.query import _model_facing_firewall_text
from app.llm.generator import _build_synthesis_prompt
from app.security.firewall import run_security_firewall
from app.security.privacy_scrubber import detect_sensitive_names, scrub_pii
from app.security.sanitizer import sanitize_query


JOB_CHOICE_QUERY = (
    "while looking for a job can I look for a job which fulfills our needs "
    "or select a job just randomly?"
)

TOXIC_MANAGER_QUERY = (
    "I am feeling extremely stressed at my job. My manager, Sarah Jenkins, is constantly "
    "micro-managing me and I can't take it anymore. You can reach out to my personal email "
    "at sarah.jenkins.mock@gmail.com or my work contact sjenkins@corporate-env.org to send me "
    "the reading list. How to deal with toxic bosses?"
)


def test_job_choice_query_is_not_treated_as_follow_up():
    result = rewrite_malformed_query(JOB_CHOICE_QUERY, previous_context={"question": "Who am I?"})

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]


def test_toxic_manager_query_preserves_workplace_retrieval_terms_after_scrubbing():
    raw = sanitize_query(TOXIC_MANAGER_QUERY)
    security = run_security_firewall(raw)
    scrubbed = scrub_pii(_model_facing_firewall_text(security.sanitized), extra_names=detect_sensitive_names(raw))
    result = rewrite_malformed_query(scrubbed)
    keywords = _extract_planner_keywords(result["rewrittenQuery"])
    candidates = _planner_candidate_terms(scrubbed, result["rewrittenQuery"])

    assert "can't" in scrubbed
    assert "&#x27;" not in scrubbed
    assert "job" in keywords
    assert "manager" in keywords
    assert "stress" in keywords
    assert "toxic" in keywords
    assert "boss" in keywords
    assert "boundary" in candidates
    assert "respect" in candidates


def test_follow_up_uses_recent_context_list_when_query_depends_on_it():
    result = rewrite_malformed_query(
        "What should I do next?",
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty."},
                {"question": "Who am I?"},
            ]
        },
    )

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"] == "I lied to my close friend and feel guilty."
    assert "Previous dilemma: I lied to my close friend and feel guilty." in result["rewrittenQuery"]


def test_follow_up_preserves_prior_moral_keywords_for_retrieval():
    result = rewrite_malformed_query(
        "What should I do next?",
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty. What should I do?"},
            ]
        },
    )
    keywords = _extract_planner_keywords(result["rewrittenQuery"])

    assert result["previousContextUsed"] is True
    assert "lie" in keywords
    assert "friend" in keywords
    assert "guilt" in keywords
    assert "previous" not in keywords
    assert "question" not in keywords


def test_friend_meeting_follow_up_uses_previous_context():
    result = rewrite_malformed_query(
        "What should I say next to my friend when we meet?",
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty. What should I do?"},
            ]
        },
    )

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"] == "I lied to my close friend and feel guilty. What should I do?"
    assert "Follow-up question: What should I say next to my friend when we meet" in result["rewrittenQuery"]


def test_meet_again_follow_up_uses_previous_friend_context():
    result = rewrite_malformed_query(
        "what if we both meet again? should I talk normally?",
        previous_context={
            "turns": [
                {"question": "I argued with my friend [NAME_REDACTED] and feel guilty."},
            ]
        },
    )

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"] == "I argued with my friend the other person and feel guilty."
    assert "[NAME_REDACTED]" not in result["rewrittenQuery"]
    assert "Follow-up question: what if we both meet again? should I talk normally?" in result["rewrittenQuery"]


def test_how_to_dharma_question_does_not_inherit_redacted_previous_context():
    result = rewrite_malformed_query(
        "how to follow dharma for time critical tasks?",
        previous_context={
            "turns": [
                {"question": "I argued with my friend [NAME_REDACTED] and feel guilty."},
            ]
        },
    )

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]
    assert "[NAME_REDACTED]" not in result["rewrittenQuery"]


def test_new_apple_ceo_question_does_not_use_previous_friend_context():
    result = rewrite_malformed_query(
        "i met apple ceo the other day. he was very nice even with low skilled people also. How he is down to earth?",
        previous_context={
            "turns": [
                {"question": "I argued with my friend [NAME_REDACTED] and feel guilty."},
            ]
        },
    )

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]
    assert "apple ceo" in result["rewrittenQuery"].lower()


def test_typo_heavy_meet_again_follow_up_uses_context_and_redacts_name():
    scrubbed_query = scrub_pii("what should I say next when I meet lakshm agan?")
    result = rewrite_malformed_query(
        scrubbed_query,
        previous_context={
            "turns": [
                {"question": "I argued with my friend [NAME_REDACTED] and feel guilty."},
            ]
        },
    )
    keywords = _extract_planner_keywords(result["rewrittenQuery"])

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"] == "I argued with my friend the other person and feel guilty."
    assert "lakshm" not in result["rewrittenQuery"].lower()
    assert "again" in result["rewrittenQuery"].lower()
    assert "friend" in keywords
    assert "guilt" in keywords
    assert "name_redacted" not in keywords


def test_typo_heavy_truth_follow_up_uses_previous_context():
    result = rewrite_malformed_query(
        (
            "As you sad told my frend the truth. my friend was angry with me after telling the truth. "
            "He stopped talking to me. What should I do now?"
        ),
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty. What should I do?"},
            ]
        },
    )
    keywords = _extract_planner_keywords(result["rewrittenQuery"])

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"] == "I lied to my close friend and feel guilty. What should I do?"
    assert "as you said told my friend the truth" in result["rewrittenQuery"].lower()
    assert "truth" in keywords
    assert "friend" in keywords


def test_unrelated_query_ignores_previous_context_list():
    result = rewrite_malformed_query(
        JOB_CHOICE_QUERY,
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty."},
                {"question": "Who am I?"},
            ]
        },
    )

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]


def test_explicit_follow_up_uses_previous_context_even_without_follow_up_markers():
    result = rewrite_malformed_query(
        "I don't have anyone to share my duties. What should I do?",
        previous_context={
            "turns": [
                {
                    "question": (
                        "I have taken on the care of my sick parent while trying to manage a failing business. "
                        "I feel entirely burned out, hopeless, and physically exhausted."
                    )
                },
            ]
        },
        use_previous_context=True,
    )

    assert result["previousContextUsed"] is True
    assert result["previousContextQuestion"].startswith("I have taken on the care of my sick parent")
    assert "Previous dilemma: I have taken on the care of my sick parent" in result["rewrittenQuery"]
    assert "Follow-up question: I don't have anyone to share my duties" in result["rewrittenQuery"]


def test_same_duties_query_stays_standalone_without_explicit_follow_up_signal():
    result = rewrite_malformed_query(
        "I don't have anyone to share my duties. What should I do?",
        previous_context={
            "turns": [
                {"question": "I have taken on the care of my sick parent while managing a failing business."},
            ]
        },
    )

    assert result["previousContextUsed"] is False
    assert result["previousContextQuestion"] is None
    assert "Previous dilemma" not in result["rewrittenQuery"]


def test_unrelated_query_with_that_does_not_use_previous_context():
    result = rewrite_malformed_query(
        "While looking for a job, should I choose one that fulfills my needs or pick randomly?",
        previous_context={
            "turns": [
                {"question": "I lied to my close friend and feel guilty. What should I do?"},
            ]
        },
    )

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


def test_parent_gift_affection_query_preserves_family_boundary_keywords():
    scrubbed = scrub_pii(
        "My mom Sita wants to see me just to get her new clothes. "
        "But she doesn't show any love or affection on me. How to deal with this?"
    )
    rewritten = rewrite_malformed_query(scrubbed)["rewrittenQuery"]
    keywords = _extract_planner_keywords(rewritten)
    candidates = _planner_candidate_terms(rewritten, rewritten)

    assert "Sita" not in scrubbed
    assert "[NAME_REDACTED]" in scrubbed
    assert "mother" in keywords
    assert "gift" in keywords
    assert "affection" in keywords
    assert "family" in candidates
    assert "compassion" in candidates
    assert "relationship" in candidates
    assert "contentment" in candidates


def test_parent_gift_affection_query_accepts_family_and_contentment_scriptures():
    scrubbed = scrub_pii(
        "My mom Sita wants to see me just to get her new clothes. "
        "But she doesn't show any love or affection on me. How to deal with this?"
    )
    rewritten = rewrite_malformed_query(scrubbed)["rewrittenQuery"]
    reranked = [
        {
            "score": 89,
            "verse": {
                "translation": "Health is the greatest of gifts, contentment the greatest wealth.",
                "context": "On minimal living, avoiding excessive consumerism, and building relational trust.",
                "source": "Dhammapada",
                "keywords": ["contentment", "trust", "relationship"],
            },
        },
        {
            "score": 87,
            "verse": {
                "translation": "Even as a mother would protect her only child with her life.",
                "context": "On empathy, expanding care beyond family, and goodwill.",
                "source": "Karaniya Metta Sutta",
                "keywords": ["compassion", "love", "goodwill"],
            },
        },
    ]

    assert _retrieval_matches_query(rewritten, reranked)


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
