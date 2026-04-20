import { defineComponent, ref } from 'vue'
import { api } from '../../api.js'
import { PipelinePanel } from './pipeline-panel.js'

const UploadPanel = defineComponent({
  name: 'UploadPanel',
  components: { PipelinePanel },
  emits: ['files-uploaded', 'pipeline-complete', 'open-collection', 'dismiss'],

  setup(props, { emit }) {
    const uploadDir         = ref('uploads')
    const pendingFiles      = ref(null)
    const fileInputKey      = ref(0)
    const loading           = ref(false)
    const error             = ref(null)
    const uploadPipelineDir = ref('')

    function onFileSelect(evt) {
      const files = evt.target.files
      if (!files.length) { pendingFiles.value = null; return }
      pendingFiles.value = files
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
        emit('files-uploaded', dir)
        uploadPipelineDir.value = dir
        uploadDir.value    = 'uploads'
        pendingFiles.value = null
        fileInputKey.value++
      } catch (e) { error.value = e.message }
      finally { loading.value = false }
    }

    return { uploadDir, pendingFiles, fileInputKey, loading, error, uploadPipelineDir, onFileSelect, uploadFiles }
  },

  template: `
<div class="card" style="margin-bottom:8px">
  <div v-if="error" class="alert alert-error" style="margin-bottom:8px">
    {{ error }}<button class="alert-close" @click="error=null">×</button>
  </div>

  <!-- Step 1: choose files -->
  <template v-if="!pendingFiles">
    <div class="form-group" style="margin-bottom:0">
      <label>Choose PDF files</label>
      <input :key="fileInputKey" type="file" accept=".pdf" multiple @change="onFileSelect"
             :disabled="loading" style="font-size:13px;width:100%;padding:6px 0;" />
    </div>
  </template>

  <!-- Step 2: name the directory and confirm -->
  <template v-else>
    <div style="margin-bottom:12px;font-size:13px">
      <strong>{{ pendingFiles.length }}</strong> file{{ pendingFiles.length !== 1 ? 's' : '' }} selected
      <button class="btn btn-secondary btn-sm" style="margin-left:8px"
              @click="pendingFiles = null; fileInputKey++">Change</button>
    </div>
    <div class="form-group">
      <label>Directory name</label>
      <input type="text" v-model="uploadDir" placeholder="uploads" />
    </div>
    <button class="btn btn-primary" :disabled="loading" @click="uploadFiles">
      <span v-if="loading"><span class="spinner" style="width:12px;height:12px;border-width:2px"></span> Uploading…</span>
      <span v-else>Upload {{ pendingFiles.length }} file{{ pendingFiles.length !== 1 ? 's' : '' }}</span>
    </button>
  </template>

  <pipeline-panel v-if="uploadPipelineDir"
                  :dir-name="uploadPipelineDir"
                  @refresh-collections="$emit('pipeline-complete')"
                  @open-collection="id => $emit('open-collection', id)"
                  @dismiss="uploadPipelineDir = ''; $emit('dismiss')" />
</div>
`,
})

export { UploadPanel }
