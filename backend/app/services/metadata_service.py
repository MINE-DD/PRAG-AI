import json
from pathlib import Path
from typing import Optional
from app.models.paper import PaperMetadata
from app.services.pdf_processor import PDFProcessor


class MetadataService:
    """Service for loading paper metadata from JSON files or PDF fallback."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self._pdf_processor = None

    @property
    def pdf_processor(self) -> PDFProcessor:
        """Lazy-load PDF processor only when needed for fallback."""
        if self._pdf_processor is None:
            self._pdf_processor = PDFProcessor()
        return self._pdf_processor

    def get_paper_metadata(self, collection_id: str, paper_id: str) -> Optional[PaperMetadata]:
        """
        Load paper metadata, preferring JSON file over PDF re-processing.

        Lookup order:
        1. /data/collections/{id}/metadata/{paper_id}.json (new ingestion flow)
        2. /data/collections/{id}/pdfs/{paper_id}.pdf (legacy fallback)
        """
        # Try JSON metadata first (fast path)
        json_path = self.data_dir / collection_id / "metadata" / f"{paper_id}.json"
        if json_path.exists():
            return self._load_from_json(json_path, paper_id)

        # Fallback: re-process PDF (legacy collections)
        pdf_path = self.data_dir / collection_id / "pdfs" / f"{paper_id}.pdf"
        if pdf_path.exists():
            result = self.pdf_processor.process_pdf(pdf_path, paper_id)
            return result["metadata"]

        return None

    def list_papers(self, collection_id: str) -> list[dict]:
        """List all papers in a collection from metadata JSON files."""
        metadata_dir = self.data_dir / collection_id / "metadata"
        papers = []

        if metadata_dir.exists():
            for json_file in sorted(metadata_dir.glob("*.json")):
                try:
                    data = json.loads(json_file.read_text(encoding="utf-8"))
                    papers.append({
                        "paper_id": data.get("paper_id", json_file.stem),
                        "title": data.get("title", json_file.stem),
                        "authors": data.get("authors", []),
                        "year": self._extract_year(data.get("publication_date")),
                        "unique_id": data.get("unique_id", ""),
                    })
                except (json.JSONDecodeError, KeyError):
                    continue

        return papers

    def _load_from_json(self, json_path: Path, paper_id: str) -> PaperMetadata:
        """Load PaperMetadata from a JSON file."""
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return PaperMetadata(
            paper_id=data.get("paper_id", paper_id),
            title=data.get("title", "Untitled"),
            authors=data.get("authors", []),
            year=self._extract_year(data.get("publication_date")),
            abstract=data.get("abstract"),
            unique_id=data.get("unique_id", paper_id),
            publication_date=data.get("publication_date"),
        )

    def _extract_year(self, publication_date) -> Optional[int]:
        """Extract year from publication date string."""
        if not publication_date:
            return None
        import re
        match = re.search(r"\d{4}", str(publication_date))
        return int(match.group()) if match else None
