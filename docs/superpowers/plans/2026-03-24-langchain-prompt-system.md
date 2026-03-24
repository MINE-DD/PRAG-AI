# Prompt System — langchain-core Integration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded inline prompts in RAG, summarize, and compare handlers with a file-based YAML prompt system that separates system from user prompts, rendered via `langchain-core`.

**Architecture:** A new `PromptService` loads YAML files from `backend/prompts/` and renders them via `langchain-core`'s `ChatPromptTemplate`. Each API handler accepts an optional `prompt_name` field (defaults to `"default"`) and delegates prompt assembly to `PromptService`. LLM services gain a `system` parameter. A new read-only `/prompts` API exposes available prompts to the frontend.

**Tech Stack:** Python 3.12, FastAPI, `langchain-core>=1.2,<2.0`, PyYAML (already a dep), pytest + unittest.mock

---

## File Map

| Action | File |
|--------|------|
| Modify | `pyproject.toml` |
| Modify | `backend/app/core/config.py` |
| Create | `backend/app/services/prompt_service.py` |
| Create | `backend/prompts/rag/default.yaml` |
| Create | `backend/prompts/summarize/default.yaml` |
| Create | `backend/prompts/compare/default.yaml` |
| Create | `backend/app/api/prompts.py` |
| Modify | `backend/app/main.py` |
| Modify | `backend/app/services/anthropic_service.py` |
| Modify | `backend/app/services/google_service.py` |
| Modify | `backend/app/api/summarize.py` (prerequisite refactor) |
| Modify | `backend/app/api/rag.py` |
| Modify | `backend/app/api/compare.py` |
| Modify | `backend/Dockerfile` |
| Modify | `docker-compose.yml` |
| Create | `tests/unit/test_prompt_service.py` |
| Create | `tests/unit/test_anthropic_service.py` |
| Create | `tests/unit/test_google_service.py` |
| Create | `tests/integration/test_prompts_api.py` |

---

## Task 1: Add dependency and config field

**Files:**
- Modify: `pyproject.toml`
- Modify: `backend/app/core/config.py`

- [ ] **Step 1: Add langchain-core to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list (NOT to `optional-dependencies`):

```toml
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.6.0",
    "pydantic-settings>=2.1.0",
    "qdrant-client>=1.7.0",
    "docling>=2.74.0",
    "pyyaml>=6.0",
    "python-multipart>=0.0.6",
    "httpx>=0.26.0",
    "ollama>=0.1.0",
    "fastembed>=0.4.0",
    "pymupdf4llm>=0.0.17",
    "langchain-core>=1.2,<2.0",
]
```

- [ ] **Step 2: Sync dependencies**

```bash
cd /Users/jose/Repos/PRAG-v2
uv sync
```

Expected: lockfile updated, `langchain-core` installed.

- [ ] **Step 3: Add prompts_dir to Settings**

In `backend/app/core/config.py`, add one field to `Settings`:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    qdrant_url: str = "http://qdrant:6333"
    ollama_url: str = "http://host.docker.internal:11434"
    data_dir: str = "/data/collections"
    pdf_input_dir: str = "/data/pdf_input"
    preprocessed_dir: str = "/data/preprocessed"
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    prompts_dir: str = "/app/prompts"   # ← add this line
```

- [ ] **Step 4: Verify import works**

```bash
cd /Users/jose/Repos/PRAG-v2
python -c "from langchain_core.prompts import ChatPromptTemplate; print('ok')"
```

Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock backend/app/core/config.py
git commit -m "feat: add langchain-core dep and prompts_dir config"
```

---

## Task 2: Create PromptService (TDD)

**Files:**
- Create: `tests/unit/test_prompt_service.py`
- Create: `backend/app/services/prompt_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_prompt_service.py`:

```python
import pytest
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))


def make_yaml(tmp_path, task: str, name: str, system: str, user: str) -> None:
    task_dir = tmp_path / task
    task_dir.mkdir(exist_ok=True)
    (task_dir / f"{name}.yaml").write_text(f"system: |\n  {system}\nuser: |\n  {user}\n")


def test_list_prompts(tmp_path):
    from app.services.prompt_service import PromptService
    make_yaml(tmp_path, "rag", "default", "sys", "usr")
    make_yaml(tmp_path, "rag", "concise", "sys2", "usr2")

    service = PromptService(str(tmp_path))
    result = service.list_prompts("rag")

    assert result == ["concise", "default"]


def test_list_prompts_unknown_task_raises(tmp_path):
    from app.services.prompt_service import PromptService
    service = PromptService(str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Unknown task type"):
        service.list_prompts("nonexistent")


def test_get_raw_returns_content_with_name(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text("system: You are helpful\nuser: Answer {question}\n")

    service = PromptService(str(tmp_path))
    result = service.get_raw("rag", "default")

    assert result["system"] == "You are helpful"
    assert "question" in result["user"]
    assert result["name"] == "default"


def test_get_raw_not_found_raises(tmp_path):
    from app.services.prompt_service import PromptService
    (tmp_path / "rag").mkdir()

    service = PromptService(str(tmp_path))

    with pytest.raises(FileNotFoundError, match="not found"):
        service.get_raw("rag", "nonexistent")


def test_render_substitutes_variables(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text(
        "system: You are {role}\nuser: Answer {question}\n"
    )

    service = PromptService(str(tmp_path))
    result = service.render("rag", "default", role="a helper", question="What is AI?")

    assert result.system == "You are a helper"
    assert result.user == "Answer What is AI?"


def test_render_missing_variable_raises(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text(
        "system: You are a helper\nuser: Answer {question} using {context}\n"
    )

    service = PromptService(str(tmp_path))

    with pytest.raises(ValueError, match="Missing template variable"):
        service.render("rag", "default", question="What is AI?")  # context missing


def test_render_missing_yaml_keys_raises(tmp_path):
    from app.services.prompt_service import PromptService
    task_dir = tmp_path / "rag"
    task_dir.mkdir()
    (task_dir / "default.yaml").write_text("system: You are helpful\n")  # no user key

    service = PromptService(str(tmp_path))

    with pytest.raises(ValueError, match="must have 'system' and 'user' keys"):
        service.render("rag", "default")


def test_validate_defaults_warns_on_missing_default(tmp_path, caplog):
    from app.services.prompt_service import PromptService
    import logging
    (tmp_path / "rag").mkdir()  # no default.yaml inside

    with caplog.at_level(logging.WARNING):
        PromptService(str(tmp_path))

    assert "No default.yaml" in caplog.text
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_prompt_service.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — `prompt_service` does not exist yet.

- [ ] **Step 3: Implement PromptService**

Create `backend/app/services/prompt_service.py`:

```python
from dataclasses import dataclass
from pathlib import Path
import logging
import yaml
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)


@dataclass
class RenderedPrompt:
    system: str
    user: str


class PromptService:
    def __init__(self, prompts_dir: str):
        self._dir = Path(prompts_dir)
        self._validate_defaults()

    def _validate_defaults(self) -> None:
        """Warn at startup if any task directory is missing a default.yaml."""
        if not self._dir.exists():
            logger.warning("Prompts directory not found: %s", self._dir)
            return
        for task_dir in self._dir.iterdir():
            if task_dir.is_dir() and not (task_dir / "default.yaml").exists():
                logger.warning("No default.yaml found for task '%s'", task_dir.name)

    def list_prompts(self, task_type: str) -> list[str]:
        """Return sorted prompt names available for a task type."""
        task_dir = self._dir / task_type
        if not task_dir.exists():
            raise FileNotFoundError(f"Unknown task type: '{task_type}'")
        return sorted(f.stem for f in task_dir.glob("*.yaml"))

    def get_raw(self, task_type: str, name: str) -> dict:
        """Return raw YAML content with name injected. Used by the API for display."""
        path = self._dir / task_type / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt '{name}' not found for task '{task_type}'")
        data = yaml.safe_load(path.read_text())
        data["name"] = name
        return data

    def render(self, task_type: str, name: str, **variables) -> RenderedPrompt:
        """Render system and user prompts with variables substituted."""
        raw = self.get_raw(task_type, name)
        if "system" not in raw or "user" not in raw:
            raise ValueError(
                f"Prompt '{name}' for task '{task_type}' must have 'system' and 'user' keys"
            )
        try:
            template = ChatPromptTemplate.from_messages([
                ("system", raw["system"]),
                ("human", raw["user"]),
            ])
            messages = template.invoke(variables).to_messages()
        except KeyError as e:
            raise ValueError(
                f"Missing template variable {e} for prompt '{name}' in task '{task_type}'"
            ) from e
        return RenderedPrompt(
            system=messages[0].content,
            user=messages[1].content,
        )


# Module-level singleton — instantiated at import time using settings.
# Tests override this via FastAPI dependency_overrides[get_prompt_service].
from app.core.config import settings as _settings  # noqa: E402

_prompt_service = PromptService(_settings.prompts_dir)


def get_prompt_service() -> PromptService:
    return _prompt_service
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_prompt_service.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prompt_service.py tests/unit/test_prompt_service.py
git commit -m "feat: add PromptService with langchain-core rendering"
```

---

## Task 3: Create default YAML prompt files

**Files:**
- Create: `backend/prompts/rag/default.yaml`
- Create: `backend/prompts/summarize/default.yaml`
- Create: `backend/prompts/compare/default.yaml`

No tests needed — these are data files validated by `PromptService` at load time.

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p /Users/jose/Repos/PRAG-v2/backend/prompts/rag
mkdir -p /Users/jose/Repos/PRAG-v2/backend/prompts/summarize
mkdir -p /Users/jose/Repos/PRAG-v2/backend/prompts/compare
```

- [ ] **Step 2: Create rag/default.yaml**

Create `backend/prompts/rag/default.yaml`:

```yaml
system: |
  You are a research assistant. Answer questions using ONLY the excerpts provided.
  Write in the style of a Wikipedia article: concise sentences, coherent paragraphs.
  Cite sources using the citation keys provided in square brackets, e.g. [AuthorTitle2024].
  Do NOT invent citation keys or use numbered references from the source text.
  The valid citation keys are: {keys_list}
  If the excerpts do not contain enough information, reply with: "{cannot_answer_phrase}"
user: |
  Context:

  {context}

  ----

  Question: {question}

  Aim for approximately {word_target} tokens.
```

- [ ] **Step 3: Create summarize/default.yaml**

Create `backend/prompts/summarize/default.yaml`:

```yaml
system: |
  You are a research assistant that summarizes academic papers clearly and accurately.
  Focus on the key contributions, methodology, and findings.
  Write in clear, accessible language suitable for a research audience.
user: |
  Based on the following excerpts from {paper_count} research paper(s), provide a comprehensive summary covering:
  1. The main research question or problem addressed
  2. The methodology or approach used
  3. Key findings or results
  4. Significance and implications

  Paper excerpts:
  {context}

  Provide a clear, concise summary in 2-3 paragraphs.
```

- [ ] **Step 4: Create compare/default.yaml**

Create `backend/prompts/compare/default.yaml`:

```yaml
system: |
  You are a research analyst that compares academic papers objectively and thoroughly.
  Be specific, reference papers by their labels (Paper A, Paper B, etc.), and support
  your analysis with evidence from the provided excerpts.
user: |
  Compare the following {paper_count} research papers. {aspect_instruction}

  {combined_content}

  Provide a structured comparison covering:
  1. **Papers:** List each paper by its label (Paper A, Paper B, etc.) with key metadata.
  2. **Similarities:** What do these papers have in common?
  3. **Differences:** How do they differ in approach, methods, or conclusions?
  4. **Key Insights:** What can we learn from comparing these papers?
```

- [ ] **Step 5: Verify YAML files load correctly**

```bash
cd /Users/jose/Repos/PRAG-v2
python -c "
import yaml
from pathlib import Path
for f in Path('backend/prompts').rglob('*.yaml'):
    data = yaml.safe_load(f.read_text())
    assert 'system' in data and 'user' in data, f'Bad YAML: {f}'
    print(f'OK: {f}')
"
```

Expected: prints three `OK:` lines, no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/prompts/
git commit -m "feat: add default prompt YAML files for rag, summarize, compare"
```

---

## Task 4: Create prompts API router (TDD)

**Files:**
- Create: `tests/integration/test_prompts_api.py`
- Create: `backend/app/api/prompts.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/integration/test_prompts_api.py`:

```python
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock
from fastapi.testclient import TestClient

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.main import app
from app.services.prompt_service import get_prompt_service


def _mock_service():
    mock = Mock()
    mock.list_prompts.return_value = ["concise", "default"]
    mock.get_raw.return_value = {
        "name": "default",
        "system": "You are a research assistant.",
        "user": "Context: {context}\nQuestion: {question}",
    }
    return mock


@pytest.fixture(autouse=True)
def override_prompt_service():
    app.dependency_overrides[get_prompt_service] = lambda: _mock_service()
    yield
    app.dependency_overrides.pop(get_prompt_service, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_list_prompts_returns_names(client):
    response = client.get("/prompts/rag")
    assert response.status_code == 200
    assert response.json() == ["concise", "default"]


def test_get_prompt_returns_content(client):
    response = client.get("/prompts/rag/default")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "default"
    assert "system" in data
    assert "user" in data


def test_list_prompts_unknown_task_returns_404(client):
    mock = Mock()
    mock.list_prompts.side_effect = FileNotFoundError("Unknown task type: 'unknown'")
    app.dependency_overrides[get_prompt_service] = lambda: mock

    response = client.get("/prompts/unknown")
    assert response.status_code == 404


def test_get_prompt_not_found_returns_404(client):
    mock = Mock()
    mock.get_raw.side_effect = FileNotFoundError("Prompt 'gone' not found for task 'rag'")
    app.dependency_overrides[get_prompt_service] = lambda: mock

    response = client.get("/prompts/rag/gone")
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_prompts_api.py -v
```

Expected: `404` or import error — router not registered yet.

- [ ] **Step 3: Create prompts router**

Create `backend/app/api/prompts.py`:

```python
from fastapi import APIRouter, HTTPException, Depends
from app.services.prompt_service import PromptService, get_prompt_service

router = APIRouter()


@router.get("/prompts/{task_type}")
def list_prompts(
    task_type: str,
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """List available prompt names for a task type."""
    try:
        return prompt_service.list_prompts(task_type)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/prompts/{task_type}/{name}")
def get_prompt(
    task_type: str,
    name: str,
    prompt_service: PromptService = Depends(get_prompt_service),
):
    """Get the raw system and user template for a named prompt."""
    try:
        return prompt_service.get_raw(task_type, name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add the import and router registration:

```python
from app.api import (
    health, collections, papers, rag, summarize, compare,
    preprocess, ingest, settings as settings_api, zotero, pipeline,
    prompts,   # ← add this
)
```

And add after the other `include_router` calls:

```python
app.include_router(prompts.router, tags=["prompts"])
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_prompts_api.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/prompts.py backend/app/main.py tests/integration/test_prompts_api.py
git commit -m "feat: add read-only prompts API router"
```

---

## Task 5: Add system param to AnthropicService (TDD)

**Files:**
- Create: `tests/unit/test_anthropic_service.py`
- Modify: `backend/app/services/anthropic_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_anthropic_service.py`:

```python
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.anthropic_service import AnthropicService


@pytest.fixture
def service():
    with patch("app.services.anthropic_service.anthropic") as mock_lib:
        mock_client = Mock()
        mock_lib.Anthropic.return_value = mock_client
        svc = AnthropicService(api_key="test-key")
        svc._mock_client = mock_client
        yield svc


def test_generate_passes_system_as_top_level_param(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="The answer")]
    service._mock_client.messages.create.return_value = mock_response

    result = service.generate(prompt="What is AI?", system="You are an expert.")

    assert result == "The answer"
    call_kwargs = service._mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == "You are an expert."
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is AI?"}]


def test_generate_system_defaults_to_empty_string(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="ok")]
    service._mock_client.messages.create.return_value = mock_response

    service.generate(prompt="test")  # no system arg

    call_kwargs = service._mock_client.messages.create.call_args.kwargs
    assert call_kwargs["system"] == ""


def test_generate_returns_text(service):
    mock_response = Mock()
    mock_response.content = [Mock(text="hello")]
    service._mock_client.messages.create.return_value = mock_response

    assert service.generate(prompt="hi") == "hello"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_anthropic_service.py -v
```

Expected: `test_generate_passes_system_as_top_level_param` FAILS — `system` kwarg not passed.

- [ ] **Step 3: Update AnthropicService**

Replace `backend/app/services/anthropic_service.py` with:

```python
import anthropic


class AnthropicService:
    """LLM generation via Anthropic API."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-6"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_anthropic_service.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/anthropic_service.py tests/unit/test_anthropic_service.py
git commit -m "feat: add system param to AnthropicService.generate()"
```

---

## Task 6: Add system param to GoogleService (TDD)

**Files:**
- Create: `tests/unit/test_google_service.py`
- Modify: `backend/app/services/google_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_google_service.py`:

```python
import sys
import pytest
from pathlib import Path
from unittest.mock import Mock, patch

backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from app.services.google_service import GoogleService


@pytest.fixture
def service():
    with patch("app.services.google_service.genai") as mock_lib:
        mock_client = Mock()
        mock_lib.Client.return_value = mock_client
        svc = GoogleService(api_key="test-key")
        svc._mock_client = mock_client
        yield svc


def test_generate_passes_system_instruction(service):
    mock_response = Mock()
    mock_response.text = "The answer"
    service._mock_client.models.generate_content.return_value = mock_response

    result = service.generate(prompt="What is AI?", system="You are an expert.")

    assert result == "The answer"
    call_kwargs = service._mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].system_instruction == "You are an expert."


def test_generate_system_defaults_to_empty_string(service):
    mock_response = Mock()
    mock_response.text = "ok"
    service._mock_client.models.generate_content.return_value = mock_response

    service.generate(prompt="test")  # no system arg

    call_kwargs = service._mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["config"].system_instruction == ""


def test_generate_returns_text(service):
    mock_response = Mock()
    mock_response.text = "hello"
    service._mock_client.models.generate_content.return_value = mock_response

    assert service.generate(prompt="hi") == "hello"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_google_service.py -v
```

Expected: `test_generate_passes_system_instruction` FAILS.

- [ ] **Step 3: Update GoogleService**

Replace `backend/app/services/google_service.py` with:

```python
from google import genai
from google.genai import types


class GoogleService:
    """LLM generation via Google Gemini API."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(
        self,
        prompt: str,
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        return response.text
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/unit/test_google_service.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/google_service.py tests/unit/test_google_service.py
git commit -m "feat: add system param to GoogleService.generate()"
```

---

## Task 7: Refactor summarize.py to use llm_service (prerequisite)

This is a prerequisite for Task 9. `summarize.py` currently calls `ollama.generate()` directly instead of going through the provider-agnostic `llm_service` pattern used by `rag.py` and `compare.py`.

**Files:**
- Modify: `backend/app/api/summarize.py`

- [ ] **Step 1: Update summarize.py get_services() and handler**

In `backend/app/api/summarize.py`, make these changes:

1. Add import at the top:
```python
from app.api.rag import _get_llm_service, _get_llm_info
```

2. Replace `get_services()`:
```python
def get_services():
    """Dependency to get services"""
    config = load_config("config.yaml")

    qdrant = QdrantService(url=settings.qdrant_url)
    collection_service = CollectionService(qdrant=qdrant)
    metadata_service = MetadataService(data_dir=settings.data_dir)
    llm_service = _get_llm_service(config)
    llm_info = _get_llm_info(config)

    return collection_service, qdrant, metadata_service, llm_service, llm_info
```

3. Update the handler: replace the old 4-tuple unpack AND the LLM call. The handler becomes a 5-tuple unpack — **replace the old `collection_service, qdrant, ollama, metadata_service = services` line**:
```python
@router.post("/collections/{collection_id}/summarize", response_model=SummarizeResponse)
def summarize_papers(
    collection_id: str,
    request: SummarizeRequest,
    services: tuple = Depends(get_services)
):
    # Replace old 4-tuple unpack with this 5-tuple unpack:
    collection_service, qdrant, metadata_service, llm_service, llm_info = services
    ...
    # Replace: summary = ollama.generate(prompt=prompt, temperature=0.3, max_tokens=request.max_tokens)
    # With:
    summary = llm_service.generate(prompt=prompt, temperature=0.3, max_tokens=request.max_tokens)
    ...
```

4. Remove the `OllamaService` import from summarize.py (it is no longer used):
```python
# Remove this line:
from app.services.ollama_service import OllamaService
```

- [ ] **Step 2: Run existing summarize tests to confirm no regression**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_summarize_api.py -v
```

Expected: all existing tests PASS (or same results as before this change).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/summarize.py
git commit -m "refactor: summarize.py uses llm_service instead of direct ollama.generate()"
```

---

## Task 8: Wire PromptService into RAG handler (TDD)

**Files:**
- Modify: `backend/app/models/rag.py` (add `prompt_name` to `RAGRequest`)
- Modify: `backend/app/api/rag.py`

- [ ] **Step 1: Write a failing test**

In `tests/integration/test_query_api.py`, add this test (or create the file if it doesn't cover RAG prompt_name yet):

```python
def test_rag_accepts_prompt_name_field(client, test_collection):
    """prompt_name field is accepted and uses the named prompt."""
    response = client.post(
        f"/collections/{test_collection}/rag",
        json={
            "query_text": "What is attention?",
            "prompt_name": "default",
        }
    )
    # Should succeed — prompt_name is a valid field
    assert response.status_code == 200
```

Run first to check current state:
```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_query_api.py::test_rag_accepts_prompt_name_field -v
```

Expected: `422 Unprocessable Entity` or test not found — `prompt_name` not yet a valid field.

- [ ] **Step 2: Add prompt_name to RAGRequest**

In `backend/app/models/rag.py`, add to `RAGRequest`:

```python
class RAGRequest(BaseModel):
    query_text: str = Field(..., description="User question")
    paper_ids: list[str] = Field(default_factory=list, description="Paper IDs to search (empty = all)")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum results to return")
    include_citations: bool = Field(default=False, description="Include formatted citations")
    max_tokens: int = Field(default=500, ge=50, le=4000, description="Desired response length in tokens")
    chat_history: list[dict] = Field(default_factory=list, description="Previous messages")
    use_hybrid: bool = Field(default=False, description="Use hybrid search (dense + sparse)")
    prompt_name: str = Field(default="default", description="Prompt variant to use")  # ← add this
```

- [ ] **Step 3: Update rag.py to use PromptService**

In `backend/app/api/rag.py`:

1. Add imports at the top:
```python
from app.services.prompt_service import PromptService, get_prompt_service
```

2. Update `rag_query` handler signature to inject `prompt_service`:
```python
@router.post("/collections/{collection_id}/rag")
def rag_query(
    collection_id: str,
    rag_request: RAGRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),   # ← add
):
```

3. Replace the inline prompt block (the `CITATION_KEY_CONSTRAINTS` and `prompt = (...)` block at lines ~208–232) with:

```python
        try:
            rendered = prompt_service.render(
                "rag",
                rag_request.prompt_name,
                context=context,
                question=rag_request.query_text,
                word_target=rag_request.max_tokens,
                keys_list=keys_list,
                cannot_answer_phrase=CANNOT_ANSWER_PHRASE,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        answer = llm_service.generate(
            prompt=rendered.user,
            system=rendered.system,
            temperature=0.3,
            max_tokens=rag_request.max_tokens,
        )
```

4. Remove the `CITATION_KEY_CONSTRAINTS` variable and the old `prompt = (...)` string (the ~20 line block). Keep the `CANNOT_ANSWER_PHRASE` constant — it is still used both in the template variable and in the cannot-answer detection logic below.

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_query_api.py -v
```

Expected: all RAG tests PASS including the new `test_rag_accepts_prompt_name_field`.

**Important:** The integration tests for RAG mock `OllamaService` and `QdrantService` but not `PromptService`. Since `get_prompt_service` returns the module-level singleton pointing to `/app/prompts` (which doesn't exist in test env), `PromptService` will log a startup warning but not crash. However, when `render()` is actually called, it will raise `FileNotFoundError` — so you need to also mock `get_prompt_service` in the RAG integration tests.

Open `tests/integration/test_query_api.py`. Ensure it already imports `app` from `app.main` (check the existing imports at the top of the file — if it uses `TestClient(app)`, it already has this). Then add the following fixture:

```python
from unittest.mock import Mock
from app.services.prompt_service import get_prompt_service, RenderedPrompt

@pytest.fixture(autouse=True)
def mock_prompt_service():
    mock = Mock()
    mock.render.return_value = RenderedPrompt(
        system="You are a research assistant.",
        user="Answer the question using the context.",
    )
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield
    app.dependency_overrides.pop(get_prompt_service, None)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/rag.py backend/app/api/rag.py tests/integration/test_query_api.py
git commit -m "feat: wire PromptService into RAG handler"
```

---

## Task 9: Wire PromptService into summarize handler (TDD)

**Files:**
- Modify: `backend/app/api/summarize.py`

- [ ] **Step 1: Write a failing test**

In `tests/integration/test_summarize_api.py`, add:

```python
def test_summarize_accepts_prompt_name_field(client, test_collection):
    response = client.post(
        f"/collections/{test_collection}/summarize",
        json={
            "paper_ids": ["paper-123"],
            "prompt_name": "default",
        }
    )
    assert response.status_code == 200
```

Run first:
```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_summarize_api.py::test_summarize_accepts_prompt_name_field -v
```

Expected: `422` — `prompt_name` not a valid field yet.

- [ ] **Step 2: Add prompt_name to SummarizeRequest and wire PromptService**

In `backend/app/api/summarize.py`:

1. Add `prompt_name` to the local `SummarizeRequest` model:
```python
class SummarizeRequest(BaseModel):
    paper_ids: list[str] = Field(..., min_length=1, description="Paper IDs to summarize")
    max_tokens: Optional[int] = Field(default=None, description="Max tokens for generated text")
    prompt_name: str = Field(default="default", description="Prompt variant to use")  # ← add
```

2. Add import:
```python
from app.services.prompt_service import PromptService, get_prompt_service
```

3. Update handler signature:
```python
@router.post("/collections/{collection_id}/summarize", response_model=SummarizeResponse)
def summarize_papers(
    collection_id: str,
    request: SummarizeRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),   # ← add
):
    collection_service, qdrant, metadata_service, llm_service, llm_info = services
```

4. Replace the inline `prompt = f"""..."""` block (both the single-paper and multi-paper branches, lines ~101–123) with:

```python
    paper_count = len(request.paper_ids)
    try:
        rendered = prompt_service.render(
            "summarize",
            request.prompt_name,
            context=context,
            paper_count=paper_count,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    summary = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
        max_tokens=request.max_tokens,
    )
```

5. Add `HTTPException` to imports if not already present:
```python
from fastapi import APIRouter, HTTPException, Depends
```

- [ ] **Step 3: Add mock_prompt_service fixture to summarize tests**

In `tests/integration/test_summarize_api.py`, add the same `mock_prompt_service` autouse fixture used in the RAG tests (same pattern — override `get_prompt_service` dependency):

```python
from app.services.prompt_service import get_prompt_service, RenderedPrompt

@pytest.fixture(autouse=True)
def mock_prompt_service():
    mock = Mock()
    mock.render.return_value = RenderedPrompt(
        system="You are a research assistant.",
        user="Summarize the following papers.",
    )
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield
    app.dependency_overrides.pop(get_prompt_service, None)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_summarize_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/summarize.py tests/integration/test_summarize_api.py
git commit -m "feat: wire PromptService into summarize handler"
```

---

## Task 10: Wire PromptService into compare handler (TDD)

**Files:**
- Modify: `backend/app/api/compare.py`

- [ ] **Step 1: Write a failing test**

In `tests/integration/test_compare_api.py`, add:

```python
def test_compare_accepts_prompt_name_field(client, test_collection):
    response = client.post(
        f"/collections/{test_collection}/compare",
        json={
            "paper_ids": ["paper-123", "paper-456"],
            "prompt_name": "default",
        }
    )
    assert response.status_code == 200
```

Run first:
```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_compare_api.py::test_compare_accepts_prompt_name_field -v
```

Expected: `422` — `prompt_name` not a valid field yet.

- [ ] **Step 2: Add prompt_name to CompareRequest and wire PromptService**

In `backend/app/api/compare.py`:

1. Add `prompt_name` to `CompareRequest`:
```python
class CompareRequest(BaseModel):
    paper_ids: list[str] = Field(..., min_length=2, description="Paper IDs to compare (min 2)")
    aspect: str = Field(default="all", description="Aspect to compare: methodology, findings, or all")
    max_tokens: Optional[int] = Field(default=None, description="Max tokens for generated text")
    prompt_name: str = Field(default="default", description="Prompt variant to use")  # ← add
```

2. Add import:
```python
from app.services.prompt_service import PromptService, get_prompt_service
```

3. Update handler signature:
```python
@router.post("/collections/{collection_id}/compare", response_model=CompareResponse)
def compare_papers(
    collection_id: str,
    request: CompareRequest,
    services: tuple = Depends(get_services),
    prompt_service: PromptService = Depends(get_prompt_service),   # ← add
):
    collection_service, qdrant, llm_service, llm_info, metadata_service = services
```

4. Replace the inline `prompt = f"""..."""` block (lines ~120–130) with:

```python
    aspect_prompts = {
        "methodology": "Focus specifically on comparing the research methodologies, experimental designs, and approaches used.",
        "findings": "Focus specifically on comparing the key findings, results, and conclusions.",
        "all": "Compare all aspects including methodologies, findings, and implications.",
    }
    aspect_instruction = aspect_prompts.get(request.aspect, aspect_prompts["all"])

    try:
        rendered = prompt_service.render(
            "compare",
            request.prompt_name,
            combined_content=combined_content,
            paper_count=len(request.paper_ids),
            aspect_instruction=aspect_instruction,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    comparison = llm_service.generate(
        prompt=rendered.user,
        system=rendered.system,
        temperature=0.3,
        max_tokens=request.max_tokens,
    )
```

Note: The `aspect_prompts` dict was previously inline in the handler — keep it there, as it feeds the `aspect_instruction` template variable.

- [ ] **Step 3: Add mock_prompt_service fixture to compare tests**

In `tests/integration/test_compare_api.py`, add the same autouse fixture:

```python
from app.services.prompt_service import get_prompt_service, RenderedPrompt

@pytest.fixture(autouse=True)
def mock_prompt_service():
    mock = Mock()
    mock.render.return_value = RenderedPrompt(
        system="You are a research analyst.",
        user="Compare the following papers.",
    )
    app.dependency_overrides[get_prompt_service] = lambda: mock
    yield
    app.dependency_overrides.pop(get_prompt_service, None)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/integration/test_compare_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/ -v
```

Expected: all tests PASS. No regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/compare.py tests/integration/test_compare_api.py
git commit -m "feat: wire PromptService into compare handler"
```

---

## Task 11: Update Dockerfile and docker-compose.yml

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`

No tests needed — deployment configuration.

- [ ] **Step 1: Update Dockerfile to bake in prompts**

In `backend/Dockerfile`, add after `COPY backend/app/ ./app/`:

```dockerfile
# Copy application code
COPY backend/app/ ./app/
COPY backend/prompts/ ./prompts/   # ← add: bake default prompts into image
```

The prompts land at `/app/prompts/` in the container, matching `settings.prompts_dir` default.

- [ ] **Step 2: Add volume mount to docker-compose.yml**

In `docker-compose.yml`, under the `backend` service `volumes`:

```yaml
    volumes:
      - ./data:/data
      - ./config.yaml:/app/config.yaml
      - ./backend/prompts:/app/prompts    # ← add: allows live editing in dev
```

- [ ] **Step 3: Verify Dockerfile builds**

```bash
cd /Users/jose/Repos/PRAG-v2
docker build -f backend/Dockerfile -t prag-v2-test . --no-cache 2>&1 | tail -20
```

Expected: build succeeds, `prompts/` directory copied into image.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile docker-compose.yml
git commit -m "chore: bake prompts into Docker image, add dev volume mount"
```

---

## Final Verification

- [ ] **Run complete test suite**

```bash
cd /Users/jose/Repos/PRAG-v2
pytest tests/ -v --tb=short
```

Expected: all tests PASS, no regressions.

- [ ] **Smoke test PromptService against real YAML files**

```bash
cd /Users/jose/Repos/PRAG-v2
python -c "
import sys
sys.path.insert(0, 'backend')
from app.services.prompt_service import PromptService

svc = PromptService('backend/prompts')
for task in ['rag', 'summarize', 'compare']:
    names = svc.list_prompts(task)
    print(f'{task}: {names}')
    raw = svc.get_raw(task, 'default')
    print(f'  system keys present: {\"system\" in raw}')
    print(f'  user keys present: {\"user\" in raw}')
print('All prompts OK')
"
```

Expected: prints each task with `["default"]` and `system/user keys present: True`.
