"""Retrieval client for Milvus search, graph expansion, and reranking."""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.agents.pipeline_errors import RetrievalError

logger = logging.getLogger(__name__)

SERVER_PATH = Path(__file__).resolve().parent / "milvus_retrieval_server.py"

# Retrieval reuses one stdio MCP subprocess for the API lifetime; this lock serializes
# tool sequences so Milvus Lite is not accessed concurrently through the same local DB.
_MCP_RETRIEVAL_LOCK = asyncio.Lock()

# Keep the reasoning workflow on a narrow tool surface instead of exposing arbitrary MCP tools.
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


class McpClientManager:
    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._lock = asyncio.Lock()

    async def get_session(self) -> ClientSession:
        async with self._lock:
            if self._session is not None:
                return self._session

            try:
                # The MCP server is a local stdio subprocess, not a network
                # service. Restarting the subprocess is enough to recover most
                # transient Milvus Lite handle issues during beta runs.
                logger.info("Initializing persistent MCP retrieval server subprocess...")
                stack = AsyncExitStack()
                params = StdioServerParameters(
                    command=sys.executable,
                    args=[str(SERVER_PATH)],
                )
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()

                self._exit_stack = stack
                self._session = session
                logger.info("Persistent MCP retrieval server initialized successfully.")
                return self._session
            except Exception as exc:
                logger.error("Failed to initialize persistent MCP session: %s. Cleaning up.", exc)
                try:
                    await stack.aclose()
                except Exception as cleanup_exc:
                    logger.warning("Error cleaning up failed MCP initialization: %s", cleanup_exc)
                raise

    async def _close_under_lock(self) -> None:
        stack = self._exit_stack
        self._session = None
        self._exit_stack = None
        if stack is not None:
            logger.info("Terminating persistent MCP stdio server process...")
            try:
                await stack.aclose()
            except Exception as exc:
                logger.warning("Error closing persistent MCP client: %s", exc)

    async def close(self) -> None:
        async with self._lock:
            await self._close_under_lock()


mcp_manager = McpClientManager()


async def close_mcp_client() -> None:
    """Shutdown the persistent retrieval MCP server process."""
    await mcp_manager.close()


async def call_mcp_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Call a single MCP tool using the persistent retrieval process."""
    _ensure_allowed_tool(name)
    try:
        session = await mcp_manager.get_session()
        return await _call_mcp_tool_in_session(session, name, arguments)
    except RetrievalError:
        raise
    except Exception as exc:
        logger.warning("MCP tool call failed: %s. Resetting session and retrying once.", exc)
        await mcp_manager.close()
        try:
            session = await mcp_manager.get_session()
            return await _call_mcp_tool_in_session(session, name, arguments)
        except Exception as retry_exc:
            logger.warning("MCP tool call failed after session reset: %s.", retry_exc)
            await mcp_manager.close()
            raise


async def retrieve_via_mcp(query: str, keywords: list[str], limit: int = 10, top_k: int = 3) -> dict[str, Any]:
    """Run retrieval only through the persistent MCP server process boundary."""
    async with _MCP_RETRIEVAL_LOCK:
        try:
            # Hybrid search, graph expansion, and reranking are one logical tool
            # sequence; keep them serialized so local Milvus Lite stays stable.
            hybrid_data, graph_data, candidates, reranked_data = await _run_retrieval_sequence(
                query,
                keywords,
                limit,
                top_k,
            )
        except RetrievalError:
            raise
        except Exception as exc:
            logger.warning("MCP retrieval via persistent session failed: %s. Resetting session and retrying once.", exc)
            await mcp_manager.close()
            try:
                hybrid_data, graph_data, candidates, reranked_data = await _run_retrieval_sequence(
                    query,
                    keywords,
                    limit,
                    top_k,
                )
            except Exception as retry_exc:
                logger.warning("MCP retrieval failed after session reset: %s.", retry_exc)
                await mcp_manager.close()
                raise

    return {
        "hybridSource": hybrid_data.get("source", "milvus"),
        "candidates": candidates,
        "reranked": reranked_data.get("results", []),
        "mcp": True,
    }


async def _run_retrieval_sequence(
    query: str,
    keywords: list[str],
    limit: int,
    top_k: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    session = await mcp_manager.get_session()
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
    return hybrid_data, graph_data, candidates, reranked_data


async def _call_mcp_tool_in_session(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    _ensure_allowed_tool(name)
    result = await session.call_tool(name, arguments)
    return _parse_tool_result(result)


def _merge_candidates(hybrid_data: dict[str, Any], graph_data: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Merge vector and graph candidates while preserving at least one strong graph result."""
    merged: dict[str, dict[str, Any]] = {}
    for item in hybrid_data.get("results", []) + graph_data.get("results", []):
        verse = item.get("verse") or {}
        verse_id = verse.get("id")
        if not verse_id:
            continue
        if verse_id not in merged or item.get("score", 0) > merged[verse_id].get("score", 0):
            merged[verse_id] = item

    ranked = sorted(merged.values(), key=lambda row: row.get("score", 0), reverse=True)
    selected = ranked[:limit]
    if any(item.get("method") == "KnowledgeGraph" for item in selected):
        return selected

    # Preserve one strong graph result when vector ranking crowds it out; this
    # keeps scripture-theme connections visible to the reranker.
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
