# Vue Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Streamlit frontend with a static Vue 3 (CDN) app in `frontend-web/`, deployable to GitHub Pages, that talks directly to the local FastAPI backend.

**Architecture:** Single `index.html` file using Vue 3 via CDN (no build step). All components are defined inline as `defineComponent` objects. A GitHub Actions workflow copies `frontend-web/` to the `gh-pages` branch on every push to `main`. The backend, Qdrant, and Ollama remain local and unchanged.

**Tech Stack:** Vue 3 (CDN, Composition API), vanilla CSS, GitHub Actions, FastAPI (existing, no changes to logic)

---

## Context You Must Read First

- Design doc: `docs/plans/2026-02-27-vue-frontend-design.md`
- Existing Streamlit tabs to mirror: `frontend/tab_preprocessing.py`, `frontend/tab_collections.py`, `frontend/tab_rag.py`, `frontend/tab_explore.py`, `frontend/tab_compare.py`
- Existing helpers: `frontend/helpers.py` (all the API calls to replicate)
- Backend CORS: `backend/app/main.py` (currently `allow_origins=["*"]`)
- Docker Compose: `docker-compose.yml` (need to remove `frontend` service)
- Current branch: `10-make-independent-front-end`

---

## Task 1: Branch Setup

**Files:**
- No file changes — git operations only

**Step 1: Verify you are on the right branch**

```bash
git branch --show-current
```
Expected: `10-make-independent-front-end`

**Step 2: Create a `streamlit` branch from `main` to preserve Streamlit forever**

```bash
git checkout main
git checkout -b streamlit
git push -u origin streamlit
git checkout 10-make-independent-front-end
```

**Step 3: Confirm you are back on the working branch**

```bash
git branch --show-current
```
Expected: `10-make-independent-front-end`

---

## Task 2: Remove Streamlit Frontend & Update Docker Compose

**Files:**
- Delete: `frontend/` (entire directory)
- Modify: `docker-compose.yml` (remove `frontend` service)

**Step 1: Delete the Streamlit frontend directory**

```bash
git rm -r frontend/
```

**Step 2: Update `docker-compose.yml` — remove the `frontend` service block**

Replace the entire file content with:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - ./data/qdrant:/qdrant/storage
    restart: unless-stopped

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
    volumes:
      - ./data:/data
      - ./config.yaml:/app/config.yaml
    env_file:
      - .env
    environment:
      - QDRANT_URL=http://qdrant:6333
      - OLLAMA_URL=http://host.docker.internal:11434
      - DATA_DIR=/data/collections
      - PDF_INPUT_DIR=/data/pdf_input
      - PREPROCESSED_DIR=/data/preprocessed
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

**Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: remove Streamlit frontend, simplify docker-compose"
```

---

## Task 3: Update Backend CORS

**Files:**
- Modify: `backend/app/main.py`

**Step 1: Replace the CORS middleware configuration**

Find this block in `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Replace with (substitute `<your-github-username>` with the real username):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "https://<your-github-username>.github.io",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Note: `allow_credentials` must be `False` when listing specific origins from a cross-origin static site.

**Step 2: Verify backend still starts**

```bash
docker compose up backend --build -d
docker compose logs backend | tail -20
```
Expected: `Application startup complete.` — no errors.

**Step 3: Commit**

```bash
git add backend/app/main.py
git commit -m "fix: restrict CORS to localhost and GitHub Pages origin"
```

---

## Task 4: Create frontend-web/ Scaffold

**Files:**
- Create: `frontend-web/.nojekyll`
- Create: `frontend-web/index.html` (skeleton only — tabs filled in subsequent tasks)

**Step 1: Create the directory and `.nojekyll`**

```bash
mkdir -p frontend-web
touch frontend-web/.nojekyll
```

**Step 2: Create `frontend-web/index.html` with the full skeleton**

This is the base structure — components and tab content are added in Tasks 5–9. Write this file exactly:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PRAG-v2</title>
  <style>
    /* ── Reset & variables ───────────────────────────── */
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --sidebar-w: 260px;
      --bg: #f8fafc;
      --card: #ffffff;
      --border: #e2e8f0;
      --text: #1e293b;
      --muted: #64748b;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --danger: #ef4444;
      --success: #22c55e;
      --warning: #f59e0b;
      --sidebar-bg: #1e293b;
      --sidebar-text: #f1f5f9;
      --sidebar-muted: #94a3b8;
      --sidebar-hover: #334155;
      --radius: 8px;
      --shadow: 0 1px 3px rgba(0,0,0,.1), 0 1px 2px rgba(0,0,0,.06);
    }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.6; }

    /* ── Layout ─────────────────────────────────────── */
    #app { display: flex; min-height: 100vh; }
    .sidebar {
      width: var(--sidebar-w); flex-shrink: 0; background: var(--sidebar-bg);
      color: var(--sidebar-text); display: flex; flex-direction: column;
      position: fixed; top: 0; left: 0; bottom: 0; overflow-y: auto; z-index: 10;
    }
    .main { margin-left: var(--sidebar-w); flex: 1; display: flex; flex-direction: column;
            min-height: 100vh; }

    /* ── Sidebar internals ───────────────────────────── */
    .sidebar-header { padding: 20px 16px 12px; border-bottom: 1px solid #334155; }
    .sidebar-header h1 { font-size: 18px; font-weight: 700; letter-spacing: -.3px; }
    .sidebar-header p  { font-size: 11px; color: var(--sidebar-muted); margin-top: 2px; }
    .sidebar-section { padding: 12px 16px; border-bottom: 1px solid #334155; }
    .sidebar-section-title { font-size: 10px; font-weight: 600; text-transform: uppercase;
                              letter-spacing: .8px; color: var(--sidebar-muted); margin-bottom: 8px; }
    .status-row { display: flex; align-items: center; gap: 8px; font-size: 13px;
                  padding: 3px 0; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .dot-green  { background: var(--success); }
    .dot-red    { background: var(--danger); }
    .dot-yellow { background: var(--warning); }
    .dot-gray   { background: var(--sidebar-muted); }
    .sidebar-label { font-size: 11px; color: var(--sidebar-muted); margin-bottom: 4px; }
    .sidebar-select {
      width: 100%; background: #334155; color: var(--sidebar-text);
      border: 1px solid #475569; border-radius: 6px; padding: 6px 8px;
      font-size: 13px; cursor: pointer;
    }
    .sidebar-select:focus { outline: 2px solid var(--primary); }
    .sidebar-footer { margin-top: auto; padding: 12px 16px;
                      border-top: 1px solid #334155; }
    .btn-ghost { width: 100%; background: none; border: 1px solid #475569;
                 color: var(--sidebar-text); padding: 7px 12px; border-radius: 6px;
                 font-size: 13px; cursor: pointer; display: flex; align-items: center;
                 gap: 6px; justify-content: center; }
    .btn-ghost:hover { background: var(--sidebar-hover); }

    /* ── Tabs ────────────────────────────────────────── */
    .tab-bar { display: flex; background: var(--card); border-bottom: 1px solid var(--border);
               padding: 0 24px; gap: 0; position: sticky; top: 0; z-index: 5; }
    .tab-btn { padding: 14px 18px; font-size: 13px; font-weight: 500; cursor: pointer;
               border: none; background: none; color: var(--muted); border-bottom: 2px solid transparent;
               transition: color .15s, border-color .15s; }
    .tab-btn:hover   { color: var(--text); }
    .tab-btn.active  { color: var(--primary); border-bottom-color: var(--primary); }

    /* ── Content area ────────────────────────────────── */
    .content { flex: 1; padding: 28px 32px; max-width: 960px; }

    /* ── Cards ───────────────────────────────────────── */
    .card { background: var(--card); border: 1px solid var(--border);
            border-radius: var(--radius); padding: 20px; margin-bottom: 16px;
            box-shadow: var(--shadow); }
    .card-title { font-size: 15px; font-weight: 600; margin-bottom: 12px; }

    /* ── Forms ───────────────────────────────────────── */
    label { display: block; font-size: 12px; font-weight: 500; color: var(--muted); margin-bottom: 4px; }
    input[type=text], input[type=number], select, textarea {
      width: 100%; border: 1px solid var(--border); border-radius: 6px;
      padding: 8px 10px; font-size: 13px; color: var(--text);
      background: var(--card); transition: border-color .15s;
    }
    input:focus, select:focus, textarea:focus {
      outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59,130,246,.15);
    }
    textarea { resize: vertical; min-height: 80px; }
    .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
    .form-group { margin-bottom: 12px; }

    /* ── Buttons ─────────────────────────────────────── */
    .btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;
           border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer;
           border: none; transition: background .15s, opacity .15s; }
    .btn:disabled { opacity: .5; cursor: not-allowed; }
    .btn-primary  { background: var(--primary); color: #fff; }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-secondary { background: var(--bg); color: var(--text); border: 1px solid var(--border); }
    .btn-secondary:hover:not(:disabled) { background: var(--border); }
    .btn-danger   { background: var(--danger); color: #fff; }
    .btn-danger:hover:not(:disabled) { background: #dc2626; }
    .btn-sm { padding: 5px 10px; font-size: 12px; }
    .btn-block { width: 100%; justify-content: center; }

    /* ── Alerts ──────────────────────────────────────── */
    .alert { padding: 10px 14px; border-radius: 6px; font-size: 13px; margin-bottom: 16px;
             display: flex; align-items: flex-start; gap: 8px; }
    .alert-error   { background: #fef2f2; border: 1px solid #fca5a5; color: #991b1b; }
    .alert-success { background: #f0fdf4; border: 1px solid #86efac; color: #166534; }
    .alert-info    { background: #eff6ff; border: 1px solid #bfdbfe; color: #1e40af; }
    .alert-warning { background: #fffbeb; border: 1px solid #fde68a; color: #92400e; }
    .alert-close { margin-left: auto; cursor: pointer; opacity: .6; background: none;
                   border: none; font-size: 16px; line-height: 1; color: inherit; }
    .alert-close:hover { opacity: 1; }

    /* ── Badge / Tag ─────────────────────────────────── */
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px;
             font-weight: 500; }
    .badge-blue   { background: #dbeafe; color: #1e40af; }
    .badge-green  { background: #dcfce7; color: #166534; }
    .badge-gray   { background: #f1f5f9; color: var(--muted); }
    .badge-yellow { background: #fef9c3; color: #854d0e; }

    /* ── Spinner ─────────────────────────────────────── */
    .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid currentColor;
               border-top-color: transparent; border-radius: 50%; animation: spin .6s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Table ───────────────────────────────────────── */
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th { text-align: left; padding: 8px 12px; font-size: 11px; font-weight: 600;
         text-transform: uppercase; color: var(--muted); border-bottom: 2px solid var(--border); }
    td { padding: 10px 12px; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--bg); }

    /* ── Misc helpers ────────────────────────────────── */
    .flex   { display: flex; }
    .items-center { align-items: center; }
    .gap-8  { gap: 8px; }
    .gap-12 { gap: 12px; }
    .mt-8   { margin-top: 8px; }
    .mt-16  { margin-top: 16px; }
    .mb-16  { margin-bottom: 16px; }
    .text-muted { color: var(--muted); }
    .text-sm    { font-size: 12px; }
    .font-mono  { font-family: 'SF Mono', 'Fira Code', monospace; }
    .divider { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
    .page-title { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
    .page-sub   { font-size: 13px; color: var(--muted); margin-bottom: 20px; }
    .empty-state { text-align: center; padding: 48px 16px; color: var(--muted); }
    .empty-state p { margin-top: 8px; font-size: 13px; }
    pre { background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
          padding: 12px; font-size: 12px; overflow-x: auto; white-space: pre-wrap;
          word-break: break-all; font-family: 'SF Mono', 'Fira Code', monospace; }

    /* ── Collapsible ─────────────────────────────────── */
    .collapsible { border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; }
    .collapsible-header { display: flex; align-items: center; justify-content: space-between;
                          padding: 10px 14px; cursor: pointer; font-weight: 500; font-size: 13px; }
    .collapsible-header:hover { background: var(--bg); border-radius: 6px; }
    .collapsible-body { padding: 0 14px 12px; font-size: 13px; }
    .chevron { transition: transform .2s; display: inline-block; }
    .chevron.open { transform: rotate(90deg); }

    /* ── Modal ───────────────────────────────────────── */
    .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4);
                     z-index: 100; display: flex; align-items: center; justify-content: center; }
    .modal { background: var(--card); border-radius: var(--radius); padding: 24px;
             width: 460px; max-width: 95vw; box-shadow: 0 20px 60px rgba(0,0,0,.2); }
    .modal-title { font-size: 16px; font-weight: 600; margin-bottom: 20px; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 20px; }

    /* ── Progress bar ────────────────────────────────── */
    .progress-bar { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--primary); border-radius: 2px;
                     transition: width .3s ease; }

    /* ── File list ───────────────────────────────────── */
    .file-item { display: flex; align-items: center; justify-content: space-between;
                 padding: 8px 12px; border: 1px solid var(--border); border-radius: 6px;
                 margin-bottom: 6px; background: var(--card); }
    .file-item:hover { border-color: var(--primary); }
    .file-name { font-size: 13px; font-weight: 500; }
    .file-meta { font-size: 11px; color: var(--muted); }

    /* ── Citation box ────────────────────────────────── */
    .citation-box { background: var(--bg); border-left: 3px solid var(--primary);
                    padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: 8px; }

    /* ── Passage ─────────────────────────────────────── */
    .passage { border: 1px solid var(--border); border-radius: 6px; padding: 12px;
               margin-bottom: 8px; }
    .passage-score { font-size: 11px; color: var(--primary); font-weight: 600; }
    .passage-text { margin: 6px 0; line-height: 1.6; }
    .passage-meta  { font-size: 11px; color: var(--muted); }

    /* ── Checkbox toggle ─────────────────────────────── */
    .checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer;
                      font-size: 13px; padding: 4px 0; }
    .checkbox-label input[type=checkbox] { width: 14px; height: 14px; cursor: pointer; }

    /* ── Radio ───────────────────────────────────────── */
    .radio-group { display: flex; flex-direction: column; gap: 6px; }
    .radio-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; }

    @media (max-width: 768px) {
      .sidebar { width: 100%; position: relative; height: auto; }
      .main { margin-left: 0; }
      .form-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
<div id="app">

  <!-- ───────────────── SIDEBAR ───────────────── -->
  <aside class="sidebar">
    <div class="sidebar-header">
      <h1>PRAG-v2</h1>
      <p>Academic RAG System</p>
    </div>

    <!-- Connection status -->
    <div class="sidebar-section">
      <div class="sidebar-section-title">Status</div>
      <div class="status-row">
        <span class="dot" :class="health.backend ? 'dot-green' : 'dot-red'"></span>
        <span>Backend</span>
      </div>
      <div class="status-row">
        <span class="dot" :class="health.qdrant ? 'dot-green' : 'dot-red'"></span>
        <span>Qdrant</span>
      </div>
      <div class="status-row">
        <span class="dot" :class="health.ollama === true ? 'dot-green' : health.ollama === false ? 'dot-red' : 'dot-yellow'"></span>
        <span>Ollama</span>
      </div>
    </div>

    <!-- Collection picker -->
    <div class="sidebar-section">
      <div class="sidebar-label">Active collection</div>
      <select class="sidebar-select" v-model="selectedCollection" @change="saveCollection">
        <option value="">— none —</option>
        <option v-for="c in collections" :key="c.collection_id" :value="c.collection_id">
          {{ c.name || c.collection_id }}
        </option>
      </select>
    </div>

    <div class="sidebar-footer">
      <button class="btn-ghost" @click="showSettings = true">⚙ Settings</button>
    </div>
  </aside>

  <!-- ───────────────── MAIN ───────────────── -->
  <div class="main">

    <!-- Tab bar -->
    <nav class="tab-bar">
      <button v-for="tab in tabs" :key="tab.id"
              class="tab-btn" :class="{active: activeTab === tab.id}"
              @click="activeTab = tab.id">
        {{ tab.label }}
      </button>
    </nav>

    <!-- Tab content -->
    <div class="content">
      <!-- Global error banner -->
      <div v-if="globalError" class="alert alert-error">
        {{ globalError }}
        <button class="alert-close" @click="globalError = null">×</button>
      </div>

      <keep-alive>
        <component :is="activeComponent"
                   :selected-collection="selectedCollection"
                   :collections="collections"
                   @update:collection="setCollection"
                   @refresh-collections="loadCollections" />
      </keep-alive>
    </div>
  </div>

  <!-- ───────────────── SETTINGS MODAL ───────────────── -->
  <div class="modal-overlay" v-if="showSettings" @click.self="showSettings = false">
    <div class="modal">
      <div class="modal-title">⚙ Settings</div>

      <div class="form-group">
        <label>Backend URL</label>
        <input type="text" v-model="settingsForm.backendUrl"
               placeholder="http://localhost:8000" />
      </div>
      <div class="flex items-center gap-8" style="margin-bottom:12px">
        <span class="dot" :class="settingsStatus === 'ok' ? 'dot-green' : settingsStatus === 'checking' ? 'dot-yellow' : 'dot-red'"></span>
        <span class="text-muted text-sm">
          {{ settingsStatus === 'ok' ? 'Connected' : settingsStatus === 'checking' ? 'Checking…' : 'Not reachable' }}
        </span>
      </div>

      <div class="modal-footer">
        <button class="btn btn-secondary" @click="showSettings = false">Cancel</button>
        <button class="btn btn-primary" @click="saveSettings">Save & connect</button>
      </div>
    </div>
  </div>

</div><!-- #app -->

<script type="module">
import {
  createApp, defineComponent, ref, reactive, computed,
  onMounted, onUnmounted, watch
} from 'https://unpkg.com/vue@3/dist/vue.esm-browser.js'

/* ═══════════════════════════════════════════════
   API WRAPPER
   All fetch calls go through here. Reads backendUrl
   from localStorage on every call so changes take
   effect immediately after saving settings.
═══════════════════════════════════════════════ */
const api = {
  url: () => localStorage.getItem('prag_backend_url') || 'http://localhost:8000',

  async get(path) {
    const r = await fetch(api.url() + path)
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async post(path, body = {}) {
    const r = await fetch(api.url() + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async del(path) {
    const r = await fetch(api.url() + path, { method: 'DELETE' })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.status === 204 ? null : r.json()
  },

  async upload(path, formData) {
    const r = await fetch(api.url() + path, { method: 'POST', body: formData })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async download(path) {
    const r = await fetch(api.url() + path)
    if (!r.ok) throw new Error(`${r.status}`)
    return r.blob()
  },
}

/* ═══════════════════════════════════════════════
   SHARED UTILITY
   Trigger a file download in the browser.
═══════════════════════════════════════════════ */
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

/* ═══════════════════════════════════════════════
   PLACEHOLDER COMPONENTS
   Filled in Tasks 5–9.
═══════════════════════════════════════════════ */
const PdfTab = defineComponent({
  name: 'PdfTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],
  template: `<div><p class="text-muted">PDF Management — coming soon</p></div>`,
})

const CollectionsTab = defineComponent({
  name: 'CollectionsTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],
  template: `<div><p class="text-muted">Collections — coming soon</p></div>`,
})

const RagTab = defineComponent({
  name: 'RagTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  template: `<div><p class="text-muted">RAG Query — coming soon</p></div>`,
})

const ExploreTab = defineComponent({
  name: 'ExploreTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  template: `<div><p class="text-muted">Explore Paper — coming soon</p></div>`,
})

const CompareTab = defineComponent({
  name: 'CompareTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  template: `<div><p class="text-muted">Compare Papers — coming soon</p></div>`,
})

/* ═══════════════════════════════════════════════
   ROOT APP
═══════════════════════════════════════════════ */
createApp({
  components: { PdfTab, CollectionsTab, RagTab, ExploreTab, CompareTab },

  setup() {
    /* ── State ──────────────────────────────── */
    const activeTab = ref('pdf')
    const selectedCollection = ref(localStorage.getItem('prag_collection') || '')
    const collections = ref([])
    const globalError = ref(null)
    const showSettings = ref(false)
    const health = reactive({ backend: false, qdrant: false, ollama: null })

    const settingsForm = reactive({
      backendUrl: localStorage.getItem('prag_backend_url') || 'http://localhost:8000',
    })
    const settingsStatus = ref('unknown') // 'ok' | 'error' | 'checking' | 'unknown'

    const tabs = [
      { id: 'pdf',         label: 'PDF Management' },
      { id: 'collections', label: 'Collections' },
      { id: 'rag',         label: 'RAG Query' },
      { id: 'explore',     label: 'Explore Paper' },
      { id: 'compare',     label: 'Compare' },
    ]

    const tabComponents = {
      pdf: 'PdfTab',
      collections: 'CollectionsTab',
      rag: 'RagTab',
      explore: 'ExploreTab',
      compare: 'CompareTab',
    }

    const activeComponent = computed(() => tabComponents[activeTab.value])

    /* ── Actions ────────────────────────────── */
    async function checkHealth() {
      try {
        const data = await api.get('/health')
        health.backend = true
        health.qdrant  = data.qdrant === 'ok'
        health.ollama  = data.ollama === 'ok'
      } catch {
        health.backend = false
        health.qdrant  = false
        health.ollama  = false
      }
    }

    async function loadCollections() {
      try {
        collections.value = await api.get('/collections')
      } catch (e) {
        globalError.value = 'Could not load collections: ' + e.message
      }
    }

    function setCollection(id) {
      selectedCollection.value = id
      localStorage.setItem('prag_collection', id)
    }

    function saveCollection() {
      localStorage.setItem('prag_collection', selectedCollection.value)
    }

    async function saveSettings() {
      settingsStatus.value = 'checking'
      localStorage.setItem('prag_backend_url', settingsForm.backendUrl)
      try {
        await api.get('/health')
        settingsStatus.value = 'ok'
        showSettings.value = false
        await checkHealth()
        await loadCollections()
      } catch {
        settingsStatus.value = 'error'
      }
    }

    /* ── Lifecycle ──────────────────────────── */
    let healthTimer
    onMounted(async () => {
      await checkHealth()
      await loadCollections()
      healthTimer = setInterval(checkHealth, 30_000)
    })
    onUnmounted(() => clearInterval(healthTimer))

    return {
      activeTab, tabs, activeComponent,
      selectedCollection, collections,
      globalError, showSettings, health,
      settingsForm, settingsStatus,
      setCollection, saveCollection, saveSettings, loadCollections,
    }
  },
}).mount('#app')
</script>
</body>
</html>
```

**Step 3: Open `frontend-web/index.html` in a browser and verify**

```bash
open frontend-web/index.html
# or on Linux:
xdg-open frontend-web/index.html
```

Expected:
- Dark sidebar with "PRAG-v2" heading
- Status dots (all red if backend not running — that is OK)
- 5 tabs at the top, all showing "coming soon" placeholder
- Settings modal opens when clicking ⚙ Settings

**Step 4: Commit the scaffold**

```bash
git add frontend-web/
git commit -m "feat: add Vue frontend scaffold with layout, sidebar, settings modal"
```

---

## Task 5: PDF Management Tab

**Files:**
- Modify: `frontend-web/index.html` — replace `PdfTab` placeholder component

This tab corresponds to `frontend/tab_preprocessing.py`.

**Functionality to implement:**
- List PDF directories with file counts
- Upload new PDFs to a directory (or new directory name)
- For each file: show conversion status, trigger conversion, delete
- Show extracted assets (metadata, tables count, images count) after conversion

**Step 1: Replace the `PdfTab` placeholder**

Find this in `index.html`:
```js
const PdfTab = defineComponent({
  name: 'PdfTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],
  template: `<div><p class="text-muted">PDF Management — coming soon</p></div>`,
})
```

Replace with:

```js
const PdfTab = defineComponent({
  name: 'PdfTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],

  setup(props, { emit }) {
    const error       = ref(null)
    const directories = ref([])    // [{ dir_name, files: [{filename, has_markdown, …}] }]
    const loading     = ref(false)
    const uploadDir   = ref('')    // directory name for uploads
    const converting  = reactive({}) // { "dirName/filename": true }
    const expanded    = reactive({}) // { "dirName": true }

    async function loadDirs() {
      try {
        const data = await api.get('/preprocess/directories')
        directories.value = data
      } catch (e) { error.value = e.message }
    }

    async function uploadFiles(evt) {
      const files = evt.target.files
      if (!files.length) return
      const dir = uploadDir.value.trim() || 'uploads'
      const fd = new FormData()
      fd.append('dir_name', dir)
      for (const f of files) fd.append('files', f)
      loading.value = true
      try {
        await api.upload('/preprocess/upload', fd)
        await loadDirs()
        uploadDir.value = ''
        evt.target.value = ''
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    async function convertFile(dirName, filename) {
      const key = `${dirName}/${filename}`
      converting[key] = true
      error.value = null
      try {
        await api.post('/preprocess/convert', {
          dir_name: dirName,
          filename,
          backend: localStorage.getItem('prag_pdf_backend') || 'pymupdf',
          enrich_metadata: true,
          metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
        })
        await loadDirs()
      } catch (e) { error.value = e.message }
      finally { delete converting[key] }
    }

    async function deleteFile(dirName, filename) {
      if (!confirm(`Delete ${filename}?`)) return
      try {
        await api.post('/preprocess/delete-pdf', { dir_name: dirName, filename })
        await loadDirs()
      } catch (e) { error.value = e.message }
    }

    function toggleDir(d) { expanded[d] = !expanded[d] }

    onMounted(loadDirs)

    return {
      error, directories, loading, uploadDir,
      converting, expanded,
      loadDirs, uploadFiles, convertFile, deleteFile, toggleDir,
    }
  },

  template: `
<div>
  <h2 class="page-title">PDF Management</h2>
  <p class="page-sub">Upload and convert PDFs to markdown for ingestion.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}
    <button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Upload card -->
  <div class="card">
    <div class="card-title">Upload PDFs</div>
    <div class="form-row">
      <div class="form-group" style="margin:0">
        <label>Directory name</label>
        <input type="text" v-model="uploadDir" placeholder="my-papers" />
      </div>
      <div class="form-group" style="margin:0; display:flex; align-items:flex-end;">
        <label style="display:none">File</label>
        <input type="file" accept=".pdf" multiple @change="uploadFiles"
               :disabled="loading" style="font-size:13px;width:100%;" />
      </div>
    </div>
    <div v-if="loading" class="flex items-center gap-8 mt-8">
      <span class="spinner"></span> <span class="text-muted">Uploading…</span>
    </div>
  </div>

  <!-- Directories -->
  <div v-if="directories.length === 0" class="empty-state">
    <div style="font-size:32px">📂</div>
    <p>No PDFs uploaded yet. Use the form above to get started.</p>
  </div>

  <div v-for="dir in directories" :key="dir.dir_name" class="card" style="padding:0;overflow:hidden">
    <!-- Directory header -->
    <div class="collapsible-header" @click="toggleDir(dir.dir_name)"
         style="padding:14px 20px;background:var(--bg);">
      <span>
        <strong>{{ dir.dir_name }}</strong>
        <span class="badge badge-gray" style="margin-left:8px">{{ dir.files.length }} files</span>
      </span>
      <span class="chevron" :class="{open: expanded[dir.dir_name]}">▶</span>
    </div>

    <div v-if="expanded[dir.dir_name]" style="padding:0 20px 16px">
      <div v-if="dir.files.length === 0" class="text-muted text-sm mt-8">No files.</div>

      <div v-for="file in dir.files" :key="file.filename" class="file-item">
        <div>
          <div class="file-name">{{ file.filename }}</div>
          <div class="file-meta">
            <span v-if="file.has_markdown" class="badge badge-green">Converted</span>
            <span v-else class="badge badge-gray">Not converted</span>
          </div>
        </div>
        <div class="flex gap-8">
          <button class="btn btn-secondary btn-sm"
                  :disabled="!!converting[dir.dir_name+'/'+file.filename]"
                  @click="convertFile(dir.dir_name, file.filename)">
            <span v-if="converting[dir.dir_name+'/'+file.filename]" class="spinner"></span>
            <span v-else>Convert</span>
          </button>
          <button class="btn btn-danger btn-sm"
                  @click="deleteFile(dir.dir_name, file.filename)">Delete</button>
        </div>
      </div>
    </div>
  </div>

  <button class="btn btn-secondary mt-16" @click="loadDirs">↻ Refresh</button>
</div>
`,
})
```

**Step 2: Open the browser, click PDF Management tab, verify:**
- Upload card renders
- Clicking a directory header expands/collapses it
- Upload a test PDF and confirm it appears in the list (backend must be running)

**Step 3: Commit**

```bash
git add frontend-web/index.html
git commit -m "feat: add PDF Management tab to Vue frontend"
```

---

## Task 6: Collections Tab

**Files:**
- Modify: `frontend-web/index.html` — replace `CollectionsTab` placeholder

Mirrors `frontend/tab_collections.py`.

**Step 1: Replace `CollectionsTab` placeholder with:**

```js
const CollectionsTab = defineComponent({
  name: 'CollectionsTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],

  setup(props, { emit }) {
    const error      = ref(null)
    const creating   = ref(false)
    const ingesting  = reactive({}) // { collectionId: true }
    const newForm    = reactive({ collection_id: '', name: '', search_type: 'dense', dir_name: '' })
    const scanResult = ref(null)

    async function createCollection() {
      if (!newForm.collection_id) { error.value = 'Collection ID is required.'; return }
      creating.value = true; error.value = null
      try {
        if (newForm.dir_name) {
          // scan + create in one call
          const data = await api.post('/ingest/create', {
            collection_id: newForm.collection_id,
            name: newForm.name || newForm.collection_id,
            search_type: newForm.search_type,
            dir_name: newForm.dir_name,
          })
          scanResult.value = data
        } else {
          await api.post('/collections', {
            collection_id: newForm.collection_id,
            name: newForm.name || newForm.collection_id,
            search_type: newForm.search_type,
          })
        }
        emit('refresh-collections')
        Object.assign(newForm, { collection_id: '', name: '', search_type: 'dense', dir_name: '' })
      } catch (e) { error.value = e.message }
      finally { creating.value = false }
    }

    async function ingestFile(collectionId, fileId) {
      ingesting[collectionId + '/' + fileId] = true
      try {
        await api.post(`/ingest/${collectionId}/file`, { file_id: fileId })
      } catch (e) { error.value = e.message }
      finally { delete ingesting[collectionId + '/' + fileId] }
    }

    async function deleteCollection(id) {
      if (!confirm(`Delete collection "${id}"? This cannot be undone.`)) return
      try {
        await api.del(`/collections/${id}`)
        if (props.selectedCollection === id) emit('update:collection', '')
        emit('refresh-collections')
      } catch (e) { error.value = e.message }
    }

    return {
      error, creating, ingesting, newForm, scanResult,
      createCollection, ingestFile, deleteCollection,
    }
  },

  template: `
<div>
  <h2 class="page-title">Collections</h2>
  <p class="page-sub">Create collections and ingest converted papers.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Create form -->
  <div class="card">
    <div class="card-title">Create collection</div>
    <div class="form-row">
      <div class="form-group" style="margin:0">
        <label>Collection ID *</label>
        <input type="text" v-model="newForm.collection_id" placeholder="my-collection" />
      </div>
      <div class="form-group" style="margin:0">
        <label>Display name</label>
        <input type="text" v-model="newForm.name" placeholder="My Papers" />
      </div>
    </div>
    <div class="form-row" style="margin-top:8px">
      <div class="form-group" style="margin:0">
        <label>Search type</label>
        <select v-model="newForm.search_type">
          <option value="dense">Dense (vector only)</option>
          <option value="hybrid">Hybrid (vector + BM42)</option>
        </select>
      </div>
      <div class="form-group" style="margin:0">
        <label>Ingest from directory (optional)</label>
        <input type="text" v-model="newForm.dir_name" placeholder="my-papers" />
      </div>
    </div>
    <div class="mt-16">
      <button class="btn btn-primary" :disabled="creating" @click="createCollection">
        <span v-if="creating" class="spinner"></span>
        Create
      </button>
    </div>
    <div v-if="scanResult" class="alert alert-success mt-8">
      Created. Ingested {{ scanResult.ingested || 0 }} files.
    </div>
  </div>

  <!-- Existing collections -->
  <div v-if="collections.length === 0" class="empty-state">
    <div style="font-size:32px">📚</div>
    <p>No collections yet.</p>
  </div>

  <div v-for="col in collections" :key="col.collection_id" class="card">
    <div class="flex items-center gap-8" style="margin-bottom:8px">
      <div style="flex:1">
        <strong>{{ col.name || col.collection_id }}</strong>
        <span class="badge badge-blue" style="margin-left:8px">{{ col.search_type }}</span>
      </div>
      <button class="btn btn-danger btn-sm" @click="deleteCollection(col.collection_id)">Delete</button>
    </div>
    <div class="text-sm text-muted">
      ID: <code class="font-mono">{{ col.collection_id }}</code>
      &nbsp;·&nbsp;
      {{ col.paper_count ?? '?' }} papers
    </div>
  </div>
</div>
`,
})
```

**Step 2: Verify in browser:**
- Form renders correctly
- Creating a collection with the backend running works
- Existing collections appear in the list

**Step 3: Commit**

```bash
git add frontend-web/index.html
git commit -m "feat: add Collections tab to Vue frontend"
```

---

## Task 7: RAG Query Tab

**Files:**
- Modify: `frontend-web/index.html` — replace `RagTab` placeholder

Mirrors `frontend/tab_rag.py`.

**Step 1: Replace `RagTab` placeholder with:**

```js
const RagTab = defineComponent({
  name: 'RagTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],

  setup(props, { emit }) {
    const error       = ref(null)
    const loading     = ref(false)
    const query       = ref('')
    const topK        = ref(10)
    const maxTokens   = ref(500)
    const result      = ref(null)
    const papers      = ref([])
    const selectedIds = ref([])
    const showFilters = ref(false)
    const citationMode = ref('apa')  // 'apa' | 'bibtex'

    const collectionId = computed(() => props.selectedCollection)
    const collection   = computed(() => props.collections.find(c => c.collection_id === collectionId.value))
    const useHybrid    = computed(() => collection.value?.search_type === 'hybrid')

    watch(collectionId, async (id) => {
      if (id) {
        try { papers.value = await api.get(`/collections/${id}/papers`) }
        catch { papers.value = [] }
      }
    }, { immediate: true })

    async function runQuery() {
      if (!collectionId.value) { error.value = 'Select a collection first.'; return }
      if (!query.value.trim()) { error.value = 'Enter a question.'; return }
      loading.value = true; error.value = null; result.value = null
      try {
        result.value = await api.post(`/collections/${collectionId.value}/rag`, {
          query_text: query.value,
          limit: topK.value,
          max_tokens: maxTokens.value,
          include_citations: true,
          use_hybrid: useHybrid.value,
          paper_ids: selectedIds.value.length ? selectedIds.value : undefined,
        })
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function exportMd() {
      if (!result.value) return
      const lines = [
        '# RAG Export', '', `**Query:** ${query.value}`, '',
        '## Answer', '', result.value.answer || '', '',
        '## Retrieved Passages', '',
        ...(result.value.results || []).flatMap((r, i) => [
          `### ${i+1}. ${r.unique_id} (score ${r.score?.toFixed(3)})`,
          `> ${r.chunk_text}`, `*Page ${r.page_number} · ${r.chunk_type}*`, '',
        ]),
        '## Citations', '',
        ...Object.values(result.value.citations || {}).flatMap(c => [
          `**${c.unique_id}**`, c.apa, '```bibtex', c.bibtex, '```', '',
        ]),
      ]
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
      downloadBlob(blob, 'rag-export.md')
    }

    return {
      error, loading, query, topK, maxTokens,
      result, papers, selectedIds, showFilters, citationMode,
      collectionId, useHybrid,
      runQuery, exportMd,
    }
  },

  template: `
<div>
  <h2 class="page-title">RAG Query</h2>
  <p class="page-sub">Ask questions across your paper collection.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="!collectionId" class="alert alert-info">
    Select a collection from the sidebar to get started.
  </div>

  <template v-else>
    <!-- Query card -->
    <div class="card">
      <div class="form-group">
        <label>Question</label>
        <textarea v-model="query" rows="3"
          placeholder="e.g., What are the main findings about attention mechanisms?"></textarea>
      </div>

      <div class="form-row">
        <div class="form-group" style="margin:0">
          <label>Top-K chunks ({{ topK }})</label>
          <input type="range" v-model.number="topK" min="1" max="50" style="width:100%" />
        </div>
        <div class="form-group" style="margin:0">
          <label>Max response tokens ({{ maxTokens }})</label>
          <input type="range" v-model.number="maxTokens" min="50" max="2000" step="50" style="width:100%" />
        </div>
      </div>

      <!-- Paper filter -->
      <div style="margin-top:8px">
        <button class="btn btn-secondary btn-sm" @click="showFilters = !showFilters">
          {{ showFilters ? '▲' : '▼' }} Filter by paper {{ selectedIds.length ? '('+selectedIds.length+' selected)' : '(all)' }}
        </button>
        <div v-if="showFilters" style="margin-top:8px;max-height:160px;overflow-y:auto;border:1px solid var(--border);border-radius:6px;padding:8px">
          <label v-for="p in papers" :key="p.paper_id" class="checkbox-label">
            <input type="checkbox" :value="p.paper_id" v-model="selectedIds" />
            {{ p.title || p.filename || p.paper_id }}
          </label>
        </div>
      </div>

      <div class="mt-16">
        <button class="btn btn-primary btn-block" :disabled="loading" @click="runQuery">
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? 'Searching…' : 'Search' }}</span>
        </button>
      </div>
    </div>

    <!-- Results -->
    <div v-if="result">
      <!-- Answer -->
      <div class="card" v-if="result.answer">
        <div class="flex items-center gap-8" style="margin-bottom:12px">
          <div class="card-title" style="margin:0;flex:1">Answer</div>
          <button class="btn btn-secondary btn-sm" @click="exportMd">⬇ Export MD</button>
        </div>
        <div style="line-height:1.7;white-space:pre-wrap">{{ result.answer }}</div>
      </div>

      <!-- Passages -->
      <div class="card" v-if="result.results?.length">
        <div class="card-title">Retrieved passages ({{ result.results.length }})</div>
        <div v-for="(r, i) in result.results" :key="i" class="collapsible">
          <div class="collapsible-header">
            <span>
              <span class="passage-score">{{ r.score?.toFixed(3) }}</span>
              &nbsp;·&nbsp;{{ r.unique_id }} · p.{{ r.page_number }} · {{ r.chunk_type }}
            </span>
            <span class="chevron" :class="{open: r._open}" @click.stop="r._open = !r._open">▶</span>
          </div>
          <div v-if="r._open" class="collapsible-body">
            <p class="passage-text">{{ r.chunk_text }}</p>
          </div>
        </div>
      </div>

      <!-- Citations -->
      <div class="card" v-if="result.citations && Object.keys(result.citations).length">
        <div class="flex items-center gap-8" style="margin-bottom:12px">
          <div class="card-title" style="margin:0;flex:1">Citations</div>
          <button class="btn btn-secondary btn-sm" :class="{active: citationMode==='apa'}"
                  @click="citationMode='apa'">APA</button>
          <button class="btn btn-secondary btn-sm" :class="{active: citationMode==='bibtex'}"
                  @click="citationMode='bibtex'">BibTeX</button>
        </div>
        <div v-for="(c, key) in result.citations" :key="key" class="citation-box" style="margin-bottom:8px">
          <div style="font-weight:600;font-size:13px;margin-bottom:4px">{{ c.unique_id }}</div>
          <pre v-if="citationMode==='bibtex'">{{ c.bibtex }}</pre>
          <p v-else style="font-size:13px">{{ c.apa }}</p>
        </div>
      </div>
    </div>
  </template>
</div>
`,
})
```

**Step 2: Verify in browser:**
- Select a collection, type a query, click Search
- Answer and passages appear
- Passages are collapsible
- Citation toggle works (APA / BibTeX)

**Step 3: Commit**

```bash
git add frontend-web/index.html
git commit -m "feat: add RAG Query tab to Vue frontend"
```

---

## Task 8: Explore Paper Tab

**Files:**
- Modify: `frontend-web/index.html` — replace `ExploreTab` placeholder

Mirrors `frontend/tab_explore.py`.

**Step 1: Replace `ExploreTab` placeholder with:**

```js
const ExploreTab = defineComponent({
  name: 'ExploreTab',
  props: ['selectedCollection', 'collections'],

  setup(props) {
    const error    = ref(null)
    const papers   = ref([])
    const selected = ref(null)  // paper object
    const detail   = ref(null)
    const loading  = ref(false)

    const collectionId = computed(() => props.selectedCollection)

    watch(collectionId, async (id) => {
      papers.value = []; selected.value = null; detail.value = null
      if (id) {
        try { papers.value = await api.get(`/collections/${id}/papers`) }
        catch (e) { error.value = e.message }
      }
    }, { immediate: true })

    async function selectPaper(paper) {
      selected.value = paper
      loading.value = true; detail.value = null
      try {
        detail.value = await api.get(`/collections/${collectionId.value}/papers/${paper.paper_id}`)
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    return { error, papers, selected, detail, loading, selectPaper }
  },

  template: `
<div>
  <h2 class="page-title">Explore Paper</h2>
  <p class="page-sub">Browse papers in the active collection.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="!collectionId" class="alert alert-info">Select a collection from the sidebar.</div>

  <template v-else>
    <div style="display:grid;grid-template-columns:260px 1fr;gap:20px">
      <!-- Paper list -->
      <div>
        <div class="card" style="padding:0;overflow:hidden">
          <div style="padding:12px 16px;border-bottom:1px solid var(--border);font-weight:600;font-size:13px">
            Papers ({{ papers.length }})
          </div>
          <div style="max-height:70vh;overflow-y:auto">
            <div v-if="papers.length === 0" class="text-muted text-sm" style="padding:16px">
              No papers in this collection.
            </div>
            <div v-for="p in papers" :key="p.paper_id"
                 style="padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--border)"
                 :style="selected?.paper_id === p.paper_id ? 'background:var(--primary);color:#fff' : ''"
                 @click="selectPaper(p)">
              <div style="font-size:13px;font-weight:500">{{ p.title || p.filename }}</div>
              <div style="font-size:11px;opacity:.7">{{ (p.authors||[]).slice(0,2).join(', ') }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Detail panel -->
      <div>
        <div v-if="loading" class="flex items-center gap-8"><span class="spinner"></span> Loading…</div>

        <template v-else-if="detail">
          <div class="card">
            <h3 style="font-size:17px;margin-bottom:8px">{{ detail.title }}</h3>
            <div class="text-muted text-sm" style="margin-bottom:12px">
              {{ (detail.authors||[]).join(', ') }}
              <span v-if="detail.year"> · {{ detail.year }}</span>
              <span v-if="detail.journal"> · <em>{{ detail.journal }}</em></span>
            </div>
            <div v-if="detail.doi" class="text-sm" style="margin-bottom:8px">
              DOI: <a :href="'https://doi.org/'+detail.doi" target="_blank"
                      style="color:var(--primary)">{{ detail.doi }}</a>
            </div>

            <!-- Abstract collapsible -->
            <div v-if="detail.abstract" class="collapsible" style="margin-top:12px">
              <div class="collapsible-header" @click="detail._showAbstract = !detail._showAbstract">
                Abstract
                <span class="chevron" :class="{open: detail._showAbstract}">▶</span>
              </div>
              <div v-if="detail._showAbstract" class="collapsible-body">
                <p>{{ detail.abstract }}</p>
              </div>
            </div>

            <!-- Chunks info -->
            <div class="text-sm text-muted" style="margin-top:12px">
              {{ detail.chunk_count ?? '?' }} chunks
              <span v-if="detail.metadata_source"> · metadata from {{ detail.metadata_source }}</span>
              <span v-if="detail.backend"> · converted with {{ detail.backend }}</span>
            </div>
          </div>
        </template>

        <div v-else class="empty-state">
          <p>Select a paper from the list to view details.</p>
        </div>
      </div>
    </div>
  </template>
</div>
`,
})
```

**Step 2: Commit**

```bash
git add frontend-web/index.html
git commit -m "feat: add Explore Paper tab to Vue frontend"
```

---

## Task 9: Compare Tab

**Files:**
- Modify: `frontend-web/index.html` — replace `CompareTab` placeholder

Mirrors `frontend/tab_compare.py`.

**Step 1: Replace `CompareTab` placeholder with:**

```js
const CompareTab = defineComponent({
  name: 'CompareTab',
  props: ['selectedCollection', 'collections'],

  setup(props) {
    const error      = ref(null)
    const loading    = ref(false)
    const papers     = ref([])
    const selectedIds = ref([])
    const aspect     = ref('all')
    const maxTokens  = ref(800)
    const result     = ref(null)

    const aspects = [
      { value: 'all',          label: 'All aspects' },
      { value: 'methodology',  label: 'Methodology' },
      { value: 'results',      label: 'Results & findings' },
      { value: 'limitations',  label: 'Limitations' },
      { value: 'contributions',label: 'Contributions' },
    ]

    const collectionId = computed(() => props.selectedCollection)

    watch(collectionId, async (id) => {
      papers.value = []; selectedIds.value = []; result.value = null
      if (id) {
        try { papers.value = await api.get(`/collections/${id}/papers`) }
        catch (e) { error.value = e.message }
      }
    }, { immediate: true })

    async function compare() {
      if (selectedIds.value.length < 2) { error.value = 'Select at least 2 papers.'; return }
      loading.value = true; error.value = null; result.value = null
      try {
        result.value = await api.post(`/collections/${collectionId.value}/compare`, {
          paper_ids: selectedIds.value,
          aspect: aspect.value,
          max_tokens: maxTokens.value,
        })
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function exportMd() {
      if (!result.value) return
      const lines = [
        '# Paper Comparison', '',
        `**Aspect:** ${aspect.value}`, '',
        '## Comparison', '', result.value.comparison || '', '',
        '## Papers', '',
        ...(result.value.papers || []).map(p => `- **${p.title}** (${p.year}) — ${(p.authors||[]).join(', ')}`),
      ]
      const blob = new Blob([lines.join('\n')], { type: 'text/markdown' })
      downloadBlob(blob, 'comparison.md')
    }

    return {
      error, loading, papers, selectedIds, aspect, maxTokens, result, aspects,
      compare, exportMd, collectionId,
    }
  },

  template: `
<div>
  <h2 class="page-title">Compare Papers</h2>
  <p class="page-sub">Ask the LLM to compare multiple papers across a specific aspect.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="!collectionId" class="alert alert-info">Select a collection from the sidebar.</div>

  <template v-else>
    <div class="card">
      <div class="card-title">Select papers to compare</div>
      <div style="max-height:200px;overflow-y:auto;margin-bottom:12px">
        <div v-if="papers.length === 0" class="text-muted text-sm">No papers in this collection.</div>
        <label v-for="p in papers" :key="p.paper_id" class="checkbox-label">
          <input type="checkbox" :value="p.paper_id" v-model="selectedIds" />
          {{ p.title || p.filename || p.paper_id }}
        </label>
      </div>

      <div class="form-row">
        <div class="form-group" style="margin:0">
          <label>Aspect</label>
          <select v-model="aspect">
            <option v-for="a in aspects" :key="a.value" :value="a.value">{{ a.label }}</option>
          </select>
        </div>
        <div class="form-group" style="margin:0">
          <label>Max tokens ({{ maxTokens }})</label>
          <input type="range" v-model.number="maxTokens" min="100" max="2000" step="50" style="width:100%" />
        </div>
      </div>

      <div class="mt-16">
        <button class="btn btn-primary btn-block" :disabled="loading || selectedIds.length < 2"
                @click="compare">
          <span v-if="loading" class="spinner"></span>
          Compare {{ selectedIds.length > 0 ? '('+selectedIds.length+' papers)' : '' }}
        </button>
        <p v-if="selectedIds.length < 2" class="text-muted text-sm mt-8">Select at least 2 papers.</p>
      </div>
    </div>

    <div v-if="result" class="card">
      <div class="flex items-center gap-8" style="margin-bottom:12px">
        <div class="card-title" style="margin:0;flex:1">Comparison</div>
        <button class="btn btn-secondary btn-sm" @click="exportMd">⬇ Export MD</button>
      </div>
      <div style="white-space:pre-wrap;line-height:1.7">{{ result.comparison }}</div>

      <hr class="divider" />
      <div class="text-sm text-muted">
        <strong>Papers compared:</strong>
        <ul style="margin-top:4px;padding-left:20px">
          <li v-for="p in result.papers" :key="p.paper_id">
            {{ p.title }} ({{ p.year }}) — {{ (p.authors||[]).slice(0,2).join(', ') }}
          </li>
        </ul>
      </div>
    </div>
  </template>
</div>
`,
})
```

**Step 2: Commit**

```bash
git add frontend-web/index.html
git commit -m "feat: add Compare tab to Vue frontend"
```

---

## Task 10: GitHub Actions Deployment Workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

**Step 1: Create the workflow directory and file**

```bash
mkdir -p .github/workflows
```

**Step 2: Create `.github/workflows/deploy.yml`**

```yaml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - 'frontend-web/**'
      - '.github/workflows/deploy.yml'

  workflow_dispatch:   # allow manual trigger from GitHub UI

permissions:
  contents: write      # needed to push to gh-pages branch

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./frontend-web
          publish_branch: gh-pages
          force_orphan: true          # gh-pages branch has no history
          enable_jekyll: false        # .nojekyll is already there; belt + suspenders
          commit_message: "deploy: update frontend from ${{ github.sha }}"
```

**Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Actions workflow to deploy frontend-web/ to gh-pages"
```

---

## Task 11: End-to-End Verification

**Step 1: Run the backend locally**

```bash
docker compose up -d
```

**Step 2: Open the frontend in a browser**

```bash
open frontend-web/index.html
```

**Step 3: Verify each tab**

- [ ] Sidebar shows green dots for backend / Qdrant / Ollama
- [ ] PDF Management: upload a PDF, directory appears, convert button works
- [ ] Collections: create a collection, it appears in the list and sidebar picker
- [ ] RAG Query: select collection, enter query, get answer and passages
- [ ] Explore Paper: select collection, click a paper, see metadata
- [ ] Compare: select 2+ papers, get comparison

**Step 4: Test the settings modal**

- Click ⚙ Settings
- Change URL to `http://localhost:9999` → status shows red "Not reachable"
- Change back to `http://localhost:8000` → status shows green "Connected"
- Close modal — sidebar dots update

**Step 5: Final commit if any tweaks were made**

```bash
git add frontend-web/index.html
git commit -m "fix: final adjustments after e2e verification"
```

---

## GitHub Pages Setup Instructions (Separate)

> These steps require GitHub UI access and are provided separately from the code changes.

```
1. Push this branch (10-make-independent-front-end) or merge to main.
   The workflow triggers on pushes to main with changes to frontend-web/.

2. On GitHub → repo → Settings → Pages:
   - Source: "Deploy from a branch"
   - Branch: gh-pages / root
   - Save

3. After the first workflow run (check Actions tab), the site will be live at:
   https://<your-github-username>.github.io/<repo-name>/

4. Update backend/app/main.py CORS with the real URL:
   "https://<your-github-username>.github.io"

5. Rebuild and restart the backend:
   docker compose up backend --build -d
```
