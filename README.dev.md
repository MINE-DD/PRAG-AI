# Developer Guide — PRAG-AI

This is the developer companion to the [user-facing README](README.md).

## Architecture Overview

```
frontend-web/           Static HTML/JS (served via GitHub Pages)
backend/app/
  api/                  FastAPI route handlers — thin, delegate to services
  services/             Business logic (PDF processing, embeddings, RAG)
  models/               Pydantic request/response schemas
  core/                 Configuration (Settings via pydantic-settings)
backend/prompts/        YAML prompt templates per task
docker-compose.yml      Runs backend + Qdrant
```

See [docs/architecture.md](docs/architecture.md) for the full class diagram.

Routers registered in `backend/app/main.py`:
`health`, `collections`, `papers`, `rag`, `summarize`, `compare`,
`preprocess`, `ingest`, `settings`, `zotero`, `pipeline`, `prompts`

## Local Dev Setup (without Docker)

```bash
# Install dependencies
uv sync --extra dev

# Qdrant still needs Docker (lightweight container)
docker run -d -p 6333:6333 qdrant/qdrant

# Start the backend with hot-reload
uv run uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Verify
curl http://localhost:8000/health
```

A minimal `config.yaml` in the project root:
```yaml
models:
  embedding: nomic-embed-text:latest
chunking:
  size: 500
```

## How to Add a New API Endpoint

1. Create `backend/app/api/my_feature.py`:

   ```python
   from fastapi import APIRouter

   router = APIRouter(prefix="/my-feature", tags=["my-feature"])

   @router.get("/")
   async def get_my_feature():
       return {"status": "ok"}
   ```

2. Register in `backend/app/main.py` (follow the existing import/include pattern):

   ```python
   from app.api import my_feature
   app.include_router(my_feature.router, tags=["my-feature"])
   ```

3. Add an integration test in `tests/integration/test_my_feature_api.py`
   following `tests/integration/test_health_api.py` as a model.

4. Run: `pytest tests/integration/test_my_feature_api.py -v`

## How to Add a New Service

Create `backend/app/services/my_service.py` following the existing pattern:

```python
class MyService:
    def __init__(self, config: dict):
        self.config = config

    def do_thing(self, input: str) -> str:
        # implementation
        ...
```

Add unit tests in `tests/unit/test_my_service.py`. Use `unittest.mock.patch`
to isolate external dependencies (see `tests/unit/test_ollama_service.py` for
a reference pattern).

## How to Add Custom Prompts

Prompts live in `backend/prompts/<task>/` as YAML files.
The prompt service discovers and validates them at startup.

### YAML structure

```yaml
variables:
  context: "Description of what this variable contains"
  question: "The user's question"
  word_target: "Approximate response length in tokens"
  # add any custom variables your template needs

system: |
  Your system prompt here. Use {variable_name} for substitution.

user: |
  {context}

  Question: {question}
```

**Rules:**
- File goes in `backend/prompts/rag/`, `backend/prompts/compare/`, or
  `backend/prompts/summarize/`
- Variable names in `{braces}` in the templates must match keys in `variables:`
- The filename (without `.yaml`) becomes the prompt's ID in the API
- The new prompt appears immediately in `/api/prompts` and the frontend dropdown

**Example — add a Spanish RAG prompt:**
```bash
cp backend/prompts/rag/default.yaml backend/prompts/rag/spanish.yaml
# Edit spanish.yaml: update system/user text to respond in Spanish
```

## How to Add a New Frontend Tab

The frontend is plain HTML/JS in `frontend-web/index.html`.
Use the Compare tab as your reference model.

**Step 1 — Add the tab button** (find the tab bar section):
```html
<button class="tab-btn" data-tab="my-tab">My Tab</button>
```

**Step 2 — Add the panel** (after the last existing panel):
```html
<div id="tab-my-tab" class="tab-panel" style="display:none">
  <h2>My Feature</h2>
  <button id="my-tab-btn">Run</button>
  <div id="my-tab-result"></div>
</div>
```

**Step 3 — Wire the API call** (find the Compare JS block and replicate):
```javascript
document.getElementById('my-tab-btn').addEventListener('click', async () => {
  const response = await fetch('http://localhost:8000/my-feature/', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  });
  const data = await response.json();
  document.getElementById('my-tab-result').textContent = JSON.stringify(data);
});
```

**Step 4 — Test locally:**
```bash
cd frontend-web
python3 -m http.server 3000
# Open http://localhost:3000
```

Tab switching is handled generically — no changes needed to the tab controller.

## CI Badges

| Badge | Meaning |
|---|---|
| CI | Tests pass on Ubuntu + Windows across Python 3.12 and 3.13 |
| Codecov | % of `backend/` source lines executed by the test suite |
| License | Apache 2.0 — free to use, modify, and distribute |

## Getting a Zenodo DOI (first release)

1. Go to [zenodo.org](https://zenodo.org) and log in with GitHub
2. Under GitHub → Settings, enable the `MINE-DD/PRAG-AI` repository
3. Create a GitHub release with a semver tag (`v0.1.0`)
4. Zenodo automatically archives it and mints a DOI
5. Copy the DOI badge URL from Zenodo and add to `README.md`
6. Set the `doi:` field in `CITATION.cff` to the new DOI
