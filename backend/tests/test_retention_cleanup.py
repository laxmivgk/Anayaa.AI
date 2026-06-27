from types import SimpleNamespace

import pytest

from app.privacy.retention import enforce_postgres_retention, ensure_retention_indexes


class FakePostgres:
    def __init__(self):
        self.calls = []

    async def execute(self, query, *args):
        self.calls.append((query, args))
        if "DELETE FROM agent_traces" in query:
            return "DELETE 3"
        return "DELETE 0"


@pytest.mark.anyio
async def test_retention_deletes_agent_traces_with_own_window():
    pg = FakePostgres()
    settings = SimpleNamespace(
        audit_logs_retention_days=90,
        request_eco_metrics_retention_days=90,
        agent_traces_retention_days=30,
        hitl_terminal_retention_days=7,
        turns_retention_days=30,
    )

    result = await enforce_postgres_retention(pg, settings)

    assert result.agent_traces == 3
    assert result.to_dict()["agentTracesDeleted"] == 3
    agent_trace_calls = [call for call in pg.calls if "DELETE FROM agent_traces" in call[0]]
    assert agent_trace_calls
    assert agent_trace_calls[0][1] == (30,)


@pytest.mark.anyio
async def test_retention_indexes_include_agent_traces():
    pg = FakePostgres()

    await ensure_retention_indexes(pg)

    assert any("idx_agent_traces_created_at" in query for query, _ in pg.calls)
