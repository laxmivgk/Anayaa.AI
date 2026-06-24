from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_auth
from app.eco.aggregator import get_daily_rollup
from app.hitl.checkpoints import resume_checkpoint
from app.memory.postgres import PostgresPool
from app.memory.streams import get_transaction_streams
from app.retrieval.corpus import get_corpus
from app.resilience.health import check_health, deep_health
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system/status")
async def system_status(request: Request):
    pg = request.app.state.pg
    redis = request.app.state.redis
    health = await check_health(pg, redis, getattr(request.app.state, "milvus_status", None))
    return {
        "quantizedModel": "llama3.2:3b-local",
        "speculativeDraftModel": "gemma2:2b-local",
        "acceleration": "Local Apple Silicon / NPU Node",
        "redisCacheSize": "active" if health.get("redis") else "unavailable",
        "streamBufferCount": len(get_transaction_streams()),
        "activePartitionTable": "dilemma_logs",
        "corpusReady": health.get("corpusReady"),
        "verseCount": health.get("verseCount"),
        "corpusSource": health.get("corpusSource", "backend/data/scriptures.json"),
        "runtimeMode": health.get("runtimeMode", "local"),
        "milvus": health.get("milvus"),
        "postgres": health.get("postgres"),
        "embeddingModel": health.get("embeddingModel"),
    }


@router.get("/system/scriptures")
async def system_scriptures():
    corpus = get_corpus()
    return {"success": True, "totalCount": len(corpus), "scriptures": [v.to_dict() for v in corpus]}


@router.get("/system/streams")
async def system_streams():
    return {"success": True, "logs": get_transaction_streams()}


@router.get("/health")
async def health(request: Request):
    return await check_health(request.app.state.pg, request.app.state.redis, getattr(request.app.state, "milvus_status", None))


@router.get("/health/deep")
async def health_deep(request: Request):
    return await deep_health(request.app.state.pg, request.app.state.redis, getattr(request.app.state, "milvus_status", None))


class HitlBody(BaseModel):
    workflowRunId: str
    decision: str


@router.post("/hitl/resume")
async def hitl_resume(body: HitlBody, request: Request, user=Depends(require_auth)):
    pg: PostgresPool = request.app.state.pg
    payload = await resume_checkpoint(pg, body.workflowRunId, body.decision)
    if not payload:
        raise HTTPException(status_code=404, detail="Checkpoint not found.")
    if body.decision == "approve":
        payload["status"] = "completed"
        payload["moralPathway"] = payload.get("hitl", {}).get("draftPathway") or payload.get("moralPathway")
    return {"success": True, "result": payload}


@router.get("/eco/daily")
async def eco_daily(request: Request, user=Depends(require_auth), date_str: str | None = None):
    pg = request.app.state.pg
    d = date.fromisoformat(date_str) if date_str else date.today()
    rollup = await get_daily_rollup(pg, user["email"], d)
    return {"success": True, "date": d.isoformat(), **rollup}


class FeedbackBody(BaseModel):
    requestId: str
    query: str | None = None
    status: str


@router.post("/feedback")
async def feedback(body: FeedbackBody, request: Request, user=Depends(require_auth)):
    if body.status not in {"FOLLOWED_DHARMA", "STRAYED_FROM_PATH"}:
        raise HTTPException(status_code=400, detail="Invalid feedback status.")
    pg = request.app.state.pg
    await pg.execute(
        """
        INSERT INTO feedback_records (request_id, user_email, query, status)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (request_id) DO UPDATE SET status = EXCLUDED.status
        """,
        body.requestId,
        user["email"],
        body.query,
        body.status,
    )
    return {"success": True, "message": "Feedback recorded."}


@router.delete("/feedback")
async def delete_all_feedback(request: Request, user=Depends(require_auth)):
    pg = request.app.state.pg
    command = await pg.execute(
        "DELETE FROM feedback_records WHERE user_email = $1",
        user["email"],
    )
    deleted = int(command.split()[-1]) if command.startswith("DELETE") else 0
    return {"success": True, "deleted": deleted}


@router.delete("/feedback/{request_id}")
async def delete_feedback(request_id: str, request: Request, user=Depends(require_auth)):
    pg = request.app.state.pg
    command = await pg.execute(
        "DELETE FROM feedback_records WHERE request_id = $1 AND user_email = $2",
        request_id,
        user["email"],
    )
    deleted = int(command.split()[-1]) if command.startswith("DELETE") else 0
    return {"success": True, "deleted": deleted}
