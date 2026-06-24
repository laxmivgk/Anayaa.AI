import hashlib
import re
from typing import Any

from app.llm.prompt_compressor import compress_query_prompt
from app.memory.redis_cache import RedisCache

REWRITE_REPLACEMENTS = {
    r"\bfrnd\b": "friend",
    r"\bfreind\b": "friend",
    r"\bfrnds\b": "friends",
    r"\bfam\b": "family",
    r"\bwrk\b": "work",
    r"\bpls\b": "please",
    r"\bplz\b": "please",
    r"\bu\b": "you",
    r"\bur\b": "your",
    r"\bmsg\b": "message",
    r"\btmrw\b": "tomorrow",
    r"\bbcoz\b": "because",
}

MORAL_REWRITE_TERMS = {
    "angry",
    "anger",
    "anxious",
    "anxiety",
    "betray",
    "cheat",
    "conflict",
    "forgive",
    "friend",
    "guilt",
    "honest",
    "hurt",
    "lied",
    "lying",
    "relationship",
    "truth",
    "wrong",
}

FOLLOW_UP_TERMS = {
    "above",
    "again",
    "also",
    "next",
    "same",
    "that",
    "then",
    "there",
    "this",
}


async def load_feedback_records(pg) -> list[dict[str, Any]]:
    rows = await pg.fetch("SELECT request_id, user_email, query, status, created_at FROM feedback_records ORDER BY created_at DESC")
    return [dict(r) for r in rows]


async def run_strategic_planner(
    dilemma: str,
    user_email: str,
    pg,
    *,
    optimized_query: str | None = None,
) -> dict[str, Any]:
    records = [r for r in await load_feedback_records(pg) if r.get("user_email") == user_email]
    followed = sum(1 for r in records if r.get("status") == "FOLLOWED_DHARMA")
    strayed = sum(1 for r in records if r.get("status") == "STRAYED_FROM_PATH")

    history_summary = f"No past feedback rows found for {user_email}. Initializing blank concierge path."
    tone_msg = ""
    if records:
        history_summary = (
            f"Found {len(records)} total interactive feedback entries for {user_email}: "
            f"{followed} followed dharma matches, {strayed} strayed boundaries."
        )
        if strayed > 0:
            tone_msg = "Compassionate Re-Alignment Mode Activated"
        elif followed > 0:
            tone_msg = "Steadfast Devotion Mode Activated"

    stopwords = {
        "about",
        "there",
        "their",
        "would",
        "could",
        "should",
        "under",
        "which",
        "other",
        "these",
        "those",
        "email",
        "phone",
        "redacted",
        "email_redacted",
        "phone_redacted",
    }
    planning_text = optimized_query or dilemma
    keywords = [
        w
        for w in re.sub(r"[^\w\s]", " ", planning_text.lower()).split()
        if len(w) > 4 and w not in stopwords
    ][:3]
    if not keywords:
        keywords = ["dharma", "duty", "virtue"]

    reasoning = (
        "Strategic Planner aligns this moral issue with wisdom from multi-faith scripts "
        "and virtues corresponding to the dilemma."
    )
    return {
        "keywords": keywords,
        "reasoning": reasoning,
        "historySummary": history_summary,
        "toneMsg": tone_msg,
    }


def _short_context_text(value: Any, max_chars: int = 280) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_chars]


def _should_use_previous_context(query: str, previous_context: dict[str, Any] | None) -> bool:
    if not previous_context or not _short_context_text(previous_context.get("question")):
        return False
    lower = query.lower()
    terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z]{2,}\b", lower))
    if terms & FOLLOW_UP_TERMS:
        return True
    if len(terms) <= 5 and any(phrase in lower for phrase in ["what should", "how should", "what now", "what next"]):
        return True
    return False


def _contextualize_follow_up(query: str, previous_context: dict[str, Any] | None) -> dict[str, Any]:
    original = query.strip()
    if not _should_use_previous_context(original, previous_context):
        return {
            "query": original,
            "previousContextUsed": False,
            "previousContextQuestion": None,
        }

    previous_question = _short_context_text(previous_context.get("question"))
    return {
        "query": f"Previous dilemma: {previous_question}. Follow-up question: {original}",
        "previousContextUsed": True,
        "previousContextQuestion": previous_question,
    }


def rewrite_malformed_query(query: str, previous_context: dict[str, Any] | None = None) -> dict[str, Any]:
    original = query.strip()
    contextual = _contextualize_follow_up(original, previous_context)
    rewritten = re.sub(r"\s+", " ", contextual["query"])
    rewritten = re.sub(r"([?!.,;:]){2,}", r"\1", rewritten)
    rewritten = rewritten.strip(" \t\n\r\"'")

    applied_rules: list[str] = []
    for pattern, replacement in REWRITE_REPLACEMENTS.items():
        next_value = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
        if next_value != rewritten:
            applied_rules.append(pattern.strip("\\b"))
            rewritten = next_value

    lower = rewritten.lower()
    terms = set(re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", lower))
    has_question_shape = any(
        phrase in lower
        for phrase in ["should i", "what should", "how should", "how can i", "is it right", "is it wrong", "?"]
    )
    looks_moral = bool(terms & MORAL_REWRITE_TERMS)

    if rewritten and looks_moral and not has_question_shape:
        rewritten = f"{rewritten}. What is the wisest and kindest thing to do?"
        applied_rules.append("added_moral_question_frame")

    return {
        "originalQuery": original,
        "rewrittenQuery": rewritten or original,
        "queryRewriteApplied": bool(applied_rules) and rewritten != original,
        "queryRewriteRules": applied_rules,
        "previousContextUsed": contextual["previousContextUsed"],
        "previousContextQuestion": contextual["previousContextQuestion"],
    }


def _build_sub_queries(dilemma: str, fallback_query: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", dilemma).strip()
    if not normalized:
        return [fallback_query]

    parts = re.split(
        r"\?+|;|\b(?:and|also|plus)\s+(?=(?:should|how|what|when|whether|do i|can i|is it|would it|could i)\b)",
        normalized,
        flags=re.IGNORECASE,
    )
    sub_queries: list[str] = []
    for part in parts:
        cleaned = part.strip(" .?,;:")
        if len(cleaned.split()) < 3:
            continue
        if cleaned.lower() not in {q.lower() for q in sub_queries}:
            sub_queries.append(cleaned)

    if len(sub_queries) < 2:
        return [normalized or fallback_query]
    return sub_queries[:3]


def optimize_query(dilemma: str, keywords: list[str], history_summary: str = "") -> dict[str, Any]:
    compression = compress_query_prompt(
        question=dilemma,
        context=history_summary,
        keywords=keywords,
    )
    compressed_query = compression.compressed_prompt or dilemma
    sub_queries = _build_sub_queries(dilemma, compressed_query)
    return {
        "subQueries": sub_queries,
        "multiQueryEnabled": len(sub_queries) > 1,
        "compressedQuery": compressed_query,
        "originalQuery": dilemma,
        "compressionMetrics": compression.to_dict(),
        "cacheKey": hashlib.sha256(f"react_v10|{dilemma}|{'|'.join(keywords)}".encode()).hexdigest()[:16],
        "faithFilters": [],
    }


async def evaluate_semantic_cache(redis: RedisCache, cache_key: str) -> dict[str, Any] | None:
    return await redis.get_json(f"semantic:{cache_key}")


async def store_semantic_cache(redis: RedisCache, cache_key: str, payload: dict[str, Any]) -> None:
    await redis.set_json(f"semantic:{cache_key}", payload, ttl_seconds=3600)


async def execute_unified_workflow(
    dilemma: str,
    user_email: str,
    pg,
    redis: RedisCache,
    eco,
    hitl_enabled: bool = True,
    milvus=None,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.agents.adk_workflow import run_adk_pipeline

    return await run_adk_pipeline(
        dilemma,
        user_email,
        pg,
        redis,
        eco,
        hitl_enabled=hitl_enabled,
        milvus=milvus,
        previous_context=previous_context,
    )
