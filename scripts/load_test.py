#!/usr/bin/env python3
"""Dependency-free API load test for a live Anayaa backend."""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any


DEFAULT_QUERY = "How can I resolve a disagreement with a close friend honestly and compassionately?"
SUPPORTED_STATUSES = {200, 403, 429, 503}


@dataclass
class WorkerResult:
    requests: int = 0
    errors: int = 0
    status_counts: dict[int, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)

    def merge(self, other: "WorkerResult") -> None:
        self.requests += other.requests
        self.errors += other.errors
        self.latencies_ms.extend(other.latencies_ms)
        for status, count in other.status_counts.items():
            self.status_counts[status] = self.status_counts.get(status, 0) + count


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None, timeout: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def login(base_url: str, worker_id: int, timeout: float) -> str:
    email = os.environ.get("ANAYAA_LOAD_TEST_EMAIL", "codex.test@example.com")
    password = os.environ.get("ANAYAA_LOAD_TEST_PASSWORD")
    if not password:
        raise RuntimeError("ANAYAA_LOAD_TEST_PASSWORD must be set for load tests.")
    status, payload = post_json(
        f"{base_url}/api/auth/login",
        {"email": email, "password": password},
        None,
        timeout,
    )
    token = payload.get("token")
    if status != 200 or not token:
        raise RuntimeError(f"login failed for worker {worker_id}: status={status} payload={payload}")
    return str(token)


def worker(worker_id: int, args: argparse.Namespace, stop_at: float) -> WorkerResult:
    result = WorkerResult()
    try:
        token = login(args.base_url, worker_id, args.timeout)
    except Exception as exc:  # noqa: BLE001 - load tests should report setup failures clearly.
        result.requests += 1
        result.errors += 1
        print(f"[anayaa-load] worker={worker_id} login failed: {exc}", file=sys.stderr)
        return result
    headers = {"Authorization": f"Bearer {token}"}

    while time.monotonic() < stop_at:
        started = time.perf_counter()
        try:
            status, payload = post_json(
                f"{args.base_url}/api/query",
                {
                    "query": args.query,
                    "preSynthesisVerification": args.pre_synthesis,
                },
                headers,
                args.timeout,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            result.requests += 1
            result.latencies_ms.append(latency_ms)
            result.status_counts[status] = result.status_counts.get(status, 0) + 1

            if status not in SUPPORTED_STATUSES:
                result.errors += 1
            if status == 503 and not payload.get("status"):
                result.errors += 1
        except Exception as exc:  # noqa: BLE001 - load tests should report all request failures.
            result.requests += 1
            result.errors += 1
            print(f"[anayaa-load] worker={worker_id} request failed: {exc}", file=sys.stderr)

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    return result


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((percent / 100) * (len(ordered) - 1))))
    return ordered[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a lightweight Anayaa API load test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=3)
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--pre-synthesis", action="store_true")
    parser.add_argument("--p95-ms", type=float, default=60000)
    parser.add_argument("--max-error-rate", type=float, default=0.05)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--sleep-seconds", type=float, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.users <= 0:
        raise SystemExit("--users must be positive")
    if args.duration_seconds <= 0:
        raise SystemExit("--duration-seconds must be positive")

    args.base_url = args.base_url.rstrip("/")
    stop_at = time.monotonic() + args.duration_seconds
    combined = WorkerResult()
    lock = threading.Lock()

    print(
        "[anayaa-load] "
        f"target={args.base_url} users={args.users} duration={args.duration_seconds}s "
        f"preSynthesisVerification={args.pre_synthesis} p95ThresholdMs={args.p95_ms}",
        flush=True,
    )

    started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.users) as executor:
        futures = [executor.submit(worker, worker_id, args, stop_at) for worker_id in range(1, args.users + 1)]
        for future in as_completed(futures):
            partial = future.result()
            with lock:
                combined.merge(partial)
    elapsed_seconds = max(time.perf_counter() - started_at, 0.001)

    latencies = combined.latencies_ms
    total = combined.requests
    error_rate = combined.errors / total if total else 1.0
    p50 = statistics.median(latencies) if latencies else 0.0
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    rps = total / elapsed_seconds

    report = {
        "requests": total,
        "errors": combined.errors,
        "errorRate": error_rate,
        "elapsedSeconds": elapsed_seconds,
        "requestsPerSecond": rps,
        "statusCounts": {str(key): value for key, value in sorted(combined.status_counts.items())},
        "latencyMs": {
            "min": min(latencies) if latencies else 0.0,
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "max": max(latencies) if latencies else 0.0,
        },
        "passed": bool(total and error_rate <= args.max_error_rate and p95 <= args.p95_ms),
    }
    print(json.dumps(report, indent=2, sort_keys=True))

    if not report["passed"]:
        print("[anayaa-load] FAILED thresholds", file=sys.stderr)
        return 1
    print("[anayaa-load] passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
