from typing import Any

import psutil

from app.config import get_settings
from app.memory.postgres import PostgresPool
from app.memory.redis_cache import RedisCache
from app.retrieval.corpus import get_corpus


async def check_health(pg: PostgresPool, redis: RedisCache, milvus=None) -> dict[str, Any]:
    settings = get_settings()
    verse_count = len(get_corpus())
    row = await pg.get_corpus_status()
    corpus_ready = bool(row.get("ready"))
    verse_count = int(row.get("verse_count") or verse_count)

    milvus_status = {"available": False, "entities": 0, "hybrid": False}
    if isinstance(milvus, dict):
        milvus_status = {
            **milvus_status,
            **milvus,
            "collection": milvus.get("collection", settings.milvus_collection),
        }
    elif milvus and getattr(milvus, "available", False):
        milvus_status = {
            "available": True,
            "entities": milvus.entity_count(),
            "hybrid": bool(getattr(milvus, "hybrid_enabled", False)),
            "collection": settings.milvus_collection,
        }

    return {
        "status": "ok",
        "runtimeMode": "local",
        "postgres": {"enabled": settings.postgres_enabled, "available": pg.available, "required": True},
        "redis": await redis.ping(),
        "milvus": {
            **milvus_status,
            "enabled": settings.milvus_enabled,
        },
        "corpusReady": corpus_ready,
        "verseCount": verse_count,
        "corpusSource": "backend/data/scriptures.json",
        "cpuPercent": psutil.cpu_percent(interval=0.1),
        "memoryMb": round(psutil.virtual_memory().used / (1024 * 1024), 1),
        "ollamaUrl": settings.ollama_base_url,
        "embeddingModel": settings.embedding_model,
    }


async def deep_health(pg: PostgresPool, redis: RedisCache, milvus=None) -> dict[str, Any]:
    base = await check_health(pg, redis, milvus)
    base["deep"] = True
    base["scripturesLoaded"] = len(get_corpus())
    return base
