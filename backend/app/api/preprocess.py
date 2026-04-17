import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import load_config, settings
from app.services.ollama_service import OllamaService
from app.services.preprocessing_service import PreprocessingService
from app.services.prompt_service import get_prompt_service

router = APIRouter()


def _safe(name: str) -> str:
    """Reject path traversal — keep only the final component of any path."""
    safe = Path(name).name
    if not safe or safe in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid path component")
    return safe


class ScanRequest(BaseModel):
    dir_name: str


class ConvertRequest(BaseModel):
    dir_name: str
    filename: str
    backend: str = "pymupdf"  # "docling", "pymupdf", or "ollama_vlm"
    metadata_backend: str = (
        "openalex"  # "openalex", "crossref", "semantic_scholar", "none"
    )
    document_type: str = "default"  # matches a vlm_extract/vlm_metadata YAML name


def get_preprocessing_service() -> PreprocessingService:
    return PreprocessingService(prompt_service=get_prompt_service())


@router.get("/preprocess/directories")
def list_directories():
    """List available PDF directories."""
    service = get_preprocessing_service()
    return service.list_directories()


@router.post("/preprocess/scan")
def scan_directory(request: ScanRequest):
    """Scan a directory for PDFs and their processing status."""
    dir_name = _safe(request.dir_name)
    service = get_preprocessing_service()
    try:
        files = service.scan_directory(dir_name)
        return {"dir_name": dir_name, "files": files}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/preprocess/convert")
def convert_pdf(request: ConvertRequest):
    """Convert a single PDF to markdown + metadata."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    try:
        result = service.convert_single_pdf(
            dir_name,
            filename,
            backend=request.backend,
            metadata_backend=request.metadata_backend,
            document_type=request.document_type,
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")


@router.post("/preprocess/extract-assets")
def extract_assets(request: ConvertRequest):
    """Extract tables and images from an already-preprocessed PDF."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    try:
        result = service.extract_assets(dir_name, filename)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Asset extraction error: {str(e)}")


class EnrichRequest(BaseModel):
    dir_name: str
    filename: str
    backend: str = "openalex"  # "openalex", "crossref", "semantic_scholar"


@router.post("/preprocess/enrich-metadata")
def enrich_metadata(request: EnrichRequest):
    """Enrich metadata for a processed PDF using an external API."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    try:
        result = service.enrich_with_api(dir_name, filename, request.backend)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Enrichment error: {str(e)}")


class DoiLookupRequest(BaseModel):
    dir_name: str
    filename: str
    doi: str


@router.post("/preprocess/enrich-by-doi")
def enrich_by_doi(request: DoiLookupRequest):
    """Enrich metadata for a processed PDF by DOI lookup (tries CrossRef → OpenAlex → Semantic Scholar)."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    try:
        result = service.enrich_with_doi(dir_name, filename, request.doi)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DOI lookup error: {str(e)}")


class DeleteRequest(BaseModel):
    dir_name: str
    filename: str


@router.post("/preprocess/delete")
def delete_preprocessed(request: DeleteRequest):
    """Delete preprocessed output for a single PDF."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    result = service.delete_preprocessed(dir_name, filename)
    return result


class DeleteDirRequest(BaseModel):
    dir_name: str


@router.post("/preprocess/delete-directory")
def delete_directory(request: DeleteDirRequest):
    """Delete an entire PDF directory and all its preprocessed output."""
    dir_name = _safe(request.dir_name)
    service = get_preprocessing_service()
    pdf_dir = Path(settings.pdf_input_dir) / dir_name
    prep_dir = service.preprocessed_dir / dir_name
    if not pdf_dir.is_dir() and not prep_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory '{dir_name}' not found")
    return service.delete_directory(dir_name)


@router.post("/preprocess/delete-pdf")
def delete_source_pdf(request: DeleteRequest):
    """Delete the source PDF (and its preprocessed output if any)."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    pdf_path = Path(settings.pdf_input_dir) / dir_name / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    try:
        service.delete_preprocessed(dir_name, filename)
    except Exception:
        pass
    pdf_path.unlink()
    return {"deleted": filename, "dir_name": dir_name}


@router.get("/preprocess/history")
def get_history():
    """Get preprocessing history."""
    service = get_preprocessing_service()
    return service.get_history()


class AssetsRequest(BaseModel):
    dir_name: str
    filename: str


@router.post("/preprocess/assets")
def get_assets(request: AssetsRequest):
    """Get tables and images info for a processed PDF."""
    dir_name, filename = _safe(request.dir_name), _safe(request.filename)
    service = get_preprocessing_service()
    return service.get_assets(dir_name, filename)


class UpdateMetadataRequest(BaseModel):
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    journal: str | None = None
    doi: str | None = None
    abstract: str | None = None


@router.patch("/preprocess/{dir_name}/{filename}/metadata")
def update_metadata_manually(
    dir_name: str, filename: str, request: UpdateMetadataRequest
):
    """Manually override metadata fields and mark source as 'manual'."""
    dir_name, filename = _safe(dir_name), _safe(filename)
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    meta_path = Path(settings.preprocessed_dir) / dir_name / f"{stem}_metadata.json"

    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Metadata file not found")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    if request.title is not None:
        meta["title"] = request.title
    if request.authors is not None:
        meta["authors"] = request.authors
    if request.year is not None:
        meta["publication_date"] = str(request.year)
    if request.journal is not None:
        meta["journal"] = request.journal
    if request.doi is not None:
        meta["doi"] = request.doi
    if request.abstract is not None:
        meta["abstract"] = request.abstract
    meta["metadata_source"] = "manual"

    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Mirror to any collection metadata copies that share the same paper_id
    paper_id = meta.get("paper_id")
    if paper_id:
        for coll_dir in Path(settings.data_dir).iterdir():
            if not coll_dir.is_dir():
                continue
            coll_meta_path = coll_dir / "metadata" / f"{paper_id}.json"
            if not coll_meta_path.exists():
                continue
            coll_meta = json.loads(coll_meta_path.read_text(encoding="utf-8"))
            if request.title is not None:
                coll_meta["title"] = request.title
            if request.authors is not None:
                coll_meta["authors"] = request.authors
            if request.year is not None:
                coll_meta["publication_date"] = str(request.year)
            if request.journal is not None:
                coll_meta["journal"] = request.journal
            if request.doi is not None:
                coll_meta["doi"] = request.doi
            if request.abstract is not None:
                coll_meta["abstract"] = request.abstract
            coll_meta["metadata_source"] = "manual"
            coll_meta_path.write_text(json.dumps(coll_meta, indent=2), encoding="utf-8")

    return {"success": True, "metadata_source": "manual"}


@router.get("/preprocess/pdf/{dir_name}/{filename}")
def serve_pdf(dir_name: str, filename: str):
    """Serve the original PDF inline so the browser can open it directly."""
    dir_name, filename = _safe(dir_name), _safe(filename)
    pdf_path = Path(settings.pdf_input_dir) / dir_name / filename
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        str(pdf_path), media_type="application/pdf", content_disposition_type="inline"
    )


@router.get("/preprocess/download/{dir_name}/{filename}/{file_type}")
def download_output(dir_name: str, filename: str, file_type: str):
    """Download the preprocessed markdown or metadata JSON for a PDF."""
    if file_type not in ("markdown", "metadata"):
        raise HTTPException(
            status_code=400, detail="file_type must be 'markdown' or 'metadata'"
        )

    dir_name, filename = _safe(dir_name), _safe(filename)
    service = get_preprocessing_service()
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    output_dir = service.preprocessed_dir / dir_name

    if file_type == "markdown":
        path = output_dir / f"{stem}.md"
        media_type = "text/markdown"
        dl_name = f"{stem}.md"
    else:
        path = output_dir / f"{stem}_metadata.json"
        media_type = "application/json"
        dl_name = f"{stem}_metadata.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{file_type} file not found")

    return FileResponse(str(path), media_type=media_type, filename=dl_name)


@router.get("/preprocess/assets/{dir_name}/{filename}/{asset_type}/{asset_file}")
def download_asset(dir_name: str, filename: str, asset_type: str, asset_file: str):
    """Download a specific asset file (table CSV or image PNG)."""
    if asset_type not in ("tables", "images"):
        raise HTTPException(
            status_code=400, detail="asset_type must be 'tables' or 'images'"
        )

    dir_name, filename, asset_file = _safe(dir_name), _safe(filename), _safe(asset_file)
    service = get_preprocessing_service()
    try:
        path = service.get_asset_path(dir_name, filename, asset_type, asset_file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type = "text/csv" if asset_file.endswith(".csv") else "image/png"
    return FileResponse(str(path), media_type=media_type, filename=asset_file)


class AnalyzeTableRequest(BaseModel):
    dir_name: str
    filename: str
    table_file: str


@router.post("/preprocess/analyze-table")
def analyze_table(request: AnalyzeTableRequest):
    """Send a CSV table to the LLM for analysis."""
    dir_name, filename, table_file = (
        _safe(request.dir_name),
        _safe(request.filename),
        _safe(request.table_file),
    )
    service = get_preprocessing_service()
    try:
        path = service.get_asset_path(dir_name, filename, "tables", table_file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not path.exists():
        raise HTTPException(status_code=404, detail="Table file not found")

    csv_content = path.read_text(encoding="utf-8")
    if not csv_content.strip():
        raise HTTPException(status_code=400, detail="Table file is empty")

    config = load_config("config.yaml")
    ollama = OllamaService(
        url=settings.ollama_url,
        model=config["models"]["llm"]["model"],
    )

    prompt = (
        "Analyze the following CSV table extracted from a research paper. "
        "Summarize what the table shows, describe the columns, highlight key findings "
        "or notable patterns in the data. Be concise.\n\n"
        f"```csv\n{csv_content}\n```"
    )

    try:
        analysis = ollama.generate(prompt=prompt, temperature=0.3, max_tokens=500)
        return {"analysis": analysis, "table_file": request.table_file}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")


@router.post("/preprocess/upload")
async def upload_pdfs(dir_name: str = Form(...), files: list[UploadFile] = File(...)):
    """Upload multiple PDF files into a pdf_input subdirectory."""
    safe_name = _safe(dir_name)
    target_dir = Path(settings.pdf_input_dir) / safe_name
    target_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for f in files:
        if not f.filename or not f.filename.lower().endswith(".pdf"):
            continue
        dest = target_dir / Path(f.filename).name
        content = await f.read()
        dest.write_bytes(content)
        saved.append(f.filename)

    return {"dir_name": safe_name, "uploaded": len(saved), "files": saved}
