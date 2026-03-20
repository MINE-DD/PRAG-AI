# backend/app/api/zotero.py
"""Zotero integration API endpoints."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.api_keys_service import ApiKeysService
from app.services import zotero_service
from app.services.zotero_service import normalize_metadata

router = APIRouter()
_api_keys = ApiKeysService()


def _get_user_id() -> str:
    return _api_keys.get_key("zotero_user_id") or ""


def _require_credentials():
    """Return (user_id, api_key) or raise 400."""
    user_id = _get_user_id()
    api_key = _api_keys.get_key("zotero")
    if not user_id or not api_key:
        raise HTTPException(
            status_code=400,
            detail="Zotero user ID or API key not configured. Go to Settings.",
        )
    return user_id, api_key


@router.get("/zotero/collections")
def list_collections():
    """List all Zotero collections for the configured user."""
    user_id, api_key = _require_credentials()
    try:
        return zotero_service.list_collections(user_id, api_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/zotero/collections/{collection_key}/items")
def list_items(collection_key: str):
    """List items with PDF attachments in a Zotero collection."""
    user_id, api_key = _require_credentials()
    try:
        return zotero_service.list_items(user_id, api_key, collection_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ImportRequest(BaseModel):
    collection_key: str
    dir_name: str
    item_keys: list[str]


@router.post("/zotero/import")
def import_from_zotero(request: ImportRequest):
    """Download selected Zotero PDFs and pre-write metadata. Streams SSE progress."""
    user_id, api_key = _require_credentials()

    # Sanitize dir_name and apply _zt suffix
    safe_dir = Path(request.dir_name).name
    dir_name = f"{safe_dir}_zt"

    pdf_dir  = Path(settings.pdf_input_dir)  / dir_name
    prep_dir = Path(settings.preprocessed_dir) / dir_name
    pdf_dir.mkdir(parents=True, exist_ok=True)
    prep_dir.mkdir(parents=True, exist_ok=True)

    # Build item_key → item map from the collection
    try:
        all_items = zotero_service.list_items(user_id, api_key, request.collection_key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    items_map = {item["item_key"]: item for item in all_items}
    selected = [items_map[k] for k in request.item_keys if k in items_map]

    def generate():
        for item in selected:
            attachment = item.get("attachment") or {}
            filename = attachment.get("filename", "attachment.pdf")
            stem = Path(filename).stem

            pdf_path  = pdf_dir  / filename
            meta_path = prep_dir / f"{stem}_metadata.json"

            yield f"data: {json.dumps({'filename': filename, 'status': 'downloading'})}\n\n"
            try:
                pdf_bytes = zotero_service.download_pdf(user_id, api_key, attachment["attachment_key"])
                pdf_path.write_bytes(pdf_bytes)
                meta_path.write_text(json.dumps(normalize_metadata(item), indent=2), encoding="utf-8")
                yield f"data: {json.dumps({'filename': filename, 'status': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'filename': filename, 'status': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
