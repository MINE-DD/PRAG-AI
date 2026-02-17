import yaml
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings, load_config
from app.services.ollama_service import OllamaService

router = APIRouter()

CONFIG_PATH = Path("config.yaml")


@router.get("/ollama/models")
def list_ollama_models():
    """List models available in Ollama."""
    try:
        client = OllamaService(url=settings.ollama_url)
        response = client.client.list()
        result = []
        for m in response.models:
            result.append({
                "name": m.model,
                "size": m.size,
            })
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {e}")


@router.get("/settings")
def get_settings():
    """Get current application settings."""
    config = load_config(str(CONFIG_PATH))
    return {
        "embedding_model": config["models"]["embedding"],
        "llm_model": config["models"]["llm"]["model"],
        "chunk_size": config["chunking"]["size"],
        "chunk_overlap": config["chunking"]["overlap"],
        "chunk_mode": config["chunking"].get("mode", "characters"),
        "top_k": config["retrieval"]["top_k"],
        "pdf_input_dir": settings.pdf_input_dir,
        "preprocessed_dir": settings.preprocessed_dir,
    }


class UpdateSettingsRequest(BaseModel):
    embedding_model: Optional[str] = None
    llm_model: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunk_mode: Optional[str] = None  # "characters" or "tokens"
    top_k: Optional[int] = None
    pdf_input_dir: Optional[str] = None
    preprocessed_dir: Optional[str] = None


@router.post("/settings")
def update_settings(request: UpdateSettingsRequest):
    """Update application settings. Writes to config.yaml."""
    config = load_config(str(CONFIG_PATH))

    if request.embedding_model is not None:
        config["models"]["embedding"] = request.embedding_model
    if request.llm_model is not None:
        config["models"]["llm"]["model"] = request.llm_model
    if request.chunk_size is not None:
        config["chunking"]["size"] = request.chunk_size
    if request.chunk_overlap is not None:
        config["chunking"]["overlap"] = request.chunk_overlap
    if request.chunk_mode is not None:
        config["chunking"]["mode"] = request.chunk_mode
    if request.top_k is not None:
        config["retrieval"]["top_k"] = request.top_k

    # Write updated config
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Update env-based settings in memory
    if request.pdf_input_dir is not None:
        settings.pdf_input_dir = request.pdf_input_dir
    if request.preprocessed_dir is not None:
        settings.preprocessed_dir = request.preprocessed_dir

    return {"status": "ok", "message": "Settings updated."}
