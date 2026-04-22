# backend/app/api/pipeline.py
"""One-click pipeline: convert → create collection → ingest, streamed as SSE."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.ingest import get_ingestion_service
from app.api.preprocess import _safe
from app.core.config import settings
from app.services.collection_service import CollectionService
from app.services.preprocessing_service import PreprocessingService
from app.services.prompt_service import get_prompt_service
from app.services.qdrant_service import QdrantService

router = APIRouter()


class PipelineRequest(BaseModel):
    dir_name: str
    collection_name: str
    pdf_backend: str = "pymupdf"
    metadata_backend: str = "openalex"
    search_type: str = "hybrid"
    chunk_size: int = 500
    chunk_overlap: int = 100
    chunk_mode: str = "tokens"
    document_type: str = "default"  # matches a vlm_extract/vlm_metadata YAML name


@router.post("/pipeline/run")
def run_pipeline(req: PipelineRequest):
    """Convert all unconverted PDFs in a directory, create a collection, ingest all. Streams SSE."""
    dir_name = _safe(req.dir_name)

    prep_svc = PreprocessingService(prompt_service=get_prompt_service())
    try:
        files = prep_svc.scan_directory(dir_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    already_done = [f for f in files if f["processed"]]
    to_convert = [f for f in files if not f["processed"]]

    def generate():
        # ── Step 1: scan ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'step': 'scan', 'total': len(files), 'to_convert': len(to_convert), 'already_done': len(already_done)})}\n\n"

        # ── Step 2: convert ───────────────────────────────────────────────────
        converted = 0
        errors = 0
        successfully_converted = set()

        # Emit skipped events for already-converted files
        for i, f in enumerate(already_done, start=1):
            fn = f["filename"]
            yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(already_done), 'status': 'skipped'})}\n\n"

        for i, f in enumerate(to_convert, start=1):
            fn = f["filename"]
            yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'converting'})}\n\n"
            try:
                prep_svc.convert_single_pdf(
                    dir_name,
                    fn,
                    backend=req.pdf_backend,
                    metadata_backend=req.metadata_backend,
                    document_type=req.document_type,
                )
                successfully_converted.add(fn)
                converted += 1
                yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'done'})}\n\n"
            except Exception as e:
                errors += 1
                yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'error', 'message': str(e)})}\n\n"

        # ── Step 3: create collection ─────────────────────────────────────────
        collection_svc = CollectionService(
            qdrant=QdrantService(url=settings.qdrant_url)
        )
        # Derive collection_id (same slug as CollectionService uses) — used as fallback if ValueError
        collection_id = re.sub(r"[^a-z0-9]+", "-", req.collection_name.lower()).strip(
            "-"
        )

        try:
            result = collection_svc.create_collection(
                name=req.collection_name, search_type=req.search_type
            )
            collection_id = result.collection_id
            yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'created'})}\n\n"
        except ValueError:
            # Collection already exists — retrieve authoritative collection_id from service.
            # isinstance guard: get_collection returns a Collection object; if it somehow
            # returns None or a non-Collection mock, fall back to the locally derived slug.
            existing = collection_svc.get_collection(collection_id)
            if existing and isinstance(existing.collection_id, str):
                collection_id = existing.collection_id
                yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'exists'})}\n\n"
            else:
                yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'exists', 'fallback': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'error', 'message': str(e)})}\n\n"
            yield f"data: {json.dumps({'done': False, 'error': str(e)})}\n\n"
            return

        # ── Step 4: ingest ────────────────────────────────────────────────────
        ingest_svc = get_ingestion_service(
            chunk_size=req.chunk_size,
            chunk_overlap=req.chunk_overlap,
            chunk_mode=req.chunk_mode,
        )

        ingested = 0

        # Build ingest list — only files with an .md that actually exists
        def _ingest_candidates():
            for filename in [f["filename"] for f in already_done] + list(
                successfully_converted
            ):
                stem = Path(filename).stem
                preprocessed = Path(settings.preprocessed_dir) / dir_name
                md_path = preprocessed / f"{stem}.md"
                metadata_path = preprocessed / f"{stem}_metadata.json"
                if md_path.exists():
                    yield filename, stem, md_path, metadata_path

        all_to_ingest = list(_ingest_candidates())
        total_ingest = len(all_to_ingest)

        for i, (_filename, stem, md_path, metadata_path) in enumerate(
            all_to_ingest, start=1
        ):
            yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'ingesting'})}\n\n"
            try:
                ingest_svc.ingest_file(
                    collection_id=collection_id,
                    md_path=str(md_path),
                    metadata_path=str(metadata_path)
                    if metadata_path.exists()
                    else None,
                )
                ingested += 1
                yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'done'})}\n\n"
            except Exception as e:
                errors += 1
                yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'error', 'message': str(e)})}\n\n"

        # ── Step 5: done ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'done': True, 'collection_id': collection_id, 'converted': converted, 'skipped': len(already_done), 'ingested': ingested, 'errors': errors})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
