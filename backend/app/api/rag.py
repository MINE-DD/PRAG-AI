import re
from fastapi import APIRouter, HTTPException, Depends
from app.models.rag import RAGRequest
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.services.ollama_service import OllamaService
from app.services.citation_service import CitationService
from app.services.metadata_service import MetadataService
from app.services.sparse_embedding_service import SparseEmbeddingService
from app.core.config import settings, load_config

router = APIRouter()

CANNOT_ANSWER_PHRASE = "Sorry, I do not know the answer for this"


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
    ollama_service = OllamaService(
        url=settings.ollama_url,
        model=config["models"]["llm"]["model"],
        embedding_model=config["models"]["embedding"]
    )
    citation_service = CitationService()
    metadata_service = MetadataService(data_dir=settings.data_dir)
    sparse_embedding_service = SparseEmbeddingService()

    return collection_service, qdrant, ollama_service, citation_service, metadata_service, sparse_embedding_service


@router.post("/collections/{collection_id}/rag")
def rag_query(
    collection_id: str,
    rag_request: RAGRequest,
    services: tuple = Depends(get_services)
):
    """
    RAG query: retrieve relevant chunks and generate an answer.

    Supports hybrid search (dense + BM42 sparse) when the collection
    was created with search_type="hybrid" and use_hybrid=True is passed.
    """
    collection_service, qdrant, ollama, citation_service, metadata_service, sparse_embedding_service = services

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

    # Format results
    results = []
    cited_papers = set()

    for result in search_results:
        paper_id = result.payload["paper_id"]
        cited_papers.add(paper_id)

        results.append({
            "chunk_text": result.payload["chunk_text"],
            "paper_id": paper_id,
            "unique_id": result.payload["unique_id"],
            "chunk_type": result.payload["chunk_type"],
            "page_number": result.payload["page_number"],
            "score": result.score,
            "metadata": result.payload.get("metadata", {})
        })

    # Generate a unified answer from the retrieved chunks using the LLM
    answer = ""
    if results:
        context_parts = []
        for r in results:
            source_label = r["unique_id"] or r["paper_id"]
            cleaned_text = _clean_context(r["chunk_text"])
            context_parts.append(f"[{source_label}]: {cleaned_text}")
        context = "\n\n".join(context_parts)

        word_target = rag_request.max_tokens
        prompt = (
            f"Based on the following excerpts from research papers, provide a clear and "
            f"coherent answer to the question. Cite sources using their labels in square "
            f"brackets (e.g. [AuthorTitle2024]). Aim for approximately {word_target} words.\n\n"
            f"The sources are only the ones IN THE COLLECTION, not general web knowledge, not the original papers." 
            f"I want you to answer based on the paper to which the retrieved excerpts belong to , not on your general knowledge.\n\n"
            f"If the context provides insufficient information to answer the question, "
            f'reply with "{CANNOT_ANSWER_PHRASE}"\n\n'
            f"Question: {rag_request.query_text}\n\n"
            f"Excerpts:\n{context}\n\n"
            f"Answer:"
        )
        answer = ollama.generate(prompt=prompt, temperature=0.3, max_tokens=rag_request.max_tokens)

        # Detect cannot-answer response
        if CANNOT_ANSWER_PHRASE.lower() in answer.lower():
            answer = (
                "The retrieved passages do not contain enough information to answer "
                "this question. Try broadening your query or selecting different papers."
            )

    response = {"answer": answer, "results": results}

    # Generate citations if requested
    if rag_request.include_citations:
        citations = {}
        for paper_id in cited_papers:
            metadata = metadata_service.get_paper_metadata(collection_id, paper_id)
            if metadata:
                citations[paper_id] = {
                    "unique_id": metadata.unique_id,
                    "title": metadata.title,
                    "authors": metadata.authors,
                    "year": metadata.year,
                    "apa": citation_service.format_apa(metadata),
                    "bibtex": citation_service.format_bibtex(metadata)
                }

        response["citations"] = citations

    return response
