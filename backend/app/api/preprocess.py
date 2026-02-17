from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.preprocessing_service import PreprocessingService

router = APIRouter()


class ScanRequest(BaseModel):
    dir_name: str


class ConvertRequest(BaseModel):
    dir_name: str
    filename: str
    backend: str = "docling"  # "docling" or "pymupdf"


def get_preprocessing_service() -> PreprocessingService:
    return PreprocessingService()


@router.get("/preprocess/directories")
def list_directories():
    """List available PDF directories."""
    service = get_preprocessing_service()
    return service.list_directories()


@router.post("/preprocess/scan")
def scan_directory(request: ScanRequest):
    """Scan a directory for PDFs and their processing status."""
    service = get_preprocessing_service()
    try:
        files = service.scan_directory(request.dir_name)
        return {"dir_name": request.dir_name, "files": files}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/preprocess/convert")
def convert_pdf(request: ConvertRequest):
    """Convert a single PDF to markdown + metadata."""
    service = get_preprocessing_service()
    try:
        result = service.convert_single_pdf(request.dir_name, request.filename, backend=request.backend)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")


@router.post("/preprocess/extract-assets")
def extract_assets(request: ConvertRequest):
    """Extract tables and images from an already-preprocessed PDF."""
    service = get_preprocessing_service()
    try:
        result = service.extract_assets(request.dir_name, request.filename)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Asset extraction error: {str(e)}")


class DeleteRequest(BaseModel):
    dir_name: str
    filename: str


@router.post("/preprocess/delete")
def delete_preprocessed(request: DeleteRequest):
    """Delete preprocessed output for a single PDF."""
    service = get_preprocessing_service()
    result = service.delete_preprocessed(request.dir_name, request.filename)
    return result


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
    service = get_preprocessing_service()
    return service.get_assets(request.dir_name, request.filename)


@router.get("/preprocess/download/{dir_name}/{filename}/{file_type}")
def download_output(dir_name: str, filename: str, file_type: str):
    """Download the preprocessed markdown or metadata JSON for a PDF."""
    if file_type not in ("markdown", "metadata"):
        raise HTTPException(status_code=400, detail="file_type must be 'markdown' or 'metadata'")

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
        raise HTTPException(status_code=400, detail="asset_type must be 'tables' or 'images'")

    service = get_preprocessing_service()
    try:
        path = service.get_asset_path(dir_name, filename, asset_type, asset_file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")

    media_type = "text/csv" if asset_file.endswith(".csv") else "image/png"
    return FileResponse(str(path), media_type=media_type, filename=asset_file)
