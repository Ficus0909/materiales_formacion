<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, qs } from '../api'
import Badge from '../components/Badge.vue'
import Modal from '../components/Modal.vue'
import { useAuth } from '../store'
import { ESTADOS, SEMAFORO, SOPORTE, fecha, fechaHora, money, number, pct, toast, toastError } from '../util'

const props = defineProps({ id: [String, Number] })
const auth = useAuth()
const s = ref(null)
const estadosPost = ref([])
const obs = ref('')
const nuevoPost = ref('')
const obsPost = ref('')
const q = ref('')
const soloAlertas = ref(false)
const verItem = ref(null)
const procesando = ref(false)

async function cargar() {
  try {
    s.value = await api.get(`/solicitudes/${props.id}`)
    if (auth.esAdmin && s.value.estado === 'ENVIADA') {
      await api.post(`/solicitudes/${props.id}/revisar`)
      s.value = await api.get(`/solicitudes/${props.id}`)
    }
    estadosPost.value = (await api.get('/estados-post')).filter((e) => e.activo)
  } catch (e) { toastError(e) }
}
onMounted(cargar)
watch(() => props.id, cargar)

const actual = computed(() => estadosPost.value.find((e) => e.id === s.value?.estado_post_id))
const siguientes = computed(() => estadosPost.value.filter((e) => !actual.value || e.orden > actual.value.orden))
const pendiente = computed(() => ['ENVIADA', 'EN_REVISION'].includes(s.value?.estado))
const items = computed(() => (s.value?.items || []).filter((i) => (!q.value || i.nombre.toLowerCase().includes(q.value.toLowerCase()))
  && (!soloAlertas.value || ['naranja', 'rojo'].includes(i.analisis.semaforo) || i.analisis.soporte !== 'COMPLETO')))
const alertas = computed(() => (s.value?.items || []).filter((i) => ['naranja', 'rojo'].includes(i.analisis.semaforo) || i.analisis.soporte !== 'COMPLETO').length)

// Stepper de dos fases: gestión + compra
const pasos = computed(() => {
  if (!s.value) return []
  const fechas = {}
  s.value.historial.forEach((h) => { fechas[h.estado_nuevo] = h.fecha })
  const gestion = ['BORRADOR', 'ENVIADA', 'EN_REVISION']
  const final = ['RECHAZADA', 'CANCELADA', 'DEVUELTA'].includes(s.value.estado) ? s.value.estado : 'APROBADA'
  const lista = [...gestion, final].map((e) => ({ clave: e, label: ESTADOS[e].label }))
  if (final === 'APROBADA') estadosPost.value.forEach((e) => lista.push({ clave: e.nombre, label: e.nombre, post: e }))
  const actualClave = s.value.estado_visible
  const idx = lista.findIndex((p) => p.clave === actualClave)
  return lista.map((p, i) => ({ ...p, fecha: fechas[p.clave], estado: i < idx ? 'done' : i === idx ? (['RECHAZADA', 'CANCELADA'].includes(p.clave) ? 'bad' : 'done cur') : '' }))
})

async function decidir(accion) {
  if (accion !== 'APROBAR' && !obs.value.trim()) return toast('Las observaciones son obligatorias para devolver o rechazar', 'error')
  const txt = { APROBAR: 'aprobar', RECHAZAR: 'RECHAZAR (la solicitud queda cerrada y no se puede reabrir)', DEVOLVER: 'devolver al líder para corrección' }[accion]
  if (!confirm(`¿Confirma ${txt}?`)) return
  procesando.value = true
  try {
    s.value = await api.post(`/solicitudes/${props.id}/decidir`, { accion, observaciones: obs.value })
    obs.value = ''
    toast('Decisión registrada y notificada al líder')
  } catch (e) { toastError(e) } finally { procesando.value = false }
}
async function avanzar() {
  if (!obsPost.value.trim()) return toast('Las observaciones son obligatorias', 'error')
  procesando.value = true
  try {
    s.value = await api.post(`/solicitudes/${props.id}/avanzar`, { estado_post_id: nuevoPost.value, observaciones: obsPost.value })
    obsPost.value = ''
    nuevoPost.value = ''
    toast('Estado actualizado')
  } catch (e) { toastError(e) } finally { procesando.value = false }
}
</script>

<template>
  <div v-if="s">
    <div class="page-head">
      <div>
        <div class="sub"><router-link :to="auth.esAdmin || auth.esManager ? '/admin/solicitudes' : '/lider/seguimiento'">‹ Volver</router-link></div>
        <h1>Solicitud #{{ s.id }} · {{ s.lote }} <Badge :estado="s.estado" :texto="s.estado_visible !== s.estado ? s.estado_visible : ''" :color="s.estado_post_color" /></h1>
        <div class="sub"><span v-if="auth.esManager">{{ s.centro }} · </span>Vigencia {{ s.vigencia }} · Líder {{ s.lider }} · {{ s.n_items }} artículos · Enviada {{ fecha(s.fecha_envio) }}<span v-if="s.reenvios"> · {{ s.reenvios }} reenvío(s)</span></div>
      </div>
      <div class="row">
        <div class="card" style="padding:10px 16px"><div class="small muted">Valor estimado</div><div style="font-size:20px;font-weight:700" class="mono">{{ money(s.total) }}</div></div>
        <button v-if="auth.esAdmin || auth.esManager" class="btn ghost" @click="api.descargar(`/analisis/exportar${qs({ vigencia_id: s.vigencia_id, lote_id: s.lote_id })}`)">Formato análisis de precios</button>
      </div>
    </div>

    <div class="card">
      <div class="stepper">
        <div v-for="p in pasos" :key="p.clave" class="step" :class="p.estado">
          <div class="c">{{ p.estado.includes('done') && !p.estado.includes('cur') ? '✓' : p.estado === 'bad' ? '✕' : '' }}</div>
          <div><b v-if="p.estado.includes('cur') || p.estado === 'bad'">{{ p.label }}</b><span v-else>{{ p.label }}</span></div>
          <div class="small muted">{{ p.fecha ? fecha(p.fecha) : '' }}</div>
        </div>
      </div>
    </div>

    <div v-if="s.observaciones_admin && ['DEVUELTA', 'RECHAZADA'].includes(s.estado)" class="alert warn" style="margin-top:16px"><b>Observaciones del administrador:</b> {{ s.observaciones_admin }}</div>

    <div class="card">
      <div class="row" style="justify-content:space-between;margin-bottom:10px">
        <h2 style="margin:0">Artículos solicitados</h2>
        <div class="row">
          <input v-model="q" placeholder="Buscar…" />
          <label v-if="auth.esAdmin || auth.esManager" class="row small" style="gap:6px"><input v-model="soloAlertas" type="checkbox" /> Sólo alertas ({{ alertas }})</label>
        </div>
      </div>
      <div class="table-wrap tall">
        <table>
          <thead><tr><th>UNSPSC</th><th>Artículo</th><th class="right">Cantidad</th><th class="right">Precio unitario</th><th class="right">Subtotal</th><th>Soporte</th><th class="right">Dispersión</th><th>Cotizaciones</th></tr></thead>
          <tbody>
            <tr v-for="i in items" :key="i.id">
              <td class="mono">{{ i.codigo_unspsc }}</td>
              <td>{{ i.nombre }}<div class="small muted">{{ i.unidad }}<span v-if="i.observacion"> · {{ i.observacion }}</span></div></td>
              <td class="right">{{ number(i.cantidad) }}</td>
              <td class="right mono">{{ money(i.precio_unitario) }}<div v-if="i.precio_congelado" class="small muted">congelado</div></td>
              <td class="right mono">{{ money(i.subtotal) }}</td>
              <td><span class="badge" :style="{ background: SOPORTE[i.analisis.soporte].color }" :title="SOPORTE[i.analisis.soporte].ayuda">{{ SOPORTE[i.analisis.soporte].label }}</span></td>
              <td class="right nowrap"><span class="dot" :style="{ background: SEMAFORO[i.analisis.semaforo] }" />{{ pct(i.analisis.dispersion_final) }}<span v-if="i.analisis.semaforo === 'rojo'" title="Dispersión alta"> ⚠</span></td>
              <td class="nowrap">
                <button class="link small" @click="verItem = i">{{ i.analisis.n_validas }}/{{ i.analisis.n_cotizaciones }} ver</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="auth.esAdmin && pendiente" class="card">
      <h2>Decisión</h2>
      <p class="sub">Revise precios, soportes y dispersión. Para ajustar precios (excluir atípicos, método o precio de experto) use
        <router-link :to="`/admin/analisis?lote=${s.lote_id}`">Análisis de precios</router-link>. Al aprobar, los precios se congelan y se registran como históricos.</p>
      <label class="f"><span>Observaciones (obligatorias para devolver o rechazar)</span><textarea v-model="obs" rows="3" placeholder="Indique al líder qué debe corregir…" /></label>
      <div class="row" style="margin-top:12px;justify-content:flex-end">
        <button class="btn amarillo" :disabled="procesando" @click="decidir('DEVOLVER')">Devolver</button>
        <button class="btn rojo" :disabled="procesando" @click="decidir('RECHAZAR')">Rechazar</button>
        <button class="btn" :disabled="procesando" @click="decidir('APROBAR')">Aprobar</button>
      </div>
    </div>

    <div v-if="s.estado === 'APROBADA'" class="card">
      <h2>Ciclo de compra</h2>
      <template v-if="auth.esAdmin">
        <div v-if="siguientes.length" class="form-grid">
          <label class="f req"><span>Nuevo estado (sólo avanza)</span>
            <select v-model="nuevoPost"><option value="" disabled>Seleccione…</option><option v-for="e in siguientes" :key="e.id" :value="e.id">{{ e.nombre }}</option></select>
          </label>
          <label class="f req"><span>Observaciones</span><input v-model="obsPost" placeholder="Ej. OC #2026-045 emitida" /></label>
          <div class="f" style="justify-content:flex-end"><button class="btn" :disabled="!nuevoPost || procesando" @click="avanzar">Actualizar estado</button></div>
        </div>
        <div v-else class="alert ok">La solicitud completó el ciclo de compra.</div>
      </template>
      <div v-else-if="auth.esManager" class="alert info">El administrador del centro actualiza los estados del ciclo de compra.</div>
      <div v-else class="alert info">Sólo el administrador actualiza los estados del ciclo de compra. Usted recibirá una notificación en cada cambio.</div>
    </div>

    <div class="card">
      <h2>Historial</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Fecha</th><th>Estado</th><th>Responsable</th><th>Observaciones</th></tr></thead>
          <tbody><tr v-for="(h, k) in [...s.historial].reverse()" :key="k">
            <td class="nowrap">{{ fechaHora(h.fecha) }}</td>
            <td class="nowrap"><span class="muted small" v-if="h.estado_anterior">{{ ESTADOS[h.estado_anterior]?.label || h.estado_anterior }} → </span><b>{{ ESTADOS[h.estado_nuevo]?.label || h.estado_nuevo }}</b></td>
            <td>{{ h.usuario }}</td><td>{{ h.observaciones }}</td>
          </tr></tbody>
        </table>
      </div>
    </div>

    <Modal v-if="verItem" :titulo="verItem.nombre" ancho="720px" @cerrar="verItem = null">
      <p class="sub">{{ verItem.analisis.justificacion }}</p>
      <table>
        <thead><tr><th>Ref.</th><th>Proveedor</th><th>Fecha</th><th class="right">Precio IVA incl.</th><th>Soporte</th></tr></thead>
        <tbody>
          <tr v-for="c in verItem.analisis.cotizaciones" :key="c.item_id" :class="{ dis: c.excluido }">
            <td>{{ c.etiqueta }}</td><td>{{ c.proveedor }}<div v-if="c.excluido" class="small">Excluida: {{ c.motivo }}</div></td><td>{{ fecha(c.fecha) }}</td>
            <td class="right mono">{{ money(c.precio) }}</td><td><a :href="api.pdfUrl(c.cotizacion_id)" target="_blank" rel="noopener">📄 PDF</a></td>
          </tr>
          <tr v-for="h in verItem.analisis.historicos" :key="h.anio"><td>Hist.</td><td>Contratación {{ h.anio }} (indexado ×{{ h.factor.toFixed(3) }})</td><td></td><td class="right mono">{{ money(h.indexado) }}</td><td></td></tr>
        </tbody>
      </table>
      <p style="margin-top:12px">Método: <b>{{ verItem.analisis.metodo || '—' }}</b> · Precio estimado: <b>{{ money(verItem.analisis.precio_estimado) }}</b> · Dispersión final: <b>{{ pct(verItem.analisis.dispersion_final) }}</b></p>
    </Modal>
  </div>
  <div v-else class="card"><div class="skeleton" v-for="i in 6" :key="i" /></div>
</template>
