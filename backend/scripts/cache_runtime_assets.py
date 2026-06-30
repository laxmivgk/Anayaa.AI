#!/usr/bin/env python3
"""Download runtime model assets that Anayaa later loads offline."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_ONNX_DIR = "data/onnx_embeddings"


def _env_file_value(name: str, default: str) -> str:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return default
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith(f"{name}="):
            continue
        value = line.split("=", 1)[1].strip().strip('"').strip("'")
        return value or default
    return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache Anayaa runtime model assets for offline use.")
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("EMBEDDING_MODEL") or _env_file_value("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help="SentenceTransformer embedding model to cache.",
    )
    parser.add_argument(
        "--onnx-dir",
        default=os.environ.get("EMBEDDING_ONNX_DIR") or _env_file_value("EMBEDDING_ONNX_DIR", DEFAULT_ONNX_DIR),
        help="Directory where the exported ONNX embedding model should be stored.",
    )
    args = parser.parse_args()

    os.environ["OFFLINE_MODE"] = "false"
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE"):
        os.environ.pop(key, None)

    from app.retrieval.embeddings import ScriptureEmbedder, export_onnx_embedding_model

    print(f"[anayaa] Caching embedding model: {args.embedding_model}")
    embedder = ScriptureEmbedder(args.embedding_model, local_files_only=False)
    embedder.embed_query("truth compassion duty")
    print(f"[anayaa] Embedding model cached. dimension={embedder.dimension}")
    onnx_dir = export_onnx_embedding_model(args.embedding_model, args.onnx_dir, local_files_only=False)
    print(f"[anayaa] ONNX embedding model exported: {onnx_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
