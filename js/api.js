/* API wrapper & utilities */
const api = {
  url: () => localStorage.getItem('prag_backend_url') || 'http://localhost:8000',

  async get(path) {
    const r = await fetch(api.url() + path)
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async post(path, body = {}) {
    const r = await fetch(api.url() + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async del(path) {
    const r = await fetch(api.url() + path, { method: 'DELETE' })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.status === 204 ? null : r.json()
  },

  async patch(path, body = {}) {
    const r = await fetch(api.url() + path, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async upload(path, formData) {
    const r = await fetch(api.url() + path, { method: 'POST', body: formData })
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
    return r.json()
  },

  async download(path) {
    const r = await fetch(api.url() + path)
    if (!r.ok) throw new Error(`${r.status}`)
    return r.blob()
  },
}

/* ═══════════════════════════════════════════════
   SHARED UTILITY
═══════════════════════════════════════════════ */
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export { api, downloadBlob }
