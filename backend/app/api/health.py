from fastapi import APIRouter

from app.core.config import load_config, settings
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService

router = APIRouter()


@router.get("/health")
def health_check():
    """Check health of all services"""
    health_status = {
        "api": "ok",
        "qdrant": "error",
        "ollama": "error",
        "models": {"embedding": "unknown", "llm": "unknown"},
        "models_ready": False,
    }

    # Check Qdrant
    try:
        qdrant = QdrantService(url=settings.qdrant_url)
        if qdrant.client.get_collections():
            health_status["qdrant"] = "ok"
    except Exception:
        pass

    # Check Ollama and whether the configured models are actually pulled
    try:
        ollama = OllamaService(url=settings.ollama_url)
        if ollama.check_health():
            health_status["ollama"] = "ok"
            config = load_config("config.yaml")
            embedding_model = config["models"]["embedding"]
            llm_model = config["models"]["llm"]["model"]
            def _norm(name: str) -> str:
                return name if ":" in name else name + ":latest"

            pulled = {_norm(m.model) for m in ollama.client.list().models}
            emb_ok = _norm(embedding_model) in pulled
            llm_ok = _norm(llm_model) in pulled
            health_status["models"]["embedding"] = "ok" if emb_ok else "missing"
            health_status["models"]["llm"] = "ok" if llm_ok else "missing"
            health_status["models_ready"] = emb_ok and llm_ok
    except Exception:
        pass

    return health_status
