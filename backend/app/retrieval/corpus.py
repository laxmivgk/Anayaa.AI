import json
from pathlib import Path

from app.config import get_settings
<<<<<<< HEAD
from app.retrieval.hybrid_search import CONCEPT_CLOUDS, ScriptureVerse
=======
from app.retrieval.hybrid_search import ScriptureVerse
>>>>>>> origin/main

_corpus_cache: list[ScriptureVerse] | None = None


def load_scriptures_json(path: Path | None = None) -> list[ScriptureVerse]:
    global _corpus_cache
    if _corpus_cache is not None:
        return _corpus_cache

    settings = get_settings()
    base = Path(__file__).resolve().parents[2]
    json_path = path or (base / settings.scriptures_json_path)
    if not json_path.exists():
        raise FileNotFoundError(
            f"Scripture corpus not found at {json_path}. Run: node export or python scripts/seed_milvus.py"
        )

    data = json.loads(json_path.read_text(encoding="utf-8"))
    _corpus_cache = [ScriptureVerse.from_dict(v) for v in data]
    return _corpus_cache


def get_corpus() -> list[ScriptureVerse]:
    return load_scriptures_json()


def expand_graph(corpus: list[ScriptureVerse], keywords: list[str], limit: int = 10) -> list[dict]:
    keyword_set = {k.lower() for k in keywords}
<<<<<<< HEAD
    expanded_keyword_set = set(keyword_set)
    for keyword in keyword_set:
        for concept, related_terms in CONCEPT_CLOUDS.items():
            if keyword == concept or keyword in related_terms:
                expanded_keyword_set.add(concept)
                expanded_keyword_set.update(related_terms)

    boosted = []
    for verse in corpus:
        verse_keywords = {k.lower() for k in verse.keywords}
        overlap = expanded_keyword_set.intersection(verse_keywords)
        if overlap:
            direct_overlap = keyword_set.intersection(verse_keywords)
            related_overlap = overlap - direct_overlap
            score = min(95, 72 + len(direct_overlap) * 12 + len(related_overlap) * 8)
            boosted.append(
                {
                    "verse": verse.to_dict(),
                    "score": score,
                    "method": "KnowledgeGraph",
                    "graphMatchTerms": sorted(overlap),
=======
    boosted = []
    for verse in corpus:
        overlap = keyword_set.intersection({k.lower() for k in verse.keywords})
        if overlap:
            boosted.append(
                {
                    "verse": verse.to_dict(),
                    "score": 55 + len(overlap) * 5,
                    "method": "KnowledgeGraph",
>>>>>>> origin/main
                }
            )
    boosted.sort(key=lambda x: x["score"], reverse=True)
    return boosted[:limit]
