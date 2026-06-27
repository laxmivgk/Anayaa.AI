import time

from app.observability.latency import AgentLatencyTracker


def test_agent_latency_tracker_records_completed_and_skipped_agents():
    tracker = AgentLatencyTracker(request_id="req_test")

    with tracker.track("Planner", category="llm", metadata={"modelRole": "planner"}):
        time.sleep(0.002)
    tracker.mark("Synthesizer", category="llm", metadata={"reason": "context_insufficient"})

    snapshot = tracker.snapshot()

    assert snapshot["requestId"] == "req_test"
    assert snapshot["totalDurationMs"] >= 0
    assert [row["agent"] for row in snapshot["agents"]] == ["Planner", "Synthesizer"]
    assert snapshot["agents"][0]["sequence"] == 1
    assert snapshot["agents"][0]["category"] == "llm"
    assert snapshot["agents"][0]["status"] == "completed"
    assert snapshot["agents"][0]["durationMs"] >= 0
    assert snapshot["agents"][0]["metadata"] == {"modelRole": "planner"}
    assert snapshot["agents"][1]["status"] == "skipped"
    assert snapshot["agents"][1]["durationMs"] == 0


def test_agent_latency_tracker_records_error_status():
    tracker = AgentLatencyTracker(request_id="req_error")

    try:
        with tracker.track("McpRetriever", category="tool"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert tracker.snapshot()["agents"][0]["status"] == "error"
