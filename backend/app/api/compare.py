from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.metadata_service import MetadataService
from app.services.prompt_service import PromptService, get_prompt_service
from app.core.config import settings, load_config
from app.api.rag import _get_llm_service, _get_llm_info

router = APIRouter()

SEARCH_CHUNKS_LIMIT = 50  # Max chunks to retrieve per paper for comparison
USE_CHUNKS_LIMIT = 10  # Limit chunks included in prompt to avoid token overload


class CompareRequest(BaseModel):
    """Request to compare papers"""
    paper_ids: list[str] = Field(..., min_length=2, description="Paper IDs to compare (min 2)")
    aspect: str = Field(default="all", description="Aspect to compare: methodology, findings, or all")
    max_tokens: Optional[int] = Field(default=None, description="Max tokens for generated text")
    prompt_name: str = Field(default="default", description="Prompt variant to use")


class CompareResponse(BaseModel):
    """Response with paper comparison"""
    comparison: str = Field(..., description="Generated comparison")
    paper_ids: list[str] = Field(..., description="Papers that were compared")
    papers: list[dict] = Field(default_factory=list, description="Paper metadata")
    llm_provider: str = Field(default="local", description="LLM provider used")
    llm_model: str = Field(default="", description="LLM model used")


def get_services():
    """Dependency to get services"""
    config = load_config("config.yaml")

    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    llm_service = _get_llm_service(config)
    llm_info = _get_llm_info(config)
    metadata_service = MetadataService(data_dir=settings.data_dir)

    return collection_service, qdrant, llm_service, llm_info, metadata_service


@router.post("/collections/{collection_id}/compare", response_model=CompareResponse)
def compare_papers(
    collection_id: str,
    request: CompareRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """
    Compare multiple papers to identify similarities and differences.

    Args:
        collection_id: Collection containing the papers
        request: Paper IDs to compare and optional aspect filter

    Returns:
        Detailed comparison with similarities and differences
    """
    collection_service, qdrant, llm_service, llm_info, metadata_service = services

    # Validate request
    if len(request.paper_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 papers are required for comparison")

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Gather chunks for each paper
    papers_metadata = []
    papers_content = {}

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

        # Get chunks for this paper
        vector_size = qdrant.get_vector_size(collection_id)
        dummy_embedding = [0.0] * vector_size
        chunks = qdrant.search(
            collection_name=collection_id,
            query_vector=dummy_embedding,
            limit=SEARCH_CHUNKS_LIMIT,
            paper_ids=[paper_id]
        )

        # Store chunks for this paper
        paper_chunks = [chunk.payload["chunk_text"] for chunk in chunks]
        papers_content[paper_id] = "\n\n".join(paper_chunks[:USE_CHUNKS_LIMIT])  # Limit to USE_CHUNKS_LIMIT chunks per paper to avoid token overload

    # Build aspect instruction and labeled content
    aspect_prompts = {
        "methodology":    "Focus specifically on comparing the research methodologies, experimental designs, and approaches used.",
        "findings":       "Focus specifically on comparing the key findings, results, and conclusions.",
        "results":        "Focus specifically on comparing the key results, findings, and conclusions reported.",
        "limitations":    "Focus specifically on comparing the limitations, weaknesses, and constraints acknowledged by each study.",
        "contributions":  "Focus specifically on comparing the novel contributions, innovations, and impact claimed by each paper.",
        "all":            "Compare all aspects including methodologies, findings, contributions, limitations, and implications.",
    }
    aspect_instruction = aspect_prompts.get(request.aspect, aspect_prompts["all"])

    paper_sections = []
    papers_info_parts = []
    meta_by_id = {m["paper_id"]: m for m in papers_metadata}

    for i, paper_id in enumerate(request.paper_ids):
        paper_label = f"Paper {chr(65 + i)}"  # A, B, C, etc.
        if paper_id in papers_content:
            paper_sections.append(f"{paper_label}:\n{papers_content[paper_id]}")
        meta = meta_by_id.get(paper_id)
        if meta:
            authors = meta["authors"][:3]
            authors_str = ", ".join(authors) + (" et al." if len(meta["authors"]) > 3 else "")
            year_str = f" ({meta['year']})" if meta.get("year") else ""
            papers_info_parts.append(f"{paper_label}: \"{meta['title']}\"{year_str} — {authors_str}")
        else:
            papers_info_parts.append(f"{paper_label}: {paper_id}")

    combined_content = "\n\n---\n\n".join(paper_sections)
    papers_info = "\n".join(papers_info_parts)

    # Render prompt via PromptService
    try:
        rendered = prompt_service.render(
            "compare", request.prompt_name,
            combined_content=combined_content,
            paper_count=len(request.paper_ids),
            aspect_instruction=aspect_instruction,
            papers_info=papers_info,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Generate comparison using LLM
    comparison = llm_service.generate(prompt=rendered.user, system=rendered.system, temperature=0.3, max_tokens=request.max_tokens)

    return CompareResponse(
        comparison=comparison,
        paper_ids=request.paper_ids,
        papers=papers_metadata,
        llm_provider=llm_info["provider"],
        llm_model=llm_info["model"],
    )
