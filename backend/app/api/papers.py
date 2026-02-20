import json
from fastapi import APIRouter, HTTPException, Depends
from pathlib import Path
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.core.config import settings

router = APIRouter()


def get_collection_service() -> CollectionService:
    """Dependency to get collection service"""
    qdrant = QdrantService(url=settings.qdrant_url)
    return CollectionService(qdrant=qdrant)


@router.get("/collections/{collection_id}/papers")
def list_papers(
    collection_id: str,
    collection_service: CollectionService = Depends(get_collection_service)
):
    """List all papers in a collection"""
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
                    "preprocessed_dir": data.get("preprocessed_dir"),
                    "source_pdf": data.get("source_pdf"),
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


@router.get("/collections/{collection_id}/papers/{paper_id}")
def get_paper_detail(
    collection_id: str,
    paper_id: str,
    collection_service: CollectionService = Depends(get_collection_service)
):
    """Get full metadata for a single paper in a collection (from collection metadata dir)."""
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    data_dir = Path(settings.data_dir)
    metadata_path = data_dir / collection_id / "metadata" / f"{paper_id}.json"
    if not metadata_path.exists():
        raise HTTPException(status_code=404, detail="Paper metadata not found in collection")

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    return data
