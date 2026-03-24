import { defineComponent, ref, onMounted } from 'vue'
import { api } from './api.js'

const PromptSelector = defineComponent({
  name: 'PromptSelector',
  props: {
    taskType: { type: String, required: true },
    modelValue: { type: String, default: 'default' },
  },
  emits: ['update:modelValue'],

  setup(props, { emit }) {
    // null = fetch failed, [] = empty, [...names] = loaded
    const prompts = ref([])
    const internalName = ref('default')
    const preview = ref({ system: '', user: '' })

    async function fetchPreview(name) {
      try {
        const raw = await api.get(`/prompts/${props.taskType}/${name}`)
        preview.value = { system: raw.system, user: raw.user }
      } catch {
        preview.value = { system: 'Could not load preview', user: 'Could not load preview' }
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

    return { prompts, internalName, preview, onSelect }
  },

  template: `
<div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">Prompt</label>
    <select
      v-if="prompts === null"
      disabled style="width:100%"
    ><option>Unavailable</option></select>
    <select
      v-else-if="prompts.length === 0"
      disabled style="width:100%"
    ><option>No prompts available</option></select>
    <select
      v-else
      :value="internalName"
      @change="onSelect($event.target.value)"
      style="width:100%"
    >
      <option v-for="name in prompts" :key="name" :value="name">{{ name }}</option>
    </select>
  </div>
  <div class="form-group" style="margin-bottom:10px">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">System prompt</label>
    <textarea
      readonly
      :value="preview.system"
      rows="10"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"
    ></textarea>
  </div>
  <div class="form-group" style="margin-bottom:0">
    <label style="font-size:12px;font-weight:500;color:var(--muted);display:block;margin-bottom:4px">User prompt</label>
    <textarea
      readonly
      :value="preview.user"
      rows="8"
      style="width:100%;background:var(--bg,#f8fafc);font-size:12px;font-family:monospace;color:var(--muted);resize:vertical"
    ></textarea>
  </div>
</div>
`
})

export { PromptSelector }
