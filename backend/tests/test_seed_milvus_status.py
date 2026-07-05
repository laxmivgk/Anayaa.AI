import importlib.util
from pathlib import Path


def _load_seed_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "seed_milvus.py"
    spec = importlib.util.spec_from_file_location("seed_milvus_script", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


seed_milvus = _load_seed_module()


def test_corpus_status_match_does_not_force_rebuild():
    status = {
        "ready": True,
        "verse_count": 2,
        "seed_version": seed_milvus.CORPUS_SEED_VERSION,
        "seed_checksum": "abc123",
    }

    assert seed_milvus.corpus_status_rebuild_reasons(status, 2, "abc123") == []


def test_corpus_status_checksum_change_forces_rebuild_even_when_count_matches():
    status = {
        "ready": True,
        "verse_count": 2,
        "seed_version": seed_milvus.CORPUS_SEED_VERSION,
        "seed_checksum": "old",
    }

    assert seed_milvus.corpus_status_rebuild_reasons(status, 2, "new") == ["corpus checksum changed"]


def test_corpus_status_count_change_forces_rebuild():
    status = {
        "ready": True,
        "verse_count": 2,
        "seed_version": seed_milvus.CORPUS_SEED_VERSION,
        "seed_checksum": "abc123",
    }

    assert seed_milvus.corpus_status_rebuild_reasons(status, 3, "abc123") == [
        "verse count changed (2 -> 3)"
    ]


def test_missing_or_unready_corpus_status_forces_rebuild():
    assert seed_milvus.corpus_status_rebuild_reasons(None, 2, "abc123") == ["corpus status is missing"]

    status = {
        "ready": False,
        "verse_count": 2,
        "seed_version": seed_milvus.CORPUS_SEED_VERSION,
        "seed_checksum": "abc123",
    }

    assert seed_milvus.corpus_status_rebuild_reasons(status, 2, "abc123") == [
        "corpus status is not ready"
    ]
