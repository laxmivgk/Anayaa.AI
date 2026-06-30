import numpy as np

from app.retrieval.embeddings import _mean_pool_and_normalize, resolve_onnx_embedding_dir


def test_mean_pool_and_normalize_uses_attention_mask():
    token_embeddings = np.array(
        [
            [
                [1.0, 1.0],
                [3.0, 1.0],
                [99.0, 99.0],
            ]
        ],
        dtype=np.float32,
    )
    attention_mask = np.array([[1, 1, 0]], dtype=np.int64)

    result = _mean_pool_and_normalize(token_embeddings, attention_mask)

    expected = np.array([[2.0, 1.0]], dtype=np.float32)
    expected = expected / np.linalg.norm(expected, axis=1, keepdims=True)
    assert np.allclose(result, expected)


def test_onnx_embedding_dir_uses_safe_model_slug():
    path = resolve_onnx_embedding_dir(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "data/onnx_embeddings",
    )

    assert path.name == "sentence-transformers__paraphrase-multilingual-MiniLM-L12-v2"
    assert path.as_posix().endswith(
        "backend/data/onnx_embeddings/sentence-transformers__paraphrase-multilingual-MiniLM-L12-v2"
    )
