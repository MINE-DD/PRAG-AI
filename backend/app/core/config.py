from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from pathlib import Path


class Settings(BaseSettings):
    """Application settings from environment"""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://host.docker.internal:11434"
    data_dir: str = "/data/collections"
    pdf_input_dir: str = "/data/pdf_input"
    preprocessed_dir: str = "/data/preprocessed"
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        return yaml.safe_load(f)


# Global instances
settings = Settings()
config = load_config()
