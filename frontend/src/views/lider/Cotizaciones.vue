<script setup>
import { computed, onMounted, ref } from 'vue'
import { api, qs } from '../../api'
import Modal from '../../components/Modal.vue'
import { useAuth } from '../../store'
import { SEMAFORO, SOPORTE, fecha, hoyISO, money, pct, toast, toastError } from '../../util'

const auth = useAuth()
const vig = computed(() => auth.vigencia)
const tab = ref('cotizaciones')
const cotizaciones = ref([])
const analisis = ref(null)
const proveedores = ref([])
const form = ref(null) // { id?, proveedor_id, fecha, pdf, archivo, precios: {id: valor}, modo }
const q = ref('')
const soloSin = ref(false)
const nuevoProv = ref(null)
const guardando = ref(false)
const arrastrando = ref(false)

async function cargar() {
  if (!vig.value) return
  try {
    const [c, a] = await Promise.all([api.get(`/cotizaciones${qs({ vigencia_id: vig.value.id })}`),
      api.get(`/analisis${qs({ vigencia_id: vig.value.id })}`)])
    cotizaciones.value = c
    analisis.value = a
  } catch (e) { toastError(e) }
}
async function cargarProveedores() { proveedores.value = (await api.get('/proveedores')).filter((p) => p.activo) }

const filtrados = computed(() => {
  const t = q.value.toLowerCase()
  return (analisis.value?.items || []).filter((i) => (!t || i.articulo.nombre.toLowerCase().includes(t) || i.articulo.codigo_unspsc.startsWith(t))
    && (!soloSin.value || i.n_validas === 0))
})
const usados = computed(() => new Set(cotizaciones.value.map((c) => c.proveedor.id)))
const nPrecios = computed(() => Object.values(form.value?.precios || {}).filter((v) => Number(v) > 0).length)

function nueva() {
  form.value = { proveedor_id: '', fecha: hoyISO(), pdf: null, archivo: null, precios: {}, modo: 'grilla' }
}
async function editar(c) {
  const d = await api.get(`/cotizaciones/${c.id}`)
  form.value = { id: c.id, etiqueta: c.etiqueta, proveedor: c.proveedor, fecha: c.fecha, pdf: null, archivo: null, modo: 'grilla',
    precios: Object.fromEntries(d.items.map((i) => [i.articulo_id, i.precio])) }
}
function soltar(ev) {
  arrastrando.value = false
  const f = ev.dataTransfer.files[0]
  if (f) elegirPdf(f)
}
function elegirPdf(f) {
  if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) return toast('El soporte debe ser un PDF', 'error')
  if (f.size > 10 * 1024 * 1024) return toast('El PDF supera 10 MB', 'error')
  form.value.pdf = f
}
async function guardar() {
  const f = form.value
  if (!f.id && !f.pdf) return toast('Adjunte el PDF de la cotización (obligatorio)', 'error')
  if (f.modo === 'excel' && !f.archivo && !f.id) return toast('Adjunte la plantilla de precios diligenciada', 'error')
  const fd = new FormData()
  if (!f.id) fd.append('proveedor_id', f.proveedor_id)
  fd.append('fecha', f.fecha)
  if (f.pdf) fd.append('pdf', f.pdf)
  if (f.modo === 'excel' && f.archivo) fd.append('archivo_precios', f.archivo)
  else fd.append('precios', JSON.stringify(Object.fromEntries(Object.entries(f.precios).filter(([, v]) => Number(v) > 0))))
  guardando.value = true
  try {
    if (f.id) await api.put(`/cotizaciones/${f.id}`, fd)
    else await api.post('/cotizaciones', fd)
    toast('Cotización guardada. Los artículos cotizados quedan habilitados para la solicitud.')
    form.value = null
    cargar()
  } catch (e) { toastError(e) } finally { guardando.value = false }
}
async function eliminar(c) {
  if (!confirm(`¿Eliminar la cotización ${c.etiqueta} de ${c.proveedor.razon_social}?`)) return
  try { await api.del(`/cotizaciones/${c.id}`); toast('Cotización eliminada'); cargar() } catch (e) { toastError(e) }
}
async function crearProveedor() {
  try {
    const p = await api.post('/proveedores', nuevoProv.value)
    await cargarProveedores()
    form.value.proveedor_id = p.id
    nuevoProv.value = null
  } catch (e) { toastError(e) }
}
onMounted(() => { cargar(); cargarProveedores() })
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Cotizaciones de proveedores</h1><div class="sub">Lote {{ auth.usuario.lote?.nombre }} · Vigencia {{ vig?.codigo || '—' }}</div></div>
      <div v-if="vig" class="row">
        <button class="btn ghost" @click="api.descargar(`/cotizaciones/plantilla${qs({ vigencia_id: vig.id })}`)">Descargar plantilla Excel</button>
        <button class="btn" @click="nueva">+ Nueva cotización</button>
      </div>
    </div>
    <div v-if="!vig" class="alert info">No hay una vigencia abierta.</div>
    <template v-else>
      <div class="alert info">Cada cotización es <b>un documento PDF de un proveedor</b> con precios (IVA incluido) para uno o varios artículos del lote.
        Se requieren cotizaciones de proveedores <b>diferentes</b>; máximo 3 por artículo. Puede digitar los precios o cargar la plantilla Excel diligenciada.</div>
      <div class="tabs">
        <button :class="{ on: tab === 'cotizaciones' }" @click="tab = 'cotizaciones'">Documentos ({{ cotizaciones.length }})</button>
        <button :class="{ on: tab === 'cobertura' }" @click="tab = 'cobertura'">Cobertura por artículo</button>
      </div>

      <div v-if="tab === 'cotizaciones'" class="table-wrap">
        <table>
          <thead><tr><th>Ref.</th><th>Proveedor</th><th>Fecha</th><th class="right">Artículos cotizados</th><th>Soporte</th><th></th></tr></thead>
          <tbody>
            <tr v-for="c in cotizaciones" :key="c.id">
              <td><b>{{ c.etiqueta }}</b></td><td>{{ c.proveedor.razon_social }}<div class="small muted">NIT {{ c.proveedor.nit }}</div></td>
              <td>{{ fecha(c.fecha) }}</td><td class="right">{{ c.n_items }}</td>
              <td><a :href="api.pdfUrl(c.id)" target="_blank" rel="noopener">📄 {{ c.pdf_nombre }}</a></td>
              <td class="nowrap right"><button class="btn ghost sm" @click="editar(c)">Editar</button> <button class="btn ghost sm" style="color:var(--rojo)" @click="eliminar(c)">Eliminar</button></td>
            </tr>
            <tr v-if="!cotizaciones.length"><td colspan="6" class="empty">Aún no ha cargado cotizaciones en esta vigencia</td></tr>
          </tbody>
        </table>
      </div>

      <div v-else>
        <div class="row" style="margin-bottom:10px">
          <input v-model="q" placeholder="Buscar artículo…" style="max-width:340px" class="grow" />
          <label class="row small" style="gap:6px"><input v-model="soloSin" type="checkbox" /> Sólo sin cotización</label>
          <span class="sub" v-if="analisis">{{ analisis.resumen.con_precio }} de {{ analisis.resumen.total }} con precio de referencia</span>
        </div>
        <div class="table-wrap tall">
          <table>
            <thead><tr><th>Artículo</th><th class="right">Cotizaciones</th><th class="right">Precio estimado</th><th class="right">Dispersión</th><th>Soporte</th></tr></thead>
            <tbody>
              <tr v-for="i in filtrados" :key="i.articulo_id">
                <td>{{ i.articulo.nombre }}<div class="small muted">{{ i.articulo.codigo_unspsc }} · {{ i.articulo.unidad }}</div></td>
                <td class="right">{{ i.cotizaciones.map((c) => c.etiqueta).join(', ') || '—' }}</td>
                <td class="right mono">{{ money(i.precio_estimado) }}</td>
                <td class="right"><span class="dot" :style="{ background: SEMAFORO[i.semaforo] }" />{{ pct(i.dispersion_final) }}</td>
                <td><span class="badge" :style="{ background: SOPORTE[i.soporte].color }" :title="SOPORTE[i.soporte].ayuda">{{ SOPORTE[i.soporte].label }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <Modal v-if="form" :titulo="form.id ? `Editar cotización ${form.etiqueta}` : 'Nueva cotización'" ancho="900px" @cerrar="form = null">
      <div class="form-grid">
        <label v-if="!form.id" class="f req"><span>Proveedor</span>
          <select v-model="form.proveedor_id" required>
            <option value="" disabled>Seleccione…</option>
            <option v-for="p in proveedores" :key="p.id" :value="p.id" :disabled="usados.has(p.id)">{{ p.razon_social }} ({{ p.nit }}){{ usados.has(p.id) ? ' · ya cotizó' : '' }}</option>
          </select>
          <button type="button" class="link small" style="text-align:left" @click="nuevoProv = { nit: '', razon_social: '', contacto: '', email: '', telefono: '' }">+ Registrar proveedor nuevo</button>
        </label>
        <div v-else class="f"><span class="small"><b>Proveedor</b></span>{{ form.proveedor.razon_social }}</div>
        <label class="f req"><span>Fecha de la cotización</span><input v-model="form.fecha" type="date" :max="hoyISO()" required /></label>
        <div class="f full" :class="{ req: !form.id }"><span class="small"><b>Documento PDF {{ form.id ? '(opcional: reemplaza el actual)' : '' }}</b></span>
          <label class="drop" :class="{ on: arrastrando }" @dragover.prevent="arrastrando = true" @dragleave="arrastrando = false" @drop.prevent="soltar">
            <input type="file" accept="application/pdf" hidden @change="elegirPdf($event.target.files[0])" />
            <span v-if="form.pdf">📄 {{ form.pdf.name }} ({{ (form.pdf.size / 1048576).toFixed(2) }} MB)</span>
            <span v-else>Arrastre el PDF aquí o haga clic para seleccionarlo · máx. 10 MB</span>
          </label>
        </div>
      </div>
      <div class="tabs" style="margin-top:14px">
        <button :class="{ on: form.modo === 'grilla' }" @click="form.modo = 'grilla'">Digitar precios ({{ nPrecios }})</button>
        <button :class="{ on: form.modo === 'excel' }" @click="form.modo = 'excel'">Cargar plantilla Excel</button>
      </div>
      <div v-if="form.modo === 'grilla'">
        <input v-model="q" placeholder="Filtrar artículos…" style="width:100%;margin-bottom:8px" />
        <div class="table-wrap" style="max-height:42vh;overflow:auto">
          <table>
            <thead><tr><th>Artículo</th><th>Unidad</th><th class="right">Precio unitario IVA incluido</th></tr></thead>
            <tbody>
              <tr v-for="i in filtrados" :key="i.articulo_id">
                <td>{{ i.articulo.nombre }}<div class="small muted">{{ i.articulo.codigo_unspsc }} · {{ i.n_cotizaciones }} cotización(es)</div></td>
                <td>{{ i.articulo.unidad }}</td>
                <td class="right"><input v-model.number="form.precios[i.articulo_id]" type="number" min="0" step="1" class="precio" placeholder="$" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else>
        <p class="sub">1) Descargue la plantilla, 2) diligencie la columna de precio sólo para los artículos que cotiza el proveedor, 3) cárguela aquí.</p>
        <div class="row">
          <button class="btn ghost" @click="api.descargar(`/cotizaciones/plantilla${qs({ vigencia_id: vig.id, cotizacion_id: form.id })}`)">Descargar plantilla</button>
          <input type="file" accept=".xlsx" @change="form.archivo = $event.target.files[0]" />
        </div>
      </div>
      <div class="alert ok" style="margin-top:12px">Al guardar, los artículos cotizados quedarán <b>habilitados</b> para incluirse en su solicitud.</div>
      <template #pie>
        <button class="btn ghost" @click="form = null">Cancelar</button>
        <button class="btn" :disabled="guardando || (!form.id && !form.proveedor_id)" @click="guardar">{{ guardando ? 'Guardando…' : 'Guardar cotización' }}</button>
      </template>
    </Modal>

    <Modal v-if="nuevoProv" titulo="Registrar proveedor" @cerrar="nuevoProv = null">
      <form id="fprov" class="form-grid" @submit.prevent="crearProveedor">
        <label class="f req"><span>NIT</span><input v-model="nuevoProv.nit" required placeholder="900123456-1" /></label>
        <label class="f req"><span>Razón social</span><input v-model="nuevoProv.razon_social" required /></label>
        <label class="f"><span>Contacto</span><input v-model="nuevoProv.contacto" /></label>
        <label class="f"><span>Correo</span><input v-model="nuevoProv.email" type="email" /></label>
        <label class="f"><span>Teléfono</span><input v-model="nuevoProv.telefono" /></label>
      </form>
      <template #pie><button class="btn ghost" @click="nuevoProv = null">Cancelar</button><button class="btn" form="fprov">Registrar</button></template>
    </Modal>
  </div>
</template>

<style scoped>
.drop { display: block; border: 2px dashed var(--borde); border-radius: 8px; padding: 18px; text-align: center; color: var(--texto2); cursor: pointer; background: var(--fila); }
.drop.on, .drop:hover { border-color: var(--verde); background: #F1F8EC; }
</style>
