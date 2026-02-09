import pytest
import sys
from pathlib import Path

# Add backend to path for local testing
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.citation_service import CitationService
from app.models.paper import PaperMetadata


def test_format_apa_citation():
    """Test APA citation formatting"""
    service = CitationService()

    metadata = PaperMetadata(
        paper_id="paper-123",
        title="Attention Is All You Need",
        authors=["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
        year=2017,
        unique_id="VaswaniAttention2017",
        journal_conference="NeurIPS"
    )

    citation = service.format_apa(metadata)

    assert "Vaswani, A." in citation
    assert "Attention Is All You Need" in citation
    assert "2017" in citation
    assert "NeurIPS" in citation


def test_format_bibtex_citation():
    """Test BibTeX citation formatting"""
    service = CitationService()

    metadata = PaperMetadata(
        paper_id="paper-123",
        title="Attention Is All You Need",
        authors=["Vaswani, A.", "Shazeer, N."],
        year=2017,
        unique_id="VaswaniAttention2017"
    )

    citation = service.format_bibtex(metadata)

    assert "@article{VaswaniAttention2017" in citation
    assert "title = {Attention Is All You Need}" in citation
    assert "author = {Vaswani, A. and Shazeer, N.}" in citation
    assert "year = {2017}" in citation


def test_format_citation_with_missing_fields():
    """Test citation formatting with missing optional fields"""
    service = CitationService()

    metadata = PaperMetadata(
        paper_id="paper-123",
        title="Unknown Paper",
        authors=[],
        unique_id="Unknown"
    )

    # Should not raise error
    apa = service.format_apa(metadata)
    bibtex = service.format_bibtex(metadata)

    assert "Unknown Paper" in apa
    assert "Unknown Paper" in bibtex


def test_extract_citation_key():
    """Test generating BibTeX citation key"""
    service = CitationService()

    # Should use unique_id as key
    metadata = PaperMetadata(
        paper_id="paper-123",
        title="Test Paper",
        authors=["Author, A."],
        year=2024,
        unique_id="AuthorTest2024"
    )

    key = service.extract_citation_key(metadata)
    assert key == "AuthorTest2024"


def test_format_author_list_apa():
    """Test APA author list formatting"""
    service = CitationService()

    # Single author
    assert service.format_authors_apa(["Smith, J."]) == "Smith, J."

    # Two authors
    assert service.format_authors_apa(["Smith, J.", "Doe, A."]) == "Smith, J., & Doe, A."

    # Three or more authors (use et al.)
    authors = ["Smith, J.", "Doe, A.", "Johnson, B."]
    formatted = service.format_authors_apa(authors)
    assert "Smith, J." in formatted
    assert "et al." in formatted or "Doe, A." in formatted  # APA 7 shows all in reference


def test_format_author_list_bibtex():
    """Test BibTeX author list formatting"""
    service = CitationService()

    authors = ["Smith, J.", "Doe, A.", "Johnson, B."]
    formatted = service.format_authors_bibtex(authors)

    assert "Smith, J. and Doe, A. and Johnson, B." == formatted
