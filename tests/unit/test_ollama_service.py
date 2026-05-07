from unittest.mock import Mock, patch

import pytest
from app.services.ollama_service import OllamaService


@pytest.fixture
def ollama_service():
    """Create OllamaService with mocked client"""
    with patch("backend.app.services.ollama_service.ollama") as mock_ollama:
        service = OllamaService(url="http://localhost:11434", model="llama3")
        service.client = mock_ollama
        return service


def _embed_response(*vectors):
    """Build a mock response matching ollama.Client.embed() return shape."""
    resp = Mock()
    resp.embeddings = [list(v) for v in vectors]
    return resp


def test_generate_embedding(ollama_service):
    """Test generating embeddings"""
    ollama_service.client.embed = Mock(return_value=_embed_response([0.1] * 768))

    embedding = ollama_service.generate_embedding("test text")

    assert len(embedding) == 768
    ollama_service.client.embed.assert_called_once()


def test_generate_embeddings_batch(ollama_service):
    """Test batch embedding generation"""
    batch = _embed_response([0.1] * 768, [0.2] * 768, [0.3] * 768)
    ollama_service.client.embed = Mock(return_value=batch)

    texts = ["text 1", "text 2", "text 3"]
    embeddings = ollama_service.generate_embeddings_batch(texts)

    assert len(embeddings) == 3
    ollama_service.client.embed.assert_called_once()


def test_generate_response(ollama_service):
    """Test generating LLM response"""
    ollama_service.client.chat = Mock(
        return_value={"message": {"content": "This is a response"}}
    )

    response = ollama_service.generate(
        prompt="Test prompt", system="You are a helpful assistant"
    )

    assert "response" in response
    ollama_service.client.chat.assert_called_once()


def test_generate_with_chat_history(ollama_service):
    """chat_history messages are included in the request."""
    ollama_service.client.chat = Mock(return_value={"message": {"content": "ok"}})
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    ollama_service.generate(prompt="follow-up", chat_history=history)

    messages = ollama_service.client.chat.call_args[1]["messages"]
    assert any(m["content"] == "hi" for m in messages)


def test_generate_empty_response_returns_fallback(ollama_service):
    """Empty LLM content returns the hardcoded fallback message."""
    ollama_service.client.chat = Mock(return_value={"message": {"content": ""}})

    response = ollama_service.generate(prompt="test")

    assert "OOPS" in response


def test_get_embedding_context_length(ollama_service):
    """Returns context length from modelinfo when available."""
    mock_info = Mock()
    mock_info.modelinfo = {"bert.context_length": 512}
    ollama_service.client.show = Mock(return_value=mock_info)

    length = ollama_service.get_embedding_context_length()

    assert length == 512


def test_get_embedding_context_length_fallback(ollama_service):
    """Returns 512 when modelinfo is unavailable."""
    ollama_service.client.show = Mock(side_effect=Exception("unavailable"))

    length = ollama_service.get_embedding_context_length()

    assert length == 512
