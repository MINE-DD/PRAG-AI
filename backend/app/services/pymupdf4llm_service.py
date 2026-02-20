"""PyMuPDF4LLM-based PDF converter backend.

Implements the ``PDFConverterBackend`` protocol using the pymupdf4llm
library for PDF-to-markdown conversion and basic metadata extraction
from the resulting markdown text.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf4llm

from app.services.pdf_converter_base import parse_authors, register_converter


class PyMuPDF4LLMService:
    """PDF converter backend powered by PyMuPDF4LLM.

    Uses ``pymupdf4llm.to_markdown`` for conversion and parses
    title/authors from the resulting markdown text.
    """

    name: str = "pymupdf"

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert the PDF at *source_path* to a Markdown string."""
        return pymupdf4llm.to_markdown(str(source_path))

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Return metadata dict with title, authors, abstract, publication_date."""
        markdown_text = self.convert_to_markdown(source_path)
        return self._extract_metadata_from_markdown(markdown_text, fallback_title)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_metadata_from_markdown(self, markdown_text: str, fallback_title: str) -> dict:
        """Parse title and authors from raw markdown text."""
        lines = markdown_text.strip().split("\n")

        title = None
        title_idx = None

        # First # heading = title
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped.lstrip("# ").strip()
                title_idx = i
                break

        # Fallback: first non-empty line
        if title is None:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("!") and not stripped.startswith("["):
                    title = stripped
                    title_idx = i
                    break

        if title is None:
            title = fallback_title

        # Authors: first non-empty, non-heading line after title
        authors = []
        if title_idx is not None:
            for line in lines[title_idx + 1:]:
                stripped = line.strip()
                if stripped.startswith("#"):
                    break
                if stripped and len(stripped) > 5:
                    authors = parse_authors(stripped)
                    break

        return {
            "title": title,
            "authors": authors,
            "abstract": None,
            "publication_date": None,
        }


# Register this backend in the converter registry
register_converter("pymupdf", PyMuPDF4LLMService)
