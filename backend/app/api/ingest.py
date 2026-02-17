from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from app.services.ingestion_service import IngestionService
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService
from app.services.sparse_embedding_service import SparseEmbeddingService
from app.core.config import settings, load_config

router = APIRouter()


class ScanRequest(BaseModel):
    path: str


class CreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    preprocessed_path: str
    search_type: str = "dense"


class IngestFileRequest(BaseModel):
    markdown_file: str
    preprocessed_path: str
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    chunk_mode: Optional[str] = None  # "characters" or "tokens"


def get_ingestion_service(
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    chunk_mode: Optional[str] = None,
) -> IngestionService:
    config = load_config("config.yaml")
    chunking_service = ChunkingService(
        chunk_size=chunk_size or config["chunking"]["size"],
        overlap=chunk_overlap or config["chunking"]["overlap"],
        mode=chunk_mode or config["chunking"].get("mode", "characters"),
    )
    ollama_service = OllamaService(
        url=settings.ollama_url,
        embedding_model=config["models"]["embedding"],
    )
    qdrant_service = QdrantService(url=settings.qdrant_url)
    sparse_embedding_service = SparseEmbeddingService()
    return IngestionService(
        chunking_service=chunking_service,
        ollama_service=ollama_service,
        qdrant_service=qdrant_service,
        sparse_embedding_service=sparse_embedding_service,
    )


@router.post("/ingest/scan")
def scan_preprocessed(request: ScanRequest):
    """Validate that a preprocessed path has markdown files."""
    service = get_ingestion_service()
    try:
        result = service.scan_preprocessed(request.path)
        return {
            "path": request.path,
            "files": result["files"],
            "file_count": len(result["files"]),
            "total_pdfs": result["total_pdfs"],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/ingest/create")
def create_collection_and_scan(request: CreateRequest):
    """Create a Qdrant collection and return the file list for ingestion."""
    service = get_ingestion_service()

    # Generate collection_id from name
    collection_id = request.name.lower().replace(" ", "_")

    try:
        info = service.create_collection(
            collection_id=collection_id,
            name=request.name,
            description=request.description,
            search_type=request.search_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Scan the preprocessed directory
    try:
        result = service.scan_preprocessed(request.preprocessed_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "collection_id": collection_id,
        "collection_info": info,
        "files": result["files"],
        "file_count": len(result["files"]),
    }


@router.post("/ingest/{collection_id}/file")
def ingest_file(collection_id: str, request: IngestFileRequest):
    """Ingest a single markdown file into a collection."""
    service = get_ingestion_service(
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
        chunk_mode=request.chunk_mode,
    )

    # Check collection directory exists
    collection_path = Path(settings.data_dir) / collection_id
    if not collection_path.exists():
        raise HTTPException(status_code=404, detail=f"Collection '{collection_id}' not found")

    # Build full paths
    preprocessed_path = Path(request.preprocessed_path)
    stem = Path(request.markdown_file).stem
    md_path = preprocessed_path / request.markdown_file
    metadata_path = preprocessed_path / f"{stem}_metadata.json"

    try:
        result = service.ingest_file(
            collection_id=collection_id,
            md_path=str(md_path),
            metadata_path=str(metadata_path) if metadata_path.exists() else None,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion error: {str(e)}")
