# PDF Batch Convert & Metadata Display Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Convert All" batch button, per-file expandable metadata panels, and PDF processing settings to the PDF Management tab.

**Architecture:** All changes are frontend-only in `frontend-web/index.html`. No new backend endpoints — existing `/preprocess/convert`, `/preprocess/download/{dir}/{file}/metadata`, and `/preprocess/enrich-metadata` endpoints are reused. Alpine.js-style reactive state is added to the `PdfTab` Vue component; two new localStorage keys (`prag_meta_backend`, `prag_pdf_backend`) are surfaced in the Settings modal (already read by the convert logic, just not editable before).

**Tech Stack:** Vue 3 (CDN, Composition API), single HTML file, localStorage, existing FastAPI backend.

---

## Chunk 1: Settings Modal — PDF Processing Section

### Task 1: Add pdfBackend and metaBackend to settingsForm

**Files:**
- Modify: `frontend-web/index.html:1632-1647` (settingsForm reactive declaration)
- Modify: `frontend-web/index.html:1732-1761` (saveSettings function)
- Modify: `frontend-web/index.html:1703-1730` (openSettings function — reset form fields on open)

- [ ] **Step 1: Add the two fields to `settingsForm`**

Find this block in `index.html` (around line 1632):
```js
const settingsForm = reactive({
  backendUrl:       localStorage.getItem('prag_backend_url')       || 'http://localhost:8000',
  preprocessedBase: localStorage.getItem('prag_preprocessed_dir') || '/data/preprocessed',
  embeddingModel: '',
  llmModel:       '',
  // Cloud LLM
  llmProvider:      'local',
  ...
})
```

Add two new fields at the top, after `preprocessedBase`:
```js
  metaBackend:      localStorage.getItem('prag_meta_backend')      || 'openalex',
  pdfBackend:       localStorage.getItem('prag_pdf_backend')        || 'pymupdf',
```

- [ ] **Step 2: Save the two fields in `saveSettings()`**

In `saveSettings()` (around line 1734), after the two existing `localStorage.setItem` calls, add:
```js
localStorage.setItem('prag_meta_backend', settingsForm.metaBackend)
localStorage.setItem('prag_pdf_backend',  settingsForm.pdfBackend)
```

- [ ] **Step 3: Reset the two fields in `openSettings()`**

In `openSettings()` (around line 1703), after `showSettings.value = true`, add the two resets so that if a user cancels and reopens, they see the last-saved values (not stale reactive state):
```js
settingsForm.metaBackend = localStorage.getItem('prag_meta_backend') || 'openalex'
settingsForm.pdfBackend  = localStorage.getItem('prag_pdf_backend')  || 'pymupdf'
```

- [ ] **Step 4: Verify in browser**

Open Settings. The two new dropdowns won't be visible yet (template not added), but confirm no JS errors in the console.

- [ ] **Step 5: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add pdfBackend and metaBackend to settingsForm state"
```

---

### Task 2: Add "PDF Processing" section to Settings modal HTML

**Files:**
- Modify: `frontend-web/index.html:458-462` (modal footer — insert new section before it)

- [ ] **Step 1: Add the PDF Processing section**

Find the modal footer (around line 458):
```html
      <div class="modal-footer">
        <button class="btn btn-secondary" @click="showSettings = false">Cancel</button>
        <button class="btn btn-primary" @click="saveSettings">Save & connect</button>
      </div>
```

Insert a `<hr>` and new section immediately before the `<div class="modal-footer">`:
```html
      <hr class="divider" />

      <!-- PDF Processing -->
      <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px">PDF Processing</div>
      <div class="form-group">
        <label>Metadata provider</label>
        <select v-model="settingsForm.metaBackend">
          <option value="openalex">OpenAlex (default)</option>
          <option value="crossref">CrossRef</option>
          <option value="semantic_scholar">Semantic Scholar</option>
          <option value="none">None (skip enrichment)</option>
        </select>
      </div>
      <div class="form-group">
        <label>PDF conversion backend</label>
        <select v-model="settingsForm.pdfBackend">
          <option value="pymupdf">PyMuPDF (fast)</option>
          <option value="docling">Docling (thorough, slow)</option>
        </select>
      </div>

```

- [ ] **Step 2: Verify in browser**

Open Settings → scroll to bottom → confirm "PDF Processing" section with two dropdowns renders. Change a value, click Save & Connect, reopen Settings → confirm value persists.

- [ ] **Step 3: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add PDF Processing section to Settings modal"
```

---

## Chunk 2: Convert All Button

### Task 3: Add convertAll state and logic to PdfTab

**Files:**
- Modify: `frontend-web/index.html:537-634` (PdfTab setup function)

- [ ] **Step 1: Add `convertingAllMap` reactive to PdfTab setup**

In `PdfTab` setup (around line 542), after `const deletingDir = reactive({})` (line 607), add:
```js
const convertingAllMap = reactive({})
// Structure per dir: { active: false, current: 0, total: 0, failed: 0 }
```

- [ ] **Step 2: Add `convertAll` function**

After the `deleteDir` function (around line 621), add:
```js
async function convertAll(dirName) {
  const files = (dirFiles[dirName] || []).filter(f => !f.processed)
  if (!files.length) return
  convertingAllMap[dirName] = { active: true, current: 0, total: files.length, failed: 0 }
  for (const file of files) {
    convertingAllMap[dirName].current++
    const key = `${dirName}/${file.filename}`
    converting[key] = true
    try {
      await api.post('/preprocess/convert', {
        dir_name: dirName,
        filename: file.filename,
        backend: localStorage.getItem('prag_pdf_backend') || 'pymupdf',
        metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
      })
      await loadFiles(dirName)
    } catch (e) {
      convertingAllMap[dirName].failed++
      console.error(`Convert failed for ${file.filename}:`, e.message)
    } finally {
      delete converting[key]
    }
  }
  convertingAllMap[dirName].active = false
}
```

- [ ] **Step 3: Add `hasUnconverted` helper function**

After `convertAll`, add:
```js
function hasUnconverted(dirName) {
  return (dirFiles[dirName] || []).some(f => !f.processed)
}
```

- [ ] **Step 4: Expose new state/functions in return statement**

In the PdfTab `return` object (around line 629), add `convertingAllMap`, `convertAll`, and `hasUnconverted`:
```js
return {
  error, directories, loading, uploadDir,
  converting, expanded, dirFiles, deletingDir,
  convertingAllMap,
  loadDirs, uploadFiles, convertFile, deleteFile, deleteDir, toggleDir,
  convertAll, hasUnconverted,
}
```

- [ ] **Step 5: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add convertAll logic and state to PdfTab"
```

---

### Task 4: Add Convert All button to folder header template

**Files:**
- Modify: `frontend-web/index.html:671-687` (directory header in PdfTab template)

- [ ] **Step 1: Add the Convert All button to the folder header**

Find the folder header in the PdfTab template (around line 679):
```html
      <span class="flex items-center gap-8">
        <button class="btn btn-danger btn-sm" @click.stop="deleteDir(dir.name)"
                :disabled="!!deletingDir[dir.name]">
          <span v-if="deletingDir[dir.name]" class="spinner"></span>
          <span v-else>Delete folder</span>
        </button>
        <span class="chevron" :class="{open: expanded[dir.name]}">▶</span>
      </span>
```

Replace with:
```html
      <span class="flex items-center gap-8">
        <template v-if="expanded[dir.name] && hasUnconverted(dir.name)">
          <span v-if="convertingAllMap[dir.name] && convertingAllMap[dir.name].active"
                class="text-sm text-muted">
            Converting {{ convertingAllMap[dir.name].current }}/{{ convertingAllMap[dir.name].total }}…
          </span>
          <button v-else class="btn btn-sm"
                  style="background:var(--success);color:#fff;border-color:var(--success)"
                  @click.stop="convertAll(dir.name)">
            Convert All
          </button>
        </template>
        <span v-if="convertingAllMap[dir.name] && !convertingAllMap[dir.name].active && convertingAllMap[dir.name].failed > 0"
              class="text-sm" style="color:var(--warning)">
          {{ convertingAllMap[dir.name].failed }} failed
        </span>
        <button class="btn btn-danger btn-sm" @click.stop="deleteDir(dir.name)"
                :disabled="!!deletingDir[dir.name]">
          <span v-if="deletingDir[dir.name]" class="spinner"></span>
          <span v-else>Delete folder</span>
        </button>
        <span class="chevron" :class="{open: expanded[dir.name]}">▶</span>
      </span>
```

- [ ] **Step 2: Verify in browser**

- Expand a folder with unconverted PDFs → green "Convert All" button appears
- Click it → progress counter shows "Converting 1/N…", spinner on current file row
- After completion → button disappears (all converted), any failures show warning
- Folders where all files are already converted → no Convert All button

- [ ] **Step 3: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add Convert All button to folder header with progress feedback"
```

---

## Chunk 3: Metadata Detail Panel

### Task 5: Add metadata panel state and logic to PdfTab

**Files:**
- Modify: `frontend-web/index.html:537-634` (PdfTab setup function)

- [ ] **Step 1: Add `expandedFiles` and `fileMetadata` reactive objects**

In PdfTab setup, after `const convertingAllMap = reactive({})`, add:
```js
const expandedFiles = reactive({})   // key: "dirName/filename" → true/false
const fileMetadata  = reactive({})   // key: "dirName/filename" → null|object|'error'
```

- [ ] **Step 2: Add `toggleFileMeta` function**

After `convertAll`, add:
```js
async function toggleFileMeta(dirName, filename) {
  const key = `${dirName}/${filename}`
  expandedFiles[key] = !expandedFiles[key]
  if (expandedFiles[key] && fileMetadata[key] === undefined) {
    fileMetadata[key] = null  // loading
    try {
      const encDir  = encodeURIComponent(dirName)
      const encFile = encodeURIComponent(filename)
      fileMetadata[key] = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
    } catch (e) {
      // 404 = not converted yet; anything else = server error
      fileMetadata[key] = e.message.startsWith('404') ? 'not_converted' : 'error'
    }
  }
}
```

- [ ] **Step 3: Add `reenrichFile` state and function**

After `toggleFileMeta`, add:
```js
const reenrichState = reactive({})
// key: "dirName/filename" → { open: false, selected: '', confirming: false, loading: false }

function openReenrich(dirName, filename) {
  const key = `${dirName}/${filename}`
  reenrichState[key] = { open: true, selected: '', confirming: false, loading: false }
}

function selectReenrichProvider(dirName, filename, provider) {
  const key = `${dirName}/${filename}`
  reenrichState[key].selected = provider
  reenrichState[key].confirming = true
}

function cancelReenrich(dirName, filename) {
  const key = `${dirName}/${filename}`
  reenrichState[key] = { open: false, selected: '', confirming: false, loading: false }
}

async function confirmReenrich(dirName, filename) {
  const key = `${dirName}/${filename}`
  const provider = reenrichState[key].selected
  reenrichState[key].loading = true
  try {
    await api.post('/preprocess/enrich-metadata', {
      dir_name: dirName,
      filename,
      backend: provider,
    })
    // Reload metadata
    const encDir  = encodeURIComponent(dirName)
    const encFile = encodeURIComponent(filename)
    fileMetadata[key] = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
  } catch (e) {
    error.value = `Re-enrich failed: ${e.message}`
  } finally {
    reenrichState[key] = { open: false, selected: '', confirming: false, loading: false }
  }
}
```

- [ ] **Step 4: Add helper to extract year from publication_date**

After the other helpers, add:
```js
function extractYear(dateStr) {
  if (!dateStr) return null
  const m = String(dateStr).match(/\d{4}/)
  return m ? m[0] : null
}
```

- [ ] **Step 5: Expose all new state/functions in return**

Update the return statement:
```js
return {
  error, directories, loading, uploadDir,
  converting, expanded, dirFiles, deletingDir,
  convertingAllMap,
  expandedFiles, fileMetadata, reenrichState,
  loadDirs, uploadFiles, convertFile, deleteFile, deleteDir, toggleDir,
  convertAll, hasUnconverted,
  toggleFileMeta, openReenrich, selectReenrichProvider, cancelReenrich, confirmReenrich,
  extractYear,
}
```

- [ ] **Step 6: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add metadata panel state and re-enrich logic to PdfTab"
```

---

### Task 6: Add metadata panel CSS

**Files:**
- Modify: `frontend-web/index.html` (style block, add near `.file-item` styles)

- [ ] **Step 1: Locate `.file-item` CSS and add panel styles after it**

Search for `.file-item` in the `<style>` block and add the following after it:
```css
    .file-meta-panel { background: var(--bg); border-top: 1px solid var(--border);
                       padding: 12px 16px 14px; font-size: 13px; }
    .file-meta-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; line-height: 1.4; }
    .file-meta-row   { display: flex; gap: 6px; align-items: baseline; margin-bottom: 3px;
                       font-size: 12px; color: var(--muted); }
    .file-meta-row strong { color: var(--text); font-weight: 500; }
    .badge-source    { display: inline-block; padding: 1px 7px; border-radius: 10px;
                       font-size: 11px; font-weight: 500; background: #eff6ff; color: #1d4ed8; }
```

- [ ] **Step 2: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add CSS for file metadata panel"
```

---

### Task 7: Add metadata panel to file row template

**Files:**
- Modify: `frontend-web/index.html:695-716` (file row in PdfTab template)

- [ ] **Step 1: Add chevron toggle and metadata panel to file row**

Find the file row in the PdfTab template:
```html
      <div v-for="file in (dirFiles[dir.name] || [])" :key="file.filename" class="file-item">
        <div>
          <div class="file-name">{{ file.filename }}</div>
          <div class="file-meta">
            <span v-if="file.processed" class="badge badge-green">Converted</span>
            <span v-else class="badge badge-gray">Not converted</span>
          </div>
        </div>
        <div class="flex gap-8">
          <button class="btn btn-secondary btn-sm"
                  :disabled="!!converting[dir.name+'/'+file.filename]"
                  @click="convertFile(dir.name, file.filename)">
            <span v-if="converting[dir.name+'/'+file.filename]" class="spinner"></span>
            <span v-else>Convert</span>
          </button>
          <button class="btn btn-danger btn-sm"
                  :disabled="!!converting[dir.name+'/'+file.filename]"
                  @click="deleteFile(dir.name, file.filename)">
            Delete
          </button>
        </div>
      </div>
```

Replace with:
```html
      <div v-for="file in (dirFiles[dir.name] || [])" :key="file.filename"
           style="border:1px solid var(--border);border-radius:6px;margin-bottom:6px;overflow:hidden">
        <!-- File row -->
        <div class="file-item" style="border:none;margin:0">
          <div style="display:flex;align-items:center;gap:8px">
            <button class="btn btn-secondary btn-sm"
                    style="padding:2px 6px;font-size:12px;min-width:20px"
                    @click="toggleFileMeta(dir.name, file.filename)">
              <span :style="expandedFiles[dir.name+'/'+file.filename] ? 'display:inline-block;transform:rotate(90deg)' : ''">▶</span>
            </button>
            <div>
              <div class="file-name">{{ file.filename }}</div>
              <div class="file-meta">
                <span v-if="file.processed" class="badge badge-green">Converted</span>
                <span v-else class="badge badge-gray">Not converted</span>
              </div>
            </div>
          </div>
          <div class="flex gap-8">
            <button class="btn btn-secondary btn-sm"
                    :disabled="!!converting[dir.name+'/'+file.filename]"
                    @click="convertFile(dir.name, file.filename)">
              <span v-if="converting[dir.name+'/'+file.filename]" class="spinner"></span>
              <span v-else>Convert</span>
            </button>
            <button class="btn btn-danger btn-sm"
                    :disabled="!!converting[dir.name+'/'+file.filename]"
                    @click="deleteFile(dir.name, file.filename)">
              Delete
            </button>
          </div>
        </div>

        <!-- Metadata panel -->
        <div v-if="expandedFiles[dir.name+'/'+file.filename]" class="file-meta-panel">
          <!-- Loading -->
          <div v-if="fileMetadata[dir.name+'/'+file.filename] === null"
               class="flex items-center gap-8">
            <span class="spinner"></span>
            <span class="text-muted text-sm">Loading metadata…</span>
          </div>
          <!-- Not converted -->
          <div v-else-if="fileMetadata[dir.name+'/'+file.filename] === 'not_converted'"
               class="text-muted text-sm">
            Not converted yet — convert the file to see metadata.
          </div>
          <!-- Server error -->
          <div v-else-if="fileMetadata[dir.name+'/'+file.filename] === 'error'"
               class="text-sm" style="color:var(--danger)">
            Could not load metadata — check the backend connection.
          </div>
          <!-- Metadata -->
          <template v-else-if="fileMetadata[dir.name+'/'+file.filename]">
            <div class="file-meta-title">
              {{ fileMetadata[dir.name+'/'+file.filename].title || file.filename }}
            </div>
            <div class="file-meta-row" v-if="(fileMetadata[dir.name+'/'+file.filename].authors || []).length">
              <strong>Authors:</strong>
              {{ (fileMetadata[dir.name+'/'+file.filename].authors || []).join(', ') }}
            </div>
            <div class="file-meta-row">
              <template v-if="extractYear(fileMetadata[dir.name+'/'+file.filename].publication_date)">
                <strong>Year:</strong>
                {{ extractYear(fileMetadata[dir.name+'/'+file.filename].publication_date) }}
              </template>
              <template v-if="fileMetadata[dir.name+'/'+file.filename].journal">
                &nbsp;·&nbsp; <strong>Journal:</strong>
                {{ fileMetadata[dir.name+'/'+file.filename].journal }}
              </template>
            </div>
            <div class="file-meta-row" v-if="fileMetadata[dir.name+'/'+file.filename].doi">
              <strong>DOI:</strong>
              <a :href="'https://doi.org/' + fileMetadata[dir.name+'/'+file.filename].doi"
                 target="_blank" style="color:var(--primary)">
                {{ fileMetadata[dir.name+'/'+file.filename].doi }}
              </a>
            </div>
            <div class="file-meta-row">
              <span class="badge-source">
                {{ fileMetadata[dir.name+'/'+file.filename].metadata_source || 'None' }}
              </span>
            </div>

            <!-- Re-enrich -->
            <div style="margin-top:10px">
              <template v-if="!reenrichState[dir.name+'/'+file.filename] || !reenrichState[dir.name+'/'+file.filename].open">
                <button class="btn btn-secondary btn-sm"
                        @click="openReenrich(dir.name, file.filename)">
                  Re-enrich metadata
                </button>
              </template>
              <template v-else-if="reenrichState[dir.name+'/'+file.filename].confirming">
                <span class="text-sm" style="margin-right:8px">
                  Re-enrich with <strong>{{ reenrichState[dir.name+'/'+file.filename].selected }}</strong>?
                </span>
                <button class="btn btn-secondary btn-sm" @click="cancelReenrich(dir.name, file.filename)">
                  Cancel
                </button>
                <button class="btn btn-primary btn-sm" style="margin-left:6px"
                        :disabled="reenrichState[dir.name+'/'+file.filename].loading"
                        @click="confirmReenrich(dir.name, file.filename)">
                  <span v-if="reenrichState[dir.name+'/'+file.filename].loading" class="spinner"></span>
                  <span v-else>Confirm</span>
                </button>
              </template>
              <template v-else>
                <div class="flex gap-8">
                  <button class="btn btn-secondary btn-sm"
                          @click="selectReenrichProvider(dir.name, file.filename, 'openalex')">
                    OpenAlex
                  </button>
                  <button class="btn btn-secondary btn-sm"
                          @click="selectReenrichProvider(dir.name, file.filename, 'crossref')">
                    CrossRef
                  </button>
                  <button class="btn btn-secondary btn-sm"
                          @click="selectReenrichProvider(dir.name, file.filename, 'semantic_scholar')">
                    Semantic Scholar
                  </button>
                  <button class="btn btn-secondary btn-sm"
                          @click="cancelReenrich(dir.name, file.filename)">
                    ✕
                  </button>
                </div>
              </template>
            </div>
          </template>
        </div>
      </div>
```

- [ ] **Step 2: Verify in browser**

- Expand a folder → each file row has a ▶ chevron button
- Click ▶ on unconverted file → panel shows "Not converted yet"
- Click ▶ on converted file → panel loads and shows title, authors, year, DOI, source badge
- Click "Re-enrich metadata" → three provider buttons appear
- Click a provider → confirm step appears with Cancel / Confirm
- Click Confirm → loading spinner, then panel refreshes with new metadata
- Click Cancel → returns to "Re-enrich metadata" button

- [ ] **Step 3: Commit**
```bash
git add frontend-web/index.html
git commit -m "feat: add expandable metadata panel to PDF file rows"
```

---

## Final Verification

- [ ] Open Settings → scroll to bottom → "PDF Processing" section with Metadata provider and PDF backend dropdowns
- [ ] Change metadata provider to CrossRef → Save → reopen Settings → CrossRef is selected
- [ ] Expand a folder with multiple unconverted PDFs → green "Convert All" button visible
- [ ] Click Convert All → progress counter in header, spinner on active file, sequential conversion
- [ ] After all converted → Convert All button disappears
- [ ] Click ▶ on a converted file → metadata panel expands with title/authors/year/DOI/source
- [ ] Re-enrich flow works end-to-end (open → pick provider → confirm → metadata refreshes)
- [ ] No console errors
