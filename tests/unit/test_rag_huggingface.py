"""Unit tests for the HuggingFace LLM branch in app.api.rag.

Tests _get_llm_service and _get_llm_info for type: huggingface config,
without starting FastAPI or connecting to Qdrant/Ollama.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.api.rag import _get_llm_info, _get_llm_service

# ---------------------------------------------------------------------------
# _get_llm_info
# ---------------------------------------------------------------------------


def test_get_llm_info_huggingface_uses_config_model():
    config = {
        "models": {
            "llm": {
                "type": "huggingface",
                "hf_model": "Qwen/Qwen2.5-7B-Instruct",
            }
        }
    }
    info = _get_llm_info(config)
    assert info["provider"] == "huggingface"
    assert info["model"] == "Qwen/Qwen2.5-7B-Instruct"


def test_get_llm_info_huggingface_falls_back_to_settings():
    config = {"models": {"llm": {"type": "huggingface"}}}
    info = _get_llm_info(config)
    assert info["provider"] == "huggingface"
    # Should be the settings default, whatever it is
    assert isinstance(info["model"], str)
    assert len(info["model"]) > 0


# ---------------------------------------------------------------------------
# _get_llm_service
# ---------------------------------------------------------------------------


def test_get_llm_service_huggingface_returns_huggingface_service():
    config = {
        "models": {
            "llm": {
                "type": "huggingface",
                "hf_model": "Qwen/Qwen2.5-3B-Instruct",
                "hf_embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            }
        }
    }

    mock_hf_instance = Mock()
    mock_hf_class = Mock(return_value=mock_hf_instance)

    with patch("app.api.rag.HuggingFaceService", mock_hf_class, create=True):
        with patch.dict(
            "sys.modules",
            {
                "app.services.huggingface_service": Mock(
                    HuggingFaceService=mock_hf_class
                )
            },
        ):
            # Patch the import inside the function
            with patch("builtins.__import__", wraps=__import__) as mock_import:

                def side_effect(name, *args, **kwargs):
                    if name == "app.services.huggingface_service":
                        m = Mock()
                        m.HuggingFaceService = mock_hf_class
                        return m
                    return __import__(name, *args, **kwargs)

                mock_import.side_effect = side_effect
                service = _get_llm_service(config)

    assert service is mock_hf_instance
    mock_hf_class.assert_called_once_with(
        model_id="Qwen/Qwen2.5-3B-Instruct",
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
    )


def test_get_llm_service_huggingface_uses_settings_defaults():
    """When hf_model/hf_embedding_model are absent, settings defaults are used."""
    config = {"models": {"llm": {"type": "huggingface"}}}

    mock_hf_instance = Mock()
    mock_hf_class = Mock(return_value=mock_hf_instance)

    def _fake_import(name, *args, **kwargs):
        if name == "app.services.huggingface_service":
            m = Mock()
            m.HuggingFaceService = mock_hf_class
            return m
        return __import__(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_fake_import):
        service = _get_llm_service(config)

    assert service is mock_hf_instance
    _, call_kwargs = mock_hf_class.call_args
    assert "model_id" in call_kwargs
    assert "embedding_model_id" in call_kwargs
