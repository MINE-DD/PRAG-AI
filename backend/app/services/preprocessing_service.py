import json
import re
import threading
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

from app.services.pdf_converter_base import get_converter
# Ensure backend modules register themselves
import app.services.docling_service  # noqa: F401
import app.services.pymupdf4llm_service  # noqa: F401

from app.core.config import settings
from app.services.paper_metadata_api_service import enrich_metadata as _api_enrich

# Module-level lock for thread-safe history.json writes
_history_lock = threading.Lock()


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

    def convert_single_pdf(
        self, dir_name: str, filename: str,
        backend: str = "docling", metadata_backend: str = "openalex",
    ) -> dict:
        """Convert a single PDF to markdown + metadata JSON.

        backend: "docling" (thorough, slower) or "pymupdf" (fast, text-based)
        metadata_backend: "openalex", "crossref", "semantic_scholar", or "none"
        """
        source_path = self.pdf_input_dir / dir_name / filename
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {dir_name}/{filename}")

        # Ensure output directory exists
        output_dir = self.preprocessed_dir / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = source_path.stem

        converter = get_converter(backend)
        # Use convert_and_extract if available (avoids double conversion for Docling)
        if hasattr(converter, "convert_and_extract"):
            markdown_content, paper_meta = converter.convert_and_extract(source_path, stem)
        else:
            markdown_content = converter.convert_to_markdown(source_path)
            paper_meta = converter.extract_metadata(source_path, stem)

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

        # Auto-enrich with metadata API
        enriched = False
        if metadata_backend and metadata_backend != "none":
            title = paper_meta.get("title", stem)
            api_data = _api_enrich(title, metadata_backend)
            if api_data:
                for key in ("title", "authors", "publication_date", "abstract", "doi", "journal"):
                    if api_data.get(key):
                        metadata[key] = api_data[key]
                if api_data.get("openalex_id"):
                    metadata["openalex_id"] = api_data["openalex_id"]
                metadata["metadata_source"] = metadata_backend
                enriched = True

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
            "metadata_enriched": enriched,
        }

    def enrich_with_api(self, dir_name: str, filename: str, backend: str) -> dict:
        """Enrich metadata for an already-preprocessed PDF using an external API."""
        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        metadata_path = output_dir / f"{stem}_metadata.json"

        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found — preprocess {filename} first")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        title = metadata.get("title", stem)

        api_data = _api_enrich(title, backend)
        if not api_data:
            return {"filename": filename, "enriched": False, "backend": backend}

        # Merge API data into metadata (overwrite with API values when present)
        for key in ("title", "authors", "publication_date", "abstract", "doi", "journal"):
            if api_data.get(key):
                metadata[key] = api_data[key]

        if api_data.get("openalex_id"):
            metadata["openalex_id"] = api_data["openalex_id"]

        metadata["metadata_source"] = backend
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        return {"filename": filename, "enriched": True, "backend": backend, "title": metadata.get("title")}

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
        from app.services.docling_service import DoclingService
        docling = DoclingService()
        doc = docling.convert_full(source_path)

        # Extract tables and images
        tables_dir = output_dir / f"{stem}_tables"
        table_info = docling.extract_tables(doc, tables_dir)

        images_dir = output_dir / f"{stem}_images"
        image_info = docling.extract_images(doc, images_dir)

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

        # Extract references section from the markdown file
        references = ""
        md_path = output_dir / f"{stem}.md"
        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            ref_pattern = re.compile(
                r"^(?:#{1,3}\s+|\*\*)?(?:References|Bibliography|Works Cited|Literature Cited)(?:\*\*)?\s*$",
                re.IGNORECASE | re.MULTILINE,
            )
            ref_match = ref_pattern.search(md_text)
            if ref_match:
                references = md_text[ref_match.start():]

        return {
            "tables": metadata.get("tables", []),
            "images": metadata.get("images", []),
            "references": references,
            "paper_metadata": {
                "title": metadata.get("title"),
                "authors": metadata.get("authors", []),
                "publication_date": metadata.get("publication_date"),
                "abstract": metadata.get("abstract"),
                "doi": metadata.get("doi"),
                "journal": metadata.get("journal"),
                "metadata_source": metadata.get("metadata_source"),
                "backend": metadata.get("backend"),
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
