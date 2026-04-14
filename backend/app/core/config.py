from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment"""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://host.docker.internal:11434"
    data_dir: str = "/data/collections"
    pdf_input_dir: str = "/data/pdf_input"
    preprocessed_dir: str = "/data/preprocessed"
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    prompts_dir: str = "/app/prompts"
    hf_text_model: str = "Qwen/Qwen2.5-3B-Instruct"
    hf_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    hf_vlm_model: str = "Qwen/Qwen2-VL-2B-Instruct"


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        return yaml.safe_load(f)


# Global instances
settings = Settings()
config = load_config()
