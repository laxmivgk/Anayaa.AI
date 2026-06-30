from __future__ import annotations

import logging
import os
import re
import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

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
def get_embedder() -> "BaseScriptureEmbedder":
    settings = get_settings()
    backend = settings.embedding_backend.lower()
    if backend in {"onnx", "auto"}:
        try:
            return OnnxScriptureEmbedder(settings.embedding_model, settings.embedding_onnx_dir)
        except RuntimeError:
            if backend == "onnx":
                raise
            logger.warning("ONNX embedding assets are unavailable; falling back to SentenceTransformer.")
    return SentenceTransformerScriptureEmbedder(settings.embedding_model, local_files_only=settings.offline_mode)


class BaseScriptureEmbedder:
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _safe_model_slug(model_name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", model_name).strip("_") or "embedding_model"


def resolve_onnx_embedding_dir(model_name: str, onnx_root: str) -> Path:
    root = Path(onnx_root)
    if not root.is_absolute():
        root = _backend_root() / root
    return root / _safe_model_slug(model_name)


class SentenceTransformerScriptureEmbedder(BaseScriptureEmbedder):
    def __init__(self, model_name: str, *, local_files_only: bool = True) -> None:
        if local_files_only:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            os.environ.setdefault("HF_DATASETS_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", model_name)
        try:
            self.model: SentenceTransformer = SentenceTransformer(model_name, local_files_only=local_files_only)
        except OSError as exc:
            if local_files_only:
                raise RuntimeError(
                    "Embedding model is not available in the local cache. "
                    f"Connect to the internet once and run backend startup/seed so '{model_name}' can download, "
                    "then Anayaa can run offline."
                ) from exc
            raise
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


class OnnxScriptureEmbedder(BaseScriptureEmbedder):
    def __init__(self, model_name: str, onnx_root: str) -> None:
        model_dir = resolve_onnx_embedding_dir(model_name, onnx_root)
        model_path = model_dir / "model.onnx"
        metadata_path = model_dir / "metadata.json"
        if not model_path.exists() or not metadata_path.exists():
            raise RuntimeError(
                "ONNX embedding assets are not available locally. "
                "Connect to Wi-Fi once and run ./scripts/setup-online.sh."
            )

        import onnxruntime as ort
        from transformers import AutoTokenizer

        with metadata_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)

        self.model_dir = model_dir
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.input_names = {item.name for item in self.session.get_inputs()}
        self.dimension = int(metadata["dimension"])
        self.max_length = int(metadata.get("max_length", 256))
        logger.info("Loaded ONNX embedding model from %s", model_dir)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        batch_size = 32
        for index in range(0, len(texts), batch_size):
            batch = texts[index : index + batch_size]
            results.extend(self._encode_batch(batch).tolist())
        return results

    def embed_query(self, text: str) -> list[float]:
        return self._encode_batch([text])[0].tolist()

    def _encode_batch(self, texts: list[str]) -> np.ndarray:
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="np",
        )
        feeds = {name: encoded[name] for name in self.input_names if name in encoded}
        outputs = self.session.run(None, feeds)
        token_embeddings = outputs[0]
        attention_mask = encoded["attention_mask"]
        return _mean_pool_and_normalize(token_embeddings, attention_mask)


def _mean_pool_and_normalize(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    mask = np.expand_dims(attention_mask.astype(np.float32), axis=-1)
    summed = np.sum(token_embeddings * mask, axis=1)
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    vectors = summed / counts
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, a_min=1e-12, a_max=None)


def export_onnx_embedding_model(
    model_name: str,
    onnx_root: str,
    *,
    local_files_only: bool = False,
    max_length: int = 256,
) -> Path:
    """Export the transformer encoder to ONNX for fast local embedding inference."""
    import torch
    from transformers import AutoModel, AutoTokenizer
    try:
        import onnxscript  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "ONNX export requires the 'onnxscript' package. "
            "Run ./scripts/setup-online.sh so backend/anayaa is refreshed from backend/requirements.txt."
        ) from exc

    model_dir = resolve_onnx_embedding_dir(model_name, onnx_root)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.onnx"

    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_files_only)
    transformer = AutoModel.from_pretrained(model_name, local_files_only=local_files_only)
    transformer.eval()

    encoded = tokenizer(
        ["truth compassion duty"],
        padding=True,
        truncation=True,
        max_length=max_length,
        return_tensors="pt",
    )
    input_names = [name for name in ("input_ids", "attention_mask", "token_type_ids") if name in encoded]

    class TransformerWrapper(torch.nn.Module):
        def __init__(self, inner_model):
            super().__init__()
            self.inner_model = inner_model

        def forward(self, *args):
            inputs = dict(zip(input_names, args))
            return self.inner_model(**inputs).last_hidden_state

    dynamic_axes = {name: {0: "batch", 1: "sequence"} for name in input_names}
    dynamic_axes["last_hidden_state"] = {0: "batch", 1: "sequence"}

    with torch.no_grad():
        torch.onnx.export(
            TransformerWrapper(transformer),
            tuple(encoded[name] for name in input_names),
            str(model_path),
            input_names=input_names,
            output_names=["last_hidden_state"],
            dynamic_axes=dynamic_axes,
            opset_version=14,
            dynamo=False,
        )

    tokenizer.save_pretrained(model_dir)
    metadata = {
        "model_name": model_name,
        "dimension": int(transformer.config.hidden_size),
        "input_names": input_names,
        "pooling": "mean",
        "normalize": True,
        "max_length": max_length,
    }
    with (model_dir / "metadata.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, sort_keys=True)
    logger.info("Exported ONNX embedding model to %s", model_path)
    return model_dir


# Backwards-compatible import name for older helper scripts.
ScriptureEmbedder = SentenceTransformerScriptureEmbedder
