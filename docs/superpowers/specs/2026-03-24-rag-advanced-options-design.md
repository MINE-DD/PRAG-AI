# RAG Advanced Options Panel Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a collapsible "Advanced options" panel to the RAG tab that consolidates the top-K and response-length sliders and exposes a prompt selector with a read-only preview.

**Scope:** RAG tab only. Compare tab will follow the same pattern in a separate cycle once this is reviewed and approved.

---

## Architecture

### New file: `frontend-web/js/prompt-selector.js`

A focused, reusable Vue 3 component responsible for:
- Fetching the list of available prompts for a given task type (`GET /prompts/{taskType}`)
- Fetching the raw YAML content of the selected prompt (`GET /prompts/{taskType}/{name}`)
- Displaying a dropdown to select a prompt and two read-only textareas for the system and user templates

**Required Vue imports:** `defineComponent`, `ref`, `onMounted`
**Required non-Vue imports:** `import { api } from './api.js'`

**Props:**
- `taskType` — string, e.g. `"rag"` or `"compare"`. Treated as **immutable** — the component reads it once at mount and never watches it. Each tab (RAG, Compare) gets its own instance; `taskType` never changes on a live instance.
- `modelValue` — string, currently selected prompt name (supports v-model)

**Emits:**
- `update:modelValue` — when the resolved or user-selected prompt name changes

**Internal state:**
- `prompts` — list of prompt names from the API; `null` if fetch failed; `[]` if empty
- `internalName` — `ref("default")`; overwritten by `onMounted` with the resolved name from the API
- `preview` — `{ system: string, user: string }`; initial value `{ system: "", user: "" }` (empty strings while the first fetch is in progress)

**Behaviour — `onMounted`:**
1. Fetch prompt list (`GET /prompts/{taskType}`)
   - On network/HTTP failure: set `prompts = null`; jump to step 3 using `internalName.value` (`"default"`)
   - On success with empty list `[]`: set `prompts = []`; **stop here** — do not emit, do not fetch preview; textareas remain `""`
   - On success with items: resolve name as `"default"` if in list, else first item
2. Set `internalName.value = resolved`; emit `update:modelValue`
3. Fetch preview for `internalName.value` (`GET /prompts/{taskType}/{name}`)
   - On success: set `preview`
   - On failure: set `preview = { system: "Could not load preview", user: "Could not load preview" }`

**Behaviour — user changes dropdown:**
```javascript
async function onSelect(name) {
  internalName.value = name
  emit('update:modelValue', name)
  await fetchPreview(name)
}
```
Template binding: `@change="onSelect($event.target.value)"`

No `watch` is used. `onSelect` is called directly from `@change`, avoiding prop-watching anti-patterns and double-fetches.

**keep-alive note:** `RagTab` is wrapped in `<keep-alive>` in `app.js`, so it is never destroyed after first mount. This means `PromptSelector` also survives tab switches — the prompt list and preview stay in memory with no re-fetch. The `v-show` on the Advanced panel body is what prevents `PromptSelector` from remounting on every open/close within the same tab session. The two mechanisms are complementary: `keep-alive` handles cross-tab persistence; `v-show` handles in-tab panel toggle.

**One-way sync note:** `internalName` is the source of truth inside `PromptSelector`. External writes to `modelValue` after mount (e.g. a future "reset" button) are **not** supported and will not update `internalName` or the preview. This is intentional and out of scope for this feature.

**Backend contract assumption:** `"default"` is always a valid prompt name — the backend enforces this via `PromptService._validate_defaults()`. Sending `prompt_name: "default"` before the panel is opened is therefore always safe.

**Display:**
- Label "Prompt" + `<select>` with `@change="onSelect($event.target.value)"`
  - Disabled with single option `"Unavailable"` if `prompts === null`
  - Disabled with single option `"No prompts available"` if `prompts.length === 0`
  - Otherwise lists all prompt names; selected option bound to `internalName`
- Two labeled `<textarea readonly>` elements: "System prompt" and "User prompt"
  - Initial value: `""` (empty while first fetch is in progress — no spinner needed)
  - Error value: `"Could not load preview"`
  - `background: var(--bg)` inline style + `readonly` HTML attribute — visually muted, text selectable/copyable but not editable

**Registration:** `PromptSelector` is registered locally per-tab via `components: { PromptSelector }`. It is **not** registered globally in `app.js`. Each future tab (e.g. Compare) must add its own local `components` registration and ES import.

**Import pattern:** imported via ES `import` at the top of `rag-tab.js`:
```javascript
import { PromptSelector } from './prompt-selector.js'
```
Not added as a `<script>` tag in `index.html`.

---

### Modified file: `frontend-web/js/rag-tab.js`

**State changes:**
- Add `showAdvanced` ref (default `false`)
- Add `selectedPrompt` ref (default `"default"`)
- Keep existing `topK` and `maxTokens` refs unchanged

**Template changes:**
- Remove `topK` and `maxTokens` sliders from their current position in the main form
- Add a collapsible "Advanced options" panel below the paper filter panel and above the Run button
- Collapsible toggle: `<button @click="showAdvanced = !showAdvanced">` displaying `showAdvanced ? '▲' : '▼'` — matches the paper filter pattern exactly
- Panel body uses **`v-show="showAdvanced"`** (not `v-if`) so that `PromptSelector` mounts once and stays alive — avoids repeated API fetches on every open/close
- Inside the panel, top to bottom:
  1. Top-K slider (moved from main form)
  2. Response length slider (moved from main form)
  3. `<hr>` divider
  4. `<prompt-selector>` component with `:task-type="'rag'"` and `v-model="selectedPrompt"`

**API call change:**
- Add `prompt_name: selectedPrompt.value` to the POST body of the RAG query

---

## Data Flow

```
[Component mounts — panel collapsed, PromptSelector not yet mounted]
selectedPrompt.value = "default"  ← safe per backend contract

[User opens Advanced options panel for the first time]
  → v-show makes panel visible; PromptSelector mounts
  → GET /prompts/rag                    (list of names)
  → resolve: "default" if in list, else first item
  → internalName.value = resolved
  → emit update:modelValue → selectedPrompt.value updated in rag-tab
  → GET /prompts/rag/{resolved}
  → system + user textareas populated

[User switches tabs and returns]
  → keep-alive: PromptSelector stays mounted, no re-fetch

[User selects different prompt from dropdown]
  → onSelect(name) called via @change="onSelect($event.target.value)"
  → internalName.value = name
  → emit update:modelValue → selectedPrompt.value updated in rag-tab
  → GET /prompts/rag/{name}
  → textareas updated

[User runs RAG query — panel open or closed]
  → POST /collections/{id}/rag { ..., prompt_name: selectedPrompt.value }
```

---

## UI Layout (RAG tab, top to bottom)

```
[ Query textarea                              ]
[ Paper filter ▼ (collapsible, unchanged)     ]
[ ⚙ Advanced options ▼ (collapsed by default) ]
  [ Top-K slider          value: 10           ]
  [ Response length slider value: 500         ]
  [ ──────────────────────────────────────── ]
  [ Prompt  [default          ▼]              ]
  [ System prompt                             ]
  [ ┌──────────────────────────────────────┐ ]
  [ │ You are a research assistant...      │ ]
  [ └──────────────────────────────────────┘ ]
  [ User prompt                              ]
  [ ┌──────────────────────────────────────┐ ]
  [ │ Context: {context}                   │ ]
  [ │ Question: {question}                 │ ]
  [ └──────────────────────────────────────┘ ]
[ Run button                                  ]
```

---

## Error Handling

| Situation | Behaviour |
|---|---|
| `/prompts/rag` fetch fails | `prompts = null`. Dropdown shows `"Unavailable"`, disabled. `selectedPrompt.value` retains `"default"` (safe per backend contract). |
| `/prompts/rag` returns `[]` | `prompts = []`. Dropdown shows `"No prompts available"`, disabled. Preview textareas remain `""`. |
| `/prompts/rag/{name}` fetch fails | `preview` set to error strings. Dropdown selection still sent in query. |
| Backend returns unknown `prompt_name` | Backend raises 422; displayed via existing error alert in RAG tab. |

---

## Implementation Notes

- Collapsible toggle: `showAdvanced ? '▲' : '▼'` ternary, matching paper filter pattern in `rag-tab.js`
- Advanced panel body uses `v-show`, **not** `v-if`, so PromptSelector mounts once
- `prompt-selector.js` imported via ES `import` in `rag-tab.js`, not via `index.html`
- Register `PromptSelector` locally: `components: { PromptSelector }` in `rag-tab.js`
- Do **not** commit during implementation — present changes to user for review before any commit
- No new CSS classes needed; use existing `.form-group`, `select`, `textarea`, `--bg` variable
