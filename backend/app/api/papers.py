import json
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pathlib import Path
import uuid
import shutil
from app.models.paper import PaperMetadata
from app.services.collection_service import CollectionService
from app.services.pdf_processor import PDFProcessor
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService
from app.services.qdrant_service import QdrantService
from app.services.paper_service import PaperService
from app.core.config import settings, load_config

router = APIRouter()


def get_services():
    """Dependency to get services"""
    # Load config for model settings
    config = load_config("config.yaml")

    # Initialize services
    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    pdf_processor = PDFProcessor()
    chunking_service = ChunkingService(
        chunk_size=config["chunking"]["size"],
        overlap=config["chunking"]["overlap"]
    )
    ollama_service = OllamaService(
        url=settings.ollama_url,
        embedding_model=config["models"]["embedding"]
    )
    paper_service = PaperService(
        pdf_processor=pdf_processor,
        chunking_service=chunking_service,
        ollama_service=ollama_service,
        qdrant_service=qdrant
    )

    return collection_service, paper_service


@router.post("/collections/{collection_id}/papers")
async def upload_paper(
    collection_id: str,
    file: UploadFile = File(...),
    services: tuple = Depends(get_services)
):
    """Upload and process a PDF in a collection"""
    collection_service, paper_service = services

    # Validate file type
    if not file.content_type == "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Generate paper ID
    paper_id = str(uuid.uuid4())

    # Save PDF to collection's pdfs directory
    data_dir = Path(settings.data_dir)
    pdf_dir = data_dir / collection_id / "pdfs"
    pdf_path = pdf_dir / f"{paper_id}.pdf"

    try:
        # Save uploaded file
        with pdf_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        # Process PDF through full pipeline (extract, chunk, embed, store)
        result = paper_service.process_paper(
            collection_id=collection_id,
            paper_id=paper_id,
            pdf_path=pdf_path
        )
        metadata = result["metadata"]

        # Return response with collection_id and processing info
        return {
            "paper_id": metadata.paper_id,
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "unique_id": metadata.unique_id,
            "collection_id": collection_id,
            "chunks_created": result["chunks_created"],
            "status": "processed"
        }

    except Exception as e:
        # Clean up PDF if processing failed
        if pdf_path.exists():
            pdf_path.unlink()
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")


@router.get("/collections/{collection_id}/papers")
def list_papers(
    collection_id: str,
    services: tuple = Depends(get_services)
):
    """List all papers in a collection"""
    collection_service, _ = services

    # Check collection exists
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    data_dir = Path(settings.data_dir)
    seen_ids = set()
    papers = []

    # Check metadata/ dir first (new ingestion flow)
    metadata_dir = data_dir / collection_id / "metadata"
    if metadata_dir.exists():
        for json_file in sorted(metadata_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                paper_id = data.get("paper_id", json_file.stem)
                seen_ids.add(paper_id)
                papers.append({
                    "paper_id": paper_id,
                    "filename": data.get("source_pdf", f"{paper_id}.md"),
                    "title": data.get("title"),
                    "authors": data.get("authors", []),
                    "unique_id": data.get("unique_id", ""),
                })
            except (json.JSONDecodeError, KeyError):
                continue

    # Also check PDFs dir (legacy flow)
    pdf_dir = data_dir / collection_id / "pdfs"
    if pdf_dir.exists():
        for pdf_file in pdf_dir.glob("*.pdf"):
            paper_id = pdf_file.stem
            if paper_id not in seen_ids:
                papers.append({
                    "paper_id": paper_id,
                    "filename": pdf_file.name,
                })

    return papers
