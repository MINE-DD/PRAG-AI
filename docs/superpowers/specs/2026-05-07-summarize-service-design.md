# Summarize Service Design
**Date:** 2026-05-07
**Branch:** 8-improve-summarize-service

## Problem

The Explore Document tab needs to help the user understand why a paper matters, what it proposes, and what conclusions it reaches. The current summarize endpoint is a naive synchronous call that grabs up to 20 chunks and calls the LLM once — no section awareness, no context-window management, no streaming.

There is also a foundational bug: `paper_id` is derived from the markdown filename stem, making it fragile with Zotero-style filenames (accented characters, en-dashes, spaces), which break URL routing.

---

## Step 1: Fix `paper_id`

### Problem
`paper_id = md_file.stem` in `ingestion_service.ingest_file()`. For Zotero imports this produces strings like `"Beck and Köllner - 2023 - GHisBERT – Training BERT from scratch for lexical "` — URL-unsafe, filesystem-dependent, fragile.

### Fix
Use the already-computed `unique_id` (author + title-words + year slug, e.g. `BeckGHisBERT2023`) as the `paper_id` everywhere.

**Collision handling:** Before writing `metadata/{unique_id}.json`, check if it already exists. If so, append `_2`, `_3`, etc. until the name is free. The same suffix is used as the `paper_id` in the Qdrant payload and the JSON content.

**Files changed:**
- `backend/app/services/ingestion_service.py` — set `paper_id = unique_id` (with collision check) instead of `md_file.stem`
- No changes needed to `papers.py`, `qdrant_service.py`, or the frontend — they already read `paper_id` from the JSON content

**Migration:** Existing collections must be deleted and re-ingested. User confirmed this is acceptable.

**Testable outcome:** After re-ingesting a Zotero collection, clicking any paper in the Explore tab succeeds. Paper IDs in Qdrant and metadata files are clean slugs like `BeckGHisBERT2023`.

---

## Step 2: Minimal Summarize Card (synchronous)

### UI
A **Summarize card** appears below the existing metadata card in the Explore tab when a paper is selected. Collapsed by default with a single "Generate summary" button.

- Button click → spinner → displays plain text result
- No streaming, no path detection, no accordion
- "Regenerate" button appears after first result

### Backend
New endpoint: `GET /collections/{collection_id}/papers/{paper_id}/summarize`

For Step 2 this is synchronous (not SSE). It:
1. Loads the paper metadata to find `preprocessed_dir` and `source_pdf`
2. Reads the markdown file from `preprocessed/{preprocessed_dir}/{stem}.md`
3. Truncates the markdown to fit in `max_allowed_tokens * 0.8` characters (rough estimate)
4. Calls the LLM with the academic paper prompt
5. Returns `{"summary": "...", "method": "markdown"|"rag"}`

If markdown is not found, falls back to fetching the top 10 Qdrant chunks sorted by `chunk_index`.

### Prompt
New file: `backend/prompts/summarize/academic_paper.yaml`

Focus: why is this paper important, what does it propose, what conclusions does it reach. Concise, 3–4 paragraphs.

**Testable outcome:** Clicking "Generate summary" in the Explore tab produces a readable academic summary. Works for both markdown-backed and chunk-only papers.

---

## Step 3: SSE Streaming + Section Accordion

### Core algorithm: `MarkdownSectionParser`
New utility (pure, no external dependencies):

1. Parse markdown into `[(heading, body)]` pairs by heading level 1–2
2. Greedily pack adjacent sections into chunks, each ≤ `max_tokens * 0.8` tokens
3. If a single section exceeds the limit, split it by paragraph (never mid-paragraph)
4. Token counting via the existing `ChunkingService` tokenizer (BERT multilingual)

### SSE events
```
{"type": "method",  "method": "markdown"|"rag", "chunk_count": N}
{"type": "section", "heading": "Introduction",  "text": "..."}
{"type": "global",  "text": "..."}
{"type": "done"}
{"type": "error",   "message": "..."}
```

### UI updates
- Progress bar: `N / M sections processed`
- Section summaries appear as collapsible accordion items as each one arrives
- Global summary appears at the top of the card in a highlighted box when complete
- Method badge: `Markdown` or `RAG (fallback)`

### What falls out naturally
- Small doc (fits in one chunk) → 1 LLM call, 1 global summary, no accordion needed
- Medium doc → a few calls, section accordion
- Large doc → many calls, full accordion
- No explicit path detection needed — the chunking algorithm handles it

**Testable outcome:** Sections stream in one by one. Progress bar updates. Global summary appears at the end.

---

## Step 4: Prompt Quality Pass

Refine `academic_paper.yaml` and add `section.yaml` / `global_from_sections.yaml`:

- `section.yaml` — inputs: `{heading}`, `{context}`. What does this section contribute?
- `global_from_sections.yaml` — input: `{context}` (all section summaries joined). Why important, what proposed, what conclusions?

**Testable outcome:** Summary quality is clearly better — relevant, structured, covers contributions and conclusions.

---

## Step 5: Advanced Override + RAG Fallback

### Advanced panel (collapsed by default in UI)
- Method override: `Auto` / `Markdown` / `RAG`
- RAG chunk count: slider 1–20 (default 5, shown only when RAG selected)

### RAG fallback path (full implementation)
When method is `rag` (or no markdown found):
- Fetch top-N chunks from Qdrant sorted by `chunk_index`
- One LLM call per chunk if N > 1 (with `section.yaml` prompt)
- One final global summary call

**Testable outcome:** User can override to RAG, adjust chunk count, and get a result. Papers without markdown files get a RAG summary automatically.

---

## Architecture Summary

```
Explore Tab
  └── Paper detail card (existing)
  └── Summarize card (new)
        ├── "Generate summary" button
        ├── Progress bar (Step 3+)
        ├── Section accordion (Step 3+)
        ├── Global summary box
        └── Advanced panel (Step 5)

Backend
  GET /collections/{id}/papers/{paper_id}/summarize
    └── SummarizeService
          ├── MarkdownSectionParser   (Step 3)
          ├── LLM calls (section + global prompts)
          └── SSE event stream        (Step 3)

Prompts
  prompts/summarize/academic_paper.yaml   (Step 2)
  prompts/summarize/section.yaml          (Step 3)
  prompts/summarize/global_from_sections.yaml (Step 3)
```

---

## Out of Scope
- Multi-paper summarization (existing POST endpoint handles that)
- Token-by-token streaming (section-at-a-time is sufficient)
- Non-academic paper types (future work)
