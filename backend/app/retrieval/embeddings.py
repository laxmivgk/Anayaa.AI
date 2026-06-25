from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


def verse_doc_text(verse) -> str:
    keywords = " ".join(verse.keywords) if verse.keywords else ""
    original = verse.original_text or ""
    return (
        f"{verse.faith} {verse.source} {verse.chapter} {verse.verse}. "
        f"{verse.translation} {verse.context} {keywords} {original}"
    ).strip()


@lru_cache
def get_embedder() -> "ScriptureEmbedder":
    settings = get_settings()
    return ScriptureEmbedder(settings.embedding_model)


class ScriptureEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        self.model: SentenceTransformer = SentenceTransformer(model_name)
        if hasattr(self.model, "get_embedding_dimension"):
            self.dimension = int(self.model.get_embedding_dimension())
        else:
            self.dimension = int(self.model.get_sentence_embedding_dimension())

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode([text], normalize_embeddings=True, show_progress_bar=False)[0]
        return vector.tolist()
