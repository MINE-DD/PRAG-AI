import { defineComponent, ref } from 'vue'
import { api } from '../../backend-client.js'

const UploadPanel = defineComponent({
  name: 'UploadPanel',
  emits: ['files-uploaded', 'dismiss'],

  setup(props, { emit }) {
    const uploadDir      = ref('uploads')
    const pendingFiles   = ref(null)
    const fileInputKey   = ref(0)
    const loading        = ref(false)
    const error          = ref(null)
    const autoConvert    = ref(true)
    const converting     = ref(false)
    const convertEvents  = ref([])
    const convertDone    = ref(false)

    function onFileSelect(evt) {
      const files = evt.target.files
      if (!files.length) { pendingFiles.value = null; return }
      pendingFiles.value = files
    }

    async function runConvertBatch(dirName) {
      converting.value    = true
      convertEvents.value = []
      convertDone.value   = false
      try {
        const resp = await fetch(`${api.url()}/preprocess/convert-batch`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dir_name:         dirName,
            backend:          localStorage.getItem('prag_pdf_backend')   || 'pymupdf',
            metadata_backend: localStorage.getItem('prag_meta_backend')  || 'openalex',
            document_type:    localStorage.getItem('prag_document_type') || 'default',
          }),
        })
        if (!resp.ok) throw new Error(await resp.text())
        const reader  = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let streamDone = false
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
            if (data.done) { convertDone.value = true; streamDone = true; break }
            if (data.filename) convertEvents.value = [...convertEvents.value, data]
          }
          if (streamDone) break
        }
      } catch (e) {
        error.value = `Conversion error: ${e.message}`
      } finally {
        converting.value = false
        if (!error.value) convertDone.value = true
      }
    }

    async function uploadFiles() {
      if (!pendingFiles.value || !pendingFiles.value.length) return
      const dir = uploadDir.value.trim() || 'uploads'
      const fd  = new FormData()
      fd.append('dir_name', dir)
      for (const f of pendingFiles.value) fd.append('files', f)
      loading.value = true
      error.value   = null
      try {
        await api.upload('/preprocess/upload', fd)
        uploadDir.value    = 'uploads'
        pendingFiles.value = null
        fileInputKey.value++
        if (autoConvert.value) {
          await runConvertBatch(dir)
        }
        if (!error.value) {
          emit('files-uploaded', dir)
        }
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    return {
      uploadDir, pendingFiles, fileInputKey, loading, error,
      autoConvert, converting, convertEvents, convertDone,
      onFileSelect, uploadFiles,
    }
  },

  template: `
<div class="card" style="margin-bottom:8px">
  <div v-if="error" class="alert alert-error" style="margin-bottom:8px">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Step 1: choose files -->
  <template v-if="!pendingFiles && !convertDone">
    <div class="form-group" style="margin-bottom:0">
      <label>Choose PDF files</label>
      <input :key="fileInputKey" type="file" accept=".pdf" multiple @change="onFileSelect"
             :disabled="loading" style="font-size:13px;width:100%;padding:6px 0;" />
    </div>
  </template>

  <!-- Step 2: name dir, confirm, checkbox -->
  <template v-else-if="pendingFiles && !converting && !convertDone">
    <div style="margin-bottom:12px;font-size:13px">
      <strong>{{ pendingFiles.length }}</strong> file{{ pendingFiles.length !== 1 ? 's' : '' }} selected
      <button class="btn btn-secondary btn-sm" style="margin-left:8px"
              @click="pendingFiles = null; fileInputKey++">Change</button>
    </div>
    <div class="form-group">
      <label>Directory name</label>
      <input type="text" v-model="uploadDir" placeholder="uploads" />
    </div>
    <label style="display:flex;align-items:center;gap:6px;font-size:13px;margin-bottom:10px;cursor:pointer">
      <input type="checkbox" v-model="autoConvert" />
      Auto-convert to .md
    </label>
    <button class="btn btn-primary" :disabled="loading" @click="uploadFiles">
      <span v-if="loading"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Uploading…</span>
      <span v-else>Upload {{ pendingFiles.length }} file{{ pendingFiles.length !== 1 ? 's' : '' }}</span>
    </button>
  </template>

  <!-- Step 3: conversion in progress -->
  <template v-else-if="converting">
    <div style="font-size:13px;margin-bottom:8px">
      <span class="spinner" style="width:12px;height:12px;border-width:2px;margin-right:6px"></span>
      Converting to .md…
    </div>
    <div style="font-size:12px;color:var(--text-muted)">
      <div v-for="ev in convertEvents" :key="ev.filename + ev.status">
        <span v-if="ev.status === 'converting'">
          <span class="spinner" style="width:10px;height:10px;border-width:2px"></span> {{ ev.filename }}…
        </span>
        <span v-else-if="ev.status === 'done'" style="color:var(--success)">✓ {{ ev.filename }}</span>
        <span v-else-if="ev.status === 'skipped'" style="color:var(--text-muted)">— {{ ev.filename }} (skipped)</span>
        <span v-else-if="ev.status === 'error'" style="color:var(--danger)">✗ {{ ev.filename }}: {{ ev.message }}</span>
      </div>
    </div>
  </template>

  <!-- Step 4: done -->
  <template v-else-if="convertDone">
    <div style="padding:10px;background:#f0fff4;border:1px solid var(--success);border-radius:4px;font-size:13px">
      <div style="color:var(--success);font-weight:600;margin-bottom:4px">✓ Upload &amp; conversion complete</div>
      <div class="text-muted">Go to the <strong>Collections</strong> tab to create a collection from this folder.</div>
    </div>
    <button class="btn btn-secondary btn-sm" style="margin-top:8px"
            @click="convertDone.value = false; convertEvents.value = []">Upload more</button>
  </template>
</div>
`,
})

export { UploadPanel }
