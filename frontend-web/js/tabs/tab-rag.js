import { defineComponent, ref, computed, watch } from 'vue'
import { api, downloadBlob } from '../backend-client.js'
import { PromptSelector } from '../components/shared/prompt-selector.js'

const RagTab = defineComponent({
  name: 'RagTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],
  components: { PromptSelector },

  setup(props) {
    const error        = ref(null)
    const loading      = ref(false)
    const query        = ref('')
    const topK         = ref(10)
    const maxTokens    = ref(500)
    const result       = ref(null)
    const papers       = ref([])
    const selectedIds  = ref([])
    const showFilters    = ref(false)
    const showAdvanced   = ref(false)
    const showPassages   = ref(false)
    const showCitations  = ref(false)
    const selectedPrompt = ref('default')
    const citationMode = ref('apa')
    const filterSearch = ref('')
    const filterDir    = ref('all')

    const collectionId = computed(() => props.selectedCollection)
    const collection   = computed(() => props.collections.find(c => c.collection_id === collectionId.value))
    const useHybrid    = computed(() => collection.value?.search_type === 'hybrid')

    const allDirs = computed(() => [...new Set(papers.value.map(p => p.preprocessed_dir).filter(Boolean))])

    const filteredPapers = computed(() => {
      const q = filterSearch.value.toLowerCase()
      return papers.value.filter(p => {
        if (filterDir.value !== 'all' && p.preprocessed_dir !== filterDir.value) return false
        if (q) {
          const label = (p.title || p.filename || p.paper_id).toLowerCase()
          if (!label.includes(q) && !(p.preprocessed_dir || '').toLowerCase().includes(q)) return false
        }
        return true
      })
    })

    function checkAll()   { const extra = filteredPapers.value.map(p => p.paper_id).filter(id => !selectedIds.value.includes(id)); selectedIds.value = [...selectedIds.value, ...extra] }
    function uncheckAll() { const rm = new Set(filteredPapers.value.map(p => p.paper_id)); selectedIds.value = selectedIds.value.filter(id => !rm.has(id)) }

    watch(collectionId, async (id) => {
      papers.value = []
      selectedIds.value = []
      result.value = null
      filterSearch.value = ''
      filterDir.value = 'all'
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
      showPassages.value = false
      showCitations.value = false
      try {
        const body = {
          query_text: query.value.trim(),
          limit: topK.value,
          max_tokens: maxTokens.value,
          include_citations: true,
          use_hybrid: useHybrid.value,
          prompt_name: selectedPrompt.value,
        }
        if (selectedIds.value.length) body.paper_ids = selectedIds.value
        result.value = await api.post(`/collections/${collectionId.value}/rag`, body)
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function togglePassage(r) { r._open = !r._open }

    function pdfUrl(citation) {
      if (!citation.pdf_url) return null
      return `${api.url()}${citation.pdf_url}`
    }

    function exportInteraction() {
      if (!result.value) return
      const now = new Date()
      const ts = now.toISOString().slice(0, 16).replace('T', '-').replace(':', '-')
      const filename = `rag-${collectionId.value}-${ts}.json`
      const payload = {
        timestamp: now.toISOString(),
        collection_id: collectionId.value,
        llm_provider: result.value.llm_provider,
        llm_model: result.value.llm_model,
        query: query.value,
        rendered_prompt: result.value.rendered_prompt || {},
        answer: result.value.answer,
        retrieved_chunks: result.value.results || [],
        citations: result.value.citations || {},
      }
      downloadBlob(
        new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }),
        filename,
      )
    }

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

    function renderMd(text, citations) {
      let html = window.marked ? window.marked.parse(text) : text
      if (citations) {
        html = html.replace(/\[([^\]]+)\]/g, (match, key) => {
          const cit = citations[key]
          if (cit?.pdf_url) {
            return `<a href="${api.url()}${cit.pdf_url}" target="_blank" rel="noopener">${match}</a>`
          }
          return match
        })
      }
      return html
    }

    return {
      error, loading, query, topK, maxTokens,
      result, papers, selectedIds, showFilters, citationMode,
      collectionId, useHybrid,
      filterSearch, filterDir, allDirs, filteredPapers,
      checkAll, uncheckAll,
      runQuery, togglePassage, exportMd, exportInteraction, pdfUrl,
      showAdvanced, selectedPrompt, renderMd,
      showPassages, showCitations,
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

        <div v-if="showFilters" style="margin-top:8px">
          <div v-if="papers.length === 0" class="text-muted text-sm" style="padding:8px 0">No papers in this collection.</div>
          <template v-else>
            <!-- Filters row -->
            <div class="picker-filters">
              <select v-if="allDirs.length > 1" v-model="filterDir">
                <option value="all">All folders</option>
                <option v-for="d in allDirs" :key="d" :value="d">{{ d }}</option>
              </select>
              <input type="text" v-model="filterSearch" placeholder="Search papers…" />
            </div>
            <!-- Bulk actions -->
            <div class="flex items-center gap-8" style="margin-bottom:8px">
              <button class="btn btn-secondary btn-sm" @click="checkAll">Check all</button>
              <button class="btn btn-secondary btn-sm" @click="uncheckAll">Uncheck all</button>
              <span class="text-muted text-sm" style="margin-left:auto">
                {{ selectedIds.length }} selected · {{ filteredPapers.length }} shown
              </span>
            </div>
            <!-- Scrollable list -->
            <div class="picker-list">
              <div v-if="filteredPapers.length === 0" class="text-muted text-sm" style="padding:12px 14px">
                No papers match the filter.
              </div>
              <label v-for="p in filteredPapers" :key="p.paper_id" class="picker-row">
                <input type="checkbox" :value="p.paper_id" v-model="selectedIds" />
                <span class="picker-row-name">
                  <span v-if="p.preprocessed_dir" class="picker-dir-tag">{{ p.preprocessed_dir }}/</span>{{ p.title || p.filename || p.paper_id }}
                </span>
              </label>
            </div>
          </template>
        </div>
      </div>

      <!-- Advanced options -->
      <div style="margin-top:12px">
        <button class="btn btn-secondary btn-sm" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '▲' : '▼' }} Advanced options
        </button>
        <div v-show="showAdvanced" style="margin-top:10px;padding:12px;border:1px solid var(--border);border-radius:6px">
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
          <hr style="border:none;border-top:1px solid var(--border);margin:12px 0" />
          <prompt-selector :task-type="'rag'" v-model="selectedPrompt" />
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
          <span v-if="result.llm_model" style="font-size:11px;font-weight:600;color:#fff;background:#22c55e;padding:2px 8px;border-radius:12px;margin-right:4px">{{ result.llm_model }}</span>
          <button class="btn btn-secondary btn-sm" @click="exportMd">⬇ Export MD</button>
          <button class="btn btn-secondary btn-sm" @click="exportInteraction">⬇ Export Interaction</button>
        </div>
        <div class="markdown-body" v-html="renderMd(result.answer, result.citations)"></div>
      </div>

      <!-- Retrieved passages -->
      <div class="card" v-if="result.results && result.results.length">
        <div class="card-title" style="cursor:pointer;user-select:none" @click="showPassages=!showPassages">
          <span class="chevron" :class="{open:showPassages}" style="margin-right:6px">▶</span>
          Retrieved passages
          <span class="badge badge-gray" style="margin-left:6px">{{ result.results.length }}</span>
        </div>
        <div v-if="showPassages" v-for="(r, i) in result.results" :key="i" class="collapsible">
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
        <div class="flex items-center gap-8" style="margin-bottom:12px;cursor:pointer;user-select:none" @click="showCitations=!showCitations">
          <div class="card-title" style="margin:0;flex:1">
            <span class="chevron" :class="{open:showCitations}" style="margin-right:6px">▶</span>
            Citations
            <span class="badge badge-gray" style="margin-left:6px">{{ Object.keys(result.citations).length }}</span>
          </div>
          <template v-if="showCitations">
            <button class="btn btn-secondary btn-sm"
                    :style="citationMode==='apa' ? 'border-color:var(--primary);color:var(--primary)' : ''"
                    @click.stop="citationMode='apa'">APA</button>
            <button class="btn btn-secondary btn-sm"
                    :style="citationMode==='bibtex' ? 'border-color:var(--primary);color:var(--primary)' : ''"
                    @click.stop="citationMode='bibtex'">BibTeX</button>
          </template>
        </div>
        <template v-if="showCitations">
          <div v-for="(c, key) in result.citations" :key="key" class="citation-box" style="margin-bottom:10px">
            <div class="flex items-center gap-8" style="margin-bottom:4px">
              <div style="font-weight:600;font-size:12px;flex:1">{{ c.unique_id }}</div>
              <a v-if="pdfUrl(c)" :href="pdfUrl(c)" target="_blank" rel="noopener"
                 class="btn btn-secondary btn-sm" style="font-size:11px;padding:2px 8px">📄 PDF</a>
            </div>
            <pre v-if="citationMode==='bibtex'" style="font-size:11px">{{ c.bibtex }}</pre>
            <p v-else style="font-size:13px;line-height:1.5">{{ c.apa }}</p>
          </div>
        </template>
      </div>
    </template>
  </template>
</div>
`,
})

export { RagTab }
