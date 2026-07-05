from app.security.privacy_scrubber import detect_sensitive_names, scrub_pii, scrub_pii_deep, scrub_pii_response_deep


def test_scrub_pii_redacts_email_phone_and_ssn():
    text = (
        "Contact Lakshmi at lakshmi@example.com or +1 415-555-0101. "
        "The backup identifier is 123-45-6789."
    )

    scrubbed = scrub_pii(text)

    assert "lakshmi@example.com" not in scrubbed
    assert "415-555-0101" not in scrubbed
    assert "123-45-6789" not in scrubbed
    assert "[EMAIL_REDACTED]" in scrubbed
    assert "[PHONE_REDACTED]" in scrubbed
    assert "[SSN_REDACTED]" in scrubbed


def test_scrub_pii_removes_markdown_mailto_url_and_patient_id():
    text = (
        "My personal contact is [david.miller.test@yahoo.com]"
        "(https://www.google.com/url?sa=E&q=mailto%3Adavid.miller.test%40yahoo.com) "
        "and Patient ID: PT-99812."
    )

    scrubbed = scrub_pii(text)

    assert "google.com" not in scrubbed
    assert "mailto" not in scrubbed
    assert "david.miller" not in scrubbed
    assert "PT-99812" not in scrubbed
    assert "[EMAIL_REDACTED]" in scrubbed
    assert "Patient ID: [PATIENT_ID_REDACTED]" in scrubbed


def test_scrub_pii_redacts_friend_name_from_model_facing_text():
    scrubbed = scrub_pii("I argued with my friend lakshmi and feel guilty.")

    assert "lakshmi" not in scrubbed.lower()
    assert scrubbed == "I argued with my friend [NAME_REDACTED] and feel guilty."


def test_scrub_pii_redacts_relation_name_without_my_prefix():
    scrubbed = scrub_pii("I argued with friend Lakshmi and need to apologize.")

    assert "Lakshmi" not in scrubbed
    assert scrubbed == "I argued with friend [NAME_REDACTED] and need to apologize."


def test_scrub_pii_redacts_parent_name_with_mom_label():
    scrubbed = scrub_pii("My mom Sita wants to see me just to get her new clothes.")

    assert "Sita" not in scrubbed
    assert scrubbed == "My mom [NAME_REDACTED] wants to see me just to get her new clothes."


def test_scrub_pii_redacts_multi_token_manager_name():
    names = detect_sensitive_names("How about my manager Sarah Jenkins?")
    scrubbed = scrub_pii("How about my manager Sarah Jenkins?", extra_names=names)

    assert names == ["Sarah Jenkins", "Sarah", "Jenkins"]
    assert "Sarah" not in scrubbed
    assert "Jenkins" not in scrubbed
    assert scrubbed == "How about my manager [NAME_REDACTED]?"


def test_ner_redacts_full_name_without_relationship_pattern():
    names = detect_sensitive_names("Hello, my name is David Miller and I feel hopeless.")
    scrubbed = scrub_pii_response_deep(
        {
            "originalQuery": "Hello, my name is David Miller and I feel hopeless.",
            "moralPathway": "David Miller should contact one trusted person today.",
        },
        extra_names=names,
    )

    assert names == ["David Miller", "David", "Miller"]
    assert "David" not in scrubbed["originalQuery"]
    assert "Miller" not in scrubbed["moralPathway"]
    assert scrubbed["originalQuery"] == "Hello, my name is the other person and I feel hopeless."


def test_output_ner_gate_redacts_model_invented_full_name():
    scrubbed = scrub_pii_response_deep(
        {
            "moralPathway": (
                "David Miller should seek support today. "
                "The Bhagavad Gita supports steady duty."
            ),
        }
    )

    assert "David" not in scrubbed["moralPathway"]
    assert "Miller" not in scrubbed["moralPathway"]
    assert "Bhagavad Gita" in scrubbed["moralPathway"]
    assert scrubbed["moralPathway"].startswith("the other person should seek support")


def test_scrub_pii_redacts_typo_multi_token_manager_name():
    names = detect_sensitive_names("How about my manager Sarah Jenkns?")
    scrubbed = scrub_pii_response_deep(
        {
            "moralPathway": "Sarah Jenkns may need a direct conversation. Jenkns should not be named.",
            "originalQuery": "How about my manager Sarah Jenkns?",
        },
        extra_names=names,
    )

    assert names == ["Sarah Jenkns", "Sarah", "Jenkns"]
    assert "Sarah" not in scrubbed["moralPathway"]
    assert "Jenkns" not in scrubbed["moralPathway"]
    assert "Sarah" not in scrubbed["originalQuery"]
    assert "Jenkns" not in scrubbed["originalQuery"]
    assert scrubbed["originalQuery"] == "How about my manager?"


def test_response_scrub_redacts_model_corrected_manager_surname():
    names = detect_sensitive_names("How about my manager Sarah Jenkns?")
    scrubbed = scrub_pii_response_deep(
        {
            "moralPathway": (
                "You can't change Sarah Jenkins' behavior, but you can focus on your own work.\n"
                "Reflection: It's possible that Sarah Jenkins is under pressure.\n"
                "Judgement: Maintain a professional relationship with Sarah Jenkins while setting boundaries.\n"
                "Next step: Write down incidents where you felt micromanaged by Sarah Jenkins."
            ),
            "originalQuery": "How about my manager Sarah Jenkns?",
        },
        extra_names=names,
    )

    assert "Sarah" not in scrubbed["moralPathway"]
    assert "Jenkins" not in scrubbed["moralPathway"]
    assert "Jenkns" not in scrubbed["originalQuery"]
    assert "the other person's behavior" in scrubbed["moralPathway"]
    assert "the other person is under pressure" in scrubbed["moralPathway"]


def test_scrub_pii_redacts_manager_name_after_is_phrase():
    names = detect_sensitive_names("My manager is Sarah Jenkins and she micromanages me.")
    scrubbed = scrub_pii_response_deep(
        {
            "moralPathway": "Sarah Jenkins keeps checking every task. Sarah Jenkins' behavior is stressful.",
            "originalQuery": "My manager is Sarah Jenkins and she micromanages me.",
        },
        extra_names=names,
    )

    assert names == ["Sarah Jenkins", "Sarah", "Jenkins"]
    assert "Sarah" not in scrubbed["moralPathway"]
    assert "Jenkins" not in scrubbed["moralPathway"]
    assert scrubbed["originalQuery"] == "My manager is the other person and she micromanages me."
    assert "the other person's behavior is stressful" in scrubbed["moralPathway"]


def test_scrub_pii_redacts_name_before_manager_role():
    names = detect_sensitive_names("Sarah Jenkins is my manager and she micromanages me.")
    scrubbed = scrub_pii_response_deep(
        {
            "moralPathway": "Sarah Jenkins may be under pressure, but Sarah Jenkins should not be named.",
            "originalQuery": "Sarah Jenkins is my manager and she micromanages me.",
        },
        extra_names=names,
    )

    assert names == ["Sarah Jenkins", "Sarah", "Jenkins"]
    assert "Sarah" not in scrubbed["moralPathway"]
    assert "Jenkins" not in scrubbed["moralPathway"]
    assert scrubbed["originalQuery"] == "the other person is my manager and she micromanages me."


def test_detect_sensitive_names_from_relation_query():
    assert detect_sensitive_names("My mom Sita wants to see me.") == ["Sita"]


def test_scrub_pii_redacts_detected_name_when_standalone_later():
    names = detect_sensitive_names("My mom Sita wants to see me.")
    scrubbed = scrub_pii("Sita may still be treated with kindness.", extra_names=names)

    assert "Sita" not in scrubbed
    assert scrubbed == "[NAME_REDACTED] may still be treated with kindness."


def test_scrub_pii_does_not_redact_common_verb_after_parent_label():
    text = "My mom wants to see me just to get her new clothes."

    assert scrub_pii(text) == text


def test_scrub_pii_redacts_name_in_meet_again_follow_up():
    scrubbed = scrub_pii("what should I say next when I meet lakshm agan?")

    assert "lakshm" not in scrubbed.lower()
    assert scrubbed == "what should I say next when I meet [NAME_REDACTED] agan?"


def test_scrub_pii_does_not_redact_company_before_role():
    text = "I met Apple CEO the other day."

    assert scrub_pii(text) == text


def test_scrub_pii_redacts_interaction_name_without_relationship_label():
    scrubbed = scrub_pii("I argued with Lakshmi and feel guilty.")

    assert "Lakshmi" not in scrubbed
    assert scrubbed == "I argued with [NAME_REDACTED] and feel guilty."


def test_scrub_pii_redacts_common_place_context():
    scrubbed = scrub_pii("I met my friend in Chennai after work.")

    assert "Chennai" not in scrubbed
    assert scrubbed == "I met my friend in [LOCATION_REDACTED] after work."


def test_scrub_pii_does_not_redact_non_user_spiritual_reference():
    text = "Goddess Lakshmi represents abundance in the tradition."

    assert scrub_pii(text) == text


def test_scrub_pii_does_not_redact_common_words_after_relationships():
    text = "My friend was angry after I told the truth."

    assert scrub_pii(text) == text


def test_scrub_pii_does_not_redact_meet_again_without_name():
    text = "What should I say when we meet again?"

    assert scrub_pii(text) == text


def test_scrub_pii_does_not_redact_interaction_pronoun():
    text = "I talked to him and apologized."

    assert scrub_pii(text) == text


def test_scrub_pii_does_not_redact_action_pronouns():
    text = "She wants to see you and visit you for clothes."

    assert scrub_pii(text) == text


def test_scrub_pii_does_not_redact_verse_friend_of_the_self():
    text = (
        "One must elevate oneself by one's own mind, and not degrade oneself. "
        "For the mind is the friend of the self, and the mind is the enemy of the self as well."
    )

    assert scrub_pii(text) == text


def test_scrub_pii_deep_redacts_nested_payloads():
    payload = {
        "query": "My email is user@example.org",
        "citations": [
            {"context": "Call (650) 555-0199 before the meeting."},
            {"context": "No PII here."},
        ],
        "history": ("SSN 987-65-4321",),
        "count": 2,
    }

    scrubbed = scrub_pii_deep(payload)

    assert scrubbed["query"] == "My email is [EMAIL_REDACTED]"
    assert scrubbed["citations"][0]["context"] == "Call [PHONE_REDACTED] before the meeting."
    assert scrubbed["citations"][1]["context"] == "No PII here."
    assert scrubbed["history"] == ("SSN [SSN_REDACTED]",)
    assert scrubbed["count"] == 2


def test_scrub_pii_response_humanizes_final_guidance_markers():
    payload = {
        "moralPathway": (
            "Summary: You can still show love to your mom [NAME_REDACTED], "
            "but do not let her visit [NAME_REDACTED] only for clothes.\n"
            "Reflection: Sita may be acting from attachment. The Dhammapada reminds us [NAME_REDACTED] hatred is not ended by hatred. "
            "Tell yourself [NAME_REDACTED] you deserve respect."
        ),
        "originalQuery": "My mom Sita wants new clothes.",
    }
    names = detect_sensitive_names(payload["originalQuery"])

    scrubbed = scrub_pii_response_deep(payload, extra_names=names)

    assert "Sita" not in scrubbed["originalQuery"]
    assert "Sita" not in scrubbed["moralPathway"]
    assert scrubbed["originalQuery"] == "My mom wants new clothes."
    assert "[NAME_REDACTED]" not in scrubbed["moralPathway"]
    assert "the other person may be acting" in scrubbed["moralPathway"]
    assert "your mom," in scrubbed["moralPathway"]
    assert "visit you only for clothes" in scrubbed["moralPathway"]
    assert "reminds us that hatred" in scrubbed["moralPathway"]
    assert "Tell yourself that you deserve respect" in scrubbed["moralPathway"]
