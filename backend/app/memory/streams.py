from datetime import datetime
from typing import Any
import random

_transaction_streams: list[dict[str, Any]] = []


def log_transaction(
    user_email: str,
    query: str,
    faith_count: int,
    cache_hit: bool,
    confidence: int,
    co2_kg: float,
    retry_details: dict[str, Any] | None = None,
    privacy_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.utcnow()
    log = {
        "timestamp": now.isoformat() + "Z",
        "requestId": f"req_{random.randbytes(4).hex()}",
        "userEmail": user_email,
        "querySummary": query[:60] + ("..." if len(query) > 60 else ""),
        "faithCount": faith_count,
        "cacheHit": cache_hit,
        "confidence": confidence,
        "powerCO2": co2_kg,
        "partitionTable": f"dilemma_logs_{now.year}_{now.month:02d}",
        "writeSpeedMs": round(0.4 + random.random() * 0.8, 2),
    }
    if retry_details:
        log["retryAttempts"] = retry_details.get("attempts", 0)
        log["retryRecovered"] = retry_details.get("recovered", False)
        log["retryDetails"] = retry_details
    if privacy_trace:
        log["privacyTrace"] = privacy_trace
    _transaction_streams.append(log)
    if len(_transaction_streams) > 50:
        _transaction_streams.pop(0)
    return log


def get_transaction_streams() -> list[dict[str, Any]]:
    return list(reversed(_transaction_streams))
