"""Ollama-based VLM PDF converter backend.

Converts PDFs to Markdown by rendering each page as an image and passing it
to a vision-capable Ollama model. Requires a multimodal model to be pulled
in Ollama before use.

Supported models (pull with ``ollama pull <model>``):
    - llava:7b          — general-purpose, widely tested
    - llava-phi3        — smaller and faster, good quality
    - minicpm-v         — strong document and OCR understanding
    - moondream         — very lightweight, fast
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import ollama

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


class OllamaVLMConverter:
    """PDF converter that uses a vision-capable Ollama model to extract text.

    Each PDF page is rendered to a JPEG image and passed to the Ollama model
    via its chat API. Per-page outputs are concatenated with Markdown
    horizontal rules as page separators.

    Args:
        url: Ollama server URL.
        model: Vision-capable model name (must be pulled in Ollama first).
        dpi: Page render resolution. Higher DPI improves OCR quality but
            increases image size and inference time.
    """

    name: str = "ollama_vlm"

    def __init__(
        self,
        url: str = "http://host.docker.internal:11434",
        model: str = "llava-phi3",
        dpi: int = 150,
    ) -> None:
        self.client = ollama.Client(host=url)
        self.model = model
        self.dpi = dpi

    # ──────────────────────────────────────────────────────────────────────
    # Protocol methods (PDFConverterBackend)
    # ──────────────────────────────────────────────────────────────────────

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert all pages of a PDF to Markdown via Ollama VLM extraction."""
        pages = self._render_pages(source_path)
        parts = []
        for i, img_bytes in enumerate(pages):
            logger.debug(
                "Ollama VLM extracting page %d/%d of %s",
                i + 1,
                len(pages),
                source_path.name,
            )
            response = self.client.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": _EXTRACT_PROMPT,
                        "images": [img_bytes],
                    }
                ],
            )
            parts.append(response["message"]["content"])
        return "\n\n---\n\n".join(parts)

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Extract title, authors, abstract, and year from the first page."""
        pages = self._render_pages(source_path)
        if not pages:
            return self._empty_metadata(fallback_title)

        response = self.client.chat(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": _METADATA_PROMPT,
                    "images": [pages[0]],
                }
            ],
        )
        raw = response["message"]["content"]
        return self._parse_metadata_json(raw, fallback_title)

    # ──────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────

    def _render_pages(self, source_path: Path) -> list[bytes]:
        """Render all PDF pages to JPEG bytes using PyMuPDF."""
        import fitz  # PyMuPDF — already a transitive dependency via pymupdf4llm

        doc = fitz.open(str(source_path))
        scale = self.dpi / 72
        mat = fitz.Matrix(scale, scale)
        images = []
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            images.append(pix.tobytes("jpeg"))
        doc.close()
        return images

    def _parse_metadata_json(self, raw: str, fallback_title: str) -> dict:
        """Parse the model's JSON output into the standard metadata dict."""
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
                "Ollama VLM metadata extraction returned non-JSON; using fallback title."
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


# Register as the "ollama_vlm" backend in the converter registry.
# Import this module to activate the registration:
#   from app.services import ollama_vlm_converter  # noqa: F401
register_converter("ollama_vlm", OllamaVLMConverter)
