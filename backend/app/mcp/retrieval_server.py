"""Legacy MCP retrieval server shim — use milvus_retrieval_server.py instead."""
from app.mcp.milvus_retrieval_server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
