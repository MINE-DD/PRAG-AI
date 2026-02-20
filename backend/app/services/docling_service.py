"""Docling-based PDF converter backend.

Implements the ``PDFConverterBackend`` protocol using the Docling library
for high-fidelity PDF-to-markdown conversion, metadata extraction, and
table/image asset extraction.
"""

from __future__ import annotations

import re
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

from app.services.pdf_converter_base import parse_authors, register_converter

# Section headers to skip when looking for the paper title
_BOILERPLATE_HEADERS = {
    "research", "research article", "original research", "original article",
    "review", "review article", "short communication", "brief communication",
    "case report", "letter", "commentary", "editorial", "perspective",
    "open access", "edited by:", "reviewed by:", "*correspondence:",
    "specialty section:", "citation:", "abstract", "background",
    "introduction", "methods", "results", "discussion", "conclusions",
    "references", "acknowledgements", "acknowledgments",
    "articleinfo", "articlei n f o",
}


class DoclingService:
    """PDF converter backend powered by Docling.

    Provides lean (text-only) and full (with images/tables) conversion
    pipelines, metadata extraction, and asset extraction.
    """

    name: str = "docling"

    def __init__(self) -> None:
        # Lean converter: text-only, no image/table generation (fast)
        lean_options = PdfPipelineOptions()
        lean_options.generate_picture_images = False
        lean_options.generate_table_images = False

        self.lean_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=lean_options)
            }
        )

        # Full converter: with image/table generation (for extract_assets)
        full_options = PdfPipelineOptions()
        full_options.generate_picture_images = True
        full_options.generate_table_images = True

        self.full_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=full_options)
            }
        )

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert the PDF at *source_path* to a Markdown string."""
        result = self.lean_converter.convert(str(source_path))
        doc = result.document
        return doc.export_to_markdown()

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Return metadata dict with title, authors, abstract, publication_date."""
        result = self.lean_converter.convert(str(source_path))
        doc = result.document
        return self._extract_paper_metadata(doc, fallback_title)

    # ------------------------------------------------------------------
    # Extended methods (beyond protocol)
    # ------------------------------------------------------------------

    def convert_and_extract(
        self, source_path: Path, fallback_title: str
    ) -> tuple[str, dict]:
        """Single Docling call returning both markdown and metadata.

        Avoids the double-conversion cost of calling ``convert_to_markdown``
        and ``extract_metadata`` separately.
        """
        result = self.lean_converter.convert(str(source_path))
        doc = result.document
        markdown = doc.export_to_markdown()
        metadata = self._extract_paper_metadata(doc, fallback_title)
        return markdown, metadata

    def convert_full(self, source_path: Path):
        """Run full converter (with image/table generation) and return the Docling document."""
        result = self.full_converter.convert(str(source_path))
        return result.document

    # ------------------------------------------------------------------
    # Asset extraction
    # ------------------------------------------------------------------

    def extract_tables(self, doc, tables_dir: Path) -> list[dict]:
        """Extract tables from a Docling document and save as CSV files."""
        tables = getattr(doc, "tables", [])
        if not tables:
            return []

        tables_dir.mkdir(parents=True, exist_ok=True)
        table_info = []

        for i, table in enumerate(tables):
            caption = ""
            try:
                caption = table.caption_text(doc) or ""
            except Exception:
                pass

            page_no = None
            if table.prov:
                page_no = table.prov[0].page_no

            # Save as CSV
            csv_path = tables_dir / f"table_{i}.csv"
            try:
                df = table.export_to_dataframe(doc)
                df.to_csv(str(csv_path), index=False)
            except Exception:
                # Fallback: save markdown version
                try:
                    md_content = table.export_to_markdown(doc)
                    csv_path = tables_dir / f"table_{i}.md"
                    csv_path.write_text(md_content, encoding="utf-8")
                except Exception:
                    continue

            table_info.append({
                "index": i,
                "caption": caption,
                "page": page_no,
                "file": csv_path.name,
            })

        return table_info

    def extract_images(self, doc, images_dir: Path) -> list[dict]:
        """Extract images/pictures from a Docling document and save as PNG files."""
        pictures = getattr(doc, "pictures", [])
        if not pictures:
            return []

        images_dir.mkdir(parents=True, exist_ok=True)
        image_info = []

        for i, picture in enumerate(pictures):
            caption = ""
            try:
                caption = picture.caption_text(doc) or ""
            except Exception:
                pass

            page_no = None
            if picture.prov:
                page_no = picture.prov[0].page_no

            # Try to get the PIL image
            pil_img = None
            if hasattr(picture, "image") and picture.image:
                pil_img = getattr(picture.image, "pil_image", None)
            if pil_img is None:
                try:
                    pil_img = picture.get_image(doc)
                except Exception:
                    pass

            if pil_img is None:
                continue

            png_path = images_dir / f"image_{i}.png"
            pil_img.save(str(png_path))

            image_info.append({
                "index": i,
                "caption": caption,
                "page": page_no,
                "file": png_path.name,
                "width": pil_img.size[0],
                "height": pil_img.size[1],
            })

        return image_info

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_paper_metadata(self, doc, fallback_title: str) -> dict:
        """Extract title, authors, abstract, and date from Docling document structure."""
        texts = getattr(doc, "texts", [])
        if not texts:
            return {"title": fallback_title, "authors": [], "abstract": None, "publication_date": None}

        title = None
        title_idx = None
        authors = []
        abstract = None
        publication_date = None

        # --- Title: longest section_header before body sections, skipping boilerplate ---
        best_len = 0
        for i, item in enumerate(texts):
            label = item.label.value
            text = (item.text or "").strip()
            lower = text.lower().rstrip(":")
            normalized = re.sub(r'\s+', '', lower)

            if label == "section_header" and normalized in (
                "background", "introduction", "methods", "abstract",
                "1.introduction", "1introduction",
            ):
                break

            if (label == "section_header"
                    and lower not in _BOILERPLATE_HEADERS
                    and normalized not in _BOILERPLATE_HEADERS
                    and len(text) > best_len):
                best_len = len(text)
                title = text
                title_idx = i

        if title is None:
            title = fallback_title

        # --- Authors: first text item after the title, before next section_header ---
        if title_idx is not None:
            for item in texts[title_idx + 1:]:
                label = item.label.value
                text = (item.text or "").strip()
                if label == "section_header":
                    break
                if label == "text" and text:
                    authors = parse_authors(text)
                    break

        # --- Abstract: text between "Abstract" header and next section_header ---
        abstract_parts = []
        in_abstract = False
        for item in texts:
            label = item.label.value
            text = (item.text or "").strip()
            normalized = re.sub(r'\s+', '', text).lower()

            if label == "section_header" and normalized in ("abstract", "abstract:"):
                in_abstract = True
                continue
            if in_abstract:
                if label == "section_header":
                    break
                if label == "text" and text:
                    abstract_parts.append(text)

        if abstract_parts:
            abstract = " ".join(abstract_parts)

        # --- Publication date: look in page_headers for year patterns ---
        for item in texts[:5]:
            if item.label.value == "page_header":
                text = item.text or ""
                year_match = re.search(r'\b(19|20)\d{2}\b', text)
                if year_match:
                    publication_date = year_match.group()
                    break

        return {
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "publication_date": publication_date,
        }


# Register this backend in the converter registry
register_converter("docling", DoclingService)
