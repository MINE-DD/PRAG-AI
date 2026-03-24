# RAG Advanced Options Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a collapsible "Advanced options" panel to the RAG tab that moves the top-K and max-tokens sliders out of the main form and adds a prompt selector with read-only system/user preview.

**Architecture:** Create a new reusable `PromptSelector` Vue 3 component in its own file; modify `rag-tab.js` to import it, add state, restructure the template, and include `prompt_name` in the POST body. No backend changes needed — all API endpoints already exist.

**Tech Stack:** Vue 3 (CDN via import map), vanilla JS (no build step), existing `api.js` fetch wrapper.

**Important:** Do NOT commit any changes — present them to the user for review first.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `frontend-web/js/prompt-selector.js` | Create | Reusable component: fetches prompt list + preview, shows dropdown + readonly textareas |
| `frontend-web/js/rag-tab.js` | Modify | Import PromptSelector, add `showAdvanced`/`selectedPrompt` state, restructure template, update POST body |

---

### Task 1: Create `frontend-web/js/prompt-selector.js`

**Files:**
- Create: `frontend-web/js/prompt-selector.js`

- [ ] **Step 1: Create the file with the complete component**

Create `frontend-web/js/prompt-selector.js` with the following content — follow the exact same pattern as `file-picker-panel.js` (named export, `import { ... } from 'vue'`, `import { api } from './api.js'`):

```javascript
import { defineComponent, ref, onMounted } from 'vue'
import { api } from './api.js'

const PromptSelector = defineComponent({
  name: 'PromptSelector',
  props: {
    taskType: { type: String, required: true },
    modelValue: { type: String, default: 'default' },
  },
  emits: ['update:modelValue'],

  setup(props, { emit }) {
    // null = fetch failed, [] = empty, [...names] = loaded
    const prompts = ref([])
    const internalName = ref('default')
    const preview = ref({ system: '', user: '' })

    async function fetchPreview(name) {
      try {
        const raw = await api.get(`/prompts/${props.taskType}/${name}`)
        preview.value = { system: raw.system, user: raw.user }
      } catch {
        preview.value = { system: 'Could not load preview', user: 'Could not load preview' }
      }
    }

    async function onSelect(name) {
      internalName.value = name
      emit('update:modelValue', name)
      await fetchPreview(name)
    }

    onMounted(async () => {
      try {
        const list = await api.get(`/prompts/${props.taskType}`)
        prompts.value = list
        if (list.length === 0) return
        const resolved = list.includes('default') ? 'default' : list[0]
        internalName.value = resolved
        emit('update:modelValue', resolved)
        await fetchPreview(resolved)
      } catch {
        prompts.value = null
        await fetchPreview(internalName.value)
      }
    })

    return { prompts, internalName, preview, onSelect }
  },

  template: `
<div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">Prompt</label>
    <select
      v-if="prompts === null"
      disabled style="width:100%"
    ><option>Unavailable</option></select>
    <select
      v-else-if="prompts.length === 0"
      disabled style="width:100%"
    ><option>No prompts available</option></select>
    <select
      v-else
      :value="internalName"
      @change="onSelect($event.target.value)"
      style="width:100%"
    >
      <option v-for="name in prompts" :key="name" :value="name">{{ name }}</option>
    </select>
  </div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">System prompt</label>
    <textarea
      readonly
      :value="preview.system"
      rows="5"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"
    ></textarea>
  </div>
  <div class="form-group" style="margin-bottom:0">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">User prompt</label>
    <textarea
      readonly
      :value="preview.user"
      rows="5"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"
    ></textarea>
  </div>
</div>
`
})

export { PromptSelector }
```

- [ ] **Step 2: Verify the file exists**

```bash
ls frontend-web/js/prompt-selector.js
```
Expected: file listed with no error.

---

### Task 2: Modify `frontend-web/js/rag-tab.js`

**Files:**
- Modify: `frontend-web/js/rag-tab.js`

The changes are in three places: imports/component registration, setup state + return, template.

- [ ] **Step 1: Add the import at the top of the file**

At line 3, after the existing imports, add:
```javascript
import { PromptSelector } from './prompt-selector.js'
```

So the top of the file becomes:
```javascript
import { defineComponent, ref, computed, watch } from 'vue'
import { api, downloadBlob } from './api.js'
import { PromptSelector } from './prompt-selector.js'
```

- [ ] **Step 2: Add `components` and new state refs**

The `defineComponent({...})` call currently has `name`, `props`, `emits`, `setup`. Add `components: { PromptSelector }` as a new key right after `emits`:

```javascript
const RagTab = defineComponent({
  name: 'RagTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  components: { PromptSelector },

  setup(props) {
```

In `setup`, add two new refs right after `showFilters`:
```javascript
    const showFilters  = ref(false)
    const showAdvanced = ref(false)
    const selectedPrompt = ref('default')
```

In the `return` statement at the end of `setup`, add `showAdvanced` and `selectedPrompt`:
```javascript
    return {
      error, loading, query, topK, maxTokens,
      result, papers, selectedIds, showFilters, citationMode,
      collectionId, useHybrid,
      filterSearch, filterDir, allDirs, filteredPapers,
      checkAll, uncheckAll,
      runQuery, togglePassage, exportMd,
      showAdvanced, selectedPrompt,
    }
```

- [ ] **Step 3: Add `prompt_name` to the POST body**

In `runQuery()`, add `prompt_name: selectedPrompt.value` to the body object:
```javascript
        const body = {
          query_text: query.value.trim(),
          limit: topK.value,
          max_tokens: maxTokens.value,
          include_citations: true,
          use_hybrid: useHybrid.value,
          prompt_name: selectedPrompt.value,
        }
```

- [ ] **Step 4: Restructure the template — remove sliders from main form**

In the template, find and remove the `<div class="form-row">` block containing the two sliders (currently lines 131-140 in the original). This block looks like:

```html
      <div class="form-row">
        <div class="form-group" style="margin:0">
          <label>Top-K chunks: {{ topK }}</label>
          <input type="range" v-model.number="topK" min="1" max="50" style="width:100%;margin-top:6px" />
        </div>
        <div class="form-group" style="margin:0">
          <label>Max response tokens: {{ maxTokens }}</label>
          <input type="range" v-model.number="maxTokens" min="50" max="2000" step="50" style="width:100%;margin-top:6px" />
        </div>
      </div>
```

Delete it entirely.

- [ ] **Step 5: Insert the Advanced options panel before the Run button**

Find the `<div class="mt-16">` block that contains the Run button:
```html
      <div class="mt-16">
        <button class="btn btn-primary btn-block" :disabled="loading" @click="runQuery">
```

Insert the following immediately before it (after the closing `</div>` of the paper filter section):

```html
      <!-- Advanced options -->
      <div style="margin-top:12px">
        <button class="btn btn-secondary btn-sm" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '▲' : '▼' }} Advanced options
        </button>
        <div v-show="showAdvanced" style="margin-top:10px;padding:12px;border:1px solid var(--border);border-radius:6px">
          <div class="form-row">
            <div class="form-group" style="margin:0">
              <label>Top-K chunks: {{ topK }}</label>
              <input type="range" v-model.number="topK" min="1" max="50" style="width:100%;margin-top:6px" />
            </div>
            <div class="form-group" style="margin:0">
              <label>Max response tokens: {{ maxTokens }}</label>
              <input type="range" v-model.number="maxTokens" min="50" max="2000" step="50" style="width:100%;margin-top:6px" />
            </div>
          </div>
          <hr style="border:none;border-top:1px solid var(--border);margin:12px 0" />
          <prompt-selector :task-type="'rag'" v-model="selectedPrompt" />
        </div>
      </div>
```

- [ ] **Step 6: Verify by opening the app in a browser**

Open `http://localhost:8000` (or wherever the frontend is served). Navigate to the RAG tab:
1. Confirm the top-K and max-tokens sliders are gone from the main form
2. Confirm an "Advanced options ▼" button appears below the paper filter
3. Click it — panel expands showing sliders + a "Prompt" dropdown
4. Confirm the dropdown shows `default` and the system/user textareas show the rag prompt content
5. Run a query — confirm it works as before

**Do NOT commit. Present the changes to the user for review.**
