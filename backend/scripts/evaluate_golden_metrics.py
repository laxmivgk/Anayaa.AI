#!/usr/bin/env python3
"""Compute Anayaa golden-dataset retrieval and targeted F1 metrics from saved predictions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.observability.evaluation_dataset import load_evaluation_dataset
from app.observability.evaluation_metrics import retrieval_metrics_at_k, targeted_f1_from_results


def load_predictions(path: Path) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    candidates_by_id: dict[str, list[dict]] = {}
    results_by_id: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            row_id = str(row.get("id") or "")
            if not row_id:
                raise ValueError(f"Prediction row {line_number} is missing id")
            candidates_by_id[row_id] = row.get("retrievalCandidates") or row.get("rerankedCitations") or []
            results_by_id[row_id] = row.get("result") or row
    return candidates_by_id, results_by_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path, help="JSONL file with id, result, and retrievalCandidates/rerankedCitations")
    parser.add_argument("--k", type=int, default=3, help="Retrieval cutoff for precision@k and recall@k")
    args = parser.parse_args()

    dataset = load_evaluation_dataset()
    candidates_by_id, results_by_id = load_predictions(args.predictions)
    report = {
        "retrieval": retrieval_metrics_at_k(dataset, candidates_by_id, k=args.k),
        "targetedF1": targeted_f1_from_results(dataset, results_by_id),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
