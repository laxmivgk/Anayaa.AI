"""Boring, explicit semantic cache policy for Anayaa final answers."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.llm.router import select_model

CACHE_SCHEMA_VERSION = "semantic_cache_schema_v2"
PROMPT_VERSION = "synthesis_prompt_v13_grounding_repair_retry"
PLANNER_VERSION = "llm_planner_compact_v4_static_prefix"
RETRIEVAL_VERSION = "mcp_milvus_graph_rerank_v3"
JUDGE_VERSION = "llm_judge_compact_grounding_contract_v5_source_named"


def cache_versions() -> dict[str, Any]:
    return {
        "cacheSchemaVersion": CACHE_SCHEMA_VERSION,
        "promptVersion": PROMPT_VERSION,
        "plannerVersion": PLANNER_VERSION,
        "retrievalVersion": RETRIEVAL_VERSION,
        "judgeVersion": JUDGE_VERSION,
        "modelVersion": {
            "planner": select_model("planner"),
            "synthesizer": select_model("synthesizer"),
            "judge": select_model("judge"),
        },
    }


def build_semantic_cache_key(dilemma: str, keywords: list[str]) -> tuple[str, dict[str, Any]]:
    """Hash the semantic inputs plus version stamps so old model/prompt behavior cannot resurface."""
    versions = cache_versions()
    normalized_keywords = [str(keyword).strip().lower() for keyword in keywords if str(keyword).strip()]
    key_payload = {
        **versions,
        "dilemma": str(dilemma or "").strip(),
        "keywords": normalized_keywords,
    }
    encoded = json.dumps(key_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:20], versions


def cache_policy_metadata(*, cache_key: str, cacheable: bool, reason: str) -> dict[str, Any]:
    return {
        **cache_versions(),
        "cacheKey": cache_key,
        "cacheable": cacheable,
        "reason": reason,
    }
