# Semantic Chunk Classification Plan

## Goal

Use the `section_heading` metadata already extracted during markdown chunking to assign
meaningful `ChunkType` values to each chunk, replacing the current hardcoded `BODY`.
This enables future filtering (e.g. exclude references from RAG), better retrieval
context, and richer Qdrant payload metadata.

## Step 1 — Expand `ChunkType` enum (`models/paper.py`)

Add:
- `INTRODUCTION`
- `RELATED_WORK`
- `METHODS`
- `DATA`
- `RESULTS`
- `DISCUSSION`
- `CONCLUSION`
- `REFERENCES`
- `ACKNOWLEDGEMENTS`
- `APPENDIX`

Keep existing `TABLE` and `FIGURE_CAPTION` for future use. `BODY` remains the default fallback.

## Step 2 — Heading classifier (`chunking_service.py`)

Add a module-level `classify_heading(heading: str) -> ChunkType` function.

Pre-processing before matching: strip markdown bold (`**`), leading section numbers
(`3.1`, `7`), and lowercase.

Pattern table (checked against real paper headings in `data/preprocessed/`):

| Regex pattern | ChunkType |
|---|---|
| `abstract`, `аннотация` | ABSTRACT |
| `intro`, `overview`, `background`, `motivation` | INTRODUCTION |
| `related work`, `prior work`, `previous work`, `literature` | RELATED_WORK |
| `method`, `approach`, `procedure`, `methodology`, `materials and methods`, `experimental setup`, `implementation` | METHODS |
| `\bdata\b`, `dataset`, `corpus`, `corpora`, `preprocessing`, `time-varying`, `data availability` | DATA |
| `result`, `finding`, `experiment`, `evaluat`, `analysis`, `scoring` | RESULTS |
| `discussion` | DISCUSSION |
| `conclusion`, `summary`, `future work`, `limitation` | CONCLUSION |
| `reference`, `bibliography`, `works cited` | REFERENCES |
| `acknowledg`, `funding`, `author contrib`, `conflict of interest`, `ethic` | ACKNOWLEDGEMENTS |
| `appendix`, `supplementary` | APPENDIX |

Precedence: patterns are checked in the order listed above; first match wins.
Empty heading → `BODY`.

## Step 3 — References: one entry per chunk

For sections classified as `REFERENCES`, skip `_merge_short` and emit each
blank-line-separated paragraph as its own chunk. Docling formats reference lists
as one entry per paragraph, so this keeps entries atomic.

This is handled inside `chunk_markdown` by checking the section heading before
deciding the merge strategy.

### Future: filter references from RAG

- Add optional `exclude_chunk_types: list[str]` to the RAG request body.
- Default: `["references", "acknowledgements", "appendix"]`.
- Translated to a Qdrant `must_not` filter on the `chunk_type` payload field.
- Expose a UI toggle in Advanced Options: "Include references / appendices" (off by default).

## Step 4 — Wire into `ingestion_service.py`

- `chunk_markdown` continues to return `(text, heading)` 2-tuples (no signature change).
- In the ingestion loop, call `classify_heading(heading)` to get `ChunkType` instead
  of hardcoding `ChunkType.BODY`.
- The references special-casing lives inside `chunk_markdown` (step 3), invisible to callers.

## Files to change

| File | Change |
|---|---|
| `backend/app/models/paper.py` | Add new `ChunkType` values |
| `backend/app/services/chunking_service.py` | Add `classify_heading()`, special-case references in `chunk_markdown` |
| `backend/app/services/ingestion_service.py` | Call `classify_heading` instead of hardcoding `BODY` |
| `tests/unit/test_chunking_service.py` | Tests for `classify_heading` and references chunking |

## Out of scope (future)

- RAG `exclude_chunk_types` filter + UI toggle
- `TABLE` and `FIGURE_CAPTION` assignment (requires Docling table/figure detection)
