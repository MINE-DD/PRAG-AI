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
         patch('app.api.compare.QdrantService') as mock_compare:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)

        # Mock search results
        mock_chunk = Mock()
        mock_chunk.payload = {
            "paper_id": "paper-123",
            "unique_id": "SmithTransformers2024",
            "chunk_text": "This paper introduces transformers with attention mechanisms.",
            "chunk_type": "abstract",
            "page_number": 1,
            "metadata": {}
        }
        mock_instance.search = Mock(return_value=[mock_chunk] * 3)

        mock_collections.return_value = mock_instance
        mock_compare.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock Ollama service"""
    with patch('app.api.compare.OllamaService') as mock:
        mock_instance = Mock()
        comparison_text = """## Similarities
Both papers focus on transformer architectures and attention mechanisms.

## Differences
Paper A uses self-attention while Paper B employs cross-attention.

## Key Findings
Both demonstrate improved performance on NLP tasks."""
        mock_instance.generate = Mock(return_value=comparison_text)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_metadata_service():
    """Mock metadata service"""
    with patch('app.api.compare.MetadataService') as mock:
        from app.models.paper import PaperMetadata

        mock_instance = Mock()

        def get_metadata(collection_id, paper_id):
            return PaperMetadata(
                paper_id=paper_id,
                title=f"Paper {paper_id[-3:]}",
                authors=["Smith, J."],
                year=2024,
                unique_id=f"Smith{paper_id[-3:]}2024"
            )

        mock_instance.get_paper_metadata = Mock(side_effect=get_metadata)
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


def test_compare_two_papers(client, test_collection):
    """Test comparing two papers"""
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={
            "paper_ids": ["paper-123", "paper-456"]
        }
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "comparison" in data
    assert "paper_ids" in data
    assert len(data["paper_ids"]) == 2
    assert "papers" in data


def test_compare_multiple_papers(client, test_collection):
    """Test comparing more than two papers"""
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={
            "paper_ids": ["paper-123", "paper-456", "paper-789"]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["paper_ids"]) == 3


def test_compare_with_aspect_filter(client, test_collection):
    """Test comparing papers with specific aspect"""
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={
            "paper_ids": ["paper-123", "paper-456"],
            "aspect": "methodology"
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "comparison" in data


def test_compare_nonexistent_collection(client):
    """Test comparing in nonexistent collection"""
    response = client.post(
        "/collections/nonexistent/compare",
        json={"paper_ids": ["paper-123", "paper-456"]}
    )

    assert response.status_code == 404


def test_compare_single_paper(client, test_collection):
    """Test compare with only one paper (should fail)"""
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={"paper_ids": ["paper-123"]}
    )

    # Need at least 2 papers to compare
    assert response.status_code == 422


def test_compare_includes_metadata(client, test_collection):
    """Test that comparison includes paper metadata"""
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={"paper_ids": ["paper-123", "paper-456"]}
    )

    assert response.status_code == 200
    data = response.json()

    # Should include metadata for all papers
    assert "papers" in data
    assert len(data["papers"]) == 2

    for paper in data["papers"]:
        assert "paper_id" in paper
        assert "title" in paper
        assert "authors" in paper
