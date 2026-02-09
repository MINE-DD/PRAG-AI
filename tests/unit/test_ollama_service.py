import pytest
from unittest.mock import Mock, patch
from backend.app.services.ollama_service import OllamaService


@pytest.fixture
def ollama_service():
    """Create OllamaService with mocked client"""
    with patch('backend.app.services.ollama_service.ollama') as mock_ollama:
        service = OllamaService(url="http://localhost:11434", model="llama3")
        service.client = mock_ollama
        return service


def test_generate_embedding(ollama_service):
    """Test generating embeddings"""
    ollama_service.client.embeddings = Mock(return_value={"embedding": [0.1] * 768})

    embedding = ollama_service.generate_embedding("test text")

    assert len(embedding) == 768
    ollama_service.client.embeddings.assert_called_once()


def test_generate_embeddings_batch(ollama_service):
    """Test batch embedding generation"""
    ollama_service.client.embeddings = Mock(return_value={"embedding": [0.1] * 768})

    texts = ["text 1", "text 2", "text 3"]
    embeddings = ollama_service.generate_embeddings_batch(texts)

    assert len(embeddings) == 3
    assert ollama_service.client.embeddings.call_count == 3


def test_generate_response(ollama_service):
    """Test generating LLM response"""
    ollama_service.client.chat = Mock(return_value={
        "message": {"content": "This is a response"}
    })

    response = ollama_service.generate(
        prompt="Test prompt",
        system="You are a helpful assistant"
    )

    assert "response" in response
    ollama_service.client.chat.assert_called_once()
