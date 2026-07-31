from app.api.routes.query import _transaction_retry_details
from app.memory.streams import log_transaction


def test_transaction_log_persists_retry_attempt_details():
    retry_details = {
        "mode": "ReAct",
        "turns": 2,
        "maxTurns": 2,
        "attempts": 1,
        "recovered": True,
        "loopLimitTriggered": False,
        "events": ["Turn 2 Reason: LLM retry planner: Retry with focused retrieval."],
    }

    log = log_transaction(
        "codex.test@example.com",
        "How can I repair a friendship?",
        2,
        False,
        91,
        0.0,
        retry_details=retry_details,
    )

    assert log["retryAttempts"] == 1
    assert log["retryRecovered"] is True
    assert log["retryDetails"] == retry_details


def test_transaction_log_persists_privacy_trace_without_raw_values():
    privacy_trace = {
        "stage": "pre_planner",
        "totalRedactions": 3,
        "queryRedactionCounts": {"name": 1, "email": 1, "phone": 1},
        "plannerInputScrubbed": True,
    }

    log = log_transaction(
        "codex.test@example.com",
        "My manager [NAME_REDACTED] emailed [EMAIL_REDACTED].",
        1,
        False,
        80,
        0.0,
        privacy_trace=privacy_trace,
    )

    assert log["privacyTrace"] == privacy_trace
    assert "Sarah" not in str(log)
    assert "lakshmi.private@example.com" not in str(log)


def test_transaction_retry_details_extracts_loop_metadata():
    details = _transaction_retry_details(
        {
            "status": "completed",
            "loopDetails": {
                "mode": "ReAct",
                "turns": 2,
                "maxTurns": 2,
                "loopLimitTriggered": False,
                "turnsLog": [
                    "Turn 1 Reason: Initial reasoning pass.",
                    "Turn 2 Reason: Grounding repair retry: existing citations need a clearer Scripture grounding section.",
                ],
            },
        }
    )

    assert details["attempts"] == 1
    assert details["recovered"] is True
    assert details["events"] == [
        "Turn 2 Reason: Grounding repair retry: existing citations need a clearer Scripture grounding section."
    ]
