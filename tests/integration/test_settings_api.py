# tests/integration/test_settings_api.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from unittest.mock import Mock, patch

import pytest
import yaml
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(app)


def test_get_settings_includes_zotero_fields(client):
    with patch("app.api.settings._api_keys") as mock_keys:
        mock_keys.has_key.side_effect = lambda p: p == "google"
        mock_keys.get_key.side_effect = lambda p: (
            "12345" if p == "zotero_user_id" else None
        )
        resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "zotero_user_id" in data
    assert data["zotero_user_id"] == "12345"
    assert "has_zotero_key" in data
    assert isinstance(data["has_zotero_key"], bool)


def test_post_settings_saves_zotero_user_id(client, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "models": {
                    "embedding": "nomic",
                    "llm": {"type": "local", "model": "llama3.2"},
                },
                "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
                "retrieval": {"top_k": 10},
            }
        )
    )
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys") as mock_keys,
    ):
        mock_keys.has_key.return_value = False
        resp = client.post("/settings", json={"zotero_user_id": "99887766"})
    assert resp.status_code == 200
    mock_keys.set_key.assert_any_call("zotero_user_id", "99887766")
    # config.yaml should NOT contain zotero section
    saved = yaml.safe_load(config_path.read_text())
    assert "zotero" not in saved


def test_post_settings_saves_zotero_key(client, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "models": {
                    "embedding": "nomic",
                    "llm": {"type": "local", "model": "llama3.2"},
                },
                "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
                "retrieval": {"top_k": 10},
            }
        )
    )
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys") as mock_keys,
    ):
        resp = client.post("/settings", json={"zotero_key": "secret_key_123"})
    assert resp.status_code == 200
    mock_keys.set_key.assert_called_once_with("zotero", "secret_key_123")


# ---------------------------------------------------------------------------
# GET /settings — new fields
# ---------------------------------------------------------------------------

_BASE_CONFIG = {
    "models": {
        "default_embedder": "nomic-embed-text",
        "default_llm": "gemma3:1b",
        "embedding": "mxbai-embed-large:latest",
        "max_embedder_tokens": 512,
        "llm": {"type": "local", "model": "gemma4:e2b", "max_allowed_tokens": 8192},
    },
    "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
    "retrieval": {"top_k": 10},
}


def test_get_settings_includes_default_model_fields(client, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(_BASE_CONFIG))
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys"),
    ):
        resp = client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default_embedder_model"] == "nomic-embed-text"
    assert data["default_llm_model"] == "gemma3:1b"
    assert data["embedding_context_length"] == 512
    assert data["llm_max_ctx"] == 8192


def test_get_settings_default_model_falls_back_to_active(client, tmp_path):
    """When default_embedder/default_llm are absent, active model names are returned."""
    cfg = {
        "models": {
            "embedding": "mxbai-embed-large:latest",
            "llm": {"type": "local", "model": "gemma4:e2b"},
        },
        "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
        "retrieval": {"top_k": 10},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(cfg))
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys"),
    ):
        resp = client.get("/settings")
    data = resp.json()
    assert data["default_embedder_model"] == "mxbai-embed-large:latest"
    assert data["default_llm_model"] == "gemma4:e2b"


# ---------------------------------------------------------------------------
# GET /ollama/models/{model}/context-length
# ---------------------------------------------------------------------------


def test_get_model_context_length_success(client):
    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_svc = Mock()
        mock_svc.client.show.return_value = Mock(capabilities=["embedding"])
        mock_svc.get_embedding_context_length.return_value = 768
        mock_cls.return_value = mock_svc
        resp = client.get("/ollama/models/nomic-embed-text/context-length")
    assert resp.status_code == 200
    data = resp.json()
    assert data["context_length"] == 768
    assert data["is_embedding_model"] is True


def test_get_model_context_length_generative_model(client):
    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_svc = Mock()
        mock_svc.client.show.return_value = Mock(capabilities=["completion"])
        mock_svc.get_llm_context_length.return_value = 4096
        mock_cls.return_value = mock_svc
        resp = client.get("/ollama/models/gemma3:1b/context-length")
    assert resp.status_code == 200
    assert resp.json()["is_embedding_model"] is False


def test_get_model_context_length_ollama_unreachable(client):
    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_cls.side_effect = Exception("connection refused")
        resp = client.get("/ollama/models/nomic-embed-text/context-length")
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# _fetch_embedding_max_tokens / _fetch_llm_context_length
# ---------------------------------------------------------------------------


def test_fetch_embedding_max_tokens_success():
    from app.api.settings import _fetch_embedding_max_tokens

    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_svc = Mock()
        mock_svc.get_embedding_context_length.return_value = 768
        mock_cls.return_value = mock_svc
        assert _fetch_embedding_max_tokens("nomic-embed-text") == 768


def test_fetch_embedding_max_tokens_fallback():
    from app.api.settings import _fetch_embedding_max_tokens

    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_cls.side_effect = Exception("timeout")
        assert _fetch_embedding_max_tokens("nomic-embed-text") == 512


def test_fetch_llm_max_tokens_success():
    from app.api.settings import _fetch_llm_context_length

    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_svc = Mock()
        mock_svc.get_llm_context_length.return_value = 4096
        mock_cls.return_value = mock_svc
        assert _fetch_llm_context_length("llama3.2") == 4096


def test_fetch_llm_max_tokens_fallback():
    from app.api.settings import _fetch_llm_context_length

    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_cls.side_effect = Exception("timeout")
        assert _fetch_llm_context_length("llama3.2") is None


# ---------------------------------------------------------------------------
# POST /settings — model-related writes
# ---------------------------------------------------------------------------


def _write_config(path, extra=None):
    cfg = {
        "models": {"embedding": "nomic", "llm": {"type": "local", "model": "llama3"}},
        "chunking": {"size": 500, "overlap": 100, "mode": "tokens"},
        "retrieval": {"top_k": 10},
    }
    if extra:
        cfg["models"].update(extra)
    path.write_text(yaml.dump(cfg))
    return path


def test_post_settings_writes_max_embedder_tokens(client, tmp_path):
    config_path = _write_config(tmp_path / "config.yaml")
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys"),
        patch("app.api.settings._fetch_embedding_max_tokens", return_value=768),
    ):
        resp = client.post("/settings", json={"embedding_model": "nomic-embed-text"})
    assert resp.status_code == 200
    assert (
        yaml.safe_load(config_path.read_text())["models"]["max_embedder_tokens"] == 768
    )


def test_post_settings_google_provider_sets_max_tokens(client, tmp_path):
    config_path = _write_config(tmp_path / "config.yaml")
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys"),
    ):
        resp = client.post("/settings", json={"llm_provider": "google"})
    assert resp.status_code == 200
    saved = yaml.safe_load(config_path.read_text())
    assert saved["models"]["llm"]["max_allowed_tokens"] == 100000


# ---------------------------------------------------------------------------
# llm_is_thinking_model — GET /settings
# ---------------------------------------------------------------------------


def test_get_settings_llm_is_thinking_model_true(client):
    """GET /settings returns llm_is_thinking_model=True for a thinking model."""
    with patch("app.api.settings._check_is_thinking_model", return_value=True):
        resp = client.get("/settings")
    assert resp.status_code == 200
    assert resp.json()["llm_is_thinking_model"] is True


def test_get_settings_llm_is_thinking_model_false(client):
    """GET /settings returns llm_is_thinking_model=False for a non-thinking model."""
    with patch("app.api.settings._check_is_thinking_model", return_value=False):
        resp = client.get("/settings")
    assert resp.status_code == 200
    assert resp.json()["llm_is_thinking_model"] is False


def test_check_is_thinking_model_true():
    """Returns True when 'thinking' is in Ollama model capabilities."""
    from app.api.settings import _check_is_thinking_model

    with patch("app.api.settings.OllamaService") as mock_cls:
        info = Mock()
        info.capabilities = ["thinking", "completion"]
        mock_cls.return_value.client.show.return_value = info
        assert _check_is_thinking_model("gemma4:e2b") is True


def test_check_is_thinking_model_false():
    """Returns False when 'thinking' is not in capabilities."""
    from app.api.settings import _check_is_thinking_model

    with patch("app.api.settings.OllamaService") as mock_cls:
        info = Mock()
        info.capabilities = ["completion"]
        mock_cls.return_value.client.show.return_value = info
        assert _check_is_thinking_model("llama3") is False


def test_check_is_thinking_model_ollama_unreachable():
    """Returns False gracefully when Ollama cannot be reached."""
    from app.api.settings import _check_is_thinking_model

    with patch("app.api.settings.OllamaService") as mock_cls:
        mock_cls.return_value.client.show.side_effect = Exception("unreachable")
        assert _check_is_thinking_model("gemma4:e2b") is False


def test_check_is_thinking_model_empty_model():
    """Returns False immediately for an empty model name (no Ollama call made)."""
    from app.api.settings import _check_is_thinking_model

    with patch("app.api.settings.OllamaService") as mock_cls:
        assert _check_is_thinking_model("") is False
        mock_cls.assert_not_called()


def test_post_settings_local_llm_fetches_max_tokens(client, tmp_path):
    config_path = _write_config(tmp_path / "config.yaml")
    with (
        patch("app.api.settings.CONFIG_PATH", config_path),
        patch("app.api.settings._api_keys"),
        patch("app.api.settings._fetch_llm_context_length", return_value=4096),
    ):
        resp = client.post("/settings", json={"llm_model": "llama3.2"})
    assert resp.status_code == 200
    saved = yaml.safe_load(config_path.read_text())
    assert saved["models"]["llm"]["max_allowed_tokens"] == 4096
