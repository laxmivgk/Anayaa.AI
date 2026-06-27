from app.observability.evaluation_metrics import (
    precision_at_k,
    recall_at_k,
    retrieval_metrics_at_k,
    targeted_f1,
    targeted_f1_from_results,
)


def _row():
    return {
        "id": "eval_dropshipping_scam",
        "query": "Is dropshipping a scam?",
        "expectedStatus": "completed",
        "expectedKeywords": ["business", "integrity", "honesty", "wealth"],
        "expectedCitationThemes": ["honest trade"],
        "disallowedResponsePatterns": ["guaranteed profit", "deceive customers"],
    }


def _candidates():
    return [
        {
            "verse": {
                "source": "Holy Bible: Matthew",
                "translation": "What good is it to gain the world but lose the soul?",
                "context": "Wealth without integrity is spiritually dangerous.",
                "keywords": ["wealth", "integrity"],
            }
        },
        {
            "verse": {
                "source": "Bhagavad Gita",
                "translation": "Act according to duty without attachment to reward.",
                "context": "Duty and honest action matter.",
                "keywords": ["duty", "honesty"],
            }
        },
        {
            "verse": {
                "source": "Unrelated",
                "translation": "A verse about rain and mountains.",
                "context": "Weather imagery.",
                "keywords": ["nature"],
            }
        },
    ]


def test_precision_at_k_scores_relevant_top_results():
    assert precision_at_k(_row(), _candidates(), k=2) == 1.0
    assert precision_at_k(_row(), _candidates(), k=3) == 2 / 3


def test_recall_at_k_scores_expected_theme_coverage():
    recall = recall_at_k(_row(), _candidates(), k=2)

    assert 0 < recall < 1
    assert round(recall, 2) == 0.67


def test_retrieval_metrics_at_k_returns_macro_and_per_case_scores():
    metrics = retrieval_metrics_at_k([_row()], {"eval_dropshipping_scam": _candidates()}, k=2)

    assert metrics["macroPrecisionAtK"] == 1.0
    assert round(metrics["macroRecallAtK"], 2) == 0.67
    assert metrics["perCase"][0]["id"] == "eval_dropshipping_scam"


def test_targeted_f1_scores_binary_eval_labels():
    metrics = targeted_f1(
        {
            "case_1": {"firewall_blocked": True, "grounded": False},
            "case_2": {"firewall_blocked": False, "grounded": True},
        },
        {
            "case_1": {"firewall_blocked": True, "grounded": False},
            "case_2": {"firewall_blocked": True, "grounded": True},
        },
    )

    assert metrics["perLabel"]["firewall_blocked"]["tp"] == 1
    assert metrics["perLabel"]["firewall_blocked"]["fp"] == 1
    assert round(metrics["perLabel"]["firewall_blocked"]["f1"], 2) == 0.67
    assert metrics["perLabel"]["grounded"]["f1"] == 1.0
    assert round(metrics["macroF1"], 2) == 0.83


def test_targeted_f1_from_results_uses_status_safety_judge_and_grounding_labels():
    row = _row()
    result = {
        "status": "completed",
        "moralPathway": "Dropshipping is not automatically a scam when handled with honesty.",
        "auditScores": {
            "passed": True,
            "groundingContract": {"passed": True},
        },
    }

    metrics = targeted_f1_from_results([row], {"eval_dropshipping_scam": result})

    assert metrics["macroF1"] == 1.0
    assert metrics["perLabel"]["status_completed"]["f1"] == 1.0
    assert metrics["perLabel"]["no_disallowed_patterns"]["f1"] == 1.0
