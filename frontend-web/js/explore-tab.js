import { defineComponent, ref, computed, watch } from 'vue'
import { api } from './api.js'

const ExploreTab = defineComponent({
  name: 'ExploreTab',
  props: ['selectedCollection', 'collections'],
  emits: ['update:collection'],

  setup(props) {
    const error    = ref(null)
    const papers   = ref([])
    const selected = ref(null)
    const detail   = ref(null)
    const loading  = ref(false)

    const collectionId = computed(() => props.selectedCollection)

    watch(collectionId, async (id) => {
      papers.value = []
      selected.value = null
      detail.value = null
      error.value = null
      if (id) {
        try {
          papers.value = await api.get(`/collections/${id}/papers`)
          // Overlay fresh metadata for each paper in parallel
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

    async function selectPaper(paper) {
      selected.value = paper
      loading.value = true
      detail.value = null
      error.value = null
      try {
        const collectionDetail = await api.get(`/collections/${collectionId.value}/papers/${paper.paper_id}`)
        // Overlay with fresh raw metadata if available (stays in sync with PDF Management edits)
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
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    return { error, papers, selected, detail, loading, collectionId, selectPaper }
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
               style="padding:10px 16px;cursor:pointer;border-bottom:1px solid var(--border);
                      transition:background .1s"
               :style="selected && selected.paper_id === p.paper_id
                 ? 'background:var(--primary);color:#fff'
                 : 'background:var(--card)'"
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
          <div class="card">
            <h3 style="font-size:18px;font-weight:700;line-height:1.4;margin-bottom:8px">
              {{ detail.title || detail.filename }}
            </h3>
            <div class="text-muted text-sm" style="margin-bottom:12px">
              {{ (detail.authors || []).join(', ') }}
              <span v-if="detail.year"> · {{ detail.year }}</span>
              <span v-if="detail.journal"> · <em>{{ detail.journal }}</em></span>
            </div>

            <div v-if="detail.doi" style="margin-bottom:10px">
              <span class="text-sm text-muted">DOI: </span>
              <a :href="detail.doi.startsWith('http') ? detail.doi : 'https://doi.org/' + detail.doi"
                 target="_blank" rel="noopener"
                 style="color:var(--primary);font-size:13px">{{ detail.doi }}</a>
            </div>

            <div class="flex gap-8" style="flex-wrap:wrap;margin-bottom:12px">
              <span v-if="detail.chunk_count" class="badge badge-gray">
                {{ detail.chunk_count }} chunks
              </span>
              <span v-if="detail.metadata_source" class="badge badge-blue">
                metadata: {{ detail.metadata_source }}
              </span>
              <span v-if="detail.backend" class="badge badge-yellow">
                {{ detail.backend }}
              </span>
            </div>

            <!-- Abstract -->
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
