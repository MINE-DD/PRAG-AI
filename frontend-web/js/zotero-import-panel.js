import { defineComponent, ref, reactive, computed, onMounted } from 'vue'
import { api } from './api.js'
import { PipelinePanel } from './pipeline-panel.js'

const ZoteroImportPanel = defineComponent({
  name: 'ZoteroImportPanel',
  components: { PipelinePanel },
  emits: ['refresh-dirs', 'refresh-collections', 'open-collection', 'close'],

  setup(props, { emit }) {
    const ztCollections   = ref([])
    const ztCollError     = ref(null)
    const ztSelCollection = ref(null)
    const ztItems         = ref([])
    const ztItemsLoading  = ref(false)
    const ztItemsError    = ref(null)
    const ztChecked       = reactive({})
    const ztDirName       = ref('')
    const ztImporting     = ref(false)
    const ztProgress      = reactive({})
    const ztDone          = ref(false)
    const ztImportError   = ref(null)
    const ztPipelineDir   = ref('')   // set after import; holds dirName_zt

    const ztCollectionSlug = computed(() =>
      ztDirName.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    )

    async function load() {
      ztCollections.value   = []
      ztCollError.value     = null
      ztSelCollection.value = null
      ztItems.value         = []
      ztDone.value          = false
      ztImportError.value   = null
      ztPipelineDir.value   = ''
      Object.keys(ztChecked).forEach(k => delete ztChecked[k])
      Object.keys(ztProgress).forEach(k => delete ztProgress[k])
      try {
        ztCollections.value = await api.get('/zotero/collections')
      } catch (e) {
        ztCollError.value = e.message
      }
    }

    async function selectCollection(collKey, collName) {
      ztSelCollection.value = { key: collKey, name: collName }
      ztDirName.value       = collName.toLowerCase().replace(/\s+/g, '_')
      ztItems.value         = []
      ztItemsError.value    = null
      ztItemsLoading.value  = true
      Object.keys(ztChecked).forEach(k => delete ztChecked[k])
      try {
        const items = await api.get(`/zotero/collections/${collKey}/items`)
        ztItems.value = items
        for (const item of items) {
          if (item.attachment?.type === 'cloud') ztChecked[item.item_key] = true
        }
      } catch (e) {
        ztItemsError.value = e.message
      } finally {
        ztItemsLoading.value = false
      }
    }

    async function runImport() {
      const selectedKeys = Object.entries(ztChecked).filter(([, v]) => v).map(([k]) => k)
      if (!selectedKeys.length) return
      ztImporting.value   = true
      ztDone.value        = false
      ztImportError.value = null
      Object.keys(ztProgress).forEach(k => delete ztProgress[k])
      try {
        const resp = await fetch(`${api.url()}/zotero/import`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            collection_key: ztSelCollection.value.key,
            dir_name:       ztDirName.value,
            item_keys:      selectedKeys,
          }),
        })
        const reader  = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            const data = JSON.parse(line.slice(6))
            if (data.done) { ztDone.value = true; break }
            if (data.filename) ztProgress[data.filename] = { status: data.status, message: data.message }
          }
        }
      } catch (e) {
        ztImportError.value = e.message
      } finally {
        ztImporting.value = false
        if (ztDone.value) {
          emit('refresh-dirs')
          ztPipelineDir.value = ztDirName.value + '_zt'
        }
      }
    }

    onMounted(load)

    return {
      ztCollections, ztCollError, ztSelCollection,
      ztItems, ztItemsLoading, ztItemsError,
      ztChecked, ztDirName, ztImporting, ztProgress, ztDone, ztImportError,
      ztPipelineDir, ztCollectionSlug,
      selectCollection, runImport,
    }
  },

  template: `
<div class="card" style="margin-bottom:8px">
  <div v-if="ztCollError" class="alert alert-error">
    {{ ztCollError }}
    <span v-if="ztCollError.includes('not configured')"> — Go to Settings to add your Zotero credentials.</span>
  </div>

  <div v-else-if="ztCollections.length === 0" class="text-muted text-sm">Loading collections…</div>

  <div v-else>
    <h3 class="page-title">PDF Files</h3>
    <div class="form-group">
      <label>Collection</label>
      <select class="form-control"
              @change="e => selectCollection(e.target.value, ztCollections.find(c=>c.key===e.target.value)?.name || '')">
        <option value="">— select a collection —</option>
        <option v-for="c in ztCollections" :key="c.key" :value="c.key">{{ c.name }}</option>
      </select>
    </div>

    <div v-if="ztItemsLoading" class="text-muted text-sm">Loading papers…</div>
    <div v-else-if="ztItemsError" class="alert alert-error">{{ ztItemsError }}</div>
    <div v-else-if="ztItems.length">
      <div style="max-height:260px;overflow-y:auto;margin:8px 0;border:1px solid var(--border);border-radius:4px">
        <label v-for="item in ztItems" :key="item.item_key"
               :style="item.attachment.type === 'linked'
                 ? 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;opacity:.5;cursor:default'
                 : 'display:flex;align-items:flex-start;gap:8px;padding:8px 12px;cursor:pointer'">
          <input type="checkbox"
                 :disabled="item.attachment.type === 'linked'"
                 :checked="!!ztChecked[item.item_key]"
                 @change="e => ztChecked[item.item_key] = e.target.checked"
                 style="margin-top:2px" />
          <div>
            <div style="font-size:13px;font-weight:500">{{ item.title }}</div>
            <div style="font-size:11px;color:var(--text-muted)">
              {{ (item.authors || []).slice(0,2).join(', ') }}
              <span v-if="(item.authors||[]).length > 2"> et al.</span>
              <span v-if="item.year"> · {{ item.year }}</span>
            </div>
            <div v-if="item.attachment.type === 'linked'"
                 style="font-size:11px;color:var(--warning);margin-top:2px">
              ⚠ Linked file — upload manually from <code>{{ item.attachment.path }}</code>
            </div>
            <div v-if="ztProgress[item.attachment.filename]" style="font-size:11px;margin-top:2px">
              <span v-if="ztProgress[item.attachment.filename].status === 'downloading'">
                <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> Downloading…
              </span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'done'"
                    style="color:var(--success)">✓ Imported</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'skipped'"
                    style="color:var(--success)">✓ Skipped (already imported)</span>
              <span v-else-if="ztProgress[item.attachment.filename].status === 'error'"
                    style="color:var(--danger)">✗ {{ ztProgress[item.attachment.filename].message }}</span>
            </div>
          </div>
        </label>
      </div>

      <div class="form-group" style="margin-bottom:8px">
        <label>Directory name
          <span style="font-size:11px;color:var(--text-muted)"> (<code>_zt</code> will be appended)</span>
        </label>
        <input v-model="ztDirName" class="form-control" placeholder="collection_name" />
      </div>

      <div v-if="ztImportError" class="alert alert-error" style="margin-bottom:8px">{{ ztImportError }}</div>

      <button class="btn btn-primary"
              :disabled="ztImporting || !ztDirName.trim() || !Object.values(ztChecked).some(Boolean)"
              @click="runImport">
        <span v-if="ztImporting"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Importing…</span>
        <span v-else>Import selected</span>
      </button>

      <div v-if="ztDone">
        <div style="color:var(--success);font-size:13px;margin-top:8px;margin-bottom:12px">✓ Import complete.</div>
        <pipeline-panel v-if="ztPipelineDir"
                        :dir-name="ztPipelineDir"
                        :initial-collection-name="ztCollectionSlug"
                        @refresh-collections="$emit('refresh-collections')"
                        @open-collection="id => $emit('open-collection', id)"
                        @dismiss="$emit('close')" />
      </div>
    </div>
  </div>
</div>
`,
})

export { ZoteroImportPanel }
