import { defineComponent, ref, reactive } from 'vue'
import { api } from './api.js'

const PipelinePanel = defineComponent({
  name: 'PipelinePanel',
  props: {
    dirName:              { type: String, required: true },
    initialCollectionName: { type: String, default: '' },
  },
  emits: ['refresh-collections', 'open-collection', 'dismiss'],

  setup(props, { emit }) {
    const form    = reactive({
      collectionName: props.initialCollectionName ||
        props.dirName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    })
    const running = ref(false)
    const events  = ref([])
    const done    = ref(null)

    async function run() {
      if (!form.collectionName.trim()) return
      if (!confirm(
        `Run pipeline on "${props.dirName}"?\n\nThis will:\n• Convert all unconverted PDFs\n• Create collection "${form.collectionName}"\n• Ingest all files\n\nAlready-converted files will be skipped.`
      )) return
      running.value = true
      events.value  = []
      done.value    = null
      try {
        const resp = await fetch(`${api.url()}/pipeline/run`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dir_name:         props.dirName,
            collection_name:  form.collectionName,
            pdf_backend:      localStorage.getItem('prag_pdf_backend')  || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend') || 'openalex',
          }),
        })
        if (!resp.ok) throw new Error(await resp.text())
        const reader  = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done: streamDone, value } = await reader.read()
          if (streamDone) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop()
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            let data
            try { data = JSON.parse(line.slice(6)) } catch { continue }
            events.value = [...events.value, data]
            if (data.done !== undefined) {
              done.value = data
              if (data.done && data.collection_id) emit('refresh-collections')
            }
          }
        }
      } catch (e) {
        done.value = { done: false, error: e.message }
      } finally {
        running.value = false
      }
    }

    function reset() { done.value = null; events.value = [] }

    return { form, running, events, done, run, reset }
  },

  template: `
<div style="border-top:1px solid var(--border);padding-top:12px">
  <div style="font-size:13px;font-weight:600;margin-bottom:4px">⚡ Run Pipeline for <code>{{ dirName }}</code></div>
  <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px">
    Converts PDFs, creates a collection, and ingests everything in one step.
  </p>

  <div v-if="!running && !done" class="form-group" style="margin-bottom:8px">
    <label style="font-size:12px">Collection name</label>
    <input type="text" v-model="form.collectionName" style="font-size:13px" placeholder="my-collection" />
  </div>
  <div v-if="!running && !done" class="flex gap-8">
    <button class="btn btn-primary btn-sm" :disabled="!form.collectionName.trim()" @click="run">Run Pipeline</button>
    <button class="btn btn-secondary btn-sm" @click="$emit('dismiss')">Done</button>
  </div>

  <div v-if="running" style="margin-bottom:8px">
    <div style="height:4px;background:var(--border);border-radius:2px;overflow:hidden">
      <div :style="{
        width: (() => {
          const s = events.find(e => e.step === 'scan')
          if (!s) return '2%'
          const tc = s.to_convert || 0, ad = s.already_done || 0, tf = tc + ad
          const cd = events.filter(e => e.step==='convert' && (e.status==='done'||e.status==='error'||e.status==='skipped')).length
          const id = events.filter(e => e.step==='ingest'  && (e.status==='done'||e.status==='error')).length
          return Math.min(95, (cd + id) / Math.max(1, tc + tf) * 100) + '%'
        })(),
        height: '4px', background: 'var(--primary)', transition: 'width .3s'
      }"></div>
    </div>
    <div class="text-sm text-muted" style="margin-top:4px">
      <span class="spinner" style="width:10px;height:10px;border-width:2px;margin-right:4px"></span>
      {{ (() => {
        const last = [...events].reverse().find(e => e.step && e.status && e.status !== 'done' && e.status !== 'skipped')
        if (!last) return 'Starting\u2026'
        if (last.step === 'convert') return 'Converting ' + last.file + '\u2026'
        if (last.step === 'collection') return 'Creating collection\u2026'
        if (last.step === 'ingest') return 'Ingesting ' + last.file + '\u2026'
        return 'Running\u2026'
      })() }}
    </div>
  </div>

  <div v-if="done && done.done"
       style="padding:10px;background:#f0fff4;border:1px solid var(--success);border-radius:4px;font-size:13px">
    <div style="color:var(--success);font-weight:600;margin-bottom:4px">✓ Pipeline complete</div>
    <div class="text-muted">
      Collection <code>{{ done.collection_id }}</code> —
      {{ done.ingested }} ingested, {{ done.converted }} converted, {{ done.skipped }} skipped
      <span v-if="done.errors > 0" style="color:var(--warning)">, {{ done.errors }} errors</span>
    </div>
    <div style="margin-top:8px;display:flex;gap:8px">
      <button class="btn btn-secondary btn-sm" @click="reset">Run again</button>
      <button class="btn btn-primary btn-sm" @click="$emit('open-collection', done.collection_id)">Query Collection</button>
    </div>
  </div>

  <div v-else-if="done && !done.done" class="alert alert-error" style="margin:0">
    Pipeline failed: {{ done.error }}
    <button class="btn btn-secondary btn-sm" style="margin-left:8px" @click="reset">Retry</button>
  </div>
</div>
`,
})

export { PipelinePanel }
