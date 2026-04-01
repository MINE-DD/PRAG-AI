import { defineComponent, ref, computed, watch } from 'vue'
import { api, downloadBlob } from './api.js'
import { PromptSelector } from './prompt-selector.js'

const CompareTab = defineComponent({
  name: 'CompareTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  components: { PromptSelector },

  setup(props) {
    const error          = ref(null)
    const loading        = ref(false)
    const papers         = ref([])
    const selectedIds    = ref([])
    const aspect         = ref('all')
    const maxTokens      = ref(800)
    const result         = ref(null)
    const filterSearch   = ref('')
    const showAdvanced   = ref(false)
    const selectedPrompt = ref('default')

    const aspects = [
      { value: 'all',           label: 'All aspects' },
      { value: 'methodology',   label: 'Methodology' },
      { value: 'results',       label: 'Results & findings' },
      { value: 'limitations',   label: 'Limitations' },
      { value: 'contributions', label: 'Contributions' },
    ]

    const collectionId = computed(() => props.selectedCollection)

    const filteredPapers = computed(() => {
      const q = filterSearch.value.toLowerCase()
      if (!q) return papers.value
      return papers.value.filter(p =>
        (p.title || p.filename || p.paper_id).toLowerCase().includes(q)
      )
    })

    watch(collectionId, async (id) => {
      papers.value = []
      selectedIds.value = []
      result.value = null
      error.value = null
      if (id) {
        try { papers.value = await api.get(`/collections/${id}/papers`) }
        catch (e) { error.value = e.message }
      }
    }, { immediate: true })

    async function compare() {
      if (selectedIds.value.length < 2) {
        error.value = 'Select at least 2 papers to compare.'
        return
      }
      loading.value = true
      error.value = null
      result.value = null
      try {
        result.value = await api.post(`/collections/${collectionId.value}/compare`, {
          paper_ids: selectedIds.value,
          aspect: aspect.value,
          max_tokens: maxTokens.value,
          prompt_name: selectedPrompt.value,
        })
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function exportMd() {
      if (!result.value) return
      const lines = [
        '# Paper Comparison', '',
        `**Aspect:** ${aspect.value}`, '',
        '## Comparison', '',
        result.value.comparison || '', '',
        '## Papers Compared', '',
        ...(result.value.papers || []).map(p =>
          `- **${p.title}** (${p.year ?? 'n.d.'}) — ${(p.authors || []).join(', ')}`
        ),
      ]
      downloadBlob(new Blob([lines.join('\n')], { type: 'text/markdown' }), 'comparison.md')
    }

    return {
      error, loading, papers, selectedIds, aspect, maxTokens, result, aspects,
      collectionId, compare, exportMd,
      filterSearch, filteredPapers, showAdvanced, selectedPrompt,
    }
  },

  template: `
<div>
  <h2 class="page-title">Compare Papers</h2>
  <p class="page-sub">Ask the LLM to compare multiple papers on a specific aspect.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="!collectionId" class="alert alert-info">
    Select a collection from the sidebar.
  </div>

  <template v-else>
    <div class="card">
      <div class="card-title">Select papers</div>

      <input type="text" v-model="filterSearch" placeholder="Search papers…"
             style="width:100%;margin-bottom:8px" />

      <div style="max-height:220px;overflow-y:auto;border:1px solid var(--border);
                  border-radius:6px;padding:8px 12px;margin-bottom:12px">
        <div v-if="papers.length === 0" class="text-muted text-sm">No papers in this collection.</div>
        <div v-else-if="filteredPapers.length === 0" class="text-muted text-sm">No papers match the search.</div>
        <label v-for="p in filteredPapers" :key="p.paper_id" class="checkbox-label">
          <input type="checkbox" :value="p.paper_id" v-model="selectedIds" />
          {{ p.title || p.filename || p.paper_id }}
        </label>
      </div>

      <div class="text-sm text-muted mb-16">
        {{ selectedIds.length }} paper{{ selectedIds.length !== 1 ? 's' : '' }} selected
      </div>

      <div class="form-group">
        <label>Comparison aspect</label>
        <select v-model="aspect">
          <option v-for="a in aspects" :key="a.value" :value="a.value">{{ a.label }}</option>
        </select>
      </div>

      <!-- Advanced options -->
      <div style="margin-top:4px">
        <button class="btn btn-secondary btn-sm" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '▲' : '▼' }} Advanced options
        </button>
        <div v-show="showAdvanced" style="margin-top:10px;padding:12px;border:1px solid var(--border);border-radius:6px">
          <div class="form-group" style="margin:0">
            <label>Max tokens: {{ maxTokens }}</label>
            <input type="range" v-model.number="maxTokens" min="100" max="2000" step="50"
                   style="width:100%;margin-top:6px" />
          </div>
          <hr style="border:none;border-top:1px solid var(--border);margin:12px 0" />
          <prompt-selector :task-type="'compare'" v-model="selectedPrompt" />
        </div>
      </div>

      <div class="mt-16">
        <button class="btn btn-primary btn-block"
                :disabled="loading || selectedIds.length < 2"
                @click="compare">
          <span v-if="loading" class="spinner"></span>
          <span v-if="loading">Comparing…</span>
          <span v-else-if="selectedIds.length < 2">Select at least 2 papers</span>
          <span v-else>⚖️ Compare {{ selectedIds.length }} papers</span>
        </button>
      </div>
    </div>

    <!-- Result -->
    <div v-if="result" class="card">
      <div class="flex items-center gap-8" style="margin-bottom:14px">
        <div class="card-title" style="margin:0;flex:1">Comparison</div>
        <span v-if="result.llm_model" style="font-size:11px;color:var(--text-muted);margin-right:4px">{{ result.llm_model }}</span>
        <button class="btn btn-secondary btn-sm" @click="exportMd">⬇ Export MD</button>
      </div>

      <div style="white-space:pre-wrap;line-height:1.75">{{ result.comparison }}</div>

      <hr class="divider" />

      <div class="text-sm text-muted">
        <strong>Papers compared:</strong>
        <ul style="margin-top:6px;padding-left:20px">
          <li v-for="p in result.papers" :key="p.paper_id" style="margin-bottom:2px">
            <strong>{{ p.title }}</strong>
            <span v-if="p.year"> ({{ p.year }})</span>
            <span v-if="p.authors && p.authors.length"> — {{ p.authors.slice(0,3).join(', ') }}<span v-if="p.authors.length > 3"> et al.</span></span>
          </li>
        </ul>
      </div>
    </div>
  </template>
</div>
`,
})

export { CompareTab }
