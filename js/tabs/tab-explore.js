import { defineComponent, ref, computed, watch } from 'vue'
import { api } from '../backend-client.js'

const ExploreTab = defineComponent({
  name: 'ExploreTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],

  setup(props) {
    const error         = ref(null)
    const papers        = ref([])
    const selected      = ref(null)
    const detail        = ref(null)
    const loading       = ref(false)

    // Summary card
    const summarizing       = ref(false)
    const summaryToc        = ref([])
    const summarySections   = ref([])
    const summaryProgress   = ref('')
    const summaryError      = ref(null)
    const summaryMethod     = ref(null)
    const summaryMaxSent    = ref(3)
    const summaryFormat     = ref('prose')
    const showSummaryAdv    = ref(false)
    const selectedSections  = ref([])
    const summaryPartial    = ref(false)
    let   _summaryAbort     = null

    // Structured abstract card
    const structuredAbstract  = ref(null)
    const generatingAbstract  = ref(false)
    const abstractError       = ref(null)

    // Key contributions card
    const explicitClaims      = ref(null)
    const generatingClaims    = ref(false)
    const claimsError         = ref(null)
    const assessClaims        = ref(null)
    const generatingAssess    = ref(false)
    const assessError         = ref(null)

    function renderMd(text) {
      return window.marked ? window.marked.parse(text) : text
    }

    function summaryTocMd() {
      if (!summaryToc.value.length) return ''
      const lines = summaryToc.value.map(h => '- ' + h).join('\n')
      return '**This paper has ' + summaryToc.value.length + ' sections:**\n\n' + lines + '\n\n---\n\n**Section summaries:**'
    }

    const collectionId = computed(() => props.selectedCollection)

    watch(collectionId, async (id) => {
      papers.value = []
      selected.value = null
      detail.value = null
      error.value = null
      if (id) {
        try {
          papers.value = await api.get(`/collections/${id}/papers`)
          await Promise.all(papers.value.map(async (paper, i) => {
            if (!paper.preprocessed_dir || !paper.source_pdf) return
            try {
              const encDir  = encodeURIComponent(paper.preprocessed_dir)
              const encFile = encodeURIComponent(paper.source_pdf)
              const raw = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
              papers.value[i] = { ...paper, ...raw }
            } catch { /* keep stale data on error */ }
          }))
        } catch (e) { error.value = e.message }
      }
    }, { immediate: true })

    function _resetDerivedCards() {
      structuredAbstract.value = null
      abstractError.value = null
      explicitClaims.value = null
      claimsError.value = null
      assessClaims.value = null
      assessError.value = null
    }

    async function generateSummary() {
      if (!detail.value) return
      if (_summaryAbort) { _summaryAbort.abort(); _summaryAbort = null }
      const ac = new AbortController()
      _summaryAbort = ac
      summarizing.value = true
      summaryToc.value = []
      summarySections.value = []
      summaryProgress.value = ''
      summaryError.value = null
      summaryMethod.value = null
      _resetDerivedCards()

      const allSections = detail.value.sections || []
      summaryPartial.value = allSections.length > 0 && selectedSections.value.length < allSections.length

      let url = api.url() + '/collections/' + collectionId.value + '/papers/' + encodeURIComponent(detail.value.paper_id) + '/summarize/stream?max_sentences=' + summaryMaxSent.value + '&summary_format=' + summaryFormat.value
      if (summaryPartial.value && selectedSections.value.length > 0) {
        url += '&filter_sections=' + encodeURIComponent(selectedSections.value.join(','))
      }

      try {
        const resp = await fetch(url, { signal: ac.signal })
        if (!resp.ok) throw new Error(await resp.text())
        const reader = resp.body.getReader()
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
            let data
            try { data = JSON.parse(line.slice(6)) } catch { continue }
            if (data.type === 'toc') {
              summaryToc.value = data.headings
              summaryMethod.value = data.method
            } else if (data.type === 'section') {
              summarySections.value.push({ heading: data.heading, content: data.content })
              summaryProgress.value = data.index + ' / ' + data.total
            } else if (data.type === 'done') {
              summarizing.value = false
            } else if (data.type === 'error') {
              summaryError.value = data.message
            }
          }
        }
      } catch (e) {
        if (e.name !== 'AbortError') summaryError.value = e.message
      } finally {
        summarizing.value = false
        _summaryAbort = null
      }
    }

    async function selectPaper(paper) {
      if (_summaryAbort) { _summaryAbort.abort(); _summaryAbort = null }
      selected.value = paper
      loading.value = true
      detail.value = null
      error.value = null
      summarizing.value = false
      summaryToc.value = []
      summarySections.value = []
      summaryProgress.value = ''
      summaryError.value = null
      summaryMethod.value = null
      summaryPartial.value = false
      selectedSections.value = []
      _resetDerivedCards()
      try {
        const collectionDetail = await api.get(`/collections/${collectionId.value}/papers/${paper.paper_id}`)
        if (paper.preprocessed_dir && paper.source_pdf) {
          try {
            const encDir  = encodeURIComponent(paper.preprocessed_dir)
            const encFile = encodeURIComponent(paper.source_pdf)
            const rawMeta = await api.get(`/preprocess/download/${encDir}/${encFile}/metadata`)
            detail.value = { ...collectionDetail, ...rawMeta }
          } catch {
            detail.value = collectionDetail
          }
        } else {
          detail.value = collectionDetail
        }
        selectedSections.value = detail.value && detail.value.sections ? [...detail.value.sections] : []
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    function toggleAllSections(checked) {
      selectedSections.value = checked ? [...(detail.value.sections || [])] : []
    }

    function _paperPath(suffix) {
      return '/collections/' + collectionId.value + '/papers/' + encodeURIComponent(detail.value.paper_id) + suffix
    }

    async function generateStructuredAbstract() {
      generatingAbstract.value = true
      abstractError.value = null
      structuredAbstract.value = null
      try {
        const res = await api.post(_paperPath('/structured-abstract'), { summaries: summarySections.value })
        structuredAbstract.value = res.content
      } catch (e) { abstractError.value = e.message }
      finally { generatingAbstract.value = false }
    }

    async function generateExplicitClaims() {
      generatingClaims.value = true
      claimsError.value = null
      explicitClaims.value = null
      try {
        const res = await api.post(_paperPath('/explicit-claims'), { summaries: summarySections.value })
        explicitClaims.value = res.content
      } catch (e) { claimsError.value = e.message }
      finally { generatingClaims.value = false }
    }

    async function generateAssessClaims() {
      generatingAssess.value = true
      assessError.value = null
      assessClaims.value = null
      try {
        const res = await api.post(_paperPath('/assess-claims'), { summaries: summarySections.value })
        assessClaims.value = res.content
      } catch (e) { assessError.value = e.message }
      finally { generatingAssess.value = false }
    }

    const apiBase = api.url()

    return {
      error, papers, selected, detail, loading, collectionId, selectPaper,
      summarizing, summaryToc, summarySections, summaryProgress,
      summaryError, summaryMethod, summaryMaxSent, summaryFormat,
      showSummaryAdv, selectedSections, summaryPartial, toggleAllSections,
      generateSummary, renderMd, summaryTocMd, apiBase,
      structuredAbstract, generatingAbstract, abstractError, generateStructuredAbstract,
      explicitClaims, generatingClaims, claimsError, generateExplicitClaims,
      assessClaims, generatingAssess, assessError, generateAssessClaims,
    }
  },

  template: `
<div>
  <h2 class="page-title">Explore Document</h2>
  <p class="page-sub">Browse and inspect documents in the active collection.</p>

  <div v-if="error" class="alert alert-error">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <div v-if="!collectionId" class="alert alert-info">
    Select a collection from the sidebar.
  </div>

  <template v-else>
    <div style="display:grid;grid-template-columns:280px 1fr;gap:20px;align-items:start">

      <!-- Paper list -->
      <div class="card" style="padding:0;overflow:hidden;position:sticky;top:72px">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);
                    font-weight:600;font-size:13px;background:var(--bg)">
          Papers
          <span class="badge badge-gray" style="margin-left:6px">{{ papers.length }}</span>
        </div>
        <div style="max-height:65vh;overflow-y:auto">
          <div v-if="papers.length === 0" class="text-muted text-sm" style="padding:16px">
            No papers in this collection.
          </div>
          <div v-for="p in papers" :key="p.paper_id"
               style="padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--border);transition:background .1s"
               :style="selected && selected.paper_id === p.paper_id ? 'background:var(--primary);color:#fff' : 'background:var(--card)'"
               @click="selectPaper(p)">
            <div style="font-size:13px;font-weight:500;line-height:1.4">
              {{ p.title || p.filename || p.paper_id }}
            </div>
            <div style="font-size:11px;opacity:.7;margin-top:2px">
              {{ (p.authors || []).slice(0, 2).join(', ') }}
              <span v-if="(p.authors || []).length > 2"> et al.</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Detail panel -->
      <div>
        <div v-if="loading" class="card flex items-center gap-8">
          <span class="spinner"></span>
          <span class="text-muted">Loading paper details…</span>
        </div>

        <template v-else-if="detail">

          <!-- ── Card 1: Paper metadata ── -->
          <div class="card">
            <h3 style="font-size:18px;font-weight:700;line-height:1.4;margin-bottom:8px">
              {{ detail.title || detail.filename }}
            </h3>
            <div class="text-muted text-sm" style="margin-bottom:12px">
              {{ (detail.authors || []).join(', ') }}
              <span v-if="detail.year"> · {{ detail.year }}</span>
              <span v-if="detail.journal"> · <em>{{ detail.journal }}</em></span>
            </div>

            <div v-if="detail.preprocessed_dir && detail.source_pdf" style="margin-bottom:10px">
              <a :href="apiBase + '/preprocess/pdf/' + encodeURIComponent(detail.preprocessed_dir) + '/' + encodeURIComponent(detail.source_pdf)"
                 target="_blank" rel="noopener"
                 style="color:var(--primary);font-size:13px">Open PDF ↗</a>
            </div>

            <div v-if="detail.doi" style="margin-bottom:10px">
              <span class="text-sm text-muted">DOI: </span>
              <a :href="detail.doi.startsWith('http') ? detail.doi : 'https://doi.org/' + detail.doi"
                 target="_blank" rel="noopener"
                 style="color:var(--primary);font-size:13px">{{ detail.doi }}</a>
            </div>

            <div class="flex gap-8" style="flex-wrap:wrap;margin-bottom:12px">
              <span v-if="detail.chunk_count" class="badge badge-gray">{{ detail.chunk_count }} chunks</span>
              <span v-if="detail.metadata_source" class="badge badge-blue">metadata: {{ detail.metadata_source }}</span>
              <span v-if="detail.backend" class="badge badge-yellow">{{ detail.backend }}</span>
            </div>

            <div v-if="detail.abstract" class="collapsible">
              <div class="collapsible-header" @click="detail._showAbstract = !detail._showAbstract">
                Abstract
                <span class="chevron" :class="{open: detail._showAbstract}">▶</span>
              </div>
              <div v-if="detail._showAbstract" class="collapsible-body">
                <p style="line-height:1.7">{{ detail.abstract }}</p>
              </div>
            </div>
          </div>

          <!-- ── Card 2: Section summaries ── -->
          <div class="card" style="margin-top:16px">
            <div style="font-weight:600;font-size:14px;margin-bottom:10px">
              Summary
              <span v-if="summaryMethod" class="badge badge-blue" style="margin-left:6px;font-weight:400">{{ summaryMethod }}</span>
            </div>

            <div v-if="summaryError" class="alert alert-error" style="margin-bottom:8px">{{ summaryError }}</div>

            <div v-if="summaryToc.length" class="markdown-body" style="margin-bottom:16px"
                 v-html="renderMd(summaryTocMd())"></div>

            <div v-for="(s, idx) in summarySections" :key="idx" style="margin-bottom:16px">
              <div class="markdown-body" v-html="renderMd('#### ' + s.heading + '\\n\\n' + s.content)"></div>
            </div>

            <div v-if="summarizing && summaryToc.length" class="flex items-center gap-8" style="margin-bottom:10px">
              <span class="spinner"></span>
              <span class="text-muted text-sm">{{ summaryProgress || '0 / ' + summaryToc.length }} sections summarised</span>
            </div>
            <div v-else-if="summarizing" class="flex items-center gap-8" style="margin-bottom:10px">
              <span class="spinner"></span>
              <span class="text-muted text-sm">Parsing sections…</span>
            </div>

            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px">
              <button class="btn btn-primary btn-sm" @click="generateSummary" :disabled="summarizing">
                {{ summarySections.length ? 'Regenerate' : 'Generate summary' }}
              </button>
              <button class="btn btn-secondary btn-sm" @click="showSummaryAdv = !showSummaryAdv">
                {{ showSummaryAdv ? '▲' : '▼' }} Settings
              </button>
            </div>

            <div v-if="showSummaryAdv" style="padding:12px;border:1px solid var(--border);border-radius:6px">

              <!-- Format -->
              <div style="margin-bottom:12px">
                <div style="font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--text-muted);margin-bottom:6px">FORMAT</div>
                <label style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;cursor:pointer;font-size:13px">
                  <input type="radio" v-model="summaryFormat" value="prose" /> Prose
                </label>
                <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:13px">
                  <input type="radio" v-model="summaryFormat" value="bullets" /> Bullet points
                </label>
              </div>

              <!-- Length -->
              <div style="margin-bottom:12px">
                <div style="font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--text-muted);margin-bottom:6px">LENGTH PER SECTION</div>
                <div style="font-size:13px;margin-bottom:4px">
                  {{ summaryMaxSent }} {{ summaryFormat === 'bullets' ? 'bullet points' : 'sentences' }}
                </div>
                <input type="range" v-model.number="summaryMaxSent" min="1" max="8" step="1" style="width:100%;margin-bottom:4px" />
                <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted)">
                  <span>1 — brief</span><span>4 — balanced</span><span>8 — detailed</span>
                </div>
              </div>

              <!-- Section filter -->
              <div v-if="detail.sections && detail.sections.length">
                <div style="font-size:11px;font-weight:700;letter-spacing:.05em;color:var(--text-muted);margin-bottom:6px">SECTIONS TO INCLUDE</div>
                <label style="display:flex;align-items:center;gap:6px;margin-bottom:6px;font-size:13px;cursor:pointer;font-weight:500">
                  <input type="checkbox"
                         :checked="selectedSections.length === detail.sections.length"
                         :indeterminate="selectedSections.length > 0 && selectedSections.length < detail.sections.length"
                         @change="toggleAllSections($event.target.checked)" />
                  All sections ({{ detail.sections.length }})
                </label>
                <div style="max-height:160px;overflow-y:auto;padding-left:4px">
                  <label v-for="sec in detail.sections" :key="sec"
                         style="display:flex;align-items:flex-start;gap:6px;margin-bottom:4px;font-size:12px;cursor:pointer;line-height:1.4">
                    <input type="checkbox" :value="sec" v-model="selectedSections" style="margin-top:2px;flex-shrink:0" />
                    {{ sec }}
                  </label>
                </div>
              </div>

            </div>
          </div>

          <!-- ── Card 3: Structured abstract ── -->
          <div v-if="!summarizing && summarySections.length" class="card" style="margin-top:16px">
            <div style="font-weight:600;font-size:14px;margin-bottom:10px">Structured Abstract</div>

            <div v-if="detail.sections && detail.sections.length > 0 && summarySections.length < detail.sections.length"
                 style="margin-bottom:10px;padding:6px 10px;background:#fffbeb;border:1px solid #b45309;border-radius:4px;font-size:12px;color:#b45309">
              ⚠ Based on {{ summarySections.length }} of {{ detail.sections.length }} sections
            </div>

            <div v-if="abstractError" class="alert alert-error" style="margin-bottom:8px">{{ abstractError }}</div>

            <div v-if="structuredAbstract" class="markdown-body" style="margin-bottom:12px"
                 v-html="renderMd(structuredAbstract)"></div>

            <div v-if="generatingAbstract" class="flex items-center gap-8" style="margin-bottom:10px">
              <span class="spinner"></span>
              <span class="text-muted text-sm">Generating…</span>
            </div>

            <button class="btn btn-primary btn-sm" @click="generateStructuredAbstract" :disabled="generatingAbstract">
              {{ structuredAbstract ? 'Regenerate' : 'Generate structured abstract' }}
            </button>
          </div>

          <!-- ── Card 4: Key contributions ── -->
          <div v-if="!summarizing && summarySections.length" class="card" style="margin-top:16px">
            <div style="font-weight:600;font-size:14px;margin-bottom:10px">Key Contributions</div>

            <div v-if="detail.sections && detail.sections.length > 0 && summarySections.length < detail.sections.length"
                 style="margin-bottom:10px;padding:6px 10px;background:#fffbeb;border:1px solid #b45309;border-radius:4px;font-size:12px;color:#b45309">
              ⚠ Based on {{ summarySections.length }} of {{ detail.sections.length }} sections
            </div>

            <!-- Explicit claims -->
            <div style="margin-bottom:16px">
              <div style="font-size:13px;font-weight:600;margin-bottom:8px">Paper's explicit claims</div>
              <div v-if="claimsError" class="alert alert-error" style="margin-bottom:8px">{{ claimsError }}</div>
              <div v-if="explicitClaims" class="markdown-body" style="margin-bottom:8px"
                   v-html="renderMd(explicitClaims)"></div>
              <div v-if="generatingClaims" class="flex items-center gap-8" style="margin-bottom:8px">
                <span class="spinner"></span>
                <span class="text-muted text-sm">Extracting claims…</span>
              </div>
              <button class="btn btn-secondary btn-sm" @click="generateExplicitClaims" :disabled="generatingClaims">
                {{ explicitClaims ? 'Regenerate' : 'Extract explicit claims' }}
              </button>
            </div>

            <!-- Assessment -->
            <div style="border-top:1px solid var(--border);padding-top:16px">
              <div style="font-size:13px;font-weight:600;margin-bottom:8px">Assessment of claims</div>
              <div v-if="assessError" class="alert alert-error" style="margin-bottom:8px">{{ assessError }}</div>
              <div v-if="assessClaims" class="markdown-body" style="margin-bottom:8px"
                   v-html="renderMd(assessClaims)"></div>
              <div v-if="generatingAssess" class="flex items-center gap-8" style="margin-bottom:8px">
                <span class="spinner"></span>
                <span class="text-muted text-sm">Assessing…</span>
              </div>
              <button class="btn btn-secondary btn-sm" @click="generateAssessClaims" :disabled="generatingAssess">
                {{ assessClaims ? 'Regenerate' : 'Assess claims' }}
              </button>
            </div>
          </div>

        </template>

        <div v-else class="empty-state">
          <div style="font-size:32px">🔬</div>
          <p>Select a paper from the list to view its details.</p>
        </div>
      </div>
    </div>
  </template>
</div>
`,
})

export { ExploreTab }
