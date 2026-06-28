"""Retrieval client for Milvus search, graph expansion, and reranking."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agents.pipeline_errors import RetrievalError

logger = logging.getLogger(__name__)

SERVER_PATH = Path(__file__).resolve().parent / "milvus_retrieval_server.py"
_MCP_RETRIEVAL_LOCK = asyncio.Lock()
ALLOWED_MCP_TOOLS = frozenset(
    {
        "milvus_hybrid_search",
        "graph_expand",
        "rerank_candidates_tool",
    }
)


def _ensure_allowed_tool(name: str) -> None:
    if name not in ALLOWED_MCP_TOOLS:
        raise RetrievalError(f"MCP tool '{name}' is not allowed by the retrieval client policy")


def _parse_tool_result(result: Any) -> dict[str, Any]:
    if result.isError:
        message = ""
        for block in result.content or []:
            text = getattr(block, "text", None)
            if text:
                message += text
        raise RetrievalError(message or "MCP tool returned an error")

    for block in result.content or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RetrievalError(f"Invalid MCP tool JSON: {exc}") from exc
    raise RetrievalError("MCP tool returned no content")


@asynccontextmanager
async def mcp_session() -> AsyncIterator[ClientSession]:
    """Open a stdio MCP session to the Milvus retrieval server."""
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER_PATH)],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a single MCP tool in an isolated subprocess."""
    _ensure_allowed_tool(name)
    async with mcp_session() as session:
        return await _call_mcp_tool_in_session(session, name, arguments)


async def retrieve_via_mcp(query: str, keywords: list[str], limit: int = 10, top_k: int = 3) -> dict[str, Any]:
    """Run retrieval only through the MCP server boundary."""
    async with _MCP_RETRIEVAL_LOCK:
        async with mcp_session() as session:
            hybrid_data = await _call_mcp_tool_in_session(
                session,
                "milvus_hybrid_search",
                {"query": query, "keywords": keywords or [], "limit": limit},
            )
            graph_data = await _call_mcp_tool_in_session(
                session,
                "graph_expand",
                {"keywords": keywords or [], "limit": 10},
            )
            candidates = _merge_candidates(hybrid_data, graph_data, limit)
            reranked_data = await _call_mcp_tool_in_session(
                session,
                "rerank_candidates_tool",
                {"candidates": candidates, "query": query, "top_k": top_k},
            )

    return {
        "hybridSource": hybrid_data.get("source", "milvus"),
        "candidates": candidates,
        "reranked": reranked_data.get("results", []),
        "mcp": True,
    }


async def _call_mcp_tool_in_session(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    _ensure_allowed_tool(name)
    result = await session.call_tool(name, arguments)
    return _parse_tool_result(result)


def _merge_candidates(hybrid_data: dict[str, Any], graph_data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in hybrid_data.get("results", []) + graph_data.get("results", []):
        verse = item.get("verse") or {}
        verse_id = verse.get("id")
        if not verse_id:
            continue
        if verse_id not in merged or item.get("score", 0) > merged[verse_id].get("score", 0):
            merged[verse_id] = item

<<<<<<< HEAD
    ranked = sorted(merged.values(), key=lambda row: row.get("score", 0), reverse=True)
    selected = ranked[:limit]
    if any(item.get("method") == "KnowledgeGraph" for item in selected):
        return selected

    graph_items = [
        item
        for item in graph_data.get("results", [])
        if (item.get("verse") or {}).get("id") and item.get("score", 0) >= 70
    ]
    if not graph_items or limit <= 0:
        return selected

    top_graph = max(graph_items, key=lambda row: row.get("score", 0))
    top_graph_id = (top_graph.get("verse") or {}).get("id")
    if any((item.get("verse") or {}).get("id") == top_graph_id for item in selected):
        return selected

    return sorted([*selected[: max(limit - 1, 0)], top_graph], key=lambda row: row.get("score", 0), reverse=True)
=======
    return sorted(merged.values(), key=lambda row: row.get("score", 0), reverse=True)[:limit]
>>>>>>> origin/main
