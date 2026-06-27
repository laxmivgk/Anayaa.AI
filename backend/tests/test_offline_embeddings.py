import os
import sys
import types

import pytest

from app.retrieval.embeddings import ScriptureEmbedder


class FakeSentenceTransformer:
    calls = []

    def __init__(self, model_name, *, local_files_only=False):
        self.calls.append({"model": model_name, "local_files_only": local_files_only})

    def get_embedding_dimension(self):
        return 384


def test_embedding_loader_uses_local_files_only_in_offline_mode(monkeypatch):
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    FakeSentenceTransformer.calls = []

    embedder = ScriptureEmbedder("cached-model", local_files_only=True)

    assert embedder.dimension == 384
    assert FakeSentenceTransformer.calls == [{"model": "cached-model", "local_files_only": True}]
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_embedding_loader_explains_missing_offline_cache(monkeypatch):
    class MissingSentenceTransformer:
        def __init__(self, model_name, *, local_files_only=False):
            raise OSError("not cached")

    fake_module = types.SimpleNamespace(SentenceTransformer=MissingSentenceTransformer)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    with pytest.raises(RuntimeError, match="not available in the local cache"):
        ScriptureEmbedder("missing-model", local_files_only=True)
