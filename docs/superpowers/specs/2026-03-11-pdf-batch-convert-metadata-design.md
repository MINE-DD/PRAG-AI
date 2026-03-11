# PDF Batch Convert & Metadata Display — Design Spec

**Date:** 2026-03-11
**Status:** Approved

---

## Overview

Three related features to improve the PDF management tab:

1. **Convert All** — batch-convert all unconverted PDFs in a folder
2. **Metadata detail panel** — show title, authors, year etc. for converted PDFs
3. **Metadata provider in Settings** — global default for which academic API to use

---

## Feature 1: Convert All Button

### Behaviour

- A green "Convert All" button appears in the **folder header row** when the folder is expanded
- Only visible when at least one PDF in the folder is unconverted
- Hidden/disabled when all files are already converted

### Processing

- On click: filter file list to unconverted PDFs only (skip already-converted)
- Convert sequentially via the existing `POST /preprocess/convert` endpoint
- Uses the global `metadata_backend` setting from `localStorage` (default: `openalex`)
- Uses the global `backend` setting from `localStorage` (default: `pymupdf`)

### Progress feedback

- Folder header shows inline progress: "Converting 2/5..." during the run
- A spinner appears on the currently-converting file row
- On completion: brief success state, then button hides (all converted)

### Future work

- A `/preprocess/convert-all` bulk backend endpoint for more robust large-folder processing

---

## Feature 2: Metadata Detail Panel

### Behaviour

- Each file row has a chevron toggle to expand/collapse a detail panel below it
- Panels are **collapsed by default**
- Panel is only meaningful for converted PDFs; unconverted files show "Not converted yet"

### Panel content (for converted PDFs)

| Field | Notes |
|-------|-------|
| Title | Prominent, large text |
| Authors | Comma-separated list |
| Year | Extracted from `publication_date` |
| Journal | If available |
| DOI | Clickable link if present |
| Metadata source | Badge: "OpenAlex", "CrossRef", "Semantic Scholar", or "None" |
| Re-enrich button | Dropdown to pick a provider and re-fetch metadata |

### Data fetching

- Metadata loaded **on demand** when the user expands a file row
- New backend endpoint: `GET /preprocess/metadata?dir_name=X&filename=Y`
- Reads the existing `{stem}_metadata.json` file and returns its contents
- If file not found: return 404; frontend shows "Not converted yet"

### Re-enrich

- Dropdown with options: OpenAlex, CrossRef, Semantic Scholar
- On select: calls existing `POST /preprocess/enrich-metadata` with chosen provider
- Panel reloads after enrichment completes

---

## Feature 3: Metadata Provider in Settings

### New "PDF Processing" section in Settings modal

Two settings surfaced here (both already exist in `localStorage` but were not in Settings UI):

| Setting | Key | Default | Options |
|---------|-----|---------|---------|
| Metadata provider | `metadata_backend` | `openalex` | OpenAlex, CrossRef, Semantic Scholar, None |
| PDF backend | `backend` | `pymupdf` | PyMuPDF (fast), Docling (thorough/slow) |

### Behaviour

- Values stored in `localStorage`
- Used as defaults for both single-file Convert and Convert All
- Per-file re-enrich in the detail panel overrides for that one operation only
- No backend persistence needed (frontend-only setting)

---

## Backend Changes

### New endpoint: `GET /preprocess/metadata`

**Request params:** `dir_name: str`, `filename: str`
**Response:** Contents of `{preprocessed_dir}/{dir_name}/{stem}_metadata.json`
**Errors:** 404 if not found

No other backend changes required. All other operations reuse existing endpoints.

---

## Frontend Changes (index.html)

1. **Folder header row**: Add green "Convert All" button with progress state
2. **File row**: Add chevron toggle + collapsible detail panel
3. **Settings modal**: Add "PDF Processing" section with two dropdowns
4. **Alpine.js state**: Add `convertingAll`, `convertAllProgress`, `expandedFiles` (Set), `fileMetadata` (Map)

---

## Out of Scope

- Bulk backend endpoint (`/preprocess/convert-all`) — future work
- Displaying abstract in detail panel — not requested
- Editing metadata manually in the UI — not requested
