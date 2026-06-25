from app.agents.adk_workflow import _retrieval_matches_query
from app.agents.workflow import _extract_planner_keywords
from app.mcp.client import _merge_candidates
from app.retrieval.corpus import expand_graph, get_corpus
from app.retrieval.hybrid_search import execute_hybrid_search, rerank_candidates


ENVIRONMENT_BUSY_LIFE_QUERY = "how can I save the environment with a busy life?"


def test_environment_busy_life_query_reaches_relevant_retrieval():
    keywords = _extract_planner_keywords(ENVIRONMENT_BUSY_LIFE_QUERY)
    corpus = get_corpus()
    candidates = execute_hybrid_search(corpus, keywords, query=ENVIRONMENT_BUSY_LIFE_QUERY)
    reranked = rerank_candidates(candidates, ENVIRONMENT_BUSY_LIFE_QUERY, top_k=5)

    assert "environment" in keywords
    assert candidates
    assert reranked[0]["score"] >= 40
    assert _retrieval_matches_query(ENVIRONMENT_BUSY_LIFE_QUERY, reranked)


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
