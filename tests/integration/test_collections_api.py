import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings


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
    with patch('backend.app.api.collections.QdrantService') as mock:
        mock_instance = Mock()
        mock_instance.create_collection = Mock()
        mock_instance.delete_collection = Mock()
        mock_instance.collection_exists = Mock(return_value=True)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def client(temp_data_dir, mock_qdrant):
    return TestClient(app)


def test_create_collection(client):
    """Test creating a new collection"""
    response = client.post(
        "/collections",
        json={"name": "Test Collection", "description": "Test"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "collection_id" in data
    assert data["name"] == "Test Collection"


def test_list_collections(client):
    """Test listing collections"""
    response = client.get("/collections")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_collection(client):
    """Test getting a specific collection"""
    # First create a collection
    create_response = client.post(
        "/collections",
        json={"name": "Test Collection 2"}
    )
    collection_id = create_response.json()["collection_id"]

    # Then get it
    response = client.get(f"/collections/{collection_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["collection_id"] == collection_id


def test_delete_collection(client):
    """Test deleting a collection"""
    # Create collection
    create_response = client.post(
        "/collections",
        json={"name": "Delete Me"}
    )
    collection_id = create_response.json()["collection_id"]

    # Delete it
    response = client.delete(f"/collections/{collection_id}")

    assert response.status_code == 200
