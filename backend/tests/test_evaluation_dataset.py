from app.observability.evaluation_dataset import load_evaluation_dataset
from app.observability.g_eval_judge import SCORE_DIMENSIONS


def test_evaluation_dataset_rows_are_valid_and_cover_release_risks():
    rows = load_evaluation_dataset()

    ids = {row["id"] for row in rows}
    categories = {row["category"] for row in rows}

    assert len(rows) >= 18
    assert len(ids) == len(rows)
    assert "business_integrity" in categories
    assert "conflict_non_retaliation" in categories
    assert "security_firewall" in categories
    assert "follow_up_relationship" in categories
    assert "confidentiality_safety" in categories
    assert "pii_privacy" in categories
    assert "retrieval_weak_current_fact" in categories
    assert "retrieval_weak_product" in categories
    assert "retrieval_weak_science" in categories
    assert "moral_current_fact_context" in categories
    assert "moral_product_context" in categories

    for row in rows:
        assert row["query"].strip()
        assert row["expectedStatus"] in {"completed", "blocked_by_firewall", "insufficient_context"}
        assert all(isinstance(keyword, str) and keyword for keyword in row["expectedKeywords"])
        assert all(isinstance(theme, str) and theme for theme in row["expectedCitationThemes"])
        assert all(isinstance(pattern, str) and pattern for pattern in row["disallowedResponsePatterns"])
        assert set(row["minimumScores"]) == set(SCORE_DIMENSIONS)
        assert all(0 <= int(score) <= 5 for score in row["minimumScores"].values())
