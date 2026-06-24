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


def _chat_response(content: str, thinking: str = ""):
    """Build a mock response matching ollama.Client.chat() return shape."""
    msg = Mock()
    msg.content = content
    msg.thinking = thinking
    resp = Mock()
    resp.message = msg
    resp.prompt_eval_count = 10
    resp.eval_count = 5
    resp.model = "test-model"
    resp.created_at = None
    resp.done_reason = "stop"
    resp.total_duration = None
    resp.load_duration = None
    resp.prompt_eval_duration = None
    resp.eval_duration = None
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
    ollama_service.client.chat = Mock(return_value=_chat_response("This is a response"))

    text, usage = ollama_service.generate(
        prompt="Test prompt", system="You are a helpful assistant"
    )

    assert "response" in text
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 5
    assert usage["total_tokens"] == 15
    ollama_service.client.chat.assert_called_once()


def test_generate_with_chat_history(ollama_service):
    """chat_history messages are included in the request."""
    ollama_service.client.chat = Mock(return_value=_chat_response("ok"))
    history = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

    ollama_service.generate(prompt="follow-up", chat_history=history)

    messages = ollama_service.client.chat.call_args[1]["messages"]
    assert any(m["content"] == "hi" for m in messages)


def test_generate_empty_response_returns_fallback(ollama_service):
    """Empty LLM content returns the hardcoded fallback message."""
    ollama_service.client.chat = Mock(return_value=_chat_response(""))

    text, _ = ollama_service.generate(prompt="test")

    assert "OOPS" in text


def test_generate_native_thinking_field(ollama_service):
    """Thinking content from the native message.thinking field is returned in usage."""
    ollama_service.client.chat = Mock(
        return_value=_chat_response("Final answer.", thinking="I reasoned about this.")
    )

    text, usage = ollama_service.generate(prompt="test")

    assert text == "Final answer."
    assert usage["thinking"] == "I reasoned about this."


def test_generate_think_tag_stripped_from_content(ollama_service):
    """<think>…</think> tags are extracted from content and returned as thinking."""
    raw = "<think>internal reasoning</think>The actual answer."
    resp = _chat_response(raw)
    resp.message.thinking = ""  # no native field
    ollama_service.client.chat = Mock(return_value=resp)

    text, usage = ollama_service.generate(prompt="test")

    assert text == "The actual answer."
    assert usage["thinking"] == "internal reasoning"


def test_generate_think_kwarg_passed_to_client(ollama_service):
    """think=True is forwarded as a keyword argument to client.chat()."""
    ollama_service.client.chat = Mock(return_value=_chat_response("ok"))

    ollama_service.generate(prompt="test", think=True)

    call_kwargs = ollama_service.client.chat.call_args[1]
    assert call_kwargs.get("think") is True


def test_generate_no_think_kwarg_when_none(ollama_service):
    """think kwarg is omitted from client.chat() when think=None."""
    ollama_service.client.chat = Mock(return_value=_chat_response("ok"))

    ollama_service.generate(prompt="test", think=None)

    call_kwargs = ollama_service.client.chat.call_args[1]
    assert "think" not in call_kwargs


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
