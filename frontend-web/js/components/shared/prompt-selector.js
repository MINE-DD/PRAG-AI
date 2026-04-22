import { defineComponent, ref, onMounted } from 'vue'
import { api } from '../../backend-client.js'

const PromptSelector = defineComponent({
  name: 'PromptSelector',
  props: {
    taskType:   { type: String, required: true },
    modelValue: { type: String, default: 'default' },
  },
  emits: ['update:modelValue'],

  setup(props, { emit }) {
    const prompts      = ref([])
    const internalName = ref('default')
    const preview      = ref({ system: '', user: '' })
    const variables    = ref(null)

    async function fetchPreview(name) {
      try {
        const raw = await api.get(`/prompts/${props.taskType}/${name}`)
        preview.value   = { system: raw.system, user: raw.user }
        variables.value = raw.variables && typeof raw.variables === 'object' && !Array.isArray(raw.variables)
          ? raw.variables : null
      } catch {
        preview.value   = { system: 'Could not load preview', user: 'Could not load preview' }
        variables.value = null
      }
    }

    async function onSelect(name) {
      internalName.value = name
      emit('update:modelValue', name)
      await fetchPreview(name)
    }

    onMounted(async () => {
      try {
        const list = await api.get(`/prompts/${props.taskType}`)
        prompts.value = list
        if (list.length === 0) return
        const resolved = list.includes('default') ? 'default' : list[0]
        internalName.value = resolved
        emit('update:modelValue', resolved)
        await fetchPreview(resolved)
      } catch {
        prompts.value = null
        await fetchPreview(internalName.value)
      }
    })

    return { prompts, internalName, preview, variables, onSelect }
  },

  template: `
<div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">Prompt</label>
    <select v-if="prompts === null" disabled style="width:100%"><option>Unavailable</option></select>
    <select v-else-if="prompts.length === 0" disabled style="width:100%"><option>No prompts available</option></select>
    <select v-else :value="internalName" @change="onSelect($event.target.value)" style="width:100%">
      <option v-for="name in prompts" :key="name" :value="name">{{ name }}</option>
    </select>
  </div>
  <div v-if="variables" style="margin-bottom:10px">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">Variables</label>
    <table style="width:100%;border-collapse:collapse;font-size:12px">
      <tr v-for="(desc, name) in variables" :key="name" style="border-top:1px solid var(--border)">
        <td style="padding:4px 8px 4px 0;font-family:monospace;white-space:nowrap;color:var(--primary);vertical-align:top">{{"{"}}{{name}}{{"}"}}</td>
        <td style="padding:4px 0;color:var(--muted);line-height:1.4">{{ desc }}</td>
      </tr>
    </table>
  </div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">System prompt</label>
    <textarea readonly :value="preview.system" rows="10"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"></textarea>
  </div>
  <div class="form-group" style="margin-bottom:0">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">User prompt</label>
    <textarea readonly :value="preview.user" rows="8"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"></textarea>
  </div>
</div>
`,
})

export { PromptSelector }
