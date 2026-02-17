import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app.services.preprocessing_service import PreprocessingService

router = APIRouter()


class ScanRequest(BaseModel):
    dir_name: str


class ConvertRequest(BaseModel):
    dir_name: str
    filename: str


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
        result = service.convert_single_pdf(request.dir_name, request.filename)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")


class ConvertBatchRequest(BaseModel):
    dir_name: str
    filenames: list[str]
    max_workers: int = 2


def _convert_one(dir_name: str, filename: str) -> dict:
    """Convert a single PDF in its own PreprocessingService instance (thread-safe)."""
    try:
        service = PreprocessingService()
        result = service.convert_single_pdf(dir_name, filename)
        return {"filename": filename, "status": "success", **result}
    except Exception as e:
        return {"filename": filename, "status": "error", "detail": str(e)}


@router.post("/preprocess/convert-batch")
async def convert_batch(request: ConvertBatchRequest):
    """Convert multiple PDFs in parallel, streaming NDJSON results as each completes."""
    workers = min(request.max_workers, 4)
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=workers)

    async def generate():
        futures = {
            loop.run_in_executor(executor, _convert_one, request.dir_name, fname): fname
            for fname in request.filenames
        }
        for coro in asyncio.as_completed(futures):
            result = await coro
            yield json.dumps(result) + "\n"
        executor.shutdown(wait=False)

    return StreamingResponse(generate(), media_type="application/x-ndjson")


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
