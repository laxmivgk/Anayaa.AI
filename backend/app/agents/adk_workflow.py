"""Google ADK multi-step workflow orchestration for Anayaa.AI."""
from __future__ import annotations

import logging
import re
from typing import Any

from google.adk import Runner, Workflow
from google.adk.events import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.workflow import node
from google.genai import types

from app.agents.pipeline_errors import PipelineError, RetrievalError
from app.agents.pipeline_messages import (
    build_insufficient_context_response,
    build_quality_failure_response,
    build_retrieval_unavailable_response,
)
from app.agents.workflow import (
    evaluate_semantic_cache,
    optimize_query,
    rewrite_malformed_query,
    run_strategic_planner,
    store_semantic_cache,
)
from app.config import get_settings
from app.eco.tracker import EcoTracker
from app.llm.generator import generate_moral_pathway
from app.mcp.client import retrieve_via_mcp
from app.memory.redis_cache import RedisCache
from app.observability.audit_logger import persist_audit_log
from app.observability.g_eval_judge import run_g_eval_judge

logger = logging.getLogger(__name__)

_session_service = InMemorySessionService()
_runner: Runner | None = None
_runtime_contexts: dict[str, dict[str, Any]] = {}

QUERY_STOPWORDS = {
    "about",
    "after",
    "again",
    "because",
    "could",
    "their",
    "there",
    "these",
    "those",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "should",
    "need",
    "want",
    "feel",
    "help",
    "handle",
    "without",
    "ensuring",
}

MORAL_QUERY_TERMS = {
    "angry",
    "anger",
    "anxious",
    "anxiety",
    "argue",
    "betray",
    "betrayed",
    "betrayal",
    "blame",
    "business",
    "care",
    "cheat",
    "cheated",
    "company",
    "compassion",
    "confess",
    "conflict",
    "decision",
    "dilemma",
    "duty",
    "fair",
    "forgive",
    "forgiveness",
    "friend",
    "guilt",
    "harm",
    "honest",
    "honesty",
    "hurt",
    "integrity",
    "jealous",
    "kind",
    "lied",
    "lie",
    "lying",
    "moral",
    "peace",
    "relationship",
    "revenge",
    "responsibility",
    "right",
    "selfish",
    "survive",
    "truth",
    "trust",
    "wrong",
}

SCRIPTURE_BRIDGES = {
    "betray": {"betrayal", "retaliation", "forgiveness", "revenge", "patience", "anger"},
    "betrayed": {"betrayal", "retaliation", "forgiveness", "revenge", "patience", "anger"},
    "betrayal": {"betrayal", "retaliation", "forgiveness", "revenge", "patience", "anger"},
    "business": {"business", "fairness", "justice", "integrity", "wealth", "duty", "work"},
    "company": {"business", "wealth", "work", "duty", "responsibility", "hardship", "failure"},
    "financial": {"wealth", "greed", "business", "duty", "work", "hardship", "contentment"},
    "financially": {"wealth", "greed", "business", "duty", "work", "hardship", "contentment"},
    "friend": {"friend", "goodwill", "love", "compassion", "trust"},
    "lied": {"truth", "honesty", "falsehood", "speech"},
    "lie": {"truth", "honesty", "falsehood", "speech"},
    "lying": {"truth", "honesty", "falsehood", "speech"},
    "forgive": {"forgiveness", "mercy", "compassion", "peace"},
    "forgiveness": {"forgiveness", "mercy", "compassion", "peace"},
    "angry": {"anger", "peace", "patience", "restraint"},
    "anger": {"anger", "peace", "patience", "restraint"},
    "anxious": {"anxiety", "worry", "peace", "trust"},
    "anxiety": {"anxiety", "worry", "peace", "trust"},
    "hurt": {"harm", "compassion", "care", "peace"},
    "partner": {"relationship", "fairness", "trust", "integrity", "business", "friend"},
    "revenge": {"revenge", "retaliation", "forgiveness", "patience", "peace", "goodness"},
    "survive": {"hardship", "hope", "ease", "duty", "work", "strength", "responsibility"},
    "trust": {"truth", "faith", "trust", "integrity"},
}


def _runtime_context(ctx) -> dict[str, Any]:
    request_id = ctx.state.get("request_id")
    if not request_id:
        return {}
    return _runtime_contexts.get(str(request_id), {})


def _content_text(node_input: Any) -> str:
    if isinstance(node_input, types.Content):
        parts = []
        for part in node_input.parts or []:
            if part.text:
                parts.append(part.text)
        return "".join(parts).strip()
    if isinstance(node_input, dict):
        return str(node_input.get("query") or node_input.get("dilemma") or node_input)
    return str(node_input or "").strip()


def _top_retrieval_score(reranked: list[dict[str, Any]]) -> float:
    if not reranked:
        return 0.0
    return float(reranked[0].get("score", 0))


def _nested_exception(exc: BaseException, exc_type: type[BaseException]) -> BaseException | None:
    if isinstance(exc, exc_type):
        return exc
    for child in getattr(exc, "exceptions", ()) or ():
        found = _nested_exception(child, exc_type)
        if found:
            return found
    return None


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", query.lower()):
        if term not in QUERY_STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def _is_moral_guidance_query(query: str) -> bool:
    lowered = query.lower()
    if any(phrase in lowered for phrase in ["should i", "is it right", "is it wrong", "what should i do"]):
        return True
    return bool(set(_query_terms(query)) & MORAL_QUERY_TERMS)


def _retrieval_matches_query(query: str, reranked: list[dict[str, Any]]) -> bool:
    terms = _query_terms(query)
    if not terms:
        return False

    expanded_terms: set[str] = set(terms)
    for term in terms:
        expanded_terms.update(SCRIPTURE_BRIDGES.get(term, set()))

    citation_text_parts: list[str] = []
    for item in reranked:
        verse = item.get("verse") or {}
        citation_text_parts.extend(
            [
                str(verse.get("translation", "")),
                str(verse.get("context", "")),
                str(verse.get("source", "")),
                " ".join(str(keyword) for keyword in verse.get("keywords", [])),
            ]
        )
    citation_text = " ".join(citation_text_parts).lower()
    matches = [term for term in expanded_terms if term and term in citation_text]
    return len(matches) >= 1


def _merge_retrieval_results(results: list[dict[str, Any]], top_k: int = 3) -> dict[str, Any]:
    candidates_by_id: dict[str, dict[str, Any]] = {}
    reranked_by_id: dict[str, dict[str, Any]] = {}
    hybrid_sources: list[str] = []
    used_mcp = False

    for result in results:
        used_mcp = used_mcp or bool(result.get("mcp", False))
        source = result.get("hybridSource")
        if source and source not in hybrid_sources:
            hybrid_sources.append(str(source))

        for item in result.get("candidates", []):
            verse = item.get("verse") or {}
            verse_id = verse.get("id")
            if verse_id and item.get("score", 0) > candidates_by_id.get(verse_id, {}).get("score", -1):
                candidates_by_id[verse_id] = item

        for item in result.get("reranked", []):
            verse = item.get("verse") or {}
            verse_id = verse.get("id")
            if verse_id and item.get("score", 0) > reranked_by_id.get(verse_id, {}).get("score", -1):
                reranked_by_id[verse_id] = item

    candidates = sorted(candidates_by_id.values(), key=lambda row: row.get("score", 0), reverse=True)
    reranked = sorted(reranked_by_id.values(), key=lambda row: row.get("score", 0), reverse=True)[:top_k]
    return {
        "hybridSource": "+".join(hybrid_sources) if hybrid_sources else None,
        "candidates": candidates,
        "reranked": reranked,
        "mcp": used_mcp,
    }


def _react_loop_details(payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    audit = payload.get("auditScores") or {}
    turn = int(payload.get("reactTurn") or 1)
    limit = int(payload.get("reactLoopLimit") or settings.react_max_turns)
    needs_more_work = (
        not payload.get("contextSufficient", True)
        or (bool(audit) and not audit.get("passed", False))
    )
    return {
        "mode": "ReAct",
        "turns": turn,
        "maxTurns": limit,
        "turnsLog": payload.get("reactLoopLog", []),
        "loopLimitTriggered": bool(needs_more_work and turn >= limit and not payload.get("retrievalError")),
    }


def _execution_plan(payload: dict[str, Any], audit: dict[str, Any] | None = None) -> list[str]:
    audit = audit or payload.get("auditScores") or {}
    return [
        f"Step 0 [Query Rewriter]: applied={payload.get('queryRewriteApplied', False)}",
        "Step 1 [ADK Optimizer / LLMLingua]: compress already-sanitized and PII-scrubbed query",
        "Step 2 [ADK Planner]: strategic keywords and feedback-aware tone from optimized query",
        "Step 3 [ReAct Reasoner]: decide the next retrieval/synthesis attempt",
        "Step 4 [MCP Retriever / Milvus]: hybrid search + graph + rerank via stdio MCP",
        f"Step 5 [LLM Synthesizer]: {payload.get('synthesisEngine', 'generator')}",
        f"Step 6 [G-Eval Judge + ReAct Observe]: passed={audit.get('passed')}",
    ]


def _is_safe_to_cache(result: dict[str, Any]) -> bool:
    audit = result.get("auditScores") or {}
    return (
        result.get("status") == "completed"
        and bool(audit.get("passed"))
        and bool(result.get("citations"))
        and result.get("moralPathway") is not None
    )


@node(name="planner")
async def planner_node(ctx, node_input) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    state = ctx.state
    dilemma = payload.get("dilemma") or state.get("dilemma") or _content_text(node_input)
    optimized_query = payload.get("compressedQuery") or payload.get("optimizedQuery")
    pg = _runtime_context(ctx).get("pg")
    user_email = state.get("user_email", "anonymous")
    planner = await run_strategic_planner(dilemma, user_email, pg, optimized_query=optimized_query)
    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    if eco:
        eco.track_stage("Planner")
    return {**payload, "dilemma": dilemma, **planner}


@node(name="optimizer")
async def optimizer_node(ctx, node_input: Any) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    optimizer = ctx.state.get("optimizer_preview")
    if not isinstance(optimizer, dict) or optimizer.get("originalQuery") != dilemma:
        optimizer = optimize_query(
            dilemma,
            payload.get("keywords", []),
            payload.get("historySummary", ""),
        )
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco:
            eco.track_stage("QueryOptimizer")
    return {
        **payload,
        **optimizer,
        "originalQuery": ctx.state.get("original_dilemma", dilemma),
        "rewrittenQuery": ctx.state.get("rewritten_dilemma", dilemma),
        "queryRewriteApplied": bool(ctx.state.get("query_rewrite_applied", False)),
        "queryRewriteRules": ctx.state.get("query_rewrite_rules", []),
        "previousContextUsed": bool(ctx.state.get("previous_context_used", False)),
        "previousContextQuestion": ctx.state.get("previous_context_question"),
        "dilemma": dilemma,
        "reactTurn": 0,
        "reactLoopLog": [],
        "reactLoopLimit": get_settings().react_max_turns,
    }


@node(name="react_reason")
async def react_reason_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    """Reason about the next retrieval/synthesis attempt in a bounded ReAct loop."""
    payload = node_input if isinstance(node_input, dict) else {}
    settings = get_settings()
    turn = int(payload.get("reactTurn") or 0) + 1
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    keywords = payload.get("keywords", [])
    audit = payload.get("auditScores") or {}
    hints = audit.get("revision_hints") or []
    failed_dimensions = audit.get("failedDimensions") or []

    reason = "Initial reasoning pass: retrieve scripture context and draft grounded guidance."
    if payload.get("retrievalError"):
        reason = "Retrieval service reported an error; prepare final graceful response."
    elif not payload.get("contextSufficient", True):
        reason = "Observation found weak scripture grounding; broaden retrieval with moral themes and planner keywords."
    elif audit and not audit.get("passed", False):
        reason = "Judge found quality gaps; revise using audit hints before the next attempt."

    query_terms = [term for term in dilemma.split() if len(term) > 3]
    if "query_relevance" in failed_dimensions:
        expansion_terms = [*keywords, *query_terms]
    elif not payload.get("contextSufficient", True):
        expansion_terms = [*keywords, "duty", "compassion", "truth", "harmony"]
    else:
        expansion_terms = [*keywords, *failed_dimensions, *" ".join(hints).split()]
    expansion = " ".join(dict.fromkeys(term.strip().lower() for term in expansion_terms if term and len(term) > 2))
    base_query = dilemma
    react_search_query = f"{base_query} {expansion}".strip() if turn > 1 else base_query

    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    if eco:
        eco.track_stage("ReActReasoner")

    return {
        **payload,
        "reactTurn": turn,
        "reactLoopLimit": settings.react_max_turns,
        "reactReasoning": reason,
        "reactSearchQuery": react_search_query,
        "reactLoopLog": [
            *payload.get("reactLoopLog", []),
            f"Turn {turn} Reason: {reason}",
        ],
    }


@node(name="retriever")
async def retriever_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    payload = node_input if isinstance(node_input, dict) else {}
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    search_query = payload.get("reactSearchQuery") or dilemma
    keywords = payload.get("keywords", [])
    if not _is_moral_guidance_query(dilemma):
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco:
            eco.track_stage("Retriever", confidence=0)
        return {
            **payload,
            "searchQuery": dilemma,
            "retrievalQueries": [dilemma],
            "multiQueryUsed": False,
            "hybridSource": None,
            "candidatesCount": 0,
            "rerankedCitations": [],
            "citations": [],
            "retrievalViaMcp": False,
            "contextSufficient": False,
            "topRetrievalScore": 0,
            "retrievalThreshold": settings.retrieval_confidence_threshold,
            "retrievalBlocked": "out_of_scope_query",
        }

    sub_queries = [
        str(query).strip()
        for query in payload.get("subQueries", [])
        if str(query).strip()
    ]
    use_multi_query = bool(payload.get("multiQueryEnabled")) and int(payload.get("reactTurn") or 1) == 1 and len(sub_queries) > 1
    retrieval_queries = sub_queries[:3] if use_multi_query else [search_query]
    try:
        retrieval_results = [
            await retrieve_via_mcp(query, keywords, limit=6 if use_multi_query else 10, top_k=2 if use_multi_query else 3)
            for query in retrieval_queries
        ]
        retrieval = _merge_retrieval_results(retrieval_results, top_k=3) if use_multi_query else retrieval_results[0]
    except Exception as exc:
        retrieval_error = _nested_exception(exc, RetrievalError)
        if not retrieval_error:
            raise
        logger.warning("MCP retrieval failed for request %s: %s", ctx.state.get("request_id"), retrieval_error)
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco:
            eco.track_stage("Retriever", confidence=0)
        return {
            **payload,
            "searchQuery": " | ".join(retrieval_queries),
            "retrievalQueries": retrieval_queries,
            "multiQueryUsed": use_multi_query,
            "hybridSource": None,
            "candidatesCount": 0,
            "rerankedCitations": [],
            "citations": [],
            "retrievalViaMcp": True,
            "contextSufficient": False,
            "topRetrievalScore": 0,
            "retrievalThreshold": settings.retrieval_confidence_threshold,
            "retrievalError": str(retrieval_error),
        }

    reranked = retrieval.get("reranked", [])
    top_score = _top_retrieval_score(reranked)
    query_supported = _retrieval_matches_query(dilemma, reranked)
    context_sufficient = bool(reranked) and query_supported and top_score >= settings.retrieval_confidence_threshold
    effective_top_score = top_score if query_supported else 0

    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    if eco:
        eco.track_stage("Retriever", confidence=effective_top_score if reranked else 0)

    citations = [(item.get("verse") or {}) for item in reranked] if context_sufficient else []
    pre_synthesis_approval_required = (
        bool(ctx.state.get("hitl_enabled", settings.hitl_enabled))
        and context_sufficient
        and not bool(ctx.state.get("hitl_resume", False))
    )
    return {
        **payload,
        "searchQuery": " | ".join(retrieval_queries),
        "retrievalQueries": retrieval_queries,
        "multiQueryUsed": use_multi_query,
        "hybridSource": retrieval.get("hybridSource"),
        "candidatesCount": len(retrieval.get("candidates", [])),
        "rerankedCitations": reranked,
        "citations": citations,
        "retrievalViaMcp": retrieval.get("mcp", False),
        "contextSufficient": context_sufficient,
        "topRetrievalScore": effective_top_score,
        "rawTopRetrievalScore": top_score,
        "retrievalThreshold": settings.retrieval_confidence_threshold,
        "retrievalBlocked": None if query_supported else "retrieval_not_relevant_to_query",
        "preSynthesisApprovalRequired": pre_synthesis_approval_required,
    }


@node(name="synthesize")
async def synthesize_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    if not payload.get("contextSufficient", True):
        return {**payload, "moralPathway": None, "quantizedMetrics": None, "synthesisEngine": None}
    if payload.get("preSynthesisApprovalRequired"):
        return {**payload, "moralPathway": None, "quantizedMetrics": None, "synthesisEngine": None}

    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    citations = payload.get("citations") or []
    tone_msg = payload.get("toneMsg", "")

    pathway, metrics = await generate_moral_pathway(dilemma, citations, tone_msg)
    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    reranked = payload.get("rerankedCitations") or []
    if eco:
        eco.track_stage("Synthesizer", confidence=reranked[0].get("score", 0) if reranked else 0)
    return {
        **payload,
        "moralPathway": pathway,
        "quantizedMetrics": metrics,
        "synthesisEngine": metrics.get("engine"),
    }


@node(name="judge")
async def judge_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    if not payload.get("contextSufficient", True):
        return {**payload, "auditScores": None, "confidence": payload.get("topRetrievalScore", 0)}
    if payload.get("preSynthesisApprovalRequired"):
        reranked = payload.get("rerankedCitations") or []
        confidence = reranked[0].get("score", 0) if reranked else payload.get("topRetrievalScore", 0)
        return {**payload, "auditScores": None, "confidence": confidence}

    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    citations = payload.get("citations") or []
    pathway = payload.get("moralPathway") or ""
    audit = run_g_eval_judge(dilemma, citations, pathway)
    pg = _runtime_context(ctx).get("pg")
    request_id = ctx.state.get("request_id")
    await persist_audit_log(pg, request_id, audit)

    reranked = payload.get("rerankedCitations") or []
    confidence = reranked[0].get("score", 0) if reranked else 0
    return {**payload, "auditScores": audit, "confidence": confidence}


@node(name="react_observe")
async def react_observe_node(ctx, node_input: dict[str, Any]) -> Event:
    """Observe the latest attempt and route either back to reasoning or to finalization."""
    payload = node_input if isinstance(node_input, dict) else {}
    settings = get_settings()
    turn = int(payload.get("reactTurn") or 1)
    audit = payload.get("auditScores") or {}
    context_sufficient = bool(payload.get("contextSufficient", True))
    audit_passed = bool(audit.get("passed", False))
    retrieval_error = payload.get("retrievalError")
    retrieval_blocked = payload.get("retrievalBlocked")

    route = "finalize"
    observation = "Observation: quality threshold passed; finalize response."
    if retrieval_error:
        observation = "Observation: retrieval service failed; finalize with a graceful retrieval message."
    elif retrieval_blocked:
        observation = f"Observation: retrieval blocked because {retrieval_blocked}; finalize without synthesis."
    elif not context_sufficient:
        observation = "Observation: retrieved context was insufficient."
        if settings.react_loop_enabled and turn < settings.react_max_turns:
            route = "retry"
            observation += " Retry with broader moral search terms."
        else:
            observation += " Finalize because the loop limit was reached."
    elif audit and not audit_passed:
        observation = f"Observation: judge failed dimensions {audit.get('failedDimensions', [])}."
        if settings.react_loop_enabled and turn < settings.react_max_turns:
            route = "retry"
            observation += " Retry with judge revision hints."
        else:
            observation += " Finalize because the loop limit was reached."

    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    if eco:
        eco.track_stage("ReActObserve", confidence=payload.get("confidence", 0))

    next_payload = {
        **payload,
        "reactRoute": route,
        "reactObservation": observation,
        "reactLoopLog": [
            *payload.get("reactLoopLog", []),
            f"Turn {turn} Observe: {observation}",
        ],
    }
    return Event(output=next_payload, route=route)


@node(name="finalize")
async def finalize_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    settings = get_settings()
    request_id = ctx.state.get("request_id")
    runtime = _runtime_context(ctx)
    eco: EcoTracker | None = runtime.get("eco")
    redis: RedisCache | None = runtime.get("redis")
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")

    if eco:
        eco.track_stage("GEvalJudge")
        power = eco.audit_power_footprint(False, payload.get("confidence", 0))
        totals = eco.totals()
    else:
        power = {}
        totals = {"ecoBreakdown": []}

    if not payload.get("contextSufficient", True):
        retrieval_payload = {
            "candidates": [],
            "reranked": payload.get("rerankedCitations", []),
            "mcp": payload.get("retrievalViaMcp", False),
            "hybridSource": payload.get("hybridSource"),
        }
        if payload.get("retrievalError"):
            result = build_retrieval_unavailable_response(
                dilemma=payload.get("dilemma") or ctx.state.get("dilemma", ""),
                request_id=request_id,
                keywords=payload.get("keywords", []),
                optimizer=payload,
                planner=payload,
                retrieval=retrieval_payload,
                eco_breakdown=totals.get("ecoBreakdown", []),
                power_metrics=power,
                detail=str(payload.get("retrievalError")),
            )
        else:
            result = build_insufficient_context_response(
                dilemma=payload.get("dilemma") or ctx.state.get("dilemma", ""),
                request_id=request_id,
                keywords=payload.get("keywords", []),
                optimizer=payload,
                planner=payload,
                retrieval=retrieval_payload,
                eco_breakdown=totals.get("ecoBreakdown", []),
                power_metrics=power,
                top_score=float(payload.get("topRetrievalScore", 0)),
                threshold=float(payload.get("retrievalThreshold", settings.retrieval_confidence_threshold)),
            )
            if payload.get("retrievalBlocked") == "out_of_scope_query":
                result["failureReason"] = "out_of_scope_query"
                result["userMessage"] = (
                    "This does not look like a moral dilemma or relationship decision that Anayaa can ground in "
                    "scripture. Please ask about a real choice, conflict, responsibility, or value you are weighing."
                )
            elif payload.get("retrievalBlocked") == "retrieval_not_relevant_to_query":
                result["failureReason"] = "retrieval_not_relevant_to_query"
                result["userMessage"] = (
                    "Anayaa found scripture passages, but they were not closely related to your actual question. "
                    "To avoid an unsupported answer, please rephrase the dilemma with clearer moral themes."
                )
        result["pipeline"] = "Google ADK ReAct Workflow + MCP Milvus Retrieval"
        result["originalQuery"] = payload.get("originalQuery") or ctx.state.get("original_dilemma") or result.get("originalQuery")
        result["rewrittenQuery"] = payload.get("rewrittenQuery") or ctx.state.get("rewritten_dilemma")
        result["queryRewriteApplied"] = payload.get("queryRewriteApplied", False)
        result["queryRewriteRules"] = payload.get("queryRewriteRules", [])
        result["previousContextUsed"] = payload.get("previousContextUsed", False)
        result["previousContextQuestion"] = payload.get("previousContextQuestion")
        result["executionPlan"] = _execution_plan(payload)
        result["loopDetails"] = _react_loop_details(payload)
        return result

    if payload.get("preSynthesisApprovalRequired"):
        candidate_items = payload.get("rerankedCitations") or payload.get("candidates") or []
        selected_verse_ids = [
            str((item.get("verse") or {}).get("id"))
            for item in payload.get("rerankedCitations", [])
            if (item.get("verse") or {}).get("id")
        ]
        result = {
            "pipeline": "Google ADK ReAct Workflow + MCP Milvus Retrieval",
            "orchestrator": "google-adk",
            "cacheHit": False,
            "status": "awaiting_pre_synthesis_approval",
            "userMessage": "Review the retrieval plan before Anayaa synthesizes the final guidance.",
            "originalQuery": payload.get("originalQuery") or ctx.state.get("original_dilemma", dilemma),
            "rewrittenQuery": payload.get("rewrittenQuery") or ctx.state.get("rewritten_dilemma", dilemma),
            "queryRewriteApplied": payload.get("queryRewriteApplied", False),
            "queryRewriteRules": payload.get("queryRewriteRules", []),
            "previousContextUsed": payload.get("previousContextUsed", False),
            "previousContextQuestion": payload.get("previousContextQuestion"),
            "compressedQuery": payload.get("compressedQuery"),
            "compressionMetrics": payload.get("compressionMetrics"),
            "keywords": payload.get("keywords", []),
            "plannerReasoning": payload.get("reasoning"),
            "historySummary": payload.get("historySummary"),
            "toneMsg": payload.get("toneMsg"),
            "candidatesCount": payload.get("candidatesCount", 0),
            "rerankedCitations": payload.get("rerankedCitations", []),
            "citations": payload.get("citations", []),
            "retrievalQueries": payload.get("retrievalQueries", []),
            "multiQueryUsed": payload.get("multiQueryUsed", False),
            "moralPathway": None,
            "quantizedMetrics": None,
            "synthesisEngine": None,
            "confidence": payload.get("confidence", 0),
            "powerMetrics": power,
            "ecoBreakdown": totals.get("ecoBreakdown", []),
            "auditScores": None,
            "retrievalViaMcp": payload.get("retrievalViaMcp", False),
            "hybridSource": payload.get("hybridSource"),
            "executionPlan": _execution_plan(payload),
            "loopDetails": _react_loop_details(payload),
            "requestId": request_id,
            "hitl": {
                "workflowRunId": request_id,
                "stage": "pre_synthesis_verification",
                "approvalTitle": "Pre-Synthesis Verification",
                "instructions": (
                    "Adjust concepts, deselect irrelevant verses, or manually add a verse before "
                    "the Synthesizer Agent compiles the final moral pathway."
                ),
                "proposedKeywords": payload.get("keywords", []),
                "candidateScriptures": candidate_items,
                "selectedVerseIds": selected_verse_ids,
            },
        }
        return result

    audit = payload.get("auditScores") or {}
    if not audit.get("passed", False):
        result = build_quality_failure_response(
            payload=payload,
            audit=audit,
            request_id=request_id,
            eco_breakdown=totals.get("ecoBreakdown", []),
            power_metrics=power,
            min_score=settings.audit_min_score,
        )
        result["pipeline"] = "Google ADK ReAct Workflow + MCP Milvus Retrieval"
        result["originalQuery"] = payload.get("originalQuery") or ctx.state.get("original_dilemma")
        result["rewrittenQuery"] = payload.get("rewrittenQuery") or ctx.state.get("rewritten_dilemma")
        result["queryRewriteApplied"] = payload.get("queryRewriteApplied", False)
        result["queryRewriteRules"] = payload.get("queryRewriteRules", [])
        result["previousContextUsed"] = payload.get("previousContextUsed", False)
        result["previousContextQuestion"] = payload.get("previousContextQuestion")
        result["executionPlan"] = _execution_plan(payload, audit)
        result["loopDetails"] = _react_loop_details(payload)
        return result

    hitl_enabled = bool(ctx.state.get("hitl_enabled", settings.hitl_enabled))
    reranked = payload.get("rerankedCitations") or []
    citations = payload.get("citations") or []

    result = {
        "pipeline": "Google ADK ReAct Workflow + MCP Milvus Retrieval",
        "orchestrator": "google-adk",
        "cacheHit": False,
        "status": "completed",
        "originalQuery": payload.get("originalQuery") or ctx.state.get("original_dilemma", dilemma),
        "rewrittenQuery": payload.get("rewrittenQuery") or ctx.state.get("rewritten_dilemma", dilemma),
        "queryRewriteApplied": payload.get("queryRewriteApplied", False),
        "queryRewriteRules": payload.get("queryRewriteRules", []),
        "previousContextUsed": payload.get("previousContextUsed", False),
        "previousContextQuestion": payload.get("previousContextQuestion"),
        "compressedQuery": payload.get("compressedQuery"),
        "compressionMetrics": payload.get("compressionMetrics"),
        "keywords": payload.get("keywords", []),
        "plannerReasoning": payload.get("reasoning"),
        "historySummary": payload.get("historySummary"),
        "toneMsg": payload.get("toneMsg"),
        "candidatesCount": payload.get("candidatesCount", 0),
        "rerankedCitations": reranked,
        "citations": citations,
        "retrievalQueries": payload.get("retrievalQueries", []),
        "multiQueryUsed": payload.get("multiQueryUsed", False),
        "moralPathway": payload.get("moralPathway"),
        "quantizedMetrics": payload.get("quantizedMetrics"),
        "synthesisEngine": payload.get("synthesisEngine"),
        "confidence": payload.get("confidence", 0),
        "powerMetrics": power,
        "ecoBreakdown": totals.get("ecoBreakdown", []),
        "auditScores": audit,
        "retrievalViaMcp": payload.get("retrievalViaMcp", False),
        "hybridSource": payload.get("hybridSource"),
        "executionPlan": _execution_plan(payload, audit),
        "loopDetails": _react_loop_details(payload),
        "requestId": request_id,
    }

    if hitl_enabled:
        result["status"] = "awaiting_approval"
        result["hitl"] = {
            "workflowRunId": request_id,
            "draftPathway": payload.get("moralPathway"),
            "auditScores": audit,
        }

    cache_key = payload.get("cacheKey")
    if redis and cache_key and _is_safe_to_cache(result):
        await store_semantic_cache(redis, cache_key, result)

    return result


def _build_workflow() -> Workflow:
    return Workflow(
        name="anayaa_dharma_workflow",
        description="Bounded ReAct dharma guidance with MCP Milvus retrieval and LLM synthesis",
        edges=[
            (
                "START",
                optimizer_node,
                planner_node,
                react_reason_node,
                retriever_node,
                synthesize_node,
                judge_node,
                react_observe_node,
                {"retry": react_reason_node, "finalize": finalize_node},
            ),
        ],
    )


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        _runner = Runner(
            agent=_build_workflow(),
            app_name="anayaa",
            session_service=_session_service,
        )
    return _runner


async def run_adk_pipeline(
    dilemma: str,
    user_email: str,
    pg,
    redis: RedisCache,
    eco: EcoTracker,
    hitl_enabled: bool = True,
    milvus=None,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the Google ADK workflow for a user dilemma."""
    del milvus  # Milvus is accessed through the MCP server subprocess

    settings = get_settings()
    if not settings.adk_enabled:
        raise PipelineError(
            "ADK orchestration is disabled (ADK_ENABLED=false).",
            user_message="The ADK workflow is disabled. Set ADK_ENABLED=true to process queries.",
            code="adk_disabled",
        )

    eco.track_stage("SanitizeGate")
    rewrite = rewrite_malformed_query(dilemma, previous_context=previous_context)
    rewritten_dilemma = rewrite["rewrittenQuery"]
    optimizer_preview = {
        **optimize_query(rewritten_dilemma, []),
        **rewrite,
    }
    eco.track_stage("QueryOptimizer")

    cached = None if hitl_enabled else await evaluate_semantic_cache(redis, optimizer_preview["cacheKey"])
    if cached:
        eco.track_stage("CacheReturn", cache_hit=True, confidence=95)
        power = eco.audit_power_footprint(True, 95)
        return {
            **cached,
            "cacheHit": True,
            "orchestrator": "google-adk",
            "originalQuery": rewrite["originalQuery"],
            "rewrittenQuery": rewritten_dilemma,
            "queryRewriteApplied": rewrite["queryRewriteApplied"],
            "queryRewriteRules": rewrite["queryRewriteRules"],
            "previousContextUsed": rewrite["previousContextUsed"],
            "previousContextQuestion": rewrite["previousContextQuestion"],
            "powerMetrics": power,
            "ecoBreakdown": eco.totals()["ecoBreakdown"],
            "requestId": eco.request_id,
        }

    request_id = str(eco.request_id)
    _runtime_contexts[request_id] = {"pg": pg, "redis": redis, "eco": eco}
    try:
        runner = _get_runner()
        session = await _session_service.create_session(
            app_name="anayaa",
            user_id=user_email,
            state={
                "dilemma": rewritten_dilemma,
                "original_dilemma": rewrite["originalQuery"],
                "rewritten_dilemma": rewritten_dilemma,
                "query_rewrite_applied": rewrite["queryRewriteApplied"],
                "query_rewrite_rules": rewrite["queryRewriteRules"],
                "previous_context_used": rewrite["previousContextUsed"],
                "previous_context_question": rewrite["previousContextQuestion"],
                "user_email": user_email,
                "request_id": request_id,
                "hitl_enabled": hitl_enabled,
                "optimizer_preview": optimizer_preview,
            },
        )

        final_payload: dict[str, Any] | None = None
        async for event in runner.run_async(
            user_id=user_email,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=rewritten_dilemma)]),
        ):
            if getattr(event, "output", None) is not None and isinstance(event.output, dict):
                if "status" in event.output or "moralPathway" in event.output or event.author in {"finalize", "anayaa_dharma_workflow"}:
                    final_payload = event.output
    finally:
        _runtime_contexts.pop(request_id, None)

    if not final_payload:
        raise PipelineError(
            "ADK workflow completed without a final payload.",
            user_message="The guidance workflow did not produce a result. Please try again.",
            code="workflow_empty",
        )

    return final_payload
