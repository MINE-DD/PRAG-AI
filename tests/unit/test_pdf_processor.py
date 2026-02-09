import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from app.services.pdf_processor import PDFProcessor
from app.models.paper import PaperMetadata


@pytest.fixture
def pdf_processor():
    """Create PDFProcessor"""
    return PDFProcessor()


def test_generate_unique_id():
    """Test unique ID generation"""
    processor = PDFProcessor()

    title = "Attention Is All You Need"
    authors = ["Vaswani", "Shazeer"]
    year = 2017

    unique_id = processor.generate_unique_id(title, authors, year)

    assert "Vaswani" in unique_id
    assert "Attention" in unique_id
    assert "2017" in unique_id


def test_extract_metadata_from_doc():
    """Test metadata extraction from docling document"""
    processor = PDFProcessor()

    # Mock docling document
    mock_doc = MagicMock()
    mock_doc.title = "Test Paper"
    mock_doc.authors = ["Author One", "Author Two"]
    mock_doc.abstract = "This is the abstract"
    mock_doc.publication_date = "2024"

    metadata = processor.extract_metadata(mock_doc, paper_id="test-123")

    assert metadata.title == "Test Paper"
    assert len(metadata.authors) == 2
    assert metadata.abstract == "This is the abstract"
    assert "2024" in metadata.unique_id or "Author" in metadata.unique_id
