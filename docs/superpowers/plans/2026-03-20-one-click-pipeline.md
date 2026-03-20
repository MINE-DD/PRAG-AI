# One-Click Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-directory "⚡ Pipeline" button that converts all unconverted PDFs, creates a collection, and ingests everything in one step, streaming live progress to the UI.

**Architecture:** New `backend/app/api/pipeline.py` endpoint that orchestrates existing services (PreprocessingService → CollectionService → IngestionService) and streams SSE events. New pipeline panel in `frontend-web/js/pdf-tab.js` with progress bar driven by those events. Zero changes to existing endpoints.

**Tech Stack:** FastAPI + SSE (StreamingResponse), Vue 3 reactive, existing services (PreprocessingService, CollectionService, IngestionService via get_ingestion_service factory).

**IMPORTANT: Do NOT commit any changes — user will review before committing.**

---

### Task 1: Backend pipeline endpoint

**Files:**
- Create: `backend/app/api/pipeline.py`
- Modify: `backend/app/main.py` (lines 3, 36)
- Test: `tests/integration/test_pipeline_api.py`

**Context:**
- `PreprocessingService.scan_directory(dir_name)` returns `[{"filename": str, "processed": bool}]`
- `PreprocessingService.convert_single_pdf(dir_name, filename, backend, metadata_backend)` raises on failure
- `CollectionService(qdrant=QdrantService(url=settings.qdrant_url)).create_collection(name, search_type)` returns a `Collection` object; raises `ValueError` if already exists
- `get_ingestion_service(chunk_size, chunk_overlap, chunk_mode)` is importable from `app.api.ingest`
- `ingest_svc.ingest_file(collection_id, md_path, metadata_path)` where paths are strings
- `_safe()` is importable from `app.api.preprocess`; raises HTTP 400 on path traversal
- SSE pattern: `StreamingResponse(generate(), media_type="text/event-stream")` where `generate()` yields `f"data: {json.dumps(event)}\n\n"`
- Test SSE parsing: `events = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]`
- Patch targets: `app.api.pipeline.PreprocessingService`, `app.api.pipeline.CollectionService`, `app.api.pipeline.QdrantService`, `app.api.pipeline.get_ingestion_service`

- [ ] **Step 1: Write the failing tests**

Create `tests/integration/test_pipeline_api.py`:

```python
# tests/integration/test_pipeline_api.py
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_prep(files):
    """files: list of (filename, processed) tuples"""
    mock = MagicMock()
    mock.scan_directory.return_value = [
        {"filename": fn, "processed": proc} for fn, proc in files
    ]
    mock.convert_single_pdf.return_value = {"filename": "x"}
    return mock


def _make_coll(collection_id="my-dir"):
    mock = MagicMock()
    coll = MagicMock()
    coll.collection_id = collection_id
    mock.create_collection.return_value = coll
    return mock


def _make_ingest():
    mock = MagicMock()
    svc = MagicMock()
    svc.ingest_file.return_value = {"chunks": 5}
    mock.return_value = svc
    return mock


def _parse_sse(resp):
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_happy_path_two_files(client):
    """Both files unconverted → convert both, create collection, ingest both → done:true."""
    prep = _make_prep([("a.pdf", False), ("b.pdf", False)])
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    # Patch Path.exists to return True so the ingest step doesn't skip files
    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    assert events[0]["step"] == "scan"
    assert events[0]["to_convert"] == 2
    convert_events = [e for e in events if e.get("step") == "convert"]
    assert len([e for e in convert_events if e["status"] == "converting"]) == 2
    assert any(e.get("done") for e in events)
    done = next(e for e in events if e.get("done"))
    assert done["collection_id"] == "my-dir"
    assert done["converted"] == 2
    assert done["skipped"] == 0
    assert done["ingested"] == 2


def test_skips_already_converted(client):
    """1 converted + 1 not → only 1 convert call, both ingested."""
    prep = _make_prep([("a.pdf", True), ("b.pdf", False)])
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    prep.convert_single_pdf.assert_called_once()  # only 1 convert call
    done = next(e for e in events if e.get("done"))
    assert done["skipped"] == 1
    assert done["converted"] == 1


def test_collection_already_exists(client):
    """Collection already exists → emit exists status, continue to ingest."""
    prep = _make_prep([("a.pdf", True)])
    coll = _make_coll("my-dir")
    coll.create_collection.side_effect = ValueError("already exists")
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    coll_event = next(e for e in events if e.get("step") == "collection")
    assert coll_event["status"] == "exists"
    assert any(e.get("done") for e in events)


def test_convert_error_continues(client):
    """One convert fails → pipeline continues, errors counted."""
    prep = _make_prep([("a.pdf", False), ("b.pdf", False)])
    prep.convert_single_pdf.side_effect = [Exception("conversion failed"), None]
    coll = _make_coll("my-dir")
    ingest_factory = _make_ingest()

    with patch("app.api.pipeline.PreprocessingService", return_value=prep), \
         patch("app.api.pipeline.CollectionService", return_value=coll), \
         patch("app.api.pipeline.QdrantService"), \
         patch("app.api.pipeline.get_ingestion_service", ingest_factory), \
         patch("pathlib.Path.exists", return_value=True):

        resp = client.post("/pipeline/run", json={
            "dir_name": "my-dir",
            "collection_name": "My Dir",
        })

    assert resp.status_code == 200
    events = _parse_sse(resp)
    error_events = [e for e in events if e.get("step") == "convert" and e.get("status") == "error"]
    assert len(error_events) == 1
    done = next(e for e in events if e.get("done"))
    assert done["errors"] >= 1


def test_path_traversal_rejected(client):
    """dir_name with path traversal returns 400."""
    resp = client.post("/pipeline/run", json={
        "dir_name": "../etc",
        "collection_name": "hack",
    })
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && python -m pytest tests/integration/test_pipeline_api.py -v 2>&1 | head -40
```

Expected: FAIL — `404` (route not found) or import error.

- [ ] **Step 3: Create `backend/app/api/pipeline.py`**

```python
# backend/app/api/pipeline.py
"""One-click pipeline: convert → create collection → ingest, streamed as SSE."""

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.config import settings
from app.services.preprocessing_service import PreprocessingService
from app.services.collection_service import CollectionService
from app.services.qdrant_service import QdrantService
from app.api.ingest import get_ingestion_service
from app.api.preprocess import _safe

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


@router.post("/pipeline/run")
def run_pipeline(req: PipelineRequest):
    """Convert all unconverted PDFs in a directory, create a collection, ingest all. Streams SSE."""
    dir_name = _safe(req.dir_name)

    prep_svc = PreprocessingService()
    try:
        files = prep_svc.scan_directory(dir_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    already_done = [f for f in files if f["processed"]]
    to_convert   = [f for f in files if not f["processed"]]

    def generate():
        # ── Step 1: scan ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'step': 'scan', 'total': len(files), 'to_convert': len(to_convert), 'already_done': len(already_done)})}\n\n"

        # ── Step 2: convert ───────────────────────────────────────────────────
        converted = 0
        errors = 0
        successfully_converted = set()

        for i, f in enumerate(to_convert, start=1):
            fn = f["filename"]
            yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'converting'})}\n\n"
            try:
                prep_svc.convert_single_pdf(
                    dir_name, fn,
                    backend=req.pdf_backend,
                    metadata_backend=req.metadata_backend,
                )
                successfully_converted.add(fn)
                converted += 1
                yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'done'})}\n\n"
            except Exception as e:
                errors += 1
                yield f"data: {json.dumps({'step': 'convert', 'file': fn, 'index': i, 'total': len(to_convert), 'status': 'error', 'message': str(e)})}\n\n"

        # ── Step 3: create collection ─────────────────────────────────────────
        collection_svc = CollectionService(qdrant=QdrantService(url=settings.qdrant_url))
        # Derive collection_id (same slug as CollectionService uses)
        collection_id = re.sub(r'[^a-z0-9]+', '-', req.collection_name.lower()).strip('-')

        try:
            result = collection_svc.create_collection(
                name=req.collection_name, search_type=req.search_type
            )
            collection_id = result.collection_id
            yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'created'})}\n\n"
        except ValueError:
            # Collection already exists — use derived ID and continue
            yield f"data: {json.dumps({'step': 'collection', 'collection_id': collection_id, 'status': 'exists'})}\n\n"
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
        ingest_errors = 0
        # Ingest already-converted + successfully converted in this run
        all_to_ingest = [f["filename"] for f in already_done] + list(successfully_converted)
        total_ingest = len(all_to_ingest)

        for i, filename in enumerate(all_to_ingest, start=1):
            stem = Path(filename).stem
            preprocessed = Path(settings.preprocessed_dir) / dir_name
            md_path       = preprocessed / f"{stem}.md"
            metadata_path = preprocessed / f"{stem}_metadata.json"

            if not md_path.exists():
                continue  # skip if .md somehow missing

            yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'ingesting'})}\n\n"
            try:
                ingest_svc.ingest_file(
                    collection_id=collection_id,
                    md_path=str(md_path),
                    metadata_path=str(metadata_path) if metadata_path.exists() else None,
                )
                ingested += 1
                yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'done'})}\n\n"
            except Exception as e:
                ingest_errors += 1
                errors += 1
                yield f"data: {json.dumps({'step': 'ingest', 'file': f'{stem}.md', 'index': i, 'total': total_ingest, 'status': 'error', 'message': str(e)})}\n\n"

        # ── Step 5: done ──────────────────────────────────────────────────────
        yield f"data: {json.dumps({'done': True, 'collection_id': collection_id, 'converted': converted, 'skipped': len(already_done), 'ingested': ingested, 'errors': errors})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Register router in `backend/app/main.py`**

In `backend/app/main.py`, change line 3:
```python
# Before:
from app.api import health, collections, papers, rag, summarize, compare, preprocess, ingest, settings as settings_api, zotero

# After:
from app.api import health, collections, papers, rag, summarize, compare, preprocess, ingest, settings as settings_api, zotero, pipeline
```

Add after line 36 (`app.include_router(zotero.router, ...)`):
```python
app.include_router(pipeline.router, tags=["pipeline"])
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && python -m pytest tests/integration/test_pipeline_api.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Run full test suite to check no regressions**

```bash
cd /Users/jose/Repos/PRAG-v2 && python -m pytest tests/integration/ -v --ignore=tests/integration/test_ingest_api.py --ignore=tests/integration/test_compare_api.py 2>&1 | tail -20
```

Expected: all pass (test_ingest_api and test_compare_api are pre-existing failures unrelated to this change).

---

### Task 2: Frontend pipeline panel

**Files:**
- Modify: `frontend-web/js/pdf-tab.js`

**Context:** The file has a `setup()` function with reactive state declarations (lines 10–31), then functions, then `return {}` (lines 489–505), then a `template` string (line 508+). The directory card template starts at line 642. The directory header is lines 644–673. The expanded file list is lines 675–893.

**No automated tests for Vue — verify manually in browser.**

- [ ] **Step 1: Add pipeline reactive state to `setup()`**

After line 31 (`const ztImportError = ref(null)`), insert:

```js
    // Pipeline state (per directory)
    const pipelineOpen    = reactive({})   // dirName → bool
    const pipelineForm    = reactive({})   // dirName → { collectionName }
    const pipelineRunning = reactive({})   // dirName → bool
    const pipelineEvents  = reactive({})   // dirName → SSE event array
    const pipelineDone    = reactive({})   // dirName → result | null
```

- [ ] **Step 2: Add `openPipeline` and `runPipeline` functions**

After the `runZoteroImport` function (after line 485, before `onMounted`), insert:

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

    async function runPipeline(dirName) {
      pipelineRunning[dirName] = true
      pipelineEvents[dirName]  = []
      pipelineDone[dirName]    = null
      const backendUrl = localStorage.getItem('prag_backend_url') || 'http://localhost:8000'
      try {
        const resp = await fetch(`${backendUrl}/pipeline/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dir_name:         dirName,
            collection_name:  pipelineForm[dirName].collectionName,
            pdf_backend:      localStorage.getItem('prag_pdf_backend')  || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
          }),
        })
        const reader  = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const data = JSON.parse(line.slice(6))
            pipelineEvents[dirName] = [...pipelineEvents[dirName], data]
            if (data.done !== undefined) {
              pipelineDone[dirName] = data
              if (data.done && data.collection_id) {
                // Refresh directory list so new converted files appear
                for (const k of Object.keys(dirFiles)) delete dirFiles[k]
                await loadDirs()
                emit('refresh-collections')
              }
            }
          }
        }
      } catch (e) {
        pipelineDone[dirName] = { done: false, error: e.message }
      } finally {
        pipelineRunning[dirName] = false
      }
    }
```

- [ ] **Step 3: Add new state/functions to the `return {}` object**

In the `return { ... }` block (lines 489–505), add to the end of the return object:

```js
      pipelineOpen, pipelineForm, pipelineRunning, pipelineEvents, pipelineDone,
      openPipeline, runPipeline,
```

The full return should end:
```js
      toggleZotero, selectZoteroCollection, runZoteroImport,
      pipelineOpen, pipelineForm, pipelineRunning, pipelineEvents, pipelineDone,
      openPipeline, runPipeline,
    }
```

- [ ] **Step 4: Add "⚡ Pipeline" button to directory header**

In the directory header template (around line 670, just before the expand chevron `▶`), inside the right-side `<span class="flex items-center gap-8">`, add the pipeline button before the `<span class="chevron"...>` line:

```html
        <button class="btn btn-sm"
                style="background:var(--primary);color:#fff;border-color:var(--primary);font-size:12px"
                @click.stop="openPipeline(dir.name)">
          ⚡ Pipeline
        </button>
```

- [ ] **Step 5: Add pipeline panel below the file list**

After the `v-for="file"` loop (the `</div>` that closes the per-file wrapper) and **before** the `</div>` that closes `v-if="expanded[dir.name]"` — the panel must be inside the expanded guard. In the current file this is before line 892 (`</div>` closing `v-if="expanded"`). Insert the pipeline panel here:

```html
      <!-- Pipeline panel -->
      <div v-if="pipelineOpen[dir.name]"
           style="margin-top:12px;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:6px">
        <div style="font-size:13px;font-weight:600;margin-bottom:8px">⚡ Quick Pipeline</div>
        <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px">
          Converts all unconverted PDFs, creates a collection, and ingests everything in one step.
        </p>

        <!-- Collection name input -->
        <div v-if="!pipelineRunning[dir.name] && !pipelineDone[dir.name]" class="form-group" style="margin-bottom:10px">
          <label style="font-size:12px">Collection name</label>
          <input type="text" v-model="pipelineForm[dir.name].collectionName"
                 style="font-size:13px" placeholder="my-collection" />
        </div>

        <!-- Run button -->
        <button v-if="!pipelineRunning[dir.name] && !pipelineDone[dir.name]"
                class="btn btn-primary btn-sm"
                :disabled="!pipelineForm[dir.name]?.collectionName?.trim()"
                @click="runPipeline(dir.name)">
          Run Pipeline
        </button>

        <!-- Progress -->
        <div v-if="pipelineRunning[dir.name] || (pipelineDone[dir.name] && pipelineEvents[dir.name]?.length)">
          <!-- Progress bar -->
          <div v-if="pipelineRunning[dir.name]" style="margin-bottom:8px">
            <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden">
              <div :style="{
                width: (() => {
                  const scanEvt = pipelineEvents[dir.name]?.find(e => e.step === 'scan')
                  if (!scanEvt) return '2%'
                  const total = (scanEvt.to_convert || 0) + (scanEvt.already_done || 0)
                  const convDone = pipelineEvents[dir.name].filter(e => e.step==='convert' && (e.status==='done'||e.status==='error'||e.status==='skipped')).length
                  const ingDone  = pipelineEvents[dir.name].filter(e => e.step==='ingest'  && (e.status==='done'||e.status==='error')).length
                  const pct = total > 0 ? Math.min(95, ((convDone + ingDone) / (total * 2)) * 100) : 5
                  return pct + '%'
                })(),
                height: '4px', background: 'var(--primary)', transition: 'width .3s'
              }"></div>
            </div>
            <div class="text-sm text-muted" style="margin-top:4px">
              <span class="spinner" style="width:10px;height:10px;border-width:2px;margin-right:4px"></span>
              {{ (() => {
                const last = [...(pipelineEvents[dir.name] || [])].reverse().find(e => e.step && e.status && e.status !== 'done' && e.status !== 'skipped')
                if (!last) return 'Starting…'
                if (last.step === 'convert') return `Converting ${last.file}…`
                if (last.step === 'collection') return 'Creating collection…'
                if (last.step === 'ingest') return `Ingesting ${last.file}…`
                return 'Running…'
              })() }}
            </div>
          </div>

          <!-- Done: success -->
          <div v-if="pipelineDone[dir.name]?.done"
               style="padding:10px;background:#f0fff4;border:1px solid var(--success);border-radius:4px;font-size:13px">
            <div style="color:var(--success);font-weight:600;margin-bottom:4px">✓ Pipeline complete</div>
            <div class="text-muted">
              Collection <code>{{ pipelineDone[dir.name].collection_id }}</code> —
              {{ pipelineDone[dir.name].ingested }} ingested,
              {{ pipelineDone[dir.name].converted }} converted,
              {{ pipelineDone[dir.name].skipped }} skipped
              <span v-if="pipelineDone[dir.name].errors > 0" style="color:var(--warning)">
                , {{ pipelineDone[dir.name].errors }} errors
              </span>
            </div>
            <div style="margin-top:8px;display:flex;gap:8px">
              <button class="btn btn-secondary btn-sm"
                      @click="() => { pipelineDone[dir.name] = null; pipelineEvents[dir.name] = [] }">
                Run again
              </button>
            </div>
          </div>

          <!-- Done: error -->
          <div v-else-if="pipelineDone[dir.name] && !pipelineDone[dir.name].done"
               class="alert alert-error" style="margin:0">
            Pipeline failed: {{ pipelineDone[dir.name].error }}
            <button class="btn btn-secondary btn-sm" style="margin-left:8px"
                    @click="() => { pipelineDone[dir.name] = null; pipelineEvents[dir.name] = [] }">
              Retry
            </button>
          </div>
        </div>
      </div>
```

- [ ] **Step 6: Manual verification**

Start backend and open the app. For a directory with unconverted PDFs:

1. Click "⚡ Pipeline" on a directory — panel opens with collection name pre-filled
2. Click "Run Pipeline" — progress bar appears, status line updates per file
3. On completion — green banner shows collection ID + counts
4. Check Collections tab — new collection appears
5. Verify Explore Document tab shows the ingested papers

Also verify: clicking "⚡ Pipeline" again collapses the panel.
