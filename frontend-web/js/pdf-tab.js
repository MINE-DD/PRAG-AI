import { defineComponent, ref, reactive, onMounted } from 'vue'
import { api, downloadBlob } from './api.js'

const PdfTab = defineComponent({
  name: 'PdfTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],

  setup(props, { emit }) {
    const error       = ref(null)
    const directories = ref([])
    const loading     = ref(false)
    const uploadDir   = ref('')
    const converting  = reactive({})
    const expanded    = reactive({})
    const dirFiles    = reactive({})

    async function loadDirs() {
      error.value = null
      try {
        directories.value = await api.get('/preprocess/directories')
      } catch (e) { error.value = e.message }
    }

    async function loadFiles(dirName) {
      try {
        const res = await api.post('/preprocess/scan', { dir_name: dirName })
        dirFiles[dirName] = res.files
      } catch (e) { dirFiles[dirName] = []; error.value = e.message }
    }

    async function uploadFiles(evt) {
      const files = evt.target.files
      if (!files.length) return
      const dir = uploadDir.value.trim() || 'uploads'
      const fd = new FormData()
      fd.append('dir_name', dir)
      for (const f of files) fd.append('files', f)
      loading.value = true
      error.value = null
      try {
        await api.upload('/preprocess/upload', fd)
        // Clear cached file lists so they reload on next expand
        for (const k of Object.keys(dirFiles)) delete dirFiles[k]
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
          metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
        })
        await loadFiles(dirName)
        // Invalidate cached metadata so panel re-fetches after conversion
        const metaKey = `${dirName}/${filename}`
        if (metaKey in fileMetadata) delete fileMetadata[metaKey]
      } catch (e) { error.value = e.message }
      finally { delete converting[key] }
    }

    async function deleteFile(dirName, filename) {
      if (!confirm(`Delete ${filename}?`)) return
      error.value = null
      try {
        await api.post('/preprocess/delete-pdf', { dir_name: dirName, filename })
        await loadFiles(dirName)
        await loadDirs()
        // Clean up metadata panel state for deleted file
        const fileKey = `${dirName}/${filename}`
        delete expandedFiles[fileKey]
        delete fileMetadata[fileKey]
        delete reenrichState[fileKey]
      } catch (e) { error.value = e.message }
    }

    const deletingDir = reactive({})
    const convertingAllMap = reactive({})
    // Structure per dir: { active: false, current: 0, total: 0, failed: 0 }
    const expandedFiles = reactive({})   // key: "dirName/filename" → true/false
    const fileMetadata  = reactive({})   // key: "dirName/filename" → null|object|'not_converted'|'error'

    async function deleteDir(dirName) {
      if (!confirm(`Delete directory "${dirName}" and all its PDFs?\nThis cannot be undone.`)) return
      deletingDir[dirName] = true
      error.value = null
      try {
        await api.post('/preprocess/delete-directory', { dir_name: dirName })
        delete dirFiles[dirName]
        delete expanded[dirName]
        await loadDirs()
      } catch (e) { error.value = e.message }
      finally { delete deletingDir[dirName] }
    }

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
          // Invalidate cached metadata so panel re-fetches after conversion
          const metaKey = `${dirName}/${file.filename}`
          if (metaKey in fileMetadata) delete fileMetadata[metaKey]
        } catch (e) {
          convertingAllMap[dirName].failed++
          console.error(`Convert failed for ${file.filename}:`, e.message)
        } finally {
          delete converting[key]
        }
      }
      convertingAllMap[dirName].active = false
    }

    function hasUnconverted(dirName) {
      return (dirFiles[dirName] || []).some(f => !f.processed)
    }

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

    const reenrichState = reactive({})
    const editState     = reactive({})
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
        // Step 1: Call enrich endpoint — response tells us if data was found
        const result = await api.post('/preprocess/enrich-metadata', {
          dir_name: dirName,
          filename,
          backend: provider,
        })
        if (!result.enriched) {
          // Show feedback inline in the panel
          reenrichState[key] = { open: false, selected: '', confirming: false, loading: false,
            message: `No metadata found with ${provider} — try another provider.`, messageType: 'warn' }
          return
        }
        // Step 2: Data was found — reload metadata panel
        try {
          const encDir  = encodeURIComponent(dirName)
          const encFile = encodeURIComponent(filename)
          fileMetadata[key] = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
          reenrichState[key] = { open: false, selected: '', confirming: false, loading: false,
            message: `Metadata updated from ${provider}.`, messageType: 'ok' }
        } catch {
          delete fileMetadata[key]
          reenrichState[key] = { open: false, selected: '', confirming: false, loading: false,
            message: 'Metadata updated, but failed to reload — click ▶ to refresh.', messageType: 'warn' }
        }
      } catch (e) {
        reenrichState[key] = { open: false, selected: '', confirming: false, loading: false,
          message: `Failed: ${e.message}`, messageType: 'error' }
      }
    }

    function startEdit(dirName, filename) {
      const key  = `${dirName}/${filename}`
      const meta = fileMetadata[key] || {}
      editState[key] = {
        editing: true, loading: false, message: '', messageType: '',
        form: {
          title:    meta.title    || '',
          authors:  (meta.authors || []).join(', '),
          year:     extractYear(meta.publication_date) || '',
          journal:  meta.journal  || '',
          doi:      meta.doi      || '',
          abstract: meta.abstract || '',
        },
      }
    }

    function cancelEdit(dirName, filename) {
      editState[`${dirName}/${filename}`] = { editing: false }
    }

    async function saveEdit(dirName, filename) {
      const key   = `${dirName}/${filename}`
      const state = editState[key]
      state.loading = true
      state.message = ''
      try {
        const body = {
          title:    state.form.title   || null,
          authors:  state.form.authors ? state.form.authors.split(',').map(a => a.trim()).filter(Boolean) : null,
          year:     state.form.year    ? parseInt(state.form.year) : null,
          journal:  state.form.journal || null,
          doi:      state.form.doi     || null,
          abstract: state.form.abstract || null,
        }
        const encDir  = encodeURIComponent(dirName)
        const encFile = encodeURIComponent(filename)
        await api.patch(`/preprocess/${encDir}/${encFile}/metadata`, body)
        // Update local cache so the read-only view reflects the edit
        if (fileMetadata[key]) {
          if (body.title   !== null) fileMetadata[key].title   = body.title
          if (body.authors !== null) fileMetadata[key].authors = body.authors
          if (body.year    !== null) fileMetadata[key].publication_date = String(body.year)
          if (body.journal !== null) fileMetadata[key].journal = body.journal
          if (body.doi     !== null) fileMetadata[key].doi     = body.doi
          if (body.abstract !== null) fileMetadata[key].abstract = body.abstract
          fileMetadata[key].metadata_source = 'manual'
        }
        editState[key] = { editing: false }
        reenrichState[key] = { open: false, selected: '', confirming: false, loading: false,
          message: 'Metadata saved manually.', messageType: 'ok' }
      } catch (e) {
        state.message     = e.message || 'Save failed'
        state.messageType = 'error'
      } finally {
        state.loading = false
      }
    }

    function pdfUrl(dirName, filename) {
      return `${api.url()}/preprocess/pdf/${encodeURIComponent(dirName)}/${encodeURIComponent(filename)}`
    }

    async function downloadMetadata(dirName, filename) {
      const encDir  = encodeURIComponent(dirName)
      const encFile = encodeURIComponent(filename)
      const stem = filename.replace(/\.pdf$/i, '')
      try {
        const blob = await api.download(`/preprocess/download/${encDir}/${encFile}/metadata`)
        downloadBlob(blob, `${stem}_metadata.json`)
      } catch (e) {
        error.value = `Download failed: ${e.message}`
      }
    }

    function extractYear(dateStr) {
      if (!dateStr) return null
      const m = String(dateStr).match(/\d{4}/)
      return m ? m[0] : null
    }

    async function toggleDir(d) {
      expanded[d] = !expanded[d]
      if (expanded[d] && !dirFiles[d]) await loadFiles(d)
    }

    onMounted(loadDirs)

    return {
      error, directories, loading, uploadDir,
      converting, expanded, dirFiles, deletingDir,
      convertingAllMap,
      expandedFiles, fileMetadata, reenrichState, editState,
      loadDirs, uploadFiles, convertFile, deleteFile, deleteDir, toggleDir,
      convertAll, hasUnconverted,
      toggleFileMeta, openReenrich, selectReenrichProvider, cancelReenrich, confirmReenrich,
      startEdit, cancelEdit, saveEdit,
      downloadMetadata, extractYear, pdfUrl,
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
        <input type="file" accept=".pdf" multiple @change="uploadFiles"
               :disabled="loading" style="font-size:13px;width:100%;padding:6px 0;" />
      </div>
    </div>
    <div v-if="loading" class="flex items-center gap-8 mt-8">
      <span class="spinner"></span>
      <span class="text-muted">Uploading…</span>
    </div>
  </div>

  <!-- Directory list -->
  <div v-if="directories.length === 0 && !loading" class="empty-state">
    <div style="font-size:32px">📂</div>
    <p>No PDFs uploaded yet. Use the form above to get started.</p>
  </div>

  <div v-for="dir in directories" :key="dir.name" class="card" style="padding:0;overflow:hidden">
    <!-- Directory header -->
    <div class="collapsible-header" @click="toggleDir(dir.name)"
         style="background:var(--bg);border-radius:0;padding:10px 20px;">
      <span class="flex items-center gap-8">
        <strong>{{ dir.name }}</strong>
        <span class="badge badge-gray">{{ dir.pdf_count }} file{{ dir.pdf_count !== 1 ? 's' : '' }}</span>
      </span>
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
    </div>

    <div v-if="expanded[dir.name]" style="padding:8px 20px 16px">
      <div v-if="!dirFiles[dir.name]" class="flex items-center gap-8 mt-8">
        <span class="spinner"></span><span class="text-muted">Loading…</span>
      </div>
      <div v-else-if="dirFiles[dir.name].length === 0" class="text-muted text-sm mt-8">No files in this directory.</div>

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

            <!-- Edit form -->
            <template v-if="editState[dir.name+'/'+file.filename]?.editing">
              <div class="form-group" style="margin-bottom:8px">
                <label style="font-size:11px;color:var(--text-muted)">Title</label>
                <input type="text" v-model="editState[dir.name+'/'+file.filename].form.title" style="width:100%" />
              </div>
              <div class="form-group" style="margin-bottom:8px">
                <label style="font-size:11px;color:var(--text-muted)">Authors (comma-separated)</label>
                <input type="text" v-model="editState[dir.name+'/'+file.filename].form.authors" style="width:100%" />
              </div>
              <div style="display:grid;grid-template-columns:80px 1fr;gap:8px;margin-bottom:8px">
                <div>
                  <label style="font-size:11px;color:var(--text-muted)">Year</label>
                  <input type="number" v-model.number="editState[dir.name+'/'+file.filename].form.year" style="width:100%" />
                </div>
                <div>
                  <label style="font-size:11px;color:var(--text-muted)">Journal / Conference</label>
                  <input type="text" v-model="editState[dir.name+'/'+file.filename].form.journal" style="width:100%" />
                </div>
              </div>
              <div class="form-group" style="margin-bottom:8px">
                <label style="font-size:11px;color:var(--text-muted)">DOI</label>
                <input type="text" v-model="editState[dir.name+'/'+file.filename].form.doi" style="width:100%" placeholder="10.xxxx/xxxxx" />
              </div>
              <div class="form-group" style="margin-bottom:8px">
                <label style="font-size:11px;color:var(--text-muted)">Abstract</label>
                <textarea v-model="editState[dir.name+'/'+file.filename].form.abstract" style="width:100%;height:80px;resize:vertical;box-sizing:border-box"></textarea>
              </div>
              <div style="display:flex;gap:8px;margin-top:8px">
                <button class="btn btn-secondary btn-sm" @click="cancelEdit(dir.name, file.filename)">Cancel</button>
                <button class="btn btn-primary btn-sm" @click="saveEdit(dir.name, file.filename)"
                        :disabled="editState[dir.name+'/'+file.filename].loading">
                  <span v-if="editState[dir.name+'/'+file.filename].loading" class="spinner"></span>
                  <span v-else>Save</span>
                </button>
              </div>
              <div v-if="editState[dir.name+'/'+file.filename].message" class="text-sm" style="margin-top:6px"
                   :style="editState[dir.name+'/'+file.filename].messageType==='ok' ? 'color:var(--success)' : 'color:var(--danger)'">
                {{ editState[dir.name+'/'+file.filename].message }}
              </div>
            </template>

            <!-- Read-only display -->
            <template v-else>
            <div class="file-meta-title">
              {{ fileMetadata[dir.name+'/'+file.filename].title || file.filename }}
            </div>
            <div class="file-meta-row" v-if="(fileMetadata[dir.name+'/'+file.filename].authors || []).length">
              <strong>Authors:</strong>
              {{ (fileMetadata[dir.name+'/'+file.filename].authors || []).join(', ') }}
            </div>
            <div class="file-meta-row"
                 v-if="extractYear(fileMetadata[dir.name+'/'+file.filename].publication_date) || fileMetadata[dir.name+'/'+file.filename].journal">
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
                 target="_blank" rel="noopener noreferrer" style="color:var(--primary)">
                {{ fileMetadata[dir.name+'/'+file.filename].doi }}
              </a>
            </div>
            <div class="file-meta-row">
              <span class="badge-source">
                {{ fileMetadata[dir.name+'/'+file.filename].metadata_source || 'None' }}
              </span>
            </div>

            <!-- Get Metadata / Download -->
            <div style="margin-top:10px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <template v-if="!reenrichState[dir.name+'/'+file.filename] || !reenrichState[dir.name+'/'+file.filename].open">
                <button class="btn btn-secondary btn-sm"
                        @click="openReenrich(dir.name, file.filename)">
                  Get Metadata
                </button>
                <button class="btn btn-secondary btn-sm"
                        @click="downloadMetadata(dir.name, file.filename)">
                  ⬇ metadata.json
                </button>
                <a class="btn btn-secondary btn-sm"
                   :href="pdfUrl(dir.name, file.filename)"
                   target="_blank" rel="noopener">
                  ↗ Open PDF
                </a>
                <button class="btn btn-secondary btn-sm"
                        @click="startEdit(dir.name, file.filename)">
                  ✏ Edit
                </button>
              </template>
              <template v-else-if="reenrichState[dir.name+'/'+file.filename].confirming">
                <span class="text-sm" style="margin-right:8px">
                  Get metadata with <strong>{{ reenrichState[dir.name+'/'+file.filename].selected }}</strong>?
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
            <div v-if="reenrichState[dir.name+'/'+file.filename] && reenrichState[dir.name+'/'+file.filename].message"
                 class="text-sm" style="margin-top:6px"
                 :style="reenrichState[dir.name+'/'+file.filename].messageType === 'ok' ? 'color:var(--success)' :
                         reenrichState[dir.name+'/'+file.filename].messageType === 'error' ? 'color:var(--danger)' :
                         'color:var(--warning)'">
              {{ reenrichState[dir.name+'/'+file.filename].message }}
            </div>
            </template><!-- end read-only -->
          </template><!-- end fileMetadata -->
        </div>
      </div>
    </div>
  </div>

  <div v-if="directories.length > 0" class="mt-16">
    <button class="btn btn-secondary" @click="loadDirs">↻ Refresh</button>
  </div>
</div>
`,
})

export { PdfTab }
