from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    SparseVectorParams,
    SparseVector,
    PointStruct,
    Modifier,
    Prefetch,
    FusionQuery,
    Fusion,
)
from typing import Optional
import uuid


class QdrantService:
    """Service for interacting with Qdrant vector database"""

    def __init__(self, url: str):
        self.client = QdrantClient(url=url)

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 768,
        search_type: str = "dense",
    ):
        """Create a new Qdrant collection.

        Args:
            collection_name: Name of the collection.
            vector_size: Dimension of dense embeddings.
            search_type: "dense" for dense-only, "hybrid" for dense + BM42 sparse.
        """
        vectors_config = {"dense": VectorParams(size=vector_size, distance=Distance.COSINE)}

        sparse_vectors_config = None
        if search_type == "hybrid":
            sparse_vectors_config = {
                "sparse": SparseVectorParams(modifier=Modifier.IDF)
            }

        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=vectors_config,
            sparse_vectors_config=sparse_vectors_config,
        )

    def delete_collection(self, collection_name: str):
        """Delete a Qdrant collection"""
        self.client.delete_collection(collection_name=collection_name)

    def collection_exists(self, collection_name: str) -> bool:
        """Check if collection exists"""
        try:
            self.client.get_collection(collection_name)
            return True
        except Exception:
            return False

    def _collection_uses_named_vectors(self, collection_name: str) -> bool:
        """Check if collection uses named vectors (dict config) vs unnamed (VectorParams)."""
        config = self.client.get_collection(collection_name).config.params.vectors
        return isinstance(config, dict)

    def _collection_has_sparse(self, collection_name: str) -> bool:
        """Check if collection has sparse vector config."""
        info = self.client.get_collection(collection_name)
        sparse_config = info.config.params.sparse_vectors
        return sparse_config is not None and len(sparse_config) > 0

    def get_vector_size(self, collection_name: str) -> int:
        """Get the dense vector size for a collection (handles named and unnamed configs)."""
        config = self.client.get_collection(collection_name).config.params.vectors
        if isinstance(config, dict):
            return config["dense"].size
        return config.size

    def upsert_chunks(
        self,
        collection_name: str,
        chunks: list,
        vectors: list,
        sparse_vectors: Optional[list[dict]] = None,
    ):
        """Upsert chunks with embeddings to Qdrant.

        Args:
            collection_name: Target collection.
            chunks: List of Chunk objects.
            vectors: List of dense embedding vectors.
            sparse_vectors: Optional list of {"indices": [...], "values": [...]} for hybrid.
        """
        named = self._collection_uses_named_vectors(collection_name)

        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            if named:
                vec_data = {"dense": vector}
                if sparse_vectors and i < len(sparse_vectors):
                    sv = sparse_vectors[i]
                    vec_data["sparse"] = SparseVector(
                        indices=sv["indices"], values=sv["values"]
                    )
            else:
                vec_data = vector

            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vec_data,
                payload={
                    "paper_id": chunk.paper_id,
                    "unique_id": chunk.unique_id,
                    "chunk_text": chunk.chunk_text,
                    "chunk_type": chunk.chunk_type.value,
                    "page_number": chunk.page_number,
                    "metadata": chunk.metadata or {},
                },
            )
            points.append(point)

        self.client.upsert(collection_name=collection_name, points=points)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        paper_ids: Optional[list[str]] = None,
        sparse_vector: Optional[dict] = None,
        use_hybrid: bool = False,
    ) -> list:
        """Search for similar chunks.

        Args:
            collection_name: Collection to search.
            query_vector: Dense query embedding.
            limit: Max results.
            paper_ids: Optional paper ID filter.
            sparse_vector: Optional {"indices": [...], "values": [...]} for hybrid.
            use_hybrid: If True and collection supports it, use RRF fusion.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchAny

        query_filter = None
        if paper_ids:
            query_filter = Filter(
                must=[FieldCondition(key="paper_id", match=MatchAny(any=paper_ids))]
            )

        named = self._collection_uses_named_vectors(collection_name)
        has_sparse = self._collection_has_sparse(collection_name)

        if use_hybrid and has_sparse and sparse_vector:
            sparse_qv = SparseVector(
                indices=sparse_vector["indices"],
                values=sparse_vector["values"],
            )
            response = self.client.query_points(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(query=query_vector, using="dense", limit=limit),
                    Prefetch(query=sparse_qv, using="sparse", limit=limit),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=limit,
                query_filter=query_filter,
            )
        elif named:
            response = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                using="dense",
                limit=limit,
                query_filter=query_filter,
            )
        else:
            response = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
                query_filter=query_filter,
            )

        return response.points

    def delete_by_paper_id(self, collection_name: str, paper_id: str):
        """Delete all chunks for a specific paper"""
        self.client.delete(
            collection_name=collection_name,
            points_selector={
                "filter": {
                    "must": [
                        {"key": "paper_id", "match": {"value": paper_id}}
                    ]
                }
            },
        )
