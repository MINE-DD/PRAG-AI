from unittest.mock import Mock, patch

import pytest
from app.models.paper import Chunk, ChunkType
from app.services.qdrant_service import QdrantService


@pytest.fixture
def qdrant_service():
    """Create QdrantService with mocked client"""
    with patch("backend.app.services.qdrant_service.QdrantClient") as mock_client:
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

    qdrant_service.client.delete_collection.assert_called_once_with(
        collection_name="test-collection"
    )


def test_upsert_chunks(qdrant_service):
    """Test upserting chunks to Qdrant"""
    chunks = [
        Chunk(
            paper_id="paper-1",
            unique_id="Test2024",
            chunk_text="Test content",
            chunk_type=ChunkType.BODY,
            page_number=1,
        )
    ]
    vectors = [[0.1] * 768]

    qdrant_service.client.upsert = Mock()

    qdrant_service.upsert_chunks("test-collection", chunks, vectors)

    qdrant_service.client.upsert.assert_called_once()


def _mock_collection(qdrant_service, sparse=False):
    mock_info = Mock()
    mock_info.config.params.vectors = {"dense": Mock(size=768)}
    mock_info.config.params.sparse_vectors = {"sparse": Mock()} if sparse else None
    qdrant_service.client.get_collection = Mock(return_value=mock_info)
    mock_response = Mock()
    mock_response.points = []
    qdrant_service.client.query_points = Mock(return_value=mock_response)


def test_search_chunks(qdrant_service):
    """Test searching for chunks"""
    _mock_collection(qdrant_service)

    results = qdrant_service.search(
        collection_name="test-collection", query_vector=[0.1] * 768, limit=10
    )

    assert isinstance(results, list)
    qdrant_service.client.query_points.assert_called_once()


def test_search_with_paper_id_filter(qdrant_service):
    """paper_ids builds a must filter."""
    _mock_collection(qdrant_service)

    qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
        paper_ids=["paper-1", "paper-2"],
    )

    call_kwargs = qdrant_service.client.query_points.call_args[1]
    assert call_kwargs["query_filter"] is not None


def test_search_with_exclude_chunk_types(qdrant_service):
    """exclude_chunk_types builds a must_not filter."""
    _mock_collection(qdrant_service)

    qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
        exclude_chunk_types=["references", "acknowledgements"],
    )

    call_kwargs = qdrant_service.client.query_points.call_args[1]
    q_filter = call_kwargs["query_filter"]
    assert q_filter is not None
    assert q_filter.must_not is not None
    assert len(q_filter.must_not) == 2


def test_search_no_filter_when_no_constraints(qdrant_service):
    """No filter is built when neither paper_ids nor exclude_chunk_types given."""
    _mock_collection(qdrant_service)

    qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
    )

    call_kwargs = qdrant_service.client.query_points.call_args[1]
    assert call_kwargs["query_filter"] is None
