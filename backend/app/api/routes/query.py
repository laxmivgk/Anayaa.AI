from html import unescape
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agents.pipeline_errors import PipelineError
from app.agents.workflow import execute_unified_workflow
from app.api.deps import require_auth
from app.config import get_settings
from app.eco.aggregator import persist_request_eco, upsert_daily_rollup
from app.eco.tracker import EcoTracker, new_request_id
from app.hitl.checkpoints import create_checkpoint
from app.memory.streams import log_transaction
from app.resilience.health import check_health
from app.security.firewall import run_security_firewall
from app.security.privacy_scrubber import detect_sensitive_names, scrub_pii, scrub_pii_deep, scrub_pii_response_deep
from app.security.sanitizer import sanitize_query

router = APIRouter(prefix="/api", tags=["query"])


class PreviousContextBody(BaseModel):
    question: str = Field(min_length=1, max_length=800)
    timestamp: str | None = Field(default=None, max_length=80)


class QueryBody(BaseModel):
    query: str = Field(min_length=1)
    preSynthesisVerification: bool = True
    previousContext: list[PreviousContextBody] = Field(default_factory=list, max_length=3)
    usePreviousContext: bool = False


def _model_facing_firewall_text(text: str) -> str:
    return unescape(text)


def _prepare_previous_context(items: list[PreviousContextBody]) -> dict[str, Any] | None:
    turns: list[dict[str, str]] = []
    for item in items[:3]:
        question = scrub_pii(sanitize_query(item.question, max_length=800))
        security = run_security_firewall(question, max_length=800)
        if not security.passed:
            continue
        sanitized_question = scrub_pii(_model_facing_firewall_text(security.sanitized)).strip()
        if not sanitized_question:
            continue
        turn: dict[str, str] = {"question": sanitized_question}
        if item.timestamp:
            turn["timestamp"] = scrub_pii(sanitize_query(item.timestamp, max_length=80))
        turns.append(turn)
    return {"turns": turns} if turns else None


async def _finalize_request_eco(pg, request_id: str, user_email: str, eco: EcoTracker, cache_hit: bool) -> dict[str, Any]:
    totals = eco.totals()
    await persist_request_eco(pg, request_id, user_email, totals["ecoBreakdown"], cache_hit)
    await upsert_daily_rollup(pg, user_email, totals["energyMWh"] / 1000, totals["co2Kg"])
    return totals


def _pipeline_error_content(exc: PipelineError, request_id: str, eco: EcoTracker, totals: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": exc.code,
        "error": str(exc),
        "userMessage": exc.user_message,
        "failureReason": getattr(exc, "detail", str(exc)),
        "requestId": request_id,
        "confidence": 0,
        "cacheHit": False,
        "powerMetrics": eco.audit_power_footprint(False, 0),
        "ecoBreakdown": totals["ecoBreakdown"],
    }


@router.post("/query")
async def query(body: QueryBody, request: Request, user=Depends(require_auth)):
    settings = get_settings()
    pg = request.app.state.pg
    redis = request.app.state.redis
    session_mgr = request.app.state.session_mgr

    health = await check_health(pg, redis, getattr(request.app.state, "milvus_status", None))
    if not health.get("corpusReady"):
        raise HTTPException(status_code=503, detail="Corpus not loaded.")

    session_id = user.get("session_id")
    if session_id and not await session_mgr.check_rate_limit(session_id, settings.rate_limit_per_minute):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    # Security gates run before any agent, model, retrieval tool, or persistence path sees the query.
    raw_query = sanitize_query(body.query)
    sensitive_names = detect_sensitive_names(raw_query)
    security = run_security_firewall(raw_query)
    if not security.passed:
        blocked = log_transaction(user["email"], f"[REJECTED FIREWALL] {scrub_pii(raw_query, extra_names=sensitive_names)}", 0, False, 0, 0)
        return JSONResponse(
            status_code=403,
            content=scrub_pii_deep({
                "error": "Regex Firewall alert! Dangerous signatures blocked.",
                "violations": security.violations,
                "transactionLog": blocked,
            }, extra_names=sensitive_names),
        )

    # The workflow receives scrubbed text so planners and traces avoid direct identifiers.
    scrubbed = scrub_pii(_model_facing_firewall_text(security.sanitized), extra_names=sensitive_names)
    previous_context = _prepare_previous_context(body.previousContext)
    request_id = new_request_id()
    eco = EcoTracker(request_id=request_id)
    await pg.execute(
        """
        INSERT INTO turns (request_id, scrubbed_query)
        VALUES ($1, $2)
        """,
        request_id,
        scrubbed,
    )

    try:
        # ADK owns the multi-agent reasoning path; the API layer remains an auth/security boundary.
        result = await execute_unified_workflow(
            scrubbed,
            user["email"],
            pg,
            redis,
            eco,
            hitl_enabled=settings.hitl_enabled and body.preSynthesisVerification,
            milvus=getattr(request.app.state, "milvus", None),
            previous_context=previous_context,
            use_previous_context=body.usePreviousContext,
        )
    except PipelineError as exc:
        totals = await _finalize_request_eco(pg, request_id, user["email"], eco, False)
        return JSONResponse(
            status_code=503,
            content=scrub_pii_deep(_pipeline_error_content(exc, request_id, eco, totals), extra_names=sensitive_names),
        )

    faith_count = len({c.get("faith") for c in result.get("citations", [])})
    co2 = result.get("powerMetrics", {}).get("co2Kg", 0)
    trans = log_transaction(
        user["email"],
        scrubbed,
        faith_count,
        result.get("cacheHit", False),
        result.get("confidence", 0),
        co2,
    )
    result["transactionLog"] = trans

    await _finalize_request_eco(pg, request_id, user["email"], eco, result.get("cacheHit", False))

    if result.get("status") in {"awaiting_approval", "awaiting_pre_synthesis_approval"} and result.get("hitl"):
        await create_checkpoint(
            pg,
            result["hitl"]["workflowRunId"],
            request_id,
            user["email"],
            result,
        )

    # Final scrub is defensive: generated text and nested metadata are cleaned before leaving the API.
    return scrub_pii_response_deep(result, extra_names=sensitive_names)
