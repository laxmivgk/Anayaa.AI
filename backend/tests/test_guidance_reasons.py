from app.observability.guidance_reasons import build_guidance_reasons


def test_guidance_reasons_are_user_facing_and_citation_grounded():
    reasons = build_guidance_reasons(
        "Is dropshipping a scam if I need money?",
        [
            {
                "faith": "Hinduism",
                "source": "Bhagavad Gita",
                "chapter": "2",
                "verse": "47",
                "translation": "You have a right to perform your duty, but not to the fruits of action.",
                "keywords": ["duty", "integrity"],
            },
            {
                "faith": "Christianity",
                "source": "Holy Bible: Matthew",
                "chapter": "16",
                "verse": "26",
                "translation": "What good is it to gain the world but lose the soul?",
                "keywords": ["wealth", "soul"],
            },
            {
                "faith": "Buddhism",
                "source": "Dhammapada",
                "chapter": "1",
                "verse": "5",
                "translation": "Hatred is never appeased by hatred.",
                "keywords": ["peace", "restraint"],
            },
        ],
    )

    assert 2 <= len(reasons) <= 3
    assert reasons[0]["citation"] == "Bhagavad Gita 2:47"
    assert "duty" in reasons[0]["reason"]
    assert "dropshipping" in reasons[0]["reason"]
    assert "agent" not in " ".join(reason["reason"].lower() for reason in reasons)
    assert "prompt" not in " ".join(reason["reason"].lower() for reason in reasons)


def test_guidance_reasons_require_at_least_two_citations():
    assert build_guidance_reasons("Should I be honest?", [{"source": "Bhagavad Gita"}]) == []


def test_guidance_reasons_use_only_grounded_citation_ids():
    reasons = build_guidance_reasons(
        "Is dropshipping a scam if I need money?",
        [
            {
                "id": "gita-2-47",
                "source": "Bhagavad Gita",
                "chapter": "2",
                "verse": "47",
                "translation": "You have a right to perform your duty.",
                "keywords": ["duty", "integrity"],
            },
            {
                "id": "matthew-16-26",
                "source": "Holy Bible: Matthew",
                "chapter": "16",
                "verse": "26",
                "translation": "What good is it to gain the world but lose the soul?",
                "keywords": ["wealth", "soul"],
            },
            {
                "id": "dhammapada-1-5",
                "source": "Dhammapada",
                "chapter": "1",
                "verse": "5",
                "translation": "Hatred is never appeased by hatred.",
                "keywords": ["peace", "restraint"],
            },
        ],
        audit={"groundingContract": {"groundedCitationIds": ["gita-2-47", "matthew-16-26"]}},
    )

    assert [reason["citation"] for reason in reasons] == ["Bhagavad Gita 2:47", "Holy Bible: Matthew 16:26"]
