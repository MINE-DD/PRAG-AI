from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.ollama_service import OllamaService
from app.services.metadata_service import MetadataService
from app.core.config import settings, load_config

router = APIRouter()


class SummarizeRequest(BaseModel):
    """Request to summarize papers"""
    paper_ids: list[str] = Field(..., min_length=1, description="Paper IDs to summarize")
    max_tokens: Optional[int] = Field(default=None, description="Max tokens for generated text")


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
    ollama_service = OllamaService(
        url=settings.ollama_url,
        model=config["models"]["llm"]["model"],
        embedding_model=config["models"]["embedding"]
    )
    metadata_service = MetadataService(data_dir=settings.data_dir)

    return collection_service, qdrant, ollama_service, metadata_service


@router.post("/collections/{collection_id}/summarize", response_model=SummarizeResponse)
def summarize_papers(
    collection_id: str,
    request: SummarizeRequest,
    services: tuple = Depends(get_services)
):
    """
    Generate a summary of one or more papers.

    Args:
        collection_id: Collection containing the papers
        request: Paper IDs to summarize

    Returns:
        Generated summary with paper metadata
    """
    collection_service, qdrant, ollama, metadata_service = services

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
            papers_metadata.append({
                "paper_id": paper_id,
                "title": metadata.title,
                "authors": metadata.authors,
                "year": metadata.year,
                "unique_id": metadata.unique_id
            })

        # Search for all chunks from this paper (use zero vector to get all)
        vector_size = qdrant.get_vector_size(collection_id)
        dummy_embedding = [0.0] * vector_size
        chunks = qdrant.search(
            collection_name=collection_id,
            query_vector=dummy_embedding,
            limit=100,  # Get up to 100 chunks per paper
            paper_ids=[paper_id]
        )

        for chunk in chunks:
            all_chunks.append(chunk.payload["chunk_text"])

    # Combine all chunks into context
    context = "\n\n".join(all_chunks[:20])  # Limit to first 20 chunks to avoid token limits

    # Build prompt for summarization
    if len(request.paper_ids) == 1:
        prompt = f"""Based on the following excerpts from a research paper, provide a comprehensive summary that covers:
1. The main research question or problem addressed
2. The methodology or approach used
3. Key findings or results
4. Significance and implications

Paper excerpts:
{context}

Please provide a clear, concise summary in 2-3 paragraphs."""
    else:
        prompt = f"""Based on the following excerpts from multiple research papers, provide a comprehensive summary that covers:
1. The common themes across papers
2. Key methodologies used
3. Main findings and results
4. Overall significance

Paper excerpts:
{context}

Please provide a clear, concise summary in 2-3 paragraphs."""

    # Generate summary using LLM
    summary = ollama.generate(prompt=prompt, temperature=0.3, max_tokens=request.max_tokens)

    return SummarizeResponse(
        summary=summary,
        paper_ids=request.paper_ids,
        papers=papers_metadata
    )
