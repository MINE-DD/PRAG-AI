import { defineComponent, ref, reactive, onMounted } from 'vue'
import { api } from '../backend-client.js'
import { FileMetadataPanel } from '../components/pdf/file-metadata-panel.js'
import { UploadPanel }       from '../components/pdf/upload-panel.js'
import { ZoteroImportPanel } from '../components/pdf/zotero-import-panel.js'

const PdfTab = defineComponent({
  name: 'PdfTab',
  components: { FileMetadataPanel, UploadPanel, ZoteroImportPanel },
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],

  setup(props, { emit }) {
    const error      = ref(null)
    const directories = ref([])
    const converting  = reactive({})
    const expanded    = reactive({})
    const dirFiles    = reactive({})
    const deletingDir     = reactive({})
    const convertingAllMap = reactive({})
    const expandedFiles    = reactive({})
    const fileMetadata     = reactive({})

    const showUpload = ref(true)
    const showZotero = ref(false)

    // ── Directory / file loading ──────────────────────────────────────────────

    async function loadDirs() {
      error.value = null
      try {
        directories.value = await api.get('/preprocess/directories')
        for (const dir of directories.value) {
          if (dirFiles[dir.name] === undefined) loadFiles(dir.name)
        }
      } catch (e) { error.value = e.message }
    }

    async function loadFiles(dirName, force = false) {
      if (!force && dirFiles[dirName] !== undefined) return
      dirFiles[dirName] = null
      try {
        const res = await api.post('/preprocess/scan', { dir_name: dirName })
        dirFiles[dirName] = res.files
        await Promise.all(res.files
          .filter(f => f.processed)
          .map(async file => {
            const key = `${dirName}/${file.filename}`
            if (fileMetadata[key] !== undefined) return
            const encDir  = encodeURIComponent(dirName)
            const encFile = encodeURIComponent(file.filename)
            const bust    = force ? `?_=${Date.now()}` : ''
            try {
              fileMetadata[key] = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata${bust}`)
            } catch {
              fileMetadata[key] = 'error'
            }
          })
        )
      } catch (e) { dirFiles[dirName] = []; error.value = e.message }
    }

    async function toggleDir(d) {
      expanded[d] = !expanded[d]
      if (expanded[d] && dirFiles[d] === undefined) await loadFiles(d)
    }

    async function toggleFileMeta(dirName, filename) {
      const key = `${dirName}/${filename}`
      expandedFiles[key] = !expandedFiles[key]
      if (expandedFiles[key] && fileMetadata[key] === undefined) {
        fileMetadata[key] = null
        try {
          const encDir  = encodeURIComponent(dirName)
          const encFile = encodeURIComponent(filename)
          fileMetadata[key] = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
        } catch (e) {
          fileMetadata[key] = e.message.startsWith('404') ? 'not_converted' : 'error'
        }
      }
    }

    function updateMetadata(dirName, filename, newMeta) {
      const key = `${dirName}/${filename}`
      if (newMeta) fileMetadata[key] = newMeta
      else delete fileMetadata[key]
    }

    // ── Conversion ───────────────────────────────────────────────────────────

    async function convertFile(dirName, filename) {
      const key = `${dirName}/${filename}`
      converting[key] = true
      error.value = null
      try {
        await api.post('/preprocess/convert', {
          dir_name:         dirName,
          filename,
          backend:          localStorage.getItem('prag_pdf_backend')    || 'pymupdf',
          metadata_backend: localStorage.getItem('prag_meta_backend')   || 'openalex',
          document_type:    localStorage.getItem('prag_document_type')  || 'default',
        })
        if (fileMetadata[key] !== undefined) delete fileMetadata[key]
        await loadFiles(dirName, true)
      } catch (e) { error.value = e.message }
      finally { delete converting[key] }
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
            dir_name:         dirName,
            filename:         file.filename,
            backend:          localStorage.getItem('prag_pdf_backend')    || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend')   || 'openalex',
            document_type:    localStorage.getItem('prag_document_type')  || 'default',
          })
          const metaKey = `${dirName}/${file.filename}`
          if (metaKey in fileMetadata) delete fileMetadata[metaKey]
          await loadFiles(dirName, true)
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

    // ── Deletion ─────────────────────────────────────────────────────────────

    async function deleteFile(dirName, filename) {
      if (!confirm(`Delete ${filename}?`)) return
      error.value = null
      try {
        await api.post('/preprocess/delete-pdf', { dir_name: dirName, filename })
        await loadFiles(dirName)
        await loadDirs()
        const fileKey = `${dirName}/${filename}`
        delete expandedFiles[fileKey]
        delete fileMetadata[fileKey]
      } catch (e) { error.value = e.message }
    }

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

    // ── Upload / pipeline callbacks ──────────────────────────────────────────

    async function onFilesUploaded() {
      for (const k of Object.keys(dirFiles)) delete dirFiles[k]
      await loadDirs()
    }

    async function onPipelineComplete() {
      for (const k of Object.keys(dirFiles)) delete dirFiles[k]
      await loadDirs()
      emit('refresh-collections')
    }

    function toggleZotero() {
      showZotero.value = !showZotero.value
      if (showZotero.value) showUpload.value = false
    }

    function openCollection(id) { emit('update:collection', id) }

    onMounted(loadDirs)

    return {
      error, directories, converting, expanded, dirFiles,
      deletingDir, convertingAllMap, expandedFiles, fileMetadata,
      showUpload, showZotero,
      loadDirs, toggleDir, toggleFileMeta, updateMetadata,
      convertFile, convertAll, hasUnconverted,
      deleteFile, deleteDir,
      onFilesUploaded, onPipelineComplete, toggleZotero, openCollection,
    }
  },

  template: `
<div>
  <h2 class="page-title">PDF Management</h2>
  <p class="page-sub">Upload and convert PDFs to markdown for ingestion.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Source selector -->
  <div class="flex gap-8" style="margin-bottom:8px">
    <button class="btn" :class="showUpload ? 'btn-primary' : 'btn-secondary'"
            @click="showUpload=!showUpload; showZotero=false">
      ↑ Upload from PC
    </button>
    <button class="btn" :class="showZotero ? 'btn-primary' : 'btn-secondary'"
            @click="toggleZotero">
      Import from Zotero
    </button>
  </div>

  <upload-panel v-if="showUpload"
                @files-uploaded="onFilesUploaded"
                @pipeline-complete="onPipelineComplete"
                @open-collection="openCollection"
                @dismiss="showUpload=false" />

  <zotero-import-panel v-if="showZotero"
                       @refresh-dirs="onFilesUploaded"
                       @refresh-collections="onPipelineComplete"
                       @open-collection="openCollection"
                       @close="showZotero=false" />

  <!-- Directory list -->
  <h2 v-if="directories.length > 0" style="font-size:15px;font-weight:600;margin-bottom:12px">
    Existing Directories ({{ directories.length }})
  </h2>
  <div v-if="directories.length === 0" class="empty-state">
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
          <span v-if="convertingAllMap[dir.name] && convertingAllMap[dir.name].active" class="text-sm text-muted">
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
              <div class="file-name">{{ (fileMetadata[dir.name+'/'+file.filename]?.title || file.filename).split(' ').slice(0,5).join(' ') }}</div>
              <div class="file-meta">
                <span v-if="file.processed" class="badge badge-green">
                  Converted{{ fileMetadata[dir.name+'/'+file.filename]?.backend ? ' with ' + fileMetadata[dir.name+'/'+file.filename].backend : '' }}
                </span>
                <span v-else class="badge badge-gray">Not converted</span>
              </div>
            </div>
          </div>
          <div class="flex gap-8">
            <button class="btn btn-secondary btn-sm"
                    :disabled="!!converting[dir.name+'/'+file.filename]"
                    @click="convertFile(dir.name, file.filename)">
              <span v-if="converting[dir.name+'/'+file.filename]" class="spinner"></span>
              <span v-else>Convert to MD</span>
            </button>
            <button class="btn btn-danger btn-sm"
                    :disabled="!!converting[dir.name+'/'+file.filename]"
                    @click="deleteFile(dir.name, file.filename)">
              Delete
            </button>
          </div>
        </div>

        <!-- Metadata panel component -->
        <file-metadata-panel
          v-if="expandedFiles[dir.name+'/'+file.filename]"
          :dir-name="dir.name"
          :filename="file.filename"
          :metadata="fileMetadata[dir.name+'/'+file.filename]"
          @metadata-updated="updateMetadata(dir.name, file.filename, $event)"
        />
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
