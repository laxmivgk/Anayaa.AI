"""Offline evaluation metrics for Anayaa golden-dataset checks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


METRIC_STOPWORDS = {
    "about",
    "after",
    "again",
    "because",
    "could",
    "dharma",
    "dilemma",
    "guidance",
    "right",
    "should",
    "their",
    "there",
    "these",
    "those",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}


def _tokens(value: Any) -> set[str]:
    terms = set()
    for token in re.findall(r"\b[a-zA-Z][a-zA-Z]{3,}\b", str(value or "").lower()):
        if token not in METRIC_STOPWORDS:
            terms.add(token)
    return terms


def _expected_terms(row: dict[str, Any]) -> set[str]:
    values = [*(row.get("expectedKeywords") or []), *(row.get("expectedCitationThemes") or [])]
    terms: set[str] = set()
    for value in values:
        terms.update(_tokens(value))
    return terms


def _verse_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    verse = candidate.get("verse")
    return verse if isinstance(verse, dict) else candidate


def _candidate_terms(candidate: dict[str, Any]) -> set[str]:
    verse = _verse_from_candidate(candidate)
    values = [
        verse.get("faith"),
        verse.get("source"),
        verse.get("translation"),
        verse.get("context"),
        " ".join(str(keyword) for keyword in (verse.get("keywords") or [])),
    ]
    terms: set[str] = set()
    for value in values:
        terms.update(_tokens(value))
    return terms


def is_relevant_candidate(row: dict[str, Any], candidate: dict[str, Any]) -> bool:
    expected = _expected_terms(row)
    if not expected:
        return False
    return bool(expected & _candidate_terms(candidate))


def precision_at_k(row: dict[str, Any], candidates: list[dict[str, Any]], k: int = 3) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    top_k = candidates[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for candidate in top_k if is_relevant_candidate(row, candidate))
    return relevant / len(top_k)


def recall_at_k(row: dict[str, Any], candidates: list[dict[str, Any]], k: int = 3) -> float:
    if k <= 0:
        raise ValueError("k must be positive")
    expected = _expected_terms(row)
    if not expected:
        return 0.0
    covered: set[str] = set()
    for candidate in candidates[:k]:
        covered.update(expected & _candidate_terms(candidate))
    return len(covered) / len(expected)


def retrieval_metrics_at_k(
    rows: list[dict[str, Any]],
    candidates_by_id: dict[str, list[dict[str, Any]]],
    *,
    k: int = 3,
) -> dict[str, Any]:
    per_case = []
    for row in rows:
        row_id = str(row.get("id"))
        candidates = candidates_by_id.get(row_id, [])
        per_case.append(
            {
                "id": row_id,
                "precisionAtK": precision_at_k(row, candidates, k),
                "recallAtK": recall_at_k(row, candidates, k),
                "k": k,
            }
        )
    count = len(per_case) or 1
    return {
        "k": k,
        "macroPrecisionAtK": sum(item["precisionAtK"] for item in per_case) / count,
        "macroRecallAtK": sum(item["recallAtK"] for item in per_case) / count,
        "perCase": per_case,
    }


def _retrieval_report_score(report: dict[str, Any], *keys: str) -> float:
    current: Any = report
    for key in keys:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key)
    try:
        return float(current or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _retrieval_report_unsupported(report: dict[str, Any]) -> bool:
    relevance = report.get("retrievalRelevance") if isinstance(report.get("retrievalRelevance"), dict) else report
    return bool(relevance.get("unsupportedQueryReason"))


def _observed_thresholds(values: list[float], default: float) -> list[float]:
    observed = sorted({round(value, 4) for value in values if value >= 0})
    candidates = {0.0, round(default, 4), *observed}
    for value in observed:
        candidates.add(round(value + 0.0001, 4))
    return sorted(candidates)


def calibrate_retrieval_gate_thresholds(
    rows: list[dict[str, Any]],
    reports_by_id: dict[str, dict[str, Any]],
    *,
    default_score_threshold: float = 40.0,
    default_semantic_threshold: float = 0.17,
) -> dict[str, Any]:
    """Recommend retrieval thresholds from labeled eval rows and raw retrieval reports."""
    cases: list[dict[str, Any]] = []
    for row in rows:
        expected_status = row.get("expectedStatus")
        if expected_status not in {"completed", "insufficient_context"}:
            continue
        report = reports_by_id.get(str(row.get("id"))) or {}
        relevance = report.get("retrievalRelevance") if isinstance(report.get("retrievalRelevance"), dict) else report
        top_score = _retrieval_report_score(report, "rawTopRetrievalScore") or _retrieval_report_score(report, "topRetrievalScore")
        semantic = _retrieval_report_score(relevance, "maxSemanticSimilarity")
        cases.append(
            {
                "id": str(row.get("id")),
                "expectedPass": expected_status == "completed",
                "topScore": top_score,
                "semanticSimilarity": semantic,
                "unsupported": _retrieval_report_unsupported(report),
            }
        )

    score_thresholds = _observed_thresholds([case["topScore"] for case in cases], default_score_threshold)
    semantic_thresholds = _observed_thresholds(
        [case["semanticSimilarity"] for case in cases],
        default_semantic_threshold,
    )

    best: dict[str, Any] | None = None
    for score_threshold in score_thresholds:
        for semantic_threshold in semantic_thresholds:
            tp = tn = fp = fn = 0
            per_case = []
            for case in cases:
                predicted_pass = (
                    not case["unsupported"]
                    and case["topScore"] >= score_threshold
                    and case["semanticSimilarity"] >= semantic_threshold
                )
                expected_pass = case["expectedPass"]
                if expected_pass and predicted_pass:
                    tp += 1
                elif not expected_pass and not predicted_pass:
                    tn += 1
                elif not expected_pass and predicted_pass:
                    fp += 1
                else:
                    fn += 1
                per_case.append({**case, "predictedPass": predicted_pass})
            positive_total = tp + fn
            negative_total = tn + fp
            true_positive_rate = tp / positive_total if positive_total else 0.0
            true_negative_rate = tn / negative_total if negative_total else 0.0
            balanced_accuracy = (true_positive_rate + true_negative_rate) / 2
            candidate = {
                "recommendedRetrievalScoreThreshold": score_threshold,
                "recommendedSemanticSimilarityThreshold": semantic_threshold,
                "balancedAccuracy": balanced_accuracy,
                "truePositiveRate": true_positive_rate,
                "trueNegativeRate": true_negative_rate,
                "counts": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
                "evaluatedCases": len(cases),
                "perCase": per_case,
            }
            if best is None or (
                candidate["balancedAccuracy"],
                candidate["trueNegativeRate"],
                candidate["truePositiveRate"],
            ) > (
                best["balancedAccuracy"],
                best["trueNegativeRate"],
                best["truePositiveRate"],
            ):
                best = candidate

    return best or {
        "recommendedRetrievalScoreThreshold": default_score_threshold,
        "recommendedSemanticSimilarityThreshold": default_semantic_threshold,
        "balancedAccuracy": 0.0,
        "truePositiveRate": 0.0,
        "trueNegativeRate": 0.0,
        "counts": {"tp": 0, "tn": 0, "fp": 0, "fn": 0},
        "evaluatedCases": 0,
        "perCase": [],
    }


@dataclass
class BinaryCounts:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0
    true_negative: int = 0

    def precision(self) -> float:
        denominator = self.true_positive + self.false_positive
        return self.true_positive / denominator if denominator else 0.0

    def recall(self) -> float:
        denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else 0.0

    def f1(self) -> float:
        precision = self.precision()
        recall = self.recall()
        return (2 * precision * recall / (precision + recall)) if precision + recall else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tp": self.true_positive,
            "fp": self.false_positive,
            "fn": self.false_negative,
            "tn": self.true_negative,
            "precision": self.precision(),
            "recall": self.recall(),
            "f1": self.f1(),
        }


def targeted_f1(
    expected_by_id: dict[str, dict[str, bool]],
    predicted_by_id: dict[str, dict[str, bool]],
) -> dict[str, Any]:
    labels = sorted(
        {
            label
            for row in [*expected_by_id.values(), *predicted_by_id.values()]
            for label in row
        }
    )
    counts = {label: BinaryCounts() for label in labels}
    for row_id, expected_labels in expected_by_id.items():
        predicted_labels = predicted_by_id.get(row_id, {})
        for label in labels:
            expected = bool(expected_labels.get(label, False))
            predicted = bool(predicted_labels.get(label, False))
            if expected and predicted:
                counts[label].true_positive += 1
            elif not expected and predicted:
                counts[label].false_positive += 1
            elif expected and not predicted:
                counts[label].false_negative += 1
            else:
                counts[label].true_negative += 1
    per_label = {label: metric.to_dict() for label, metric in counts.items()}
    active_labels = [
        metric
        for metric in per_label.values()
        if metric["tp"] + metric["fp"] + metric["fn"] > 0
    ]
    macro_f1 = sum(metric["f1"] for metric in active_labels) / (len(active_labels) or 1)
    return {"macroF1": macro_f1, "perLabel": per_label}


def expected_target_labels(row: dict[str, Any]) -> dict[str, bool]:
    status = row.get("expectedStatus")
    return {
        "status_completed": status == "completed",
        "blocked_by_firewall": status == "blocked_by_firewall",
        "no_disallowed_patterns": True,
        "grounding_contract_passed": status == "completed",
        "judge_passed": status == "completed",
    }


def predicted_target_labels(row: dict[str, Any], result: dict[str, Any]) -> dict[str, bool]:
    text = " ".join(
        str(value or "")
        for value in [
            result.get("moralPathway"),
            result.get("userMessage"),
            result.get("failureReason"),
        ]
    ).lower()
    disallowed = [str(pattern).lower() for pattern in row.get("disallowedResponsePatterns") or []]
    audit = result.get("auditScores") or {}
    grounding = audit.get("groundingContract") or {}
    return {
        "status_completed": result.get("status") == "completed",
        "blocked_by_firewall": result.get("status") == "blocked_by_firewall" or bool(result.get("violations")),
        "no_disallowed_patterns": not any(pattern and pattern in text for pattern in disallowed),
        "grounding_contract_passed": bool(grounding.get("passed")),
        "judge_passed": bool(audit.get("passed")),
    }


def targeted_f1_from_results(
    rows: list[dict[str, Any]],
    results_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    expected = {str(row["id"]): expected_target_labels(row) for row in rows}
    predicted = {
        str(row["id"]): predicted_target_labels(row, results_by_id.get(str(row["id"]), {}))
        for row in rows
    }
    return targeted_f1(expected, predicted)
