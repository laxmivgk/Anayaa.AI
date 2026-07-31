"""Google ADK multi-step workflow orchestration for Anayaa.AI."""
from __future__ import annotations

import json
import logging
import re
from contextlib import nullcontext
from typing import Any

import httpx
from google.adk import Runner, Workflow
from google.adk.events import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.workflow import node
from google.genai import types

from app.agents.cache_policy import cache_policy_metadata
from app.agents.pipeline_errors import PipelineError, RetrievalError, ServiceUnavailableError
from app.agents.pipeline_messages import (
    build_insufficient_context_response,
    build_planner_unavailable_response,
    build_quality_failure_response,
    build_retrieval_unavailable_response,
    build_synthesizer_unavailable_response,
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
from app.llm.json_repair import extract_json_object
from app.llm.router import select_model
from app.mcp.client import retrieve_via_mcp
from app.memory.redis_cache import RedisCache
from app.observability.audit_logger import persist_audit_log
from app.observability.g_eval_judge import run_g_eval_judge
from app.observability.guidance_reasons import build_guidance_reasons
from app.observability.latency import AgentLatencyTracker
from app.observability.plan_trace import persist_request_plan_trace
from app.retrieval.embeddings import get_embedder
from app.retrieval.hybrid_search import CONCEPT_CLOUDS

logger = logging.getLogger(__name__)

_session_service = InMemorySessionService()
_runner: Runner | None = None

# Live handles stay out of ADK session state because the session service clones serializable payloads.
_runtime_contexts: dict[str, dict[str, Any]] = {}

RETRY_PLANNER_SYSTEM_PROMPT = (
    "You are Anayaa's retry planner for a bounded ReAct loop. "
    "Use only the provided sanitized runtime data. Do not write final user guidance. "
    "If another attempt can improve scripture retrieval or answer quality, return action='retry'; "
    "otherwise return action='finalize'. "
    "For retry, produce one concise retryQuery that preserves the user's original dilemma and adds only relevant focus terms. "
    "Return 2 to 6 lowercase focusKeywords. "
    "Do not include reasoning, rationale, explanation, or final advice. "
    "Return only valid compact JSON with keys: action, retryQuery, focusKeywords."
)

GROUNDING_FAILURE_DIMENSIONS = {"citation_grounding", "context_grounding", "grounding_contract"}
NON_RETRYABLE_FAILURE_DIMENSIONS = {"harmlessness", "privacy"}

QUERY_STOPWORDS = {
    "about",
    "after",
    "again",
    "and",
    "because",
    "can",
    "could",
    "for",
    "from",
    "into",
    "that",
    "the",
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
    "how",
    "wants",
    "without",
    "ensuring",
    "explain",
    "simple",
    "words",
    "word",
    "today",
    "tomorrow",
    "okay",
    "our",
    "people",
    "them",
}

UNSUPPORTED_PRODUCT_TERMS = {
    "laptop",
    "phone",
    "camera",
    "tablet",
    "computer",
    "monitor",
    "headphones",
    "software",
    "car",
}
CURRENT_FACT_TERMS = {
    "climate",
    "forecast",
    "rain",
    "rainfall",
    "raining",
    "rains",
    "score",
    "stock",
    "news",
    "price",
    "prices",
    "weather",
}
TECH_EXPLANATION_TERMS = {
    "quantum",
    "entanglement",
    "physics",
    "algorithm",
    "database",
    "python",
    "javascript",
    "react",
}
MORAL_INTENT_TERMS = {
    "duty",
    "honest",
    "honesty",
    "truth",
    "lie",
    "lied",
    "guilt",
    "guilty",
    "harm",
    "hurt",
    "fair",
    "unfair",
    "right",
    "wrong",
    "ethical",
    "moral",
    "care",
    "parent",
    "friend",
    "spouse",
    "manager",
    "business",
    "work",
    "job",
    "livelihood",
    "responsibility",
    "compassion",
    "values",
}


def _runtime_context(ctx) -> dict[str, Any]:
    # ADK session state must stay serializable, so non-serializable handles such as
    # Postgres, Redis, EcoTracker, and latency tracking live in this per-request map.
    request_id = ctx.state.get("request_id")
    if not request_id:
        return {}
    return _runtime_contexts.get(str(request_id), {})


def _latency_tracker(ctx) -> AgentLatencyTracker | None:
    tracker = _runtime_context(ctx).get("latency")
    return tracker if isinstance(tracker, AgentLatencyTracker) else None


def _track_agent(ctx, agent: str, *, category: str = "agent", metadata: dict[str, Any] | None = None):
    tracker = _latency_tracker(ctx)
    return tracker.track(agent, category=category, metadata=metadata) if tracker else nullcontext()


def _mark_agent(
    ctx,
    agent: str,
    *,
    category: str = "agent",
    status: str = "skipped",
    metadata: dict[str, Any] | None = None,
) -> None:
    tracker = _latency_tracker(ctx)
    if tracker:
        tracker.mark(agent, category=category, status=status, metadata=metadata)


def _attach_agent_latency(ctx, result: dict[str, Any]) -> dict[str, Any]:
    _mark_agent(ctx, "Finalize", category="workflow", status="completed")
    tracker = _latency_tracker(ctx)
    if tracker:
        result["agentLatencyMetrics"] = tracker.snapshot()
    return result


async def _finalize_with_trace(ctx, result: dict[str, Any]) -> dict[str, Any]:
    result = _attach_agent_latency(ctx, result)
    runtime = _runtime_context(ctx)
    # Persist the final product-visible contract, including failure statuses, so
    # release debugging can reconstruct what the agents actually returned.
    await persist_request_plan_trace(runtime.get("pg"), str(result.get("requestId") or ctx.state.get("request_id") or ""), result)
    return result


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


def _extract_json_object(raw: str) -> dict[str, Any]:
    return extract_json_object(raw, object_name="Retry planner response")


def _build_retry_planner_messages(payload: dict[str, Any], dilemma: str, turn: int) -> list[dict[str, str]]:
    audit = payload.get("auditScores") or {}
    citations = [
        {
            "source": verse.get("source"),
            "faith": verse.get("faith"),
            "keywords": verse.get("keywords") or [],
        }
        for verse in (payload.get("citations") or [])[:3]
        if isinstance(verse, dict)
    ]
    user_payload = {
        "dilemma": dilemma,
        "turn": turn,
        "maxTurns": payload.get("reactLoopLimit"),
        "currentKeywords": payload.get("keywords") or [],
        "contextSufficient": bool(payload.get("contextSufficient", True)),
        "retrievalBlocked": payload.get("retrievalBlocked"),
        "failedDimensions": audit.get("failedDimensions") or [],
        "revisionHints": audit.get("revision_hints") or [],
        "matchedQueryTerms": audit.get("matchedQueryTerms") or [],
        "groundedTerms": audit.get("groundedTerms") or [],
        "retrievedCitationHints": citations,
    }
    return [
        {"role": "system", "content": RETRY_PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
    ]


def _normalize_focus_keywords(value: Any) -> list[str]:
    keywords: list[str] = []
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = [value]
    for item in raw_items:
        for term in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", str(item).lower()):
            if term not in QUERY_STOPWORDS and term not in keywords:
                keywords.append(term)
    return keywords[:6]


def _parse_retry_plan_response(raw: str) -> dict[str, Any]:
    parsed = _extract_json_object(raw)
    action = str(parsed.get("action") or "retry").strip().lower()
    if action not in {"retry", "finalize"}:
        action = "retry"
    retry_query = re.sub(r"\s+", " ", str(parsed.get("retryQuery") or "")).strip()
    focus_keywords = _normalize_focus_keywords(parsed.get("focusKeywords"))
    if action == "retry" and not retry_query:
        raise ValueError("Retry planner response must include retryQuery for retry action")
    if action == "retry" and not focus_keywords:
        raise ValueError("Retry planner response must include focusKeywords for retry action")
    reason = "Retry with focused retrieval." if action == "retry" else "Finalize current result."
    return {
        "action": action,
        "retryQuery": retry_query,
        "focusKeywords": focus_keywords,
        "reason": reason,
    }


def _audit_failed_dimensions(audit: dict[str, Any]) -> set[str]:
    failed = {str(name) for name in audit.get("failedDimensions", []) if str(name).strip()}
    for name, value in (audit.get("scores") or {}).items():
        try:
            score = int(value)
        except (TypeError, ValueError):
            continue
        if score < int(audit.get("minScore") or get_settings().audit_min_score):
            failed.add(str(name))
    return failed


def _should_repair_synthesis_grounding(payload: dict[str, Any]) -> bool:
    audit = payload.get("auditScores") or {}
    if not audit or audit.get("passed", False):
        return False
    failed = _audit_failed_dimensions(audit)
    if failed & NON_RETRYABLE_FAILURE_DIMENSIONS:
        return False
    if not (failed & GROUNDING_FAILURE_DIMENSIONS):
        return False
    return bool(payload.get("citations"))


def _citation_repair_label(citation: dict[str, Any]) -> str:
    parts = [
        str(citation.get("source") or "").strip(),
        str(citation.get("chapter") or "").strip(),
        str(citation.get("verse") or "").strip(),
    ]
    return ", ".join(part for part in parts if part) or "retrieved scripture"


def _grounding_repair_tone(payload: dict[str, Any], base_tone: str) -> str:
    citation_requirements: list[str] = []
    for citation in (payload.get("citations") or [])[:3]:
        if not isinstance(citation, dict):
            continue
        keywords = [
            str(keyword).strip().lower()
            for keyword in (citation.get("keywords") or [])[:4]
            if str(keyword).strip()
        ]
        anchors = ", ".join(keywords) if keywords else str(citation.get("source") or "retrieved scripture")
        citation_requirements.append(f"{_citation_repair_label(citation)} -> {anchors}")

    requirement_text = "; ".join(citation_requirements) or "each retrieved scripture source -> one anchor keyword"
    follow_up_text = (
        " Keep the answer tied to the previous dilemma and the follow-up question."
        if payload.get("previousContextUsed")
        else ""
    )
    repair_text = (
        "Grounding repair mode: The previous draft failed scripture grounding. "
        "In the Scripture grounding section only, name each retrieved source exactly and reuse at least one anchor "
        f"word for each source: {requirement_text}. Do not mention scripture names, chapters, verses, or citation "
        f"labels before Scripture grounding.{follow_up_text}"
    )
    return f"{base_tone.strip()} {repair_text}".strip() if base_tone else repair_text


async def _plan_react_retry_with_llm(payload: dict[str, Any], dilemma: str, turn: int) -> dict[str, Any] | None:
    if turn <= 1 or payload.get("retrievalError"):
        return None
    audit = payload.get("auditScores") or {}
    should_plan = not payload.get("contextSufficient", True) or bool(audit and not audit.get("passed", False))
    if not should_plan:
        return None

    settings = get_settings()
    model = select_model("planner")
    async with httpx.AsyncClient(base_url=settings.ollama_base_url, timeout=45.0) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": model,
                "messages": _build_retry_planner_messages(payload, dilemma, turn),
                "format": "json",
                "stream": False,
                "think": False,
                "keep_alive": "30m",
                "options": {"temperature": 0.0, "num_predict": 120, "num_ctx": 2048},
            },
        )
        response.raise_for_status()
        raw = (response.json().get("message") or {}).get("content", "")
        plan = _parse_retry_plan_response(raw)
        return {**plan, "model": model}


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
    for term in re.findall(r"\b[a-zA-Z][a-zA-Z]{2,}\b", query.lower()):
        if term not in QUERY_STOPWORDS and term not in terms:
            terms.append(term)
    return terms


def _normalize_focus_terms(value: Any) -> list[str]:
    terms: list[str] = []
    if isinstance(value, (list, tuple, set)):
        iterable = value
    else:
        iterable = [value]
    for item in iterable:
        for term in re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", str(item).lower()):
            if term not in QUERY_STOPWORDS and term not in terms:
                terms.append(term)
    return terms[:10]


def _citation_text(reranked: list[dict[str, Any]]) -> str:
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
    return " ".join(citation_text_parts).lower()


def _word_tokens(text: str) -> set[str]:
    return set(re.findall(r"\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b", str(text or "").lower()))


def _term_variants(term: str) -> set[str]:
    normalized = term.strip().lower()
    variants = {normalized} if normalized else set()
    if normalized.endswith("ies") and len(normalized) > 4:
        variants.add(f"{normalized[:-3]}y")
    if normalized.endswith("es") and len(normalized) > 4:
        variants.add(normalized[:-2])
    if normalized.endswith("s") and len(normalized) > 3:
        variants.add(normalized[:-1])
    if normalized.endswith("ing") and len(normalized) > 5:
        variants.add(normalized[:-3])
    return {variant for variant in variants if len(variant) > 2}


def _expanded_support_terms(term: str) -> set[str]:
    expanded = _term_variants(term)
    for concept, related_terms in CONCEPT_CLOUDS.items():
        related_tokens = set()
        for related in related_terms:
            related_tokens.update(_term_variants(related))
        if expanded & ({concept} | related_tokens):
            expanded.add(concept)
            expanded.update(related_tokens)
    return expanded


def _term_supported_by_text(term: str, citation_text: str, citation_tokens: set[str]) -> bool:
    for candidate in _expanded_support_terms(term):
        if " " in candidate:
            if candidate in citation_text:
                return True
        elif candidate in citation_tokens:
            return True
    return False


def _lexical_support_score(
    *,
    direct_matches: list[str],
    focus_matches: list[str],
    reranked: list[dict[str, Any]],
) -> float:
    if not reranked:
        return 0.0
    direct_weight = min(len(direct_matches), 4) * 0.12
    focus_weight = min(len(focus_matches), 4) * 0.25
    return round(min(1.0, direct_weight + focus_weight), 4)


def _citation_doc_texts(reranked: list[dict[str, Any]]) -> list[str]:
    docs: list[str] = []
    for item in reranked:
        verse = item.get("verse") or {}
        docs.append(
            " ".join(
                [
                    str(verse.get("translation", "")),
                    str(verse.get("context", "")),
                    str(verse.get("source", "")),
                    " ".join(str(keyword) for keyword in verse.get("keywords", [])),
                ]
            ).strip()
        )
    return docs


def _dot_product(left: list[float], right: list[float]) -> float:
    return sum(float(a) * float(b) for a, b in zip(left, right))


def _semantic_similarity_report(
    query: str,
    reranked: list[dict[str, Any]],
    focus_terms: list[str],
    threshold: float,
) -> dict[str, Any]:
    docs = _citation_doc_texts(reranked)
    semantic_query = " ".join([query, " ".join(focus_terms)]).strip()
    if not semantic_query or not docs:
        return {
            "semanticQuery": semantic_query,
            "semanticSimilarityThreshold": threshold,
            "semanticSimilarities": [],
            "maxSemanticSimilarity": 0.0,
            "passesSemanticSimilarity": False,
            "semanticSimilarityAvailable": False,
        }
    try:
        embedder = get_embedder()
        query_vector = embedder.embed_query(semantic_query)
        doc_vectors = embedder.embed_documents(docs)
        similarities = [round(_dot_product(query_vector, doc_vector), 4) for doc_vector in doc_vectors]
    except Exception as exc:
        logger.warning("Retrieval semantic similarity check failed: %s", exc)
        return {
            "semanticQuery": semantic_query,
            "semanticSimilarityThreshold": threshold,
            "semanticSimilarities": [],
            "maxSemanticSimilarity": 0.0,
            "passesSemanticSimilarity": False,
            "semanticSimilarityAvailable": False,
            "semanticSimilarityError": str(exc),
        }
    max_similarity = max(similarities) if similarities else 0.0
    return {
        "semanticQuery": semantic_query,
        "semanticSimilarityThreshold": threshold,
        "semanticSimilarities": similarities,
        "maxSemanticSimilarity": max_similarity,
        "passesSemanticSimilarity": max_similarity >= threshold,
        "semanticSimilarityAvailable": True,
    }


def _unsupported_non_guidance_reason(query: str, focus_terms: list[str]) -> str | None:
    query_terms = set(_query_terms(query))
    focus = set(focus_terms)
    all_terms = query_terms | focus
    has_moral_intent = bool(all_terms & MORAL_INTENT_TERMS)
    lower = query.lower()

    if not has_moral_intent and all_terms & {"weather", "forecast", "rain", "raining", "rainfall"} and {
        "today",
        "current",
        "now",
        "tomorrow",
        "year",
        "usual",
    } & set(re.findall(r"\b[a-zA-Z]+\b", lower)):
        return "unsupported_current_fact_query"
    if (
        not has_moral_intent
        and {"which", "best"} & set(re.findall(r"\b[a-zA-Z]+\b", lower))
        and "buy" in lower
        and all_terms & UNSUPPORTED_PRODUCT_TERMS
    ):
        return "unsupported_product_recommendation"
    if not has_moral_intent and all_terms & CURRENT_FACT_TERMS:
        return "unsupported_current_fact_query"
    if not has_moral_intent and all_terms & TECH_EXPLANATION_TERMS and re.search(r"\b(explain|what is|how does)\b", lower):
        return "unsupported_explanation_query"
    return None


def _retrieval_relevance_report(
    query: str,
    reranked: list[dict[str, Any]],
    *,
    focus_terms: list[str] | None = None,
    semantic_threshold: float = 0.17,
) -> dict[str, Any]:
    terms = _query_terms(query)
    normalized_focus_terms = _normalize_focus_terms(focus_terms or [])

    citation_text = _citation_text(reranked)
    citation_tokens = _word_tokens(citation_text)
    direct_matches = sorted(
        term for term in terms if term and _term_supported_by_text(term, citation_text, citation_tokens)
    )
    focus_matches = sorted(
        term for term in normalized_focus_terms if term and _term_supported_by_text(term, citation_text, citation_tokens)
    )
    matched_terms = sorted(set(direct_matches + focus_matches))
    semantic = _semantic_similarity_report(query, reranked, normalized_focus_terms, semantic_threshold)
    lexical_score = _lexical_support_score(
        direct_matches=direct_matches,
        focus_matches=focus_matches,
        reranked=reranked,
    )
    max_similarity = max(float(semantic.get("maxSemanticSimilarity") or 0.0), lexical_score)
    unsupported_reason = _unsupported_non_guidance_reason(query, normalized_focus_terms)
    return {
        "queryTerms": terms,
        "focusTerms": normalized_focus_terms,
        "directMatches": direct_matches,
        "focusMatches": focus_matches,
        "matchedTerms": matched_terms,
        "supportMatches": focus_matches,
        "matchedCount": len(matched_terms),
        "supportMatchCount": len(focus_matches),
        "unsupportedQueryReason": unsupported_reason,
        **semantic,
        "lexicalSupportScore": lexical_score,
        "maxSemanticSimilarity": max_similarity,
        "passesSemanticSimilarity": bool(max_similarity >= semantic_threshold),
        "passesCitationRelevance": bool(max_similarity >= semantic_threshold and not unsupported_reason),
    }


def _retrieval_gate_reason(
    query: str,
    reranked: list[dict[str, Any]],
    *,
    top_score: float,
    threshold: float,
    focus_terms: list[str] | None = None,
    semantic_threshold: float = 0.17,
) -> tuple[str | None, dict[str, Any]]:
    relevance = _retrieval_relevance_report(
        query,
        reranked,
        focus_terms=focus_terms,
        semantic_threshold=semantic_threshold,
    )
    if not reranked:
        return "no_retrieved_citations", relevance
    if relevance.get("unsupportedQueryReason"):
        return relevance["unsupportedQueryReason"], relevance
    if top_score < threshold:
        return "retrieval_score_below_threshold", relevance
    if not relevance["passesSemanticSimilarity"]:
        return "retrieval_not_relevant_to_query", relevance
    return None, relevance


def _pre_retrieval_topic_block(query: str, focus_terms: list[str] | None = None) -> tuple[str | None, dict[str, Any] | None]:
    normalized_focus_terms = _normalize_focus_terms(focus_terms or [])
    blocked_reason = _unsupported_non_guidance_reason(query, [])
    if not blocked_reason:
        blocked_reason = _unsupported_non_guidance_reason(query, normalized_focus_terms)
    if not blocked_reason:
        return None, None
    report = _retrieval_relevance_report(query, [], focus_terms=normalized_focus_terms)
    report["unsupportedQueryReason"] = blocked_reason
    report["passesCitationRelevance"] = False
    return blocked_reason, report


def _retrieval_matches_query(query: str, reranked: list[dict[str, Any]], focus_terms: list[str] | None = None) -> bool:
    return _retrieval_relevance_report(query, reranked, focus_terms=focus_terms)["passesCitationRelevance"]


def _retrieval_gate_query(payload: dict[str, Any], ctx, fallback_dilemma: str) -> str:
    current = str(payload.get("originalQuery") or ctx.state.get("original_dilemma") or fallback_dilemma or "").strip()
    previous = str(payload.get("previousContextQuestion") or ctx.state.get("previous_context_question") or "").strip()
    if _unsupported_non_guidance_reason(current, []):
        return current
    if payload.get("previousContextUsed") and previous:
        return f"{previous} {current}".strip()
    return current


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
    """Build a concise trace that explains the agent path without exposing hidden prompts."""
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
    """Only cache completed, judge-passed, citation-grounded answers."""
    audit = result.get("auditScores") or {}
    grounding_contract = audit.get("groundingContract") or {}
    return (
        result.get("status") == "completed"
        and bool(audit.get("passed"))
        and not bool(audit.get("judgeFallback", False))
        and str(audit.get("auditStatus") or "") == "ok"
        and bool(grounding_contract.get("passed"))
        and len(result.get("citations") or []) >= 2
        and result.get("moralPathway") is not None
    )


def _cache_rejection_reason(result: dict[str, Any]) -> str:
    audit = result.get("auditScores") or {}
    grounding_contract = audit.get("groundingContract") or {}
    if result.get("status") != "completed":
        return f"status_{result.get('status') or 'unknown'}"
    if not result.get("moralPathway"):
        return "missing_moral_pathway"
    if len(result.get("citations") or []) < 2:
        return "fewer_than_two_citations"
    if not audit.get("passed"):
        return "judge_not_passed"
    if audit.get("judgeFallback"):
        return "judge_fallback_used"
    if str(audit.get("auditStatus") or "") != "ok":
        return "audit_status_not_ok"
    if not grounding_contract.get("passed"):
        return "grounding_contract_not_passed"
    return "cacheable"


def _attach_cache_policy(result: dict[str, Any], cache_key: str | None) -> dict[str, Any]:
    key = cache_key or str(result.get("cachePolicy", {}).get("cacheKey") or "")
    cacheable = _is_safe_to_cache(result)
    result["cachePolicy"] = cache_policy_metadata(
        cache_key=key,
        cacheable=cacheable,
        reason="cacheable" if cacheable else _cache_rejection_reason(result),
    )
    return result


@node(name="planner")
async def planner_node(ctx, node_input) -> dict[str, Any]:
    """LLM agent: choose moral retrieval concepts and tone from the optimized dilemma."""
    payload = node_input if isinstance(node_input, dict) else {}
    state = ctx.state
    dilemma = payload.get("dilemma") or state.get("dilemma") or _content_text(node_input)
    optimized_query = payload.get("compressedQuery") or payload.get("optimizedQuery")
    pg = _runtime_context(ctx).get("pg")
    user_email = state.get("user_email", "anonymous")
    try:
        with _track_agent(ctx, "Planner", category="llm", metadata={"modelRole": "planner"}):
            planner = await run_strategic_planner(dilemma, user_email, pg, optimized_query=optimized_query)
    except ServiceUnavailableError as exc:
        logger.warning("Planner unavailable for request %s: %s", ctx.state.get("request_id"), exc)
        return {
            **payload,
            "dilemma": dilemma,
            "keywords": [],
            "reasoning": None,
            "historySummary": None,
            "toneMsg": None,
            "plannerEngine": None,
            "plannerModel": None,
            "plannerError": str(exc),
            "contextSufficient": False,
        }
    eco: EcoTracker | None = _runtime_context(ctx).get("eco")
    if eco:
        eco.track_stage("Planner")
    return {**payload, "dilemma": dilemma, **planner}


@node(name="optimizer")
async def optimizer_node(ctx, node_input: Any) -> dict[str, Any]:
    """Deterministic agent: prepare compression, subqueries, and cache metadata before planning."""
    payload = node_input if isinstance(node_input, dict) else {}
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    optimizer = ctx.state.get("optimizer_preview")
    with _track_agent(ctx, "QueryOptimizer", category="deterministic"):
        if not isinstance(optimizer, dict) or optimizer.get("originalQuery") != dilemma:
            optimizer = optimize_query(
                dilemma,
                payload.get("keywords", []),
                payload.get("historySummary", ""),
            )
        else:
            optimizer = {**optimizer, "optimizerCache": "preview"}
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco and optimizer.get("optimizerCache") != "preview":
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


async def _react_reason_impl(ctx, payload: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    turn = int(payload.get("reactTurn") or 0) + 1
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    if payload.get("plannerError"):
        _mark_agent(ctx, "ReActReasoner", category="workflow", status="skipped", metadata={"reason": "planner_unavailable"})
        return {
            **payload,
            "reactTurn": turn,
            "reactLoopLimit": settings.react_max_turns,
            "reactReasoning": "Planner unavailable; finalize with an explicit planner-unavailable response.",
            "reactSearchQuery": dilemma,
            "reactLoopLog": [
                *payload.get("reactLoopLog", []),
                f"Turn {turn} Reason: Planner unavailable; retrieval and synthesis skipped.",
            ],
        }
    keywords = payload.get("keywords", [])
    audit = payload.get("auditScores") or {}
    context_sufficient = bool(payload.get("contextSufficient", True))

    reason = "Initial reasoning pass: retrieve scripture context and draft grounded guidance."
    if payload.get("retrievalError"):
        reason = "Retrieval service reported an error; prepare final graceful response."
    elif not context_sufficient:
        reason = "Observation found weak scripture grounding; broaden retrieval with moral themes and planner keywords."
    elif audit and not audit.get("passed", False):
        reason = "Judge found quality gaps; revise using audit hints before the next attempt."

    # Retry planning is intentionally LLM-driven. If it fails, Anayaa finalizes
    # with an explicit status instead of inventing a deterministic backup answer.
    retry_plan = None
    retry_plan_error = None
    grounding_repair = _should_repair_synthesis_grounding(payload)
    try:
        with _track_agent(ctx, "ReActRetryPlanner", category="llm", metadata={"turn": turn, "modelRole": "planner"}):
            retry_plan = await _plan_react_retry_with_llm(payload, dilemma, turn)
    except Exception as exc:
        retry_plan_error = str(exc)
        logger.warning("LLM ReAct retry planner failed for request %s: %s", ctx.state.get("request_id"), exc)

    if retry_plan and retry_plan.get("action") == "retry":
        react_search_query = retry_plan["retryQuery"]
        planned_keywords = retry_plan.get("focusKeywords") or []
        keywords = list(dict.fromkeys([*keywords, *planned_keywords]))[:8]
        reason = f"LLM retry planner: {retry_plan['reason']}"
        skip_retry = False
    elif grounding_repair:
        react_search_query = payload.get("searchQuery") or dilemma
        reason = "Grounding repair retry: existing citations need a clearer Scripture grounding section."
        skip_retry = False
    elif retry_plan_error:
        react_search_query = payload.get("searchQuery") or dilemma
        reason = "LLM retry planner failed; finalize without deterministic retry fallback."
        skip_retry = True
    elif retry_plan and retry_plan.get("action") == "finalize":
        react_search_query = payload.get("searchQuery") or dilemma
        reason = "LLM retry planner chose to finalize without another retrieval attempt."
        skip_retry = True
    else:
        react_search_query = dilemma
        skip_retry = False

    route_hint = "retry" if retry_plan and retry_plan.get("action") == "retry" else "finalize" if skip_retry else "initial"
    with _track_agent(ctx, "ReActReasoner", category="workflow", metadata={"turn": turn, "routeHint": route_hint}):
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco:
            eco.track_stage("ReActReasoner")

    return {
        **payload,
        "reactTurn": turn,
        "reactLoopLimit": settings.react_max_turns,
        "reactReasoning": reason,
        "reactSearchQuery": react_search_query,
        "keywords": keywords,
        "reactRetryPlan": retry_plan,
        "reactRetryPlanError": retry_plan_error,
        "skipRetryRetrieval": skip_retry,
        "synthesisGroundingRepair": bool(grounding_repair and not skip_retry),
        "reactLoopLog": [
            *payload.get("reactLoopLog", []),
            f"Turn {turn} Reason: {reason}",
        ],
    }


@node(name="react_reason")
async def react_reason_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    """Reason about the next retrieval/synthesis attempt in a bounded ReAct loop."""
    payload = node_input if isinstance(node_input, dict) else {}
    return await _react_reason_impl(ctx, payload)


@node(name="retriever")
async def retriever_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    payload = node_input if isinstance(node_input, dict) else {}
    if payload.get("plannerError"):
        _mark_agent(ctx, "McpRetriever", category="tool", status="skipped", metadata={"reason": "planner_unavailable"})
        return {
            **payload,
            "searchQuery": payload.get("dilemma") or ctx.state.get("dilemma", ""),
            "retrievalQueries": [],
            "multiQueryUsed": False,
            "hybridSource": None,
            "candidatesCount": 0,
            "rerankedCitations": [],
            "citations": [],
            "retrievalViaMcp": False,
            "contextSufficient": False,
            "topRetrievalScore": 0,
            "retrievalThreshold": settings.retrieval_confidence_threshold,
        }
    if payload.get("skipRetryRetrieval"):
        _mark_agent(ctx, "McpRetriever", category="tool", status="skipped", metadata={"reason": "retry_planner_finalized"})
        return payload
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    search_query = payload.get("reactSearchQuery") or dilemma
    keywords = payload.get("keywords", [])
    gate_query = _retrieval_gate_query(payload, ctx, dilemma)
    pre_retrieval_blocked, pre_retrieval_report = _pre_retrieval_topic_block(gate_query, keywords)
    if pre_retrieval_blocked:
        _mark_agent(
            ctx,
            "McpRetriever",
            category="tool",
            status="skipped",
            metadata={"reason": "pre_retrieval_topic_gate", "retrievalBlocked": pre_retrieval_blocked},
        )
        eco: EcoTracker | None = _runtime_context(ctx).get("eco")
        if eco:
            eco.track_stage("Retriever", confidence=0)
        return {
            **payload,
            "searchQuery": gate_query,
            "retrievalQueries": [],
            "multiQueryUsed": False,
            "hybridSource": None,
            "candidatesCount": 0,
            "rerankedCitations": [],
            "citations": [],
            "retrievalViaMcp": False,
            "contextSufficient": False,
            "topRetrievalScore": 0,
            "rawTopRetrievalScore": 0,
            "retrievalThreshold": settings.retrieval_confidence_threshold,
            "retrievalBlocked": pre_retrieval_blocked,
            "retrievalRelevance": pre_retrieval_report,
            "retrievalGateQuery": gate_query,
            "preRetrievalBlocked": True,
            "preSynthesisApprovalRequired": False,
        }

    sub_queries = [
        str(query).strip()
        for query in payload.get("subQueries", [])
        if str(query).strip()
    ]
    use_multi_query = bool(payload.get("multiQueryEnabled")) and int(payload.get("reactTurn") or 1) == 1 and len(sub_queries) > 1
    retrieval_queries = sub_queries[:3] if use_multi_query else [search_query]
    try:
        # Scripture access goes through the MCP tool process only; the workflow
        # does not read Milvus directly, which keeps tool use auditable.
        with _track_agent(
            ctx,
            "McpRetriever",
            category="tool",
            metadata={"queryCount": len(retrieval_queries), "multiQuery": use_multi_query},
        ):
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
    retrieval_blocked, relevance_report = _retrieval_gate_reason(
        gate_query,
        reranked,
        top_score=top_score,
        threshold=settings.retrieval_confidence_threshold,
        focus_terms=keywords,
        semantic_threshold=settings.retrieval_semantic_similarity_threshold,
    )
    # A high vector score is not enough: the retrieved verses must also overlap
    # the user's actual dilemma and support a moral/life-guidance concept before
    # synthesis is allowed.
    context_sufficient = retrieval_blocked is None
    effective_top_score = top_score if context_sufficient else 0

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
        "retrievalBlocked": retrieval_blocked,
        "retrievalRelevance": relevance_report,
        "retrievalGateQuery": gate_query,
        "preSynthesisApprovalRequired": pre_synthesis_approval_required,
    }


@node(name="synthesize")
async def synthesize_node(ctx, node_input: dict[str, Any]) -> dict[str, Any]:
    payload = node_input if isinstance(node_input, dict) else {}
    if payload.get("plannerError"):
        _mark_agent(ctx, "Synthesizer", category="llm", metadata={"reason": "planner_unavailable"})
        return {**payload, "moralPathway": None, "quantizedMetrics": None, "synthesisEngine": None}
    if payload.get("skipRetryRetrieval"):
        _mark_agent(ctx, "Synthesizer", category="llm", status="skipped", metadata={"reason": "retry_planner_finalized"})
        return payload
    if not payload.get("contextSufficient", True):
        _mark_agent(ctx, "Synthesizer", category="llm", metadata={"reason": "context_insufficient"})
        return {**payload, "moralPathway": None, "quantizedMetrics": None, "synthesisEngine": None}
    if payload.get("preSynthesisApprovalRequired"):
        # Interactive Guidance pauses here so the user can approve or adjust the
        # evidence set before any final moral guidance is generated.
        _mark_agent(ctx, "Synthesizer", category="llm", metadata={"reason": "pre_synthesis_approval"})
        return {**payload, "moralPathway": None, "quantizedMetrics": None, "synthesisEngine": None}

    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    citations = payload.get("citations") or []
    tone_msg = payload.get("toneMsg", "")
    if payload.get("synthesisGroundingRepair"):
        tone_msg = _grounding_repair_tone(payload, tone_msg)

    try:
        with _track_agent(ctx, "Synthesizer", category="llm", metadata={"modelRole": "synthesizer"}):
            pathway, metrics = await generate_moral_pathway(dilemma, citations, tone_msg)
    except PipelineError as exc:
        logger.warning("Synthesizer unavailable for request %s: %s", ctx.state.get("request_id"), exc)
        _mark_agent(ctx, "Synthesizer", category="llm", status="error", metadata={"reason": "synthesizer_unavailable"})
        return {
            **payload,
            "synthesizerError": str(exc),
            "synthesizerUserMessage": exc.user_message,
            "synthesizerStatus": exc.code,
            "synthesizerFailureReason": getattr(exc, "detail", str(exc)),
            "moralPathway": None,
            "quantizedMetrics": None,
            "synthesisEngine": None,
        }
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
    if payload.get("plannerError"):
        _mark_agent(ctx, "GEvalJudge", category="llm", metadata={"reason": "planner_unavailable"})
        return {**payload, "auditScores": None, "confidence": 0}
    if payload.get("synthesizerError"):
        _mark_agent(ctx, "GEvalJudge", category="llm", metadata={"reason": "synthesizer_unavailable"})
        return {**payload, "auditScores": None, "confidence": payload.get("confidence", 0)}
    if payload.get("skipRetryRetrieval"):
        _mark_agent(ctx, "GEvalJudge", category="llm", status="skipped", metadata={"reason": "retry_planner_finalized"})
        return payload
    if not payload.get("contextSufficient", True):
        _mark_agent(ctx, "GEvalJudge", category="llm", metadata={"reason": "context_insufficient"})
        return {**payload, "auditScores": None, "confidence": payload.get("topRetrievalScore", 0)}
    if payload.get("preSynthesisApprovalRequired"):
        _mark_agent(ctx, "GEvalJudge", category="llm", metadata={"reason": "pre_synthesis_approval"})
        reranked = payload.get("rerankedCitations") or []
        confidence = reranked[0].get("score", 0) if reranked else payload.get("topRetrievalScore", 0)
        return {**payload, "auditScores": None, "confidence": confidence}
    dilemma = payload.get("dilemma") or ctx.state.get("dilemma", "")
    citations = payload.get("citations") or []
    pathway = payload.get("moralPathway") or ""
    with _track_agent(ctx, "GEvalJudge", category="llm", metadata={"modelRole": "judge"}):
        audit = await run_g_eval_judge(dilemma, citations, pathway)
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
    planner_error = payload.get("plannerError")
    synthesizer_error = payload.get("synthesizerError")
    retrieval_error = payload.get("retrievalError")
    retrieval_blocked = payload.get("retrievalBlocked")
    retry_planner_stopped = bool(payload.get("skipRetryRetrieval"))

    route = "finalize"
    observation = "Observation: quality threshold passed; finalize response."
    if planner_error:
        observation = "Observation: strategic planner failed; finalize with a planner-unavailable message."
    elif synthesizer_error:
        observation = "Observation: guidance synthesizer failed; finalize with a synthesizer-unavailable message."
    elif retry_planner_stopped:
        if payload.get("reactRetryPlanError"):
            observation = "Observation: retry planner failed; finalize without deterministic retry fallback."
        else:
            observation = "Observation: retry planner chose to finalize without another retrieval attempt."
    elif retrieval_error:
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

    with _track_agent(ctx, "ReActObserve", category="workflow", metadata={"turn": turn, "route": route}):
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

    if payload.get("plannerError"):
        result = build_planner_unavailable_response(
            dilemma=payload.get("dilemma") or ctx.state.get("dilemma", ""),
            request_id=request_id,
            optimizer=payload,
            eco_breakdown=totals.get("ecoBreakdown", []),
            power_metrics=power,
            detail=str(payload.get("plannerError")),
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
        _attach_cache_policy(result, payload.get("cacheKey"))
        return await _finalize_with_trace(ctx, result)

    if payload.get("synthesizerError"):
        result = build_synthesizer_unavailable_response(
            payload=payload,
            request_id=request_id,
            eco_breakdown=totals.get("ecoBreakdown", []),
            power_metrics=power,
            detail=str(payload.get("synthesizerError")),
            user_message=payload.get("synthesizerUserMessage"),
            status=payload.get("synthesizerStatus") or "synthesizer_unavailable",
            failure_reason=payload.get("synthesizerFailureReason") or "synthesizer_service_unavailable",
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
        _attach_cache_policy(result, payload.get("cacheKey"))
        return await _finalize_with_trace(ctx, result)

    if not payload.get("contextSufficient", True):
        # Retrieval failures and weak retrieval are different user states. Keep
        # them separate so users know whether to repair setup or rephrase.
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
            if payload.get("retrievalBlocked") == "retrieval_not_relevant_to_query":
                result["failureReason"] = "retrieval_not_relevant_to_query"
                result["userMessage"] = (
                    "Anayaa found scripture passages, but they were not closely related to your actual question. "
                    "To avoid an unsupported answer, please rephrase the dilemma with clearer life context."
                )
            elif payload.get("retrievalBlocked") == "citation_relevance_below_threshold":
                result["failureReason"] = "citation_relevance_below_threshold"
                result["userMessage"] = (
                    "Anayaa found scripture passages, but their connection to your actual dilemma was too weak "
                    "to support grounded guidance. To avoid an unsupported answer, please rephrase with clearer "
                    "moral or life context."
                )
            elif payload.get("retrievalBlocked") == "retrieval_score_below_threshold":
                result["failureReason"] = "retrieval_score_below_threshold"
            elif payload.get("retrievalBlocked") == "no_retrieved_citations":
                result["failureReason"] = "no_retrieved_citations"
            elif str(payload.get("retrievalBlocked") or "").startswith("unsupported_"):
                result["failureReason"] = payload.get("retrievalBlocked")
                result["userMessage"] = (
                    "Anayaa is designed for moral and life guidance grounded in the local scripture corpus. "
                    "This question looks like a factual, product, or technical request, so Anayaa will not "
                    "force a scripture-grounded answer."
                )
            result["retrievalBlocked"] = payload.get("retrievalBlocked")
            result["retrievalRelevance"] = payload.get("retrievalRelevance")
            result["rawTopRetrievalScore"] = payload.get("rawTopRetrievalScore")
        result["pipeline"] = "Google ADK ReAct Workflow + MCP Milvus Retrieval"
        result["originalQuery"] = payload.get("originalQuery") or ctx.state.get("original_dilemma") or result.get("originalQuery")
        result["rewrittenQuery"] = payload.get("rewrittenQuery") or ctx.state.get("rewritten_dilemma")
        result["queryRewriteApplied"] = payload.get("queryRewriteApplied", False)
        result["queryRewriteRules"] = payload.get("queryRewriteRules", [])
        result["previousContextUsed"] = payload.get("previousContextUsed", False)
        result["previousContextQuestion"] = payload.get("previousContextQuestion")
        result["executionPlan"] = _execution_plan(payload)
        result["loopDetails"] = _react_loop_details(payload)
        _attach_cache_policy(result, payload.get("cacheKey"))
        return await _finalize_with_trace(ctx, result)

    if payload.get("preSynthesisApprovalRequired"):
        # HITL checkpoints expose concepts and candidate scriptures, not hidden
        # chain-of-thought, and resume later through the same audited pipeline.
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
        _attach_cache_policy(result, payload.get("cacheKey"))
        return await _finalize_with_trace(ctx, result)

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
        _attach_cache_policy(result, payload.get("cacheKey"))
        return await _finalize_with_trace(ctx, result)

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
        "guidanceReasons": build_guidance_reasons(dilemma, citations, payload.get("moralPathway"), audit),
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
    _attach_cache_policy(result, cache_key)
    if redis and cache_key and _is_safe_to_cache(result):
        await store_semantic_cache(redis, cache_key, result)

    return await _finalize_with_trace(ctx, result)


def _build_workflow() -> Workflow:
    """The ADK edge order is the runtime source of truth for agent execution."""
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


async def _delete_adk_session(user_email: str, session_id: str | None) -> None:
    if not session_id:
        return
    try:
        await _session_service.delete_session(
            app_name="anayaa",
            user_id=user_email,
            session_id=session_id,
        )
    except Exception:
        logger.exception("Failed to delete ADK session %s", session_id)


async def run_adk_pipeline(
    dilemma: str,
    user_email: str,
    pg,
    redis: RedisCache,
    eco: EcoTracker,
    hitl_enabled: bool = True,
    milvus=None,
    previous_context: dict[str, Any] | None = None,
    use_previous_context: bool = False,
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

    request_id = str(eco.request_id)
    latency = AgentLatencyTracker(request_id=request_id)
    eco.track_stage("SanitizeGate")

    # Pre-ADK rewrite/cache preview lets direct guidance return safely from cache when HITL is off.
    with latency.track("QueryRewriter", category="deterministic"):
        rewrite = rewrite_malformed_query(
            dilemma,
            previous_context=previous_context,
            use_previous_context=use_previous_context,
        )
    rewritten_dilemma = rewrite["rewrittenQuery"]
    with latency.track("QueryOptimizer", category="deterministic", metadata={"phase": "pre_adk_preview"}):
        optimizer_preview = {
            **optimize_query(rewritten_dilemma, []),
            **rewrite,
        }
    eco.track_stage("QueryOptimizer")

    with latency.track("SemanticCache", category="cache", metadata={"enabled": not hitl_enabled}):
        cached = None if hitl_enabled else await evaluate_semantic_cache(redis, optimizer_preview["cacheKey"])
    if cached and _is_safe_to_cache(cached):
        eco.track_stage("CacheReturn", cache_hit=True, confidence=95)
        power = eco.audit_power_footprint(True, 95)
        cached_result = {
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
            "agentLatencyMetrics": latency.snapshot(),
        }
        cached_result["cachePolicy"] = {
            **cached_result.get("cachePolicy", {}),
            "cacheable": True,
            "reason": "cache_hit",
        }
        await persist_request_plan_trace(pg, request_id, cached_result)
        return cached_result

    # The runtime map is removed in finally so long-lived local serving does not
    # accumulate handles after ADK sessions complete or error.
    _runtime_contexts[request_id] = {"pg": pg, "redis": redis, "eco": eco, "latency": latency}
    session_id: str | None = None
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
        session_id = session.id

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
        await _delete_adk_session(user_email, session_id)
        _runtime_contexts.pop(request_id, None)

    if not final_payload:
        raise PipelineError(
            "ADK workflow completed without a final payload.",
            user_message="The guidance workflow did not produce a result. Please try again.",
            code="workflow_empty",
        )

    return final_payload
