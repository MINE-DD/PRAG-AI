from docling.document_converter import DocumentConverter
from pathlib import Path
from typing import Optional
import re
from app.models.paper import PaperMetadata


class PDFProcessor:
    """Service for processing PDFs with Docling"""

    def __init__(self):
        self.converter = DocumentConverter()

    def generate_unique_id(
        self,
        title: Optional[str],
        authors: Optional[list[str]],
        year: Optional[int]
    ) -> str:
        """
        Generate human-readable unique ID from paper metadata.
        Format: FirstAuthorLastNameTitleWordsYear
        """
        parts = []

        # Add first author last name
        if authors and len(authors) > 0:
            author = authors[0].split()[-1]  # Last word is last name
            author = re.sub(r'[^a-zA-Z]', '', author)  # Remove non-letters
            parts.append(author)

        # Add first 1-2 words from title
        if title:
            title_words = title.split()[:2]
            title_part = ''.join(w.capitalize() for w in title_words)
            title_part = re.sub(r'[^a-zA-Z]', '', title_part)
            parts.append(title_part)

        # Add year
        if year:
            parts.append(str(year))

        # Fallback
        if not parts:
            return "UnknownPaper"

        return ''.join(parts)

    def extract_metadata(self, doc, paper_id: str) -> PaperMetadata:
        """
        Extract metadata from Docling document.

        Args:
            doc: Docling document object
            paper_id: Unique paper identifier

        Returns:
            PaperMetadata object
        """
        # Extract basic metadata
        title = getattr(doc, 'title', None) or "Untitled"
        authors = getattr(doc, 'authors', []) or []
        abstract = getattr(doc, 'abstract', None)
        publication_date = getattr(doc, 'publication_date', None)

        # Extract year from publication date
        year = None
        if publication_date:
            year_match = re.search(r'\d{4}', str(publication_date))
            if year_match:
                year = int(year_match.group())

        # Generate unique ID
        unique_id = self.generate_unique_id(title, authors, year)

        return PaperMetadata(
            paper_id=paper_id,
            title=title,
            authors=authors,
            year=year,
            abstract=abstract,
            unique_id=unique_id,
            publication_date=publication_date
        )

    def process_pdf(self, pdf_path: Path, paper_id: str) -> dict:
        """
        Process PDF and extract all content.

        Args:
            pdf_path: Path to PDF file
            paper_id: Unique paper identifier

        Returns:
            Dictionary with metadata, text, tables, figures
        """
        # Convert PDF
        result = self.converter.convert(str(pdf_path))
        doc = result.document

        # Extract metadata
        metadata = self.extract_metadata(doc, paper_id)

        # Extract text content
        text_content = doc.export_to_text()

        # TODO: Extract tables and figures (Phase 4.3)

        return {
            "metadata": metadata,
            "text": text_content,
            "tables": [],
            "figures": []
        }
