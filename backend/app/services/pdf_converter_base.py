"""Shared protocol and utilities for PDF converter backends.

Defines the ``PDFConverterBackend`` protocol that every concrete backend
(Docling, PyMuPDF, ...) must satisfy, a lightweight registry for
discovering backends by name, and the ``parse_authors`` helper reused
across backends.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class PDFConverterBackend(Protocol):
    """Interface that every PDF-to-markdown converter must implement."""

    name: str

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert the PDF at *source_path* to a Markdown string."""
        ...

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Return a metadata dict with at least title, authors, abstract, publication_date."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CONVERTER_REGISTRY: dict[str, type[PDFConverterBackend]] = {}


def register_converter(name: str, cls: type[PDFConverterBackend]) -> None:
    """Register a converter class under the given *name*."""
    _CONVERTER_REGISTRY[name] = cls


def get_converter(backend: str) -> PDFConverterBackend:
    """Instantiate and return the converter registered under *backend*.

    Raises ``KeyError`` if *backend* has not been registered.
    """
    try:
        cls = _CONVERTER_REGISTRY[backend]
    except KeyError:
        raise KeyError(
            f"Unknown converter backend {backend!r}. "
            f"Available: {sorted(_CONVERTER_REGISTRY)}"
        )
    return cls()


# ---------------------------------------------------------------------------
# Shared utility – author parsing
# ---------------------------------------------------------------------------

def parse_authors(raw: str) -> list[str]:
    """Parse a raw author line into a list of clean author names.

    Strips superscript numbers, footnote markers (*†‡§), letter
    annotations, and filters out affiliations / emails.
    """
    cleaned = re.sub(r'\s+\d+(?:\s*,\s*\d+)*[*†‡§]*', '', raw)
    cleaned = re.sub(r'[*†‡§]+', '', cleaned)
    cleaned = re.sub(r'\s+[a-e]\b', '', cleaned)

    parts = re.split(r'\s*,\s*|\s+and\s+|\s+&\s+', cleaned)

    authors: list[str] = []
    for part in parts:
        name = part.strip().strip(",")
        if not name or len(name) < 3:
            continue
        if "@" in name or "university" in name.lower() or "department" in name.lower():
            continue
        alpha_chars = sum(1 for c in name if c.isalpha())
        if alpha_chars < 3:
            continue
        authors.append(name)

    return authors
