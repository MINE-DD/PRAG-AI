import { defineComponent, ref, computed, watch } from 'vue'
import { api, downloadBlob } from './api.js'

const RagTab = defineComponent({
  name: 'RagTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],

  setup(props) {
    const error        = ref(null)
    const loading      = ref(false)
    const query        = ref('')
    const topK         = ref(10)
    const maxTokens    = ref(500)
    const result       = ref(null)
    const papers       = ref([])
    const selectedIds  = ref([])
    const showFilters  = ref(false)
    const citationMode = ref('apa')

    const collectionId = computed(() => props.selectedCollection)
    const collection   = computed(() => props.collections.find(c => c.collection_id === collectionId.value))
    const useHybrid    = computed(() => collection.value?.search_type === 'hybrid')

    watch(collectionId, async (id) => {
      papers.value = []
      selectedIds.value = []
      result.value = null
      if (id) {
        try { papers.value = await api.get(`/collections/${id}/papers`) }
        catch { papers.value = [] }
      }
    }, { immediate: true })

    async function runQuery() {
      if (!collectionId.value) { error.value = 'Select a collection from the sidebar first.'; return }
      if (!query.value.trim()) { error.value = 'Please enter a question.'; return }
      loading.value = true
      error.value = null
      result.value = null
      try {
        const body = {
          query_text: query.value.trim(),
          limit: topK.value,
          max_tokens: maxTokens.value,
          include_citations: true,
          use_hybrid: useHybrid.value,
        }
        if (selectedIds.value.length) body.paper_ids = selectedIds.value
        result.value = await api.post(`/collections/${collectionId.value}/rag`, body)
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function togglePassage(r) { r._open = !r._open }

    function exportMd() {
      if (!result.value) return
      const lines = [
        '# RAG Export', '',
        `**Query:** ${query.value}`, '',
        '## Answer', '',
        result.value.answer || '(no answer)', '',
        '## Retrieved Passages', '',
      ]
      for (const [i, r] of (result.value.results || []).entries()) {
        lines.push(`### ${i + 1}. ${r.unique_id}`)
        lines.push(`> ${r.chunk_text}`)
        lines.push(`*Page ${r.page_number} · ${r.chunk_type}*`, '')
      }
      lines.push('## Citations', '')
      for (const c of Object.values(result.value.citations || {})) {
        lines.push(`**${c.unique_id}**`, c.apa, '```bibtex', c.bibtex, '```', '')
      }
      downloadBlob(new Blob([lines.join('\n')], { type: 'text/markdown' }), 'rag-export.md')
    }

    return {
      error, loading, query, topK, maxTokens,
      result, papers, selectedIds, showFilters, citationMode,
      collectionId, useHybrid,
      runQuery, togglePassage, exportMd,
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
          <label>Top-K chunks: {{ topK }}</label>
          <input type="range" v-model.number="topK" min="1" max="50" style="width:100%;margin-top:6px" />
        </div>
        <div class="form-group" style="margin:0">
          <label>Max response tokens: {{ maxTokens }}</label>
          <input type="range" v-model.number="maxTokens" min="50" max="2000" step="50" style="width:100%;margin-top:6px" />
        </div>
      </div>

      <div v-if="useHybrid" class="text-sm text-muted mt-8">
        ⚡ Hybrid search enabled for this collection
      </div>

      <!-- Paper filter -->
      <div style="margin-top:12px">
        <button class="btn btn-secondary btn-sm" @click="showFilters = !showFilters">
          {{ showFilters ? '▲' : '▼' }}
          Filter by paper
          <span v-if="selectedIds.length" class="badge badge-blue" style="margin-left:4px">{{ selectedIds.length }}</span>
          <span v-else class="text-muted" style="margin-left:4px;font-weight:400">(all papers)</span>
        </button>

        <div v-if="showFilters" style="margin-top:8px;max-height:180px;overflow-y:auto;
             border:1px solid var(--border);border-radius:6px;padding:8px 12px">
          <div v-if="papers.length === 0" class="text-muted text-sm">No papers in this collection.</div>
          <label v-for="p in papers" :key="p.paper_id" class="checkbox-label">
            <input type="checkbox" :value="p.paper_id" v-model="selectedIds" />
            {{ p.title || p.filename || p.paper_id }}
          </label>
        </div>
      </div>

      <div class="mt-16">
        <button class="btn btn-primary btn-block" :disabled="loading" @click="runQuery">
          <span v-if="loading" class="spinner"></span>
          <span>{{ loading ? 'Searching…' : '🔍 Search' }}</span>
        </button>
      </div>
    </div>

    <!-- Results -->
    <template v-if="result">
      <!-- Answer -->
      <div class="card" v-if="result.answer">
        <div class="flex items-center gap-8" style="margin-bottom:12px">
          <div class="card-title" style="margin:0;flex:1">Answer</div>
          <span v-if="result.llm_model" style="font-size:11px;color:var(--text-muted);margin-right:4px">{{ result.llm_model }}</span>
          <button class="btn btn-secondary btn-sm" @click="exportMd">⬇ Export MD</button>
        </div>
        <div style="line-height:1.75;white-space:pre-wrap">{{ result.answer }}</div>
      </div>

      <!-- Retrieved passages -->
      <div class="card" v-if="result.results && result.results.length">
        <div class="card-title">
          Retrieved passages
          <span class="badge badge-gray" style="margin-left:6px">{{ result.results.length }}</span>
        </div>
        <div v-for="(r, i) in result.results" :key="i" class="collapsible">
          <div class="collapsible-header" @click="togglePassage(r)">
            <span>
              {{ r.unique_id }}
              &nbsp;·&nbsp;p.{{ r.page_number }}
              &nbsp;·&nbsp;<span class="badge badge-gray">{{ r.chunk_type }}</span>
            </span>
            <span class="chevron" :class="{open: r._open}">▶</span>
          </div>
          <div v-if="r._open" class="collapsible-body">
            <p style="line-height:1.6;margin-bottom:8px">{{ r.chunk_text }}</p>
          </div>
        </div>
      </div>

      <!-- Citations -->
      <div class="card" v-if="result.citations && Object.keys(result.citations).length">
        <div class="flex items-center gap-8" style="margin-bottom:12px">
          <div class="card-title" style="margin:0;flex:1">
            Citations
            <span class="badge badge-gray" style="margin-left:6px">{{ Object.keys(result.citations).length }}</span>
          </div>
          <button class="btn btn-secondary btn-sm"
                  :style="citationMode==='apa' ? 'border-color:var(--primary);color:var(--primary)' : ''"
                  @click="citationMode='apa'">APA</button>
          <button class="btn btn-secondary btn-sm"
                  :style="citationMode==='bibtex' ? 'border-color:var(--primary);color:var(--primary)' : ''"
                  @click="citationMode='bibtex'">BibTeX</button>
        </div>
        <div v-for="(c, key) in result.citations" :key="key" class="citation-box" style="margin-bottom:10px">
          <div style="font-weight:600;font-size:12px;margin-bottom:4px">{{ c.unique_id }}</div>
          <pre v-if="citationMode==='bibtex'" style="font-size:11px">{{ c.bibtex }}</pre>
          <p v-else style="font-size:13px;line-height:1.5">{{ c.apa }}</p>
        </div>
      </div>
    </template>
  </template>
</div>
`,
})

export { RagTab }
