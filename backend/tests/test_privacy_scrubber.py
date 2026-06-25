from app.security.privacy_scrubber import scrub_pii, scrub_pii_deep


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
