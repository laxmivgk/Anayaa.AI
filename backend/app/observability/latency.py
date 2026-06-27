"""Per-request agent latency collection for Anayaa workflows."""
from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class AgentLatencyRecord:
    sequence: int
    agent: str
    category: str
    status: str
    duration_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "sequence": self.sequence,
            "agent": self.agent,
            "category": self.category,
            "status": self.status,
            "durationMs": self.duration_ms,
        }
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class AgentLatencyTracker:
    request_id: str
    records: list[AgentLatencyRecord] = field(default_factory=list)
    _started_at: float = field(default_factory=time.perf_counter)
    _sequence: int = 0

    def _append(self, agent: str, category: str, status: str, duration_ms: int, metadata: dict[str, Any] | None) -> None:
        self._sequence += 1
        clean_metadata = {
            str(key): value
            for key, value in (metadata or {}).items()
            if value is not None
        }
        self.records.append(
            AgentLatencyRecord(
                sequence=self._sequence,
                agent=agent,
                category=category,
                status=status,
                duration_ms=max(0, int(duration_ms)),
                metadata=clean_metadata,
            )
        )

    @contextmanager
    def track(
        self,
        agent: str,
        *,
        category: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        started = time.perf_counter()
        status = "completed"
        try:
            yield
        except Exception:
            status = "error"
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._append(agent, category, status, elapsed_ms, metadata)

    def mark(
        self,
        agent: str,
        *,
        category: str = "agent",
        status: str = "skipped",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._append(agent, category, status, 0, metadata)

    def snapshot(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "totalDurationMs": int((time.perf_counter() - self._started_at) * 1000),
            "agents": [record.to_dict() for record in self.records],
        }
