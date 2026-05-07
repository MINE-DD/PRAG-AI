import { defineComponent, ref, reactive, computed, watch } from 'vue'
import { api } from '../backend-client.js'

const SettingsPanel = defineComponent({
  name: 'SettingsPanel',
  props: {
    visible: { type: Boolean, required: true },
  },
  emits: ['update:visible', 'saved'],

  setup(props, { emit }) {
    const form = reactive({
      backendUrl:     localStorage.getItem('prag_backend_url')  || 'http://localhost:8000',
      metaBackend:    localStorage.getItem('prag_meta_backend') || 'openalex',
      pdfBackend:     localStorage.getItem('prag_pdf_backend')  || 'pymupdf',
      documentType:   localStorage.getItem('prag_document_type') || 'default',
      embeddingModel: '',
      embeddingContextLength: null,
      embeddingModelWarning: null,
      llmModel:       '',
      llmProvider:    'local',
      googleModel:    'gemini-2.5-flash',
      googleKey:      '',
      hasGoogleKey:   false,
      clearGoogleKey: false,
      zoteroUserId:   '',
      zoteroKey:      '',
      hasZoteroKey:   false,
      clearZoteroKey: false,
    })

    const status     = ref('unknown')
    const modelError = ref(null)
    const loading    = ref(false)

    const defaultEmbeddingModel = ref('')
    const defaultLlmModel       = ref('')
    const ollamaModels               = ref([])  // [{name, capabilities}]
    const googleModels               = ref(['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-pro', 'gemini-1.5-flash'])
    const recommendedEmbeddingModels = ref([])
    const recommendedLlmModels       = ref([])

    // Models filtered by capability; fall back to full list if Ollama returned no capability data
    const embeddingModels = computed(() => {
      const tagged = ollamaModels.value.filter(m => m.capabilities.includes('embedding'))
      return tagged.length ? tagged : ollamaModels.value
    })
    const llmModels = computed(() => {
      const tagged = ollamaModels.value.filter(
        m => m.capabilities.includes('completion') || m.capabilities.includes('tools')
      )
      return tagged.length ? tagged : ollamaModels.value
    })

    const pullModel       = ref('')
    const pulling         = ref(false)
    const pullingDefaults = ref(false)
    const pullProgress    = ref(null)
    const pullStatus      = ref('')
    const pullError       = ref(null)
    const pullDone        = ref(false)

    // Ollama appends :latest when no tag is specified, so normalize both sides.
    const normalizeModel = name => (name && !name.includes(':') ? name + ':latest' : name)

    // True only when both default models are confirmed in the pulled list.
    const defaultsPulled = computed(() => {
      if (!defaultEmbeddingModel.value && !defaultLlmModel.value) return true
      const names = new Set(ollamaModels.value.map(m => normalizeModel(m.name)))
      const embOk = !defaultEmbeddingModel.value || names.has(normalizeModel(defaultEmbeddingModel.value))
      const llmOk = !defaultLlmModel.value       || names.has(normalizeModel(defaultLlmModel.value))
      return embOk && llmOk
    })

    async function load() {
      status.value     = 'checking'
      modelError.value = null
      loading.value    = true
      form.metaBackend  = localStorage.getItem('prag_meta_backend')  || 'openalex'
      form.pdfBackend   = localStorage.getItem('prag_pdf_backend')   || 'pymupdf'
      form.documentType = localStorage.getItem('prag_document_type') || 'default'
      try {
        const [cfg, models, cloudModels] = await Promise.all([
          api.get('/settings'),
          api.get('/ollama/models'),
          api.get('/settings/cloud-models'),
          api.get('/health'),
        ])
        status.value = 'ok'
        if (cloudModels.google?.length)           googleModels.value               = cloudModels.google
        if (cloudModels.ollama_embedding?.length) recommendedEmbeddingModels.value = cloudModels.ollama_embedding
        if (cloudModels.ollama_llm?.length)       recommendedLlmModels.value       = cloudModels.ollama_llm
        if (!pullModel.value && cloudModels.ollama_embedding?.length) pullModel.value = cloudModels.ollama_embedding[0]
        ollamaModels.value   = models.map(m => ({ name: m.name, capabilities: m.capabilities || [] }))
        defaultEmbeddingModel.value = cfg.default_embedder_model
        defaultLlmModel.value       = cfg.default_llm_model
        form.embeddingModel         = cfg.embedding_model
        form.embeddingContextLength = cfg.embedding_context_length ?? null
        form.embeddingModelWarning  = null
        fetchEmbeddingInfo(cfg.embedding_model)
        form.llmModel        = cfg.llm_model
        form.llmProvider     = cfg.llm_provider || 'local'
        form.googleModel     = cfg.google_model || googleModels.value[0]
        form.hasGoogleKey    = !!cfg.has_google_key
        form.googleKey       = ''
        form.clearGoogleKey  = false
        form.zoteroUserId    = cfg.zotero_user_id || ''
        form.hasZoteroKey    = !!cfg.has_zotero_key
        form.zoteroKey       = ''
        form.clearZoteroKey  = false
      } catch (e) {
        modelError.value = e.message
        status.value     = 'error'
      } finally {
        loading.value = false
      }
    }

    watch(() => props.visible, v => { if (v) load() })

    async function fetchEmbeddingInfo(model) {
      if (!model) return
      form.embeddingModelWarning = null
      try {
        const res = await api.get(`/ollama/models/${encodeURIComponent(model)}/context-length`)
        form.embeddingContextLength = res.context_length ?? null
        if (res.is_embedding_model === false) {
          form.embeddingModelWarning =
            `"${model}" is a generative model, not an embedding model. ` +
            `It will not produce valid embeddings. Choose a model with embedding capability (e.g. mxbai-embed-large, nomic-embed-text).`
        }
      } catch {
        form.embeddingContextLength = null
      }
    }

    async function pullOllamaModel() {
      if (!pullModel.value) return
      pulling.value      = true
      pullProgress.value = 0
      pullStatus.value   = ''
      pullError.value    = null
      pullDone.value     = false
      try {
        const resp = await fetch(`${api.url()}/ollama/pull`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: pullModel.value }),
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
            if (data.error) { pullError.value = data.error; break }
            if (data.done)  { pullDone.value  = true; load(); break }
            pullStatus.value = data.status || ''
            if (data.completed && data.total)
              pullProgress.value = Math.round(data.completed / data.total * 100)
          }
        }
      } catch (e) {
        pullError.value = e.message
      } finally {
        pulling.value = false
      }
    }

    async function pullDefaults() {
      pullingDefaults.value = true
      try {
        for (const model of [defaultEmbeddingModel.value, defaultLlmModel.value]) {
          if (!model) continue
          pullModel.value = model
          await pullOllamaModel()
          if (pullError.value) break
        }
        if (!pullError.value) {
          await load()
          // Pre-select the downloaded defaults so the dropdowns aren't empty.
          // The user still clicks Save to persist them to config.
          form.embeddingModel = defaultEmbeddingModel.value
          form.llmModel       = defaultLlmModel.value
        }
      } finally {
        pullingDefaults.value = false
      }
    }

    async function save() {
      status.value = 'checking'
      localStorage.setItem('prag_backend_url',  form.backendUrl)
      localStorage.setItem('prag_meta_backend', form.metaBackend)
      localStorage.setItem('prag_pdf_backend',  form.pdfBackend)
      localStorage.setItem('prag_document_type', form.documentType)
      try {
        await api.get('/health')
        status.value = 'ok'
        const body = {}
        if (form.embeddingModel) body.embedding_model = form.embeddingModel
        if (form.llmModel)       body.llm_model       = form.llmModel
        body.llm_provider = form.llmProvider
        if (form.llmProvider === 'google') {
          body.google_model = form.googleModel
          if (form.clearGoogleKey)        body.clear_google_key = true
          else if (form.googleKey.trim()) body.google_key = form.googleKey.trim()
        }
        if (form.clearZoteroKey) {
          body.clear_zotero_key = true
          body.zotero_user_id = ''
        } else {
          if (form.zoteroUserId.trim()) body.zotero_user_id = form.zoteroUserId.trim()
          if (form.zoteroKey.trim())    body.zotero_key = form.zoteroKey.trim()
        }
        await api.post('/settings', body)
        emit('update:visible', false)
        emit('saved')
      } catch {
        status.value = 'error'
      }
    }

    function close() { emit('update:visible', false) }

    return {
      form, status, modelError, loading,
      ollamaModels, embeddingModels, llmModels,
      googleModels, recommendedEmbeddingModels, recommendedLlmModels,
      defaultEmbeddingModel, defaultLlmModel, defaultsPulled,
      pullModel, pulling, pullingDefaults, pullProgress, pullStatus, pullError, pullDone,
      fetchEmbeddingInfo, pullOllamaModel, pullDefaults, save, close,
    }
  },

  template: `
<div class="modal-overlay" v-if="visible" @click.self="close">
  <div class="modal">
    <div class="modal-title">⚙ Settings</div>

    <!-- 1. Connection -->
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px">Connection</div>
    <div class="form-group">
      <label>Backend URL</label>
      <input type="text" v-model="form.backendUrl" placeholder="http://localhost:8000" />
    </div>
    <div class="flex items-center gap-8" style="margin-bottom:8px">
      <span class="dot" :class="status === 'ok' ? 'dot-green' : status === 'checking' ? 'dot-yellow' : 'dot-red'"></span>
      <span class="text-muted text-sm">
        {{ status === 'ok' ? 'Connected' : status === 'checking' ? 'Checking…' : 'Not reachable' }}
      </span>
    </div>
    <div v-if="status === 'error'" class="alert alert-warning" style="margin-bottom:16px;font-size:12px">
      Could not reach the backend at <strong>{{ form.backendUrl }}</strong>. Check that the URL is correct and the backend is running.
    </div>

    <hr class="divider" />

    <!-- 2. PDF Processing -->
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px">PDF Processing</div>
    <div class="form-group">
      <label>PDF conversion backend</label>
      <select v-model="form.pdfBackend">
        <option value="pymupdf">PyMuPDF (fast)</option>
        <option value="docling">Docling (thorough, slow)</option>
        <option value="ollama_vlm">Ollama VLM (vision model)</option>
      </select>
    </div>
    <div class="form-group" v-if="form.pdfBackend === 'ollama_vlm'">
      <label>Document type</label>
      <select v-model="form.documentType">
        <option value="default">Default (research paper)</option>
        <option value="invoice">Invoice</option>
      </select>
    </div>
    <div class="form-group">
      <label>Metadata provider</label>
      <select v-model="form.metaBackend">
        <option value="openalex">OpenAlex (default)</option>
        <option value="crossref">CrossRef</option>
        <option value="semantic_scholar">Semantic Scholar</option>
        <option value="none">None (skip enrichment)</option>
      </select>
    </div>

    <hr class="divider" />

    <!-- 3. Generation Provider -->
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px">Generation Provider</div>
    <div class="text-muted text-sm" style="margin-bottom:12px">
      Local (Ollama) keeps everything on your machine. Google Gemini sends your queries and retrieved passages to Google's servers.
    </div>

    <div class="provider-tabs" style="margin-bottom:16px">
      <button :class="['provider-tab', form.llmProvider === 'local' ? 'active' : '']"
              @click="form.llmProvider = 'local'">🖥 Local (Ollama)</button>
      <button :class="['provider-tab', form.llmProvider === 'google' ? 'active' : '']"
              @click="form.llmProvider = 'google'">☁ Google Gemini</button>
    </div>

    <!-- Local: Ollama model selectors -->
    <template v-if="form.llmProvider === 'local'">
      <div v-if="loading" class="flex items-center gap-8" style="margin-bottom:16px">
        <span class="spinner"></span>
        <span class="text-muted text-sm">Loading available models…</span>
      </div>
      <div v-else-if="modelError" class="alert alert-warning" style="margin-bottom:16px;font-size:12px">
        Could not reach Ollama: {{ modelError }}
      </div>
      <div v-else-if="pullingDefaults"
           style="margin-bottom:16px;padding:14px;background:var(--info-bg,#eff6ff);border:1px solid var(--info-border,#bfdbfe);border-radius:6px">
        <div style="font-size:13px;font-weight:600;color:var(--info-text,#1d4ed8);margin-bottom:10px">
          Downloading <code>{{ pullModel }}</code>…
        </div>
        <!-- spinner + status while manifest is being fetched (no byte progress yet) -->
        <div v-if="!pullProgress" class="flex items-center gap-8" style="margin-bottom:4px">
          <span class="spinner" style="width:14px;height:14px;flex-shrink:0"></span>
          <span style="font-size:12px;color:var(--info-text,#1d4ed8)">{{ pullStatus || 'Connecting…' }}</span>
        </div>
        <!-- determinate bar once layer data starts flowing -->
        <template v-else>
          <div style="background:var(--border);border-radius:4px;height:6px;overflow:hidden;margin-bottom:4px">
            <div style="background:var(--accent,#2563eb);height:100%;transition:width .2s" :style="{width: pullProgress + '%'}"></div>
          </div>
          <div style="font-size:11px;color:var(--text-muted)">{{ pullStatus }} — {{ pullProgress }}%</div>
        </template>
        <div v-if="pullError" class="alert alert-warning" style="margin-top:8px;font-size:12px">{{ pullError }}</div>
      </div>
      <div v-else-if="!defaultsPulled"
           style="margin-bottom:16px;padding:14px;background:var(--warning-bg,#fffbeb);border:1px solid var(--warning,#b45309);border-radius:6px">
        <div style="font-size:13px;font-weight:600;color:var(--warning,#b45309);margin-bottom:6px">No models downloaded yet</div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:12px">
          This app needs two AI models to work: one for understanding text (embeddings) and one for generating answers.
          Click below to download the recommended defaults — this may take a few minutes depending on your connection.
        </div>
        <div style="font-size:12px;margin-bottom:8px">
          <span style="font-weight:600">Embedding:</span>
          <code style="margin-left:4px">{{ defaultEmbeddingModel }}</code>
        </div>
        <div style="font-size:12px;margin-bottom:12px">
          <span style="font-weight:600">Generation (LLM):</span>
          <code style="margin-left:4px">{{ defaultLlmModel }}</code>
        </div>
        <button class="btn btn-primary btn-sm" @click="pullDefaults" :disabled="pulling">
          Download both models
        </button>
      </div>
      <template v-else>
        <div class="form-group">
          <label>Embedding model</label>
          <select v-model="form.embeddingModel" @change="fetchEmbeddingInfo(form.embeddingModel)">
            <option v-for="m in embeddingModels" :key="m.name" :value="m.name">
              {{ m.name }}{{ m.capabilities.length ? ' (' + m.capabilities.join(', ') + ')' : '' }}
            </option>
          </select>
          <div v-if="form.embeddingContextLength" class="text-sm text-muted" style="margin-top:3px">
            Context window: {{ form.embeddingContextLength }} tokens
            (~{{ Math.floor(form.embeddingContextLength * 4) }} chars max per chunk)
          </div>
          <div v-if="form.embeddingModelWarning" class="text-sm" style="color:var(--danger,#dc2626);margin-top:4px">
            ⚠ {{ form.embeddingModelWarning }}
          </div>
        </div>
        <div class="form-group">
          <label>Generation (LLM) model</label>
          <select v-model="form.llmModel">
            <option v-for="m in llmModels" :key="m.name" :value="m.name">
              {{ m.name }}{{ m.capabilities.length ? ' (' + m.capabilities.join(', ') + ')' : '' }}
            </option>
          </select>
        </div>
      </template>
      <div v-if="defaultsPulled" style="margin-top:8px">
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
          Don't see a model above? Pull a recommended one:
        </div>
        <div class="flex items-center gap-8">
          <select v-model="pullModel" style="flex:1">
            <optgroup label="Embedding">
              <option v-for="m in recommendedEmbeddingModels" :key="m" :value="m">{{ m }}</option>
            </optgroup>
            <optgroup label="LLM">
              <option v-for="m in recommendedLlmModels" :key="m" :value="m">{{ m }}</option>
            </optgroup>
          </select>
          <button class="btn btn-secondary btn-sm" @click="pullOllamaModel" :disabled="pulling" style="white-space:nowrap">
            <span v-if="pulling" class="spinner" style="width:12px;height:12px;margin-right:4px"></span>
            {{ pulling ? 'Pulling…' : 'Pull' }}
          </button>
        </div>
        <div v-if="pulling || pullProgress !== null" style="margin-top:8px">
          <div v-if="!pullProgress" class="flex items-center gap-8" style="margin-bottom:4px">
            <span class="spinner" style="width:14px;height:14px;flex-shrink:0"></span>
            <span style="font-size:12px;color:var(--text-muted)">{{ pullStatus || 'Connecting…' }}</span>
          </div>
          <template v-else>
            <div style="background:var(--border);border-radius:4px;height:6px;overflow:hidden;margin-bottom:4px">
              <div style="background:var(--accent,#2563eb);height:100%;transition:width .2s" :style="{width: pullProgress + '%'}"></div>
            </div>
            <div style="font-size:11px;color:var(--text-muted)">{{ pullStatus }} — {{ pullProgress }}%</div>
          </template>
        </div>
        <div v-if="pullError" class="alert alert-warning" style="margin-top:8px;font-size:12px">{{ pullError }}</div>
        <div v-if="pullDone" style="font-size:12px;color:var(--success,#22c55e);margin-top:6px">Model pulled successfully. Reload models to see it.</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:8px">
          For other models visit <a href="https://ollama.com/library" target="_blank" rel="noopener" style="color:var(--accent)">ollama.com/library</a>
        </div>
      </div>
    </template>

    <!-- Google -->
    <template v-if="form.llmProvider === 'google'">
      <div class="alert alert-warning" style="margin-bottom:12px;font-size:12px">
        ⚠️ Queries and retrieved passages will be sent to Google's servers.
      </div>
      <div class="form-group">
        <label>Gemini model</label>
        <select v-model="form.googleModel">
          <option v-for="m in googleModels" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div class="form-group">
        <label>Google API key</label>
        <div v-if="form.hasGoogleKey && !form.clearGoogleKey"
             class="flex items-center gap-8" style="margin-bottom:8px">
          <span style="color:var(--success);font-size:13px">✓ Key saved</span>
          <button class="btn btn-secondary btn-sm" @click="form.clearGoogleKey = true">Clear key</button>
        </div>
        <input v-else type="password" v-model="form.googleKey"
               :placeholder="form.clearGoogleKey ? 'Enter new key…' : 'AIzaSy…'"
               autocomplete="off" />
      </div>
    </template>

    <hr class="divider" />

    <!-- 4. Zotero -->
    <div style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin-bottom:8px">Zotero</div>
    <div v-if="form.hasZoteroKey && !form.clearZoteroKey"
         class="form-group flex items-center gap-8">
      <span style="color:var(--success);font-size:13px">✓ Connected (User ID: {{ form.zoteroUserId }})</span>
      <button class="btn btn-secondary btn-sm"
              @click="form.clearZoteroKey = true; form.zoteroUserId = ''">Disconnect</button>
    </div>
    <template v-else>
      <div class="form-group">
        <label>Zotero User ID</label>
        <input v-model="form.zoteroUserId" class="form-control" placeholder="e.g. 1234567" />
      </div>
      <div class="form-group">
        <label>Zotero API Key</label>
        <input type="password" v-model="form.zoteroKey"
               placeholder="Paste API key" autocomplete="off" />
      </div>
    </template>

    <div class="modal-footer">
      <button class="btn btn-secondary" @click="close">Cancel</button>
      <button class="btn btn-primary" @click="save">Save & connect</button>
    </div>
  </div>
</div>
`,
})

export { SettingsPanel }
