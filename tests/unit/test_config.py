import pytest
import sys
from pathlib import Path

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.core.config import Settings, load_config


def test_settings_from_env(monkeypatch):
    """Test Settings loaded from environment"""
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    monkeypatch.setenv("OLLAMA_URL", "http://localhost:11434")
    monkeypatch.setenv("DATA_DIR", "/tmp/data")

    settings = Settings()

    assert settings.qdrant_url == "http://localhost:6333"
    assert settings.ollama_url == "http://localhost:11434"
    assert settings.data_dir == "/tmp/data"


def test_load_config_from_yaml():
    """Test loading config.yaml"""
    config = load_config("config.yaml")

    assert "models" in config
    assert "chunking" in config
    assert config["models"]["embedding"] == "mxbai-embed-large"
    assert config["chunking"]["size"] == 500
