import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import psutil


@dataclass
class StageMetrics:
    stage: str
    energy_wh: float
    co2_kg: float
    cpu_watts: float
    gpu_watts: float
    duration_ms: int


@dataclass
class EcoTracker:
    request_id: str
    cache_hit: bool = False
    stages: list[StageMetrics] = field(default_factory=list)

    def audit_power_footprint(self, cache_hit: bool, confidence: float) -> dict[str, Any]:
        """Estimate local edge energy/CO2 for demo observability, not certified hardware metering."""
        base_cpu = 4.2
        base_gpu = 12.8
        if cache_hit:
            compute_sec = 0.002
            multiplier = 0.01
        else:
            compute_sec = 0.35 if confidence < 70 else 1.2
            multiplier = 2.4 if confidence >= 70 else 1.0

        cpu_wh = base_cpu * (compute_sec / 3600) * 1000
        gpu_wh = base_gpu * (compute_sec / 3600) * multiplier * 1000
        total_mwh = cpu_wh + gpu_wh
        co2 = (total_mwh / 1000) * 0.000385
        return {
            "energyMWh": round(total_mwh, 6),
            "co2Kg": round(co2, 8),
            "cpuWatts": round(base_cpu * multiplier, 2),
            "gpuWatts": round(base_gpu * multiplier, 2),
            "hardwareLevel": "Cache-Bypass Edge" if cache_hit else "Local Apple Silicon / NPU Node",
        }

    def track_stage(self, stage: str, cache_hit: bool = False, confidence: float = 80.0) -> StageMetrics:
        """Record a coarse per-stage footprint so the UI can show where local compute was spent."""
        start = time.perf_counter()
        cpu_before = psutil.cpu_percent(interval=0.05)
        metrics = self.audit_power_footprint(cache_hit, confidence)
        duration_ms = int((time.perf_counter() - start) * 1000)
        stage_metric = StageMetrics(
            stage=stage,
            energy_wh=metrics["energyMWh"] / 1000,
            co2_kg=metrics["co2Kg"],
            cpu_watts=max(metrics["cpuWatts"], cpu_before),
            gpu_watts=metrics["gpuWatts"],
            duration_ms=duration_ms,
        )
        self.stages.append(stage_metric)
        return stage_metric

    def totals(self) -> dict[str, Any]:
        total_energy = sum(s.energy_wh for s in self.stages)
        total_co2 = sum(s.co2_kg for s in self.stages)
        return {
            "energyMWh": round(total_energy * 1000, 6),
            "co2Kg": round(total_co2, 8),
            "ecoBreakdown": [
                {
                    "stage": s.stage,
                    "energyWh": round(s.energy_wh, 6),
                    "co2Kg": round(s.co2_kg, 8),
                    "cpuWatts": s.cpu_watts,
                    "gpuWatts": s.gpu_watts,
                    "durationMs": s.duration_ms,
                }
                for s in self.stages
            ],
        }


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:9]}"
