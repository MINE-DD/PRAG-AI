import { createApp, ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { api } from './api.js'
import { PdfTab } from './pdf-tab.js'
import { CollectionsTab } from './collections-tab.js'
import { RagTab } from './rag-tab.js'
import { ExploreTab } from './explore-tab.js'
import { CompareTab } from './compare-tab.js'

createApp({
  components: { PdfTab, CollectionsTab, RagTab, ExploreTab, CompareTab },

  setup() {
    const activeTab = ref('pdf')
    const selectedCollection = ref(localStorage.getItem('prag_collection') || '')
    const collections = ref([])
    const globalError = ref(null)
    const showSettings = ref(false)
    const health = reactive({ backend: false, qdrant: false, ollama: null })

    const settingsForm = reactive({
      backendUrl:       localStorage.getItem('prag_backend_url')       || 'http://localhost:8000',
      preprocessedBase: localStorage.getItem('prag_preprocessed_dir') || '/data/preprocessed',
      metaBackend:      localStorage.getItem('prag_meta_backend')      || 'openalex',
      pdfBackend:       localStorage.getItem('prag_pdf_backend')        || 'pymupdf',
      embeddingModel: '',
      llmModel:       '',
      // Cloud LLM
      llmProvider:      'local',
      anthropicModel:   'claude-opus-4-6',
      googleModel:      'gemini-2.5-flash',
      anthropicKey:     '',
      googleKey:        '',
      hasAnthropicKey:  false,
      hasGoogleKey:     false,
      clearAnthropicKey: false,
      clearGoogleKey:    false,
      zoteroUserId:    '',
      zoteroKey:       '',
      hasZoteroKey:    false,
      clearZoteroKey:  false,
    })
    const settingsStatus  = ref('unknown')
    const ollamaModels    = ref([])
    const loadingModels   = ref(false)
    const modelError      = ref(null)
    const anthropicModels = ref(['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'])
    const googleModels    = ref(['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-1.5-pro', 'gemini-1.5-flash'])
    const recommendedEmbeddingModels = ref([])
    const recommendedLlmModels       = ref([])
    const pullModel    = ref('')
    const pulling      = ref(false)
    const pullProgress = ref(null)
    const pullStatus   = ref('')
    const pullError    = ref(null)
    const pullDone     = ref(false)

    const tabs = [
      { id: 'pdf',         label: 'PDF Management' },
      { id: 'collections', label: 'Collections' },
      { id: 'rag',         label: 'RAG Query' },
      { id: 'explore',     label: 'Explore Document' },
      { id: 'compare',     label: 'Compare' },
    ]

    const tabComponents = {
      pdf:         PdfTab,
      collections: CollectionsTab,
      rag:         RagTab,
      explore:     ExploreTab,
      compare:     CompareTab,
    }

    const activeComponent = computed(() => tabComponents[activeTab.value])

    async function checkHealth() {
      try {
        const data = await api.get('/health')
        health.backend = true
        health.qdrant  = data.qdrant === 'ok'
        health.ollama  = data.ollama === 'ok'
      } catch {
        health.backend = false
        health.qdrant  = false
        health.ollama  = null  // null = unknown (yellow), not false = down (red)
      }
    }

    async function loadCollections() {
      try {
        collections.value = await api.get('/collections')
      } catch (e) {
        globalError.value = 'Could not load collections: ' + e.message
      }
    }

    function setCollection(id) {
      selectedCollection.value = id
      localStorage.setItem('prag_collection', id)
      activeTab.value = 'rag'
    }

    function saveCollection() {
      localStorage.setItem('prag_collection', selectedCollection.value)
    }

    async function openSettings() {
      showSettings.value   = true
      settingsStatus.value = 'checking'
      modelError.value     = null
      loadingModels.value  = true
      settingsForm.metaBackend = localStorage.getItem('prag_meta_backend') || 'openalex'
      settingsForm.pdfBackend  = localStorage.getItem('prag_pdf_backend')  || 'pymupdf'
      try {
        const [cfg, models, cloudModels] = await Promise.all([
          api.get('/settings'),
          api.get('/ollama/models'),
          api.get('/settings/cloud-models'),
          api.get('/health'),
        ])
        settingsStatus.value = 'ok'
        if (cloudModels.anthropic?.length)       anthropicModels.value          = cloudModels.anthropic
        if (cloudModels.google?.length)          googleModels.value             = cloudModels.google
        if (cloudModels.ollama_embedding?.length) recommendedEmbeddingModels.value = cloudModels.ollama_embedding
        if (cloudModels.ollama_llm?.length)       recommendedLlmModels.value       = cloudModels.ollama_llm
        if (!pullModel.value && cloudModels.ollama_embedding?.length) pullModel.value = cloudModels.ollama_embedding[0]
        settingsForm.embeddingModel    = cfg.embedding_model
        settingsForm.llmModel          = cfg.llm_model
        settingsForm.llmProvider       = cfg.llm_provider || 'local'
        settingsForm.anthropicModel    = cfg.anthropic_model || anthropicModels.value[0]
        settingsForm.googleModel       = cfg.google_model   || googleModels.value[0]
        settingsForm.hasAnthropicKey   = !!cfg.has_anthropic_key
        settingsForm.hasGoogleKey      = !!cfg.has_google_key
        settingsForm.anthropicKey      = ''
        settingsForm.googleKey         = ''
        settingsForm.clearAnthropicKey = false
        settingsForm.clearGoogleKey    = false
        settingsForm.zoteroUserId   = cfg.zotero_user_id || ''
        settingsForm.hasZoteroKey   = !!cfg.has_zotero_key
        settingsForm.zoteroKey      = ''
        settingsForm.clearZoteroKey = false
        ollamaModels.value             = models.map(m => m.name)
      } catch (e) {
        modelError.value     = e.message
        settingsStatus.value = 'error'
      } finally {
        loadingModels.value = false
      }
    }

    async function pullOllamaModel() {
      if (!pullModel.value) return
      pulling.value    = true
      pullProgress.value = 0
      pullStatus.value = ''
      pullError.value  = null
      pullDone.value   = false
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
            if (data.error)  { pullError.value = data.error; break }
            if (data.done)   { pullDone.value  = true; break }
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

    async function saveSettings() {
      settingsStatus.value = 'checking'
      localStorage.setItem('prag_backend_url',      settingsForm.backendUrl)
      localStorage.setItem('prag_preprocessed_dir', settingsForm.preprocessedBase)
      localStorage.setItem('prag_meta_backend', settingsForm.metaBackend)
      localStorage.setItem('prag_pdf_backend',  settingsForm.pdfBackend)
      try {
        await api.get('/health')
        settingsStatus.value = 'ok'
        // Persist settings to config.yaml / api_keys.json
        const body = {}
        if (settingsForm.embeddingModel) body.embedding_model = settingsForm.embeddingModel
        if (settingsForm.llmModel)       body.llm_model       = settingsForm.llmModel
        body.llm_provider = settingsForm.llmProvider
        if (settingsForm.llmProvider === 'anthropic') {
          body.anthropic_model = settingsForm.anthropicModel
          if (settingsForm.clearAnthropicKey)        body.clear_anthropic_key = true
          else if (settingsForm.anthropicKey.trim()) body.anthropic_key = settingsForm.anthropicKey.trim()
        }
        if (settingsForm.llmProvider === 'google') {
          body.google_model = settingsForm.googleModel
          if (settingsForm.clearGoogleKey)        body.clear_google_key = true
          else if (settingsForm.googleKey.trim()) body.google_key = settingsForm.googleKey.trim()
        }
        if (settingsForm.zoteroUserId.trim())
          body.zotero_user_id = settingsForm.zoteroUserId.trim()
        if (settingsForm.clearZoteroKey)
          body.clear_zotero_key = true
        else if (settingsForm.zoteroKey.trim())
          body.zotero_key = settingsForm.zoteroKey.trim()
        await api.post('/settings', body)
        showSettings.value = false
        await checkHealth()
        await loadCollections()
      } catch {
        settingsStatus.value = 'error'
      }
    }

    let healthTimer
    onMounted(async () => {
      await checkHealth()
      await loadCollections()
      healthTimer = setInterval(checkHealth, 30_000)
    })
    onUnmounted(() => clearInterval(healthTimer))

    return {
      activeTab, tabs, activeComponent,
      selectedCollection, collections,
      globalError, showSettings, health,
      settingsForm, settingsStatus, ollamaModels, loadingModels, modelError,
      anthropicModels, googleModels,
      recommendedEmbeddingModels, recommendedLlmModels,
      pullModel, pulling, pullProgress, pullStatus, pullError, pullDone, pullOllamaModel,
      setCollection, saveCollection, openSettings, saveSettings, loadCollections,
    }
  },
}).mount('#app')
