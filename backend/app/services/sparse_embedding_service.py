from typing import Optional


class SparseEmbeddingService:
    """Service for generating sparse (BM42) embeddings using fastembed."""

    MODEL_NAME = "Qdrant/bm42-all-minilm-l6-v2-attentions"

    def __init__(self):
        self._model = None

    def _get_model(self):
        """Lazy-load the sparse embedding model on first use."""
        if self._model is None:
            from fastembed import SparseTextEmbedding
            self._model = SparseTextEmbedding(model_name=self.MODEL_NAME)
        return self._model

    def generate_sparse_embedding(self, text: str) -> dict:
        """Generate a sparse embedding for a single text.

        Returns:
            {"indices": [...], "values": [...]}
        """
        model = self._get_model()
        results = list(model.embed([text]))
        embedding = results[0]
        return {
            "indices": embedding.indices.tolist(),
            "values": embedding.values.tolist(),
        }

    def generate_sparse_embeddings_batch(self, texts: list[str]) -> list[dict]:
        """Generate sparse embeddings for a batch of texts.

        Returns:
            List of {"indices": [...], "values": [...]}
        """
        model = self._get_model()
        results = list(model.embed(texts))
        return [
            {
                "indices": embedding.indices.tolist(),
                "values": embedding.values.tolist(),
            }
            for embedding in results
        ]
