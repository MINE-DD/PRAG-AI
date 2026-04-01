import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.google_service import GoogleService


@pytest.fixture
def service():
    with patch("app.services.google_service.genai") as mock_lib:
        mock_client = Mock()
        mock_lib.Client.return_value = mock_client
        svc = GoogleService(api_key="test-key")
        svc._mock_client = mock_client
        yield svc


def test_generate_passes_system_instruction(service):
    mock_response = Mock()
    mock_response.text = "The answer"
    service._mock_client.models.generate_content.return_value = mock_response

    result = service.generate(prompt="What is AI?", system="You are an expert.")

    assert result == "The answer"
    call_kwargs = service._mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].system_instruction == "You are an expert."


def test_generate_system_defaults_to_empty_string(service):
    mock_response = Mock()
    mock_response.text = "ok"
    service._mock_client.models.generate_content.return_value = mock_response

    service.generate(prompt="test")  # no system arg

    call_kwargs = service._mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].system_instruction == ""


def test_generate_returns_text(service):
    mock_response = Mock()
    mock_response.text = "hello"
    service._mock_client.models.generate_content.return_value = mock_response

    assert service.generate(prompt="hi") == "hello"
