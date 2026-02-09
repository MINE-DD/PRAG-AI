from pathlib import Path
from datetime import datetime, UTC
import uuid
import shutil
from typing import Optional
from app.models.collection import Collection
from app.services.qdrant_service import QdrantService
from app.core.config import settings


class CollectionService:
    """Service for managing collections"""

    def __init__(self, qdrant: QdrantService):
        self.qdrant = qdrant
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def create_collection(self, name: str, description: Optional[str] = None) -> Collection:
        """Create a new collection"""
        # Generate collection ID (sanitized name)
        collection_id = name.lower().replace(" ", "_")

        # Check if already exists
        collection_path = self.data_dir / collection_id
        if collection_path.exists():
            raise ValueError(
                f'Collection "{name}" already exists at {collection_path}. '
                f'Please use a different name or reprocess the existing collection.'
            )

        # Create directories
        collection_path.mkdir(parents=True)
        (collection_path / "pdfs").mkdir()
        (collection_path / "figures").mkdir()

        # Create Qdrant collection
        self.qdrant.create_collection(collection_id)

        return Collection(
            collection_id=collection_id,
            name=name,
            description=description
        )

    def list_collections(self) -> list[Collection]:
        """List all collections"""
        collections = []

        for path in self.data_dir.iterdir():
            if path.is_dir():
                # Count PDFs
                pdf_count = len(list((path / "pdfs").glob("*.pdf")))

                collections.append(Collection(
                    collection_id=path.name,
                    name=path.name.replace("_", " ").title(),
                    paper_count=pdf_count,
                    created_date=datetime.fromtimestamp(path.stat().st_ctime, tz=UTC),
                    last_updated=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                ))

        return collections

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a specific collection"""
        collection_path = self.data_dir / collection_id

        if not collection_path.exists():
            return None

        pdf_count = len(list((collection_path / "pdfs").glob("*.pdf")))

        return Collection(
            collection_id=collection_id,
            name=collection_id.replace("_", " ").title(),
            paper_count=pdf_count,
            created_date=datetime.fromtimestamp(collection_path.stat().st_ctime, tz=UTC),
            last_updated=datetime.fromtimestamp(collection_path.stat().st_mtime, tz=UTC)
        )

    def delete_collection(self, collection_id: str):
        """Delete collection (Qdrant only, keep files)"""
        # Delete from Qdrant
        if self.qdrant.collection_exists(collection_id):
            self.qdrant.delete_collection(collection_id)

    def delete_collection_files(self, collection_id: str):
        """Delete collection files (for testing)"""
        collection_path = self.data_dir / collection_id
        if collection_path.exists():
            shutil.rmtree(collection_path)
