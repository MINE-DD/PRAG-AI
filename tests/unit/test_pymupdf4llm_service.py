import pytest
from unittest.mock import patch
from pathlib import Path
from app.services.pymupdf4llm_service import PyMuPDF4LLMService
from app.services.pdf_converter_base import PDFConverterBackend

def test_implements_protocol():
    assert isinstance(PyMuPDF4LLMService(), PDFConverterBackend)

def test_name():
    assert PyMuPDF4LLMService().name == "pymupdf"

@patch("app.services.pymupdf4llm_service.pymupdf4llm")
def test_convert_to_markdown(mock_pymupdf4llm):
    mock_pymupdf4llm.to_markdown.return_value = "# Title\n\nContent"
    service = PyMuPDF4LLMService()
    result = service.convert_to_markdown(Path("/fake/paper.pdf"))
    assert result == "# Title\n\nContent"
    mock_pymupdf4llm.to_markdown.assert_called_once_with(str(Path("/fake/paper.pdf")))

@patch("app.services.pymupdf4llm_service.pymupdf4llm")
def test_extract_metadata_from_heading(mock_pymupdf4llm):
    mock_pymupdf4llm.to_markdown.return_value = "# My Paper Title\n\nAlice Smith, Bob Jones\n\n## Introduction\n\nText."
    service = PyMuPDF4LLMService()
    meta = service.extract_metadata(Path("/fake/paper.pdf"), "fallback")
    assert meta["title"] == "My Paper Title"
    assert "Alice Smith" in meta["authors"]
    assert "Bob Jones" in meta["authors"]

@patch("app.services.pymupdf4llm_service.pymupdf4llm")
def test_extract_metadata_fallback(mock_pymupdf4llm):
    mock_pymupdf4llm.to_markdown.return_value = ""
    service = PyMuPDF4LLMService()
    meta = service.extract_metadata(Path("/fake/paper.pdf"), "my_fallback")
    assert meta["title"] == "my_fallback"
