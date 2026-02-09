import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert "qdrant" in data
    assert "ollama" in data
