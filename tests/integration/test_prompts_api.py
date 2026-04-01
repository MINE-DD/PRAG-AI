import sys
import pytest
from pathlib import Path
from unittest.mock import Mock
from fastapi.testclient import TestClient

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
from app.services.prompt_service import get_prompt_service


def _mock_service():
    mock = Mock()
    mock.list_prompts.return_value = ["concise", "default"]
    mock.get_raw.return_value = {
        "name": "default",
        "system": "You are a research assistant.",
        "user": "Context: {context}\nQuestion: {question}",
    }
    return mock


@pytest.fixture(autouse=True)
def override_prompt_service():
    app.dependency_overrides[get_prompt_service] = lambda: _mock_service()
    yield
    app.dependency_overrides.pop(get_prompt_service, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_list_prompts_returns_names(client):
    response = client.get("/prompts/rag")
    assert response.status_code == 200
    assert response.json() == ["concise", "default"]


def test_get_prompt_returns_content(client):
    response = client.get("/prompts/rag/default")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "default"
    assert "system" in data
    assert "user" in data


def test_list_prompts_unknown_task_returns_404(client):
    mock = Mock()
    mock.list_prompts.side_effect = FileNotFoundError("Unknown task type: 'unknown'")
    app.dependency_overrides[get_prompt_service] = lambda: mock

    response = client.get("/prompts/unknown")
    assert response.status_code == 404


def test_get_prompt_not_found_returns_404(client):
    mock = Mock()
    mock.get_raw.side_effect = FileNotFoundError("Prompt 'gone' not found for task 'rag'")
    app.dependency_overrides[get_prompt_service] = lambda: mock

    response = client.get("/prompts/rag/gone")
    assert response.status_code == 404
