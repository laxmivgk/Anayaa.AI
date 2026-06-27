"""Utilities for loading Anayaa's source-controlled evaluation dataset."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


EVALUATION_DATASET_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "anayaa_eval_dataset.jsonl"
REQUIRED_EVAL_FIELDS = {
    "id",
    "query",
    "category",
    "expectedStatus",
    "expectedKeywords",
    "expectedCitationThemes",
    "minimumScores",
    "disallowedResponsePatterns",
}


def load_evaluation_dataset(path: Path = EVALUATION_DATASET_PATH) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            row = json.loads(text)
            missing = REQUIRED_EVAL_FIELDS - set(row)
            if missing:
                raise ValueError(f"Evaluation row {line_number} is missing fields: {sorted(missing)}")
            if not isinstance(row["expectedKeywords"], list) or not row["expectedKeywords"]:
                raise ValueError(f"Evaluation row {line_number} must define expectedKeywords")
            if not isinstance(row["minimumScores"], dict):
                raise ValueError(f"Evaluation row {line_number} must define minimumScores")
            rows.append(row)
    if not rows:
        raise ValueError("Evaluation dataset is empty")
    return rows
