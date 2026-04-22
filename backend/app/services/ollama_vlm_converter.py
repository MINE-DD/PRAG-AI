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
from app.services.prompt_service import PromptService

logger = logging.getLogger(__name__)


class OllamaVLMConverter:
    """PDF converter that uses a vision-capable Ollama model to extract text.

    Each PDF page is rendered to a JPEG image and passed to the Ollama model
    via its chat API. Per-page outputs are concatenated with Markdown
    horizontal rules as page separators.

    Prompts are loaded from the prompt template system (``vlm_extract`` and
    ``vlm_metadata`` task types), allowing different prompt variants per
    document type without changing code.

    Args:
        url: Ollama server URL.
        model: Vision-capable model name (must be pulled in Ollama first).
        dpi: Page render resolution. Higher DPI improves OCR quality but
            increases image size and inference time.
        prompt_service: Service used to render extraction and metadata prompts.
        extract_prompt_name: Named prompt under ``vlm_extract/`` to use for
            per-page text extraction.
        metadata_prompt_name: Named prompt under ``vlm_metadata/`` to use for
            first-page metadata extraction.
        document_type: Passed as ``{document_type}`` template variable to the
            prompts. Use to tune extraction for a specific document class
            (e.g. ``"academic paper"``, ``"invoice"``, ``"report"``).
    """

    name: str = "ollama_vlm"

    def __init__(
        self,
        url: str = "http://host.docker.internal:11434",
        model: str = "llava-phi3",
        dpi: int = 150,
        *,
        prompt_service: PromptService,
        extract_prompt_name: str = "default",
        metadata_prompt_name: str = "default",
        document_type: str = "document",
    ) -> None:
        self.client = ollama.Client(host=url)
        self.model = model
        self.dpi = dpi
        self._prompt_service = prompt_service
        self._extract_prompt_name = extract_prompt_name
        self._metadata_prompt_name = metadata_prompt_name
        self._document_type = document_type

    # ──────────────────────────────────────────────────────────────────────
    # Protocol methods (PDFConverterBackend)
    # ──────────────────────────────────────────────────────────────────────

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert all pages of a PDF to Markdown via Ollama VLM extraction."""
        rendered = self._prompt_service.render(
            "vlm_extract",
            self._extract_prompt_name,
            document_type=self._document_type,
        )
        pages = self._render_pages(source_path)
        parts = []
        for i, img_bytes in enumerate(pages):
            logger.debug(
                "Ollama VLM extracting page %d/%d of %s",
                i + 1,
                len(pages),
                source_path.name,
            )
            messages = []
            if rendered.system:
                messages.append({"role": "system", "content": rendered.system})
            messages.append(
                {"role": "user", "content": rendered.user, "images": [img_bytes]}
            )
            response = self.client.chat(model=self.model, messages=messages)
            parts.append(response["message"]["content"])
        return "\n\n---\n\n".join(parts)

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Extract title, authors or creators, summary, and date from the first page."""
        pages = self._render_pages(source_path)
        if not pages:
            return self._empty_metadata(fallback_title)

        rendered = self._prompt_service.render(
            "vlm_metadata",
            self._metadata_prompt_name,
            document_type=self._document_type,
        )
        messages = []
        if rendered.system:
            messages.append({"role": "system", "content": rendered.system})
        messages.append(
            {"role": "user", "content": rendered.user, "images": [pages[0]]}
        )
        response = self.client.chat(model=self.model, messages=messages)
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
        """Parse the model's JSON output into the standard metadata dict.

        Known keys (title, authors, abstract, year) are mapped to fixed fields.
        Any additional keys returned by the model are collected into extra_metadata,
        allowing document-type-specific prompts to extract arbitrary fields.
        """
        _KNOWN_KEYS = {"title", "authors", "abstract", "year"}
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
            extra = {
                k: v for k, v in data.items() if k not in _KNOWN_KEYS and v is not None
            }
            return {
                "title": data.get("title") or fallback_title,
                "authors": authors,
                "abstract": data.get("abstract"),
                "publication_date": str(data["year"]) if data.get("year") else None,
                "extra_metadata": extra,
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
            "extra_metadata": {},
        }


# Register as the "ollama_vlm" backend in the converter registry.
# Import this module to activate the registration:
#   from app.services import ollama_vlm_converter  # noqa: F401
register_converter("ollama_vlm", OllamaVLMConverter)
