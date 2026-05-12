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


# ---------------------------------------------------------------------------
# create_collection hybrid path
# ---------------------------------------------------------------------------


def test_create_collection_hybrid_sets_sparse_config(qdrant_service):
    """hybrid search_type passes sparse_vectors_config to client."""
    qdrant_service.client.create_collection = Mock()
    qdrant_service.create_collection("coll", vector_size=768, search_type="hybrid")
    call_kwargs = qdrant_service.client.create_collection.call_args[1]
    assert call_kwargs["sparse_vectors_config"] is not None


def test_create_collection_dense_has_no_sparse_config(qdrant_service):
    """Dense-only search_type passes None for sparse_vectors_config."""
    qdrant_service.client.create_collection = Mock()
    qdrant_service.create_collection("coll", vector_size=768, search_type="dense")
    call_kwargs = qdrant_service.client.create_collection.call_args[1]
    assert call_kwargs["sparse_vectors_config"] is None


# ---------------------------------------------------------------------------
# collection_exists
# ---------------------------------------------------------------------------


def test_collection_exists_true(qdrant_service):
    """Returns True when get_collection succeeds."""
    qdrant_service.client.get_collection = Mock(return_value=Mock())
    assert qdrant_service.collection_exists("coll") is True


def test_collection_exists_false_on_exception(qdrant_service):
    """Returns False when get_collection raises any exception."""
    qdrant_service.client.get_collection = Mock(side_effect=Exception("not found"))
    assert qdrant_service.collection_exists("coll") is False


# ---------------------------------------------------------------------------
# get_vector_size
# ---------------------------------------------------------------------------


def test_get_vector_size_named_vectors(qdrant_service):
    """Named-vectors config (dict) returns the dense vector size."""
    mock_info = Mock()
    mock_info.config.params.vectors = {"dense": Mock(size=1024)}
    qdrant_service.client.get_collection = Mock(return_value=mock_info)
    assert qdrant_service.get_vector_size("coll") == 1024


def test_get_vector_size_unnamed_vectors(qdrant_service):
    """Unnamed-vectors config (VectorParams) returns its size attribute."""
    mock_info = Mock()
    unnamed = Mock()
    unnamed.size = 512
    # Not a dict — isinstance check will be False
    mock_info.config.params.vectors = unnamed
    qdrant_service.client.get_collection = Mock(return_value=mock_info)
    assert qdrant_service.get_vector_size("coll") == 512


# ---------------------------------------------------------------------------
# upsert_chunks with sparse vectors
# ---------------------------------------------------------------------------


def test_upsert_chunks_with_sparse_vectors(qdrant_service):
    """Sparse vectors are embedded in point data when named vectors + sparse provided."""
    mock_info = Mock()
    mock_info.config.params.vectors = {"dense": Mock(size=768)}
    qdrant_service.client.get_collection = Mock(return_value=mock_info)
    qdrant_service.client.upsert = Mock()

    chunks = [
        Chunk(
            paper_id="p1",
            unique_id="U1",
            chunk_text="text",
            chunk_type=ChunkType.BODY,
            page_number=1,
        )
    ]
    dense = [[0.1] * 768]
    sparse = [{"indices": [1, 2], "values": [0.5, 0.3]}]

    qdrant_service.upsert_chunks("coll", chunks, dense, sparse_vectors=sparse)

    qdrant_service.client.upsert.assert_called_once()
    points = qdrant_service.client.upsert.call_args[1]["points"]
    assert "dense" in points[0].vector
    assert "sparse" in points[0].vector


# ---------------------------------------------------------------------------
# search — hybrid and unnamed-vector paths
# ---------------------------------------------------------------------------


def test_search_hybrid_uses_fusion_query(qdrant_service):
    """use_hybrid=True with sparse collection triggers RRF fusion search."""
    _mock_collection(qdrant_service, sparse=True)

    qdrant_service.search(
        collection_name="test-collection",
        query_vector=[0.1] * 768,
        sparse_vector={"indices": [1, 2], "values": [0.5, 0.3]},
        use_hybrid=True,
    )

    call_kwargs = qdrant_service.client.query_points.call_args[1]
    assert "prefetch" in call_kwargs
    assert len(call_kwargs["prefetch"]) == 2


def test_search_unnamed_vector_collection(qdrant_service):
    """Collections without named vectors use legacy search (no 'using' key)."""
    mock_info = Mock()
    mock_info.config.params.vectors = Mock()  # not a dict
    mock_info.config.params.sparse_vectors = None
    qdrant_service.client.get_collection = Mock(return_value=mock_info)
    mock_response = Mock()
    mock_response.points = []
    qdrant_service.client.query_points = Mock(return_value=mock_response)

    qdrant_service.search("coll", [0.1] * 768)

    call_kwargs = qdrant_service.client.query_points.call_args[1]
    assert "using" not in call_kwargs


# ---------------------------------------------------------------------------
# get_chunks_for_paper
# ---------------------------------------------------------------------------


def test_get_chunks_for_paper_returns_sorted_by_chunk_index(qdrant_service):
    """scroll results are sorted by chunk_index ascending and capped at limit."""
    p1 = Mock()
    p1.payload = {"metadata": {"chunk_index": 1}}
    p0 = Mock()
    p0.payload = {"metadata": {"chunk_index": 0}}

    qdrant_service.client.scroll = Mock(return_value=([p1, p0], None))

    results = qdrant_service.get_chunks_for_paper("coll", "paper-1", limit=10)

    assert len(results) == 2
    assert results[0].payload["metadata"]["chunk_index"] == 0
    assert results[1].payload["metadata"]["chunk_index"] == 1


def test_get_chunks_for_paper_stops_on_no_offset(qdrant_service):
    """Loop exits when scroll returns offset=None (no more pages)."""
    p = Mock()
    p.payload = {"metadata": {"chunk_index": 0}}
    qdrant_service.client.scroll = Mock(return_value=([p], None))

    results = qdrant_service.get_chunks_for_paper("coll", "paper-1", limit=5)

    assert qdrant_service.client.scroll.call_count == 1
    assert len(results) == 1


# ---------------------------------------------------------------------------
# delete_by_paper_id
# ---------------------------------------------------------------------------


def test_delete_by_paper_id(qdrant_service):
    """delete_by_paper_id calls client.delete with the collection name."""
    qdrant_service.client.delete = Mock()
    qdrant_service.delete_by_paper_id("coll", "paper-1")
    qdrant_service.client.delete.assert_called_once()
    assert qdrant_service.client.delete.call_args[1]["collection_name"] == "coll"
