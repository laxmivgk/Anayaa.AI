from app.llm.generator import (
    _build_synthesis_prompt,
    _clean_synthesis_output,
    _is_caregiver_burnout_dilemma,
    _should_reject_synthesis,
    _synthesis_rejection_reason,
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

    assert "Judgement: say what choice seems wisest and kindest." in prompt
    assert "Next step: give one concrete, stable action" in prompt
    assert "Citation anchors:" in prompt
    assert "Isha Upanishad Chapter 1:Verse 1 anchors: stewardship, renunciation" in prompt
    assert "name two exact sources from Citation anchors and reuse at least one anchor keyword from each" in prompt
    assert "Start with a practical verb" not in prompt
    assert "situation-specific moral stance" not in prompt


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
    assert "treat exhaustion, hopelessness, and 'giving up' as the urgent center" in prompt
    assert "must not start with business finances, debt tracking, saving money, or productivity" in prompt
    assert "contact one real person today" in prompt
    assert "parent-care coverage" in prompt
    assert "local emergency or crisis support now" in prompt


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

    assert output.startswith("One-line summary: Dropshipping is not automatically a scam")
    assert "Dilemma:" not in output
    assert "Citation anchors:" not in output
    assert "anchors: duty" not in output
    assert "Write exactly these" not in output
    assert "Use simple everyday words" not in output


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
