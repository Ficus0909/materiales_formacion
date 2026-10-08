import { reactive } from 'vue'

const cop = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 })
const num = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 })

export const money = (v) => (v === null || v === undefined ? '—' : cop.format(v))
export const number = (v) => (v === null || v === undefined ? '—' : num.format(v))
export const pct = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)} %`)
export const fecha = (v) => (v ? new Date(v.length === 10 ? `${v}T00:00:00` : v).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' }) : '—')
export const fechaHora = (v) => (v ? new Date(v).toLocaleString('es-CO', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—')
export const hoyISO = () => new Date().toISOString().slice(0, 10)

export const ESTADOS = {
  BORRADOR: { label: 'Borrador', color: '#718096' },
  ENVIADA: { label: 'Enviada', color: '#1E3A5F' },
  EN_REVISION: { label: 'En revisión', color: '#FD7E14' },
  APROBADA: { label: 'Aprobada', color: '#39A909' },
  RECHAZADA: { label: 'Rechazada', color: '#DC3545' },
  DEVUELTA: { label: 'Devuelta', color: '#C99A00' },
  CANCELADA: { label: 'Cancelada', color: '#4A5568' },
  PROGRAMADA: { label: 'Programada', color: '#718096' },
  ABIERTA: { label: 'Abierta', color: '#39A909' },
  CERRADA: { label: 'Cerrada', color: '#1E3A5F' },
  PENDIENTE: { label: 'Pendiente', color: '#FD7E14' },
}

export const SOPORTE = {
  COMPLETO: { label: 'Cotizado', color: '#39A909', ayuda: 'Cumple el mínimo de cotizaciones de proveedores diferentes' },
  INSUFICIENTE: { label: 'Cotización insuficiente', color: '#FD7E14', ayuda: 'Tiene cotizaciones pero menos del mínimo exigido' },
  HISTORICO: { label: 'Precio histórico', color: '#17A2B8', ayuda: 'Se usa el promedio de precios históricos indexados' },
  EXPERTO: { label: 'Precio experto', color: '#71277A', ayuda: 'Precio fijado por el analista' },
  SIN_PRECIO: { label: 'Sin precio', color: '#A0AEC0', ayuda: 'No tiene cotizaciones ni históricos: no se puede solicitar' },
}

export const SEMAFORO = { verde: '#39A909', naranja: '#FD7E14', rojo: '#DC3545', gris: '#A0AEC0' }

// Notificaciones tipo "toast"
export const toasts = reactive([])
export function toast(msg, tipo = 'ok', ms = 4000) {
  const t = { id: Math.random(), msg, tipo }
  toasts.push(t)
  setTimeout(() => { const i = toasts.indexOf(t); if (i >= 0) toasts.splice(i, 1) }, ms)
}
export function toastError(e) {
  const extra = e?.errores?.length ? `: ${e.errores.slice(0, 4).join(' · ')}${e.errores.length > 4 ? '…' : ''}` : ''
  toast(`${e?.message || e}${extra}`, 'error', 7000)
}

export function debounce(fn, ms) {
  let t
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms) }
  d.flush = (...a) => { clearTimeout(t); return fn(...a) }
  return d
}
