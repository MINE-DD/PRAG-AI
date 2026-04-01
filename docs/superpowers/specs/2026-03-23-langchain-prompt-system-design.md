# Prompt System Design — LangChain-Core Integration

**Date:** 2026-03-23
**Status:** Approved (v2 — post spec-review fixes)
**Scope:** Backend only

---

## 1. Problem

All LLM prompts in the app are hardcoded inline inside API handlers (`rag.py`, `summarize.py`, `compare.py`). There is no separation between system prompts (instructions that shape LLM behaviour) and user prompts (the actual content/query for each call). This makes prompts hard to iterate on, impossible to swap without code changes, and does not scale as new task types are added.

---

## 2. Goals

- Separate **system prompts** (LLM behaviour/persona) from **user prompts** (task-specific content)
- Store prompts in **YAML files** committed to the repo, one file per prompt variant
- Allow UI users to **select** a named prompt per task; they cannot create or edit prompts
- Adding a new prompt = **one new YAML file**, no code changes
- Adding a new task type = **one new subdirectory** with a `default.yaml`
- Integrate `langchain-core` as the prompt rendering layer to enable future agent/chain work
- Preserve all existing LLM functionality (Ollama, Anthropic, Google)

---

## 3. Non-Goals

- No user-editable prompts via the UI (read-only selection only)
- No prompt versioning or history
- No per-collection prompt assignments (prompts are global)
- No replacement of existing LLM service classes with LangChain provider wrappers

---

## 4. Dependency

```toml
# pyproject.toml — add to [project.dependencies] (NOT to [project.optional-dependencies].api)
# Prompt rendering applies to all providers including the default local/Ollama path.
langchain-core>=1.2,<2.0
```

`langchain-core` 1.2.20 is the current stable release (verified March 2026 via PyPI).

Used **only** inside `PromptService` for template rendering. No other part of the app imports from `langchain-core`. Easy to eject: replacing it with ~15 lines of Python format-string logic is a 30-minute job.

---

## 5. Prerequisite: Align `summarize.py` with other handlers

`summarize.py` currently calls `ollama.generate()` directly. Before integrating the prompt system, it must be updated to use `_get_llm_service(config)` (the same pattern used by `rag.py` and `compare.py`). This gives `summarize.py` a provider-agnostic `llm_service` that accepts a `system` parameter — required for the new architecture. This is a standalone refactor step that must happen before touching the prompt system in that handler.

---

## 6. File Layout

```
backend/
  prompts/                          ← new: all prompt definitions live here
    rag/
      default.yaml
    summarize/
      default.yaml
    compare/
      default.yaml
  app/
    services/
      prompt_service.py             ← new
    api/
      prompts.py                    ← new (read-only endpoints)
    services/
      ollama_service.py             ← unchanged (already has system param)
      anthropic_service.py          ← add system param
      google_service.py             ← add system param
    api/
      rag.py                        ← updated: load prompt, pass system+user
      summarize.py                  ← updated: switch to llm_service + load prompt
      compare.py                    ← updated: load prompt, pass system+user
    core/
      config.py                     ← add prompts_dir to Settings
    main.py                         ← register prompts router
docker-compose.yml                  ← add prompts volume mount
```

---

## 7. Prompt YAML Format

Each file defines one named prompt variant for one task type. The `name` field is **not included** — the name is derived from the filename stem. This avoids a class of bugs where a copied file has a mismatched `name` field.

```yaml
# backend/prompts/rag/default.yaml
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

**Rules:**
- Variables use single curly braces: `{variable_name}` (LangChain format-string syntax, not Jinja2)
- Filename stem is the prompt name (e.g. `default.yaml` → name `"default"`)
- Every task directory must contain a `default.yaml`
- `system` and `user` are both required fields
- `{word_target}` passes the token budget from the request; the template says "tokens" to match what is actually passed

---

## 8. Template Variables per Task

| Task | Variables |
|------|-----------|
| `rag` | `context`, `question`, `word_target`, `keys_list`, `cannot_answer_phrase` |
| `summarize` | `context`, `paper_count` |
| `compare` | `combined_content`, `paper_count`, `aspect_instruction` |

New task types define their own variables freely — no constraints imposed by `PromptService`.

**Note on `summarize`:** The current handler branches on `len(paper_ids) == 1` to produce slightly different phrasing. The default YAML uses a single generic template with `{paper_count}` so the template author can write "Summarize these {paper_count} paper(s)..." without needing two files. Developers who want distinct single vs. multi behaviour can add `single_paper.yaml` and `multi_paper.yaml` and let the frontend select them.

---

## 9. PromptService

```python
# backend/app/services/prompt_service.py
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
        """Return available prompt names for a task type."""
        task_dir = self._dir / task_type
        if not task_dir.exists():
            raise FileNotFoundError(f"Unknown task type: '{task_type}'")
        return sorted(f.stem for f in task_dir.glob("*.yaml"))

    def get_raw(self, task_type: str, name: str) -> dict:
        """Return raw YAML content (for display in UI). Name is derived from filename."""
        path = self._dir / task_type / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt '{name}' not found for task '{task_type}'")
        data = yaml.safe_load(path.read_text())
        data["name"] = name  # inject derived name for API responses
        return data

    def render(self, task_type: str, name: str, **variables) -> RenderedPrompt:
        """Render system and user prompts with variables substituted."""
        raw = self.get_raw(task_type, name)
        # Guard YAML structure separately from missing render variables
        if "system" not in raw or "user" not in raw:
            raise ValueError(f"Prompt '{name}' for task '{task_type}' must have 'system' and 'user' keys")
        try:
            template = ChatPromptTemplate.from_messages([
                ("system", raw["system"]),
                ("human", raw["user"]),
            ])
            messages = template.invoke(variables).to_messages()
        except KeyError as e:
            raise ValueError(f"Missing template variable {e} for prompt '{name}' in task '{task_type}'") from e
        return RenderedPrompt(
            system=messages[0].content,
            user=messages[1].content,
        )
```

**Dependency injection** — `PromptService` is instantiated once at module level in `prompt_service.py` using the settings singleton, and exposed via a FastAPI dependency:

```python
# bottom of prompt_service.py
from app.core.config import settings as _settings
_prompt_service = PromptService(_settings.prompts_dir)

def get_prompt_service() -> PromptService:
    return _prompt_service
```

Handlers import `get_prompt_service` and use `Depends(get_prompt_service)` — same pattern as other services.

---

## 10. API Endpoints

New read-only router in `app/api/prompts.py`, registered in `main.py` with tag `"prompts"`. No `/api` prefix — consistent with all existing routes (e.g. `/collections/{id}/rag`).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/prompts/{task_type}` | List available prompt names for a task |
| `GET` | `/prompts/{task_type}/{name}` | Get raw template content (system + user + name) |

**Example responses:**

```json
// GET /prompts/rag
["default", "concise"]

// GET /prompts/rag/default
{
  "name": "default",
  "system": "You are a research assistant...",
  "user": "Context:\n\n{context}\n\n..."
}
```

**Errors:**
- `404` if task type directory does not exist (both list and get)
- `404` if prompt name does not exist (get only)

`FileNotFoundError` from `PromptService` is caught inside the handler and re-raised as `HTTPException(status_code=404)`.

---

## 11. LLM Service Changes

`AnthropicService` and `GoogleService` gain a `system` parameter on `generate()`. `OllamaService` already supports it — no change needed.

```python
# anthropic_service.py — updated signature
def generate(self, prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 500) -> str:
    message = self.client.messages.create(   # mock target: self.client.messages.create
        model=self.model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,                        # ← new; top-level param, not in messages array
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text

# google_service.py — updated signature
def generate(self, prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 500) -> str:
    response = self.client.models.generate_content(  # mock target: self.client.models.generate_content
        model=self.model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,         # ← new; correct field name for Google genai SDK
            temperature=temperature,
            max_output_tokens=max_tokens,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text
```

---

## 12. Handler Changes

Each handler gains:
1. `prompt_name: str = Field(default="default", ...)` on its request model
2. `prompt_service: PromptService = Depends(get_prompt_service)` in its signature
3. A `prompt_service.render(task_type, prompt_name, **vars)` call before the LLM call
4. `rendered.system` and `rendered.user` passed separately to `llm_service.generate()`
5. `ValueError` from `render()` (missing template variable) caught and re-raised as `HTTPException(status_code=422)`

**Example — RAG handler diff:**

```python
# RAGRequest gains:
prompt_name: str = Field(default="default", description="Prompt variant to use")

# In rag_query(), before the LLM call:
try:
    rendered = prompt_service.render(
        "rag", rag_request.prompt_name,
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

The existing `CITATION_KEY_CONSTRAINTS` block and inline prompt strings in `rag.py` are removed — their content moves into `prompts/rag/default.yaml`.

---

## 13. Configuration Changes

**`config.py` — new field:**

```python
prompts_dir: str = "/app/prompts"  # Docker default; override via PROMPTS_DIR env var for local dev
```

**`Dockerfile` — bake prompts into the image** (so the container works in CI and staging without a volume mount):

```dockerfile
COPY backend/prompts /app/prompts
```

**`docker-compose.yml` — also add a volume mount** so local edits to YAML files are picked up without rebuilding:

```yaml
volumes:
  - ./data:/data
  - ./config.yaml:/app/config.yaml
  - ./backend/prompts:/app/prompts   # ← new: overrides baked-in prompts at runtime
```

Both together: the image ships with defaults baked in; the volume mount allows live editing in development.

---

## 14. Error Handling Summary

| Scenario | Where caught | Response |
|----------|-------------|----------|
| Unknown task type (list or render) | Handler catches `FileNotFoundError` | `404` with detail message |
| Unknown prompt name (get or render) | Handler catches `FileNotFoundError` | `404` with detail message |
| Missing template variable | Handler catches `ValueError` from `render()` | `422` with variable name |
| Prompts dir missing at startup | `PromptService.__init__` | Warning log, no crash |
| Missing `default.yaml` at startup | `PromptService._validate_defaults` | Warning log, no crash |

---

## 15. Developer Workflow

### Add a new prompt variant
1. Create `backend/prompts/{task_type}/{name}.yaml`
2. Write `system:` and `user:` using `{variable}` placeholders
3. The prompt is immediately available via `GET /prompts/{task_type}` (no restart needed since the file is volume-mounted)
4. **Note:** Content errors in YAML files (missing keys, bad syntax, wrong variable names) are not caught at startup — they surface as `ValueError` (422) at the first render request. Validate your YAML locally before deploying.

### Add a new task type
1. Create `backend/prompts/{new_task}/default.yaml`
2. Define which variables the handler will pass to `render()`
3. Add `prompt_name` field to the new task's request model
4. Call `prompt_service.render(new_task, request.prompt_name, ...)` in the handler
5. No changes to `PromptService`

---

## 16. Future Extensibility

- **Agents:** `RenderedPrompt.system` and `.user` map directly to LangChain `SystemMessage`/`HumanMessage` — wrapping in an agent chain requires no changes to `PromptService`.
- **Chat history:** Orthogonal to this design. `OllamaService` already supports it. Anthropic and Google services can add `chat_history` as a separate concern.
- **Model parameter metadata:** A future `ModelInfoService` queries each provider's own API (Ollama `/api/show`, Anthropic models endpoint, Google models endpoint). Independent of the prompt system.

---

## 17. Testing

| Test | Mock target | What it covers |
|------|-------------|---------------|
| `test_prompt_service_list` | filesystem (tmp_path) | Returns correct names from directory |
| `test_prompt_service_render` | filesystem (tmp_path) | Variables substituted in system and user |
| `test_prompt_service_missing_prompt` | filesystem (tmp_path) | `FileNotFoundError` on unknown prompt name |
| `test_prompt_service_missing_variable` | filesystem (tmp_path) | `ValueError` when variable absent |
| `test_prompt_api_list` | `get_prompt_service` override | `GET /prompts/rag` returns `["default"]` |
| `test_prompt_api_get` | `get_prompt_service` override | `GET /prompts/rag/default` returns correct fields |
| `test_prompt_api_404_task` | `get_prompt_service` override | `GET /prompts/unknown` returns 404 |
| `test_prompt_api_404_name` | `get_prompt_service` override | `GET /prompts/rag/nonexistent` returns 404 |
| `test_rag_with_prompt_name` | `get_prompt_service` override | RAG endpoint routes `prompt_name` correctly |
| `test_anthropic_system_param` | `self.client.messages.create` | System string passed as top-level param |
| `test_google_system_param` | `self.client.models.generate_content` | System string passed as `system_instruction` |
