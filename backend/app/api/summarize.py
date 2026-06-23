import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
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
    summary, _ = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
        max_tokens=request.max_tokens,
    )

    return SummarizeResponse(
        summary=summary, paper_ids=request.paper_ids, papers=papers_metadata
    )


class SinglePaperSummaryResponse(BaseModel):
    summary: str
    method: str  # "markdown" or "rag"


@router.get(
    "/collections/{collection_id}/papers/{paper_id}/summarize",
    response_model=SinglePaperSummaryResponse,
)
def summarize_single_paper(
    collection_id: str,
    paper_id: str,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """Summarize a single paper by reading its markdown or falling back to Qdrant chunks."""
    collection_service, qdrant, metadata_service, llm_service, llm_info = services

    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    data_dir = Path(settings.data_dir)
    meta_path = data_dir / collection_id / "metadata" / f"{paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Paper not found")
    paper_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    config = load_config("config.yaml")
    llm_cfg = config.get("models", {}).get("llm", {})
    max_allowed = llm_cfg.get("num_context_tokens") or llm_cfg.get("max_allowed_tokens") or 8192
    # Cap at 6000 tokens worth of chars — local models choke on larger contexts
    practical_limit = max(int(max_allowed * 0.6), 6000)
    char_budget = int(practical_limit * 4 * 0.8)

    context: str | None = None
    method = "rag"

    preprocessed_dir = paper_meta.get("preprocessed_dir")
    source_pdf = paper_meta.get("source_pdf")
    if preprocessed_dir and source_pdf:
        stem = Path(source_pdf).stem
        md_path = Path(settings.preprocessed_dir) / preprocessed_dir / f"{stem}.md"
        if md_path.exists():
            context = md_path.read_text(encoding="utf-8")[:char_budget]
            method = "markdown"

    if context is None:
        chunks = qdrant.get_chunks_for_paper(collection_id, paper_id, limit=10)
        if not chunks:
            raise HTTPException(status_code=404, detail="No content found for paper")
        context = "\n\n".join(c.payload["chunk_text"] for c in chunks)[:char_budget]

    rendered = prompt_service.render("summarize", "academic_paper", context=context)
    summary, _ = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
    )

    return SinglePaperSummaryResponse(summary=summary, method=method)


def _parse_sections(
    text: str, max_sections: int = 50, min_body_chars: int = 150
) -> list[tuple[str, str]]:
    """Split markdown into [(heading, body)] pairs by H1/H2 headings."""
    pattern = re.compile(r"^(#{1,2} .+)$", re.MULTILINE)
    parts = pattern.split(text)

    sections: list[tuple[str, str]] = []

    for i in range(1, len(parts), 2):
        heading = re.sub(r"^#+\s*", "", parts[i]).strip()
        body = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if len(body) >= min_body_chars:
            sections.append((heading, body))

    return sections[:max_sections]


@router.get("/collections/{collection_id}/papers/{paper_id}/summarize/stream")
def summarize_single_paper_stream(
    collection_id: str,
    paper_id: str,
    max_sentences: int = 3,
    filter_sections: str = "",
    summary_format: str = "prose",
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """Stream section-by-section summaries of a paper as SSE."""
    collection_service, qdrant, metadata_service, llm_service, llm_info = services

    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    data_dir = Path(settings.data_dir)
    meta_path = data_dir / collection_id / "metadata" / f"{paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Paper not found")
    paper_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    sections: list[tuple[str, str]] = []
    method = "rag"

    preprocessed_dir = paper_meta.get("preprocessed_dir")
    source_pdf = paper_meta.get("source_pdf")
    if preprocessed_dir and source_pdf:
        stem = Path(source_pdf).stem
        md_path = Path(settings.preprocessed_dir) / preprocessed_dir / f"{stem}.md"
        if md_path.exists():
            sections = _parse_sections(md_path.read_text(encoding="utf-8"))
            method = "markdown"

    if not sections:
        chunks = qdrant.get_chunks_for_paper(collection_id, paper_id, limit=10)
        if not chunks:
            raise HTTPException(status_code=404, detail="No content found for paper")
        sections = [
            (f"Chunk {i + 1}", c.payload["chunk_text"]) for i, c in enumerate(chunks)
        ]
        method = "rag"

    if filter_sections:
        allowed = {s.strip() for s in filter_sections.split(",") if s.strip()}
        # Re-parse without the body-length filter so explicitly selected short
        # sections are not silently dropped.
        if preprocessed_dir and source_pdf:
            stem = Path(source_pdf).stem
            md_path = Path(settings.preprocessed_dir) / preprocessed_dir / f"{stem}.md"
            if md_path.exists():
                sections = _parse_sections(
                    md_path.read_text(encoding="utf-8"), min_body_chars=0
                )
        sections = [(h, b) for h, b in sections if h in allowed]

    if summary_format == "bullets":
        format_instruction = f"Write as exactly {max_sentences} concise bullet points, one per line starting with -."
    else:
        format_instruction = f"Write exactly {max_sentences} sentences in prose."

    # 2000 tokens ≈ 8000 chars — safe for any local model per section
    section_char_limit = 8000

    def generate():
        headings = [h for h, _ in sections]
        yield f"data: {json.dumps({'type': 'toc', 'headings': headings, 'count': len(sections), 'method': method})}\n\n"

        for i, (heading, body) in enumerate(sections):
            try:
                rendered = prompt_service.render(
                    "summarize",
                    "section",
                    heading=heading,
                    context=body[:section_char_limit],
                    format_instruction=format_instruction,
                )
                content, _ = llm_service.generate(
                    prompt=rendered.user,
                    system=rendered.system,
                    temperature=0.3,
                )
                yield f"data: {json.dumps({'type': 'section', 'heading': heading, 'index': i + 1, 'total': len(sections), 'content': content})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class SummariesInput(BaseModel):
    summaries: list[dict]


class TextResponse(BaseModel):
    content: str


def _summaries_to_text(summaries: list[dict]) -> str:
    return "\n\n".join(
        f"**{s.get('heading', '')}**\n{s.get('content', '')}" for s in summaries
    )


@router.post(
    "/collections/{collection_id}/papers/{paper_id}/structured-abstract",
    response_model=TextResponse,
)
def generate_structured_abstract(
    collection_id: str,
    paper_id: str,
    body: SummariesInput,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
) -> TextResponse:
    """Generate a structured abstract from provided section summaries."""
    _, _, _, llm_service, _ = services
    rendered = prompt_service.render(
        "summarize", "structured_abstract", summaries=_summaries_to_text(body.summaries)
    )
    content, _ = llm_service.generate(
        prompt=rendered.user, system=rendered.system, temperature=0.3
    )
    return TextResponse(content=content)


@router.post(
    "/collections/{collection_id}/papers/{paper_id}/explicit-claims",
    response_model=TextResponse,
)
def generate_explicit_claims(
    collection_id: str,
    paper_id: str,
    body: SummariesInput,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
) -> TextResponse:
    """Extract explicit claims the paper makes about its own contributions."""
    _, _, _, llm_service, _ = services
    rendered = prompt_service.render(
        "summarize", "explicit_claims", summaries=_summaries_to_text(body.summaries)
    )
    content, _ = llm_service.generate(
        prompt=rendered.user, system=rendered.system, temperature=0.3
    )
    return TextResponse(content=content)


@router.post(
    "/collections/{collection_id}/papers/{paper_id}/assess-claims",
    response_model=TextResponse,
)
def generate_assess_claims(
    collection_id: str,
    paper_id: str,
    body: SummariesInput,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
) -> TextResponse:
    """Provide critical and contextual assessment of a paper's claims."""
    _, _, _, llm_service, _ = services
    rendered = prompt_service.render(
        "summarize", "assess_claims", summaries=_summaries_to_text(body.summaries)
    )
    content, _ = llm_service.generate(
        prompt=rendered.user, system=rendered.system, temperature=0.3
    )
    return TextResponse(content=content)
