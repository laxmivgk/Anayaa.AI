from app.llm.generator import _build_grounded_fallback_summary, _build_synthesis_prompt


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
            }
        ],
        "",
    )

    assert "Judgement: say what choice seems wisest and kindest." in prompt
    assert "Next step: give one concrete, stable action" in prompt
    assert "Start with a practical verb" not in prompt
    assert "situation-specific moral stance" not in prompt


def test_grounded_fallback_uses_different_judgment_and_next_step_text():
    summary = _build_grounded_fallback_summary(
        "how can I save the environment with a busy life?",
        [{"keywords": ["sharing", "greed", "sustainable"]}],
    )
    sections = dict(line.split(": ", 1) for line in summary.splitlines() if ": " in line)

    assert sections["Judgement"] != sections["Next step"]
    assert sections["Judgement"] == "Choose the action that is honest, kind, and least harmful."
    assert sections["Next step"].startswith("Write ")
