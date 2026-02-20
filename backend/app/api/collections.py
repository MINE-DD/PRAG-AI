from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.core.config import settings
from app.models.collection import Collection, CreateCollectionRequest

router = APIRouter()


def get_collection_service():
    """Dependency to get collection service"""
    qdrant = QdrantService(url=settings.qdrant_url)
    return CollectionService(qdrant=qdrant)


@router.post("/collections", response_model=Collection)
def create_collection(request: CreateCollectionRequest):
    """Create a new collection"""
    service = get_collection_service()

    try:
        return service.create_collection(
            name=request.name,
            description=request.description
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("/collections", response_model=list[Collection])
def list_collections():
    """List all collections"""
    service = get_collection_service()
    return service.list_collections()


@router.get("/collections/{collection_id}", response_model=Collection)
def get_collection(collection_id: str):
    """Get a specific collection"""
    service = get_collection_service()
    collection = service.get_collection(collection_id)

    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection '{collection_id}' not found"
        )

    return collection


@router.delete("/collections/{collection_id}")
def delete_collection(collection_id: str):
    """Delete a collection (Qdrant + files on disk)"""
    service = get_collection_service()
    service.delete_collection(collection_id)
    service.delete_collection_files(collection_id)
    return {"success": True}
