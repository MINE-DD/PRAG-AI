# One-Click Pipeline Design

## Goal

Add a "Run Pipeline" shortcut per directory that chains convert → create collection → ingest in one step, with SSE-streamed progress, without changing any existing endpoint or behaviour.

## Architecture

One new backend endpoint (`POST /pipeline/run`) that orchestrates existing services in sequence and streams SSE progress events. One new UI section per directory card in the PDF tab with a collection name field, a progress bar, and a single button. Everything else is untouched.

## Backend: `POST /pipeline/run`

**New file:** `backend/app/api/pipeline.py`

**Request body:**
```python
class PipelineRequest(BaseModel):
    dir_name: str
    collection_name: str        # user-provided; passed to CollectionService.create_collection(name=...)
    pdf_backend: str = "pymupdf"       # matches frontend localStorage default
    metadata_backend: str = "openalex"
    search_type: str = "hybrid"
    chunk_size: int = 500
    chunk_overlap: int = 100
    chunk_mode: str = "tokens"
```

**SSE pattern** (same pattern as `zotero.py`):
```python
from fastapi.responses import StreamingResponse
import json

def generate():
    yield f"data: {json.dumps(event)}\n\n"
    ...

return StreamingResponse(generate(), media_type="text/event-stream")
```

**Service instantiation** (copy patterns from existing API files):
```python
# From collections.py pattern:
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
collection_svc = CollectionService(qdrant=QdrantService(url=settings.qdrant_url))

# From ingest.py — reuse the factory function directly:
from app.api.ingest import get_ingestion_service
ingest_svc = get_ingestion_service(chunk_size=req.chunk_size,
                                    chunk_overlap=req.chunk_overlap,
                                    chunk_mode=req.chunk_mode)
```

**Steps (streamed as SSE):**

### Step 1 — Scan
```python
svc = PreprocessingService()
files = svc.scan_directory(dir_name)
# returns: [{"filename": str, "processed": bool}, ...]
already_done = [f for f in files if f["processed"]]
to_convert   = [f for f in files if not f["processed"]]
yield f"data: {json.dumps({'step':'scan','total':len(files),
    'to_convert':len(to_convert),'already_done':len(already_done)})}\n\n"
```

### Step 2 — Convert (only unprocessed files)
For each file in `to_convert`, call `svc.convert_single_pdf(dir_name, filename, backend, metadata_backend)`.
Files in `already_done` emit a `skipped` status with no conversion call.

```python
# Per file:
yield ... {"step":"convert","file":f,"index":i,"total":len(to_convert),"status":"converting"}
try:
    svc.convert_single_pdf(dir_name, filename, backend=req.pdf_backend,
                           metadata_backend=req.metadata_backend)
    yield ... {"status":"done"}
except Exception as e:
    yield ... {"status":"error","message":str(e)}
    # continue — don't abort on individual conversion error
```

### Step 3 — Create collection
```python
# Check existence first (get_collection returns None if not found):
existing = collection_svc.get_collection(collection_id)
if existing:
    yield ... {"step":"collection","collection_id":collection_id,"status":"exists"}
else:
    try:
        result = collection_svc.create_collection(
            name=req.collection_name, search_type=req.search_type)
        collection_id = result.collection_id   # Collection object, attribute access; dash-slug
        yield ... {"step":"collection","collection_id":collection_id,"status":"created"}
    except Exception as e:
        yield ... {"step":"collection","status":"error","message":str(e)}
        yield ... {"done": False, "error": str(e)}
        return   # abort — can't ingest without a collection
```

Note: `collection_id` comes from the return value of `create_collection()` (or from `get_collection()` when it already exists), never computed independently. CollectionService uses dashes: `re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')`.

### Step 4 — Ingest all files that have a `.md`
```python
# md path construction (matching ingest.py pattern):
md_path = str(Path(settings.preprocessed_dir) / dir_name / f"{stem}.md")
metadata_path = str(Path(settings.preprocessed_dir) / dir_name / f"{stem}_metadata.json")

ingest_svc.ingest_file(collection_id=collection_id,
                       md_path=md_path,
                       metadata_path=metadata_path if Path(metadata_path).exists() else None)
```
Only ingest files whose `.md` exists (i.e., already-done + successfully converted in Step 2).

### Step 5 — Done
```json
{"done": true, "collection_id": "my-papers", "converted": 3, "skipped": 2, "ingested": 5, "errors": 0}
```

**Path safety:** `dir_name` sanitised with `_safe()` (import from `preprocess.py`).

**SSE event shapes summary:**
```json
{"step": "scan",       "total": 5, "to_convert": 3, "already_done": 2}
{"step": "convert",    "file": "paper.pdf",  "index": 1, "total": 3, "status": "converting|done|skipped|error", "message": "..."}
{"step": "collection", "collection_id": "my-papers", "status": "created|exists|error", "message": "..."}
{"step": "ingest",     "file": "paper.md",   "index": 1, "total": 5, "status": "ingesting|done|error", "message": "..."}
{"done": true,  "collection_id": "my-papers", "converted": 3, "skipped": 2, "ingested": 5, "errors": 0}
{"done": false, "error": "Collection creation failed: ..."}
```

## Frontend: pipeline section in pdf-tab.js

Inside each directory card, add a "⚡ Pipeline" button to the directory header row. Clicking it opens a collapsible panel below the file list.

**New reactive state** (add to existing reactive declarations in `setup()`):
```js
const pipelineOpen    = reactive({})   // dirName → bool
const pipelineForm    = reactive({})   // dirName → { collectionName }
const pipelineRunning = reactive({})   // dirName → bool
const pipelineEvents  = reactive({})   // dirName → array of SSE event objects
const pipelineDone    = reactive({})   // dirName → result object | null
```

**`openPipeline(dirName)`** — toggles panel; pre-fills collection name:
```js
function openPipeline(dirName) {
    pipelineOpen[dirName] = !pipelineOpen[dirName]
    if (pipelineOpen[dirName] && !pipelineForm[dirName]) {
        pipelineForm[dirName] = {
            collectionName: dirName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
        }
        pipelineEvents[dirName] = []
        pipelineDone[dirName]   = null
    }
}
```

**`runPipeline(dirName)`** — reads `localStorage` for backend settings (same pattern as `convertFile`), posts to `/pipeline/run`, reads SSE stream, updates `pipelineEvents[dirName]` reactively:
```js
async function runPipeline(dirName) {
    pipelineRunning[dirName] = true
    pipelineEvents[dirName]  = []
    pipelineDone[dirName]    = null
    const body = {
        dir_name: dirName,
        collection_name: pipelineForm[dirName].collectionName,
        pdf_backend:  localStorage.getItem('prag_pdf_backend')  || 'pymupdf',
        metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
    }
    const resp = await fetch(`${backendUrl}/pipeline/run`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
    })
    const reader = resp.body.getReader()
    // parse SSE lines, push to pipelineEvents[dirName], detect done event
    // on done: set pipelineDone[dirName] = event; pipelineRunning[dirName] = false
    // on done with collection_id: emit('refresh-collections')
}
```

**Progress bar:** `(convert_done + ingest_done) / max(1, to_convert + total_files) * 100`
Derived live from `pipelineEvents[dirName]`.

**On success:** green banner — "Pipeline complete. Collection `my-papers` — 5 files ingested." + "Open Collection" button that emits `update:collection` to switch tab.

**`backendUrl`** — read from `localStorage.getItem('prag_backend_url') || 'http://localhost:8000'` (same pattern used elsewhere for SSE fetch calls, e.g. Zotero import in the same file).

## Files changed

| File | Change |
|------|--------|
| `backend/app/api/pipeline.py` | New — pipeline endpoint |
| `backend/app/main.py` | Add `pipeline` router import and `app.include_router()` |
| `frontend-web/js/pdf-tab.js` | Add pipeline state, `openPipeline()`, `runPipeline()`, template section |
| `tests/integration/test_pipeline_api.py` | New — integration tests |

**No other files change.**

## Testing

`test_pipeline_api.py` covers:
1. Happy path: 2 unconverted files → both converted, collection created, both ingested → `done: true`
2. Skip already-converted: 1 converted + 1 not → only 1 conversion call, both ingested
3. Collection already exists: `get_collection()` returns existing → emit `exists`, continue to ingest
4. Convert error on one file: pipeline continues, file counted in `errors`
5. `dir_name` with path traversal: `_safe()` raises 400 before streaming

## Test strategy

Patch at the service level (not HTTP level) to avoid double-instantiation:
- `patch("app.api.pipeline.PreprocessingService")`
- `patch("app.api.pipeline.CollectionService")`
- `patch("app.api.pipeline.get_ingestion_service")`

Parse SSE from `resp.text` the same way `test_zotero_api.py` does:
```python
events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
```
