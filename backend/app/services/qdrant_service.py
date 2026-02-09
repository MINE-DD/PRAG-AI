from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from typing import Optional
import uuid


class QdrantService:
    """Service for interacting with Qdrant vector database"""

    def __init__(self, url: str):
        self.client = QdrantClient(url=url)

    def create_collection(self, collection_name: str, vector_size: int = 768):
        """Create a new Qdrant collection"""
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
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

    def upsert_chunks(self, collection_name: str, chunks: list, vectors: list):
        """Upsert chunks with embeddings to Qdrant"""
        points = []
        for chunk, vector in zip(chunks, vectors):
            point = PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={
                    "paper_id": chunk.paper_id,
                    "unique_id": chunk.unique_id,
                    "chunk_text": chunk.chunk_text,
                    "chunk_type": chunk.chunk_type.value,
                    "page_number": chunk.page_number,
                    "metadata": chunk.metadata or {}
                }
            )
            points.append(point)

        self.client.upsert(collection_name=collection_name, points=points)

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 10,
        paper_ids: Optional[list[str]] = None
    ) -> list:
        """Search for similar chunks"""
        query_filter = None
        if paper_ids:
            query_filter = {
                "must": [
                    {"key": "paper_id", "match": {"any": paper_ids}}
                ]
            }

        return self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            query_filter=query_filter
        )

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
            }
        )
