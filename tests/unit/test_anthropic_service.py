import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.anthropic_service import AnthropicService


@pytest.fixture
def service():
    with patch("app.services.anthropic_service.anthropic") as mock_lib:
        mock_client = Mock()
        mock_lib.Anthropic.return_value = mock_client
        svc = AnthropicService(api_key="test-key")
        svc._mock_client = mock_client
        yield svc


def test_generate_passes_system_as_top_level_param(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="The answer")]
    service._mock_client.messages.create.return_value = mock_response

    result = service.generate(prompt="What is AI?", system="You are an expert.")

    assert result == "The answer"
    call_kwargs = service._mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are an expert."
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is AI?"}]


def test_generate_system_defaults_to_empty_string(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="ok")]
    service._mock_client.messages.create.return_value = mock_response

    service.generate(prompt="test")  # no system arg

    call_kwargs = service._mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == ""


def test_generate_returns_text(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="hello")]
    service._mock_client.messages.create.return_value = mock_response

    assert service.generate(prompt="hi") == "hello"
