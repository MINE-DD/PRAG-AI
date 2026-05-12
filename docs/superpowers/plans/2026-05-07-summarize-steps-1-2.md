# Summarize Service Steps 1 & 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the fragile `paper_id` (Step 1) and add a minimal synchronous Summarize card to the Explore tab (Step 2).

**Architecture:** Step 1 replaces `paper_id = md_file.stem` with the already-computed `unique_id` slug in `ingestion_service.py`. Step 2 adds a `GET /collections/{id}/papers/{paper_id}/summarize` endpoint that reads the markdown file directly, truncates to the LLM context budget, calls the LLM, and returns JSON. The frontend adds a collapsed Summarize card below the metadata card.

**Tech Stack:** Python 3.12, FastAPI, Qdrant scroll API, Vue 3 Composition API, Ollama LLM, YAML prompts

---

### Task 1: Fix paper_id in ingestion_service.py

**Files:**
- Modify: `backend/app/services/ingestion_service.py:109-234`
- Test: `backend/tests/test_ingestion_service.py` (existing, extend)

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_ingestion_service.py`:

```python
def test_paper_id_uses_unique_id_slug(tmp_path, ingestion_service):
    """paper_id must be the unique_id slug, not the filename stem."""
    md = tmp_path / "Beck and Köllner - 2023 - GHisBERT.md"
    md.write_text("# Introduction\nHello world.", encoding="utf-8")
    meta = tmp_path / "Beck and Köllner - 2023 - GHisBERT_metadata.json"
    meta.write_json = None  # not used; pass metadata_path=None
    result = ingestion_service.ingest_file(
        collection_id="test-col",
        md_path=str(md),
        metadata_path=None,
    )
    # paper_id must be URL-safe (no spaces, accented chars)
    assert " " not in result["paper_id"]
    assert result["paper_id"] == result["unique_id"]


def test_paper_id_collision_handling(tmp_path, ingestion_service):
    """Second ingest with same unique_id gets _2 suffix."""
    md = tmp_path / "paper.md"
    md.write_text("# Intro\nBody.", encoding="utf-8")
    meta = {"title": "MyPaper", "authors": ["Smith"], "publication_date": "2023"}
    import json
    meta_path = tmp_path / "paper_metadata.json"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    r1 = ingestion_service.ingest_file("test-col", str(md), str(meta_path))
    r2 = ingestion_service.ingest_file("test-col", str(md), str(meta_path))
    assert r1["paper_id"] == "SmithMyPaper2023"
    assert r2["paper_id"] == "SmithMyPaper2023_2"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/test_ingestion_service.py::test_paper_id_uses_unique_id_slug backend/tests/test_ingestion_service.py::test_paper_id_collision_handling -v
```

Expected: FAIL (paper_id is currently md_file.stem, not unique_id)

- [ ] **Step 3: Implement the fix**

In `backend/app/services/ingestion_service.py`, replace:

```python
        # Derive paper_id from filename stem
        paper_id = md_file.stem

        # Build unique_id from metadata
        unique_id = self._generate_unique_id(
            title=metadata.get("title", paper_id),
            authors=metadata.get("authors", []),
            year=self._extract_year(metadata.get("publication_date")),
        )
```

With:

```python
        # Build unique_id from metadata
        unique_id = self._generate_unique_id(
            title=metadata.get("title", md_file.stem),
            authors=metadata.get("authors", []),
            year=self._extract_year(metadata.get("publication_date")),
        )

        # Use unique_id as paper_id; handle collisions by appending _2, _3, …
        collection_meta_dir = self.data_dir / collection_id / "metadata"
        collection_meta_dir.mkdir(parents=True, exist_ok=True)
        paper_id = unique_id
        candidate = collection_meta_dir / f"{paper_id}.json"
        counter = 2
        while candidate.exists():
            paper_id = f"{unique_id}_{counter}"
            candidate = collection_meta_dir / f"{paper_id}.json"
            counter += 1
```

Also remove the duplicate `collection_meta_dir.mkdir(...)` that appears later in the method (around line 214), and update the `dest` path to use `candidate` instead of recomputing:

```python
        # Copy metadata JSON to collection's metadata/ dir  (collection_meta_dir already set above)
        paper_meta = {
            **metadata,
            "paper_id": paper_id,
            "unique_id": unique_id,
            "preprocessed_dir": md_file.parent.name,
            "source_pdf": md_file.stem,  # keep original stem for file lookup
            "chunks_created": len(chunks),
            "references": references,
            "ingested_at": datetime.now(UTC).isoformat(),
        }
        candidate.write_text(json.dumps(paper_meta, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/test_ingestion_service.py -v
```

Expected: all pass

- [ ] **Step 5: Type-check and lint**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run mypy backend/ && uv run ruff check && uv run ruff format --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/ingestion_service.py backend/tests/test_ingestion_service.py
git commit -m "fix: use unique_id slug as paper_id in ingestion (with collision handling)"
```

---

### Task 2: Add scroll-based chunk fetcher to QdrantService

**Files:**
- Modify: `backend/app/services/qdrant_service.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_qdrant_service.py` (or create it):

```python
def test_get_chunks_for_paper_returns_sorted(qdrant_service_with_data):
    chunks = qdrant_service_with_data.get_chunks_for_paper("test-col", "Smith2023", limit=10)
    indices = [c.payload["metadata"]["chunk_index"] for c in chunks]
    assert indices == sorted(indices)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/ -k "get_chunks_for_paper" -v
```

Expected: AttributeError (method does not exist yet)

- [ ] **Step 3: Add `get_chunks_for_paper` to QdrantService**

Append to `backend/app/services/qdrant_service.py`:

```python
    def get_chunks_for_paper(
        self, collection_name: str, paper_id: str, limit: int = 10
    ) -> list:
        """Fetch up to `limit` chunks for a paper, sorted by chunk_index ascending."""
        query_filter = Filter(
            must=[FieldCondition(key="paper_id", match=MatchValue(value=paper_id))]
        )
        results = []
        offset = None
        while len(results) < limit:
            batch, offset = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=query_filter,
                limit=min(100, limit - len(results)),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            results.extend(batch)
            if offset is None:
                break
        results.sort(key=lambda p: p.payload.get("metadata", {}).get("chunk_index", 0))
        return results[:limit]
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/ -k "qdrant" -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/qdrant_service.py
git commit -m "feat: add get_chunks_for_paper scroll method to QdrantService"
```

---

### Task 3: Create academic_paper.yaml prompt

**Files:**
- Create: `backend/prompts/summarize/academic_paper.yaml`

- [ ] **Step 1: Create the prompt file**

```yaml
variables:
  context: "Full text (or excerpts) of a single academic paper"
system: |
  You are a research assistant specializing in academic paper analysis.
  Your task is to produce a clear, structured summary of a single paper.
  Write for an audience of researchers who want to quickly understand the paper's contribution.
  Be factual and concise. Do not invent information not present in the text.
user: |
  Read the following academic paper text and write a summary covering:
  1. Why this paper matters — the problem it addresses and its significance
  2. What it proposes — the approach, method, or system introduced
  3. What it concludes — key results, findings, and takeaways

  Write 3–4 focused paragraphs. Do not include headings or bullet points.

  Paper text:
  {context}
```

- [ ] **Step 2: Verify prompt loads without error**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -c "
from app.services.prompt_service import PromptService
ps = PromptService('backend/prompts')
r = ps.render('summarize', 'academic_paper', context='Test paper text here.')
print('system:', r.system[:60])
print('user prefix:', r.user[:60])
"
```

Expected: prints first 60 chars of each without raising.

- [ ] **Step 3: Commit**

```bash
git add backend/prompts/summarize/academic_paper.yaml
git commit -m "feat: add academic_paper summarize prompt"
```

---

### Task 4: Add GET /collections/{id}/papers/{paper_id}/summarize endpoint

**Files:**
- Modify: `backend/app/api/summarize.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_summarize.py` (or create it):

```python
def test_summarize_paper_returns_summary(client, collection_with_paper):
    collection_id, paper_id = collection_with_paper
    response = client.get(f"/collections/{collection_id}/papers/{paper_id}/summarize")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert data["method"] in ("markdown", "rag")
    assert len(data["summary"]) > 0


def test_summarize_paper_404_on_missing(client, existing_collection):
    response = client.get(f"/collections/{existing_collection}/papers/NoSuchPaper/summarize")
    assert response.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/test_summarize.py::test_summarize_paper_returns_summary -v
```

Expected: 404 (endpoint does not exist yet)

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/api/summarize.py` after the existing imports:

```python
import json
from pathlib import Path

from fastapi.responses import JSONResponse
```

Add a new response model and endpoint (append after the existing `summarize_papers` function):

```python
class SinglePaperSummaryResponse(BaseModel):
    summary: str
    method: str  # "markdown" or "rag"


@router.get(
    "/collections/{collection_id}/papers/{paper_id}/summarize",
    response_model=SinglePaperSummaryResponse,
)
def summarize_single_paper(
    collection_id: str,
    paper_id: str,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """Summarize a single paper by reading its markdown or falling back to Qdrant chunks."""
    from app.core.config import load_config, settings

    collection_service, qdrant, metadata_service, llm_service, llm_info = services

    # Validate collection
    collection = collection_service.get_collection(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Load paper metadata
    data_dir = Path(settings.data_dir)
    meta_path = data_dir / collection_id / "metadata" / f"{paper_id}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="Paper not found")
    paper_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # Compute token budget: max_allowed_tokens × 4 chars × 0.8 safety margin
    config = load_config("config.yaml")
    max_allowed = config.get("models", {}).get("max_allowed_tokens", 8192)
    char_budget = int(max_allowed * 4 * 0.8)

    context: str | None = None
    method = "rag"

    # Try markdown path first
    preprocessed_dir = paper_meta.get("preprocessed_dir")
    source_pdf = paper_meta.get("source_pdf")
    if preprocessed_dir and source_pdf:
        # source_pdf may be "filename.pdf" or just the stem
        stem = Path(source_pdf).stem
        md_path = Path(settings.preprocessed_dir) / preprocessed_dir / f"{stem}.md"
        if md_path.exists():
            raw = md_path.read_text(encoding="utf-8")
            context = raw[:char_budget]
            method = "markdown"

    # RAG fallback: top-10 chunks sorted by chunk_index
    if context is None:
        chunks = qdrant.get_chunks_for_paper(collection_id, paper_id, limit=10)
        if not chunks:
            raise HTTPException(status_code=404, detail="No content found for paper")
        context = "\n\n".join(c.payload["chunk_text"] for c in chunks)[:char_budget]

    # Render prompt and call LLM
    rendered = prompt_service.render("summarize", "academic_paper", context=context)
    summary = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
    )

    return SinglePaperSummaryResponse(summary=summary, method=method)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run python -m pytest backend/tests/test_summarize.py -v
```

- [ ] **Step 5: Type-check and lint**

```bash
cd /Users/jose/Repos/PRAG-v2 && uv run mypy backend/ && uv run ruff check && uv run ruff format --check
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/summarize.py
git commit -m "feat: add GET summarize endpoint for single paper"
```

---

### Task 5: Add Summarize card to Explore tab

**Files:**
- Modify: `frontend-web/js/tabs/tab-explore.js`

- [ ] **Step 1: Add reactive refs and summarize function to setup()**

In the `setup(props)` block, after `const loading = ref(false)`, add:

```javascript
const summarizing   = ref(false)
const summaryResult = ref(null)
const summaryError  = ref(null)
const summaryMethod = ref(null)
```

Add `selectPaper` side-effect to reset summary state on paper change (inside `selectPaper` before the try block):

```javascript
    async function selectPaper(paper) {
      selected.value = paper
      loading.value = true
      detail.value = null
      error.value = null
      summarizing.value = false
      summaryResult.value = null
      summaryError.value = null
      summaryMethod.value = null
      // ... rest of existing function unchanged
```

Add the summarize function:

```javascript
    async function generateSummary() {
      if (!detail.value) return
      summarizing.value = true
      summaryResult.value = null
      summaryError.value = null
      summaryMethod.value = null
      try {
        const res = await api.get(
          `/collections/${collectionId.value}/papers/${encodeURIComponent(detail.value.paper_id)}/summarize`
        )
        summaryResult.value = res.summary
        summaryMethod.value = res.method
      } catch (e) {
        summaryError.value = e.message
      } finally {
        summarizing.value = false
      }
    }
```

Update the return statement to expose new refs:

```javascript
    return { error, papers, selected, detail, loading, collectionId, selectPaper,
             summarizing, summaryResult, summaryError, summaryMethod, generateSummary }
```

- [ ] **Step 2: Add Summarize card to template**

In the template, after the closing `</div>` of the existing metadata card (after the abstract collapsible), add:

```html
          <!-- Summarize card -->
          <div class="card" style="margin-top:16px">
            <div style="font-weight:600;font-size:14px;margin-bottom:10px">
              Summary
              <span v-if="summaryMethod" class="badge badge-blue" style="margin-left:6px;font-weight:400">
                {{ summaryMethod }}
              </span>
            </div>

            <div v-if="summaryError" class="alert alert-error" style="margin-bottom:8px">
              {{ summaryError }}
            </div>

            <div v-if="summarizing" class="flex items-center gap-8" style="margin-bottom:8px">
              <span class="spinner"></span>
              <span class="text-muted text-sm">Generating summary…</span>
            </div>

            <div v-if="summaryResult" style="line-height:1.7;font-size:14px;margin-bottom:12px;white-space:pre-wrap">
              {{ summaryResult }}
            </div>

            <button class="btn btn-primary btn-sm" @click="generateSummary" :disabled="summarizing">
              {{ summaryResult ? 'Regenerate' : 'Generate summary' }}
            </button>
          </div>
```

- [ ] **Step 3: Verify the UI renders**

Start the dev server and open the Explore tab. Select a paper. The Summarize card should appear below the metadata card with a "Generate summary" button. Clicking it should show a spinner then the result.

- [ ] **Step 4: Commit**

```bash
git add frontend-web/js/tabs/tab-explore.js
git commit -m "feat: add Summarize card to Explore tab (sync, Step 2)"
```

---

## Self-Review

**Spec coverage check:**
- Step 1 (fix paper_id): Task 1 ✓
- Step 2 markdown read + truncation: Task 4 ✓
- Step 2 RAG fallback via scroll: Task 2 + Task 4 ✓
- academic_paper.yaml prompt: Task 3 ✓
- Frontend collapsed card with button/spinner/result: Task 5 ✓
- Regenerate button after first result: Task 5 ✓

**Placeholder scan:** None found — all steps have complete code.

**Type consistency:** `get_chunks_for_paper` used consistently in Task 2 and Task 4. `SinglePaperSummaryResponse` defined and returned correctly. `summaryResult`, `summarizing`, `summaryMethod`, `summaryError` consistent between setup and template.
