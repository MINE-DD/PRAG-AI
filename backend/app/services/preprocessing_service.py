import json
import re
import threading
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

from app.core.config import settings

# Module-level lock for thread-safe history.json writes
_history_lock = threading.Lock()

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


class PreprocessingService:
    """Service for preprocessing PDFs into markdown + metadata JSON"""

    def __init__(
        self,
        pdf_input_dir: Optional[str] = None,
        preprocessed_dir: Optional[str] = None,
    ):
        self.pdf_input_dir = Path(pdf_input_dir or settings.pdf_input_dir)
        self.preprocessed_dir = Path(preprocessed_dir or settings.preprocessed_dir)
        self.history_path = self.preprocessed_dir / "history.json"

        # Lean converter: text-only, no image/table generation (fast)
        lean_options = PdfPipelineOptions()
        lean_options.generate_picture_images = False
        lean_options.generate_table_images = False

        self.converter = DocumentConverter(
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

    def list_directories(self) -> list[dict]:
        """List subdirectories under pdf_input_dir with PDF counts."""
        self.pdf_input_dir.mkdir(parents=True, exist_ok=True)
        dirs = []
        for path in sorted(self.pdf_input_dir.iterdir()):
            if path.is_dir():
                pdf_count = len(list(path.glob("*.pdf")))
                dirs.append({
                    "name": path.name,
                    "pdf_count": pdf_count,
                })
        return dirs

    def scan_directory(self, dir_name: str) -> list[dict]:
        """List PDFs in a directory, flagging already-processed ones."""
        source_dir = self.pdf_input_dir / dir_name
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Directory not found: {dir_name}")

        output_dir = self.preprocessed_dir / dir_name
        files = []
        for pdf_path in sorted(source_dir.glob("*.pdf")):
            stem = pdf_path.stem
            md_path = output_dir / f"{stem}.md"
            files.append({
                "filename": pdf_path.name,
                "processed": md_path.exists(),
            })
        return files

    def convert_single_pdf(self, dir_name: str, filename: str, backend: str = "docling") -> dict:
        """Convert a single PDF to markdown + minimal metadata JSON.

        backend: "docling" (thorough, slower) or "pymupdf" (fast, text-based)
        """
        source_path = self.pdf_input_dir / dir_name / filename
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {dir_name}/{filename}")

        # Ensure output directory exists
        output_dir = self.preprocessed_dir / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = source_path.stem

        if backend == "pymupdf":
            markdown_content = self._convert_with_pymupdf(source_path)
            paper_meta = {"title": stem, "authors": [], "abstract": None, "publication_date": None}
        else:
            result = self.converter.convert(str(source_path))
            doc = result.document
            markdown_content = doc.export_to_markdown()
            paper_meta = self._extract_paper_metadata(doc, stem)

        # Write markdown
        md_path = output_dir / f"{stem}.md"
        md_path.write_text(markdown_content, encoding="utf-8")

        # Write metadata (with paper info, but no tables/images yet)
        metadata = {
            **paper_meta,
            "source_pdf": filename,
            "backend": backend,
            "preprocessed_at": datetime.now(UTC).isoformat(),
        }
        metadata_path = output_dir / f"{stem}_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        # Update history
        self._update_history(dir_name, filename)

        return {
            "filename": filename,
            "markdown_path": str(md_path),
            "metadata_path": str(metadata_path),
            "markdown_length": len(markdown_content),
            "table_count": 0,
            "image_count": 0,
        }

    @staticmethod
    def _convert_with_pymupdf(source_path: Path) -> str:
        """Convert PDF to markdown using pymupdf4llm (fast, text-based)."""
        import pymupdf4llm
        return pymupdf4llm.to_markdown(str(source_path))

    def extract_assets(self, dir_name: str, filename: str) -> dict:
        """Extract tables and images from an already-preprocessed PDF.

        Re-runs Docling conversion to get the Document object, then extracts
        tables and images and updates the metadata JSON.
        """
        source_path = self.pdf_input_dir / dir_name / filename
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {dir_name}/{filename}")

        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        metadata_path = output_dir / f"{stem}_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found — preprocess {filename} first")

        # Re-run Docling with full converter (image/table generation enabled)
        result = self.full_converter.convert(str(source_path))
        doc = result.document

        # Extract tables and images
        tables_dir = output_dir / f"{stem}_tables"
        table_info = self._extract_tables(doc, tables_dir)

        images_dir = output_dir / f"{stem}_images"
        image_info = self._extract_images(doc, images_dir)

        # Update metadata JSON with tables/images arrays
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["tables"] = table_info
        metadata["images"] = image_info
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return {
            "filename": filename,
            "table_count": len(table_info),
            "image_count": len(image_info),
        }

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

            if label == "section_header" and lower not in _BOILERPLATE_HEADERS and normalized not in _BOILERPLATE_HEADERS and len(text) > best_len:
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
                    authors = self._parse_authors(text)
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

    @staticmethod
    def _parse_authors(raw: str) -> list[str]:
        """Parse an author line into a list of clean author names."""
        cleaned = re.sub(r'\s+\d+(?:\s*,\s*\d+)*[*†‡§]*', '', raw)
        cleaned = re.sub(r'[*†‡§]+', '', cleaned)
        cleaned = re.sub(r'\s+[a-e]\b', '', cleaned)

        parts = re.split(r'\s*,\s*|\s+and\s+|\s+&\s+', cleaned)

        authors = []
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

    def _extract_tables(self, doc, tables_dir: Path) -> list[dict]:
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

    def _extract_images(self, doc, images_dir: Path) -> list[dict]:
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

    def delete_preprocessed(self, dir_name: str, filename: str) -> dict:
        """Delete the preprocessed output (.md + _metadata.json + tables + images) for a single PDF."""
        import shutil

        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        md_path = output_dir / f"{stem}.md"
        meta_path = output_dir / f"{stem}_metadata.json"
        tables_dir = output_dir / f"{stem}_tables"
        images_dir = output_dir / f"{stem}_images"

        deleted = []
        for p in (md_path, meta_path):
            if p.exists():
                p.unlink()
                deleted.append(p.name)

        for d in (tables_dir, images_dir):
            if d.is_dir():
                shutil.rmtree(d)
                deleted.append(d.name)

        # Remove from history
        self._remove_from_history(dir_name, filename)

        return {"filename": filename, "deleted_files": deleted}

    def get_assets(self, dir_name: str, filename: str) -> dict:
        """Get tables and images info for a processed PDF."""
        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        meta_path = output_dir / f"{stem}_metadata.json"

        if not meta_path.exists():
            return {"tables": [], "images": [], "paper_metadata": {}}

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        return {
            "tables": metadata.get("tables", []),
            "images": metadata.get("images", []),
            "paper_metadata": {
                "title": metadata.get("title"),
                "authors": metadata.get("authors", []),
                "publication_date": metadata.get("publication_date"),
                "abstract": metadata.get("abstract"),
            },
        }

    def get_asset_path(self, dir_name: str, filename: str, asset_type: str, asset_file: str) -> Path:
        """Get the filesystem path for a specific asset file."""
        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        if asset_type == "tables":
            return output_dir / f"{stem}_tables" / asset_file
        elif asset_type == "images":
            return output_dir / f"{stem}_images" / asset_file
        raise ValueError(f"Unknown asset type: {asset_type}")

    def _remove_from_history(self, dir_name: str, filename: str):
        """Remove a file from history.json."""
        with _history_lock:
            history = self.get_history()
            entry = history.get("directories", {}).get(dir_name)
            if entry and filename in entry.get("files", []):
                entry["files"].remove(filename)
                if not entry["files"]:
                    del history["directories"][dir_name]
                self.preprocessed_dir.mkdir(parents=True, exist_ok=True)
                self.history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    def get_history(self) -> dict:
        """Read preprocessing history."""
        if not self.history_path.exists():
            return {"directories": {}}
        return json.loads(self.history_path.read_text(encoding="utf-8"))

    def _update_history(self, dir_name: str, filename: str):
        """Update history.json with a newly processed file."""
        with _history_lock:
            self.preprocessed_dir.mkdir(parents=True, exist_ok=True)
            history = self.get_history()

            if dir_name not in history["directories"]:
                history["directories"][dir_name] = {
                    "files": [],
                    "last_processed": None,
                }

            entry = history["directories"][dir_name]
            if filename not in entry["files"]:
                entry["files"].append(filename)
            entry["last_processed"] = datetime.now(UTC).isoformat()

            self.history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
