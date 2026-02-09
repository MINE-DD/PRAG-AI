from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pathlib import Path
import uuid
import shutil
from app.models.paper import PaperMetadata
from app.services.collection_service import CollectionService
from app.services.pdf_processor import PDFProcessor
from app.services.qdrant_service import QdrantService
from app.core.config import settings

router = APIRouter()


def get_services():
    """Dependency to get services"""
    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    pdf_processor = PDFProcessor()
    return collection_service, pdf_processor


@router.post("/collections/{collection_id}/papers")
async def upload_paper(
    collection_id: str,
    file: UploadFile = File(...),
    services: tuple = Depends(get_services)
):
    """Upload a PDF to a collection"""
    collection_service, pdf_processor = services

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

        # Process PDF to extract metadata
        result = pdf_processor.process_pdf(pdf_path, paper_id)
        metadata = result["metadata"]

        # Return response with collection_id included
        return {
            "paper_id": metadata.paper_id,
            "title": metadata.title,
            "authors": metadata.authors,
            "year": metadata.year,
            "unique_id": metadata.unique_id,
            "collection_id": collection_id
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

    # Get all PDFs in collection
    data_dir = Path(settings.data_dir)
    pdf_dir = data_dir / collection_id / "pdfs"

    papers = []
    for pdf_file in pdf_dir.glob("*.pdf"):
        # Extract paper_id from filename (uuid.pdf)
        paper_id = pdf_file.stem
        papers.append({
            "paper_id": paper_id,
            "filename": pdf_file.name
        })

    return papers
