import pytest

from app.agents import adk_workflow


class FakeSessionService:
    def __init__(self):
        self.deleted = []

    async def delete_session(self, *, app_name, user_id, session_id):
        self.deleted.append(
            {
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
            }
        )


@pytest.mark.anyio
async def test_delete_adk_session_uses_in_memory_session_service(monkeypatch):
    service = FakeSessionService()
    monkeypatch.setattr(adk_workflow, "_session_service", service)

    await adk_workflow._delete_adk_session("user@example.com", "session_123")

    assert service.deleted == [
        {
            "app_name": "anayaa",
            "user_id": "user@example.com",
            "session_id": "session_123",
        }
    ]


@pytest.mark.anyio
async def test_delete_adk_session_skips_missing_session_id(monkeypatch):
    service = FakeSessionService()
    monkeypatch.setattr(adk_workflow, "_session_service", service)

    await adk_workflow._delete_adk_session("user@example.com", None)

    assert service.deleted == []
