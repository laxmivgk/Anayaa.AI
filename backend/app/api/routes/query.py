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
from app.security.privacy_scrubber import scrub_pii, scrub_pii_deep
from app.security.sanitizer import sanitize_query

router = APIRouter(prefix="/api", tags=["query"])


class QueryBody(BaseModel):
    query: str = Field(min_length=1)
    preSynthesisVerification: bool = True


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

    raw_query = sanitize_query(body.query)
    security = run_security_firewall(raw_query)
    if not security.passed:
        blocked = log_transaction(user["email"], f"[REJECTED FIREWALL] {scrub_pii(raw_query)}", 0, False, 0, 0)
        return JSONResponse(
            status_code=403,
            content=scrub_pii_deep({
                "error": "Regex Firewall alert! Dangerous signatures blocked.",
                "violations": security.violations,
                "transactionLog": blocked,
            }),
        )

    scrubbed = scrub_pii(security.sanitized)
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
        result = await execute_unified_workflow(
            scrubbed,
            user["email"],
            pg,
            redis,
            eco,
            hitl_enabled=settings.hitl_enabled and body.preSynthesisVerification,
            milvus=getattr(request.app.state, "milvus", None),
            previous_context=None,
        )
    except PipelineError as exc:
        return JSONResponse(
            status_code=503,
            content=scrub_pii_deep({
                "status": exc.code,
                "error": str(exc),
                "userMessage": exc.user_message,
                "requestId": request_id,
            }),
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

    totals = eco.totals()
    await persist_request_eco(pg, request_id, user["email"], totals["ecoBreakdown"], result.get("cacheHit", False))
    await upsert_daily_rollup(pg, user["email"], totals["energyMWh"] / 1000, totals["co2Kg"])

    if result.get("status") in {"awaiting_approval", "awaiting_pre_synthesis_approval"} and result.get("hitl"):
        await create_checkpoint(
            pg,
            result["hitl"]["workflowRunId"],
            request_id,
            user["email"],
            result,
        )

    return scrub_pii_deep(result)
