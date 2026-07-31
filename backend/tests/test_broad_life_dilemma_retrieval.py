import asyncio
from types import SimpleNamespace

from app.agents import adk_workflow
from app.agents.adk_workflow import _retrieval_gate_reason, _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords
from app.mcp.client import _merge_candidates
from app.retrieval.corpus import expand_graph, get_corpus
from app.retrieval.hybrid_search import CONCEPT_CLOUDS, execute_hybrid_search, rerank_candidates


ENVIRONMENT_BUSY_LIFE_QUERY = "how can I save the environment with a busy life?"


def test_grudge_concept_cloud_expands_to_forgiveness_and_resentment():
    cloud = CONCEPT_CLOUDS["grudge"]

    assert "resentment" in cloud
    assert "forgiveness" in cloud
    assert "hatred" in cloud
    assert "attachment" in cloud


def test_retriever_node_reaches_mcp_for_discipline_question(monkeypatch):
    calls = []

    async def fake_retrieve_via_mcp(query, keywords, *, limit, top_k):
        calls.append({"query": query, "keywords": keywords, "limit": limit, "top_k": top_k})
        verse = {
            "id": "test-discipline",
            "source": "Bhagavad Gita",
            "reference": "6.26",
            "translation": "A disciplined mind returns to steady practice.",
            "context": "discipline, practice, and self-control",
            "keywords": ["discipline", "practice", "self-control"],
        }
        row = {"verse": verse, "score": 92, "method": "test"}
        return {"candidates": [row], "reranked": [row], "hybridSource": "test", "mcp": True}

    monkeypatch.setattr(adk_workflow, "retrieve_via_mcp", fake_retrieve_via_mcp)
    ctx = SimpleNamespace(state={"request_id": "test-retriever-discipline", "hitl_enabled": False})

    result = asyncio.run(
        adk_workflow.retriever_node._func(
            ctx,
            {"dilemma": "How to be disciplined?", "keywords": ["discipline"], "reactTurn": 1},
        )
    )

    assert calls == [
        {"query": "How to be disciplined?", "keywords": ["discipline"], "limit": 10, "top_k": 3}
    ]
    assert result["retrievalViaMcp"] is True
    assert result["contextSufficient"] is True
    assert result["retrievalBlocked"] is None
    assert result["retrievalRelevance"]["supportMatches"]
    assert result["citations"][0]["id"] == "test-discipline"


def test_retriever_blocks_weak_factual_citations_before_synthesis(monkeypatch):
    calls = []

    async def fake_retrieve_via_mcp(query, keywords, *, limit, top_k):
        calls.append(query)
        verse = {
            "id": "test-weather",
            "source": "Test Corpus",
            "reference": "1.1",
            "translation": "The seasons and weather change over time.",
            "context": "A general note about weather patterns.",
            "keywords": ["weather"],
        }
        row = {"verse": verse, "score": 95, "method": "test"}
        return {"candidates": [row], "reranked": [row], "hybridSource": "test", "mcp": True}

    monkeypatch.setattr(adk_workflow, "retrieve_via_mcp", fake_retrieve_via_mcp)
    ctx = SimpleNamespace(state={"request_id": "test-retriever-weather", "hitl_enabled": False})

    result = asyncio.run(
        adk_workflow.retriever_node._func(
            ctx,
            {"dilemma": "What is the weather today?", "keywords": ["weather"], "reactTurn": 1},
        )
    )

    assert calls == []
    assert result["contextSufficient"] is False
    assert result["retrievalBlocked"] == "unsupported_current_fact_query"
    assert result["citations"] == []
    assert result["retrievalViaMcp"] is False
    assert result["preRetrievalBlocked"] is True
    assert result["retrievalRelevance"]["unsupportedQueryReason"] == "unsupported_current_fact_query"


def test_current_rainfall_question_is_blocked_even_with_previous_context(monkeypatch):
    calls = []

    async def fake_retrieve_via_mcp(query, keywords, *, limit, top_k):
        calls.append(query)
        verse = {
            "id": "test-rainfall",
            "source": "Test Corpus",
            "reference": "1.2",
            "translation": "Rain falls in different seasons.",
            "context": "A general note about rainfall.",
            "keywords": ["rainfall", "weather"],
        }
        row = {"verse": verse, "score": 95, "method": "test"}
        return {"candidates": [row], "reranked": [row], "hybridSource": "test", "mcp": True}

    monkeypatch.setattr(adk_workflow, "retrieve_via_mcp", fake_retrieve_via_mcp)
    previous = "I lied to my close friend and feel guilty. What should I do?"
    current = "Explain why it's raining more this year than usual."
    ctx = SimpleNamespace(
        state={
            "request_id": "test-retriever-rainfall-current-fact",
            "hitl_enabled": False,
            "original_dilemma": current,
            "previous_context_question": previous,
        }
    )

    result = asyncio.run(
        adk_workflow.retriever_node._func(
            ctx,
            {
                "dilemma": f"Previous dilemma: {previous}. Follow-up question: {current}",
                "originalQuery": current,
                "previousContextUsed": True,
                "previousContextQuestion": previous,
                "keywords": ["friend", "truth", "rainfall"],
                "reactTurn": 1,
            },
        )
    )

    assert calls == []
    assert result["contextSufficient"] is False
    assert result["retrievalBlocked"] == "unsupported_current_fact_query"
    assert result["citations"] == []
    assert result["retrievalViaMcp"] is False
    assert result["preRetrievalBlocked"] is True
    assert result["retrievalGateQuery"] == current
    assert result["retrievalRelevance"]["unsupportedQueryReason"] == "unsupported_current_fact_query"


def test_follow_up_retrieval_gate_uses_previous_context(monkeypatch):
    async def fake_retrieve_via_mcp(query, keywords, *, limit, top_k):
        verse = {
            "id": "test-caregiver-duty",
            "source": "Bhagavad Gita",
            "reference": "2.47",
            "translation": "You have a right to perform your duty with steadiness.",
            "context": "On duty, responsibility, care, and burden during hardship.",
            "keywords": ["duty", "responsibility", "care", "hardship"],
        }
        row = {"verse": verse, "score": 91, "method": "test"}
        return {"candidates": [row], "reranked": [row], "hybridSource": "test", "mcp": True}

    previous = (
        "I have taken on the care of my sick parent while trying to manage a failing business. "
        "I feel entirely burned out, hopeless, and physically exhausted. I feel like giving up on everything."
    )
    follow_up = "I don't have anyone to share my duties. What should I do?"

    monkeypatch.setattr(adk_workflow, "retrieve_via_mcp", fake_retrieve_via_mcp)
    ctx = SimpleNamespace(
        state={
            "request_id": "test-retriever-caregiver-follow-up",
            "hitl_enabled": False,
            "original_dilemma": follow_up,
            "previous_context_question": previous,
        }
    )

    result = asyncio.run(
        adk_workflow.retriever_node._func(
            ctx,
            {
                "dilemma": f"Previous dilemma: {previous}. Follow-up question: {follow_up}",
                "originalQuery": follow_up,
                "previousContextUsed": True,
                "previousContextQuestion": previous,
                "keywords": ["duty", "care", "responsibility"],
                "reactTurn": 1,
            },
        )
    )

    assert result["contextSufficient"] is True
    assert result["retrievalBlocked"] is None
    assert result["citations"][0]["id"] == "test-caregiver-duty"
    assert previous in result["retrievalGateQuery"]
    assert follow_up in result["retrievalGateQuery"]
    assert result["retrievalRelevance"]["passesSemanticSimilarity"] is True


def test_quantum_explanation_does_not_pass_semantic_retrieval_gate():
    reranked = [
        {
            "score": 95,
            "verse": {
                "translation": "A person should act with duty and self-control.",
                "context": "On duty, discipline, and steady practice.",
                "source": "Test Corpus",
                "keywords": ["duty", "discipline"],
            },
        }
    ]

    assert not _retrieval_matches_query("Explain quantum entanglement in simple words.", reranked)


def test_crypto_investment_can_match_future_anxiety_semantically():
    reranked = [
        {
            "score": 100,
            "verse": {
                "translation": "Therefore do not worry about tomorrow, for tomorrow will worry about itself.",
                "context": "On relieving chronic anxiety, future insecurity, and immediate moral actions.",
                "source": "Test Corpus",
                "keywords": ["anxiety", "future", "trust", "worry"],
            },
        },
        {
            "score": 97,
            "verse": {
                "translation": "You have a right to perform your duties, but not to the fruits of action.",
                "context": "On decision paralysis, anxiety about outcomes, and dedicated work.",
                "source": "Test Corpus",
                "keywords": ["duty", "results", "career", "anxiety", "choice"],
            },
        },
    ]

    reason, report = _retrieval_gate_reason(
        "Should I invest in crypto tomorrow?",
        reranked,
        top_score=100,
        threshold=40,
        focus_terms=["future", "anxiety", "choice", "duty"],
        semantic_threshold=0.30,
    )

    assert reason is None
    assert report["passesSemanticSimilarity"] is True
    assert report["maxSemanticSimilarity"] >= 0.30


def test_laptop_product_advice_still_blocks_unrelated_scripture():
    reranked = [
        {
            "score": 98,
            "verse": {
                "translation": "Repel evil by that which is better.",
                "context": "On conflict de-escalation and professional diplomacy under pressure.",
                "source": "Test Corpus",
                "keywords": ["reconciliation", "kindness", "relationship", "conflict"],
            },
        },
        {
            "score": 91,
            "verse": {
                "translation": "For indeed, with hardship comes ease.",
                "context": "On business failures, sorrow, or difficult transitions.",
                "source": "Test Corpus",
                "keywords": ["hardship", "hope", "failure", "patience"],
            },
        },
    ]

    reason, report = _retrieval_gate_reason(
        "Which laptop should I buy for video editing?",
        reranked,
        top_score=98,
        threshold=40,
    )

    assert reason == "unsupported_product_recommendation"
    assert report["unsupportedQueryReason"] == "unsupported_product_recommendation"


def test_weather_risk_moral_dilemma_is_not_blocked_as_current_fact_query():
    reranked = [
        {
            "score": 96,
            "verse": {
                "translation": "Speak truthfully and act with care for others.",
                "context": "On honesty, responsibility, care, and protecting people from harm.",
                "source": "Test Corpus",
                "keywords": ["honesty", "responsibility", "care", "harm"],
            },
        }
    ]

    reason, report = _retrieval_gate_reason(
        "Should I be honest about weather risk for an event tomorrow?",
        reranked,
        top_score=96,
        threshold=40,
        focus_terms=["honesty", "responsibility", "care"],
    )

    assert reason is None
    assert report["unsupportedQueryReason"] is None
    assert report["passesCitationRelevance"] is True


def test_product_buy_moral_dilemma_is_not_blocked_as_product_recommendation():
    reranked = [
        {
            "score": 94,
            "verse": {
                "translation": "Let justice and fairness guide your dealings.",
                "context": "On fair buying, responsibility, exploitation, and avoiding harm.",
                "source": "Test Corpus",
                "keywords": ["fair", "responsibility", "harm", "justice"],
            },
        }
    ]

    reason, report = _retrieval_gate_reason(
        "Which laptop should I buy if the seller may be exploited?",
        reranked,
        top_score=94,
        threshold=40,
        focus_terms=["fair", "responsibility", "harm"],
    )

    assert reason is None
    assert report["unsupportedQueryReason"] is None
    assert report["passesCitationRelevance"] is True


def test_environment_busy_life_query_reaches_relevant_retrieval():
    keywords = _extract_planner_keywords(ENVIRONMENT_BUSY_LIFE_QUERY)
    corpus = get_corpus()
    candidates = execute_hybrid_search(corpus, keywords, query=ENVIRONMENT_BUSY_LIFE_QUERY)
    reranked = rerank_candidates(candidates, ENVIRONMENT_BUSY_LIFE_QUERY, top_k=5)

    assert "environment" in keywords
    assert candidates
    assert reranked[0]["score"] >= 40
    assert _retrieval_matches_query(ENVIRONMENT_BUSY_LIFE_QUERY, reranked, focus_terms=keywords)


def test_environment_busy_life_retrieval_includes_sustainable_or_care_context():
    keywords = _extract_planner_keywords(ENVIRONMENT_BUSY_LIFE_QUERY)
    reranked = rerank_candidates(
        execute_hybrid_search(get_corpus(), keywords, query=ENVIRONMENT_BUSY_LIFE_QUERY),
        ENVIRONMENT_BUSY_LIFE_QUERY,
        top_k=5,
    )
    joined_context = " ".join(
        f"{item['verse'].get('context', '')} {' '.join(item['verse'].get('keywords', []))}"
        for item in reranked
    ).lower()

    assert any(term in joined_context for term in ["sustainable", "living", "goodwill", "responsibility", "stress"])


def test_environment_keyword_graph_expansion_promotes_isha_upanishad():
    results = expand_graph(get_corpus(), ["environment"], limit=5)

    assert any(item["verse"]["id"] == "h4" for item in results)
    isha = next(item for item in results if item["verse"]["id"] == "h4")
    assert isha["score"] >= 80


def test_environment_final_rerank_surfaces_isha_upanishad_from_graph_candidates():
    keywords = _extract_planner_keywords(ENVIRONMENT_BUSY_LIFE_QUERY)
    corpus = get_corpus()
    graph_data = {"results": expand_graph(corpus, keywords, limit=10)}
    hybrid_rows = [
        {
            "verse": verse.to_dict(),
            "score": max(55, 95 - idx * 4),
            "method": "Hybrid HNSW+BM25",
        }
        for idx, verse in enumerate(verse for verse in corpus if verse.id != "h4")
    ][:10]

    merged = _merge_candidates({"results": hybrid_rows}, graph_data, limit=10)
    reranked = rerank_candidates(merged, ENVIRONMENT_BUSY_LIFE_QUERY, top_k=3)

    assert any(item["verse"]["id"] == "h4" for item in merged)
    assert any(item["verse"]["id"] == "h4" for item in reranked)
