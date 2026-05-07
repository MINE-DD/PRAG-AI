# Paper Document Type Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `paper` document type with academic-paper-tuned VLM prompts and `markdown-academic` chunking as the default throughout the pipeline.

**Architecture:** `document_type` in PRAG-v2 is used as both the prompt YAML filename (e.g. `vlm_extract/paper.yaml`) and the `{document_type}` template variable rendered into that prompt. Adding a `paper` type means creating two new YAML files and updating three defaults: the pipeline request model, `config.yaml`, and the frontend fallback. `default.yaml` is kept as-is for backward compatibility — it remains valid if someone's localStorage still holds `document_type: default`.

**Tech Stack:** Python/FastAPI, Pydantic, YAML prompts, Vue 3, `config.yaml`

---

## File Map

| Action | File | What changes |
|---|---|---|
| Create | `backend/prompts/vlm_extract/paper.yaml` | Academic extraction prompt |
| Create | `backend/prompts/vlm_metadata/paper.yaml` | Academic metadata prompt |
| Modify | `backend/app/api/pipeline.py:31-32` | `document_type` and `chunk_mode` defaults |
| Modify | `config.yaml:14` | `chunking.mode` default |
| Modify | `frontend-web/js/components/pdf/pipeline-panel.js:37-39` | localStorage fallbacks |
| Keep | `backend/prompts/vlm_extract/default.yaml` | Untouched — backward compat |
| Keep | `backend/prompts/vlm_metadata/default.yaml` | Untouched — backward compat |

---

### Task 1: Create paper VLM extraction prompt

**Files:**
- Create: `backend/prompts/vlm_extract/paper.yaml`

- [ ] **Step 1: Create the file**

```yaml
variables:
  document_type: "Type of document being processed (e.g. academic paper)"
system: |
  You are an academic document extraction assistant.
user: |
  Extract all text from this {document_type} page exactly as it appears.
  Preserve the document structure using Markdown:
  - Use # / ## / ### for section headings
  - Preserve paragraph breaks
  - Format tables and lists in Markdown
  - Preserve mathematical notation as-is
  Do not add commentary or summaries — output only the extracted content.
```

- [ ] **Step 2: Verify it loads without error**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -c "
from app.services.prompt_service import PromptService
ps = PromptService('backend/prompts')
r = ps.render('vlm_extract', 'paper', document_type='academic paper')
print('OK:', r.user[:80])
"
```

Expected output: `OK: Extract all text from this academic paper page…`

- [ ] **Step 3: Commit**

```bash
git add backend/prompts/vlm_extract/paper.yaml
git commit -m "feat: add vlm_extract/paper.yaml prompt"
```

---

### Task 2: Create paper VLM metadata prompt

**Files:**
- Create: `backend/prompts/vlm_metadata/paper.yaml`

- [ ] **Step 1: Create the file**

```yaml
variables:
  document_type: "Type of document being processed (e.g. academic paper)"
system: |
  You are an academic metadata extractor.
user: |
  Extract the following fields from this {document_type} page if present:
  - title
  - authors (comma-separated full names)
  - abstract or summary
  - publication year (4-digit)

  Return ONLY a JSON object with keys: title, authors, abstract, year.
  Use null for any field not found. Do not include any other text.
```

- [ ] **Step 2: Verify it loads without error**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -c "
from app.services.prompt_service import PromptService
ps = PromptService('backend/prompts')
r = ps.render('vlm_metadata', 'paper', document_type='academic paper')
print('OK:', r.user[:80])
"
```

Expected output: `OK: Extract the following fields from this academic paper page…`

- [ ] **Step 3: Commit**

```bash
git add backend/prompts/vlm_metadata/paper.yaml
git commit -m "feat: add vlm_metadata/paper.yaml prompt"
```

---

### Task 3: Update pipeline backend defaults

**Files:**
- Modify: `backend/app/api/pipeline.py:29-32`

- [ ] **Step 1: Write the test**

Add to `tests/integration/test_pipeline_api.py` (create file if it doesn't exist):

```python
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

client = TestClient(app)


def test_pipeline_request_defaults():
    """PipelineRequest defaults must be paper-oriented."""
    from app.api.pipeline import PipelineRequest
    req = PipelineRequest(dir_name="test", collection_name="test-col")
    assert req.document_type == "paper"
    assert req.chunk_mode == "markdown-academic"
    assert req.search_type == "hybrid"
    assert req.chunk_size == 500
    assert req.chunk_overlap == 100
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -m pytest tests/integration/test_pipeline_api.py::test_pipeline_request_defaults -v
```

Expected: FAIL — `assert 'tokens' == 'markdown-academic'` and `assert 'default' == 'paper'`

- [ ] **Step 3: Update the defaults in pipeline.py**

In `backend/app/api/pipeline.py`, change lines 31–32:

```python
class PipelineRequest(BaseModel):
    dir_name: str
    collection_name: str
    pdf_backend: str = "pymupdf"
    metadata_backend: str = "openalex"
    search_type: str = "hybrid"
    chunk_size: int = 500
    chunk_overlap: int = 100
    chunk_mode: str = "markdown-academic"
    document_type: str = "paper"
```

- [ ] **Step 4: Run to confirm pass**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -m pytest tests/integration/test_pipeline_api.py::test_pipeline_request_defaults -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all pass (no existing test hardcodes `document_type="default"` in a pipeline context)

- [ ] **Step 6: Type-check and lint**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run mypy backend/ && uv run ruff check && uv run ruff format --check
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/pipeline.py tests/integration/test_pipeline_api.py
git commit -m "feat: default pipeline to paper document type and markdown-academic chunking"
```

---

### Task 4: Update config.yaml chunking default

**Files:**
- Modify: `config.yaml`

- [ ] **Step 1: Update the mode field**

In `config.yaml`, change:

```yaml
chunking:
  size: 500
  overlap: 100
  mode: markdown-academic
  strategy: fixed
```

(was `mode: tokens`)

- [ ] **Step 2: Verify the config loads cleanly**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -c "
from app.core.config import load_config
c = load_config('config.yaml')
assert c['chunking']['mode'] == 'markdown-academic', c['chunking']
print('OK:', c['chunking'])
"
```

Expected: `OK: {'size': 500, 'overlap': 100, 'mode': 'markdown-academic', 'strategy': 'fixed'}`

- [ ] **Step 3: Run tests to confirm no regressions**

```bash
cd /Users/jose/Repos/PRAG-v2
uv run python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

- [ ] **Step 4: Commit**

```bash
git add config.yaml
git commit -m "config: set default chunking mode to markdown-academic"
```

---

### Task 5: Update frontend pipeline panel defaults

**Files:**
- Modify: `frontend-web/js/components/pdf/pipeline-panel.js:37-39`

- [ ] **Step 1: Update the localStorage fallbacks**

In `frontend-web/js/components/pdf/pipeline-panel.js`, change the `body` of the `fetch` call:

```javascript
        body: JSON.stringify({
          dir_name:         props.dirName,
          collection_name:  form.collectionName,
          pdf_backend:      localStorage.getItem('prag_pdf_backend')    || 'pymupdf',
          metadata_backend: localStorage.getItem('prag_meta_backend')   || 'openalex',
          document_type:    localStorage.getItem('prag_document_type')  || 'paper',
        }),
```

(was `|| 'default'` on the last line)

- [ ] **Step 2: Manual verification**

Open the app in a browser (or check the network tab): click **Run Pipeline** and confirm the POST body sent to `/pipeline/run` includes `"document_type": "paper"` when no localStorage override is set.

To clear any stale localStorage value first, run in browser console:
```javascript
localStorage.removeItem('prag_document_type')
```

- [ ] **Step 3: Commit**

```bash
git add frontend-web/js/components/pdf/pipeline-panel.js
git commit -m "feat: default frontend pipeline document_type to paper"
```

---

## Self-Review

**Spec coverage:**
- `paper` document type (vlm_extract + vlm_metadata): Tasks 1 & 2 ✓
- Pipeline backend default `document_type: "paper"`: Task 3 ✓
- Pipeline backend default `chunk_mode: "markdown-academic"`: Task 3 ✓
- `config.yaml` chunking mode default: Task 4 ✓
- Frontend fallback updated: Task 5 ✓
- `default.yaml` kept for backward compat: confirmed — not touched ✓

**Placeholder scan:** None. All steps contain the exact file content or command needed.

**Type consistency:** `PipelineRequest` field names match what `generate()` uses (`req.chunk_mode`, `req.document_type`) — no changes needed to the generator function body.

**Backward compat note:** Any user with `prag_document_type: default` in localStorage will continue to use the old `default.yaml` prompts and `tokens` chunking (those values come from the client, not the server default). Only new runs without a localStorage override will pick up the new defaults.
