import json
from typing import Any

from app.memory.postgres import PostgresPool


async def persist_audit_log(pg: PostgresPool, request_id: str, audit: dict[str, Any]) -> None:
    await pg.execute(
        """
        INSERT INTO audit_logs (request_id, g_eval_scores, judge_model, passed, raw_rationale)
        VALUES ($1, $2::jsonb, $3, $4, $5)
        """,
        request_id,
        json.dumps(audit.get("scores", {})),
        audit.get("judgeModel"),
        audit.get("passed", False),
        audit.get("rationale"),
    )
