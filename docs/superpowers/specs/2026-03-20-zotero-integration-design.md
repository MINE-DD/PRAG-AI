# Zotero Integration Design

**Date:** 2026-03-20
**Status:** Approved

## Overview

Allow users to import PDFs from their Zotero library directly into PRAG as an alternative to manual upload. Zotero is used as a PDF source only — once files are imported the standard preprocess → ingest pipeline is unchanged. Metadata from Zotero pre-fills the `_metadata.json` file, skipping the external enrichment step entirely.

---

## Architecture

```
Frontend (pdf-tab.js)          Backend                      Zotero API
  "Import from Zotero"   →   GET /zotero/collections   →   api.zotero.org
  Pick folder            →   GET /zotero/collections/{key}/items
  Click Import           →   POST /zotero/import       →   download PDFs
                                    ↓
                             /data/pdf_input/{dir}_zt/     (same as manual upload)
                             /data/preprocessed/{dir}_zt/  (metadata pre-written)
                                    ↓
                         Normal convert → ingest flow (unchanged)
```

No existing endpoints are modified. Zotero import is an additive feature.

---

## Directory Naming

All Zotero-imported directories are suffixed with `_zt` server-side. The frontend sends a plain name (e.g. `my_collection`); the backend always saves to `my_collection_zt`. This prevents clashes with manually uploaded directories and makes Zotero-sourced directories visually identifiable in the PDF tab.

The suffix propagates naturally — all downstream logic uses the `dir_name` string as-is, no special handling needed.

---

## Backend

### New file: `backend/app/services/zotero_service.py`

Three responsibilities:

- `list_collections(user_id, api_key)` — fetches all Zotero collections from `api.zotero.org/users/{user_id}/collections`
- `list_items(user_id, api_key, collection_key)` — fetches all items with PDF attachments; returns normalized list including `linkMode` per attachment (`cloud` or `linked`)
- `download_pdf(user_id, api_key, item_key)` — downloads a single cloud PDF via `api.zotero.org/users/{user_id}/items/{key}/file`

Metadata returned by `list_items` is normalized to the same format as `_metadata.json` produced by OpenAlex/CrossRef/Semantic Scholar (same fields, same structure).

### New file: `backend/app/api/zotero.py`

Three endpoints:

**`GET /zotero/collections`**
- Returns list of `{ name, key }` for all Zotero collections
- Returns 400 if Zotero key/user_id not configured, with message pointing to Settings

**`GET /zotero/collections/{key}/items`**
- Returns list of items in the collection
- Each item: `{ title, authors, year, doi, journal, abstract, attachment: { type: "cloud"|"linked", filename, path? } }`

**`POST /zotero/import`**
- Body: `{ collection_key: str, dir_name: str }`
- Backend appends `_zt` to `dir_name`
- For each cloud PDF:
  - If `/data/pdf_input/{dir_name}_zt/{filename}` already exists → stream `skipped`
  - Otherwise → download PDF, write to `/data/pdf_input/{dir_name}_zt/`
  - Write pre-filled `_metadata.json` to `/data/preprocessed/{dir_name}_zt/`
- Streams SSE progress per file (same pattern as Ollama model pull)
- Never all-or-nothing: failures on individual files do not stop the import

### Settings

- `zotero_user_id` stored in config (not a secret, treated like other settings)
- `zotero_key` stored via `ApiKeysService` (`/data/api_keys.json`), never returned to frontend (only `has_zotero_key` boolean)

---

## Frontend

### Settings tab (`app.js`)

Two new fields in the settings form:
- **Zotero User ID** — plain text input, saved to config
- **Zotero API Key** — password input, write-only, shows `has_key` boolean (same pattern as Anthropic/Google keys)

### PDF tab (`pdf-tab.js`)

A second option alongside "Upload from PC": **"Import from Zotero"** button that toggles an inline collapsible panel.

Panel contents:
1. Dropdown: list of Zotero collections (fetched on panel open)
2. On collection select: item list renders below
   - Cloud PDFs: checkbox + title + authors (importable)
   - Linked PDFs: greyed out, warning icon, local path, note: *"To import, upload manually from `{path}`"*
3. "Directory name" text input — pre-filled with Zotero collection name (editable); note shown that `_zt` will be appended
4. "Import" button → calls `POST /zotero/import`, shows streaming progress per file

Per-file streaming status states:
| State | Display |
|-------|---------|
| Downloading | spinner |
| Downloaded | ✓ |
| Already exists | ✓ Skipped |
| Linked file | ⚠ Linked — upload manually from `{path}` |
| Failed | ✗ + error reason |

On import completion → directory list refreshes so imported PDFs appear immediately in the normal flow.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Zotero key/user_id not configured | `GET /zotero/collections` returns 400; frontend shows inline alert pointing to Settings |
| Invalid API key / network error | 401/502 returned; shown inline in Zotero panel |
| Individual PDF download failure | Streamed as ✗ with reason; rest of import continues |
| Linked file attachment | Shown as skipped before import starts; not treated as an error |
| Duplicate directory (`_zt` already exists) | Files added to existing directory; already-present PDFs skipped (idempotent) |

---

## Attachment Type Support

Zotero supports two attachment storage modes per item (can be mixed within a library):

- **Cloud (`imported_file` / `imported_url`)** — file synced to zotero.org; downloaded automatically via API
- **Linked (`linked_file`)** — file at a local path; shown with path and "upload manually" note; not downloaded

The import flow handles both in the same pass. Mixed collections (some cloud, some linked) work correctly.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/zotero_service.py` | New |
| `backend/app/api/zotero.py` | New |
| `backend/app/main.py` | Register zotero router |
| `backend/app/core/config.py` | Add `zotero_user_id` field |
| `backend/app/api/settings.py` | Add Zotero key management |
| `frontend-web/js/app.js` | Add Zotero settings fields |
| `frontend-web/js/pdf-tab.js` | Add Zotero import panel |
