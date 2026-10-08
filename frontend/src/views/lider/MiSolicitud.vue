<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import Modal from '../../components/Modal.vue'
import { SEMAFORO, SOPORTE, debounce, fecha, fechaHora, money, number, toast, toastError } from '../../util'

const data = ref(null)
const q = ref('')
const filtro = ref('todos')
const pendientes = new Map() // articulo_id -> cantidad (0 = retirar)
const estadoGuardado = ref('guardado') // guardado | pendiente | guardando | error
const errores = ref([])
const clonar = ref(null)
const origenSel = ref(null)
const importando = ref(false)

const s = computed(() => data.value?.solicitud)
const editable = computed(() => s.value && ['BORRADOR', 'DEVUELTA'].includes(s.value.estado))
const catalogo = computed(() => data.value?.catalogo || [])
const seleccionados = computed(() => catalogo.value.filter((a) => a.seleccionado))
const conPrecio = computed(() => catalogo.value.filter((a) => a.precio_estimado !== null).length)
const total = computed(() => seleccionados.value.reduce((t, a) => t + (a.precio_estimado || 0) * (a.cantidad || 0), 0))
const filas = computed(() => {
  const t = q.value.toLowerCase()
  return catalogo.value.filter((a) => {
    if (t && !a.nombre.toLowerCase().includes(t) && !a.codigo_unspsc.startsWith(t)) return false
    if (filtro.value === 'disponibles') return a.precio_estimado !== null
    if (filtro.value === 'seleccionados') return a.seleccionado
    if (filtro.value === 'sin') return a.precio_estimado === null
    return true
  })
})

async function cargar() {
  try { data.value = await api.get('/solicitudes/mia') } catch (e) { toastError(e) }
}

const guardar = debounce(async () => {
  if (!pendientes.size || !s.value) return
  const lote = [...pendientes].map(([articulo_id, cantidad]) => ({ articulo_id, cantidad }))
  pendientes.clear()
  estadoGuardado.value = 'guardando'
  try {
    const r = await api.put(`/solicitudes/${s.value.id}/items`, lote)
    s.value.actualizado = r.actualizado
    s.value.n_items = r.n_items
    estadoGuardado.value = pendientes.size ? 'pendiente' : 'guardado'
  } catch (e) {
    lote.forEach((i) => { if (!pendientes.has(i.articulo_id)) pendientes.set(i.articulo_id, i.cantidad) })
    estadoGuardado.value = 'error'
    toastError(e)
  }
}, 1200)

function marcar(a) {
  pendientes.set(a.id, a.seleccionado ? (a.cantidad || 0) : 0)
  estadoGuardado.value = 'pendiente'
  guardar()
}
function toggle(a) {
  a.seleccionado = !a.seleccionado
  if (a.seleccionado && !a.cantidad) a.cantidad = 1
  marcar(a)
}
function cambiarCantidad(a) {
  if (a.cantidad === '' || a.cantidad === null || a.cantidad < 0) return
  a.seleccionado = a.cantidad > 0
  marcar(a)
}
function seleccionarVisibles() {
  filas.value.filter((a) => !a.seleccionado && a.precio_estimado !== null).forEach((a) => { a.seleccionado = true; a.cantidad = a.cantidad || 1; marcar(a) })
}

async function enviar() {
  await guardar.flush()
  errores.value = []
  if (!confirm(`¿Enviar la solicitud con ${seleccionados.value.length} artículos por ${money(total.value)}? Después de enviarla no podrá editarla salvo que sea devuelta.`)) return
  try {
    await api.post(`/solicitudes/${s.value.id}/enviar`)
    toast('Solicitud enviada al administrador')
    cargar()
  } catch (e) {
    errores.value = e.errores
    if (!e.errores.length) toastError(e)
  }
}

async function importar(ev) {
  const f = ev.target.files[0]
  ev.target.value = ''
  if (!f) return
  await guardar.flush()
  if (!confirm('La plantilla reemplaza las cantidades de toda la solicitud (lo que no esté en la plantilla se retira). ¿Continuar?')) return
  importando.value = true
  const fd = new FormData()
  fd.append('archivo', f)
  try {
    const r = await api.post(`/solicitudes/${s.value.id}/importar`, fd)
    toast(`Importado: ${r.agregados} agregados, ${r.actualizados} actualizados, ${r.retirados} retirados`)
    cargar()
  } catch (e) { toastError(e) } finally { importando.value = false }
}

async function abrirClonar() {
  await guardar.flush()
  try {
    clonar.value = await api.get(`/solicitudes/${s.value.id}/clonables`)
    origenSel.value = clonar.value[0]?.id || null
  } catch (e) { toastError(e) }
}
const origen = computed(() => clonar.value?.find((o) => o.id === origenSel.value))
const conteoClon = computed(() => {
  const c = { LISTO: 0, PENDIENTE_PRECIO: 0, NO_DISPONIBLE: 0 }
  origen.value?.vista.forEach((v) => { c[v.estado]++ })
  return c
})
async function confirmarClon() {
  try {
    const r = await api.post(`/solicitudes/${s.value.id}/clonar`, { origen_id: origenSel.value })
    toast(`Clonado: ${r.agregados} artículos agregados${r.omitidos ? `, ${r.omitidos} no disponibles omitidos` : ''}${r.pendientes_precio ? `, ${r.pendientes_precio} pendientes de precio` : ''}`)
    clonar.value = null
    cargar()
  } catch (e) { toastError(e) }
}

const salir = (e) => { if (pendientes.size) { guardar.flush(); e.preventDefault() } }
onMounted(() => { cargar(); window.addEventListener('beforeunload', salir) })
onBeforeUnmount(() => window.removeEventListener('beforeunload', salir))
onBeforeRouteLeave(() => { if (pendientes.size) guardar.flush() })
const ESTADO_CLON = { LISTO: ['Listo', '#39A909'], PENDIENTE_PRECIO: ['Pte. precio', '#C99A00'], NO_DISPONIBLE: ['No disponible', '#DC3545'] }
</script>

<template>
  <div>
    <div v-if="data && !data.vigencia" class="alert info">No hay una vigencia abierta: no es posible crear solicitudes en este momento.</div>
    <template v-if="s">
      <div class="page-head">
        <div>
          <h1>Mi solicitud · Vigencia {{ data.vigencia.codigo }} <Badge :estado="s.estado" :texto="s.estado_visible !== s.estado ? s.estado_visible : ''" /></h1>
          <div class="sub">
            Lote {{ s.lote }} · Cierre {{ fecha(data.vigencia.fecha_cierre) }}
            <template v-if="editable"> · Autoguardado:
              <b :style="{ color: estadoGuardado === 'error' ? 'var(--rojo)' : 'var(--verde)' }">{{ { guardado: 'al día', pendiente: 'cambios pendientes…', guardando: 'guardando…', error: 'error al guardar' }[estadoGuardado] }}</b>
              · Última modificación {{ fechaHora(s.actualizado) }}
            </template>
          </div>
        </div>
        <div v-if="editable" class="row">
          <button class="btn ghost" @click="api.descargar(`/solicitudes/${s.id}/plantilla`)">Descargar plantilla</button>
          <label class="btn ghost" :class="{ disabled: importando }">Importar cantidades<input type="file" accept=".xlsx" hidden @change="importar" /></label>
          <button class="btn outline" @click="abrirClonar">Clonar anterior</button>
        </div>
      </div>

      <div v-if="s.estado === 'DEVUELTA'" class="alert warn"><b>Devuelta por el administrador:</b> {{ s.observaciones_admin }}<br>Corrija y vuelva a enviar.</div>
      <div v-if="!editable" class="alert info">La solicitud está en estado <b>{{ s.estado_visible }}</b> y no se puede editar. Consulte su avance en <router-link to="/lider/seguimiento">Seguimiento</router-link>.</div>
      <div v-else class="alert info">Seleccione los materiales que su lote necesita para la vigencia e indique la cantidad. Sólo los artículos con <b>precio de referencia</b> (cotización o histórico) son seleccionables. Hay <b>una solicitud por lote y vigencia</b>.</div>
      <div v-if="data.inactivos?.length" class="alert error">Estos artículos fueron retirados del listado maestro y deben quitarse: {{ data.inactivos.map((i) => i.nombre).join(', ') }}</div>
      <div v-if="errores.length" class="alert error"><b>No se pudo enviar:</b><ul><li v-for="e in errores" :key="e">{{ e }}</li></ul></div>

      <div class="row" style="margin-bottom:10px">
        <input v-model="q" placeholder="Buscar artículo o código…" class="grow" style="max-width:360px" />
        <select v-model="filtro">
          <option value="todos">Todos ({{ catalogo.length }})</option>
          <option value="disponibles">Sólo disponibles ({{ conPrecio }})</option>
          <option value="seleccionados">Seleccionados ({{ seleccionados.length }})</option>
          <option value="sin">Sin precio ({{ catalogo.length - conPrecio }})</option>
        </select>
        <button v-if="editable" class="btn ghost sm" @click="seleccionarVisibles">Seleccionar visibles disponibles</button>
      </div>

      <div class="table-wrap tall">
        <table>
          <thead><tr><th style="width:34px"></th><th>Código</th><th>Artículo</th><th>Unidad</th><th class="right">Cotiz.</th><th class="right">Precio ref.</th><th class="right">Cantidad</th><th class="right">Subtotal</th><th>Estado</th></tr></thead>
          <tbody>
            <tr v-for="a in filas" :key="a.id" :class="{ dis: a.precio_estimado === null && !a.seleccionado }">
              <td><input type="checkbox" :checked="a.seleccionado" :disabled="!editable || (a.precio_estimado === null && !a.seleccionado)" :aria-label="`Seleccionar ${a.nombre}`" @change="toggle(a)" /></td>
              <td class="mono">{{ a.codigo_unspsc }}</td>
              <td :title="a.descripcion">{{ a.nombre }}</td>
              <td>{{ a.unidad }}</td>
              <td class="right">{{ a.n_cotizaciones }}</td>
              <td class="right mono nowrap"><span v-if="a.precio_estimado !== null" class="dot" :style="{ background: SEMAFORO[a.semaforo] }" />{{ money(a.precio_estimado) }}</td>
              <td class="right">
                <input v-if="editable" v-model.number="a.cantidad" type="number" min="0" step="any" class="cant" :disabled="a.precio_estimado === null && !a.seleccionado" @input="cambiarCantidad(a)" />
                <span v-else>{{ number(a.cantidad) }}</span>
              </td>
              <td class="right mono">{{ a.seleccionado ? money((a.precio_estimado || 0) * (a.cantidad || 0)) : '' }}</td>
              <td>
                <span v-if="a.seleccionado && a.precio_estimado === null" class="badge" style="background:#C99A00">Pte. precio</span>
                <span v-else-if="a.seleccionado" class="badge" style="background:var(--verde)">Seleccionado</span>
                <span v-else class="badge" :style="{ background: SOPORTE[a.soporte].color }" :title="SOPORTE[a.soporte].ayuda">{{ a.precio_estimado === null ? 'Sin precio' : 'Disponible' }}</span>
              </td>
            </tr>
            <tr v-if="!filas.length"><td colspan="9" class="empty">Sin artículos para el filtro</td></tr>
          </tbody>
        </table>
      </div>

      <div class="card resumen">
        <span><b>{{ seleccionados.length }}</b> artículos seleccionados de <b>{{ conPrecio }}</b> disponibles · {{ catalogo.length - conPrecio }} sin precio (no seleccionables)</span>
        <span class="grow" />
        <span>Valor estimado: <b class="mono">{{ money(total) }}</b></span>
        <button v-if="editable" class="btn azul" :disabled="!seleccionados.length" @click="enviar">{{ s.estado === 'DEVUELTA' ? 'REENVIAR' : 'ENVIAR' }}</button>
      </div>
    </template>
    <div v-else-if="!data" class="card"><div class="skeleton" v-for="i in 6" :key="i" /></div>

    <Modal v-if="clonar" titulo="Clonar solicitud anterior" ancho="820px" @cerrar="clonar = null">
      <div v-if="!clonar.length" class="empty">No hay solicitudes aprobadas de vigencias anteriores para su lote.</div>
      <template v-else>
        <div class="table-wrap" style="margin-bottom:12px">
          <table>
            <thead><tr><th></th><th>Vigencia</th><th>Estado</th><th class="right">Artículos</th></tr></thead>
            <tbody><tr v-for="o in clonar" :key="o.id" class="click" @click="origenSel = o.id">
              <td><input type="radio" :checked="origenSel === o.id" /></td><td>{{ o.vigencia }}</td><td><Badge :estado="o.estado" :texto="o.estado_visible" /></td><td class="right">{{ o.n_items }}</td>
            </tr></tbody>
          </table>
        </div>
        <template v-if="origen">
          <div class="row small" style="margin-bottom:8px">
            <span class="badge" style="background:#39A909">{{ conteoClon.LISTO }} listos</span>
            <span class="badge" style="background:#C99A00">{{ conteoClon.PENDIENTE_PRECIO }} pendientes de precio</span>
            <span class="badge" style="background:#DC3545">{{ conteoClon.NO_DISPONIBLE }} no disponibles</span>
          </div>
          <div class="table-wrap" style="max-height:34vh;overflow:auto">
            <table><tbody><tr v-for="v in origen.vista" :key="v.articulo_id">
              <td>{{ v.nombre }}</td><td class="right">{{ number(v.cantidad) }}</td>
              <td><span class="badge" :style="{ background: ESTADO_CLON[v.estado][1] }">{{ ESTADO_CLON[v.estado][0] }}</span></td>
            </tr></tbody></table>
          </div>
          <div class="alert warn" style="margin-top:10px">Se copian artículos y cantidades (no precios). Los «no disponibles» se omiten; los ya incluidos no se duplican; los «pendientes de precio» no podrán enviarse hasta cargar su cotización.</div>
        </template>
      </template>
      <template #pie><button class="btn ghost" @click="clonar = null">Cancelar</button><button class="btn" :disabled="!origenSel" @click="confirmarClon">CLONAR</button></template>
    </Modal>
  </div>
</template>

<style scoped>
.resumen { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 12px; border-color: var(--verde); background: #F6FBF3; position: sticky; bottom: 8px; }
.disabled { opacity: .5; pointer-events: none; }
</style>
