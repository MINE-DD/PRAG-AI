import { defineComponent, ref, reactive, computed, watch, onMounted } from 'vue'
import { api } from '../backend-client.js'
import { FilePickerPanel } from '../components/collections/file-picker-panel.js'

const CollectionsTab = defineComponent({
  name: 'CollectionsTab',
  components: { FilePickerPanel },
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection', 'refresh-collections'],

  setup(props, { emit }) {
    const error          = ref(null)
    const creating       = ref(false)
    const deleting       = reactive({})
    const newForm        = reactive({ name: '', search_type: 'hybrid', ingestDir: '',
                                      chunkSize: 2000, chunkOverlap: 0, chunkMode: 'markdown-academic' })
    const createMsg             = ref(null)
    const ingestErrors          = ref([])
    const ingestProgress        = reactive({ current: 0, total: 0 })
    const showAdvanced          = ref(false)
    const pickerCollId          = ref(null)
    const convertedDirs         = ref([])   // [{name, files:[{mdName}]}]
    const loadingDirs           = ref(false)
    const embeddingModel        = ref('')
    const embeddingContextLen   = ref(null)  // tokens; null = unknown
    const chunkSizeWarning      = ref(null)

    async function loadEmbeddingInfo() {
      try {
        const cfg = await api.get('/settings')
        embeddingModel.value      = cfg.embedding_model      || ''
        embeddingContextLen.value = cfg.embedding_context_length ?? null
      } catch { /* non-critical */ }
    }

    // Max chunk size in the units used by the current mode:
    //   tokens mode  → context window in tokens
    //   chars/markdown → context window × 4 chars/token (conservative estimate)
    const maxChunkSize = computed(() => {
      if (!embeddingContextLen.value) return 4000
      return newForm.chunkMode === 'tokens'
        ? embeddingContextLen.value
        : embeddingContextLen.value * 4
    })

    async function loadConvertedDirs() {
      loadingDirs.value = true
      try {
        const dirs = await api.get('/preprocess/directories')
        const result = []
        for (const dir of dirs) {
          if (dir.pdf_count === 0) continue
          try {
            const res = await api.post('/preprocess/scan', { dir_name: dir.name })
            const converted = res.files
              .filter(f => f.processed)
              .map(f => ({ mdName: f.filename.replace(/\.pdf$/i, '.md') }))
            if (converted.length > 0) result.push({ name: dir.name, files: converted })
          } catch { /* skip */ }
        }
        convertedDirs.value = result
      } catch { /* ignore — not critical */ }
      finally { loadingDirs.value = false }
    }

    function extractDetail(msg) {
      try {
        const j = msg.slice(msg.indexOf('{'))
        return JSON.parse(j).detail || msg
      } catch { return msg }
    }

    async function createCollection() {
      if (!newForm.name.trim()) { error.value = 'Collection name is required.'; return }
      creating.value   = true
      error.value      = null
      createMsg.value  = null
      ingestErrors.value = []
      try {
        const coll = await api.post('/collections', {
          name:        newForm.name.trim(),
          search_type: newForm.search_type,
        })
        const collId = coll.collection_id

        if (newForm.ingestDir) {
          const dir = convertedDirs.value.find(d => d.name === newForm.ingestDir)
          const files = dir?.files ?? []
          let ok = 0
          const errors = []
          ingestProgress.current = 0
          ingestProgress.total   = files.length
          for (const f of files) {
            try {
              await api.post(`/ingest/${collId}/file`, {
                markdown_file: f.mdName,
                dir_name:      newForm.ingestDir,
                chunk_size:    newForm.chunkSize,
                chunk_overlap: newForm.chunkOverlap,
                chunk_mode:    newForm.chunkMode,
              })
              ok++
            } catch (e) { errors.push({ file: f.mdName, message: extractDetail(e.message) }) }
            ingestProgress.current++
          }
          if (errors.length === 0) {
            createMsg.value = `Created and ingested ${ok} file(s) from "${newForm.ingestDir}".`
          } else {
            createMsg.value = `Ingested ${ok}/${ok + errors.length} file(s).`
            ingestErrors.value = errors
          }
        } else {
          createMsg.value = 'Collection created. Use "+ Add files" to ingest papers.'
        }

        Object.assign(newForm, { name: '', search_type: 'hybrid', ingestDir: '',
                                 chunkSize: 2000, chunkOverlap: 0, chunkMode: 'markdown-academic' })
        emit('refresh-collections')
      } catch (e) { error.value = e.message }
      finally { creating.value = false }
    }

    async function deleteCollection(id) {
      if (!confirm(`Delete collection "${id}"? This cannot be undone.`)) return
      deleting[id] = true
      error.value  = null
      try {
        await api.del(`/collections/${id}`)
        if (props.selectedCollection === id) emit('update:collection', '')
        if (pickerCollId.value === id) pickerCollId.value = null
        emit('refresh-collections')
      } catch (e) { error.value = e.message }
      finally { delete deleting[id] }
    }

    function togglePicker(collId) {
      pickerCollId.value = pickerCollId.value === collId ? null : collId
    }

    // Default char/markdown chunk size scales with the embedder's context window:
    // 2 chars/token (conservative floor), rounded to 100, capped at 2000.
    // Examples: 512 → 1000, 768 → 1500, 1024+ → 2000.
    const defaultCharSize = computed(() => {
      if (!embeddingContextLen.value) return 2000
      return Math.min(2000, Math.floor(embeddingContextLen.value * 2 / 100) * 100)
    })

    const CHUNK_DEFAULTS = computed(() => ({
      tokens:              { size: 500,                   overlap: 100 },
      characters:          { size: defaultCharSize.value, overlap: 200 },
      'markdown-academic': { size: defaultCharSize.value, overlap: 0   },
    }))

    watch(() => newForm.chunkMode, mode => {
      const d = CHUNK_DEFAULTS.value[mode]
      if (d) { newForm.chunkSize = d.size; newForm.chunkOverlap = d.overlap }
    })

    // When the embedder context length loads, update the form to the appropriate default.
    watch(embeddingContextLen, () => {
      const d = CHUNK_DEFAULTS.value[newForm.chunkMode]
      if (d) newForm.chunkSize = d.size
    })

    watch(() => newForm.chunkSize, size => {
      const max = maxChunkSize.value
      if (!embeddingContextLen.value || size <= max) {
        chunkSizeWarning.value = null
        return
      }
      const unit = newForm.chunkMode === 'tokens' ? 'tokens' : 'chars'
      chunkSizeWarning.value =
        `Exceeds ${embeddingModel.value || 'embedder'} context window ` +
        `(${embeddingContextLen.value} tokens ≈ ${embeddingContextLen.value * 4} chars). ` +
        `Clamped to ${max} ${unit}.`
      newForm.chunkSize = max
    })

    onMounted(() => { loadConvertedDirs(); loadEmbeddingInfo() })

    return {
      error, creating, deleting, newForm, createMsg, ingestErrors, ingestProgress,
      showAdvanced, pickerCollId, convertedDirs, loadingDirs, embeddingContextLen,
      maxChunkSize, chunkSizeWarning, createCollection, deleteCollection, togglePicker,
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
      <div class="form-group" style="margin:0;flex:1">
        <label>Collection name *</label>
        <input type="text" v-model="newForm.name" placeholder="Mini NLP" />
        <div v-if="newForm.name.trim()" class="text-sm text-muted" style="margin-top:3px">
          ID: <code>{{ newForm.name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') }}</code>
        </div>
      </div>
      <div class="form-group" style="margin:0;flex:1">
        <label>
          Ingest from directory
          <span v-if="loadingDirs" class="spinner" style="width:10px;height:10px;border-width:2px;margin-left:4px"></span>
        </label>
        <select v-model="newForm.ingestDir" :disabled="loadingDirs">
          <option value="">— none (empty collection) —</option>
          <option v-for="d in convertedDirs" :key="d.name" :value="d.name">
            {{ d.name }} ({{ d.files.length }} converted file{{ d.files.length !== 1 ? 's' : '' }})
          </option>
        </select>
        <div v-if="!loadingDirs && convertedDirs.length === 0" class="text-muted text-sm" style="margin-top:4px">
          No converted files found — convert PDFs first.
        </div>
      </div>
    </div>

    <!-- Advanced settings -->
    <div style="margin-top:10px">
      <button type="button" class="btn btn-secondary btn-sm"
              @click="showAdvanced = !showAdvanced"
              style="font-size:12px;color:var(--text-muted)">
        <span :style="showAdvanced ? 'display:inline-block;transform:rotate(90deg)' : ''">▶</span>
        Advanced settings
      </button>
    </div>
    <div v-if="showAdvanced" class="form-row" style="margin-top:8px">
      <div class="form-group" style="margin:0">
        <label>Chunk mode</label>
        <select v-model="newForm.chunkMode">
          <option value="tokens">Tokens (approx)</option>
          <option value="characters">Characters</option>
          <option value="markdown-academic">Markdown (Academic Papers)</option>
        </select>
      </div>
      <template v-if="newForm.chunkMode !== 'markdown-academic'">
        <div class="form-group" style="margin:0">
          <label>Chunk size</label>
          <input type="number" v-model.number="newForm.chunkSize" min="50" :max="maxChunkSize" step="50" />
          <div v-if="chunkSizeWarning" class="text-sm" style="color:var(--warning,#b45309);margin-top:3px">
            ⚠ {{ chunkSizeWarning }}
          </div>
        </div>
        <div class="form-group" style="margin:0">
          <label>Chunk overlap</label>
          <input type="number" v-model.number="newForm.chunkOverlap" min="0" max="500" step="10" />
        </div>
      </template>
      <div v-else class="form-group" style="margin:0">
        <label>Max paragraph size (chars)</label>
        <input type="number" v-model.number="newForm.chunkSize" min="100" :max="maxChunkSize" step="100" />
        <div v-if="chunkSizeWarning" class="text-sm" style="color:var(--warning,#b45309);margin-top:3px">
          ⚠ {{ chunkSizeWarning }}
        </div>
      </div>
      <div class="form-group" style="margin:0">
        <label>Search type</label>
        <select v-model="newForm.search_type">
          <option value="dense">Dense (vector only)</option>
          <option value="hybrid">Hybrid (vector + BM42)</option>
        </select>
      </div>
    </div>

    <div class="mt-16">
      <div v-if="newForm.ingestDir && embeddingContextLen && newForm.chunkMode !== 'tokens'"
           style="margin-bottom:8px;padding:6px 10px;background:var(--info-bg,#eff6ff);border:1px solid var(--info-border,#bfdbfe);border-radius:4px;font-size:12px;color:var(--info-text,#1d4ed8)">
        ℹ The current embedder model max length is {{ embeddingContextLen }} tokens.
        Chunks exceeding this will be automatically truncated.
        Use the advanced settings to select <strong>Tokens mode</strong> and control the limit.
      </div>
      <div class="flex gap-8 items-center">
        <button class="btn btn-primary" :disabled="creating" @click="createCollection">
          <span v-if="creating" class="spinner"></span>
          <span>{{ creating ? (newForm.ingestDir ? 'Creating & ingesting…' : 'Creating…') : (newForm.ingestDir ? 'Create & Ingest' : 'Create') }}</span>
        </button>
        <span v-if="createMsg" class="text-sm" :style="ingestErrors.length ? 'color:var(--warning,#b45309)' : 'color:var(--success)'">{{ createMsg }}</span>
      </div>
      <div v-if="ingestErrors.length > 0" style="margin-top:10px;border:1px solid var(--warning,#b45309);border-radius:4px;overflow:hidden">
        <div style="background:var(--warning-bg,#fffbeb);padding:6px 10px;font-size:12px;font-weight:600;color:var(--warning,#b45309)">
          {{ ingestErrors.length }} file{{ ingestErrors.length !== 1 ? 's' : '' }} failed to ingest
        </div>
        <div v-for="e in ingestErrors" :key="e.file"
             style="padding:5px 10px;font-size:12px;border-top:1px solid var(--border);display:flex;gap:8px;align-items:baseline">
          <span style="font-family:monospace;color:var(--text-muted);flex-shrink:0">{{ e.file }}</span>
          <span style="color:var(--error,#dc2626)">{{ e.message }}</span>
        </div>
      </div>
      <div v-if="creating && ingestProgress.total > 0" style="margin-top:10px">
        <div class="text-sm text-muted" style="margin-bottom:4px">
          Ingesting {{ ingestProgress.current }} / {{ ingestProgress.total }} files…
        </div>
        <div style="background:var(--border,#e5e7eb);border-radius:4px;height:6px;overflow:hidden">
          <div :style="{
            width: (ingestProgress.current / ingestProgress.total * 100) + '%',
            background: 'var(--primary,#2563eb)',
            height: '100%',
            transition: 'width 0.3s ease',
          }"></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Existing collections -->
  <h2 style="font-size:15px;font-weight:600;margin-bottom:12px">
    Existing collections ({{ collections.length }})
  </h2>

  <div v-if="collections.length === 0" class="empty-state">
    <div style="font-size:32px">📚</div>
    <p>No collections yet. Create one above.</p>
  </div>

  <div v-for="col in collections" :key="col.collection_id" class="card">
    <!-- Header row -->
    <div class="flex items-center gap-8">
      <div style="flex:1">
        <div style="font-weight:600;font-size:15px">{{ col.name || col.collection_id }}</div>
        <div class="text-sm text-muted" style="margin-top:2px">
          <code class="font-mono" style="font-size:11px">{{ col.collection_id }}</code>
          &nbsp;·&nbsp;
          <span class="badge badge-blue">{{ col.search_type }}</span>
          &nbsp;·&nbsp;
          {{ col.paper_count ?? '?' }} paper{{ col.paper_count !== 1 ? 's' : '' }}
        </div>
      </div>
      <button class="btn btn-secondary btn-sm"
              @click="$emit('update:collection', col.collection_id)">
        {{ selectedCollection === col.collection_id ? '✓ Active' : 'Select' }}
      </button>
      <button class="btn btn-secondary btn-sm" @click="togglePicker(col.collection_id)">
        {{ pickerCollId === col.collection_id ? '✕ Close' : '+ Add files' }}
      </button>
      <button class="btn btn-danger btn-sm"
              :disabled="!!deleting[col.collection_id]"
              @click="deleteCollection(col.collection_id)">
        <span v-if="deleting[col.collection_id]" class="spinner"></span>
        <span v-else>Delete</span>
      </button>
    </div>

    <!-- File picker panel -->
    <div v-if="pickerCollId === col.collection_id" class="picker-panel">
      <file-picker-panel :collection-id="col.collection_id"
                         @ingest-complete="$emit('refresh-collections')" />
    </div>
  </div>
</div>
`,
})

export { CollectionsTab }
