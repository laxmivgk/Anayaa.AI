import pytest

from app.agents.pipeline_errors import SynthesisRejectedError
from app.llm.generator import (
    SYNTHESIS_SYSTEM_PROMPT,
    _build_synthesis_prompt,
    _clean_synthesis_output,
    _is_caregiver_burnout_dilemma,
    _relationship_role_groups,
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
    assert "one concrete action, one preparation detail" in SYNTHESIS_SYSTEM_PROMPT
    assert "Do not make the whole Next step only writing, documenting, or gathering evidence" in SYNTHESIS_SYSTEM_PROMPT
    assert "Citation anchors:" in prompt
    assert "Isha Upanishad, Chapter 1, Verse 1 anchors: stewardship, renunciation" in prompt
    assert "name every exact source from Citation anchors and reuse at least one anchor keyword from each" in SYNTHESIS_SYSTEM_PROMPT
    assert "Keep scripture names, chapter numbers, verse numbers, and citation labels only in Scripture grounding" in SYNTHESIS_SYSTEM_PROMPT
    assert "never mix sources" in SYNTHESIS_SYSTEM_PROMPT
    assert "if a sentence quotes or references Romans, the sentence subject must be Romans or Holy Bible" in SYNTHESIS_SYSTEM_PROMPT
    assert "Write exactly these 5 labeled sections" not in prompt
    assert "Start with a practical verb" not in prompt
    assert "situation-specific moral stance" not in SYNTHESIS_SYSTEM_PROMPT


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
