import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from app.services.docling_service import DoclingService
from app.services.pdf_converter_base import PDFConverterBackend


def test_implements_protocol():
    assert isinstance(DoclingService(), PDFConverterBackend)


def test_name():
    assert DoclingService().name == "docling"


def test_convert_to_markdown():
    service = DoclingService()
    mock_doc = MagicMock()
    mock_doc.export_to_markdown.return_value = "# Title\n\nContent"
    mock_result = MagicMock()
    mock_result.document = mock_doc
    service.lean_converter = MagicMock()
    service.lean_converter.convert.return_value = mock_result
    md = service.convert_to_markdown(Path("/fake/paper.pdf"))
    assert md == "# Title\n\nContent"
    service.lean_converter.convert.assert_called_once()


def test_extract_metadata_finds_title():
    service = DoclingService()
    mock_title = MagicMock()
    mock_title.label.value = "section_header"
    mock_title.text = "My Great Paper Title"
    mock_author = MagicMock()
    mock_author.label.value = "text"
    mock_author.text = "Alice Smith, Bob Jones"
    mock_doc = MagicMock()
    mock_doc.texts = [mock_title, mock_author]
    mock_doc.export_to_markdown.return_value = "# My Great Paper Title"
    mock_result = MagicMock()
    mock_result.document = mock_doc
    service.lean_converter = MagicMock()
    service.lean_converter.convert.return_value = mock_result
    meta = service.extract_metadata(Path("/fake/paper.pdf"), "fallback")
    assert meta["title"] == "My Great Paper Title"
    assert "Alice Smith" in meta["authors"]


def test_extract_metadata_fallback_title():
    service = DoclingService()
    mock_doc = MagicMock()
    mock_doc.texts = []
    mock_doc.export_to_markdown.return_value = ""
    mock_result = MagicMock()
    mock_result.document = mock_doc
    service.lean_converter = MagicMock()
    service.lean_converter.convert.return_value = mock_result
    meta = service.extract_metadata(Path("/fake/paper.pdf"), "my_fallback")
    assert meta["title"] == "my_fallback"
