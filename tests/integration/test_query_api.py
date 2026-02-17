import pytest
import sys
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
from app.core.config import settings


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory for tests"""
    temp_dir = tempfile.mkdtemp()
    original_data_dir = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    settings.data_dir = original_data_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant service"""
    with patch('app.api.collections.QdrantService') as mock_collections, \
         patch('app.api.rag.QdrantService') as mock_rag:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.delete_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)

        # Mock search results
        mock_search_result = Mock()
        mock_search_result.id = "chunk-123"
        mock_search_result.score = 0.95
        mock_search_result.payload = {
            "paper_id": "paper-123",
            "unique_id": "AuthorTest2024",
            "chunk_text": "This is a relevant chunk about natural language processing.",
            "chunk_type": "body",
            "page_number": 1,
            "metadata": {"chunk_index": 0}
        }
        mock_instance.search = Mock(return_value=[mock_search_result])

        mock_collections.return_value = mock_instance
        mock_rag.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock Ollama service"""
    with patch('app.api.rag.OllamaService') as mock:
        mock_instance = Mock()
        # Return fake embedding (1024-dimensional)
        mock_instance.generate_embedding = Mock(return_value=[0.1] * 1024)
        mock_instance.generate = Mock(return_value="This is a generated answer about NLP.")
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service"""
    with patch('app.api.rag.MetadataService') as mock:
        from app.models.paper import PaperMetadata

        mock_instance = Mock()
        # Return fake paper metadata
        fake_metadata = PaperMetadata(
            paper_id="paper-123",
            title="Test Paper on NLP",
            authors=["Smith, J.", "Doe, A."],
            year=2024,
            unique_id="SmithTestPaper2024"
        )
        mock_instance.get_paper_metadata = Mock(return_value=fake_metadata)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def test_collection(client, temp_data_dir, mock_qdrant):
    """Create a test collection"""
    response = client.post(
        "/collections",
        json={"name": "Test Collection"}
    )
    return response.json()["collection_id"]


@pytest.fixture
def client(temp_data_dir, mock_qdrant, mock_ollama, mock_metadata_service):
    return TestClient(app)


def test_rag_query_collection(client, test_collection):
    """Test RAG querying a collection with semantic search"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={
            "query_text": "What is natural language processing?",
            "limit": 5
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "answer" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) > 0

    # Verify result structure
    result = data["results"][0]
    assert "chunk_text" in result
    assert "paper_id" in result
    assert "unique_id" in result
    assert "score" in result
    assert result["score"] > 0


def test_rag_query_with_paper_filter(client, test_collection):
    """Test RAG querying with paper_ids filter"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={
            "query_text": "machine learning",
            "paper_ids": ["paper-123"],
            "limit": 3
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0


def test_rag_query_nonexistent_collection(client):
    """Test RAG querying a collection that doesn't exist"""
    response = client.post(
        "/collections/nonexistent/rag",
        json={"query_text": "test"}
    )

    assert response.status_code == 404


def test_rag_query_empty_text(client, test_collection):
    """Test RAG querying with empty query text"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": ""}
    )

    assert response.status_code == 400


def test_rag_query_returns_metadata(client, test_collection):
    """Test that RAG query results include chunk metadata"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "natural language processing"}
    )

    assert response.status_code == 200
    data = response.json()
    result = data["results"][0]

    # Verify metadata fields
    assert "chunk_type" in result
    assert "page_number" in result
    assert result["chunk_type"] in ["abstract", "body", "table", "figure_caption"]


def test_rag_query_with_citations(client, test_collection):
    """Test that RAG query results include citation information"""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={"query_text": "machine learning", "include_citations": True}
    )

    assert response.status_code == 200
    data = response.json()

    # Should have citations field
    assert "citations" in data
    assert isinstance(data["citations"], dict)

    # Citations should map paper_id to citation info
    if len(data["results"]) > 0:
        paper_id = data["results"][0]["paper_id"]
        assert paper_id in data["citations"]

        citation_info = data["citations"][paper_id]
        assert "apa" in citation_info
        assert "bibtex" in citation_info
        assert "unique_id" in citation_info
