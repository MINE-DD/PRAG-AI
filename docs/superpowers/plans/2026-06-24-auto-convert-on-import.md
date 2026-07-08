# Auto-Convert on Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge PDF import with Markdown conversion into a single auto-triggered step, and remove the now-redundant pipeline.

**Architecture:** Add a `POST /preprocess/convert-batch` SSE endpoint for batch conversion after file upload. Extend `POST /zotero/import` with an `auto_convert` flag that converts each PDF inline after downloading. Both frontend panels get an "Auto-convert to .md" checkbox (on by default). The `PipelinePanel` component and `/pipeline/run` endpoint are deleted entirely.

**Tech Stack:** Python 3.12, FastAPI, SSE (StreamingResponse), Vue 3 (defineComponent), uv/pytest

## Global Constraints

- Python 3.12, type hints required on all new functions
- Run `uv run --extra dev python -m pytest` for tests
- Run `uv run ruff check && uv run ruff format --check` before committing
- Run `uv run mypy backend/` before committing
- Checkbox label must be exactly: **"Auto-convert to .md"**
- SSE events must use `data: {json}\n\n` format
- No parallelism in conversion — sequential only
- Conversion errors are non-fatal: log, continue, count

---

## File Map

| File | Action |
|------|--------|
| `backend/app/api/preprocess.py` | **Modify** — add `ConvertBatchRequest` + `/preprocess/convert-batch` endpoint |
| `backend/app/api/zotero.py` | **Modify** — add `auto_convert`, `pdf_backend`, `metadata_backend`, `document_type` to `ImportRequest`; convert inline after download |
| `backend/app/main.py` | **Modify** — remove pipeline import and router registration |
| `backend/app/api/pipeline.py` | **Delete** |
| `tests/integration/test_preprocess_api.py` | **Modify** — add tests for `/preprocess/convert-batch` |
| `tests/integration/test_zotero_api.py` | **Modify** — add tests for `auto_convert=true` |
| `tests/integration/test_pipeline_api.py` | **Delete** |
| `frontend-web/js/components/pdf/zotero-import-panel.js` | **Modify** — checkbox, handle convert events, remove PipelinePanel |
| `frontend-web/js/components/pdf/upload-panel.js` | **Modify** — checkbox, call convert-batch stream, remove PipelinePanel |
| `frontend-web/js/components/pdf/pipeline-panel.js` | **Delete** |

---

### Task 1: `/preprocess/convert-batch` endpoint

**Files:**
- Modify: `backend/app/api/preprocess.py`
- Test: `tests/integration/test_preprocess_api.py`

**Interfaces:**
- Produces: `POST /preprocess/convert-batch` accepting `{"dir_name": str, "backend": str, "metadata_backend": str, "document_type": str}`, streaming SSE events:
  - `{"filename": "x.pdf", "status": "converting", "index": 1, "total": 3}`
  - `{"filename": "x.pdf", "status": "done", "index": 1, "total": 3}`
  - `{"filename": "x.pdf", "status": "skipped", "index": 1, "total": 3}`
  - `{"filename": "x.pdf", "status": "error", "index": 1, "total": 3, "message": "..."}`
  - `{"done": true, "converted": N, "skipped": N, "errors": N}`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_preprocess_api.py`:

```python
def test_convert_batch_streams_events(client, tmp_path):
    """POST /preprocess/convert-batch converts unconverted PDFs and streams SSE."""
    from unittest.mock import patch, MagicMock

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    pdf_dir = tmp_path / "pdf_input" / "mydir"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "a.pdf").write_bytes(b"%PDF a")
    (pdf_dir / "b.pdf").write_bytes(b"%PDF b")

    # b.pdf already converted — should be skipped
    prep_dir = tmp_path / "preprocessed" / "mydir"
    prep_dir.mkdir(parents=True)
    (prep_dir / "b.md").write_text("existing")

    mock_svc = MagicMock()
    mock_svc.scan_directory.return_value = [
        {"filename": "a.pdf", "processed": False},
        {"filename": "b.pdf", "processed": True},
    ]
    mock_svc.convert_single_pdf.return_value = {"filename": "a.pdf"}

    with patch("app.api.preprocess.get_preprocessing_service", return_value=mock_svc):
        resp = client.post(
            "/preprocess/convert-batch",
            json={"dir_name": "mydir", "backend": "pymupdf",
                  "metadata_backend": "openalex", "document_type": "default"},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    statuses = [(e.get("filename"), e.get("status")) for e in events if "filename" in e]
    assert ("a.pdf", "converting") in statuses
    assert ("a.pdf", "done") in statuses
    assert ("b.pdf", "skipped") in statuses
    done_event = next(e for e in events if e.get("done") is True)
    assert done_event["converted"] == 1
    assert done_event["skipped"] == 1
    assert done_event["errors"] == 0


def test_convert_batch_handles_conversion_error(client, tmp_path):
    """Conversion errors are non-fatal — error event emitted, processing continues."""
    from unittest.mock import patch, MagicMock

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    pdf_dir = tmp_path / "pdf_input" / "mydir"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "bad.pdf").write_bytes(b"%PDF bad")

    mock_svc = MagicMock()
    mock_svc.scan_directory.return_value = [{"filename": "bad.pdf", "processed": False}]
    mock_svc.convert_single_pdf.side_effect = RuntimeError("corrupt pdf")

    with patch("app.api.preprocess.get_preprocessing_service", return_value=mock_svc):
        resp = client.post(
            "/preprocess/convert-batch",
            json={"dir_name": "mydir", "backend": "pymupdf",
                  "metadata_backend": "openalex", "document_type": "default"},
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    error_events = [e for e in events if e.get("status") == "error"]
    assert error_events
    assert "corrupt pdf" in error_events[0]["message"]
    done_event = next(e for e in events if e.get("done") is True)
    assert done_event["errors"] == 1
    assert done_event["converted"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --extra dev python -m pytest tests/integration/test_preprocess_api.py -k "convert_batch" -v
```

Expected: FAIL with `404` or route not found.

- [ ] **Step 3: Add the endpoint to `backend/app/api/preprocess.py`**

Add after the existing `ConvertRequest` model and before `get_preprocessing_service`:

```python
class ConvertBatchRequest(BaseModel):
    dir_name: str
    backend: str = "pymupdf"
    metadata_backend: str = "openalex"
    document_type: str = "default"
```

Add after the `@router.post("/preprocess/convert")` route (anywhere in the file is fine, but keep it near the convert endpoint):

```python
@router.post("/preprocess/convert-batch")
def convert_batch(request: ConvertBatchRequest):
    """Convert all unconverted PDFs in a directory. Streams SSE progress."""
    dir_name = _safe(request.dir_name)
    service = get_preprocessing_service()
    try:
        files = service.scan_directory(dir_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    to_convert = [f for f in files if not f["processed"]]
    already_done = [f for f in files if f["processed"]]
    total = len(files)

    def generate():
        converted = 0
        errors = 0
        idx = 0

        for f in already_done:
            idx += 1
            yield f"data: {json.dumps({'filename': f['filename'], 'status': 'skipped', 'index': idx, 'total': total})}\n\n"

        for f in to_convert:
            idx += 1
            fn = f["filename"]
            yield f"data: {json.dumps({'filename': fn, 'status': 'converting', 'index': idx, 'total': total})}\n\n"
            try:
                service.convert_single_pdf(
                    dir_name,
                    fn,
                    backend=request.backend,
                    metadata_backend=request.metadata_backend,
                    document_type=request.document_type,
                )
                converted += 1
                yield f"data: {json.dumps({'filename': fn, 'status': 'done', 'index': idx, 'total': total})}\n\n"
            except Exception as e:
                errors += 1
                yield f"data: {json.dumps({'filename': fn, 'status': 'error', 'index': idx, 'total': total, 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'done': True, 'converted': converted, 'skipped': len(already_done), 'errors': errors})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --extra dev python -m pytest tests/integration/test_preprocess_api.py -k "convert_batch" -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Run linter and type checker**

```bash
uv run ruff check backend/app/api/preprocess.py && uv run mypy backend/app/api/preprocess.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/preprocess.py tests/integration/test_preprocess_api.py
git commit -m "feat: add /preprocess/convert-batch SSE endpoint"
```

---

### Task 2: Zotero import with `auto_convert`

**Files:**
- Modify: `backend/app/api/zotero.py`
- Test: `tests/integration/test_zotero_api.py`

**Interfaces:**
- Consumes: `PreprocessingService.convert_single_pdf(dir_name, filename, backend, metadata_backend, document_type)` from Task 1 context (already exists in `preprocessing_service.py`)
- Produces: `POST /zotero/import` now accepts additional optional fields `auto_convert: bool = False`, `pdf_backend: str = "pymupdf"`, `metadata_backend: str = "openalex"`, `document_type: str = "default"`. When `auto_convert` is true, emits extra SSE events per file:
  - `{"filename": "x.pdf", "status": "converting"}`
  - `{"filename": "x.pdf", "status": "converted"}`
  - `{"filename": "x.pdf", "status": "convert_error", "message": "..."}`

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_zotero_api.py`:

```python
def test_import_with_auto_convert_emits_convert_events(client, tmp_path):
    """When auto_convert=True, convert events are emitted after each download."""
    from unittest.mock import patch, MagicMock

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    mock_svc = MagicMock()
    mock_svc.convert_single_pdf.return_value = {"filename": "test.pdf"}

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"),
        patch("app.api.zotero.load_config", return_value=_EMPTY_CONFIG),
        patch("app.api.zotero.PreprocessingService", return_value=mock_svc),
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Test",
                "authors": ["Alice"],
                "year": 2023,
                "doi": None,
                "journal": None,
                "abstract": None,
                "attachment": {
                    "type": "cloud",
                    "filename": "test.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
                "auto_convert": True,
                "pdf_backend": "pymupdf",
                "metadata_backend": "openalex",
                "document_type": "default",
            },
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    statuses = {e.get("filename"): e.get("status") for e in events if "filename" in e}
    assert statuses.get("test.pdf") == "converted"
    mock_svc.convert_single_pdf.assert_called_once_with(
        "mycol_zt", "test.pdf",
        backend="pymupdf",
        metadata_backend="openalex",
        document_type="default",
    )


def test_import_auto_convert_error_is_nonfatal(client, tmp_path):
    """A conversion failure emits convert_error but does not stop remaining downloads."""
    from unittest.mock import patch, MagicMock

    settings.pdf_input_dir = str(tmp_path / "pdf_input")
    settings.preprocessed_dir = str(tmp_path / "preprocessed")

    mock_svc = MagicMock()
    mock_svc.convert_single_pdf.side_effect = RuntimeError("bad pdf")

    with (
        patch("app.api.zotero._api_keys", _mock_keys()),
        patch("app.api.zotero._get_user_id", return_value="12345"),
        patch("app.services.zotero_service.list_items") as mock_items,
        patch("app.services.zotero_service.download_pdf", return_value=b"%PDF fake"),
        patch("app.api.zotero.load_config", return_value=_EMPTY_CONFIG),
        patch("app.api.zotero.PreprocessingService", return_value=mock_svc),
    ):
        mock_items.return_value = [
            {
                "item_key": "I1",
                "title": "Test",
                "authors": [],
                "year": None,
                "doi": None,
                "journal": None,
                "abstract": None,
                "attachment": {
                    "type": "cloud",
                    "filename": "test.pdf",
                    "attachment_key": "A1",
                },
            }
        ]
        resp = client.post(
            "/zotero/import",
            json={
                "collection_key": "C1",
                "dir_name": "mycol",
                "item_keys": ["I1"],
                "auto_convert": True,
            },
        )

    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert any(e.get("status") == "convert_error" for e in events)
    assert any(e.get("done") for e in events)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run --extra dev python -m pytest tests/integration/test_zotero_api.py -k "auto_convert" -v
```

Expected: FAIL — `ImportRequest` does not have `auto_convert` field.

- [ ] **Step 3: Modify `backend/app/api/zotero.py`**

Replace the `ImportRequest` model and `import_from_zotero` function. The full new versions:

```python
from app.services.preprocessing_service import PreprocessingService
from app.services.prompt_service import get_prompt_service
```

Add these imports near the top (after existing imports).

Replace `ImportRequest`:

```python
class ImportRequest(BaseModel):
    collection_key: str
    dir_name: str
    item_keys: list[str]
    auto_convert: bool = False
    pdf_backend: str = "pymupdf"
    metadata_backend: str = "openalex"
    document_type: str = "default"
```

Replace the `generate()` inner function inside `import_from_zotero` — add auto-convert block after the `yield f"data: ... 'done' ..."` line for each file. The full updated `generate()`:

```python
    def generate():
        prep_svc = (
            PreprocessingService(prompt_service=get_prompt_service())
            if request.auto_convert
            else None
        )

        for item in selected:
            attachment = item.get("attachment") or {}
            filename = attachment.get("filename", "attachment.pdf")
            attachment_key = attachment.get("attachment_key", "")
            stem = Path(filename).stem

            pdf_path = pdf_dir / filename
            meta_path = prep_dir / f"{stem}_metadata.json"

            yield f"data: {json.dumps({'filename': filename, 'status': 'downloading'})}\n\n"
            try:
                pdf_bytes: bytes | None = None

                # 1. Try Zotero cloud
                try:
                    pdf_bytes = zotero_service.download_pdf(
                        user_id, api_key, attachment_key
                    )
                except RuntimeError:
                    pass

                # 2. Try local Zotero storage
                if pdf_bytes is None and local_storage:
                    local_path = Path(local_storage) / attachment_key / filename
                    if local_path.exists():
                        yield f"data: {json.dumps({'filename': filename, 'status': 'downloading', 'source': 'local'})}\n\n"
                        pdf_bytes = local_path.read_bytes()

                if pdf_bytes is None:
                    raise RuntimeError(
                        "PDF not found in Zotero cloud or local storage. "
                        "Configure a local Zotero storage path in Settings."
                    )

                pdf_path.write_bytes(pdf_bytes)
                meta_path.write_text(
                    json.dumps(normalize_metadata(item), indent=2), encoding="utf-8"
                )
                yield f"data: {json.dumps({'filename': filename, 'status': 'done'})}\n\n"

                # Auto-convert to markdown if requested
                if prep_svc is not None:
                    yield f"data: {json.dumps({'filename': filename, 'status': 'converting'})}\n\n"
                    try:
                        prep_svc.convert_single_pdf(
                            dir_name,
                            filename,
                            backend=request.pdf_backend,
                            metadata_backend=request.metadata_backend,
                            document_type=request.document_type,
                        )
                        yield f"data: {json.dumps({'filename': filename, 'status': 'converted'})}\n\n"
                    except Exception as conv_err:
                        yield f"data: {json.dumps({'filename': filename, 'status': 'convert_error', 'message': str(conv_err)})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'filename': filename, 'status': 'error', 'message': str(e)})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"
```

- [ ] **Step 4: Run all zotero tests**

```bash
uv run --extra dev python -m pytest tests/integration/test_zotero_api.py -v
```

Expected: all pass (existing + 2 new).

- [ ] **Step 5: Run linter and type checker**

```bash
uv run ruff check backend/app/api/zotero.py && uv run mypy backend/app/api/zotero.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/zotero.py tests/integration/test_zotero_api.py
git commit -m "feat: add auto_convert option to /zotero/import"
```

---

### Task 3: Update `ZoteroImportPanel` frontend

**Files:**
- Modify: `frontend-web/js/components/pdf/zotero-import-panel.js`

**Interfaces:**
- Consumes: `POST /zotero/import` now accepts `auto_convert`, `pdf_backend`, `metadata_backend`, `document_type`
- New SSE statuses to handle: `"converting"`, `"converted"`, `"convert_error"`
- Removes: `PipelinePanel` import and usage

- [ ] **Step 1: Replace `zotero-import-panel.js` entirely**

The full replacement (remove PipelinePanel, add checkbox, handle convert events):

```javascript
import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { api } from '../../backend-client.js'

const ZoteroImportPanel = defineComponent({
  name: 'ZoteroImportPanel',
  emits: ['refresh-dirs', 'refresh-collections', 'open-collection', 'close'],

  setup(props, { emit }) {
    const ztCollections   = ref([])
    const ztCollError     = ref(null)
    const ztSelCollection = ref(null)
    const ztItems         = ref([])
    const ztItemsLoading  = ref(false)
    const ztItemsError    = ref(null)
    const ztChecked       = reactive({})
    const ztDirName       = ref('')
    const ztImporting     = ref(false)
    const ztProgress      = reactive({})
    const ztDone          = ref(false)
    const ztImportError   = ref(null)
    const autoConvert     = ref(true)

    const ztCollectionSlug = computed(() =>
      ztDirName.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    )

    async function load() {
      ztCollections.value   = []
      ztCollError.value     = null
      ztSelCollection.value = null
      ztItems.value         = []
      ztDone.value          = false
      ztImportError.value   = null
      Object.keys(ztChecked).forEach(k => delete ztChecked[k])
      Object.keys(ztProgress).forEach(k => delete ztProgress[k])
      try {
        ztCollections.value = await api.get('/zotero/collections')
      } catch (e) {
        ztCollError.value = e.message
      }
    }

    async function selectCollection(collKey, collName) {
      ztSelCollection.value = { key: collKey, name: collName }
      ztDirName.value       = collName.toLowerCase().replace(/\s+/g, '_')
      ztItems.value         = []
      ztItemsError.value    = null
      ztItemsLoading.value  = true
      Object.keys(ztChecked).forEach(k => delete ztChecked[k])
      try {
        const items = await api.get(`/zotero/collections/${collKey}/items`)
        ztItems.value = items
        for (const item of items) {
          if (item.attachment?.type === 'cloud') ztChecked[item.item_key] = true
        }
      } catch (e) {
        ztItemsError.value = e.message
      } finally {
        ztItemsLoading.value = false
      }
    }

    async function runImport() {
      const selectedKeys = Object.entries(ztChecked).filter(([, v]) => v).map(([k]) => k)
      if (!selectedKeys.length) return
      ztImporting.value   = true
      ztDone.value        = false
      ztImportError.value = null
      Object.keys(ztProgress).forEach(k => delete ztProgress[k])
      try {
        const resp = await fetch(`${api.url()}/zotero/import`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            collection_key:   ztSelCollection.value.key,
            dir_name:         ztDirName.value,
            item_keys:        selectedKeys,
            auto_convert:     autoConvert.value,
            pdf_backend:      localStorage.getItem('prag_pdf_backend')   || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend')  || 'openalex',
            document_type:    localStorage.getItem('prag_document_type') || 'default',
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
            if (data.done) { ztDone.value = true; break }
            if (data.filename) ztProgress[data.filename] = { status: data.status, message: data.message }
          }
        }
      } catch (e) {
        ztImportError.value = e.message
      } finally {
        ztImporting.value = false
        if (ztDone.value) emit('refresh-dirs')
      }
    }

    onMounted(load)

    return {
      ztCollections, ztCollError, ztSelCollection,
      ztItems, ztItemsLoading, ztItemsError,
      ztChecked, ztDirName, ztImporting, ztProgress, ztDone, ztImportError,
      autoConvert, ztCollectionSlug,
      selectCollection, runImport,
    }
  },

  template: `
<div class="card" style="margin-bottom:8px">
  <div v-if="ztCollError" class="alert alert-error">
    {{ ztCollError }}
    <span v-if="ztCollError.includes('not configured')"> — Go to Settings to add your Zotero credentials.</span>
  </div>

  <div v-else-if="ztCollections.length === 0" class="text-muted text-sm">Loading collections…</div>

  <div v-else>
    <h3 class="page-title">PDF Files</h3>
    <div class="form-group">
      <label>Collection</label>
      <select class="form-control"
              @change="e => selectCollection(e.target.value, ztCollections.find(c=>c.key===e.target.value)?.name || '')">
        <option value="">— select a collection —</option>
        <option v-for="c in ztCollections" :key="c.key" :value="c.key">{{ c.name }}</option>
      </select>
    </div>

    <div v-if="ztItemsLoading" class="text-muted text-sm">Loading papers…</div>
    <div v-else-if="ztItemsError" class="alert alert-error">{{ ztItemsError }}</div>
    <div v-else-if="ztItems.length">
      <div style="max-height:260px;overflow-y:auto;margin:8px 0;border:1px solid var(--border);border-radius:4px">
        <label v-for="item in ztItems" :key="item.item_key"
               :style="item.attachment.type === 'linked'
                 ? 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;opacity:.5;cursor:default'
                 : 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;cursor:pointer'">
          <input type="checkbox"
                 :disabled="item.attachment.type === 'linked'"
                 :checked="!!ztChecked[item.item_key]"
                 @change="e => ztChecked[item.item_key] = e.target.checked"
                 style="margin-top:2px" />
          <div>
            <div style="font-size:13px;font-weight:500">{{ item.title }}</div>
            <div style="font-size:11px;color:var(--text-muted)">
              {{ (item.authors || []).slice(0,2).join(', ') }}
              <span v-if="(item.authors||[]).length > 2"> et al.</span>
              <span v-if="item.year"> · {{ item.year }}</span>
            </div>
            <div v-if="item.attachment.type === 'linked'"
                 style="font-size:11px;color:var(--warning);margin-top:2px">
              ⚠ Linked file — upload manually from <code>{{ item.attachment.path }}</code>
            </div>
            <div v-if="ztProgress[item.attachment.filename]" style="font-size:11px;margin-top:2px">
              <span v-if="ztProgress[item.attachment.filename].status === 'downloading'">
                <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Downloading…
              </span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'converting'">
                <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Converting…
              </span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'converted'"
                    style="color:var(--success)">✓ Imported &amp; converted</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'done'"
                    style="color:var(--success)">✓ Imported</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'skipped'"
                    style="color:var(--success)">✓ Skipped (already imported)</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'convert_error'"
                    style="color:var(--warning)">⚠ Imported, conversion failed: {{ ztProgress[item.attachment.filename].message }}</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'error'"
                    style="color:var(--danger)">✗ {{ ztProgress[item.attachment.filename].message }}</span>
            </div>
          </div>
        </label>
      </div>

      <div class="form-group" style="margin-bottom:8px">
        <label>Directory name
          <span style="font-size:11px;color:var(--text-muted)"> (<code>_zt</code> will be appended)</span>
        </label>
        <input v-model="ztDirName" class="form-control" placeholder="collection_name" />
      </div>

      <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:10px;cursor:pointer">
        <input type="checkbox" v-model="autoConvert" />
        Auto-convert to .md
      </label>

      <div v-if="ztImportError" class="alert alert-error" style="margin-bottom:8px">{{ ztImportError }}</div>

      <button class="btn btn-primary"
              :disabled="ztImporting || !ztDirName.trim() || !Object.values(ztChecked).some(Boolean)"
              @click="runImport">
        <span v-if="ztImporting"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Importing…</span>
        <span v-else>Import selected</span>
      </button>

      <div v-if="ztDone"
           style="margin-top:12px;padding:10px;background:#f0fff4;border:1px solid var(--success);border-radius:4px;font-size:13px">
        <div style="color:var(--success);font-weight:600;margin-bottom:4px">✓ Import complete</div>
        <div class="text-muted">Go to the <strong>Collections</strong> tab to create a collection from this folder.</div>
      </div>
    </div>
  </div>
</div>
`,
})

export { ZoteroImportPanel }
```

- [ ] **Step 2: Verify no references to `PipelinePanel` remain**

```bash
grep -n "PipelinePanel\|pipeline-panel" frontend-web/js/components/pdf/zotero-import-panel.js
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend-web/js/components/pdf/zotero-import-panel.js
git commit -m "feat: add Auto-convert to .md checkbox to Zotero import panel"
```

---

### Task 4: Update `UploadPanel` frontend

**Files:**
- Modify: `frontend-web/js/components/pdf/upload-panel.js`

**Interfaces:**
- Consumes: `POST /preprocess/convert-batch` SSE stream from Task 1
- Removes: `PipelinePanel` import and usage

- [ ] **Step 1: Replace `upload-panel.js` entirely**

```javascript
import { defineComponent, ref } from 'vue'
import { api } from '../../backend-client.js'

const UploadPanel = defineComponent({
  name: 'UploadPanel',
  emits: ['files-uploaded', 'dismiss'],

  setup(props, { emit }) {
    const uploadDir      = ref('uploads')
    const pendingFiles   = ref(null)
    const fileInputKey   = ref(0)
    const loading        = ref(false)
    const error          = ref(null)
    const autoConvert    = ref(true)
    const converting     = ref(false)
    const convertEvents  = ref([])
    const convertDone    = ref(false)

    function onFileSelect(evt) {
      const files = evt.target.files
      if (!files.length) { pendingFiles.value = null; return }
      pendingFiles.value = files
    }

    async function runConvertBatch(dirName) {
      converting.value    = true
      convertEvents.value = []
      convertDone.value   = false
      try {
        const resp = await fetch(`${api.url()}/preprocess/convert-batch`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dir_name:         dirName,
            backend:          localStorage.getItem('prag_pdf_backend')   || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend')  || 'openalex',
            document_type:    localStorage.getItem('prag_document_type') || 'default',
          }),
        })
        if (!resp.ok) throw new Error(await resp.text())
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
            let data
            try { data = JSON.parse(line.slice(6)) } catch { continue }
            if (data.done) { convertDone.value = true; break }
            if (data.filename) convertEvents.value = [...convertEvents.value, data]
          }
        }
      } catch (e) {
        error.value = `Conversion error: ${e.message}`
      } finally {
        converting.value = false
      }
    }

    async function uploadFiles() {
      if (!pendingFiles.value || !pendingFiles.value.length) return
      const dir = uploadDir.value.trim() || 'uploads'
      const fd  = new FormData()
      fd.append('dir_name', dir)
      for (const f of pendingFiles.value) fd.append('files', f)
      loading.value = true
      error.value   = null
      try {
        await api.upload('/preprocess/upload', fd)
        uploadDir.value    = 'uploads'
        pendingFiles.value = null
        fileInputKey.value++
        if (autoConvert.value) {
          await runConvertBatch(dir)
        }
        emit('files-uploaded', dir)
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    return {
      uploadDir, pendingFiles, fileInputKey, loading, error,
      autoConvert, converting, convertEvents, convertDone,
      onFileSelect, uploadFiles,
    }
  },

  template: `
<div class="card" style="margin-bottom:8px">
  <div v-if="error" class="alert alert-error" style="margin-bottom:8px">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Step 1: choose files -->
  <template v-if="!pendingFiles && !convertDone">
    <div class="form-group" style="margin-bottom:0">
      <label>Choose PDF files</label>
      <input :key="fileInputKey" type="file" accept=".pdf" multiple @change="onFileSelect"
             :disabled="loading" style="font-size:13px;width:100%;padding:6px 0;" />
    </div>
  </template>

  <!-- Step 2: name dir, confirm, checkbox -->
  <template v-else-if="pendingFiles && !converting && !convertDone">
    <div style="margin-bottom:12px;font-size:13px">
      <strong>{{ pendingFiles.length }}</strong> file{{ pendingFiles.length !== 1 ? 's' : '' }} selected
      <button class="btn btn-secondary btn-sm" style="margin-left:8px"
              @click="pendingFiles = null; fileInputKey++">Change</button>
    </div>
    <div class="form-group">
      <label>Directory name</label>
      <input type="text" v-model="uploadDir" placeholder="uploads" />
    </div>
    <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:10px;cursor:pointer">
      <input type="checkbox" v-model="autoConvert" />
      Auto-convert to .md
    </label>
    <button class="btn btn-primary" :disabled="loading" @click="uploadFiles">
      <span v-if="loading"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Uploading…</span>
      <span v-else>Upload {{ pendingFiles.length }} file{{ pendingFiles.length !== 1 ? 's' : '' }}</span>
    </button>
  </template>

  <!-- Step 3: conversion in progress -->
  <template v-else-if="converting">
    <div style="font-size:13px;margin-bottom:8px">
      <span class="spinner" style="width:12px;height:12px;border-width:2px;margin-right:6px"></span>
      Converting to .md…
    </div>
    <div style="font-size:12px;color:var(--text-muted)">
      <div v-for="ev in convertEvents" :key="ev.filename + ev.status">
        <span v-if="ev.status === 'converting'">
          <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> {{ ev.filename }}…
        </span>
        <span v-else-if="ev.status === 'done'" style="color:var(--success)">✓ {{ ev.filename }}</span>
        <span v-else-if="ev.status === 'skipped'" style="color:var(--text-muted)">— {{ ev.filename }} (skipped)</span>
        <span v-else-if="ev.status === 'error'" style="color:var(--danger)">✗ {{ ev.filename }}: {{ ev.message }}</span>
      </div>
    </div>
  </template>

  <!-- Step 4: done -->
  <template v-else-if="convertDone">
    <div style="padding:10px;background:#f0fff4;border:1px solid var(--success);border-radius:4px;font-size:13px">
      <div style="color:var(--success);font-weight:600;margin-bottom:4px">✓ Upload &amp; conversion complete</div>
      <div class="text-muted">Go to the <strong>Collections</strong> tab to create a collection from this folder.</div>
    </div>
    <button class="btn btn-secondary btn-sm" style="margin-top:8px"
            @click="convertDone = false; convertEvents = []">Upload more</button>
  </template>
</div>
`,
})

export { UploadPanel }
```

- [ ] **Step 2: Verify no references to `PipelinePanel` remain**

```bash
grep -n "PipelinePanel\|pipeline-panel" frontend-web/js/components/pdf/upload-panel.js
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend-web/js/components/pdf/upload-panel.js
git commit -m "feat: add Auto-convert to .md checkbox to upload panel"
```

---

### Task 5: Delete pipeline code

**Files:**
- Delete: `backend/app/api/pipeline.py`
- Delete: `frontend-web/js/components/pdf/pipeline-panel.js`
- Delete: `tests/integration/test_pipeline_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Remove pipeline from `backend/app/main.py`**

Remove `pipeline,` from the import block and remove `app.include_router(pipeline.router, tags=["pipeline"])`.

The updated import block (lines 4–16) should be:

```python
from app.api import (
    collections,
    compare,
    health,
    ingest,
    papers,
    preprocess,
    prompts,
    rag,
    summarize,
    zotero,
)
from app.api import settings as settings_api
```

And the router registrations should no longer include the pipeline line.

- [ ] **Step 2: Delete the three files**

```bash
rm backend/app/api/pipeline.py
rm frontend-web/js/components/pdf/pipeline-panel.js
rm tests/integration/test_pipeline_api.py
```

- [ ] **Step 3: Verify no remaining references to pipeline**

```bash
grep -rn "pipeline" backend/ frontend-web/ tests/ --include="*.py" --include="*.js" | grep -v ".venv" | grep -v "__pycache__"
```

Expected: no output.

- [ ] **Step 4: Run full test suite**

```bash
uv run --extra dev python -m pytest -v
```

Expected: all tests pass, no references to deleted pipeline module.

- [ ] **Step 5: Run linter and type checker**

```bash
uv run ruff check && uv run mypy backend/
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py
git rm backend/app/api/pipeline.py frontend-web/js/components/pdf/pipeline-panel.js tests/integration/test_pipeline_api.py
git commit -m "chore: remove pipeline endpoint and PipelinePanel component"
```
