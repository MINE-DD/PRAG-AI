from unittest.mock import Mock, patch

import numpy as np
from app.services.sparse_embedding_service import SparseEmbeddingService


def _mock_embedding(indices, values):
    emb = Mock()
    emb.indices = np.array(indices)
    emb.values = np.array(values)
    return emb


@patch("app.services.sparse_embedding_service.SparseEmbeddingService._get_model")
def test_generate_sparse_embedding(mock_get_model):
    mock_model = Mock()
    mock_model.embed.return_value = [_mock_embedding([0, 1, 2], [0.1, 0.5, 0.3])]
    mock_get_model.return_value = mock_model

    svc = SparseEmbeddingService()
    result = svc.generate_sparse_embedding("test text")

    assert "indices" in result
    assert "values" in result
    assert result["indices"] == [0, 1, 2]
    assert len(result["values"]) == 3


@patch("app.services.sparse_embedding_service.SparseEmbeddingService._get_model")
def test_generate_sparse_embeddings_batch(mock_get_model):
    mock_model = Mock()
    mock_model.embed.return_value = [
        _mock_embedding([0, 1], [0.2, 0.8]),
        _mock_embedding([2, 3], [0.4, 0.6]),
    ]
    mock_get_model.return_value = mock_model

    svc = SparseEmbeddingService()
    results = svc.generate_sparse_embeddings_batch(["text one", "text two"])

    assert len(results) == 2
    assert all("indices" in r and "values" in r for r in results)


def test_model_lazy_loaded():
    """_model starts as None and is loaded on first _get_model call."""
    svc = SparseEmbeddingService()
    assert svc._model is None
