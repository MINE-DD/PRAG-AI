import json
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
        (collection_path / "metadata").mkdir()

        # Create Qdrant collection
        self.qdrant.create_collection(collection_id)

        return Collection(
            collection_id=collection_id,
            name=name,
            description=description
        )

    def _read_collection_info(self, collection_path: Path) -> dict:
        """Read collection_info.json for a collection directory."""
        info_path = collection_path / "collection_info.json"
        if info_path.exists():
            return json.loads(info_path.read_text(encoding="utf-8"))
        return {}

    def _count_papers(self, collection_path: Path) -> int:
        """Count papers in a collection by checking metadata/ then pdfs/ dir."""
        meta_dir = collection_path / "metadata"
        if meta_dir.is_dir():
            count = len(list(meta_dir.glob("*.json")))
            if count > 0:
                return count
        pdfs_dir = collection_path / "pdfs"
        if pdfs_dir.is_dir():
            return len(list(pdfs_dir.glob("*.pdf")))
        return 0

    def list_collections(self) -> list[Collection]:
        """List all collections"""
        collections = []

        for path in self.data_dir.iterdir():
            if path.is_dir():
                info = self._read_collection_info(path)
                collections.append(Collection(
                    collection_id=path.name,
                    name=info.get("name", path.name.replace("_", " ").title()),
                    paper_count=self._count_papers(path),
                    created_date=datetime.fromtimestamp(path.stat().st_ctime, tz=UTC),
                    last_updated=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
                    search_type=info.get("search_type", "dense"),
                ))

        return collections

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a specific collection"""
        collection_path = self.data_dir / collection_id

        if not collection_path.exists():
            return None

        info = self._read_collection_info(collection_path)
        return Collection(
            collection_id=collection_id,
            name=info.get("name", collection_id.replace("_", " ").title()),
            paper_count=self._count_papers(collection_path),
            created_date=datetime.fromtimestamp(collection_path.stat().st_ctime, tz=UTC),
            last_updated=datetime.fromtimestamp(collection_path.stat().st_mtime, tz=UTC),
            search_type=info.get("search_type", "dense"),
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
