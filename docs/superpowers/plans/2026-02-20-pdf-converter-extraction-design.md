# PDF Converter Backend Extraction

## Problem

`PreprocessingService` has Docling and PyMuPDF conversion logic inlined with `if/else` branching. Adding a new backend (e.g. Marker) requires modifying the orchestration code.

## Design

### Common protocol (`pdf_converter_base.py`)

```python
class PDFConverterBackend(Protocol):
    name: str

    def convert_to_markdown(self, source_path: Path) -> str: ...
    def extract_metadata(self, source_path: Path, fallback_title: str) -> dict: ...
```

A `get_converter(backend: str) -> PDFConverterBackend` factory returns the right implementation from a simple registry dict.

### Backend implementations

- `docling_service.py` — Docling-based. Also exposes `extract_tables()` and `extract_images()` for asset extraction.
- `pymupdf4llm_service.py` — pymupdf4llm-based. Lightweight, text-only.

### Shared utilities

`_parse_authors()` moves to a shared location since both backends use it for metadata extraction.

### PreprocessingService changes

`convert_single_pdf()` replaces the `if backend == "pymupdf"` branch with:

```python
converter = get_converter(backend)
markdown_content = converter.convert_to_markdown(source_path)
paper_meta = converter.extract_metadata(source_path, stem)
```

Asset extraction (`extract_assets`) continues to instantiate `DoclingService` directly since only Docling supports table/image extraction.

### pdf_processor.py

Accepts a `backend` param and delegates to `get_converter()` instead of hardcoding Docling.

### Extensibility

Adding a new backend (e.g. Marker):
1. Create `marker_service.py` implementing `PDFConverterBackend`
2. Add one entry to the registry in `pdf_converter_base.py`
3. No changes to `PreprocessingService` or API layer

### Files unchanged

- `backend/app/api/preprocess.py`
- `backend/app/api/papers.py`
- Frontend code
