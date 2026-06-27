"""Persist compact per-request planning traces for local audit/debugging."""
from __future__ import annotations

import json
from typing import Any

from app.memory.postgres import PostgresPool


def build_request_plan_trace(result: dict[str, Any]) -> dict[str, Any]:
    audit = result.get("auditScores") or {}
    return {
        "status": result.get("status"),
        "requestId": result.get("requestId"),
        "cacheHit": bool(result.get("cacheHit", False)),
        "plannerReasoning": result.get("plannerReasoning"),
        "executionPlan": result.get("executionPlan") or [],
        "loopDetails": result.get("loopDetails") or {},
        "agentLatencyMetrics": result.get("agentLatencyMetrics") or {},
        "cachePolicy": result.get("cachePolicy") or {},
        "retrieval": {
            "keywords": result.get("keywords") or [],
            "retrievalQueries": result.get("retrievalQueries") or [],
            "candidatesCount": result.get("candidatesCount", 0),
            "citationsCount": len(result.get("citations") or []),
            "retrievalViaMcp": bool(result.get("retrievalViaMcp", False)),
            "hybridSource": result.get("hybridSource"),
            "confidence": result.get("confidence", 0),
        },
        "judge": {
            "passed": audit.get("passed"),
            "failedDimensions": audit.get("failedDimensions") or [],
            "judgeModel": audit.get("judgeModel"),
            "judgeFallback": bool(audit.get("judgeFallback", False)),
            "auditStatus": audit.get("auditStatus"),
            "groundingContractPassed": (audit.get("groundingContract") or {}).get("passed"),
        },
    }


async def persist_request_plan_trace(pg: PostgresPool | None, request_id: str | None, result: dict[str, Any]) -> None:
    if not pg or not request_id:
        return
    detail = build_request_plan_trace(result)
    duration_ms = None
    workflow = (detail.get("agentLatencyMetrics") or {}).get("workflow") or {}
    if isinstance(workflow.get("totalDurationMs"), (int, float)):
        duration_ms = int(workflow["totalDurationMs"])
    await pg.execute(
        """
        INSERT INTO agent_traces (request_id, stage, detail, duration_ms)
        VALUES ($1, 'request_plan', $2::jsonb, $3)
        """,
        request_id,
        json.dumps(detail, ensure_ascii=True),
        duration_ms,
    )
