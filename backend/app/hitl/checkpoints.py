from datetime import datetime, timezone
from typing import Any
import json

from app.memory.postgres import PostgresPool


async def create_checkpoint(
    pg: PostgresPool,
    workflow_run_id: str,
    request_id: str,
    user_email: str,
    payload: dict[str, Any],
) -> None:
    await pg.execute(
        """
        INSERT INTO hitl_checkpoints (workflow_run_id, request_id, user_email, status, payload_json)
        VALUES ($1, $2, $3, 'pending', $4::jsonb)
        ON CONFLICT (workflow_run_id) DO UPDATE SET payload_json = EXCLUDED.payload_json, status = 'pending'
        """,
        workflow_run_id,
        request_id,
        user_email,
        json.dumps(payload),
    )


async def resume_checkpoint(pg: PostgresPool, workflow_run_id: str, decision: str) -> dict[str, Any] | None:
    row = await pg.fetchrow(
        "SELECT payload_json, status FROM hitl_checkpoints WHERE workflow_run_id = $1",
        workflow_run_id,
    )
    if not row:
        return None
    status = "approved" if decision == "approve" else "rejected"
    await pg.execute(
        """
        UPDATE hitl_checkpoints SET status = $2, resumed_at = $3 WHERE workflow_run_id = $1
        """,
        workflow_run_id,
        status,
        datetime.now(timezone.utc),
    )
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    payload["status"] = status
    payload["hitlDecision"] = decision
    return payload
