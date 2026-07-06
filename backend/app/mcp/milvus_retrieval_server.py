"""MCP stdio server — Milvus hybrid search, graph expansion, and reranking."""
from __future__ import annotations

import atexit
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP

from app.config import get_settings
from app.memory.milvus_store import MilvusStore
from app.retrieval.corpus import expand_graph, get_corpus, load_scriptures_json
from app.retrieval.hybrid_search import rerank_candidates

logger = logging.getLogger(__name__)

mcp = FastMCP("anayaa-milvus-retrieval")
_store: MilvusStore | None = None


def _cleanup_store() -> None:
    global _store
    if _store is not None:
        try:
            logger.info("Cleaning up and closing MilvusStore connection...")
            _store.close()
        except Exception as exc:
            logger.warning("Error closing MilvusStore at process exit: %s", exc)


atexit.register(_cleanup_store)


def _get_store() -> MilvusStore:
    """Lazy-load the seeded local Milvus store when the first MCP tool call arrives."""
    global _store
    if _store is None:
        settings = get_settings()
        load_scriptures_json()
        corpus = get_corpus()
        # Fail fast if setup did not seed the collection. Retrieval quality is a
        # release requirement, so an empty store should never become a fallback.
        _store = MilvusStore(settings.milvus_uri)
        if not settings.milvus_enabled:
            raise RuntimeError("Milvus is disabled (MILVUS_ENABLED=false). Enable Milvus for retrieval.")
        connected = _store.connect()
        if not connected:
            raise RuntimeError(
                f"Milvus connection failed for URI {settings.milvus_uri}. "
                "Ensure milvus-lite is installed and the database is seeded."
            )
        if _store.entity_count() <= 0:
            raise RuntimeError(
                "Milvus collection is empty. Run `python scripts/seed_milvus.py` before querying."
            )
        _store._corpus_by_id = {verse.id: verse for verse in corpus}
    return _store


@mcp.tool()
def milvus_hybrid_search(
    query: str,
    keywords: list[str] | None = None,
    limit: int = 20,
) -> dict:
    """Search scripture verses using Milvus HNSW+BM25 hybrid search."""
    store = _get_store()
    keywords = keywords or []
    results = store.hybrid_search(query, keywords, limit=limit)
    return {"results": results, "source": "milvus", "count": len(results)}


@mcp.tool()
def graph_expand(keywords: list[str], limit: int = 10) -> dict:
    """Expand retrieval candidates via the scripture knowledge graph."""
    # Graph expansion complements vector search for moral themes such as duty,
    # restraint, compassion, and truth that may not share surface wording.
    results = expand_graph(get_corpus(), keywords, limit)
    return {"results": results, "count": len(results)}


@mcp.tool()
def rerank_candidates_tool(
    candidates: list[dict],
    query: str,
    top_k: int = 5,
) -> dict:
    """Rerank merged candidates with cross-encoder or keyword overlap."""
    results = rerank_candidates(candidates, query, top_k=top_k)
    return {"results": results, "count": len(results)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
