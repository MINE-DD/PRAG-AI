# Zotero Integration Design

**Date:** 2026-03-20
**Status:** Approved

## Overview

Allow users to import PDFs from their Zotero library directly into PRAG as an alternative to manual upload. Zotero is used as a PDF + metadata source. The import step downloads PDFs and pre-writes metadata; the user then converts and ingests using the normal flow.

---

## Architecture

```
Frontend (pdf-tab.js)          Backend                        Zotero API
  "Import from Zotero"   →   GET /zotero/collections    →   api.zotero.org
  Pick folder + items    →   GET /zotero/collections/{key}/items
  Click Import           →   POST /zotero/import        →   download PDFs
                                      ↓
                               1. Save PDF → /data/pdf_input/{dir}_zt/{file}.pdf
                               2. Write Zotero metadata →
                                  /data/preprocessed/{dir}_zt/{file}_metadata.json
                                      ↓
                         User converts in PDF tab (normal flow)
                         Convert step: if _metadata.json exists → skip enrichment,
                                       only run PDF→markdown conversion
                                      ↓
                         Normal ingest flow (unchanged)
```

Only one existing behavior is modified: the convert step gains a one-line guard to skip metadata enrichment when a `_metadata.json` already exists for the file.

---

## Directory Naming

All Zotero-imported directories are suffixed with `_zt` **server-side**. The frontend sends a plain name (e.g. `my_collection`); the backend sanitizes with `Path(dir_name).name` (prevents path traversal) then appends `_zt`, producing e.g. `my_collection_zt`.

The suffix is directory-scoped only. `paper_id` and `unique_id` are derived from the PDF filename stem and are unaffected.

Re-importing a `_zt` directory is safe and idempotent — PDFs already present are skipped.

---

## Backend

### New file: `backend/app/services/zotero_service.py`

**`list_collections(user_id, api_key) -> list[dict]`**
Fetches `GET api.zotero.org/users/{user_id}/collections`, returns `[{ key, name }]`.

**`list_items(user_id, api_key, collection_key) -> list[dict]`**
Fetches items in a collection with their PDF attachments. Returns:
```json
{
  "item_key": "ABC123",
  "title": "...",
  "authors": ["..."],
  "year": 2023,
  "doi": "...",
  "journal": "...",
  "abstract": "...",
  "attachment": {
    "type": "cloud" | "linked",
    "filename": "paper.pdf",
    "attachment_key": "DEF456",
    "path": "/local/path.pdf"
  }
}
```
**Multiple attachments:** first cloud attachment wins. If no cloud attachment, first linked attachment. Additional attachments are ignored.

**`download_pdf(user_id, api_key, attachment_key) -> bytes`**
Downloads `GET api.zotero.org/users/{user_id}/items/{attachment_key}/file`.
Uses synchronous `httpx.Client` (matches existing SSE generator pattern in `settings.py`).
Handles HTTP 429 with a single exponential-backoff retry before surfacing an error.

**`normalize_metadata(zotero_item) -> dict`**
Converts a Zotero item to the standard `_metadata.json` format (same fields and structure as OpenAlex/CrossRef/Semantic Scholar). Sets `metadata_source = "zotero"`.

```json
{
  "title": "...",
  "authors": ["..."],
  "publication_date": "2023",
  "abstract": "...",
  "doi": "...",
  "journal": "...",
  "metadata_source": "zotero",
  "source_pdf": "paper.pdf"
}
```
`backend` and `preprocessed_at` are omitted at import time (PDF conversion has not run yet); the convert step merges them in when it processes the file.

---

### New file: `backend/app/api/zotero.py`

**`GET /zotero/collections`**
Returns `[{ key, name }]`.
Returns HTTP 400 `"Zotero user ID or API key not configured. Go to Settings."` if not set.

**`GET /zotero/collections/{key}/items`**
Returns list of items as described above.

**`POST /zotero/import`**
```json
{
  "collection_key": "ABCD1234",
  "dir_name": "my_collection",
  "item_keys": ["ABC123", "DEF456"]
}
```
- `item_keys`: only the user-selected items are imported
- Backend sanitizes `dir_name` with `Path(dir_name).name` then appends `_zt`
- For each selected cloud item:
  - If `/data/pdf_input/{dir}_zt/{filename}` already exists → stream `skipped` (skip both PDF download and metadata write)
  - Otherwise → download PDF, save to `/data/pdf_input/{dir}_zt/`
  - Write normalized Zotero metadata to `/data/preprocessed/{dir}_zt/{stem}_metadata.json`
- Streams SSE per-file progress (synchronous generator, same pattern as `pull_ollama_model`)

Per-file SSE events:
```json
{ "filename": "paper.pdf", "status": "downloading" }
{ "filename": "paper.pdf", "status": "done" }
{ "filename": "paper.pdf", "status": "skipped" }
{ "filename": "paper.pdf", "status": "error", "message": "..." }
{ "done": true }
```

Failures on individual files do not stop the import. `{ "done": true }` is always sent last.

---

### Modification to existing convert step

**`backend/app/services/preprocessing_service.py`** — one guard added to `convert_single_pdf`:

Before calling the metadata enrichment API, check if `{stem}_metadata.json` already exists in the preprocessed directory. If it does:
- Skip the enrichment API call
- Skip the metadata write (do not overwrite the existing file)
- Merge `backend` and `preprocessed_at` into the existing file and write it back (so these fields are always present after conversion)
- Continue with the PDF→markdown conversion normally

This is the only change to existing code.

---

### Settings changes

**`config.yaml`** — new top-level section:
```yaml
zotero:
  user_id: ""
```

**`GET /settings`** — two new fields in response:
```json
{
  "zotero_user_id": "",
  "has_zotero_key": false
}
```

**`UpdateSettingsRequest`** — three new fields:
```python
zotero_user_id: Optional[str] = None
zotero_key: Optional[str] = None       # write-only, never returned
clear_zotero_key: bool = False
```

`zotero_user_id` written to `config.yaml` under `zotero.user_id`. The `update_settings` handler must initialize `config["zotero"] = {}` if the key is absent before writing (guards against `KeyError` on fresh installs). `GET /settings` must read it as `config.get("zotero", {}).get("user_id", "")` since the key may not exist in older `config.yaml` files.

`zotero_key` stored via `ApiKeysService` (key `"zotero"`), never returned to frontend.

---

## Frontend

### Settings tab (`app.js`)

Two new fields grouped together in the settings form:
- **Zotero User ID** — plain text input, saved to config
- **Zotero API Key** — password input, write-only; shows `✓ Key saved` / `No key` and a clear button (same pattern as Anthropic/Google keys)

### PDF tab (`pdf-tab.js`)

An **"Import from Zotero"** button alongside "Upload from PC" toggles an inline collapsible panel.

**Panel flow:**
1. On open: `GET /zotero/collections` — collection dropdown (or inline error if key not configured)
2. On collection select: `GET /zotero/collections/{key}/items` — item list:
   - **Cloud PDFs:** checkbox (checked by default) + title + authors
   - **Linked PDFs:** greyed out, ⚠ icon, path shown, note: *"Upload manually from `{path}`"*, checkbox disabled
3. **Directory name** input — pre-filled with Zotero collection name (editable); note: *"`_zt` will be appended automatically"*
4. **Import** button — calls `POST /zotero/import` with `{ collection_key, dir_name, item_keys: [selected] }`

**Streaming progress** — per-file status:

| Status | Display |
|--------|---------|
| `downloading` | spinner |
| `done` | ✓ |
| `skipped` | ✓ Skipped (already imported) |
| `error` | ✗ + reason |

Linked-file items remain greyed out in place — they are not sent to the import endpoint.

On `{ "done": true }` → directory list refreshes; imported PDFs appear immediately in the PDF tab ready for the normal convert → ingest flow.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Zotero key/user_id not configured | 400 returned; frontend shows inline alert pointing to Settings |
| Invalid API key | Zotero returns 403; shown inline in panel |
| Network / 5xx error | Shown inline in panel |
| 429 rate limit | Single exponential-backoff retry; if still 429, streamed as `error` for that file |
| Individual PDF download failure | Streamed as `error` with reason; rest of import continues |
| Linked file | Shown disabled in item list; not sent to import endpoint |
| Duplicate directory | Files added to existing dir; already-present PDFs streamed as `skipped` |
| `dir_name` path traversal | `Path(dir_name).name` strips path components before `_zt` is appended |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/zotero_service.py` | New |
| `backend/app/api/zotero.py` | New |
| `backend/app/main.py` | Register zotero router |
| `backend/app/services/preprocessing_service.py` | Add skip-enrichment guard when `_metadata.json` already exists |
| `backend/app/api/settings.py` | Add `zotero_user_id`, `zotero_key`, `clear_zotero_key` to request/response |
| `config.yaml` | Add `zotero.user_id: ""` section |
| `frontend-web/js/app.js` | Add Zotero User ID + API Key fields to settings form |
| `frontend-web/js/pdf-tab.js` | Add Zotero import panel |
