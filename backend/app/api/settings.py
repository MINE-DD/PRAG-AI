import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import load_config, settings
from app.services.api_keys_service import ApiKeysService
from app.services.ollama_service import OllamaService

router = APIRouter()

CONFIG_PATH = Path("config.yaml")
_api_keys = ApiKeysService()

GOOGLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite-preview",
]

RECOMMENDED_EMBEDDING_MODELS = [
    "all-minilm",
    "nomic-embed-text",
    "mxbai-embed-large",
    "embeddinggemma",
    "qwen3-embedding:4b",
]

RECOMMENDED_LLM_MODELS = [
    "gemma3:1b",
    "gemma4:e2b",
    "llama3.2",
    "phi3:mini",
    "mistral:7b",
    "qwen3:8b",
]


@router.get("/ollama/models")
def list_ollama_models():
    """List models available in Ollama, including their capabilities."""
    try:
        client = OllamaService(url=settings.ollama_url)
        response = client.client.list()
        result = []
        for m in response.models:
            try:
                info = client.client.show(m.model)
                capabilities = list(info.capabilities or [])
            except Exception:
                capabilities = []
            result.append(
                {
                    "name": m.model,
                    "size": m.size,
                    "capabilities": capabilities,
                }
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {e}")


@router.get("/ollama/models/{model:path}/context-length")
def get_model_context_length(model: str):
    """Return context length and capability info for a specific Ollama model."""
    try:
        svc = OllamaService(url=settings.ollama_url, embedding_model=model)
        info = svc.client.show(model)
        capabilities = info.capabilities or []
        context_length = svc.get_embedding_context_length()
        return {
            "model": model,
            "context_length": context_length,
            "capabilities": capabilities,
            "is_embedding_model": "embedding" in capabilities,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Cannot reach Ollama: {e}")


@router.get("/settings")
def get_settings():
    """Get current application settings.

    API keys are never returned — only a boolean 'has_key' indicator.
    """
    config = load_config(str(CONFIG_PATH))
    llm_cfg = config["models"]["llm"]

    from app.services.ollama_service import OllamaService

    ollama = OllamaService(
        url=settings.ollama_url,
        embedding_model=config["models"]["embedding"],
    )
    embedding_context_length = ollama.get_embedding_context_length()

    return {
        "embedding_model": config["models"]["embedding"],
        "embedding_context_length": embedding_context_length,
        "llm_model": llm_cfg["model"],
        "llm_provider": llm_cfg.get("type", "local"),
        "llm_max_allowed_tokens": llm_cfg.get("max_allowed_tokens", 8192),
        "google_model": llm_cfg.get("google_model", GOOGLE_MODELS[0]),
        "has_google_key": _api_keys.has_key("google"),
        "zotero_user_id": _api_keys.get_key("zotero_user_id") or "",
        "has_zotero_key": _api_keys.has_key("zotero"),
        "chunk_size": config["chunking"]["size"],
        "chunk_overlap": config["chunking"]["overlap"],
        "chunk_mode": config["chunking"].get("mode", "characters"),
        "top_k": config["retrieval"]["top_k"],
        "pdf_input_dir": settings.pdf_input_dir,
        "preprocessed_dir": settings.preprocessed_dir,
    }


@router.get("/settings/cloud-models")
def get_cloud_models():
    """Return the list of supported cloud model IDs and recommended Ollama models."""
    return {
        "google": GOOGLE_MODELS,
        "ollama_embedding": RECOMMENDED_EMBEDDING_MODELS,
        "ollama_llm": RECOMMENDED_LLM_MODELS,
    }


class PullModelRequest(BaseModel):
    model: str


@router.post("/ollama/pull")
def pull_ollama_model(request: PullModelRequest):
    """Pull an Ollama model, streaming download progress as SSE."""

    def generate():
        try:
            client = OllamaService(url=settings.ollama_url)
            for progress in client.client.pull(request.model, stream=True):
                payload = {"status": progress.status}
                if progress.completed and progress.total:
                    payload["completed"] = progress.completed
                    payload["total"] = progress.total
                yield f"data: {json.dumps(payload)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class UpdateSettingsRequest(BaseModel):
    embedding_model: str | None = None
    llm_model: str | None = None
    llm_provider: str | None = None  # "local", "google"
    google_model: str | None = None
    google_key: str | None = None  # write-only — never returned
    clear_google_key: bool = False
    zotero_user_id: str | None = None
    zotero_key: str | None = None  # write-only — never returned
    clear_zotero_key: bool = False
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    chunk_mode: str | None = None
    top_k: int | None = None


def _fetch_llm_max_tokens(model: str) -> int:
    """Return context length for a local Ollama LLM model, fallback 8192."""
    try:
        svc = OllamaService(url=settings.ollama_url, embedding_model=model)
        info = svc.client.show(model)
        modelinfo = info.modelinfo or {}
        for key, value in modelinfo.items():
            if key.endswith(".context_length"):
                return int(value)
    except Exception:
        pass
    return 8192


@router.post("/settings")
def update_settings(request: UpdateSettingsRequest):
    """Update application settings. Writes to config.yaml.

    API keys are stored in /data/api_keys.json (mounted volume) and are
    never echoed back in any response.
    """
    config = load_config(str(CONFIG_PATH))

    if request.embedding_model is not None:
        config["models"]["embedding"] = request.embedding_model
    if request.llm_model is not None:
        config["models"]["llm"]["model"] = request.llm_model
    if request.llm_provider is not None:
        config["models"]["llm"]["type"] = request.llm_provider
    if request.google_model is not None:
        config["models"]["llm"]["google_model"] = request.google_model

    # Update max_allowed_tokens whenever the LLM model or provider changes
    provider = request.llm_provider or config["models"]["llm"].get("type", "local")
    if provider == "google":
        config["models"]["llm"]["max_allowed_tokens"] = 100000
    elif request.llm_model is not None:
        config["models"]["llm"]["max_allowed_tokens"] = _fetch_llm_max_tokens(
            request.llm_model
        )
    if request.chunk_size is not None:
        config["chunking"]["size"] = request.chunk_size
    if request.chunk_overlap is not None:
        config["chunking"]["overlap"] = request.chunk_overlap
    if request.chunk_mode is not None:
        config["chunking"]["mode"] = request.chunk_mode
    if request.top_k is not None:
        config["retrieval"]["top_k"] = request.top_k

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    # Handle API keys — write-only, stored in data volume
    if request.clear_google_key:
        _api_keys.clear_key("google")
    elif request.google_key:
        _api_keys.set_key("google", request.google_key)

    if request.zotero_user_id is not None:
        if request.zotero_user_id.strip():
            _api_keys.set_key("zotero_user_id", request.zotero_user_id.strip())
        else:
            _api_keys.clear_key("zotero_user_id")

    if request.clear_zotero_key:
        _api_keys.clear_key("zotero")
    elif request.zotero_key:
        _api_keys.set_key("zotero", request.zotero_key)

    return {"status": "ok", "message": "Settings updated."}
