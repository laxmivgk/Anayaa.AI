import pytest

from app.agents.adk_workflow import _attach_cache_policy, _is_safe_to_cache
from app.agents.cache_policy import build_semantic_cache_key, cache_policy_metadata, cache_versions
from app.agents.workflow import evaluate_semantic_cache


def _successful_result():
    return {
        "status": "completed",
        "moralPathway": "One-line summary: Be honest.\nScripture grounding: Gita duty and Matthew soul.",
        "citations": [{"id": "gita-2-47"}, {"id": "matthew-16-26"}],
        "auditScores": {
            "passed": True,
            "auditStatus": "ok",
            "judgeFallback": False,
            "groundingContract": {"passed": True},
        },
    }


def test_semantic_cache_key_includes_explicit_versions_and_model_versions():
    key, versions = build_semantic_cache_key("Should I be honest?", ["truth"])

    assert len(key) == 20
    assert versions["cacheSchemaVersion"]
    assert versions["promptVersion"]
    assert versions["plannerVersion"]
    assert versions["retrievalVersion"]
    assert versions["modelVersion"]["planner"]
    assert versions["modelVersion"]["synthesizer"]
    assert versions["modelVersion"]["judge"]


def test_cache_policy_allows_only_grounded_judge_passed_success():
    result = _successful_result()

    _attach_cache_policy(result, "abc123")

    assert _is_safe_to_cache(result) is True
    assert result["cachePolicy"]["cacheable"] is True
    assert result["cachePolicy"]["reason"] == "cacheable"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda result: result.update({"status": "quality_threshold_not_met"}), "status_quality_threshold_not_met"),
        (lambda result: result.update({"citations": [{"id": "gita-2-47"}]}), "fewer_than_two_citations"),
        (lambda result: result["auditScores"].update({"passed": False}), "judge_not_passed"),
        (lambda result: result["auditScores"].update({"judgeFallback": True}), "judge_fallback_used"),
        (lambda result: result["auditScores"].update({"auditStatus": "fallback_ok"}), "audit_status_not_ok"),
        (lambda result: result["auditScores"].update({"groundingContract": {"passed": False}}), "grounding_contract_not_passed"),
    ],
)
def test_cache_policy_rejects_unsafe_results(mutation, reason):
    result = _successful_result()
    mutation(result)

    _attach_cache_policy(result, "abc123")

    assert _is_safe_to_cache(result) is False
    assert result["cachePolicy"]["cacheable"] is False
    assert result["cachePolicy"]["reason"] == reason


@pytest.mark.anyio
async def test_evaluate_semantic_cache_rejects_stale_version_metadata():
    class FakeRedis:
        async def get_json(self, key):
            result = _successful_result()
            result["cachePolicy"] = cache_policy_metadata(cache_key="abc123", cacheable=True, reason="cacheable")
            result["cachePolicy"]["promptVersion"] = "old_prompt"
            return result

    assert await evaluate_semantic_cache(FakeRedis(), "abc123") is None


@pytest.mark.anyio
async def test_evaluate_semantic_cache_accepts_matching_version_metadata():
    class FakeRedis:
        async def get_json(self, key):
            result = _successful_result()
            result["cachePolicy"] = {
                **cache_policy_metadata(cache_key="abc123", cacheable=True, reason="cacheable"),
                **cache_versions(),
            }
            return result

    cached = await evaluate_semantic_cache(FakeRedis(), "abc123")

    assert cached is not None
    assert cached["cachePolicy"]["promptVersion"] == cache_versions()["promptVersion"]
