import re
from fastapi import APIRouter, HTTPException, Depends
from app.models.rag import RAGRequest
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.ollama_service import OllamaService
from app.services.citation_service import CitationService
from app.services.metadata_service import MetadataService
from app.services.sparse_embedding_service import SparseEmbeddingService
from app.services.api_keys_service import ApiKeysService
from app.services.prompt_service import PromptService, get_prompt_service
from app.core.config import settings, load_config

router = APIRouter()
_api_keys = ApiKeysService()

CANNOT_ANSWER_PHRASE = "Sorry, I do not know the answer for this"


def _get_llm_info(config: dict) -> dict:
    """Return provider/model metadata for display."""
    llm_cfg = config["models"]["llm"]
    provider = llm_cfg.get("type", "local")
    if provider == "anthropic":
        return {"provider": "anthropic", "model": llm_cfg.get("anthropic_model", "claude-opus-4-6")}
    if provider == "google":
        return {"provider": "google", "model": llm_cfg.get("google_model", "gemini-2.5-flash")}
    return {"provider": "local", "model": llm_cfg.get("model", "")}


def _get_llm_service(config: dict):
    """Return the appropriate LLM generation service based on config."""
    llm_cfg = config["models"]["llm"]
    provider = llm_cfg.get("type", "local")

    if provider == "anthropic":
        from app.services.anthropic_service import AnthropicService
        api_key = _api_keys.get_key("anthropic")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Anthropic API key not configured. Set it in Settings.",
            )
        model = llm_cfg.get("anthropic_model", "claude-opus-4-6")
        return AnthropicService(api_key=api_key, model=model)

    if provider == "google":
        from app.services.google_service import GoogleService
        api_key = _api_keys.get_key("google")
        if not api_key:
            raise HTTPException(
                status_code=503,
                detail="Google API key not configured. Set it in Settings.",
            )
        model = llm_cfg.get("google_model", "gemini-2.5-flash")
        return GoogleService(api_key=api_key, model=model)

    # Default: local Ollama
    return OllamaService(
        url=settings.ollama_url,
        model=llm_cfg["model"],
        embedding_model=config["models"]["embedding"],
    )


def _clean_context(text: str) -> str:
    """Remove numeric citation indices from text to prevent LLM confusion.

    Strips patterns like [2,3], (2), [7][8] that come from the original papers
    so they don't clash with our own citation keys.
    """
    # Remove parentheses containing comma-separated numbers, e.g. (2, 3, 11, 12)
    text = re.sub(r'\(\s*\d+(?:\s*,\s*\d+)*\s*\)', '', text)
    # Remove square brackets containing comma-separated numbers, e.g. [2, 3, 11, 12] or [7,32]
    text = re.sub(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', '', text)
    # Remove consecutive square-bracket numbers, e.g. [2][3][4]
    text = re.sub(r'(?:\[\d+\])+', '', text)
    # Remove standalone numbers in square brackets, e.g. [2], [3]
    text = re.sub(r'\[\d+\]', '', text)
    # Remove standalone numbers in parentheses followed by punctuation, e.g. (2)., (3),
    text = re.sub(r'\(\d+\)[\.\,]+', '', text)
    return text


def get_services():
    """Dependency to get services"""
    config = load_config("config.yaml")

    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    # Embeddings always use Ollama (local)
    ollama_service = OllamaService(
        url=settings.ollama_url,
        model=config["models"]["llm"]["model"],
        embedding_model=config["models"]["embedding"],
    )
    citation_service = CitationService()
    metadata_service = MetadataService(data_dir=settings.data_dir)
    sparse_embedding_service = SparseEmbeddingService()
    llm_service = _get_llm_service(config)
    llm_info = _get_llm_info(config)

    return collection_service, qdrant, ollama_service, citation_service, metadata_service, sparse_embedding_service, llm_service, llm_info


@router.post("/collections/{collection_id}/rag")
def rag_query(
    collection_id: str,
    rag_request: RAGRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """
    RAG query: retrieve relevant chunks and generate an answer.

    Supports hybrid search (dense + BM42 sparse) when the collection
    was created with search_type="hybrid" and use_hybrid=True is passed.
    """
    collection_service, qdrant, ollama, citation_service, metadata_service, sparse_embedding_service, llm_service, llm_info = services

    # Validate query text
    if not rag_request.query_text or not rag_request.query_text.strip():
        raise HTTPException(status_code=400, detail="Query text cannot be empty")

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Generate dense embedding for query
    query_embedding = ollama.generate_embedding(rag_request.query_text)

    # Generate sparse embedding if hybrid requested and supported
    sparse_vector = None
    use_hybrid = False
    if rag_request.use_hybrid and collection.search_type == "hybrid":
        sparse_vector = sparse_embedding_service.generate_sparse_embedding(rag_request.query_text)
        use_hybrid = True

    # Search Qdrant
    search_results = qdrant.search(
        collection_name=collection_id,
        query_vector=query_embedding,
        limit=rag_request.limit,
        paper_ids=rag_request.paper_ids,
        sparse_vector=sparse_vector,
        use_hybrid=use_hybrid,
    )

    # Format results and build citation key map
    results = []
    # Map paper_id → unique_id (citation key) for all retrieved chunks
    paper_citation_keys = {}  # paper_id → unique_id

    for result in search_results:
        paper_id = result.payload["paper_id"]
        unique_id = result.payload["unique_id"]
        paper_citation_keys[paper_id] = unique_id

        results.append({
            "chunk_text": result.payload["chunk_text"],
            "paper_id": paper_id,
            "unique_id": unique_id,
            "chunk_type": result.payload["chunk_type"],
            "page_number": result.payload["page_number"],
            "score": result.score,
            "metadata": result.payload.get("metadata", {})
        })

    # Load metadata for all cited papers upfront
    paper_metadata_map = {}  # paper_id → PaperMetadata
    for paper_id in paper_citation_keys:
        meta = metadata_service.get_paper_metadata(collection_id, paper_id)
        if meta:
            paper_metadata_map[paper_id] = meta

    # Generate a unified answer from the retrieved chunks using the LLM
    answer = ""
    if results:
        # Build context: each chunk tagged with its citation key
        context_parts = []
        for r in results:
            citation_key = r["unique_id"] or r["paper_id"]
            cleaned_text = _clean_context(r["chunk_text"])
            context_parts.append(
                f"--- Source: [{citation_key}] ---\n{cleaned_text}"
            )
        context = "\n\n".join(context_parts)

        # List all valid citation keys for the prompt
        valid_keys = sorted(set(paper_citation_keys.values()))
        keys_list = ", ".join(f"[{k}]" for k in valid_keys)

        word_target = rag_request.max_tokens
        try:
            rendered = prompt_service.render(
                "rag", rag_request.prompt_name,
                context=context,
                question=rag_request.query_text,
                word_target=word_target,
                keys_list=keys_list,
                cannot_answer_phrase=CANNOT_ANSWER_PHRASE,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        answer = llm_service.generate(prompt=rendered.user, system=rendered.system, temperature=0.3, max_tokens=rag_request.max_tokens)

        # Detect cannot-answer response
        if CANNOT_ANSWER_PHRASE.lower() in answer.lower():
            answer = (
                "The retrieved passages do not contain enough information to answer "
                "this question. Try broadening your query or selecting different papers."
            )

    # Always build citations for all retrieved papers
    citations = {}
    for paper_id, unique_id in paper_citation_keys.items():
        meta = paper_metadata_map.get(paper_id)
        if meta:
            citations[unique_id] = {
                "unique_id": meta.unique_id,
                "title": meta.title,
                "authors": meta.authors,
                "year": meta.year,
                "apa": citation_service.format_apa(meta),
                "bibtex": citation_service.format_bibtex(meta),
            }

    response = {
        "answer": answer,
        "results": results,
        "citations": citations,
        "llm_provider": llm_info["provider"],
        "llm_model": llm_info["model"],
    }

    return response
