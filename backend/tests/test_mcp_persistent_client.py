from types import SimpleNamespace

import pytest

from app.mcp import client as mcp_client


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_client_manager_reuses_one_session(monkeypatch):
    stdio_contexts = []
    session_contexts = []

    class FakeStdioContext:
        def __init__(self, params):
            self.params = params
            self.enter_count = 0
            self.exit_count = 0

        async def __aenter__(self):
            self.enter_count += 1
            return "read-stream", "write-stream"

        async def __aexit__(self, exc_type, exc, traceback):
            self.exit_count += 1
            return False

    class FakeClientSession:
        def __init__(self, read, write):
            self.read = read
            self.write = write
            self.enter_count = 0
            self.exit_count = 0
            self.initialize_count = 0
            session_contexts.append(self)

        async def __aenter__(self):
            self.enter_count += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            self.exit_count += 1
            return False

        async def initialize(self):
            self.initialize_count += 1

    def fake_stdio_client(params):
        context = FakeStdioContext(params)
        stdio_contexts.append(context)
        return context

    monkeypatch.setattr(mcp_client, "stdio_client", fake_stdio_client)
    monkeypatch.setattr(mcp_client, "ClientSession", FakeClientSession)

    manager = mcp_client.McpClientManager()

    first = await manager.get_session()
    second = await manager.get_session()

    assert first is second
    assert len(stdio_contexts) == 1
    assert len(session_contexts) == 1
    assert stdio_contexts[0].enter_count == 1
    assert session_contexts[0].enter_count == 1
    assert session_contexts[0].initialize_count == 1

    await manager.close()

    assert session_contexts[0].exit_count == 1
    assert stdio_contexts[0].exit_count == 1


@pytest.mark.anyio
async def test_call_mcp_tool_resets_and_retries_broken_session(monkeypatch):
    class FailingSession:
        async def call_tool(self, name, arguments):
            raise RuntimeError("stdio transport closed")

    class WorkingSession:
        async def call_tool(self, name, arguments):
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text='{"ok": true, "tool": "milvus_hybrid_search"}')],
            )

    class FakeManager:
        def __init__(self):
            self.sessions = [FailingSession(), WorkingSession()]
            self.get_count = 0
            self.close_count = 0

        async def get_session(self):
            session = self.sessions[self.get_count]
            self.get_count += 1
            return session

        async def close(self):
            self.close_count += 1

    manager = FakeManager()
    monkeypatch.setattr(mcp_client, "mcp_manager", manager)

    result = await mcp_client.call_mcp_tool("milvus_hybrid_search", {"query": "truth"})

    assert result == {"ok": True, "tool": "milvus_hybrid_search"}
    assert manager.get_count == 2
    assert manager.close_count == 1
