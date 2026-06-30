from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.retrieval.embeddings import get_embedder, verse_doc_text
from app.retrieval.hybrid_search import ScriptureVerse

logger = logging.getLogger(__name__)


class MilvusStore:
    def __init__(self, uri: str | None = None) -> None:
        settings = get_settings()
        self.uri = uri or settings.milvus_uri
        self.collection_name = settings.milvus_collection
        self.available = False
        self.hybrid_enabled = False
        self._client: Any | None = None
        self._corpus_by_id: dict[str, ScriptureVerse] = {}

    def _resolve_uri(self) -> str:
        if not self.uri.endswith(".db"):
            return self.uri

        path = Path(self.uri)
        if not path.is_absolute():
            backend_root = Path(__file__).resolve().parents[2]
            path = backend_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    def connect(self) -> bool:
        from pymilvus import MilvusClient

        uri = self._resolve_uri()
        is_lite = self.uri.endswith(".db")
        attempts = 3 if is_lite else 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._client = MilvusClient(uri=uri)
                self.available = True
                if self._client.has_collection(self.collection_name):
                    self.hybrid_enabled = self._detect_hybrid_support()
                return True
            except Exception as exc:
                self._client = None
                self.available = False
                last_error = exc
                if is_lite:
                    self._release_lite_server(uri)
                if attempt < attempts:
                    logger.warning(
                        "Milvus Lite connection failed on attempt %s/%s; retrying: %s",
                        attempt,
                        attempts,
                        exc,
                    )
                    time.sleep(1)

        if is_lite:
            self._release_lite_server(uri)
        raise RuntimeError(f"Milvus is required but unavailable at {self.uri}.") from last_error

    def close(self) -> None:
        resolved_uri = self._resolve_uri() if self.uri.endswith(".db") else None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        if resolved_uri:
            self._release_lite_server(resolved_uri)
        self._client = None
        self.available = False

    def _release_lite_server(self, resolved_uri: str) -> None:
        try:
            from milvus_lite.server_manager import server_manager_instance

            server_manager_instance.release_server(resolved_uri)
        except Exception:
            pass

    def ensure_collection(self, dim: int, recreate: bool = False) -> None:
        if not self._client:
            return

        if self._client.has_collection(self.collection_name):
            if recreate:
                self._client.drop_collection(self.collection_name)
            else:
                self.hybrid_enabled = self._detect_hybrid_support()
                self._client.load_collection(self.collection_name)
                return

        try:
            self._create_hybrid_collection(dim)
        except Exception as exc:
            logger.warning("Hybrid Milvus schema failed, using dense-only collection: %s", exc)
            self._create_dense_collection(dim)

    def _create_hybrid_collection(self, dim: int) -> None:
        from pymilvus import (
            CollectionSchema,
            DataType,
            FieldSchema,
            Function,
            FunctionType,
        )
        from pymilvus.milvus_client import IndexParams

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
            FieldSchema(name="faith", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="doc_text", dtype=DataType.VARCHAR, max_length=8192, enable_analyzer=True),
            FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="Anayaa scripture hybrid index")
        schema.add_function(
            Function(
                name="doc_bm25",
                input_field_names=["doc_text"],
                output_field_names=["sparse_vector"],
                function_type=FunctionType.BM25,
            )
        )

        index_params = IndexParams()
        index_params.add_index(
            "embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            nlist=128,
        )
        index_params.add_index(
            "sparse_vector",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
        )

        self._client.create_collection(
            self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self.hybrid_enabled = True

    def _create_dense_collection(self, dim: int) -> None:
        from pymilvus import CollectionSchema, DataType, FieldSchema
        from pymilvus.milvus_client import IndexParams

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=128, is_primary=True),
            FieldSchema(name="faith", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=128),
            FieldSchema(name="doc_text", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields, description="Anayaa scripture dense index")

        index_params = IndexParams()
        index_params.add_index(
            "embedding",
            index_type="IVF_FLAT",
            metric_type="COSINE",
            nlist=128,
        )

        self._client.create_collection(
            self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        self.hybrid_enabled = False

    def _detect_hybrid_support(self) -> bool:
        if not self._client:
            return False
        try:
            desc = self._client.describe_collection(self.collection_name)
            field_names = {field["name"] for field in desc.get("fields", [])}
            return "sparse_vector" in field_names and "embedding" in field_names
        except Exception:
            return False

    def seed_verses(self, corpus: list[ScriptureVerse], recreate: bool = False) -> int:
        if not self.available:
            self.connect()
        if not self.available or not self._client:
            raise RuntimeError("Milvus client is not connected.")

        if not recreate and self.entity_count() >= len(corpus):
            self._corpus_by_id = {verse.id: verse for verse in corpus}
            return len(corpus)

        embedder = get_embedder()
        self._corpus_by_id = {verse.id: verse for verse in corpus}
        self.ensure_collection(embedder.dimension, recreate=recreate)

        rows = []
        doc_texts = [verse_doc_text(verse) for verse in corpus]
        embeddings = embedder.embed_documents(doc_texts)
        for verse, doc_text, embedding in zip(corpus, doc_texts, embeddings):
            rows.append(
                {
                    "id": verse.id,
                    "faith": verse.faith,
                    "source": verse.source,
                    "doc_text": doc_text,
                    "embedding": embedding,
                }
            )

        self._client.insert(self.collection_name, rows)
        logger.info("Seeded %s verses into Milvus collection %s", len(corpus), self.collection_name)
        return len(corpus)

    def entity_count(self) -> int:
        if not self._client or not self._client.has_collection(self.collection_name):
            return 0
        try:
            stats = self._client.get_collection_stats(self.collection_name)
            return int(stats.get("row_count", 0))
        except Exception:
            return 0

    def hybrid_search(
        self,
        query: str,
        keywords: list[str] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not self.available or not self._client:
            raise RuntimeError("Milvus client is not connected.")
        if not self._client.has_collection(self.collection_name):
            raise RuntimeError(f"Milvus collection '{self.collection_name}' does not exist.")

        embedder = get_embedder()
        query_text = query
        if keywords:
            query_text = f"{query} {' '.join(keywords)}"

        dense_vector = embedder.embed_query(query_text)
        output_fields = ["id", "faith", "source"]

        if self.hybrid_enabled:
            try:
                from pymilvus import AnnSearchRequest, RRFRanker

                sparse_req = AnnSearchRequest(
                    data=[query_text],
                    anns_field="sparse_vector",
                    param={"metric_type": "BM25"},
                    limit=limit,
                )
                dense_req = AnnSearchRequest(
                    data=[dense_vector],
                    anns_field="embedding",
                    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
                    limit=limit,
                )
                results = self._client.hybrid_search(
                    collection_name=self.collection_name,
                    reqs=[sparse_req, dense_req],
                    ranker=RRFRanker(k=60),
                    limit=limit,
                    output_fields=output_fields,
                )
                return self._format_hits(results, default_method="Hybrid HNSW+BM25")
            except Exception as exc:
                logger.warning("Milvus hybrid search failed, falling back to dense HNSW: %s", exc)

        return self._dense_search(dense_vector, limit, output_fields)

    def _dense_search(
        self,
        dense_vector: list[float],
        limit: int,
        output_fields: list[str],
    ) -> list[dict[str, Any]]:
        results = self._client.search(
            collection_name=self.collection_name,
            data=[dense_vector],
            anns_field="embedding",
            search_params={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=limit,
            output_fields=output_fields,
        )
        return self._format_hits(results, default_method="Dense HNSW")

    def _format_hits(self, results, default_method: str) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        if not results or not results[0]:
            return hits

        for idx, hit in enumerate(results[0]):
            entity = hit.get("entity") or {}
            verse_id = hit.get("id") or entity.get("id")
            verse = self._corpus_by_id.get(verse_id)
            if verse is None:
                continue
            distance = float(hit.get("distance", 0.0))
            if default_method == "Dense HNSW":
                score = max(1, min(100, int((1.0 - distance) * 100)))
            else:
                score = max(1, min(100, 95 - idx * 4))
            hits.append(
                {
                    "verse": verse.to_dict(),
                    "score": score,
                    "method": default_method,
                    "milvusDistance": round(distance, 4),
                }
            )
        return hits
