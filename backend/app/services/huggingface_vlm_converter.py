"""VLM-based PDF converter backend using HuggingFace vision-language models.

Converts PDFs to Markdown by rendering each page as an image and passing it
through a VLM. Useful for scanned PDFs, image-heavy documents, or any file
where layout-based converters (Docling, PyMuPDF4LLM) fall short.

Install optional dependencies before use:
    uv sync --extra huggingface
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.services.huggingface_service import HuggingFaceService
from app.services.pdf_converter_base import register_converter

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "You are a document extraction assistant. "
    "Extract all text from this PDF page exactly as it appears. "
    "Preserve headings, paragraphs, lists, and table structure using Markdown formatting. "
    "Do not add commentary or summaries — output only the extracted content."
)

_METADATA_PROMPT = (
    "Extract the following fields from this document page if present:\n"
    "- title\n"
    "- authors (comma-separated full names)\n"
    "- abstract\n"
    "- publication year (4-digit number)\n\n"
    "Return ONLY a JSON object with keys: title, authors, abstract, year. "
    "Use null for any field not found. Do not include any other text."
)


class HuggingFaceVLMConverter:
    """PDF converter that uses a VLM to extract text from rendered page images.

    Each page is rendered to a PIL Image at a configurable DPI and passed to
    the VLM with an extraction prompt. Per-page outputs are concatenated with
    Markdown horizontal rules as page separators.

    Args:
        vlm_service: An existing HuggingFaceService instance. If None, a new
            one is created using *vlm_model_id*.
        vlm_model_id: Model ID used when creating a new service instance.
        dpi: Page render resolution. Higher DPI → better OCR quality, slower.
    """

    name: str = "vlm"

    def __init__(
        self,
        vlm_service: HuggingFaceService | None = None,
        vlm_model_id: str = "Qwen/Qwen2-VL-7B-Instruct",
        dpi: int = 150,
    ) -> None:
        self._service = vlm_service or HuggingFaceService(vlm_model_id=vlm_model_id)
        self.dpi = dpi

    # ──────────────────────────────────────────────────────────────────────
    # Protocol methods (PDFConverterBackend)
    # ──────────────────────────────────────────────────────────────────────

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert all pages of a PDF to Markdown via VLM extraction."""
        pages = self._render_pages(source_path)
        parts = []
        for i, page_img in enumerate(pages):
            logger.debug(
                "VLM extracting page %d/%d of %s", i + 1, len(pages), source_path.name
            )
            text = self._service.extract_from_image(page_img, prompt=_EXTRACT_PROMPT)
            parts.append(text)
        return "\n\n---\n\n".join(parts)

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Extract title, authors, abstract, and year from the first page."""
        pages = self._render_pages(source_path)
        if not pages:
            return self._empty_metadata(fallback_title)

        raw = self._service.extract_from_image(pages[0], prompt=_METADATA_PROMPT)
        return self._parse_metadata_json(raw, fallback_title)

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _render_pages(self, source_path: Path) -> list:
        """Render all PDF pages to PIL Images using PyMuPDF."""
        import fitz  # PyMuPDF — already a transitive dependency via pymupdf4llm
        from PIL import Image

        doc = fitz.open(str(source_path))
        scale = self.dpi / 72
        mat = fitz.Matrix(scale, scale)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(img)
        doc.close()
        return images

    def _parse_metadata_json(self, raw: str, fallback_title: str) -> dict:
        """Parse VLM JSON output into the standard metadata dict."""
        try:
            cleaned = (
                raw.strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
                .strip()
            )
            data = json.loads(cleaned)
            authors_raw = data.get("authors") or ""
            authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
            return {
                "title": data.get("title") or fallback_title,
                "authors": authors,
                "abstract": data.get("abstract"),
                "publication_date": str(data["year"]) if data.get("year") else None,
            }
        except (json.JSONDecodeError, AttributeError, KeyError):
            logger.warning(
                "VLM metadata extraction returned non-JSON output; using fallback title."
            )
            return self._empty_metadata(fallback_title)

    @staticmethod
    def _empty_metadata(fallback_title: str) -> dict:
        return {
            "title": fallback_title,
            "authors": [],
            "abstract": None,
            "publication_date": None,
        }


# Register as the "vlm" backend in the converter registry.
# Import this module to activate the registration:
#   from app.services import huggingface_vlm_converter  # noqa: F401
register_converter("vlm", HuggingFaceVLMConverter)
