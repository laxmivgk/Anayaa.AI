"""PostgreSQL retention policy enforcement."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass

from app.config import Settings
from app.memory.postgres import PostgresPool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetentionResult:
    audit_logs: int
    request_eco_metrics: int
    hitl_checkpoints: int
    turns: int

    def to_dict(self) -> dict[str, int]:
        return {
            "auditLogsDeleted": self.audit_logs,
            "requestEcoMetricsDeleted": self.request_eco_metrics,
            "hitlCheckpointsDeleted": self.hitl_checkpoints,
            "turnsDeleted": self.turns,
        }


def _deleted_count(command_tag: str) -> int:
    """Extract row count from asyncpg command tags like 'DELETE 12'."""
    with contextlib.suppress(IndexError, ValueError):
        return int(command_tag.split()[-1])
    return 0


async def ensure_retention_indexes(pg: PostgresPool) -> None:
    """Create indexes used by retention cleanup for already-initialized DBs."""
    statements = [
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_request_eco_metrics_created_at ON request_eco_metrics(created_at)",
        """
        CREATE INDEX IF NOT EXISTS idx_hitl_checkpoints_terminal_retention
        ON hitl_checkpoints(status, resumed_at, created_at)
        """,
        "CREATE INDEX IF NOT EXISTS idx_turns_created_at ON turns(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_records_user_email ON feedback_records(user_email)",
    ]
    for statement in statements:
        await pg.execute(statement)


async def enforce_postgres_retention(pg: PostgresPool, settings: Settings) -> RetentionResult:
    """Delete Postgres rows that exceed the configured retention windows."""
    audit_logs = _deleted_count(
        await pg.execute(
            """
            DELETE FROM audit_logs
            WHERE created_at < NOW() - ($1::int * INTERVAL '1 day')
            """,
            settings.audit_logs_retention_days,
        )
    )
    request_eco_metrics = _deleted_count(
        await pg.execute(
            """
            DELETE FROM request_eco_metrics
            WHERE created_at < NOW() - ($1::int * INTERVAL '1 day')
            """,
            settings.request_eco_metrics_retention_days,
        )
    )
    hitl_checkpoints = _deleted_count(
        await pg.execute(
            """
            DELETE FROM hitl_checkpoints
            WHERE status IN ('approved', 'rejected')
              AND COALESCE(resumed_at, created_at) < NOW() - ($1::int * INTERVAL '1 day')
            """,
            settings.hitl_terminal_retention_days,
        )
    )
    turns = _deleted_count(
        await pg.execute(
            """
            DELETE FROM turns
            WHERE created_at < NOW() - ($1::int * INTERVAL '1 day')
            """,
            settings.turns_retention_days,
        )
    )

    return RetentionResult(
        audit_logs=audit_logs,
        request_eco_metrics=request_eco_metrics,
        hitl_checkpoints=hitl_checkpoints,
        turns=turns,
    )


async def retention_loop(pg: PostgresPool, settings: Settings) -> None:
    """Run retention cleanup daily until the app shuts down."""
    try:
        await ensure_retention_indexes(pg)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Postgres retention index setup failed")

    while True:
        try:
            result = await enforce_postgres_retention(pg, settings)
            logger.info("Postgres retention cleanup completed: %s", result.to_dict())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Postgres retention cleanup failed")
        await asyncio.sleep(settings.retention_cleanup_interval_seconds)
