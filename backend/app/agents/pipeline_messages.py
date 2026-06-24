"""Structured pipeline outcomes when context or quality thresholds are not met."""
from __future__ import annotations

from typing import Any


def build_insufficient_context_response(
    *,
    dilemma: str,
    request_id: str,
    keywords: list[str],
    optimizer: dict[str, Any],
    planner: dict[str, Any],
    retrieval: dict[str, Any],
    eco_breakdown: list[dict[str, Any]],
    power_metrics: dict[str, Any],
    top_score: float,
    threshold: float,
) -> dict[str, Any]:
    return {
        "status": "insufficient_context",
        "userMessage": (
            "We could not find scripture passages that are closely related to your dilemma in our corpus. "
            "This usually means the question is outside the themes covered by the seeded texts, or the wording "
            "is too vague for reliable retrieval. Try rephrasing with clearer moral themes "
            "(for example: duty, compassion, conflict, forgiveness, or anxiety) and ask again."
        ),
        "failureReason": "no_relevant_scripture_context",
        "contextThreshold": threshold,
        "topRetrievalScore": top_score,
        "originalQuery": dilemma,
        "compressedQuery": optimizer.get("compressedQuery"),
        "compressionMetrics": optimizer.get("compressionMetrics"),
        "keywords": keywords,
        "plannerReasoning": planner.get("reasoning"),
        "historySummary": planner.get("historySummary"),
        "toneMsg": planner.get("toneMsg"),
        "candidatesCount": len(retrieval.get("candidates", [])),
        "rerankedCitations": retrieval.get("reranked", []),
        "citations": [],
        "moralPathway": None,
        "confidence": top_score,
        "powerMetrics": power_metrics,
        "ecoBreakdown": eco_breakdown,
        "retrievalViaMcp": retrieval.get("mcp", False),
        "hybridSource": retrieval.get("hybridSource"),
        "orchestrator": "google-adk",
        "pipeline": "Google ADK Workflow + MCP Milvus Retrieval",
        "requestId": request_id,
    }


def build_retrieval_unavailable_response(
    *,
    dilemma: str,
    request_id: str,
    keywords: list[str],
    optimizer: dict[str, Any],
    planner: dict[str, Any],
    retrieval: dict[str, Any],
    eco_breakdown: list[dict[str, Any]],
    power_metrics: dict[str, Any],
    detail: str,
) -> dict[str, Any]:
    return {
        "status": "retrieval_unavailable",
        "userMessage": (
            "Scripture retrieval service is unavailable right now, so Anayaa cannot safely ground a response in "
            "the scripture corpus. Please check that Milvus is enabled, seeded, and not locked by another process, "
            "then try again."
        ),
        "failureReason": "scripture_retrieval_service_unavailable",
        "retrievalError": detail,
        "originalQuery": dilemma,
        "compressedQuery": optimizer.get("compressedQuery"),
        "compressionMetrics": optimizer.get("compressionMetrics"),
        "keywords": keywords,
        "plannerReasoning": planner.get("reasoning"),
        "historySummary": planner.get("historySummary"),
        "toneMsg": planner.get("toneMsg"),
        "candidatesCount": len(retrieval.get("candidates", [])),
        "rerankedCitations": retrieval.get("reranked", []),
        "citations": [],
        "moralPathway": None,
        "confidence": 0,
        "powerMetrics": power_metrics,
        "ecoBreakdown": eco_breakdown,
        "retrievalViaMcp": retrieval.get("mcp", False),
        "hybridSource": retrieval.get("hybridSource"),
        "orchestrator": "google-adk",
        "pipeline": "Google ADK Workflow + MCP Milvus Retrieval",
        "requestId": request_id,
    }


def build_quality_failure_response(
    *,
    payload: dict[str, Any],
    audit: dict[str, Any],
    request_id: str,
    eco_breakdown: list[dict[str, Any]],
    power_metrics: dict[str, Any],
    min_score: int,
) -> dict[str, Any]:
    failed_dims = [
        name.replace("_", " ")
        for name, value in audit.get("scores", {}).items()
        if value < min_score
    ]
    hints = audit.get("revision_hints") or []
    hint_text = f" {' '.join(hints)}" if hints else ""

    return {
        "status": "quality_threshold_not_met",
        "userMessage": (
            "A draft response was generated, but it did not meet our quality and faithfulness thresholds "
            f"for safe dharma guidance (minimum score {min_score}/5 on all audit dimensions). "
            f"Areas needing improvement: {', '.join(failed_dims) or 'general alignment'}.{hint_text} "
            "Please refine your question or try again later."
        ),
        "failureReason": "audit_threshold_not_met",
        "auditMinScore": min_score,
        "originalQuery": payload.get("dilemma"),
        "compressedQuery": payload.get("compressedQuery"),
        "compressionMetrics": payload.get("compressionMetrics"),
        "keywords": payload.get("keywords", []),
        "plannerReasoning": payload.get("reasoning"),
        "historySummary": payload.get("historySummary"),
        "toneMsg": payload.get("toneMsg"),
        "candidatesCount": payload.get("candidatesCount", 0),
        "rerankedCitations": payload.get("rerankedCitations", []),
        "citations": payload.get("citations", []),
        "moralPathway": None,
        "quantizedMetrics": payload.get("quantizedMetrics"),
        "confidence": payload.get("confidence", 0),
        "powerMetrics": power_metrics,
        "ecoBreakdown": eco_breakdown,
        "auditScores": audit,
        "retrievalViaMcp": payload.get("retrievalViaMcp", False),
        "hybridSource": payload.get("hybridSource"),
        "orchestrator": "google-adk",
        "pipeline": "Google ADK Workflow + MCP Milvus Retrieval",
        "requestId": request_id,
    }
