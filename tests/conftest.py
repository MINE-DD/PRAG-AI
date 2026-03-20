import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend to path for local testing
backend_path = Path(__file__).parent / "backend"
if not backend_path.exists():
    backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


@pytest.fixture(scope="session", autouse=True)
def mock_config():
    """Mock the config loading at the module level to avoid needing config.yaml"""
    mock_config_dict = {
        "models": {"embedding": "nomic-embed-text:latest"},
        "chunking": {"size": 500},
    }
    with patch("app.core.config.load_config", return_value=mock_config_dict):
        yield
