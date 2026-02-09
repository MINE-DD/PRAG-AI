from pathlib import Path
from typing import Optional
from app.models.paper import PaperMetadata
from app.services.pdf_processor import PDFProcessor


class MetadataService:
    """Service for loading paper metadata"""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.pdf_processor = PDFProcessor()

    def get_paper_metadata(self, collection_id: str, paper_id: str) -> Optional[PaperMetadata]:
        """
        Load paper metadata from PDF file.

        Args:
            collection_id: Collection containing the paper
            paper_id: Paper identifier

        Returns:
            PaperMetadata if paper exists, None otherwise
        """
        pdf_path = self.data_dir / collection_id / "pdfs" / f"{paper_id}.pdf"

        if not pdf_path.exists():
            return None

        # Process PDF to extract metadata
        result = self.pdf_processor.process_pdf(pdf_path, paper_id)
        return result["metadata"]
