# tests/integration/test_settings_api.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from unittest.mock import patch

import pytest
import yaml
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    return TestClient(app)


def test_get_settings_includes_zotero_fields(client):
    with patch("app.api.settings._api_keys") as mock_keys:
        mock_keys.has_key.side_effect = lambda p: p == "anthropic"
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
