"""Unit tests for HuggingFaceService.

All heavy optional dependencies (torch, transformers, PIL) are mocked so
these tests run in the standard CI environment without GPU or extra packages.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.huggingface_service import HuggingFaceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(**kwargs):
    return HuggingFaceService(
        model_id="test/model",
        embedding_model_id="test/embed",
        vlm_model_id=kwargs.get("vlm_model_id"),
    )


# ---------------------------------------------------------------------------
# _get_device
# ---------------------------------------------------------------------------

def test_get_device_cuda():
    with patch("torch.cuda.is_available", return_value=True):
        with patch("torch.backends.mps.is_available", return_value=False):
            assert HuggingFaceService._get_device() == "cuda"


def test_get_device_mps():
    with patch("torch.cuda.is_available", return_value=False):
        with patch("torch.backends.mps.is_available", return_value=True):
            assert HuggingFaceService._get_device() == "mps"


def test_get_device_cpu():
    with patch("torch.cuda.is_available", return_value=False):
        with patch("torch.backends.mps.is_available", return_value=False):
            assert HuggingFaceService._get_device() == "cpu"


# ---------------------------------------------------------------------------
# generate (text)
# ---------------------------------------------------------------------------

def test_generate_returns_assistant_content():
    svc = _make_service()
    mock_pipe = Mock(return_value=[{"generated_text": [{"role": "assistant", "content": "hello"}]}])
    svc._text_pipe = mock_pipe

    result = svc.generate(prompt="hi", system="be helpful")

    assert result == "hello"
    mock_pipe.assert_called_once()
    call_args = mock_pipe.call_args
    messages = call_args[0][0]
    assert messages[0] == {"role": "system", "content": "be helpful"}
    assert messages[1] == {"role": "user", "content": "hi"}


def test_generate_without_system():
    svc = _make_service()
    mock_pipe = Mock(return_value=[{"generated_text": [{"role": "assistant", "content": "ok"}]}])
    svc._text_pipe = mock_pipe

    result = svc.generate(prompt="test")

    messages = mock_pipe.call_args[0][0]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert result == "ok"


def test_generate_plain_string_output():
    """Pipeline returning a plain string (not list) is handled."""
    svc = _make_service()
    mock_pipe = Mock(return_value=[{"generated_text": "plain string"}])
    svc._text_pipe = mock_pipe

    result = svc.generate(prompt="hi")
    assert result == "plain string"


def test_generate_passes_temperature_and_max_tokens():
    svc = _make_service()
    mock_pipe = Mock(return_value=[{"generated_text": [{"role": "assistant", "content": "x"}]}])
    svc._text_pipe = mock_pipe

    svc.generate(prompt="hi", temperature=0.0, max_tokens=256)

    kwargs = mock_pipe.call_args[1]
    assert kwargs["max_new_tokens"] == 256
    assert kwargs["temperature"] == 0.0
    assert kwargs["do_sample"] is False


# ---------------------------------------------------------------------------
# generate_embedding
# ---------------------------------------------------------------------------

def test_generate_embedding_returns_list():
    svc = _make_service()

    mock_tokenizer = Mock()
    mock_tokenizer.return_value = {
        "input_ids": MagicMock(),
        "attention_mask": MagicMock(),
    }
    mock_model = Mock()

    # Simulate model output with last_hidden_state
    import torch
    fake_hidden = torch.zeros(1, 5, 384)
    fake_mask = torch.ones(1, 5)
    mock_model_output = Mock()
    mock_model_output.last_hidden_state = fake_hidden

    mock_model.return_value = mock_model_output
    mock_model.parameters.return_value = iter([torch.zeros(1)])

    svc._embed_tokenizer = mock_tokenizer
    svc._embed_model = mock_model

    with patch("torch.no_grad", return_value=MagicMock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=False))):
        with patch.object(svc, "_mean_pool", return_value=[0.1] * 384) as mock_pool:
            result = svc.generate_embedding("test text")

    assert isinstance(result, list)
    mock_pool.assert_called_once()


def test_generate_embeddings_batch():
    svc = _make_service()
    with patch.object(svc, "generate_embedding", return_value=[0.1] * 384) as mock_emb:
        results = svc.generate_embeddings_batch(["a", "b", "c"])

    assert len(results) == 3
    assert mock_emb.call_count == 3


# ---------------------------------------------------------------------------
# check_health
# ---------------------------------------------------------------------------

def test_check_health_true_when_pipe_loads():
    svc = _make_service()
    svc._text_pipe = Mock()  # already loaded
    assert svc.check_health() is True


def test_check_health_false_when_pipe_raises():
    svc = _make_service()

    with patch.object(svc, "_get_text_pipe", side_effect=RuntimeError("no GPU")):
        assert svc.check_health() is False


# ---------------------------------------------------------------------------
# generate_multimodal
# ---------------------------------------------------------------------------

def test_generate_multimodal_returns_content():
    svc = _make_service(vlm_model_id="test/vlm")
    mock_pipe = Mock(return_value=[{"generated_text": [{"role": "assistant", "content": "extracted text"}]}])
    svc._vlm_pipe = mock_pipe

    fake_image = Mock()
    result = svc.generate_multimodal(prompt="extract text", images=[fake_image])

    assert result == "extracted text"
    mock_pipe.assert_called_once()


def test_generate_multimodal_includes_system():
    svc = _make_service(vlm_model_id="test/vlm")
    mock_pipe = Mock(return_value=[{"generated_text": [{"role": "assistant", "content": "ok"}]}])
    svc._vlm_pipe = mock_pipe

    svc.generate_multimodal(prompt="p", images=[Mock()], system="sys prompt")

    messages = mock_pipe.call_args[0][0]
    assert messages[0] == {"role": "system", "content": "sys prompt"}


def test_get_vlm_pipe_raises_without_model_id():
    svc = HuggingFaceService(model_id="x", embedding_model_id="y", vlm_model_id=None)
    with pytest.raises(ValueError, match="vlm_model_id is not set"):
        svc._get_vlm_pipe()


# ---------------------------------------------------------------------------
# extract_from_image
# ---------------------------------------------------------------------------

def test_extract_from_image_calls_generate_multimodal():
    svc = _make_service(vlm_model_id="test/vlm")
    with patch.object(svc, "generate_multimodal", return_value="# Heading") as mock_gen:
        result = svc.extract_from_image(image=Mock())

    assert result == "# Heading"
    mock_gen.assert_called_once()
    call_kwargs = mock_gen.call_args[1]
    assert "images" in call_kwargs
