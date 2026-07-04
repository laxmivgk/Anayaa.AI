from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_auth
from app.agents.pipeline_errors import PipelineError
from app.agents.pipeline_messages import build_hitl_compile_failure_user_message
from app.eco.aggregator import get_daily_rollup
from app.hitl.checkpoints import resume_checkpoint
from app.llm.generator import generate_moral_pathway
from app.memory.postgres import PostgresPool
from app.memory.streams import get_transaction_streams
from app.observability.audit_logger import persist_audit_log
from app.observability.g_eval_judge import run_g_eval_judge
from app.observability.guidance_reasons import build_guidance_reasons
from app.retrieval.corpus import get_corpus
from app.resilience.health import check_health, deep_health
from app.security.harm_normalizer import normalize_harmful_concepts, normalize_harmful_framing_text
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system/status")
async def system_status(request: Request):
    pg = request.app.state.pg
    redis = request.app.state.redis
    health = await check_health(pg, redis, getattr(request.app.state, "milvus_status", None))
    return {
        "quantizedModel": "qwen3:4b-local",
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
    concepts: list[str] | None = None
    selectedVerseIds: list[str] | None = None
    manualVerse: dict[str, str] | None = None


def _manual_verse_to_citation(manual_verse: dict[str, str] | None) -> dict | None:
    if not manual_verse:
        return None
    translation = str(manual_verse.get("translation") or "").strip()
    if not translation:
        return None
    source = str(manual_verse.get("source") or "Manual scripture").strip()[:120]
    faith = str(manual_verse.get("faith") or "User provided").strip()[:80]
    chapter = str(manual_verse.get("chapter") or "").strip()[:80]
    verse = str(manual_verse.get("verse") or "").strip()[:80]
    context = str(manual_verse.get("context") or "User-provided verse for pre-synthesis grounding.").strip()[:240]
    keywords = [
        keyword.strip().lower()
        for keyword in str(manual_verse.get("keywords") or "").split(",")
        if keyword.strip()
    ][:8]
    return {
        "id": f"manual-{abs(hash((source, chapter, verse, translation))) % 10_000_000}",
        "faith": faith,
        "source": source,
        "chapter": chapter,
        "verse": verse,
        "translation": translation[:800],
        "context": context,
        "keywords": keywords or ["manual", "guidance"],
        "originalText": str(manual_verse.get("originalText") or "").strip()[:800] or None,
    }


def _approved_pre_synthesis_citations(payload: dict, body: HitlBody) -> list[dict]:
    hitl = payload.get("hitl") or {}
    candidate_items = hitl.get("candidateScriptures") or []
    selected_ids = set(body.selectedVerseIds or hitl.get("selectedVerseIds") or [])
    citations: list[dict] = []
    for item in candidate_items:
        verse = item.get("verse") if isinstance(item, dict) else None
        if not isinstance(verse, dict):
            continue
        verse_id = str(verse.get("id") or "")
        if selected_ids and verse_id not in selected_ids:
            continue
        citations.append(verse)

    manual_citation = _manual_verse_to_citation(body.manualVerse)
    if manual_citation:
        citations.append(manual_citation)

    seen: set[str] = set()
    deduped: list[dict] = []
    for citation in citations:
        citation_id = str(citation.get("id") or citation.get("translation") or "")
        if citation_id in seen:
            continue
        seen.add(citation_id)
        deduped.append(citation)
    return deduped[:4]


def _hitl_compile_audit_query(dilemma: str, concepts: list[str]) -> str:
    """Judge interactive compile against the user's dilemma plus selected focus terms."""
    safe_dilemma = normalize_harmful_framing_text(dilemma)
    safe_lower = safe_dilemma.lower()
    focus_terms: list[str] = []
    for concept in normalize_harmful_concepts(concepts):
        term = str(concept or "").strip().lower()
        if not term or term in safe_lower or term in focus_terms:
            continue
        focus_terms.append(term)
    if not focus_terms:
        return safe_dilemma
    return f"{safe_dilemma} Selected concepts: {', '.join(focus_terms)}"


def _hitl_compile_synthesis_tone(base_tone: str, concepts: list[str], *, retry: bool = False) -> str:
    focus_terms = [str(concept).strip().lower() for concept in concepts if str(concept).strip()][:8]
    parts = [str(base_tone or "Balanced guidance mode").strip()]
    if focus_terms:
        parts.append(f"Interactive compile selected concepts: {', '.join(focus_terms)}.")
    parts.append(
        "Interactive compile mode: use the selected scriptures as the grounding source. "
        "In Scripture grounding, name at least two selected scripture sources exactly and reuse one anchor "
        "keyword from each."
    )
    if retry:
        parts.append(
            "Regenerate because the previous draft did not prove enough support from the selected scripture passages. "
            "Make the Scripture grounding section explicit, concrete, and tied to two selected citations."
        )
    return " ".join(part for part in parts if part)


def _should_retry_hitl_compile(audit: dict, citations: list[dict]) -> bool:
    if audit.get("passed") or len(citations) < 2:
        return False
    failed = set(audit.get("failedDimensions") or [])
    grounding_failed = bool(failed & {"citation_grounding", "context_grounding", "grounding_contract"})
    contract = audit.get("groundingContract") or {}
    contract_failed = bool(
        set(contract.get("failedChecks") or [])
        & {"scriptureGroundingSectionPresent", "citationTermsInScriptureGrounding"}
    )
    return grounding_failed or contract_failed


@router.post("/hitl/resume")
async def hitl_resume(body: HitlBody, request: Request, user=Depends(require_auth)):
    pg: PostgresPool = request.app.state.pg
    payload = await resume_checkpoint(pg, body.workflowRunId, body.decision)
    if not payload:
        raise HTTPException(status_code=404, detail="Checkpoint not found.")
    if body.decision != "approve":
        return {"success": True, "result": payload}

    hitl = payload.get("hitl") or {}
    if hitl.get("stage") == "pre_synthesis_verification":
        citations = _approved_pre_synthesis_citations(payload, body)
        if not citations:
            raise HTTPException(status_code=400, detail="Select at least one scripture or add a manual verse.")

        concept_source = body.concepts if body.concepts is not None else (
            hitl.get("proposedKeywords") or payload.get("keywords") or []
        )
        concepts = [
            str(concept).strip().lower()
            for concept in concept_source
            if str(concept).strip()
        ][:8]
        concepts = normalize_harmful_concepts(concepts)
        dilemma = payload.get("rewrittenQuery") or payload.get("originalQuery") or ""
        try:
            synthesis_tone = _hitl_compile_synthesis_tone(payload.get("toneMsg") or "", concepts)
            pathway, metrics = await generate_moral_pathway(dilemma, citations, synthesis_tone)
        except PipelineError as exc:
            return {
                "success": True,
                "result": {
                    **payload,
                    "status": "synthesizer_unavailable",
                    "userMessage": exc.user_message,
                    "failureReason": "synthesizer_service_unavailable",
                    "synthesizerError": str(exc),
                    "hitlDecision": body.decision,
                    "humanApprovedConcepts": concepts,
                    "keywords": concepts or payload.get("keywords", []),
                    "citations": citations,
                    "moralPathway": None,
                    "guidanceReasons": [],
                    "hitl": {
                        **hitl,
                        "approvedConcepts": concepts,
                        "approvedVerseIds": [str(citation.get("id")) for citation in citations if citation.get("id")],
                    },
                    "quantizedMetrics": None,
                    "synthesisEngine": None,
                    "auditScores": None,
                    "confidence": max([item.get("score", 0) for item in payload.get("rerankedCitations", [])] or [payload.get("confidence", 0)]),
                    "cacheHit": False,
                },
            }
        # Judge compiled HITL guidance against the user's dilemma, with selected concepts as extra focus.
        audit_query = _hitl_compile_audit_query(dilemma, concepts)
        audit = await run_g_eval_judge(audit_query, citations, pathway)
        if _should_retry_hitl_compile(audit, citations):
            try:
                retry_tone = _hitl_compile_synthesis_tone(payload.get("toneMsg") or "", concepts, retry=True)
                retry_pathway, retry_metrics = await generate_moral_pathway(dilemma, citations, retry_tone)
                retry_audit = await run_g_eval_judge(audit_query, citations, retry_pathway)
                if retry_audit.get("passed"):
                    pathway = retry_pathway
                    metrics = {**retry_metrics, "hitlGroundingRetry": True}
                    audit = retry_audit
                else:
                    audit["hitlGroundingRetry"] = {
                        "attempted": True,
                        "passed": False,
                        "failedDimensions": retry_audit.get("failedDimensions", []),
                    }
            except PipelineError as exc:
                audit["hitlGroundingRetry"] = {
                    "attempted": True,
                    "passed": False,
                    "error": str(exc),
                }
        await persist_audit_log(pg, payload.get("requestId") or body.workflowRunId, audit)

        result = {
            **payload,
            "status": "completed" if audit.get("passed") else "quality_threshold_not_met",
            "userMessage": None
            if audit.get("passed")
            else build_hitl_compile_failure_user_message(audit, audit.get("minScore", 3)),
            "hitlDecision": body.decision,
            "humanApprovedConcepts": concepts,
            "keywords": concepts or payload.get("keywords", []),
            "citations": citations,
            "moralPathway": pathway if audit.get("passed") else None,
            "guidanceReasons": build_guidance_reasons(dilemma, citations, pathway, audit) if audit.get("passed") else [],
            "hitl": {
                **hitl,
                "approvedConcepts": concepts,
                "approvedVerseIds": [str(citation.get("id")) for citation in citations if citation.get("id")],
            },
            "quantizedMetrics": metrics,
            "synthesisEngine": metrics.get("engine"),
            "auditScores": audit,
            "confidence": max([item.get("score", 0) for item in payload.get("rerankedCitations", [])] or [payload.get("confidence", 0)]),
            "cacheHit": False,
        }
        return {"success": True, "result": result}

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
