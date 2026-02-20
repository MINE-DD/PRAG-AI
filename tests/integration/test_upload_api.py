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
    # Override settings for tests
    original_data_dir = settings.data_dir
    settings.data_dir = temp_dir
    yield temp_dir
    # Restore original and cleanup
    settings.data_dir = original_data_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def mock_qdrant():
    """Mock Qdrant client"""
    with patch('app.api.collections.QdrantService') as mock:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.delete_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def client(temp_data_dir, mock_qdrant):
    return TestClient(app)


@pytest.fixture
def test_collection(client, temp_data_dir, mock_qdrant):
    """Create a test collection"""
    response = client.post(
        "/collections",
        json={"name": "Test Collection"}
    )
    return response.json()["collection_id"]


def test_list_papers_in_collection(client, test_collection):
    """Test listing papers in a collection"""
    response = client.get(f"/collections/{test_collection}/papers")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
