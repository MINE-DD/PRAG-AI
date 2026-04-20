import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { api } from '../../api.js'

const FilePickerPanel = defineComponent({
  name: 'FilePickerPanel',
  props: {
    collectionId: { type: String, required: true },
  },
  emits: ['ingest-complete'],

  setup(props, { emit }) {
    const allFiles       = ref([])
    const loadingFiles   = ref(false)
    const error          = ref(null)
    const checked        = reactive({})
    const pickerSearch   = ref('')
    const pickerDir      = ref('all')
    const ingesting      = ref(false)
    const ingestStatuses = reactive({})
    const ingestMsg      = ref(null)

    const allDirs = computed(() => [...new Set(allFiles.value.map(f => f.dirName))])

    const filteredFiles = computed(() => {
      const q = pickerSearch.value.toLowerCase()
      return allFiles.value.filter(f => {
        if (pickerDir.value !== 'all' && f.dirName !== pickerDir.value) return false
        if (q && !f.mdName.toLowerCase().includes(q) && !f.dirName.toLowerCase().includes(q)) return false
        return true
      })
    })

    const checkedCount = computed(() => Object.values(checked).filter(Boolean).length)

    async function loadAllFiles() {
      loadingFiles.value = true
      error.value = null
      try {
        const dirs = await api.get('/preprocess/directories')
        const results = []
        for (const dir of dirs) {
          try {
            const res = await api.post('/preprocess/scan', { dir_name: dir.name })
            for (const f of res.files) {
              if (f.processed) results.push({
                dirName: dir.name,
                mdName:  f.filename.replace(/\.pdf$/i, '.md'),
              })
            }
          } catch { /* skip unreachable dir */ }
        }
        allFiles.value = results
      } catch (e) { error.value = e.message }
      finally { loadingFiles.value = false }
    }

    function checkAll()   { for (const f of filteredFiles.value) checked[f.dirName + '/' + f.mdName] = true }
    function uncheckAll() { for (const key of Object.keys(checked)) checked[key] = false }

    async function ingestSelected() {
      const toIngest = allFiles.value.filter(f => checked[f.dirName + '/' + f.mdName])
      if (!toIngest.length) return
      ingesting.value = true
      ingestMsg.value = null
      let ok = 0, fail = 0
      for (const f of toIngest) {
        const key = f.dirName + '/' + f.mdName
        ingestStatuses[key] = 'pending'
        try {
          await api.post(`/ingest/${props.collectionId}/file`, {
            markdown_file: f.mdName,
            dir_name:      f.dirName,
          })
          ingestStatuses[key] = 'ok'
          checked[key] = false
          ok++
        } catch {
          ingestStatuses[key] = 'error'
          fail++
        }
      }
      ingesting.value = false
      ingestMsg.value = `Done: ${ok} ingested${fail ? `, ${fail} failed` : ''}.`
      emit('ingest-complete', { ok, fail })
    }

    onMounted(loadAllFiles)

    return {
      allFiles, loadingFiles, error, checked, pickerSearch, pickerDir,
      ingesting, ingestStatuses, ingestMsg,
      allDirs, filteredFiles, checkedCount,
      loadAllFiles, checkAll, uncheckAll, ingestSelected,
    }
  },

  template: `
<div>
  <div v-if="error" class="alert alert-error" style="margin-bottom:10px">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="loadingFiles" class="flex items-center gap-8">
    <span class="spinner"></span>
    <span class="text-muted text-sm">Loading converted files…</span>
  </div>

  <div v-else-if="allFiles.length === 0">
    <p class="text-muted text-sm">No converted files found. Convert PDFs in the PDF Management tab first.</p>
    <button class="btn btn-secondary btn-sm" style="margin-top:8px" @click="loadAllFiles">↻ Retry</button>
  </div>

  <template v-else>
    <div class="picker-filters">
      <select v-model="pickerDir">
        <option value="all">All folders</option>
        <option v-for="d in allDirs" :key="d" :value="d">{{ d }}</option>
      </select>
      <input type="text" v-model="pickerSearch" placeholder="Search files…" />
    </div>

    <div class="flex items-center gap-8" style="margin-bottom:8px">
      <button class="btn btn-secondary btn-sm" @click="checkAll"   :disabled="ingesting">Check all</button>
      <button class="btn btn-secondary btn-sm" @click="uncheckAll" :disabled="ingesting">Uncheck all</button>
      <span class="text-muted text-sm" style="margin-left:auto">
        {{ checkedCount }} selected · {{ filteredFiles.length }} shown
      </span>
    </div>

    <div class="picker-list">
      <div v-if="filteredFiles.length === 0" class="text-muted text-sm" style="padding:12px 14px">
        No files match the current filter.
      </div>
      <label v-for="f in filteredFiles" :key="f.dirName+'/'+f.mdName" class="picker-row">
        <input type="checkbox"
               :checked="!!checked[f.dirName+'/'+f.mdName]"
               @change="e => checked[f.dirName+'/'+f.mdName] = e.target.checked"
               :disabled="ingesting" />
        <span class="picker-row-name">
          <span class="picker-dir-tag">{{ f.dirName }}/</span>{{ f.mdName }}
        </span>
        <span class="picker-status">
          <span v-if="ingestStatuses[f.dirName+'/'+f.mdName] === 'pending'" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
          <span v-else-if="ingestStatuses[f.dirName+'/'+f.mdName] === 'ok'"    style="color:var(--success)">✓</span>
          <span v-else-if="ingestStatuses[f.dirName+'/'+f.mdName] === 'error'" style="color:var(--danger)">✗</span>
        </span>
      </label>
    </div>

    <div class="flex items-center gap-8" style="margin-top:12px">
      <button class="btn btn-primary btn-sm"
              :disabled="ingesting || checkedCount === 0"
              @click="ingestSelected">
        <span v-if="ingesting" class="spinner"></span>
        <span>{{ ingesting ? 'Ingesting…' : 'Ingest ' + checkedCount + ' file' + (checkedCount !== 1 ? 's' : '') }}</span>
      </button>
      <button class="btn btn-secondary btn-sm" @click="loadAllFiles" :disabled="loadingFiles || ingesting">
        ↻ Refresh list
      </button>
      <span v-if="ingestMsg" class="text-sm"
            :style="ingestMsg.startsWith('Done') ? 'color:var(--success)' : 'color:var(--danger)'">
        {{ ingestMsg }}
      </span>
    </div>
  </template>
</div>
`,
})

export { FilePickerPanel }
