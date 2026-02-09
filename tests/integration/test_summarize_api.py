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
         patch('app.api.summarize.QdrantService') as mock_summarize:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)

        # Mock search results for paper chunks
        mock_chunk = Mock()
        mock_chunk.payload = {
            "paper_id": "paper-123",
            "unique_id": "AuthorTest2024",
            "chunk_text": "This paper introduces a novel approach to natural language processing using transformers.",
            "chunk_type": "abstract",
            "page_number": 1,
            "metadata": {}
        }
        mock_instance.search = Mock(return_value=[mock_chunk] * 5)

        mock_collections.return_value = mock_instance
        mock_summarize.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock Ollama service"""
    with patch('app.api.summarize.OllamaService') as mock:
        mock_instance = Mock()
        # Return fake summary
        mock_instance.generate = Mock(return_value="This paper presents a comprehensive study on transformers in NLP. Key findings include improved performance and efficiency.")
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service"""
    with patch('app.api.summarize.MetadataService') as mock:
        from app.models.paper import PaperMetadata

        mock_instance = Mock()
        fake_metadata = PaperMetadata(
            paper_id="paper-123",
            title="Transformers in NLP",
            authors=["Smith, J."],
            year=2024,
            unique_id="AuthorTest2024"
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


def test_summarize_single_paper(client, test_collection):
    """Test summarizing a single paper"""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={
            "paper_ids": ["paper-123"]
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "summary" in data
    assert "paper_ids" in data
    assert data["paper_ids"] == ["paper-123"]
    assert len(data["summary"]) > 0


def test_summarize_multiple_papers(client, test_collection):
    """Test summarizing multiple papers"""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={
            "paper_ids": ["paper-123", "paper-456"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert len(data["paper_ids"]) == 2


def test_summarize_nonexistent_collection(client):
    """Test summarizing in nonexistent collection"""
    response = client.post(
        "/collections/nonexistent/summarize",
        json={"paper_ids": ["paper-123"]}
    )

    assert response.status_code == 404


def test_summarize_empty_paper_ids(client, test_collection):
    """Test summarize with empty paper_ids"""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={"paper_ids": []}
    )

    # Pydantic validation returns 422 for invalid input
    assert response.status_code == 422


def test_summarize_includes_metadata(client, test_collection):
    """Test that summary includes paper metadata"""
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={"paper_ids": ["paper-123"]}
    )

    assert response.status_code == 200
    data = response.json()

    # Should include paper metadata
    assert "papers" in data
    assert len(data["papers"]) > 0

    paper = data["papers"][0]
    assert "paper_id" in paper
    assert "title" in paper
    assert "authors" in paper
