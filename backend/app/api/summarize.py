
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.rag import _get_llm_info, _get_llm_service
from app.core.config import load_config, settings
from app.services.collection_service import CollectionService
from app.services.metadata_service import MetadataService
from app.services.prompt_service import PromptService, get_prompt_service
from app.services.qdrant_service import QdrantService

router = APIRouter()


class SummarizeRequest(BaseModel):
    """Request to summarize papers"""

    paper_ids: list[str] = Field(
        ..., min_length=1, description="Paper IDs to summarize"
    )
    max_tokens: int | None = Field(
        default=None, description="Max tokens for generated text"
    )
    prompt_name: str = Field(default="default", description="Prompt variant to use")


class SummarizeResponse(BaseModel):
    """Response with paper summary"""

    summary: str = Field(..., description="Generated summary")
    paper_ids: list[str] = Field(..., description="Papers that were summarized")
    papers: list[dict] = Field(default_factory=list, description="Paper metadata")


def get_services():
    """Dependency to get services"""
    config = load_config("config.yaml")

    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    metadata_service = MetadataService(data_dir=settings.data_dir)
    llm_service = _get_llm_service(config)
    llm_info = _get_llm_info(config)

    return collection_service, qdrant, metadata_service, llm_service, llm_info


@router.post("/collections/{collection_id}/summarize", response_model=SummarizeResponse)
def summarize_papers(
    collection_id: str,
    request: SummarizeRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """
    Generate a summary of one or more papers.

    Args:
        collection_id: Collection containing the papers
        request: Paper IDs to summarize

    Returns:
        Generated summary with paper metadata
    """
    collection_service, qdrant, metadata_service, llm_service, llm_info = services

    # Validate request
    if not request.paper_ids:
        raise HTTPException(status_code=400, detail="At least one paper_id is required")

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Gather all chunks for the specified papers
    all_chunks = []
    papers_metadata = []

    for paper_id in request.paper_ids:
        # Get paper metadata
        metadata = metadata_service.get_paper_metadata(collection_id, paper_id)
        if metadata:
            papers_metadata.append(
                {
                    "paper_id": paper_id,
                    "title": metadata.title,
                    "authors": metadata.authors,
                    "year": metadata.year,
                    "unique_id": metadata.unique_id,
                }
            )

        # Search for all chunks from this paper (use zero vector to get all)
        vector_size = qdrant.get_vector_size(collection_id)
        dummy_embedding = [0.0] * vector_size
        chunks = qdrant.search(
            collection_name=collection_id,
            query_vector=dummy_embedding,
            limit=100,  # Get up to 100 chunks per paper
            paper_ids=[paper_id],
        )

        for chunk in chunks:
            all_chunks.append(chunk.payload["chunk_text"])

    # Combine all chunks into context
    context = "\n\n".join(
        all_chunks[:20]
    )  # Limit to first 20 chunks to avoid token limits

    # Render prompt via PromptService
    try:
        rendered = prompt_service.render(
            "summarize",
            request.prompt_name,
            context=context,
            paper_count=len(request.paper_ids),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Generate summary using LLM
    summary = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
        max_tokens=request.max_tokens,
    )

    return SummarizeResponse(
        summary=summary, paper_ids=request.paper_ids, papers=papers_metadata
    )
