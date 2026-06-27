from app.observability.plan_trace import build_request_plan_trace


def test_request_plan_trace_keeps_compact_debug_fields():
    trace = build_request_plan_trace(
        {
            "status": "completed",
            "requestId": "req_123",
            "cacheHit": False,
            "plannerReasoning": "Search scripture using: integrity, duty.",
            "executionPlan": ["Step 1", "Step 2"],
            "loopDetails": {"turns": 1, "loopLimit": 2},
            "agentLatencyMetrics": {"workflow": {"totalDurationMs": 1234}},
            "cachePolicy": {"cacheable": True, "reason": "cacheable"},
            "keywords": ["integrity", "duty"],
            "retrievalQueries": ["integrity duty"],
            "candidatesCount": 3,
            "citations": [{"translation": "Do not persist full citation text here."}],
            "retrievalViaMcp": True,
            "hybridSource": "milvus",
            "confidence": 91,
            "moralPathway": "Do not persist full final answer here.",
            "auditScores": {
                "passed": True,
                "failedDimensions": [],
                "judgeModel": "qwen3:4b",
                "judgeFallback": False,
                "auditStatus": "ok",
                "groundingContract": {"passed": True},
            },
        }
    )

    assert trace["requestId"] == "req_123"
    assert trace["executionPlan"] == ["Step 1", "Step 2"]
    assert trace["retrieval"]["citationsCount"] == 1
    assert trace["judge"]["groundingContractPassed"] is True
    assert "moralPathway" not in trace
    assert "citations" not in trace["retrieval"]
