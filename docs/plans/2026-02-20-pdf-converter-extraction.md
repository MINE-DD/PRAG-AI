# PDF Converter Backend Extraction — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extract Docling and PyMuPDF conversion logic from `PreprocessingService` into independent backend services behind a common protocol, so new backends (e.g. Marker) can be added with zero changes to orchestration code.

**Architecture:** A `PDFConverterBackend` Protocol defines two methods (`convert_to_markdown`, `extract_metadata`). Each backend (Docling, PyMuPDF) implements it in its own file. A `get_converter()` factory maps backend names to implementations. `PreprocessingService` and `PDFProcessor` delegate to the factory instead of containing conversion logic.

**Tech Stack:** Python 3.12, `typing.Protocol`, Docling, pymupdf4llm, pytest

---

### Task 1: Create the shared protocol and `_parse_authors` utility

**Files:**
- Create: `backend/app/services/pdf_converter_base.py`

**Step 1: Write the failing test**

Create `tests/unit/test_pdf_converter_base.py`:

```python
import pytest
from app.services.pdf_converter_base import PDFConverterBackend, get_converter, parse_authors


def test_parse_authors_simple():
    result = parse_authors("Alice Smith, Bob Jones")
    assert result == ["Alice Smith", "Bob Jones"]


def test_parse_authors_with_superscripts():
    result = parse_authors("Alice Smith 1,2*, Bob Jones 3†")
    assert result == ["Alice Smith", "Bob Jones"]


def test_parse_authors_filters_affiliations():
    result = parse_authors("Alice Smith, University of Testing, Bob Jones")
    assert len(result) == 2
    assert "University of Testing" not in result


def test_get_converter_unknown_raises():
    with pytest.raises(KeyError):
        get_converter("nonexistent_backend")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pdf_converter_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.pdf_converter_base'`

**Step 3: Write minimal implementation**

Create `backend/app/services/pdf_converter_base.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Protocol, runtime_checkable

_CONVERTER_REGISTRY: dict[str, type[PDFConverterBackend]] = {}


@runtime_checkable
class PDFConverterBackend(Protocol):
    """Common interface every PDF-to-markdown backend must implement."""

    name: str

    def convert_to_markdown(self, source_path: Path) -> str:
        """Convert a PDF file to markdown text."""
        ...

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        """Extract paper metadata. Returns dict with keys:
        title, authors, abstract, publication_date."""
        ...


def register_converter(name: str, cls: type[PDFConverterBackend]) -> None:
    _CONVERTER_REGISTRY[name] = cls


def get_converter(backend: str) -> PDFConverterBackend:
    """Return an instance of the requested backend."""
    return _CONVERTER_REGISTRY[backend]()


def parse_authors(raw: str) -> list[str]:
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pdf_converter_base.py -v`
Expected: 4 PASSED

**Step 5: Commit**

```bash
git add backend/app/services/pdf_converter_base.py tests/unit/test_pdf_converter_base.py
git commit -m "feat: add PDFConverterBackend protocol and parse_authors utility"
```

---

### Task 2: Create `docling_service.py`

**Files:**
- Create: `backend/app/services/docling_service.py`
- Create: `tests/unit/test_docling_service.py`

**Step 1: Write the failing test**

Create `tests/unit/test_docling_service.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_docling_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

Create `backend/app/services/docling_service.py`:

```python
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
    """Docling-based PDF converter backend."""

    name: str = "docling"

    def __init__(self) -> None:
        lean_options = PdfPipelineOptions()
        lean_options.generate_picture_images = False
        lean_options.generate_table_images = False

        self.lean_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=lean_options)
            }
        )

        full_options = PdfPipelineOptions()
        full_options.generate_picture_images = True
        full_options.generate_table_images = True

        self.full_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=full_options)
            }
        )

    def convert_to_markdown(self, source_path: Path) -> str:
        result = self.lean_converter.convert(str(source_path))
        return result.document.export_to_markdown()

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        result = self.lean_converter.convert(str(source_path))
        doc = result.document
        return self._extract_paper_metadata(doc, fallback_title)

    def convert_and_extract(self, source_path: Path, fallback_title: str) -> tuple[str, dict]:
        """Single Docling call that returns both markdown and metadata."""
        result = self.lean_converter.convert(str(source_path))
        doc = result.document
        markdown = doc.export_to_markdown()
        metadata = self._extract_paper_metadata(doc, fallback_title)
        return markdown, metadata

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

            csv_path = tables_dir / f"table_{i}.csv"
            try:
                df = table.export_to_dataframe(doc)
                df.to_csv(str(csv_path), index=False)
            except Exception:
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

    def convert_full(self, source_path: Path):
        """Run full converter (with image/table generation) and return Docling doc."""
        result = self.full_converter.convert(str(source_path))
        return result.document

    def _extract_paper_metadata(self, doc, fallback_title: str) -> dict:
        texts = getattr(doc, "texts", [])
        if not texts:
            return {"title": fallback_title, "authors": [], "abstract": None, "publication_date": None}

        title = None
        title_idx = None
        authors = []
        abstract = None
        publication_date = None

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

        if title_idx is not None:
            for item in texts[title_idx + 1:]:
                label = item.label.value
                text = (item.text or "").strip()
                if label == "section_header":
                    break
                if label == "text" and text:
                    authors = parse_authors(text)
                    break

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


register_converter("docling", DoclingService)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_docling_service.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add backend/app/services/docling_service.py tests/unit/test_docling_service.py
git commit -m "feat: extract Docling logic into DoclingService"
```

---

### Task 3: Create `pymupdf4llm_service.py`

**Files:**
- Create: `backend/app/services/pymupdf4llm_service.py`
- Create: `tests/unit/test_pymupdf4llm_service.py`

**Step 1: Write the failing test**

Create `tests/unit/test_pymupdf4llm_service.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pymupdf4llm_service.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

Create `backend/app/services/pymupdf4llm_service.py`:

```python
from __future__ import annotations

from pathlib import Path

import pymupdf4llm

from app.services.pdf_converter_base import parse_authors, register_converter


class PyMuPDF4LLMService:
    """PyMuPDF-based PDF converter backend (fast, text-based)."""

    name: str = "pymupdf"

    def convert_to_markdown(self, source_path: Path) -> str:
        return pymupdf4llm.to_markdown(str(source_path))

    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict:
        markdown_text = self.convert_to_markdown(source_path)
        return self._extract_metadata_from_markdown(markdown_text, fallback_title)

    def _extract_metadata_from_markdown(self, markdown_text: str, fallback_title: str) -> dict:
        lines = markdown_text.strip().split("\n")

        title = None
        title_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped.lstrip("# ").strip()
                title_idx = i
                break

        if title is None:
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("!") and not stripped.startswith("["):
                    title = stripped
                    title_idx = i
                    break

        if title is None:
            title = fallback_title

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


register_converter("pymupdf", PyMuPDF4LLMService)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pymupdf4llm_service.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add backend/app/services/pymupdf4llm_service.py tests/unit/test_pymupdf4llm_service.py
git commit -m "feat: extract PyMuPDF logic into PyMuPDF4LLMService"
```

---

### Task 4: Refactor `PreprocessingService` to use the converter backends

**Files:**
- Modify: `backend/app/services/preprocessing_service.py`
- Modify: `tests/unit/test_preprocessing_service.py`

**Step 1: Update existing test to use new structure**

In `tests/unit/test_preprocessing_service.py`, update the mock-based conversion test. The existing `test_convert_single_pdf_success` mocks `service.converter` — it should still work since we're patching `get_converter`. Update to:

```python
# Add this import at the top:
from unittest.mock import patch, MagicMock

# Replace test_convert_single_pdf_success with:
def test_convert_single_pdf_success(service, temp_dirs):
    """Test successful PDF conversion with mocked backend."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Test Paper\n\nSome content here."
    mock_converter.extract_metadata.return_value = {
        "title": "Test Paper",
        "authors": [],
        "abstract": None,
        "publication_date": None,
    }

    with patch("app.services.preprocessing_service.get_converter", return_value=mock_converter):
        result = service.convert_single_pdf("my_papers", "paper1.pdf", metadata_backend="none")

    assert result["filename"] == "paper1.pdf"
    assert result["markdown_length"] > 0

    output_dir = Path(preprocessed) / "my_papers"
    assert (output_dir / "paper1.md").exists()
    assert (output_dir / "paper1_metadata.json").exists()

    metadata = json.loads((output_dir / "paper1_metadata.json").read_text())
    assert metadata["title"] == "Test Paper"
    assert metadata["source_pdf"] == "paper1.pdf"
```

Also update `test_convert_single_pdf_file_not_found`:

```python
@patch.object(PreprocessingService, "__init__", lambda self, **kw: None)
def test_convert_single_pdf_file_not_found():
    """Test converting a non-existent PDF."""
    service = PreprocessingService()
    service.pdf_input_dir = Path("/nonexistent")
    service.preprocessed_dir = Path("/nonexistent_out")
    service.history_path = service.preprocessed_dir / "history.json"

    with pytest.raises(FileNotFoundError):
        service.convert_single_pdf("dir", "missing.pdf")
```

And update `test_history_updated_after_conversion`:

```python
def test_history_updated_after_conversion(service, temp_dirs):
    """Test that history is updated after conversion."""
    pdf_input, preprocessed = temp_dirs
    dir1 = Path(pdf_input) / "my_papers"
    dir1.mkdir()
    _create_fake_pdf(str(dir1), "paper1.pdf")

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Content"
    mock_converter.extract_metadata.return_value = {
        "title": "Content",
        "authors": [],
        "abstract": None,
        "publication_date": None,
    }

    with patch("app.services.preprocessing_service.get_converter", return_value=mock_converter):
        service.convert_single_pdf("my_papers", "paper1.pdf", metadata_backend="none")

    history = service.get_history()
    assert "my_papers" in history["directories"]
    assert "paper1.pdf" in history["directories"]["my_papers"]["files"]
    assert history["directories"]["my_papers"]["last_processed"] is not None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_preprocessing_service.py -v`
Expected: FAIL — `get_converter` not imported in preprocessing_service yet

**Step 3: Refactor `preprocessing_service.py`**

Key changes:
1. Remove Docling imports and converter setup from `__init__`
2. Import `get_converter` from `pdf_converter_base`
3. Import `DoclingService` for asset extraction (which needs the full converter)
4. Replace `convert_single_pdf` branching with `get_converter(backend)`
5. Replace `extract_assets` to use `DoclingService` directly
6. Remove `_convert_with_pymupdf`, `_extract_metadata_from_markdown`, `_extract_paper_metadata`, `_parse_authors`, `_extract_tables`, `_extract_images`, and `_BOILERPLATE_HEADERS`

The refactored `preprocessing_service.py`:

```python
import json
import threading
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional

from app.core.config import settings
from app.services.pdf_converter_base import get_converter
from app.services.paper_metadata_api_service import enrich_metadata as _api_enrich

# Ensure backend modules are imported so they register themselves
import app.services.docling_service  # noqa: F401
import app.services.pymupdf4llm_service  # noqa: F401

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

        backend: registered converter name (e.g. "docling", "pymupdf")
        metadata_backend: "openalex", "crossref", "semantic_scholar", or "none"
        """
        source_path = self.pdf_input_dir / dir_name / filename
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {dir_name}/{filename}")

        output_dir = self.preprocessed_dir / dir_name
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = source_path.stem
        converter = get_converter(backend)

        # Use convert_and_extract if available (avoids double conversion)
        if hasattr(converter, "convert_and_extract"):
            markdown_content, paper_meta = converter.convert_and_extract(source_path, stem)
        else:
            markdown_content = converter.convert_to_markdown(source_path)
            paper_meta = converter.extract_metadata(source_path, stem)

        # Write markdown
        md_path = output_dir / f"{stem}.md"
        md_path.write_text(markdown_content, encoding="utf-8")

        # Write metadata
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

        Uses DoclingService directly since only Docling supports asset extraction.
        """
        from app.services.docling_service import DoclingService

        source_path = self.pdf_input_dir / dir_name / filename
        if not source_path.exists():
            raise FileNotFoundError(f"PDF not found: {dir_name}/{filename}")

        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        metadata_path = output_dir / f"{stem}_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadata not found — preprocess {filename} first")

        docling = DoclingService()
        doc = docling.convert_full(source_path)

        tables_dir = output_dir / f"{stem}_tables"
        table_info = docling.extract_tables(doc, tables_dir)

        images_dir = output_dir / f"{stem}_images"
        image_info = docling.extract_images(doc, images_dir)

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
        """Delete the preprocessed output for a single PDF."""
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

        self._remove_from_history(dir_name, filename)

        return {"filename": filename, "deleted_files": deleted}

    def get_assets(self, dir_name: str, filename: str) -> dict:
        """Get tables and images info for a processed PDF."""
        import re

        stem = Path(filename).stem
        output_dir = self.preprocessed_dir / dir_name
        meta_path = output_dir / f"{stem}_metadata.json"

        if not meta_path.exists():
            return {"tables": [], "images": [], "paper_metadata": {}}

        metadata = json.loads(meta_path.read_text(encoding="utf-8"))

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
        if not self.history_path.exists():
            return {"directories": {}}
        return json.loads(self.history_path.read_text(encoding="utf-8"))

    def _update_history(self, dir_name: str, filename: str):
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_preprocessing_service.py -v`
Expected: All PASSED

**Step 5: Commit**

```bash
git add backend/app/services/preprocessing_service.py tests/unit/test_preprocessing_service.py
git commit -m "refactor: PreprocessingService delegates to converter backends"
```

---

### Task 5: Refactor `PDFProcessor` to use converter backends

**Files:**
- Modify: `backend/app/services/pdf_processor.py`
- Modify: `tests/unit/test_pdf_processor.py`

**Step 1: Update tests**

Replace `tests/unit/test_pdf_processor.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from app.services.pdf_processor import PDFProcessor
from app.models.paper import PaperMetadata


def test_generate_unique_id():
    processor = PDFProcessor()
    title = "Attention Is All You Need"
    authors = ["Vaswani", "Shazeer"]
    year = 2017

    unique_id = processor.generate_unique_id(title, authors, year)

    assert "Vaswani" in unique_id
    assert "Attention" in unique_id
    assert "2017" in unique_id


def test_process_pdf_uses_backend():
    processor = PDFProcessor(backend="pymupdf")

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Test\n\nContent"
    mock_converter.extract_metadata.return_value = {
        "title": "Test",
        "authors": ["Author One"],
        "abstract": "Abstract text",
        "publication_date": "2024",
    }

    with patch("app.services.pdf_processor.get_converter", return_value=mock_converter):
        result = processor.process_pdf(Path("/fake/paper.pdf"), "test-123")

    assert result["metadata"].title == "Test"
    assert result["text"] == "# Test\n\nContent"
    mock_converter.convert_to_markdown.assert_called_once()


def test_process_pdf_defaults_to_docling():
    processor = PDFProcessor()

    mock_converter = MagicMock()
    mock_converter.convert_to_markdown.return_value = "# Title"
    mock_converter.extract_metadata.return_value = {
        "title": "Title",
        "authors": [],
        "abstract": None,
        "publication_date": None,
    }

    with patch("app.services.pdf_processor.get_converter", return_value=mock_converter) as mock_get:
        processor.process_pdf(Path("/fake/paper.pdf"), "test-456")

    mock_get.assert_called_once_with("docling")
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_pdf_processor.py -v`
Expected: FAIL — `get_converter` not used in pdf_processor yet

**Step 3: Refactor `pdf_processor.py`**

```python
import re
from pathlib import Path
from typing import Optional
from app.models.paper import PaperMetadata
from app.services.pdf_converter_base import get_converter

# Ensure backend modules are imported so they register themselves
import app.services.docling_service  # noqa: F401
import app.services.pymupdf4llm_service  # noqa: F401


class PDFProcessor:
    """Service for processing PDFs with pluggable backends"""

    def __init__(self, backend: str = "docling"):
        self.backend = backend

    def generate_unique_id(
        self,
        title: Optional[str],
        authors: Optional[list[str]],
        year: Optional[int]
    ) -> str:
        """Generate human-readable unique ID from paper metadata."""
        parts = []

        if authors and len(authors) > 0:
            author = authors[0].split()[-1]
            author = re.sub(r'[^a-zA-Z]', '', author)
            parts.append(author)

        if title:
            title_words = title.split()[:2]
            title_part = ''.join(w.capitalize() for w in title_words)
            title_part = re.sub(r'[^a-zA-Z]', '', title_part)
            parts.append(title_part)

        if year:
            parts.append(str(year))

        if not parts:
            return "UnknownPaper"

        return ''.join(parts)

    def process_pdf(self, pdf_path: Path, paper_id: str) -> dict:
        """Process PDF and extract all content."""
        converter = get_converter(self.backend)

        text_content = converter.convert_to_markdown(pdf_path)
        raw_meta = converter.extract_metadata(pdf_path, paper_id)

        year = None
        if raw_meta.get("publication_date"):
            year_match = re.search(r'\d{4}', str(raw_meta["publication_date"]))
            if year_match:
                year = int(year_match.group())

        unique_id = self.generate_unique_id(
            raw_meta.get("title"), raw_meta.get("authors", []), year
        )

        metadata = PaperMetadata(
            paper_id=paper_id,
            title=raw_meta.get("title", "Untitled"),
            authors=raw_meta.get("authors", []),
            year=year,
            abstract=raw_meta.get("abstract"),
            unique_id=unique_id,
            publication_date=raw_meta.get("publication_date"),
        )

        return {
            "metadata": metadata,
            "text": text_content,
            "tables": [],
            "figures": []
        }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_pdf_processor.py -v`
Expected: All PASSED

**Step 5: Run all tests to check nothing is broken**

Run: `pytest tests/unit/ -v`
Expected: All PASSED

**Step 6: Commit**

```bash
git add backend/app/services/pdf_processor.py tests/unit/test_pdf_processor.py
git commit -m "refactor: PDFProcessor delegates to converter backends"
```

---

### Task 6: Update integration tests and verify full suite

**Files:**
- Modify: `tests/integration/test_pdf_processing.py` (only if it breaks — the mock interface for `PDFProcessor` hasn't changed, just its internals)

**Step 1: Run integration tests**

Run: `pytest tests/ -v --timeout=60`
Expected: All PASSED (integration tests mock `PDFProcessor` at the spec level, so the interface hasn't changed)

**Step 2: If anything fails, fix imports or mocks**

The `PDFProcessor()` constructor now takes an optional `backend` param with default `"docling"`, so `PDFProcessor()` still works as before. `Mock(spec=PDFProcessor)` should still work.

**Step 3: Commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: update integration tests for converter refactor"
```

---

### Task 7: Clean up — remove `_parse_authors` duplicates

**Step 1: Verify no remaining references to old methods**

Search for any lingering `_parse_authors`, `_convert_with_pymupdf`, `_extract_metadata_from_markdown`, `_extract_paper_metadata` in `preprocessing_service.py`:

Run: `grep -n "_parse_authors\|_convert_with_pymupdf\|_extract_metadata_from_markdown\|_extract_paper_metadata\|_extract_tables\|_extract_images\|_BOILERPLATE" backend/app/services/preprocessing_service.py`
Expected: No matches

**Step 2: Run full test suite one final time**

Run: `pytest tests/ -v`
Expected: All PASSED

**Step 3: Final commit**

```bash
git add -u
git commit -m "chore: clean up after converter backend extraction"
```
