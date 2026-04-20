import { defineComponent, ref, reactive } from 'vue'
import { api, downloadBlob } from '../../api.js'

const FileMetadataPanel = defineComponent({
  name: 'FileMetadataPanel',
  props: {
    dirName:  { type: String, required: true },
    filename: { type: String, required: true },
    // Object | null (loading) | 'not_converted' | 'error'
    metadata: { required: true },
  },
  emits: ['metadata-updated'],

  setup(props, { emit }) {
    const editState     = reactive({ editing: false, loading: false, message: '', messageType: '', form: {} })
    const reenrichState = reactive({ open: false, selected: '', confirming: false, loading: false, message: '', messageType: '' })
    const doiLookup     = reactive({ open: false, input: '', loading: false, error: '' })
    const downloadError = ref(null)

    function extractYear(dateStr) {
      if (!dateStr) return null
      const m = String(dateStr).match(/\d{4}/)
      return m ? m[0] : null
    }

    function pdfUrl() {
      return `${api.url()}/preprocess/pdf/${encodeURIComponent(props.dirName)}/${encodeURIComponent(props.filename)}`
    }

    async function downloadMetadata() {
      const encDir  = encodeURIComponent(props.dirName)
      const encFile = encodeURIComponent(props.filename)
      const stem = props.filename.replace(/\.pdf$/i, '')
      try {
        const blob = await api.download(`/preprocess/download/${encDir}/${encFile}/metadata`)
        downloadBlob(blob, `${stem}_metadata.json`)
      } catch (e) { downloadError.value = `Download failed: ${e.message}` }
    }

    async function downloadMarkdown() {
      const encDir  = encodeURIComponent(props.dirName)
      const encFile = encodeURIComponent(props.filename)
      const stem = props.filename.replace(/\.pdf$/i, '')
      try {
        const blob = await api.download(`/preprocess/download/${encDir}/${encFile}/markdown`)
        downloadBlob(blob, `${stem}.md`)
      } catch (e) { downloadError.value = `Download failed: ${e.message}` }
    }

    // ── Re-enrichment ────────────────────────────────────────────────────────

    function openReenrich() {
      Object.assign(reenrichState, { open: true, selected: '', confirming: false, loading: false, message: '', messageType: '' })
    }

    function selectReenrichProvider(provider) {
      reenrichState.selected   = provider
      reenrichState.confirming = true
    }

    function cancelReenrich() {
      Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false })
    }

    async function confirmReenrich() {
      const provider = reenrichState.selected
      reenrichState.loading = true
      try {
        const result = await api.post('/preprocess/enrich-metadata', {
          dir_name: props.dirName,
          filename: props.filename,
          backend:  provider,
        })
        if (!result.enriched) {
          Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false,
            message: `No metadata found with ${provider} — try another provider.`, messageType: 'warn' })
          return
        }
        const encDir  = encodeURIComponent(props.dirName)
        const encFile = encodeURIComponent(props.filename)
        try {
          const newMeta = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
          emit('metadata-updated', newMeta)
          Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false,
            message: `Metadata updated from ${provider}.`, messageType: 'ok' })
        } catch {
          emit('metadata-updated', null)
          Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false,
            message: 'Metadata updated, but failed to reload — click ▶ to refresh.', messageType: 'warn' })
        }
      } catch (e) {
        Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false,
          message: `Failed: ${e.message}`, messageType: 'error' })
      }
    }

    // ── Edit form ────────────────────────────────────────────────────────────

    function startEdit() {
      const meta = props.metadata || {}
      Object.assign(editState, {
        editing: true, loading: false, message: '', messageType: '',
        form: {
          title:    meta.title    || '',
          authors:  (meta.authors || []).join(', '),
          year:     extractYear(meta.publication_date) || '',
          journal:  meta.journal  || '',
          doi:      meta.doi      || '',
          abstract: meta.abstract || '',
        },
      })
    }

    function cancelEdit() { editState.editing = false }

    async function saveEdit() {
      editState.loading = true
      editState.message = ''
      try {
        const body = {
          title:    editState.form.title    || null,
          authors:  editState.form.authors  ? editState.form.authors.split(',').map(a => a.trim()).filter(Boolean) : null,
          year:     editState.form.year     ? parseInt(editState.form.year) : null,
          journal:  editState.form.journal  || null,
          doi:      editState.form.doi      || null,
          abstract: editState.form.abstract || null,
        }
        const encDir  = encodeURIComponent(props.dirName)
        const encFile = encodeURIComponent(props.filename)
        await api.patch(`/preprocess/${encDir}/${encFile}/metadata`, body)
        const updated = { ...(props.metadata || {}) }
        if (body.title    !== null) updated.title            = body.title
        if (body.authors  !== null) updated.authors          = body.authors
        if (body.year     !== null) updated.publication_date = String(body.year)
        if (body.journal  !== null) updated.journal          = body.journal
        if (body.doi      !== null) updated.doi              = body.doi
        if (body.abstract !== null) updated.abstract         = body.abstract
        updated.metadata_source = 'manual'
        emit('metadata-updated', updated)
        editState.editing = false
        Object.assign(reenrichState, { open: false, selected: '', confirming: false, loading: false,
          message: 'Metadata saved manually.', messageType: 'ok' })
      } catch (e) {
        editState.message     = e.message || 'Save failed'
        editState.messageType = 'error'
      } finally {
        editState.loading = false
      }
    }

    // ── DOI lookup ───────────────────────────────────────────────────────────

    const DOI_RE = /^10\.\d{4,}\/\S+$/

    function normalizeDoi(raw) {
      return raw.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '')
    }

    function openDoiLookup()  { Object.assign(doiLookup, { open: true, input: '', loading: false, error: '' }) }
    function closeDoiLookup() { doiLookup.open = false }

    async function fetchByDoi() {
      const doi = normalizeDoi(doiLookup.input)
      if (!DOI_RE.test(doi)) {
        doiLookup.error = 'Invalid DOI format — must start with 10. followed by digits, a slash, and a suffix (e.g. 10.1038/nature14539)'
        return
      }
      doiLookup.error   = ''
      doiLookup.loading = true
      try {
        const result = await api.post('/preprocess/enrich-by-doi', {
          dir_name: props.dirName, filename: props.filename, doi,
        })
        if (!result.enriched) {
          doiLookup.error   = "DOI saved, but no metadata found — the DOI may be incorrect or the paper isn't indexed yet."
          doiLookup.loading = false
          return
        }
        const encDir  = encodeURIComponent(props.dirName)
        const encFile = encodeURIComponent(props.filename)
        const newMeta = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
        emit('metadata-updated', newMeta)
        doiLookup.open = false
      } catch (e) {
        doiLookup.error = e.message
      } finally {
        doiLookup.loading = false
      }
    }

    return {
      editState, reenrichState, doiLookup, downloadError,
      extractYear, pdfUrl, downloadMetadata, downloadMarkdown,
      openReenrich, selectReenrichProvider, cancelReenrich, confirmReenrich,
      startEdit, cancelEdit, saveEdit,
      openDoiLookup, closeDoiLookup, fetchByDoi,
    }
  },

  template: `
<div class="file-meta-panel">
  <div v-if="downloadError" class="text-sm" style="color:var(--danger);margin-bottom:6px">
    {{ downloadError }} <button @click="downloadError=null" style="margin-left:4px">×</button>
  </div>

  <!-- Loading -->
  <div v-if="metadata === null" class="flex items-center gap-8">
    <span class="spinner"></span>
    <span class="text-muted text-sm">Loading metadata…</span>
  </div>

  <!-- Not converted -->
  <div v-else-if="metadata === 'not_converted'" class="text-muted text-sm">
    Not converted yet — convert the file to see metadata.
  </div>

  <!-- Server error -->
  <div v-else-if="metadata === 'error'" class="text-sm" style="color:var(--danger)">
    Could not load metadata — check the backend connection.
  </div>

  <!-- Metadata loaded -->
  <template v-else-if="metadata">

    <!-- Edit form -->
    <template v-if="editState.editing">
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:11px;color:var(--text-muted)">Title</label>
        <input type="text" v-model="editState.form.title" style="width:100%" />
      </div>
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:11px;color:var(--text-muted)">Authors (comma-separated)</label>
        <input type="text" v-model="editState.form.authors" style="width:100%" />
      </div>
      <div style="display:grid;grid-template-columns:80px 1fr;gap:8px;margin-bottom:8px">
        <div>
          <label style="font-size:11px;color:var(--text-muted)">Year</label>
          <input type="number" v-model.number="editState.form.year" style="width:100%" />
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-muted)">Journal / Conference</label>
          <input type="text" v-model="editState.form.journal" style="width:100%" />
        </div>
      </div>
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:11px;color:var(--text-muted)">DOI</label>
        <input type="text" v-model="editState.form.doi" style="width:100%" placeholder="10.xxxx/xxxxx" />
      </div>
      <div class="form-group" style="margin-bottom:8px">
        <label style="font-size:11px;color:var(--text-muted)">Abstract</label>
        <textarea v-model="editState.form.abstract" style="width:100%;height:80px;resize:vertical;box-sizing:border-box"></textarea>
      </div>
      <div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-secondary btn-sm" @click="cancelEdit">Cancel</button>
        <button class="btn btn-primary btn-sm" @click="saveEdit" :disabled="editState.loading">
          <span v-if="editState.loading" class="spinner"></span>
          <span v-else>Save</span>
        </button>
      </div>
      <div v-if="editState.message" class="text-sm" style="margin-top:6px"
           :style="editState.messageType==='ok' ? 'color:var(--success)' : 'color:var(--danger)'">
        {{ editState.message }}
      </div>
    </template>

    <!-- Read-only display -->
    <template v-else>
      <div class="file-meta-title">{{ metadata.title || filename }}</div>
      <div class="file-meta-row"><strong>File:</strong> {{ filename }}</div>
      <div class="file-meta-row" v-if="(metadata.authors || []).length">
        <strong>Authors:</strong> {{ (metadata.authors || []).join(', ') }}
      </div>
      <div class="file-meta-row"
           v-if="extractYear(metadata.publication_date) || metadata.journal">
        <template v-if="extractYear(metadata.publication_date)">
          <strong>Year:</strong> {{ extractYear(metadata.publication_date) }}
        </template>
        <template v-if="metadata.journal">
          &nbsp;·&nbsp; <strong>Journal:</strong> {{ metadata.journal }}
        </template>
      </div>
      <div class="file-meta-row" v-if="metadata.doi">
        <strong>DOI:</strong>
        <a :href="'https://doi.org/' + metadata.doi" target="_blank" rel="noopener noreferrer"
           style="color:var(--primary)">{{ metadata.doi }}</a>
      </div>
      <div class="file-meta-row">
        <span class="badge-source">{{ metadata.metadata_source || 'None' }}</span>
      </div>

      <div style="margin-top:12px;display:flex;flex-direction:column;gap:10px">

        <!-- Metadata actions -->
        <div>
          <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">Metadata</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <template v-if="!reenrichState.open">
              <button class="btn btn-secondary btn-sm" @click="openReenrich">Get Metadata</button>
              <button class="btn btn-secondary btn-sm" @click="openDoiLookup">🔍 Lookup by DOI</button>
              <button class="btn btn-secondary btn-sm" @click="startEdit">✏ Edit</button>
            </template>
            <template v-else-if="reenrichState.confirming">
              <span class="text-sm" style="margin-right:8px">
                Get metadata with <strong>{{ reenrichState.selected }}</strong>?
              </span>
              <button class="btn btn-secondary btn-sm" @click="cancelReenrich">Cancel</button>
              <button class="btn btn-primary btn-sm" style="margin-left:6px"
                      :disabled="reenrichState.loading" @click="confirmReenrich">
                <span v-if="reenrichState.loading" class="spinner"></span>
                <span v-else>Confirm</span>
              </button>
            </template>
            <template v-else>
              <button class="btn btn-secondary btn-sm" @click="selectReenrichProvider('openalex')">OpenAlex</button>
              <button class="btn btn-secondary btn-sm" @click="selectReenrichProvider('crossref')">CrossRef</button>
              <button class="btn btn-secondary btn-sm" @click="selectReenrichProvider('semantic_scholar')">Semantic Scholar</button>
              <button class="btn btn-secondary btn-sm" @click="cancelReenrich">✕</button>
            </template>
          </div>
        </div>

        <!-- Associated files -->
        <div>
          <div style="font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">Associated files</div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <button class="btn btn-secondary btn-sm" @click="downloadMetadata">⬇ metadata.json</button>
            <a class="btn btn-secondary btn-sm" :href="pdfUrl()" target="_blank" rel="noopener">↗ Open PDF</a>
            <button class="btn btn-secondary btn-sm" @click="downloadMarkdown">⬇ markdown</button>
          </div>
        </div>

      </div>

      <div v-if="reenrichState.message" class="text-sm" style="margin-top:6px"
           :style="reenrichState.messageType === 'ok' ? 'color:var(--success)' :
                   reenrichState.messageType === 'error' ? 'color:var(--danger)' : 'color:var(--warning)'">
        {{ reenrichState.message }}
      </div>

      <!-- DOI lookup panel -->
      <div v-if="doiLookup.open"
           style="margin-top:10px;padding:10px;background:var(--bg);border:1px solid var(--border);border-radius:4px">
        <div style="display:flex;gap:8px;align-items:center">
          <input type="text" v-model="doiLookup.input" placeholder="10.1038/nature14539"
                 style="flex:1;font-size:13px" @keyup.enter="fetchByDoi" />
          <button class="btn btn-primary btn-sm"
                  :disabled="doiLookup.loading || !doiLookup.input.trim()" @click="fetchByDoi">
            <span v-if="doiLookup.loading" class="spinner" style="width:10px;height:10px;border-width:2px"></span>
            <span v-else>Fetch</span>
          </button>
          <button class="btn btn-secondary btn-sm" @click="closeDoiLookup">✕</button>
        </div>
        <div v-if="doiLookup.error" class="text-sm" style="margin-top:6px;color:var(--danger)">
          {{ doiLookup.error }}
        </div>
      </div>
    </template>
  </template>
</div>
`,
})

export { FileMetadataPanel }
