from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from app.models.query import QueryRequest, QueryResponse, Source
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.ollama_service import OllamaService
from app.core.config import settings, load_config

router = APIRouter()


def get_services():
    """Dependency to get services"""
    config = load_config("config.yaml")

    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    ollama_service = OllamaService(
        url=settings.ollama_url,
        embedding_model=config["models"]["embedding"]
    )

    return collection_service, qdrant, ollama_service


@router.post("/collections/{collection_id}/query")
def query_collection(
    collection_id: str,
    query_request: QueryRequest,
    services: tuple = Depends(get_services)
):
    """
    Query a collection with semantic search.

    Args:
        collection_id: Collection to search
        query_request: Query parameters (query_text, paper_ids, limit)

    Returns:
        Search results with ranked chunks
    """
    collection_service, qdrant, ollama = services

    # Validate query text
    if not query_request.query_text or not query_request.query_text.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty")

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Generate embedding for query
    query_embedding = ollama.generate_embedding(query_request.query_text)

    # Search Qdrant
    search_results = qdrant.search(
        collection_name=collection_id,
        query_vector=query_embedding,
        limit=query_request.limit,
        paper_ids=query_request.paper_ids
    )

    # Format results
    results = []
    for result in search_results:
        results.append({
            "chunk_text": result.payload["chunk_text"],
            "paper_id": result.payload["paper_id"],
            "unique_id": result.payload["unique_id"],
            "chunk_type": result.payload["chunk_type"],
            "page_number": result.payload["page_number"],
            "score": result.score,
            "metadata": result.payload.get("metadata", {})
        })

    return {"results": results}
