import { createApp, ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from './backend-client.js'
import { PdfTab } from './tabs/tab-pdf.js'
import { CollectionsTab } from './tabs/tab-collections.js'
import { RagTab } from './tabs/tab-rag.js'
import { ExploreTab } from './tabs/tab-explore.js'
import { CompareTab } from './tabs/tab-compare.js'
import { SettingsPanel } from './components/settings-panel.js'

createApp({
  components: { PdfTab, CollectionsTab, RagTab, ExploreTab, CompareTab, SettingsPanel },

  setup() {
    const activeTab = ref('pdf')
    const selectedCollection = ref(localStorage.getItem('prag_collection') || '')
    const collections = ref([])
    const globalError = ref(null)
    const showSettings = ref(false)
    const health = ref({ backend: false, qdrant: false, ollama: null })

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
        health.value = { backend: true, qdrant: data.qdrant === 'ok', ollama: data.ollama === 'ok' }
      } catch {
        health.value = { backend: false, qdrant: false, ollama: null }
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

    async function onSettingsSaved() {
      await checkHealth()
      await loadCollections()
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
      setCollection, saveCollection, loadCollections, onSettingsSaved,
    }
  },
}).mount('#app')
