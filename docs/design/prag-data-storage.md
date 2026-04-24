# PRAG Data Storage and Data Flow Complete Design

> This document provides a unified design for 7 critical gaps in prag-architecture-v3.md: paper_id strategy, storage structure, PDF deduplication & Zotero references, vectordb collection organization, conversation history storage, paper group management, and deletion cascading.

**Core storage decision: pure filesystem (JSON + JSONL), no SQLite.** At the MVP scale of papers (tens to hundreds) and conversations (tens to hundreds), the filesystem fully meets performance requirements, with zero additional dependencies, transparent debugging, and backup as simple as copying the directory.

**Note: There is a causal chain between gaps** — paper_id (Gap 1) determines directory naming (Gap 2), affects deduplication implementation (Gap 3), constrains vectordb filter fields (Gap 4), propagates to conversation reference structure (Gap 5), group management (Gap 6) defines dynamic resolution of conversation scopes, and deletion paths (Gap 7) need to handle group associations.

---

## Gap 1: paper_id Generation Strategy

**Decision: First 32 hex characters (16 bytes / 128 bits) of SHA-256 content hash**

```python
import hashlib

def generate_paper_id(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:32]
# Output example: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"
```

**Rationale:**
- Idempotent: same PDF → same ID, naturally supports deduplication (Gap 3)
- Filesystem-safe: pure lowercase letters + digits, 32 characters
- Collision probability: approximately 10^-29 for 100,000 papers, far beyond individual researcher scale
- Zotero compatible: does not use Zotero key as ID; instead stores `zotero_key` mapping in metadata.json

**Edge cases:**
- Same paper downloaded from different sources (embedded PDF metadata differs) → binary differs → different IDs → acceptable for MVP, no semantic deduplication
- PDF re-imported after annotation → new ID → correct behavior (annotated version is indeed a different document)

---

## Gap 2: Storage Structure (Pure Filesystem, No SQLite)

### Directory Structure

```
~/.prag/
├── config.yaml                            # User configuration
├── papers/{paper_id}.pdf                  # Original PDF (PRAG-managed copy)
├── parsed/{paper_id}/                     # Parse artifacts + metadata (source of truth)
│   ├── metadata.json                      # Paper metadata (extended version, see below)
│   ├── content.md                         # MinerU structured full text
│   ├── chunks.json                        # Chunking results + metadata
│   ├── tables/                            # Extracted tables
│   └── references.json                    # GROBID structured references
├── groups/{group_id}.json                 # Local paper groups
├── conversations/{conversation_id}.jsonl  # Conversation history (append-only)
├── vectordb/                              # Qdrant persistence (embedded mode)
└── logs/
```

**Source of truth responsibilities:**
- `parsed/{paper_id}/metadata.json` → source of truth for paper metadata
- `conversations/{id}.jsonl` → source of truth for conversation history
- `vectordb/` → retrieval acceleration layer, can be fully rebuilt from parsed/

### metadata.json Extended Fields

The v3 architecture originally only had parse outputs (title/authors/abstract). The following fields are added to cover the responsibilities of the original SQLite papers table:

```json
{
  "paper_id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
  "title": "Attention Is All You Need",
  "authors": ["Vaswani, A.", "Shazeer, N."],
  "abstract": "The dominant sequence transduction models...",
  "year": 2017,
  "doi": "10.48550/arXiv.1706.03762",

  "import_source": "zotero",
  "zotero_key": "N7SMB24A",
  "original_path": "/Users/neo/Zotero/storage/N7SMB24A/vaswani2017.pdf",

  "status": "ready",
  "status_message": null,
  "page_count": 15,
  "chunk_count": 47,

  "created_at": "2026-03-09T10:00:00Z",
  "updated_at": "2026-03-09T10:02:30Z",
  "deleted_at": null
}
```

**State machine:** `pending → parsing → chunking → indexing → ready`, each stage may enter its corresponding `*_error` state.

**Deduplication check method:** During import, compute paper_id and check whether the `parsed/{paper_id}/` directory exists. If it exists, it is a duplicate.

### Conversation List Query

No additional index file is maintained. When listing all conversations, iterate over `conversations/*.jsonl` and read the first line (meta line) of each file to get title/paper_ids/timestamps. A few hundred conversations is still a millisecond-level operation.

---

## Gap 3: PDF Deduplication and Zotero Reference Strategy

### Deduplication: Binary Deduplication Based on paper_id

```
Import PDF → Compute SHA-256 → Check parsed/{paper_id}/ directory
├─ Does not exist → Normal import
├─ Exists and deleted_at is null → Reject (PaperAlreadyExistsError)
│   └─ Special case: During Zotero import, can supplement zotero_key to metadata.json
└─ Exists and deleted_at is not null → Restore paper, re-trigger indexing
```

### Zotero PDF Strategy: Always Copy to `~/.prag/papers/`

**Decision: Do not use symbolic links or direct references to Zotero storage paths.**

Rationale:
- Zotero paths are unstable (users may move the data directory, reinstall Zotero, or delete entries)
- Symbolic links are unreliable across filesystems; Windows requires administrator privileges
- Disk overhead is acceptable (1,000 papers ≈ 1-10 GB)
- The `original_path` field is preserved to record the source, used for UI display

### Zotero Import Flow

```
User selects "Import from Zotero" → Detect Zotero running status (/connector/ping)
├─ Running → Local API lists papers → User selects
│   → GET /items/{attachment_key}/file/view/url → Get PDF physical path
│   → Read PDF → Compute paper_id → Deduplication check
│   → Copy PDF → Write metadata.json (including zotero_key) → Async parsing
└─ Not running → Prompt "Please start Zotero"
    (SQLite direct read retained as Phase 2 enhancement option)
```

---

## Gap 4: vectordb Collection Organization

**Decision: Single global collection `prag_chunks` + paper_id metadata filter**

Rationale:
- Cross-paper search is a core scenario; a single collection handles it with one `query()` call
- Qdrant's payload pre-filter is millisecond-level at the scale of thousands of papers
- Delete operation: implemented via `QdrantStore.remove_chunks(paper_id)`
- `QdrantStore` interface is concise (concrete class, no Port abstraction)

**chunk_id format:**
```python
def generate_chunk_id(paper_id: str, ordinal: int) -> str:
    return f"{paper_id[:8]}_chunk_{ordinal:04d}"
# Example: "a1b2c3d4_chunk_0001"
```

**chunk metadata fields:**
```python
{
    "paper_id": str,          # Full 32 characters
    "section_title": str,
    "page_number": int,
    "chunk_type": str,        # "text" | "table" | "equation" | "figure"
    "ordinal": int,           # Reading order within the paper
}
```

**QdrantStore interface (aligned with v3 architecture, Qdrant already selected, no Port abstraction needed):**
```python
class QdrantStore:
    def __init__(self, path: str, ollama_url: str, embedding_model: str):
        self.client = QdrantClient(path=path)  # Embedded mode, no standalone server needed

    async def add_chunks(self, chunks: list[Chunk]) -> None: ...
    async def remove_chunks(self, paper_id: str) -> None: ...
    async def hybrid_search(self, query: str, top_k: int = 20,
                            paper_ids: list[str] | None = None) -> list[SearchResult]:
        # Qdrant native hybrid search (dense + sparse vectors + payload pre-filter)
        ...
```

**Embedding strategy: QdrantStore handles vectorization internally.** `hybrid_search()` accepts query text — internally calls the Ollama embedding API to convert the query into dense + sparse vectors, then executes Qdrant native hybrid search. Similarly, `add_chunks()` internally vectorizes each chunk before writing. Embedding and vector retrieval are naturally coupled (must use the same model), so encapsulating them inside QdrantStore is the most sensible approach. SearchService is completely unaware of embedding.

The `paper_ids` parameter is `list[str] | None` (None = entire library). QdrantStore internally implements paper scope filtering through Qdrant payload pre-filter.

---

## Gap 5: Conversation History Storage (JSONL)

### Format Selection

| Data | Format | Rationale |
|------|--------|-----------|
| Paper metadata | JSON | Write once, read many times, single object |
| Conversation messages | **JSONL** | Append-only, O(1) append for new messages, crash only corrupts the last line |
| Chunking results | JSON | Written once during parsing |
| Group definitions | JSON | Single object, low-frequency updates |

### JSONL Conversation File Structure

One file per conversation: `conversations/{conversation_id}.jsonl`

```jsonl
{"type":"meta","conversation_id":"550e8400-...","title":"Core Contributions of the Attention Mechanism","scope":{"type":"group","group_id":"grp_transformer"},"created_at":"2026-03-09T10:00:00Z","updated_at":"2026-03-09T10:05:00Z"}
{"type":"message","message_id":"msg_001","role":"user","content":"What are the core contributions of this paper?","created_at":"2026-03-09T10:00:00Z"}
{"type":"message","message_id":"msg_002","role":"assistant","content":"According to the paper [1], the core contributions are...","citations":[{"paper_id":"a1b2c3d4...","chunk_id":"a1b2c3d4_chunk_0012","section_title":"3. Methods","page_number":5,"snippet":"We propose a novel...","marker":"[1]"}],"retrieval":{"query":"core contributions","method":"hybrid","top_k":5,"resolved_paper_ids":["a1b2c3d4...","f5e6d7c8..."],"chunks":[{"chunk_id":"a1b2c3d4_chunk_0012","paper_id":"a1b2c3d4...","score":0.92,"text":"We propose...","section_title":"3. Methods","page_number":5}]},"created_at":"2026-03-09T10:00:05Z"}
```

**Key design points:**
- First line `type: "meta"` stores conversation meta-information (only the first line is read when listing conversations)
- **`scope` field replaces the original `paper_ids`** — supports dynamic resolution (see Gap 6)
- Assistant messages embed `citations` and `retrieval` — redundant storage, not dependent on vectordb reverse lookup
- `retrieval.resolved_paper_ids` records which papers were actually searched for this question (a snapshot of the scope)
- `retrieval` is an immutable retrieval snapshot — even if the group changes later, the historical record remains complete
- New messages are directly appended as a line, no need to read/write the entire file
- Updating conversation title/updated_at: rewrite the first line (infrequent, acceptable)

**Conversation creation timing:** The file is created when the user asks their first question + meta line is written + first user message.

**Conversation title:** For MVP, truncate the first message to the first 50 characters.

**Conversation history loading:** Read the entire JSONL file, filter `type: "message"` lines, take the most recent 20 turns. Context window management is handled inside the Orchestrator.

---

## Gap 6: Paper Group Management (Groups + Zotero Collections)

### Group Types

PRAG supports four conversation scope types, uniformly expressed through the `scope` object:

| Scope Type | Meaning | Dynamism |
|-----------|---------|----------|
| `all` | Search entire library | **Dynamic** (enumerates all non-deleted papers at each question) |
| `papers` | Manually selected paper list | Static (determined at creation) |
| `group` | Local named group | **Dynamic** (resolves latest members at each question) |
| `zotero_collection` | Zotero folder | **Dynamic** (reads from Zotero at each question) |

### Scope Object Format

```python
# Search entire library (dynamic)
{"type": "all"}

# Manually selected papers (static)
{"type": "papers", "paper_ids": ["a1b2c3d4...", "f5e6d7c8..."]}

# Local group (dynamic)
{"type": "group", "group_id": "grp_transformer"}

# Zotero Collection (dynamic)
{"type": "zotero_collection", "collection_key": "ABC123", "collection_name": "Transformer Papers"}
```

### Dynamic Resolution Flow

Each time the user asks a question, the Orchestrator first resolves the scope → current paper_ids:

```python
async def resolve_scope(scope: dict) -> list[str]:
    match scope["type"]:
        case "all":
            return get_all_active_paper_ids()  # Enumerate parsed/*/metadata.json, filter out deleted_at != null
        case "papers":
            return scope["paper_ids"]
        case "group":
            group = load_group(scope["group_id"])
            return group["paper_ids"]
        case "zotero_collection":
            items = await zotero_client.get_collection_items(scope["collection_key"])
            return [find_paper_id_by_zotero_key(item["key"]) for item in items
                    if find_paper_id_by_zotero_key(item["key"]) is not None]
```

**Important:** `retrieval.resolved_paper_ids` records the actual list of papers resolved from the scope at each question. This is an immutable snapshot — even if the group changes later, you can trace back "which papers this answer was generated from."

### Local Group Storage

```
~/.prag/groups/{group_id}.json
```

```json
{
  "group_id": "grp_transformer",
  "name": "Transformer Series Papers",
  "description": "Collection of papers related to attention mechanisms",
  "paper_ids": ["a1b2c3d4...", "f5e6d7c8...", "9a8b7c6d..."],
  "created_at": "2026-03-09T10:00:00Z",
  "updated_at": "2026-03-09T10:30:00Z"
}
```

**Group operations:**
- Create group: write a new JSON file
- Add paper to group: read → append paper_id → write back
- Remove paper from group: read → remove paper_id → write back
- Delete group: delete JSON file (does not affect papers themselves or existing conversations)
- List groups: iterate over `groups/*.json`, read name + paper_ids.length

**Zotero Collections as groups:**
- Zotero collection contents are not stored locally (read in real-time each time)
- Users can see Zotero collections list in the PRAG UI (via Local API `/collections`)
- When creating a conversation with a Zotero collection selected, the scope records the `collection_key`
- Prerequisite: papers in the collection must already be imported into PRAG (unimported papers are filtered out during resolve_scope)

### Relationship Between Groups and Zotero Collections

```
Zotero Collection "Attention Papers"
  ├─ Paper A (imported into PRAG) ──→ Participates in retrieval ✅
  ├─ Paper B (imported into PRAG) ──→ Participates in retrieval ✅
  └─ Paper C (not imported into PRAG) ──→ Skipped ⚠️ UI shows "2 of 3 papers available"
```

Users can also batch import papers from a Zotero collection into PRAG; after import, all become automatically available.

---

## Gap 7: Deletion Cascading

**Strategy: Soft delete (metadata.json marks deleted_at) + deferred physical cleanup.**

### Deletion Flow

```
User deletes paper
│
├─ Step 1: Mark soft delete
│   Read parsed/{paper_id}/metadata.json
│   Set deleted_at = NOW(), write back
│
├─ Step 2: Remove from all local groups
│   Iterate over groups/*.json
│   If paper_ids contains this paper → remove the ID → write back
│
├─ Step 3: Handle associated conversations
│   Iterate over conversations/*.jsonl first lines
│   scope.type == "papers" and paper_ids only contains this paper → mark deleted_at in meta line
│   scope.type == "papers" and paper_ids contains other papers → remove the ID from paper_ids, rewrite first line
│   scope.type == "group" or "zotero_collection" → no action needed (dynamically resolved, deleted papers excluded automatically)
│
├─ Step 4: vectordb cleanup (best effort)
│   collection.delete(where={"paper_id": paper_id})
│   Failure → log to logs/, background retry
│
└─ Step 5: Deferred hard delete (after 30 days or user manual confirmation)
    ├─ Delete papers/{paper_id}.pdf
    ├─ Delete parsed/{paper_id}/ entire directory
    └─ Delete conversation JSONL files marked with deleted_at
```

**Dynamic scope simplifies deletion cascading:** Conversations with `group` and `zotero_collection` scope types do not need modification — on the next question, `resolve_scope` will naturally exclude deleted papers (metadata.json's deleted_at is not null).

**Consistency guarantees:**
- `parsed/{paper_id}/metadata.json` is the source of truth for paper status
- Paper list queries filter out entries where `deleted_at != null`
- `resolve_scope` also filters out deleted papers when resolving groups/collections
- vectordb cleanup failure does not block soft delete — all queries first check metadata.json status, residual chunks will not be returned to the user
- vectordb can be fully rebuilt from parsed/

**Undo delete:** Within 30 days, read metadata.json and set `deleted_at` to null. If vectordb chunks have already been cleaned up, re-vectorize. The paper needs to be manually re-added to groups (if needed).

---

## Global Data Flow Overview

```
=== Import Flow ===
PDF → SHA-256 → paper_id → Check if parsed/{paper_id}/ exists (deduplication)
→ Copy to papers/{paper_id}.pdf
→ Create parsed/{paper_id}/metadata.json (status: pending)
→ Async: MinerU parsing → GROBID references → Structural chunking → Vectorize and write to prag_chunks
→ Update metadata.json status → ready

=== Q&A Flow ===
User asks question → Create/continue conversation JSONL → Append user message line
→ resolve_scope(scope) → Current paper_ids (dynamically resolve group/collection)
→ Orchestrator.run(query, resolved_paper_ids, history)
→ hybrid_search: vectordb.query(where={paper_id in [...]}) + BM25
→ RRF fusion → [Optional cross-encoder] → LLM generation (streaming)
→ Append assistant message line (including citations + retrieval snapshot + resolved_paper_ids)

=== Group Management ===
Create/edit local group → groups/{group_id}.json
Zotero Collections → Read in real-time via Local API, not cached locally
When creating conversation, select scope (manually select papers / local group / Zotero Collection / entire library)

=== Deletion Flow ===
metadata.json marks deleted_at → Remove from groups/ → Handle static scope conversations
→ Best effort vectordb cleanup → Hard delete physical files after 30 days
(Dynamic scope conversations need no handling: resolve_scope automatically excludes deleted papers)

=== Zotero Flow ===
Ping Zotero → Local API lists papers/Collections → Get PDF path → Standard import flow (including zotero_key)
→ Embed zotero://select/... deep links in answers
→ Zotero Collections can be used directly as conversation scope (dynamic reference)
```

---

## Validation Methods

1. **Data flow walkthrough**: Manually walk through the complete path of import → Q&A → deletion, confirming paper_id is consistent across all storage locations
2. **Deduplication test**: Re-importing the same PDF should detect that parsed/{paper_id}/ already exists and reject; after Zotero import, manually uploading the same PDF should be identified as duplicate
3. **JSONL integrity**: Simulate write interruption, confirm only the last line is corrupted and previous messages can be read normally
4. **Deletion completeness**: After deleting a paper, confirm no residuals remain in vectordb, parsed/, papers/, groups/ (after 30 days)
5. **Conversation list performance**: With 100+ JSONL files, reading all first lines should still be < 100ms
6. **Dynamic scope test**: After adding a paper to a group, the next question in an existing conversation should retrieve the new paper; after deleting a paper, it should be automatically excluded
7. **Zotero Collection scope**: Papers in a Zotero Collection not imported into PRAG should be skipped and indicated in the UI
