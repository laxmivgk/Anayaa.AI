"""Structured pipeline outcomes when context or quality thresholds are not met."""
from __future__ import annotations

from typing import Any


def _failed_dimension_names(audit: dict[str, Any], min_score: int) -> list[str]:
    failed = [
        str(name)
        for name in audit.get("failedDimensions", [])
        if str(name).strip()
    ]
    for name, value in audit.get("scores", {}).items():
        if value < min_score and name not in failed:
            failed.append(name)
    return failed


def _friendly_failure_areas(failed: list[str]) -> list[str]:
    labels = {
        "citation_grounding": "scripture grounding",
        "context_grounding": "scripture grounding",
        "grounding_contract": "scripture grounding",
        "query_relevance": "question focus",
        "dharma_alignment": "dharma alignment",
        "faithfulness": "scripture faithfulness",
        "harmlessness": "safety",
        "privacy": "privacy",
    }
    areas: list[str] = []
    for name in failed:
        label = labels.get(name, name.replace("_", " "))
        if label not in areas:
            areas.append(label)
    return areas


def build_quality_failure_user_message(audit: dict[str, Any], min_score: int) -> str:
    failed_raw = _failed_dimension_names(audit, min_score)
    failed_display = _friendly_failure_areas(failed_raw)

    if "harmlessness" in failed_raw:
        return (
            "Anayaa generated a draft, but it cannot be shown as final guidance because the safety review flagged "
            "possible harmful or retaliatory advice. Use The Interactive Guidance to review the proposed concepts "
            "and scriptures, remove any revenge or retaliation framing, and compile guidance again around lawful "
            "protection, documentation, calm boundaries, and non-retaliation."
        )

    if "privacy" in failed_raw:
        return (
            "Anayaa generated a draft, but it cannot be shown as final guidance because the privacy review found "
            "possible exposure of personal identifiers. Human approval cannot override the privacy gate. "
            "Remove personal details, keep the dilemma general, and compile guidance again. "
            f"Areas needing improvement: {', '.join(failed_display) or 'privacy'}."
        )

    if "grounding_contract" in failed_raw or "citation_grounding" in failed_raw or "context_grounding" in failed_raw:
        return (
            "Anayaa retrieved scripture citations, but the drafted guidance did not connect its final advice clearly "
            "enough to at least two scripture passages. Try adding a little more context about the situation, or use "
            "The Interactive Guidance to choose scriptures that directly match your dilemma, then compile guidance again."
        )

    return (
        "Anayaa drafted a response, but it needs one more review before it can be shown as final guidance. "
        f"Areas needing improvement: {', '.join(failed_display) or 'general alignment'}. "
        "Use The Interactive Guidance to adjust concepts or scripture selections, then compile the guidance again."
    )


def build_hitl_compile_failure_user_message(audit: dict[str, Any], min_score: int) -> str:
    failed_raw = _failed_dimension_names(audit, min_score)
    failed_display = _friendly_failure_areas(failed_raw)

    if "harmlessness" in failed_raw:
        return (
            "Anayaa used the reviewed scriptures, but the compiled draft still cannot be shown because the safety "
            "review flagged possible harmful or retaliatory advice. Adjust the concepts toward lawful protection, "
            "documentation, calm boundaries, and non-retaliation, then compile again."
        )

    if "privacy" in failed_raw:
        return (
            "Anayaa used the reviewed scriptures, but the compiled draft still cannot be shown because the privacy "
            "review found possible personal identifiers. Remove personal details, keep the dilemma general, and "
            "compile again."
        )

    if "grounding_contract" in failed_raw or "citation_grounding" in failed_raw or "context_grounding" in failed_raw:
        return (
            "Anayaa used the scriptures selected in Interactive Guidance, but the compiled draft still did not "
            "connect its final advice clearly enough to at least two selected passages. Select scriptures with a "
            "closer connection to the dilemma, or add one more specific detail about the situation, then compile again."
        )

    return (
        "Anayaa used the reviewed concepts and scriptures, but the compiled draft still needs one more review before "
        f"it can be shown as final guidance. Areas needing improvement: "
        f"{', '.join(failed_display) or 'general alignment'}. "
        "Adjust the selections, then compile again."
    )


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


def build_planner_unavailable_response(
    *,
    dilemma: str,
    request_id: str,
    optimizer: dict[str, Any],
    eco_breakdown: list[dict[str, Any]],
    power_metrics: dict[str, Any],
    detail: str,
) -> dict[str, Any]:
    return {
        "status": "planner_unavailable",
        "userMessage": (
            "The strategic planner is unavailable right now, so Anayaa cannot safely choose retrieval concepts "
            "or continue to scripture grounding. Please check that the planner LLM is running and try again."
        ),
        "failureReason": "planner_service_unavailable",
        "plannerError": detail,
        "originalQuery": dilemma,
        "compressedQuery": optimizer.get("compressedQuery"),
        "compressionMetrics": optimizer.get("compressionMetrics"),
        "keywords": [],
        "plannerReasoning": None,
        "historySummary": None,
        "toneMsg": None,
        "candidatesCount": 0,
        "rerankedCitations": [],
        "citations": [],
        "moralPathway": None,
        "confidence": 0,
        "powerMetrics": power_metrics,
        "ecoBreakdown": eco_breakdown,
        "retrievalViaMcp": False,
        "hybridSource": None,
        "orchestrator": "google-adk",
        "pipeline": "Google ADK Workflow + MCP Milvus Retrieval",
        "requestId": request_id,
    }


def build_synthesizer_unavailable_response(
    *,
    payload: dict[str, Any],
    request_id: str,
    eco_breakdown: list[dict[str, Any]],
    power_metrics: dict[str, Any],
    detail: str,
    user_message: str | None = None,
) -> dict[str, Any]:
    return {
        "status": "synthesizer_unavailable",
        "userMessage": user_message or (
            "The guidance synthesizer could not produce a reliable final answer right now. "
            "No fallback answer was shown. Please try again, or use The Interactive Guidance to choose clearer concepts and scriptures."
        ),
        "failureReason": "synthesizer_service_unavailable",
        "synthesizerError": detail,
        "originalQuery": payload.get("originalQuery") or payload.get("dilemma"),
        "rewrittenQuery": payload.get("rewrittenQuery"),
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
        "confidence": payload.get("confidence", 0),
        "powerMetrics": power_metrics,
        "ecoBreakdown": eco_breakdown,
        "retrievalViaMcp": payload.get("retrievalViaMcp", False),
        "hybridSource": payload.get("hybridSource"),
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
    return {
        "status": "quality_threshold_not_met",
        "userMessage": build_quality_failure_user_message(audit, min_score),
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
