// Cliente HTTP mínimo sobre fetch con token JWT y mensajes de error legibles.
const TOKEN_KEY = 'mf_token'

export const token = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } },
  set: (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* sin storage */ } },
}

export class ApiError extends Error {
  constructor(status, detail) {
    const msg = typeof detail === 'string' ? detail : detail?.mensaje || 'Error inesperado'
    super(msg)
    this.status = status
    this.errores = Array.isArray(detail?.errores) ? detail.errores : []
  }
}

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

async function request(method, url, body, { raw = false } = {}) {
  const headers = {}
  const t = token.get()
  if (t) headers.Authorization = `Bearer ${t}`
  let payload
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(`/api${url}`, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Sin conexión con el servidor')
  }
  if (res.status === 401 && !url.startsWith('/auth/login')) onUnauthorized()
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail } catch { /* no json */ }
    throw new ApiError(res.status, detail)
  }
  if (raw) return res
  return res.status === 204 ? null : res.json()
}

export const api = {
  get: (u) => request('GET', u),
  post: (u, b) => request('POST', u, b),
  put: (u, b) => request('PUT', u, b),
  del: (u) => request('DELETE', u),
  async descargar(u, nombre) {
    const res = await request('GET', u, undefined, { raw: true })
    const cd = res.headers.get('Content-Disposition') || ''
    const m = cd.match(/filename="?([^"]+)"?/)
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = nombre || (m ? m[1] : 'archivo')
    a.click()
    setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  },
  pdfUrl: (cid) => `/api/cotizaciones/${cid}/pdf?token=${encodeURIComponent(token.get() || '')}`,
}

export const qs = (o) => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) p.set(k, v) })
  const s = p.toString()
  return s ? `?${s}` : ''
}
