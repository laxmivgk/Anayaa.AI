import pytest

from app.agents.pipeline_errors import SynthesisRejectedError
from app.llm.generator import (
    SYNTHESIS_SYSTEM_PROMPT,
    _build_synthesis_prompt,
    _clean_synthesis_output,
    _deterministic_scripture_grounding,
    _is_caregiver_burnout_dilemma,
    _query_focus_terms,
    _relationship_role_groups,
    _repair_synthesis_sections,
    _should_reject_synthesis,
    _synthesis_rejection_reason,
    generate_moral_pathway,
)


def test_synthesis_prompt_uses_restored_summary_section_tone():
    prompt = _build_synthesis_prompt(
        "how can I save the environment with a busy life?",
        [
            {
                "faith": "Hinduism",
                "source": "Isha Upanishad",
                "chapter": "Chapter 1",
                "verse": "Verse 1",
                "translation": "All this is enveloped by the Divine.",
                "keywords": ["stewardship", "renunciation"],
            }
        ],
        "",
    )

    assert "Judgement: say what choice seems wisest and kindest, without naming scripture sources" in SYNTHESIS_SYSTEM_PROMPT
    assert "Next step: give a useful small sequence" in SYNTHESIS_SYSTEM_PROMPT
    assert "one concrete action, one way to prepare" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not use literal sublabels such as Preparation detail or Calm follow-through" in SYNTHESIS_SYSTEM_PROMPT
    assert "Only mention another person listening or not listening when the dilemma confirms" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not make the whole Next step only writing, documenting, or gathering evidence" in SYNTHESIS_SYSTEM_PROMPT
    assert "do not treat secrecy as absolute" in SYNTHESIS_SYSTEM_PROMPT
    assert "minimum necessary information" in SYNTHESIS_SYSTEM_PROMPT
    assert "Citation cards:" in prompt
    assert "Source: Isha Upanishad, Chapter 1, Verse 1" in prompt
    assert "Passage: \"All this is enveloped by the Divine.\"" in prompt
    assert "Deterministic output skeleton:" in prompt
    assert "Required citation anchors:" in prompt
    assert "Isha Upanishad, Chapter 1, Verse 1 anchors: stewardship, renunciation" in prompt
    assert "name every exact source from Required citation anchors and reuse at least one anchor keyword from each" in SYNTHESIS_SYSTEM_PROMPT
    assert "Keep scripture names, chapter numbers, verse numbers, and citation labels only in Scripture grounding" in SYNTHESIS_SYSTEM_PROMPT
    assert "never mix sources" in SYNTHESIS_SYSTEM_PROMPT
    assert "if a sentence quotes or references Romans, the sentence subject must be Romans or Holy Bible" in SYNTHESIS_SYSTEM_PROMPT
    assert "Write exactly these 5 labeled sections" not in prompt
    assert "Start with a practical verb" not in prompt
    assert "situation-specific moral stance" not in SYNTHESIS_SYSTEM_PROMPT


def test_scripture_grounding_avoids_repeated_titles_and_anchors():
    grounding = _deterministic_scripture_grounding(
        "How can I handle a disagreement with someone compassionately?",
        [
            {
                "source": "Sutta Nipata: Karaniya Metta Sutta",
                "chapter": "Metta Sutta",
                "verse": "Verse 3-4",
                "keywords": ["empathy", "brotherhood", "protection", "compassion"],
            },
            {
                "source": "Holy Bible: Luke",
                "chapter": "Chapter 6",
                "verse": "Verse 31",
                "keywords": ["empathy", "golden rule", "fairness", "relationship"],
            },
        ],
    )

    assert "Sutta Nipata: Karaniya Metta Sutta, Verse 3-4" in grounding
    assert "Karaniya Metta Sutta, Metta Sutta" not in grounding
    assert "empathy and brotherhood" in grounding
    assert "golden rule and fairness" in grounding


def test_terse_job_offer_choice_uses_user_terms_for_synthesis_relevance():
    dilemma = (
        "I am asking a dharma dilemma about this terse user-provided choice: "
        "Which should guide my decision between two job offers: security or purpose?. "
        "The situation may involve competing duties, relationships, values, needs, or responsibilities. "
        "Without assuming missing facts about urgency, safety, health, dependency, money, "
        "or who needs help most, how should I understand the wisest, kindest, most truthful, "
        "and least harmful next step?"
    )
    citations = [
        {
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but not to the fruits.",
            "keywords": ["duty", "work", "purpose", "responsibility"],
        },
        {
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 15",
            "verse": "Verse 204",
            "translation": "Contentment is the greatest wealth.",
            "keywords": ["contentment", "security", "wealth"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Let purpose guide the choice, but do not ignore real security needs in the job offers.",
            "Reflection: This is a tension between stable livelihood and meaningful work.",
            "Judgement: Choose the offer that lets you meet responsibilities while staying close to honest purpose.",
            "Next step: Compare the two offers by basic needs, growth, and the duty you can perform well.",
            "Scripture grounding: Bhagavad Gita, Chapter 2, Verse 47 emphasizes duty and work. Dhammapada, Chapter 15, Verse 204 emphasizes contentment and security.",
        ]
    )

    focus_terms = _query_focus_terms(dilemma)

    assert "security" in focus_terms
    assert "purpose" in focus_terms
    assert "terse" not in focus_terms
    assert "offers" not in focus_terms
    assert _synthesis_rejection_reason(dilemma, citations, pathway) == ""

    repaired = _repair_synthesis_sections(dilemma, citations, pathway)

    assert "security alongside purpose" in repaired
    assert "act responsibly and meaningfully" in repaired
    assert "without making claims beyond the retrieved passages" not in repaired
    assert "without inventing more than the passage provides" not in repaired


def test_grudge_explanation_allows_resentment_and_forgiveness_language():
    dilemma = (
        "I am asking a dharma dilemma about this user-provided situation: "
        "Why is it so hard for people to let go of old grudges?. "
        "Without inventing missing facts, what is the wisest, kindest, most truthful, "
        "and least harmful way to understand or act?"
    )
    citations = [
        {
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 1",
            "verse": "Verse 5",
            "translation": "Hatred is never appeased by hatred; by non-hatred alone is hatred appeased.",
            "keywords": ["hatred", "forgiveness", "compassion"],
        }
    ]
    pathway = "\n".join(
        [
            "Summary: Old grudges are hard to release because resentment can feel like protection.",
            "Reflection: Hurt can keep anger active even when forgiveness would bring more peace.",
            "Judgement: The wiser path is to loosen resentment without pretending the hurt never happened.",
            "Next step: Notice one memory that still tightens your mind, then choose one calm act of release today.",
            "Scripture grounding: Dhammapada, Chapter 1, Verse 5 emphasizes hatred and forgiveness, which supports loosening resentment instead of feeding old anger.",
        ]
    )

    focus_terms = _query_focus_terms(dilemma)

    assert "people" not in focus_terms
    assert "grudges" in focus_terms
    assert _synthesis_rejection_reason(dilemma, citations, pathway) == ""


def test_confidentiality_safety_dilemma_uses_limited_disclosure_template():
    citations = [
        {
            "id": "i1",
            "faith": "Islam",
            "source": "Quran",
            "chapter": "Ma'idah (5)",
            "verse": "Verse 8",
            "translation": "Stand firm for justice, as witnesses, even if it is against yourselves.",
            "keywords": ["justice", "truth", "responsibility"],
        },
        {
            "id": "c1",
            "faith": "Christianity",
            "source": "Holy Bible: Matthew",
            "chapter": "Chapter 7",
            "verse": "Verse 12",
            "translation": "Do to others what you would have them do to you.",
            "keywords": ["care", "neighbor", "harm"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Keeping a friend's secret is always loyal.",
            "Reflection: You feel torn about whether to break confidence.",
            "Judgement: Keep the secret unless you feel uncomfortable.",
            "Next step: Say nothing for now and hope the situation improves.",
            "Scripture grounding: The retrieved scriptures support care.",
        ]
    )

    repaired = _repair_synthesis_sections(
        "A friend told me a secret, but keeping it may let someone else get hurt. Should I break confidentiality?",
        citations,
        pathway,
    )

    assert "Do not treat confidentiality as absolute" in repaired
    assert "protect safety with the least necessary disclosure" in repaired
    assert "risk is serious or immediate" in repaired
    assert "minimum necessary facts" in repaired
    assert "confidential guidance" in repaired
    assert "limited, responsible disclosure" in repaired
    assert "broadcast" not in repaired
    assert "Quran, Ma'idah (5), Verse 8 emphasizes justice and truth" in repaired
    assert "Holy Bible: Matthew, Chapter 7, Verse 12 emphasizes care and neighbor" in repaired
    assert _synthesis_rejection_reason(
        "A friend told me a secret, but keeping it may let someone else get hurt. Should I break confidentiality?",
        citations,
        repaired,
    ) == ""


def test_follow_up_friend_truth_silence_uses_repair_without_pressure_template():
    citations = [
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 16",
            "verse": "Verse 2",
            "translation": "Truthfulness, absence of anger, renunciation, peacefulness...",
            "keywords": ["truthfulness", "peace", "restraint"],
        },
        {
            "id": "b1",
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 1",
            "verse": "Verse 5",
            "translation": "Hatred is never appeased by hatred; by non-hatred alone is hatred appeased.",
            "keywords": ["non-hatred", "patience", "friendship"],
        },
    ]
    dilemma = (
        "Previous dilemma: I lied to my close friend and feel guilty. What should I do? "
        "Follow-up question: I told the truth, but my friend stopped talking to me. What should I do now?"
    )
    pathway = "\n".join(
        [
            "Summary: Keep trying until your friend understands you.",
            "Reflection: This is frustrating because you already told the truth.",
            "Judgement: The best choice is to convince your friend to respond.",
            "Next step: Send several messages explaining why you lied and ask them to stop ignoring you.",
            "Scripture grounding: The retrieved scriptures support honesty.",
        ]
    )

    repaired = _repair_synthesis_sections(dilemma, citations, pathway)

    assert "accountability without pressure" in repaired
    assert "give your friend space" in repaired
    assert "one short message" in repaired
    assert "stop repeating the apology" in repaired
    assert "one gentle check-in" in repaired
    assert "forcing a response" in repaired
    assert "Send several messages" not in repaired
    assert "convince your friend" not in repaired
    assert "Bhagavad Gita, Chapter 16, Verse 2 emphasizes truthfulness and peace" in repaired
    assert "Dhammapada, Chapter 1, Verse 5 emphasizes non-hatred and patience" in repaired
    assert _synthesis_rejection_reason(dilemma, citations, repaired) == ""


def test_repair_replaces_invented_conversation_next_step_for_patience_query():
    citations = [
        {
            "id": "b5",
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 20 (Magga Vagga)",
            "verse": "Verse 276",
            "translation": "You yourselves must strive; the Buddhas only point the way.",
            "keywords": ["responsibility", "effort", "action", "guidance"],
        },
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but you are not entitled to the fruits.",
            "keywords": ["work", "duty", "results", "detachment"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Patience matters when things don't go my way.",
            "Reflection: I feel frustrated when outcomes do not match my hopes.",
            "Judgement: Choose responsibility and steady effort instead of anxiety about outcomes.",
            "Next step: Today, I will call a trusted friend or family member who can offer emotional support. If they do not listen, I will follow up with another trusted person.",
            "Scripture grounding: The Dhammapada's emphasis on personal responsibility and the other person guidance on working with dedication offer valuable insights.",
        ]
    )

    repaired = _repair_synthesis_sections("Why patience matters when things don't go my way?", citations, pathway)

    assert "trusted friend or family member" not in repaired
    assert "they do not listen" not in repaired
    assert "pause for one minute" in repaired
    assert "Dhammapada, Chapter 20 (Magga Vagga), Verse 276 emphasizes responsibility and effort" in repaired
    assert "Bhagavad Gita, Chapter 2, Verse 47 emphasizes work and duty" in repaired
    assert "the other person guidance" not in repaired


def test_repair_replaces_template_support_next_step_for_self_regulation_query():
    citations = [
        {
            "id": "b5",
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 20 (Magga Vagga)",
            "verse": "Verse 276",
            "translation": "You yourselves must strive; the Buddhas only point the way.",
            "keywords": ["responsibility", "effort", "action", "guidance"],
        },
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but you are not entitled to the fruits.",
            "keywords": ["work", "duty", "results", "detachment"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Patience matters when things don't go my way.",
            "Reflection: I feel stuck when plans fail.",
            "Judgement: Choose steady effort instead of anxiety about outcomes.",
            "Next step: Today, I will call a trusted friend or family member who can offer emotional support and help me brainstorm ways to move forward. Preparation detail: Before calling, I'll take a few minutes to collect my thoughts and identify what specific challenges I'm facing. Calm follow-through if it does not improve: If the conversation doesn't lead to immediate solutions, I will focus on taking small, manageable steps towards my goals.",
            "Scripture grounding: The citations support responsibility and work.",
        ]
    )

    repaired = _repair_synthesis_sections("Why should I be patient when things don't go my way?", citations, pathway)

    assert "trusted friend or family member" not in repaired
    assert "Preparation detail" not in repaired
    assert "Calm follow-through" not in repaired
    assert "brainstorm ways" not in repaired
    assert "pause for one minute" in repaired
    assert "one small duty" in repaired


def test_repair_uses_gift_specific_next_step_for_time_or_money_choice():
    citations = [
        {
            "id": "c1",
            "faith": "Christianity",
            "source": "Holy Bible: Matthew",
            "chapter": "Chapter 16",
            "verse": "Verse 26",
            "translation": "What good will it be for someone to gain the whole world, yet forfeit their soul?",
            "keywords": ["integrity", "greed"],
        },
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but you are not entitled to the fruits.",
            "keywords": ["duty", "karma"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Choose time over money when someone already has everything.",
            "Reflection: This is about giving care rather than proving value through wealth.",
            "Judgement: The wiser choice is presence, unless a practical need makes money kinder.",
            "Next step: Today, I will call a trusted friend or family member who can offer emotional support and help me brainstorm ways to move forward.",
            "Scripture grounding: The citations support taking the next right action patiently.",
        ]
    )

    repaired = _repair_synthesis_sections(
        "What should I choose to give someone who has everything: time or money?",
        citations,
        pathway,
    )

    assert "trusted friend or family member" not in repaired
    assert "pause for one minute" not in repaired
    assert "shared meal" in repaired
    assert "personal note" in repaired
    assert "care rather than price" in repaired
    assert "material value alone" in repaired
    assert "patiently while staying responsible" not in repaired


def test_scripture_grounding_uses_investment_risk_wording_for_all_in_opportunity_query():
    citations = [
        {
            "id": "c1",
            "faith": "Christianity",
            "source": "Holy Bible: Matthew",
            "chapter": "Chapter 6",
            "verse": "Verse 34",
            "translation": "Do not worry about tomorrow, for tomorrow will worry about itself.",
            "keywords": ["anxiety", "future", "trust"],
        },
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but not to the fruits.",
            "keywords": ["duty", "results", "choice"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: It is usually unwise to invest everything in one opportunity without weighing risk and duty.",
            "Reflection: A single opportunity can feel urgent when hope and fear are both strong.",
            "Judgement: The wiser path is restraint, clarity, and protecting real needs before committing everything.",
            "Next step: List what you cannot afford to lose, then compare the opportunity with your duties and needs.",
            "Scripture grounding: The retrieved scriptures support care and responsibility.",
        ]
    )

    repaired = _repair_synthesis_sections(
        "Explain whether it's wise to invest everything I have in one opportunity.",
        citations,
        pathway,
    )

    assert "wealth and opportunity with restraint" in repaired
    assert "weighing risk, duty, and real needs" in repaired
    assert "before committing everything" in repaired
    assert "real choice in front of the user" not in repaired
    assert "without making claims beyond the retrieved passages" not in repaired


def test_scripture_grounding_uses_truthfulness_wording_for_repeated_lying_query():
    citations = [
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 16",
            "verse": "Verse 2",
            "translation": "Truthfulness, absence of anger, renunciation, peacefulness...",
            "keywords": ["truthfulness", "honesty"],
        },
        {
            "id": "b1",
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 1",
            "verse": "Verse 1",
            "translation": "Mind precedes all things.",
            "keywords": ["mind", "habit"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: People may keep lying after being caught because fear and habit can feel safer than accountability.",
            "Reflection: Being caught does not always change the inner impulse that protects pride or avoids consequences.",
            "Judgement: The wiser path is truth, responsibility, and repair before the habit causes more harm.",
            "Next step: Name the specific truth being avoided, then make one honest correction today.",
            "Scripture grounding: The retrieved scriptures support honesty and responsibility.",
        ]
    )

    repaired = _repair_synthesis_sections(
        "Why do people keep lying even after they've been caught once?",
        citations,
        pathway,
    )

    assert "repeated falsehood" in repaired
    assert "honesty, accountability, and repair" in repaired
    assert "real choice in front of the user" not in repaired
    assert "without making claims beyond the retrieved passages" not in repaired


def test_follow_up_ai_moral_decision_grounding_does_not_inherit_lying_category_or_redaction_prefixes():
    citations = [
        {
            "id": "h2",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 3",
            "verse": "Verse 35",
            "translation": "Better is one's own duty, though imperfect, than another's duty well performed.",
            "keywords": ["identity", "path"],
        },
        {
            "id": "i1",
            "faith": "Islam",
            "source": "[NAME_REDACTED]Quran",
            "chapter": "[NAME_REDACTED]Ma'idah (5)",
            "verse": "Verse 8",
            "translation": "Stand firm for justice, as witnesses to Allah, even if it is against yourselves.",
            "keywords": ["justice", "equity"],
        },
    ]
    dilemma = (
        "Previous dilemma: Why do people keep lying even after they've been caught once? "
        "Follow-up question: Explain whether it's okay to let an AI make moral decisions for you."
    )
    pathway = "\n".join(
        [
            "Summary: AI can help you reflect, but it should not replace your moral responsibility.",
            "Reflection: The question is about whether a tool can carry conscience for a person.",
            "Judgement: Use AI for perspective, but keep the final ethical choice with a responsible human.",
            "Next step: Ask AI for options, then compare them with justice, duty, and the people affected.",
            "Scripture grounding: The retrieved scriptures support honesty and responsibility.",
        ]
    )

    repaired = _repair_synthesis_sections(dilemma, citations, pathway)

    assert "Quran, Ma'idah (5), Verse 8 emphasizes justice and equity" in repaired
    assert "the other personQuran" not in repaired
    assert "the other personMa'idah" not in repaired
    assert "[NAME_REDACTED]" not in repaired
    assert "using AI as a tool for reflection" in repaired
    assert "moral responsibility, justice, and accountability" in repaired
    assert "repeated falsehood" not in repaired


def test_repair_uses_topic_aware_next_step_for_explanation_query():
    citations = [
        {
            "id": "b5",
            "faith": "Buddhism",
            "source": "Dhammapada",
            "chapter": "Chapter 20 (Magga Vagga)",
            "verse": "Verse 276",
            "translation": "You yourselves must strive; the Buddhas only point the way.",
            "keywords": ["responsibility", "effort", "action", "guidance"],
        }
    ]
    pathway = "\n".join(
        [
            "Summary: Patience means steady effort when outcomes are not under your control.",
            "Reflection: The question is about understanding patience, not resolving a conflict with another person.",
            "Judgement: Learn patience as a practice of effort without panic.",
            "Next step: Today, I will call a trusted friend or family member who can offer emotional support and help me brainstorm ways to move forward. Preparation detail: Before calling, I'll take a few minutes to collect my thoughts. Calm follow-through if it does not improve: If the conversation doesn't lead to immediate solutions, I will focus on small steps.",
            "Scripture grounding: The citation supports responsibility.",
        ]
    )

    repaired = _repair_synthesis_sections("Explain patience in simple words", citations, pathway)

    assert "trusted friend or family member" not in repaired
    assert "Preparation detail" not in repaired
    assert "Calm follow-through" not in repaired
    assert "pause for one minute before reacting" not in repaired
    assert "connect patience" in repaired
    assert "one concrete situation" in repaired


def test_repair_strips_next_step_template_sublabels_without_replacing_good_step():
    citations = [
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but not to the fruits.",
            "keywords": ["work", "duty"],
        }
    ]
    pathway = "\n".join(
        [
            "Summary: Choose honest work without clinging to results.",
            "Reflection: The pressure is about outcome anxiety.",
            "Judgement: Do the duty that can be done cleanly.",
            "Next step: Choose one honest task to complete today. Preparation detail: Set aside ten quiet minutes. Calm follow-through if it does not improve: Return to the task without forcing the result.",
            "Scripture grounding: The citation supports duty.",
        ]
    )

    repaired = _repair_synthesis_sections("What is duty without attachment?", citations, pathway)

    assert "Preparation detail" not in repaired
    assert "Calm follow-through" not in repaired
    assert "Choose one honest task" in repaired
    assert "Set aside ten quiet minutes" in repaired


def test_synthesis_prompt_preserves_confirmed_friend_role_after_pii_redaction():
    dilemma = "I argued with my friend [NAME_REDACTED] and her phone is [PHONE_REDACTED]. I feel guilty. What should I do?"
    prompt = _build_synthesis_prompt(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "chapter": "Verse",
                "verse": "5",
                "translation": "Hatred is never appeased by hatred.",
                "keywords": ["friendship", "compassion"],
            }
        ],
        "",
    )

    assert _relationship_role_groups(dilemma) == {"friend"}
    assert "Known relationship roles from the dilemma: friend." in prompt
    assert "use only those confirmed roles or neutral wording" in SYNTHESIS_SYSTEM_PROMPT
    assert "do not change one relationship into another" in SYNTHESIS_SYSTEM_PROMPT
    assert "such as your mom, your friend" not in prompt


def test_caregiver_burnout_prompt_prioritizes_support_over_business_finances():
    dilemma = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted. "
        "I feel like giving up on everything."
    )
    prompt = _build_synthesis_prompt(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "chapter": "Verse",
                "verse": "3",
                "translation": "Mind precedes all things.",
                "keywords": ["care", "mind", "peace"],
            }
        ],
        "",
    )

    assert _is_caregiver_burnout_dilemma(dilemma)
    assert "treat exhaustion, hopelessness, and 'giving up' as the urgent center" in SYNTHESIS_SYSTEM_PROMPT
    assert "must not start with business finances, debt tracking, saving money, or productivity" in SYNTHESIS_SYSTEM_PROMPT
    assert "contact one real person today" in SYNTHESIS_SYSTEM_PROMPT
    assert "parent-care coverage" in SYNTHESIS_SYSTEM_PROMPT
    assert "local emergency or crisis support now" in SYNTHESIS_SYSTEM_PROMPT
    assert "never print [NAME_REDACTED] in final guidance" in SYNTHESIS_SYSTEM_PROMPT
    assert "Parent-care wording is allowed because the dilemma is about caregiving duties." in prompt


def test_caregiver_burnout_support_first_answer_passes_relevance_guardrail():
    dilemma = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted. "
        "I feel like giving up on everything."
    )
    pathway = "\n".join(
        [
            "Summary: You are burned out and need immediate human support before trying to solve the business.",
            "Reflection: Caring for a sick parent while feeling hopeless and exhausted is too much to carry alone.",
            "Judgement: The wisest choice is to pause non-urgent business decisions and ask for help now.",
            "Next step: Contact one trusted person today and say, I cannot carry this alone. Ask for one concrete relief action such as parent-care coverage, a meal, a ride, or help calling a doctor or respite resource; if you cannot stay safe, contact emergency or crisis support now.",
            "Scripture grounding: Dhammapada supports steadying the mind before action, which fits asking for support and rest before making decisions.",
        ]
    )

    assert _synthesis_rejection_reason(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "translation": "Mind precedes all things.",
                "keywords": ["mind", "peace"],
            }
        ],
        pathway,
    ) == ""


def test_caregiver_burnout_guard_accepts_natural_support_and_risk_wording():
    dilemma = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted. "
        "I feel like giving up on everything."
    )
    pathway = "\n".join(
        [
            "Summary: This is too much to carry alone, and immediate support matters more than fixing the business today.",
            "Reflection: You sound overwhelmed and worn down from caring for your parent while trying to keep everything else afloat.",
            "Judgement: The wisest choice is to pause non-urgent decisions and let someone help you before exhaustion takes over.",
            "Next step: Call a family member or trusted friend today and ask them to cover one concrete task, such as sitting with your parent, bringing food, or helping arrange respite. If you feel at risk of hurting yourself, contact crisis support now.",
            "Scripture grounding: Dhammapada supports steadying the mind before action, which fits asking for support and rest before making decisions.",
        ]
    )

    assert _synthesis_rejection_reason(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "translation": "Mind precedes all things.",
                "keywords": ["mind", "peace"],
            }
        ],
        pathway,
    ) == ""


def test_caregiver_follow_up_allows_parent_role_from_previous_dilemma_context():
    dilemma = (
        "Previous dilemma: I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted. "
        "Follow-up question: I don't have anyone to share my duties. What should I do?"
    )
    pathway = "\n".join(
        [
            "Summary: You need immediate shared support, not more silent endurance.",
            "Reflection: Caring for your parent while exhausted can make every duty feel impossible.",
            "Judgement: The wisest choice is to ask one real person for concrete help today and pause non-urgent business decisions.",
            "Next step: Call a trusted person and ask for one specific relief action, such as sitting with your parent, bringing a meal, or helping call a doctor or respite resource. If you cannot stay safe, contact local emergency or crisis support now.",
            "Scripture grounding: Dhammapada supports steadying the mind before action, which fits asking for support and rest before deciding next steps.",
        ]
    )

    assert _relationship_role_groups(dilemma) == {"parent"}
    assert _synthesis_rejection_reason(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "translation": "Mind precedes all things.",
                "keywords": ["mind", "peace"],
            }
        ],
        pathway,
    ) == ""


def test_caregiver_burnout_allows_tentative_family_helper_without_role_drift():
    dilemma = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted."
    )
    pathway = "\n".join(
        [
            "Summary: You need support today, not more pressure.",
            "Reflection: Caring for your parent while exhausted can feel impossible.",
            "Judgement: Ask for help before making business decisions.",
            "Next step: Call a trusted relative or your sibling if available and ask them to cover one parent-care task today. If you cannot stay safe, contact emergency or crisis support now.",
            "Scripture grounding: Dhammapada supports steadying the mind before action, which fits asking for support and rest before deciding next steps.",
        ]
    )

    assert _synthesis_rejection_reason(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "translation": "Mind precedes all things.",
                "keywords": ["mind", "peace"],
            }
        ],
        pathway,
    ) == ""


def test_caregiver_burnout_still_rejects_unrelated_role_as_claimed_fact():
    dilemma = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted."
    )
    pathway = "\n".join(
        [
            "Summary: You need support today, not more pressure.",
            "Reflection: Your spouse is clearly responsible for helping, and that is why you feel abandoned.",
            "Judgement: Ask for help before making business decisions.",
            "Next step: Call one trusted person today and ask for one parent-care task to be covered. If you cannot stay safe, contact emergency or crisis support now.",
            "Scripture grounding: Dhammapada supports steadying the mind before action, which fits asking for support and rest before deciding next steps.",
        ]
    )

    assert _synthesis_rejection_reason(
        dilemma,
        [
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "translation": "Mind precedes all things.",
                "keywords": ["mind", "peace"],
            }
        ],
        pathway,
    ) == "unsupported_relationship_drift"


def test_next_step_prompt_handles_not_listening_with_boundary_not_only_documentation():
    assert "give the other person a real chance to respond" in SYNTHESIS_SYSTEM_PROMPT
    assert "If they do not listen" in SYNTHESIS_SYSTEM_PROMPT
    assert "set a clear boundary" in SYNTHESIS_SYSTEM_PROMPT
    assert "note key facts only if it helps protect truth" in SYNTHESIS_SYSTEM_PROMPT
    assert "specific constructive conversation or accountability move" in SYNTHESIS_SYSTEM_PROMPT


def test_clean_synthesis_output_removes_prompt_echo_before_summary():
    output = _clean_synthesis_output(
        "\n".join(
            [
                "Dilemma:",
                "is dropshipping a scam?",
                "Must stay focused on these user-topic words:",
                "dropshipping, scam",
                "Citation anchors:",
                "1. Bhagavad Gita Chapter 2:Verse 47 anchors: duty, integrity",
                "Write exactly these 5 labeled sections, 180 words or fewer total.",
                "Use simple everyday words. Each title must be visible at the start of its own line:",
                "One-line summary: Dropshipping is not automatically a scam, but it becomes wrong when it misleads customers.",
                "Reflection: This is a business-integrity question about honesty and trust.",
                "Judgement: Choose transparent selling and fair customer treatment.",
                "Next step: Check supplier quality, delivery times, refund terms, and customer disclosures.",
                "Scripture grounding: The retrieved scriptures support honesty and responsible action.",
            ]
        )
    )

    assert output.startswith("Summary: Dropshipping is not automatically a scam")
    assert "Dilemma:" not in output
    assert "Citation anchors:" not in output
    assert "anchors: duty" not in output
    assert "Write exactly these" not in output
    assert "Use simple everyday words" not in output


@pytest.mark.anyio
async def test_generate_moral_pathway_preserves_synthesis_rejection(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "message": {
                    "content": (
                        "Summary: Build steady discipline through a small daily routine.\n"
                        "Reflection: It is normal to feel scattered.\n"
                        "Judgement: Choose consistency.\n"
                        "Next step: Write one task and do it today.\n"
                        "Scripture grounding: The Bhagavad Gita supports duty."
                    )
                },
                "eval_count": 42,
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.llm.generator.httpx.AsyncClient", FakeAsyncClient)

    with pytest.raises(SynthesisRejectedError) as exc:
        await generate_moral_pathway(
            "My mom wants to see me just to get her new clothes. How to deal with this?",
            [{"source": "Dhammapada", "faith": "Buddhism", "keywords": ["contentment", "relationship"]}],
        )

    assert exc.value.code == "quality_threshold_not_met"
    assert exc.value.detail == "summary_not_relevant_to_query"


def test_clean_synthesis_output_normalizes_bare_section_labels_and_infers_summary():
    output = _clean_synthesis_output(
        "\n".join(
            [
                "Disciplined",
                "You can cultivate discipline by setting clear goals and tracking your progress.",
                "Reflection",
                "It is normal to feel stuck when building discipline.",
                "Judgement",
                "Choose steady duty over waiting for motivation.",
                "Next step",
                "Write one goal today and block ten quiet minutes for it.",
                "Scripture grounding",
                "The Bhagavad Gita points to duty and self-control.",
            ]
        )
    )

    assert output.startswith("Summary: You can cultivate discipline")
    assert "Reflection: It is normal" in output
    assert "Judgement: Choose steady duty" in output
    assert "Next step: Write one goal" in output
    assert "Scripture grounding: The Bhagavad Gita" in output
    assert _synthesis_rejection_reason("How to be disciplined?", [{"keywords": ["discipline", "duty"]}], output) == ""


def test_clean_synthesis_output_merges_duplicate_next_step_sections():
    output = _clean_synthesis_output(
        "\n".join(
            [
                "Summary: Your friend may need time, but you can stay truthful and gentle.",
                "Reflection: Anger after hearing the truth can be painful.",
                "Judgement: Do not chase or punish; choose patience and honesty.",
                "Next step: Send one short apology that accepts the hurt.",
                "Next step: Give your friend space and ask to talk when they are ready.",
                "Scripture grounding: The retrieved scriptures support truth and restraint.",
            ]
        )
    )

    assert output.count("Next step:") == 1
    assert "Send one short apology" in output
    assert "Give your friend space" in output


def test_synthesis_rejects_crossed_scripture_quote_attribution():
    citations = [
        {
            "id": "c3",
            "faith": "Christianity",
            "source": "Holy Bible: Romans",
            "chapter": "Chapter 12",
            "verse": "Verse 21",
            "translation": "Do not be overcome by evil, but overcome evil with good.",
            "keywords": ["betrayal", "retaliation", "forgiveness", "anger"],
        },
        {
            "id": "h2",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 63",
            "translation": "From anger arises complete delusion, and from delusion bewilderment of memory.",
            "keywords": ["anger", "rationality", "delusion", "mind"],
        },
    ]
    pathway = (
        "Summary: Do not retaliate; protect yourself with truth and calm boundaries.\n"
        "Reflection: Betrayal can make anger feel strong.\n"
        "Judgement: Choose truthful boundaries instead of revenge.\n"
        "Next step: Write down what was said and limit contact if needed.\n"
        "Scripture grounding: The Bhagavad Gita also advises us to \"overcome evil with good\" "
        "(Holy Bible: Romans Chapter 12:Verse 21), which supports responding with truth. "
        "The Dhammapada reminds us that hatred does not end hatred."
    )

    assert _synthesis_rejection_reason("betrayed and angry; revenge or forgive?", citations, pathway) == "scripture_source_mismatch"


def test_synthesis_allows_correct_scripture_quote_attribution():
    citations = [
        {
            "id": "c3",
            "faith": "Christianity",
            "source": "Holy Bible: Romans",
            "chapter": "Chapter 12",
            "verse": "Verse 21",
            "translation": "Do not be overcome by evil, but overcome evil with good.",
            "keywords": ["betrayal", "retaliation", "forgiveness", "anger"],
        },
        {
            "id": "h2",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 63",
            "translation": "From anger arises complete delusion, and from delusion bewilderment of memory.",
            "keywords": ["anger", "rationality", "delusion", "mind"],
        },
    ]
    pathway = (
        "Summary: Do not retaliate; protect yourself with truth and calm boundaries.\n"
        "Reflection: Betrayal can make anger feel strong.\n"
        "Judgement: Choose truthful boundaries instead of revenge.\n"
        "Next step: Write down what was said and limit contact if needed.\n"
        "Scripture grounding: Holy Bible: Romans teaches \"overcome evil with good,\" which supports not retaliating. "
        "The Bhagavad Gita warns that anger leads to delusion, which supports pausing before action."
    )

    assert _synthesis_rejection_reason("betrayed and angry; revenge or forgive?", citations, pathway) == ""


def test_synthesis_rejects_scripture_reference_outside_grounding_section():
    citations = [
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but not to the fruits of action.",
            "keywords": ["duty", "work", "detachment", "livelihood"],
        },
        {
            "id": "u1",
            "faith": "Hinduism",
            "source": "Isha Upanishad",
            "chapter": "Chapter 1",
            "verse": "Verse 1",
            "translation": "Enjoy through renunciation; do not covet what belongs to another.",
            "keywords": ["renunciation", "joy", "wealth", "detachment"],
        },
    ]
    pathway = "\n".join(
        [
            "Summary: Losing livelihood to automation is frightening, but your response can stay steady.",
            "Reflection: Fear about automation can make the future feel closed.",
            "Judgement: Focus on fulfilling your duties, as suggested by Bhagavad Gita Chapter 2:Verse 47.",
            "Next step: Write down one skill or client relationship you can strengthen today.",
            "Scripture grounding: Bhagavad Gita, Chapter 2, Verse 47 supports focusing on duty without attachment to results. Isha Upanishad, Chapter 1, Verse 1 supports loosening fear around possession and security.",
        ]
    )

    assert _synthesis_rejection_reason("Will automation make me lose my livelihood?", citations, pathway) == "scripture_reference_outside_grounding"


def test_synthesis_allows_scripture_references_only_in_grounding_section():
    citations = [
        {
            "id": "h1",
            "faith": "Hinduism",
            "source": "Bhagavad Gita",
            "chapter": "Chapter 2",
            "verse": "Verse 47",
            "translation": "You have a right to perform your prescribed duties, but not to the fruits of action.",
            "keywords": ["duty", "work", "detachment", "livelihood"],
        }
    ]
    pathway = "\n".join(
        [
            "Summary: Losing livelihood to automation is frightening, but your response can stay steady.",
            "Reflection: Fear about automation can make the future feel closed.",
            "Judgement: Focus on what you can control: honest work, preparation, and calm choices.",
            "Next step: Write down one skill or client relationship you can strengthen today.",
            "Scripture grounding: Bhagavad Gita, Chapter 2, Verse 47 supports focusing on duty without attachment to results.",
        ]
    )

    assert _synthesis_rejection_reason("Will automation make me lose my livelihood?", citations, pathway) == ""


def test_clean_synthesis_output_merges_duplicate_summary_sections():
    output = _clean_synthesis_output(
        "\n".join(
            [
                "One-line summary: Be steady and kind in each role.",
                "Reflection: Many roles can feel heavy.",
                "Judgement: Choose goodwill without losing your limits.",
                "Next step: Pick one caring action today.",
                "Scripture grounding: The retrieved scriptures support goodwill and duty.",
                "One-line summary: To be a good wife, mom, daughter, sister, friend, and neighbor, practice goodwill.",
            ]
        )
    )

    assert output.count("Summary:") == 1
    assert "One-line summary:" not in output
    assert "Be steady and kind" in output
    assert "practice goodwill" in output


def test_prompt_instruction_as_summary_triggers_synthesis_rejection():
    pathway = "\n".join(
        [
            "One-line summary: answer the dilemma directly in one compact sentence.",
            "Reflection: This is about dropshipping and scam concerns.",
            "Judgement: Choose transparent selling and customer accountability.",
            "Next step: Check supplier reliability, shipping times, refunds, and disclosures.",
            "Scripture grounding: The retrieved scriptures point toward integrity and business morality.",
        ]
    )

    cleaned = _clean_synthesis_output(pathway)

    assert "answer the dilemma directly" not in cleaned
    assert _should_reject_synthesis("is dropshipping a scam?", [{"keywords": ["integrity", "business"]}], cleaned)
    assert _synthesis_rejection_reason("is dropshipping a scam?", [{"keywords": ["integrity", "business"]}], cleaned)


def test_prompt_like_response_triggers_synthesis_rejection():
    pathway = "\n".join(
        [
            "One-line summary: Treat is dropshipping a scam as a business-integrity question, not just a profit question.",
            "Reflection: A business model is not automatically wrong.",
            "Judgement: Choose transparent selling and customer accountability.",
            "Next step: Check supplier reliability, shipping times, refunds, and disclosures.",
            "Scripture grounding: The retrieved scriptures point toward integrity and business morality.",
        ]
    )

    assert _should_reject_synthesis("is dropshipping a scam?", [{"keywords": ["integrity", "business"]}], pathway)
    assert _synthesis_rejection_reason("is dropshipping a scam?", [{"keywords": ["integrity", "business"]}], pathway) == "prompt_like_response"


def test_synthesis_rejects_mom_drift_for_friend_dilemma_after_pii_redaction():
    dilemma = "I argued with my friend [NAME_REDACTED] and her phone is [PHONE_REDACTED]. I feel guilty. What should I do?"
    citations = [
        {
            "source": "Dhammapada",
            "faith": "Buddhism",
            "keywords": ["friendship", "compassion"],
        }
    ]
    pathway = "\n".join(
        [
            "Summary: Apologize to your friend with honesty and care.",
            "Reflection: It is painful to argue with your mom and still feel guilty.",
            "Judgement: Choose humility and repair with your mom.",
            "Next step: Send your mom one short apology today.",
            "Scripture grounding: Dhammapada supports compassion and restraint.",
        ]
    )

    assert _synthesis_rejection_reason(dilemma, citations, pathway) == "unsupported_relationship_drift"
    assert _should_reject_synthesis(dilemma, citations, pathway)
