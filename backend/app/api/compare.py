from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.ollama_service import OllamaService
from app.services.metadata_service import MetadataService
from app.core.config import settings, load_config

router = APIRouter()


class CompareRequest(BaseModel):
    """Request to compare papers"""
    paper_ids: list[str] = Field(..., min_length=2, description="Paper IDs to compare (min 2)")
    aspect: str = Field(default="all", description="Aspect to compare: methodology, findings, or all")


class CompareResponse(BaseModel):
    """Response with paper comparison"""
    comparison: str = Field(..., description="Generated comparison")
    paper_ids: list[str] = Field(..., description="Papers that were compared")
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


@router.post("/collections/{collection_id}/compare", response_model=CompareResponse)
def compare_papers(
    collection_id: str,
    request: CompareRequest,
    services: tuple = Depends(get_services)
):
    """
    Compare multiple papers to identify similarities and differences.

    Args:
        collection_id: Collection containing the papers
        request: Paper IDs to compare and optional aspect filter

    Returns:
        Detailed comparison with similarities and differences
    """
    collection_service, qdrant, ollama, metadata_service = services

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
        dummy_embedding = [0.0] * 1024
        chunks = qdrant.search(
            collection_name=collection_id,
            query_vector=dummy_embedding,
            limit=50,  # Get up to 50 chunks per paper
            paper_ids=[paper_id]
        )

        # Store chunks for this paper
        paper_chunks = [chunk.payload["chunk_text"] for chunk in chunks]
        papers_content[paper_id] = "\n\n".join(paper_chunks[:10])  # Limit to 10 chunks per paper

    # Build comparison prompt based on aspect
    aspect_prompts = {
        "methodology": "Focus specifically on comparing the research methodologies, experimental designs, and approaches used.",
        "findings": "Focus specifically on comparing the key findings, results, and conclusions.",
        "all": "Compare all aspects including methodologies, findings, and implications."
    }

    aspect_instruction = aspect_prompts.get(request.aspect, aspect_prompts["all"])

    # Create labeled content for each paper
    paper_sections = []
    for i, paper_id in enumerate(request.paper_ids):
        paper_label = f"Paper {chr(65 + i)}"  # A, B, C, etc.
        if paper_id in papers_content:
            paper_sections.append(f"{paper_label} ({paper_id}):\n{papers_content[paper_id]}")

    combined_content = "\n\n---\n\n".join(paper_sections)

    prompt = f"""Compare the following {len(request.paper_ids)} research papers. {aspect_instruction}

{combined_content}

Provide a structured comparison covering:
1. **Similarities**: What do these papers have in common?
2. **Differences**: How do they differ in approach, methods, or conclusions?
3. **Key Insights**: What can we learn from comparing these papers?

Be specific and reference the papers by their labels (Paper A, Paper B, etc.)."""

    # Generate comparison using LLM
    comparison = ollama.generate(prompt=prompt, temperature=0.3)

    return CompareResponse(
        comparison=comparison,
        paper_ids=request.paper_ids,
        papers=papers_metadata
    )
