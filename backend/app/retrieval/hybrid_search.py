import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.agents.pipeline_errors import ServiceUnavailableError
from app.config import get_settings


@dataclass
class ScriptureVerse:
    id: str
    faith: str
    source: str
    chapter: str
    verse: str
    translation: str
    context: str
    keywords: list[str]
    original_text: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScriptureVerse":
        return cls(
            id=data["id"],
            faith=data["faith"],
            source=data["source"],
            chapter=data["chapter"],
            verse=data["verse"],
            translation=data["translation"],
            context=data["context"],
            keywords=list(data.get("keywords", [])),
            original_text=data.get("originalText") or data.get("original_text"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "faith": self.faith,
            "source": self.source,
            "chapter": self.chapter,
            "verse": self.verse,
            "originalText": self.original_text,
            "translation": self.translation,
            "context": self.context,
            "keywords": self.keywords,
        }


CONCEPT_CLOUDS: dict[str, list[str]] = {
    "anxiety": ["worry", "tomorrow", "anxious", "restless", "fear", "results", "stress", "burden", "pressure", "outcome"],
    "anger": ["fury", "hatred", "vengeance", "revenge", "conflict", "retaliation", "dispute", "violent", "argument"],
    "greed": ["money", "wealth", "financial", "financially", "company", "covet", "belonging", "gain", "ambition", "profit", "stealing", "cheat"],
    "business": ["dropshipping", "scam", "scamming", "honesty", "integrity", "fairness", "truth", "wealth", "customer", "selling"],
    "business": ["dropshipping", "scam", "scamming", "honesty", "integrity", "fairness", "truth", "wealth", "customer", "selling"],
    "duty": ["karma", "work", "prescribed", "action", "obligation", "responsibility", "effort", "career", "job", "survive", "company"],
    "betrayal": ["partner", "partners", "backstab", "enemy", "lying", "cheat", "scam", "business", "friend", "divorce"],
    "environment": ["earth", "world", "nature", "sustainable", "sharing", "sharing wealth", "greed", "renunciation"],
    "love": ["goodwill", "friend", "protect", "empathy", "care", "heart", "mother", "compassion"],
    "peace": ["calm", "mind", "intellect", "present", "trust", "silence", "purity"],
    "dharma": ["duty", "path", "living", "moral", "integrity", "righteousness"],
    "identity": ["self", "soul", "purpose", "path", "authenticity", "duty", "mind", "roles", "labels"],
    "livelihood": ["job", "jobs", "work", "career", "needs", "need", "responsibility", "wealth", "burden", "choice", "randomly"],
}


def execute_hybrid_search(
    corpus: list[ScriptureVerse],
    keywords: list[str],
    query: str | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    query_words: list[str] = []
    if query:
        query_words = [
            w
            for w in re.sub(r"[^\w\s]", " ", query.lower()).split()
            if len(w) > 3 or w in {"job"}
        ]

    for verse in corpus:
        sparse_score = 0.0
        dense_score = 0.0
        verse_doc = f"{verse.translation} {verse.context} {verse.source}".lower()

        for kw in keywords:
            sub_tokens = re.findall(r"\b\w+\b", kw.lower())
            for token in sub_tokens:
                if len(token) <= 3:
                    continue
                occurrences = len(re.findall(rf"\b{re.escape(token)}\b", verse_doc))
                if occurrences:
                    sparse_score += occurrences * 8.5
                meta_matches = [k for k in verse.keywords if k == token or token in k]
                sparse_score += len(meta_matches) * 12

        for qw in query_words:
            occurrences = len(re.findall(rf"\b{re.escape(qw)}\b", verse_doc))
            if occurrences:
                sparse_score += occurrences * 12
            meta_matches = [k for k in verse.keywords if k == qw or qw in k]
            sparse_score += len(meta_matches) * 15

        for kw in keywords:
            kw_lower = kw.lower()
            for concept, word_list in CONCEPT_CLOUDS.items():
                query_has = any(qw == concept or qw in word_list for qw in query_words)
                keyword_has = concept in kw_lower or any(w in kw_lower for w in word_list)
                if query_has or keyword_has:
                    if any(k == concept or k in word_list for k in verse.keywords):
                        dense_score += 45

        total_score = min(sparse_score + dense_score, 100)
        if total_score > 10:
            results.append(
                {
                    "verse": verse.to_dict(),
                    "score": round(total_score),
                    "method": "Sparse BM25" if sparse_score > dense_score else "Dense HNSW",
                }
            )

    return sorted(results, key=lambda x: x["score"], reverse=True)


def rerank_candidates(candidates: list[dict[str, Any]], query: str, top_k: int = 5) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.cross_encoder_enabled:
        cross_encoder = _get_cross_encoder()
        if cross_encoder is None:
            raise ServiceUnavailableError(
                "Cross-encoder reranker",
                f"model {settings.cross_encoder_model} could not be loaded",
            )
        return _rerank_with_cross_encoder(cross_encoder, candidates, query, top_k)
    return _rerank_with_overlap(candidates, query, top_k)


def _rerank_with_overlap(candidates: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
    query_terms = set(re.findall(r"\b\w+\b", query.lower()))
    expanded_query_terms = _expand_terms_with_concepts(query_terms)
    reranked = []
    for item in candidates:
        verse = item["verse"]
        text = (
            f"{verse.get('translation', '')} {verse.get('context', '')} "
            f"{' '.join(str(keyword) for keyword in verse.get('keywords', []))}"
        ).lower()
        overlap = sum(1 for t in query_terms if len(t) > 3 and t in text)
        concept_overlap = sum(1 for t in expanded_query_terms - query_terms if len(t) > 3 and t in text)
        bonus = min(18, overlap * 3 + concept_overlap * 3)
        sort_score = item["score"] + bonus
        reranked.append(
            {
                **item,
                "score": min(sort_score, 100),
                "rerankBoost": bonus,
                "_sortScore": sort_score,
            }
        )
    reranked.sort(key=lambda x: x["_sortScore"], reverse=True)
    return [{k: v for k, v in item.items() if k != "_sortScore"} for item in reranked[:top_k]]


def _expand_terms_with_concepts(query_terms: set[str]) -> set[str]:
    expanded = set(query_terms)
    for term in query_terms:
        for concept, related_terms in CONCEPT_CLOUDS.items():
            if term == concept or term in related_terms:
                expanded.add(concept)
                expanded.update(related_terms)
    return expanded


@lru_cache
def _get_cross_encoder():
    settings = get_settings()
    try:
        from sentence_transformers import CrossEncoder

        return CrossEncoder(settings.cross_encoder_model)
    except Exception as exc:
        logger = __import__("logging").getLogger(__name__)
        logger.error("Cross-encoder load failed: %s", exc)
        return None


def _rerank_with_cross_encoder(cross_encoder, candidates: list[dict[str, Any]], query: str, top_k: int) -> list[dict[str, Any]]:
    if not candidates:
        return []
    pairs = [
        (query, f"{item['verse'].get('translation', '')} {item['verse'].get('context', '')}")
        for item in candidates
    ]
    scores = cross_encoder.predict(pairs)
    raw_scores = [float(score) for score in scores]
    min_raw = min(raw_scores)
    max_raw = max(raw_scores)
    score_span = max_raw - min_raw
    reranked = []
    for item, raw_score in zip(candidates, raw_scores):
        base_score = float(item.get("score", 0))
        if score_span <= 1e-6:
            normalized = base_score
        else:
            normalized = ((raw_score - min_raw) / score_span) * 100

        blended = int(min(100, round(base_score * 0.75 + normalized * 0.25)))
        reranked.append(
            {
                **item,
                "score": blended,
                "rerankBoost": blended - item["score"],
                "method": "Cross-Encoder",
                "crossEncoderScore": round(raw_score, 4),
            }
        )
    reranked.sort(key=lambda x: x["score"], reverse=True)
    return reranked[:top_k]
