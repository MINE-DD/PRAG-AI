from fastapi import APIRouter
from backend.app.core.config import settings
from backend.app.services.qdrant_service import QdrantService
from backend.app.services.ollama_service import OllamaService

router = APIRouter()


@router.get("/health")
def health_check():
    """Check health of all services"""
    health_status = {
        "api": "ok",
        "qdrant": "error",
        "ollama": "error",
        "models": {
            "embedding": "unknown",
            "llm": "unknown"
        }
    }

    # Check Qdrant
    try:
        qdrant = QdrantService(url=settings.qdrant_url)
        if qdrant.client.get_collections():
            health_status["qdrant"] = "ok"
    except Exception:
        pass

    # Check Ollama
    try:
        ollama = OllamaService(url=settings.ollama_url)
        if ollama.check_health():
            health_status["ollama"] = "ok"
            health_status["models"]["embedding"] = "ok"
            health_status["models"]["llm"] = "ok"
    except Exception:
        pass

    return health_status
