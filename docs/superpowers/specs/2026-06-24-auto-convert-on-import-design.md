# Auto-Convert on Import Design

**Date:** 2026-06-24  
**Branch:** 27-improve-rag-service  
**Status:** Approved

## Summary

Merge PDF import with Markdown conversion into a single step. Both the Zotero import panel and the file upload panel get an **"Auto-convert to .md"** checkbox (checked by default). When checked, conversion runs automatically after import/upload completes. The `PipelinePanel` component and `/pipeline/run` endpoint are removed entirely — users create collections manually from the Collections tab, which already supports picking a converted directory.

## New User Flow

1. **Zotero panel**: select papers → click Import → PDFs download + convert sequentially in one stream → done
2. **Upload panel**: select files → click Upload → files saved → conversion stream runs automatically → done
3. **Collections tab** (unchanged): pick the converted folder → name collection → create → ingests everything

## Backend Changes

### 1. Modify `POST /zotero/import`

- Add `auto_convert: bool = False` to `ImportRequest`
- Add `pdf_backend: str = "pymupdf"`, `metadata_backend: str = "openalex"`, `document_type: str = "default"` to `ImportRequest`
- In `generate()`: after a successful PDF download (`status: done`), if `auto_convert` is true, call `PreprocessingService.convert_single_pdf()` and yield a `convert` event per file:
  ```json
  {"filename": "paper.pdf", "status": "converting"}
  {"filename": "paper.pdf", "status": "converted"}
  {"filename": "paper.pdf", "status": "convert_error", "message": "..."}
  ```
- Conversion errors are non-fatal — log and continue to next file
- The final `{"done": true}` event is unchanged

### 2. New `POST /preprocess/convert-batch`

New endpoint in `backend/app/api/preprocess.py`.

Request body:
```json
{
  "dir_name": "my_papers_zt",
  "backend": "pymupdf",
  "metadata_backend": "openalex",
  "document_type": "default"
}
```

Behaviour:
- Scan the directory for unconverted PDFs (`.md` does not exist yet)
- Convert sequentially, streaming SSE events:
  ```json
  {"filename": "paper.pdf", "status": "converting", "index": 1, "total": 3}
  {"filename": "paper.pdf", "status": "done",       "index": 1, "total": 3}
  {"filename": "paper.pdf", "status": "skipped",    "index": 1, "total": 3}
  {"filename": "paper.pdf", "status": "error",      "index": 1, "total": 3, "message": "..."}
  {"done": true, "converted": 2, "skipped": 1, "errors": 0}
  ```
- Already-converted PDFs (`.md` exists) emit `skipped` and are not re-processed
- No parallelism — sequential, same as current pipeline behaviour

### 3. Remove `/pipeline/run`

Delete `backend/app/api/pipeline.py` and remove its router registration from `main.py` (or wherever it is registered).

## Frontend Changes

### 4. `ZoteroImportPanel` (`zotero-import-panel.js`)

- Add `autoConvert = ref(true)`
- Add `convertProgress = reactive({})` to track per-file convert status
- Add checkbox before the Import button:
  ```html
  <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:8px">
    <input type="checkbox" v-model="autoConvert" />
    Auto-convert to .md
  </label>
  ```
- In `runImport()`: include `auto_convert`, `pdf_backend`, `metadata_backend`, `document_type` in the POST body (read backend prefs from `localStorage` same as PipelinePanel did)
- Handle new SSE events: `converting` and `converted`/`convert_error` — update `convertProgress[filename]`
- In the item list, show convert status below the download status when `autoConvert` is true
- Remove `PipelinePanel` import and usage; after `ztDone`, show a simple success message with a "Go to Collections" hint instead

### 5. `UploadPanel` (`upload-panel.js`)

- Add `autoConvert = ref(true)` and `converting = ref(false)`, `convertEvents = ref([])`
- Add checkbox (same style as above) visible at step 2 (after files are selected)
- In `uploadFiles()`: after the upload API call succeeds, if `autoConvert` is true, call `runConvertBatch(dir)` before emitting `files-uploaded`
- `runConvertBatch(dir)`: streams `/preprocess/convert-batch`, populates `convertEvents`, shows inline progress
- Remove `PipelinePanel` import and usage; after conversion (or upload if `autoConvert` is false), show success + "Go to Collections" hint

### 6. Remove `PipelinePanel` (`pipeline-panel.js`)

Delete the file. It is only used by `ZoteroImportPanel` and `UploadPanel`, both of which are updated above.

## Files Changed

| File | Action |
|------|--------|
| `backend/app/api/zotero.py` | Modify — add `auto_convert` + convert inline |
| `backend/app/api/preprocess.py` | Add `ConvertBatchRequest` model + `/preprocess/convert-batch` endpoint |
| `backend/app/api/pipeline.py` | **Delete** |
| `frontend-web/js/components/pdf/zotero-import-panel.js` | Modify — checkbox, handle convert events, remove PipelinePanel |
| `frontend-web/js/components/pdf/upload-panel.js` | Modify — checkbox, call convert-batch, remove PipelinePanel |
| `frontend-web/js/components/pdf/pipeline-panel.js` | **Delete** |

## Out of Scope

- Parallelizing batch conversion (can be added later)
- Changes to the Collections tab or ingest flow
- Changes to the PDF metadata panel or file browser
