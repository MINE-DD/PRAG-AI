import pytest
from unittest.mock import Mock, AsyncMock, patch
from app.services.qdrant_service import QdrantService
from app.models.paper import Chunk, ChunkType


@pytest.fixture
def qdrant_service():
    """Create QdrantService with mocked client"""
    with patch('backend.app.services.qdrant_service.QdrantClient') as mock_client:
        service = QdrantService(url="http://localhost:6333")
        service.client = Mock()
        return service


def test_create_collection(qdrant_service):
    """Test creating a Qdrant collection"""
    qdrant_service.client.create_collection = Mock()

    qdrant_service.create_collection("test-collection", vector_size=768)

    qdrant_service.client.create_collection.assert_called_once()


def test_delete_collection(qdrant_service):
    """Test deleting a Qdrant collection"""
    qdrant_service.client.delete_collection = Mock()

    qdrant_service.delete_collection("test-collection")

    qdrant_service.client.delete_collection.assert_called_once_with(collection_name="test-collection")


def test_upsert_chunks(qdrant_service):
    """Test upserting chunks to Qdrant"""
    chunks = [
        Chunk(
            paper_id="paper-1",
            unique_id="Test2024",
            chunk_text="Test content",
            chunk_type=ChunkType.BODY,
            page_number=1
        )
    ]
    vectors = [[0.1] * 768]

    qdrant_service.client.upsert = Mock()

    qdrant_service.upsert_chunks("test-collection", chunks, vectors)

    qdrant_service.client.upsert.assert_called_once()


def test_search_chunks(qdrant_service):
    """Test searching for chunks"""
    qdrant_service.client.search = Mock(return_value=[])

    results = qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
        limit=10
    )

    assert isinstance(results, list)
    qdrant_service.client.search.assert_called_once()
