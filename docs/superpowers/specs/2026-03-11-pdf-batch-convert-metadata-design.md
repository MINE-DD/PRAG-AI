# PDF Batch Convert & Metadata Display — Design Spec

**Date:** 2026-03-11
**Status:** Approved

---

## Overview

Three features to improve the PDF management tab:

1. **Convert All** — batch-convert all unconverted PDFs in a folder sequentially
2. **Metadata detail panel** — expandable per-file panel showing title, authors, year etc.
3. **Metadata provider in Settings** — global default for which academic API to use

---

## Feature 1: Convert All Button

### Behaviour

- A green "Convert All" button appears in the **folder header row** when the folder is expanded
- Only visible when at least one PDF in the folder is unconverted
- Hidden entirely when all files are already converted

### Processing

- On click: filter file list to unconverted PDFs only (skip already-converted)
- Convert sequentially via the existing `POST /preprocess/convert` endpoint
- Uses `prag_meta_backend` from `localStorage` (default: `openalex`)
- Uses `prag_pdf_backend` from `localStorage` (default: `pymupdf`)
- If `prag_meta_backend` is `none`, passes `metadata_backend: "none"` (no enrichment)

### Progress feedback

- Folder header shows inline progress: "Converting 2/5..." during the run
- A spinner appears on the currently-converting file row
- On completion: button hides (all converted)

### Error handling

- If a single file fails, log the error and continue to the next file
- After the batch completes, show a warning if any failed: "Converted X/Y — Z failed"
- Failed files remain "Not converted" so the user can retry individually

### Alpine.js state (per-folder)

Progress scoped per folder via a Map keyed by `dir_name`:
- `convertingAllMap`: `Map<dir_name, { active: bool, current: number, total: number, failed: number }>`

### Future work

- A `/preprocess/convert-all` bulk backend endpoint for large-folder processing

---

## Feature 2: Metadata Detail Panel

### Behaviour

- Each file row has a chevron toggle to expand/collapse a detail panel below it
- Panels are **collapsed by default**
- Unconverted files show "Not converted yet" when expanded

### Panel content (for converted PDFs)

| Field | Source key in `_metadata.json` | Notes |
|-------|-------------------------------|-------|
| Title | `title` | Prominent, large text |
| Authors | `authors` (array) | Comma-separated |
| Year | `publication_date` | Frontend extracts 4-digit year |
| Journal | `journal` | Hidden if absent |
| DOI | `doi` | Clickable link if present |
| Metadata source | `metadata_source` | Badge: "OpenAlex", "CrossRef", "Semantic Scholar", or "None" |

### Data fetching

- Metadata loaded **on demand** when the user expands a file row
- Reuses existing `GET /preprocess/download/{dir_name}/{filename}/metadata`
- Returns 404 if not found → frontend shows "Not converted yet"
- No new backend endpoint needed

### Re-enrich

- A "Re-enrich" button opens an inline dropdown: OpenAlex, CrossRef, Semantic Scholar
- Selecting an option shows a confirm step: "Re-enrich with [Provider]?" + Cancel / Confirm
- On confirm: calls existing `POST /preprocess/enrich-metadata` with body `{ "dir_name": ..., "filename": ..., "backend": "<chosen_provider>" }` — note the field is `backend`, not `provider`
- Panel reloads metadata after enrichment completes

### Implementation notes

- The download endpoint is a `FileResponse` serving `application/json` — the frontend must call `.json()` on the fetch response to parse it
- The backend `ConvertRequest.backend` defaults to `"docling"` — always pass the value explicitly from `localStorage` (never rely on the backend default)

### Alpine.js state

- `expandedFiles`: `Set<string>` of `"dir_name/filename"` keys
- `fileMetadata`: `Map<string, object|null>` — `null` while loading, object when loaded

---

## Feature 3: Metadata Provider in Settings

### New "PDF Processing" section in Settings modal

Two settings surfaced here (already exist in `localStorage` but not in the Settings UI):

| Setting | localStorage key | Default | Options |
|---------|-----------------|---------|---------|
| Metadata provider | `prag_meta_backend` | `openalex` | OpenAlex, CrossRef, Semantic Scholar, None |
| PDF backend | `prag_pdf_backend` | `pymupdf` | PyMuPDF (fast), Docling (thorough/slow) |

### Behaviour

- Values stored in `localStorage`; no backend persistence needed
- Used as defaults for both single-file Convert and Convert All
- Per-file re-enrich overrides for that one operation only

---

## Backend Changes

None. All operations reuse existing endpoints:
- `POST /preprocess/convert` — single file conversion (used sequentially for Convert All)
- `GET /preprocess/download/{dir_name}/{filename}/metadata` — fetch metadata JSON
- `POST /preprocess/enrich-metadata` — re-enrich metadata for a file

---

## Frontend Changes (index.html)

1. **Folder header row**: Add green "Convert All" button with per-folder progress state
2. **File row**: Add chevron toggle + collapsible detail panel with metadata + re-enrich control
3. **Settings modal**: Add "PDF Processing" section with two dropdowns
4. **Alpine.js state**: Add `convertingAllMap` (Map), `expandedFiles` (Set), `fileMetadata` (Map)

---

## Out of Scope

- Bulk backend endpoint (`/preprocess/convert-all`) — future work
- Displaying abstract in detail panel — not requested
- Editing metadata manually in the UI — not requested
