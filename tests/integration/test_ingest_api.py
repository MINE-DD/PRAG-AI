import json
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
    """Create temporary data directory."""
    temp_dir = tempfile.mkdtemp()
    original = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    settings.data_dir = original
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_preprocessed_dir():
    """Create temporary preprocessed directory."""
    temp_dir = tempfile.mkdtemp()
    (Path(temp_dir) / "paper1.md").write_text("# Paper 1\n\nContent here.")
    (Path(temp_dir) / "paper1_metadata.json").write_text(json.dumps({
        "title": "Test Paper",
        "authors": ["Author One"],
        "publication_date": "2024",
    }))
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant service."""
    with patch("app.api.ingest.QdrantService") as mock_cls:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.upsert_chunks = Mock()
        mock_instance.collection_exists = Mock(return_value=True)
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_ollama():
    """Mock Ollama service."""
    with patch("app.api.ingest.OllamaService") as mock_cls:
        mock_instance = Mock()
        mock_instance.generate_embedding.return_value = [0.1] * 1024
        mock_instance.generate_embeddings_batch.return_value = [[0.1] * 1024] * 10
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def client(temp_data_dir, mock_qdrant, mock_ollama):
    return TestClient(app)


def test_scan_not_found(client):
    """Test scanning a non-existent path."""
    response = client.post("/ingest/scan", json={"path": "/nonexistent"})
    assert response.status_code == 404


def test_scan_preprocessed(client, temp_preprocessed_dir):
    """Test scanning a preprocessed directory."""
    response = client.post("/ingest/scan", json={"path": temp_preprocessed_dir})
    assert response.status_code == 200
    data = response.json()
    assert data["file_count"] == 1
    assert data["files"][0]["markdown_file"] == "paper1.md"


def test_create_collection(client, temp_data_dir, temp_preprocessed_dir):
    """Test creating a collection via ingestion API."""
    response = client.post("/ingest/create", json={
        "name": "Test Collection",
        "preprocessed_path": temp_preprocessed_dir,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == "test_collection"
    assert data["file_count"] == 1

    # Verify directory structure
    coll_path = Path(temp_data_dir) / "test_collection"
    assert coll_path.exists()
    assert (coll_path / "metadata").exists()
    assert (coll_path / "collection_info.json").exists()


def test_create_collection_duplicate(client, temp_data_dir, temp_preprocessed_dir):
    """Test creating a duplicate collection."""
    client.post("/ingest/create", json={
        "name": "Test Collection",
        "preprocessed_path": temp_preprocessed_dir,
    })
    response = client.post("/ingest/create", json={
        "name": "Test Collection",
        "preprocessed_path": temp_preprocessed_dir,
    })
    assert response.status_code == 409


def test_ingest_file(client, temp_data_dir, temp_preprocessed_dir):
    """Test ingesting a single file."""
    # Create collection first
    client.post("/ingest/create", json={
        "name": "Test Collection",
        "preprocessed_path": temp_preprocessed_dir,
    })

    response = client.post("/ingest/test_collection/file", json={
        "markdown_file": "paper1.md",
        "preprocessed_path": temp_preprocessed_dir,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["paper_id"] == "paper1"
    assert data["chunks_created"] > 0


def test_ingest_file_collection_not_found(client, temp_preprocessed_dir):
    """Test ingesting into non-existent collection."""
    response = client.post("/ingest/nonexistent/file", json={
        "markdown_file": "paper1.md",
        "preprocessed_path": temp_preprocessed_dir,
    })
    assert response.status_code == 404
