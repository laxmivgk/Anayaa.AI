from datetime import date
from typing import Any

from app.memory.postgres import PostgresPool


async def upsert_daily_rollup(
    pg: PostgresPool,
    user_email: str,
    energy_wh: float,
    co2_kg: float,
    rollup_date: date | None = None,
) -> None:
    d = rollup_date or date.today()
    await pg.execute(
        """
        INSERT INTO daily_eco_rollups (rollup_date, user_email, total_energy_wh, total_co2_kg, query_count)
        VALUES ($1, $2, $3, $4, 1)
        ON CONFLICT (rollup_date, user_email) DO UPDATE SET
            total_energy_wh = daily_eco_rollups.total_energy_wh + EXCLUDED.total_energy_wh,
            total_co2_kg = daily_eco_rollups.total_co2_kg + EXCLUDED.total_co2_kg,
            query_count = daily_eco_rollups.query_count + 1
        """,
        d,
        user_email,
        energy_wh,
        co2_kg,
    )


async def get_daily_rollup(pg: PostgresPool, user_email: str, rollup_date: date | None = None) -> dict[str, Any]:
    d = rollup_date or date.today()
    row = await pg.fetchrow(
        """
        SELECT total_energy_wh, total_co2_kg, query_count
        FROM daily_eco_rollups WHERE rollup_date = $1 AND user_email = $2
        """,
        d,
        user_email,
    )
    if not row:
        return {"totalEnergyWh": 0, "totalCo2Kg": 0, "queryCount": 0}
    return {
        "totalEnergyWh": float(row["total_energy_wh"]),
        "totalCo2Kg": float(row["total_co2_kg"]),
        "queryCount": int(row["query_count"]),
    }


async def persist_request_eco(pg: PostgresPool, request_id: str, user_email: str, stages: list[dict[str, Any]], cache_hit: bool) -> None:
    for stage in stages:
        await pg.execute(
            """
            INSERT INTO request_eco_metrics
            (request_id, user_email, agent_stage, energy_wh, co2_kg, cpu_watts, gpu_watts, duration_ms, cache_hit)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            request_id,
            user_email,
            stage["stage"],
            stage["energyWh"],
            stage["co2Kg"],
            stage.get("cpuWatts", 0),
            stage.get("gpuWatts", 0),
            stage.get("durationMs", 0),
            cache_hit,
        )
