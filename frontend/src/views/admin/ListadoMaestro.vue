<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../../api'
import Modal from '../../components/Modal.vue'
import { debounce, money, number, toast, toastError } from '../../util'

const lotes = ref([])
const f = ref({ q: '', lote_id: '', activo: 'true' })
const pagina = ref(1)
const datos = ref({ items: [], total: 0 })
const form = ref(null)
const detalle = ref(null)
const imp = ref(null) // { paso, archivo, hojas, hoja, desactivar, prev, resultado }
const hist = ref(null)

async function cargar() {
  try { datos.value = await api.get(`/articulos${qs({ ...f.value, pagina: pagina.value, por_pagina: 50 })}`) } catch (e) { toastError(e) }
}
const recargar = debounce(() => { pagina.value = 1; cargar() }, 300)
watch(f, recargar, { deep: true })
onMounted(async () => { lotes.value = await api.get('/lotes'); cargar() })

const nuevo = () => { form.value = { lote_id: f.value.lote_id || lotes.value[0]?.id, codigo_unspsc: '', nombre: '', unidad: 'UN', descripcion: '', activo: true } }
const editar = (a) => { form.value = { ...a } }
async function guardar() {
  try {
    if (form.value.id) await api.put(`/articulos/${form.value.id}`, form.value)
    else await api.post('/articulos', form.value)
    toast('Artículo guardado')
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
async function eliminar(a) {
  if (!confirm(`¿Eliminar «${a.nombre}»? Si tiene cotizaciones o solicitudes sólo se desactivará.`)) return
  try { const r = await api.del(`/articulos/${a.id}`); toast(r.mensaje || 'Artículo eliminado'); cargar() } catch (e) { toastError(e) }
}
async function ver(a) { detalle.value = await api.get(`/articulos/${a.id}`) }

// --- Importación asistida ---
async function elegirArchivo(ev) {
  const archivo = ev.target.files[0]
  if (!archivo) return
  const fd = new FormData()
  fd.append('archivo', archivo)
  try {
    const { hojas } = await api.post('/articulos/importar/hojas', fd)
    if (!hojas.length) return toast('El archivo no tiene hojas con formato de listado maestro (columnas UNSPSC y Producto)', 'error')
    imp.value = { ...imp.value, archivo, hojas, hoja: hojas.find((h) => /^LM-\d{4}$/.test(h)) || hojas[0], prev: null }
  } catch (e) { toastError(e) }
}
async function previsualizar(confirmar = false) {
  const fd = new FormData()
  fd.append('archivo', imp.value.archivo)
  fd.append('hoja', imp.value.hoja)
  fd.append('desactivar_ausentes', imp.value.desactivar)
  fd.append('confirmar', confirmar)
  try {
    const r = await api.post('/articulos/importar', fd)
    if (confirmar) {
      toast(`Importación aplicada: ${r.resumen.nuevos} nuevos, ${r.resumen.actualizados} actualizados, ${r.resumen.a_desactivar} desactivados`)
      imp.value = null
      cargar()
    } else imp.value.prev = r
  } catch (e) { toastError(e) }
}
async function importarHist() {
  const fd = new FormData()
  fd.append('archivo', hist.value.archivo)
  fd.append('anio', hist.value.anio)
  try {
    const r = await api.post('/articulos/importar-historicos', fd)
    toast(`${r.importados} precios históricos importados`)
    hist.value = null
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Listado maestro de artículos</h1><div class="sub">{{ number(datos.total) }} artículos · fichas técnicas con código UNSPSC (SECOP II)</div></div>
      <div class="row">
        <button class="btn ghost" @click="api.descargar(`/articulos/exportar${qs(f)}`)">Exportar Excel</button>
        <button class="btn ghost" @click="hist = { archivo: null, anio: new Date().getFullYear() }">Importar históricos</button>
        <button class="btn outline" @click="imp = { archivo: null, hojas: [], hoja: '', desactivar: false, prev: null }">Importar desde Excel</button>
        <button class="btn" @click="nuevo">+ Nuevo artículo</button>
      </div>
    </div>
    <div class="row" style="margin-bottom:12px">
      <input v-model="f.q" placeholder="Buscar por nombre o código…" class="grow" style="max-width:360px" />
      <select v-model="f.lote_id"><option value="">Todos los lotes</option><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }} ({{ l.articulos }})</option></select>
      <select v-model="f.activo"><option value="true">Activos</option><option value="false">Inactivos</option><option value="todos">Todos</option></select>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>UNSPSC</th><th>Artículo</th><th>Lote</th><th>Unidad</th><th class="right">Cotizaciones</th><th></th></tr></thead>
        <tbody>
          <tr v-for="a in datos.items" :key="a.id" :class="{ dis: !a.activo }">
            <td class="mono">{{ a.codigo_unspsc }}</td>
            <td><button class="link" style="text-decoration:none;color:inherit;text-align:left" @click="ver(a)">{{ a.nombre }}</button></td>
            <td>{{ a.lote_abrev }}</td><td>{{ a.unidad }}</td><td class="right">{{ a.cotizaciones }}</td>
            <td class="right nowrap"><button class="btn ghost sm" @click="editar(a)">Editar</button> <button class="btn ghost sm" style="color:var(--rojo)" @click="eliminar(a)">Eliminar</button></td>
          </tr>
          <tr v-if="!datos.items.length"><td colspan="6" class="empty">Sin artículos. Use «Importar desde Excel» para cargar el listado maestro.</td></tr>
        </tbody>
      </table>
    </div>
    <div class="pager">
      <button class="btn ghost sm" :disabled="pagina === 1" @click="pagina--; cargar()">‹ Anterior</button>
      Página {{ pagina }} de {{ Math.max(1, Math.ceil(datos.total / 50)) }}
      <button class="btn ghost sm" :disabled="pagina * 50 >= datos.total" @click="pagina++; cargar()">Siguiente ›</button>
    </div>

    <Modal v-if="form" :titulo="form.id ? 'Editar artículo' : 'Nuevo artículo'" @cerrar="form = null">
      <form id="fa" class="form-grid" @submit.prevent="guardar">
        <label class="f req"><span>Lote</span><select v-model="form.lote_id" required><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}</option></select></label>
        <label class="f req"><span>Código UNSPSC (8 dígitos)</span><input v-model="form.codigo_unspsc" required pattern="\d{8}" maxlength="8" inputmode="numeric" /></label>
        <label class="f req full"><span>Nombre del producto</span><input v-model="form.nombre" required maxlength="300" /></label>
        <label class="f req"><span>Unidad SECOP II</span><input v-model="form.unidad" required maxlength="10" /></label>
        <label class="f"><span>Estado</span><select v-model="form.activo"><option :value="true">Activo</option><option :value="false">Inactivo</option></select></label>
        <label class="f full"><span>Descripción / ficha técnica</span><textarea v-model="form.descripcion" rows="5" /></label>
      </form>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fa">Guardar</button></template>
    </Modal>

    <Modal v-if="detalle" :titulo="detalle.nombre" ancho="760px" @cerrar="detalle = null">
      <p><b>UNSPSC:</b> {{ detalle.codigo_unspsc }} · <b>Unidad:</b> {{ detalle.unidad }} · <b>Lote:</b> {{ detalle.lote }} · {{ detalle.activo ? 'Activo' : 'Inactivo' }}</p>
      <p style="white-space:pre-line">{{ detalle.descripcion }}</p>
      <div class="cols-2">
        <div><h3>Precios históricos</h3><table><tbody><tr v-for="h in detalle.historicos" :key="h.anio"><td>{{ h.anio }}</td><td class="right">{{ money(h.precio) }}</td><td class="small muted">{{ h.fuente }}</td></tr></tbody></table></div>
        <div><h3>Cotizaciones</h3><table><tbody><tr v-for="(c, i) in detalle.cotizaciones" :key="i" :class="{ dis: c.excluido }"><td>{{ c.vigencia }} {{ c.etiqueta }}</td><td>{{ c.proveedor }}</td><td class="right">{{ money(c.precio) }}</td></tr></tbody></table></div>
      </div>
    </Modal>

    <Modal v-if="imp" titulo="Importar listado maestro desde Excel" ancho="900px" @cerrar="imp = null">
      <p class="sub">Formato esperado (como las hojas LM-AAAA del estudio de mercados): columnas <b>Lote</b> (abreviatura o número), <b>Código UNSPSC</b>, <b>Producto</b>, <b>Unidad SECOP</b> y <b>Descripción</b>.
        Los artículos se identifican por lote + nombre: los existentes se actualizan y los nuevos se crean.</p>
      <div class="form-grid">
        <label class="f req"><span>Archivo .xlsx</span><input type="file" accept=".xlsx" @change="elegirArchivo" /></label>
        <label v-if="imp.hojas.length" class="f req"><span>Hoja</span><select v-model="imp.hoja" @change="imp.prev = null"><option v-for="h in imp.hojas" :key="h">{{ h }}</option></select></label>
        <label v-if="imp.hojas.length" class="row small full" style="gap:6px"><input v-model="imp.desactivar" type="checkbox" @change="imp.prev = null" /> Desactivar los artículos de los lotes incluidos que no aparezcan en el archivo (nuevo listado de la vigencia)</label>
      </div>
      <template v-if="imp.prev">
        <div class="kpis" style="margin-top:14px">
          <div class="card kpi"><div class="l">Filas leídas</div><div class="v">{{ imp.prev.resumen.leidas }}</div></div>
          <div class="card kpi"><div class="l">Nuevos</div><div class="v">{{ imp.prev.resumen.nuevos }}</div></div>
          <div class="card kpi" style="border-color:var(--cyan)"><div class="l">Actualizados</div><div class="v">{{ imp.prev.resumen.actualizados }}</div></div>
          <div class="card kpi" style="border-color:var(--texto2)"><div class="l">A desactivar</div><div class="v">{{ imp.prev.resumen.a_desactivar }}</div></div>
          <div class="card kpi" style="border-color:var(--rojo)"><div class="l">Con errores (se omiten)</div><div class="v">{{ imp.prev.resumen.errores }}</div></div>
          <div class="card kpi" style="border-color:var(--amarillo)"><div class="l">Advertencias</div><div class="v">{{ imp.prev.resumen.advertencias }}</div></div>
        </div>
        <div v-if="imp.prev.errores.length" class="alert error"><b>Filas con errores (no se importan):</b>
          <ul><li v-for="e in imp.prev.errores.slice(0, 30)" :key="e.fila">Fila {{ e.fila }} · {{ e.nombre }}: {{ e.errores.join('; ') }}</li></ul></div>
        <div v-if="imp.prev.advertencias.length" class="alert warn"><b>Advertencias:</b>
          <ul><li v-for="(a, k) in imp.prev.advertencias.slice(0, 30)" :key="k">Fila {{ a.fila }} · {{ a.nombre }}: {{ a.mensaje }}</li></ul></div>
        <div v-if="imp.prev.actualizados.length" class="small"><b>Cambios en existentes:</b> {{ imp.prev.actualizados.slice(0, 15).map((a) => `${a.nombre} (${a.cambios.join(', ')})`).join(' · ') }}{{ imp.prev.actualizados.length > 15 ? '…' : '' }}</div>
      </template>
      <template #pie>
        <button class="btn ghost" @click="imp = null">Cancelar</button>
        <button class="btn outline" :disabled="!imp.archivo" @click="previsualizar(false)">Previsualizar</button>
        <button class="btn" :disabled="!imp.prev" @click="previsualizar(true)">Aplicar importación</button>
      </template>
    </Modal>

    <Modal v-if="hist" titulo="Importar precios históricos" @cerrar="hist = null">
      <p class="sub">Carga el «Precio unitario estimado IVA incluido» de las hojas L1…L11 de un estudio de mercados firmado como precio histórico del año indicado. Se usa para indexar precios en las vigencias siguientes.</p>
      <div class="form-grid">
        <label class="f req"><span>Archivo del estudio (.xlsx)</span><input type="file" accept=".xlsx" @change="hist.archivo = $event.target.files[0]" /></label>
        <label class="f req"><span>Año del estudio</span><input v-model.number="hist.anio" type="number" /></label>
      </div>
      <template #pie><button class="btn ghost" @click="hist = null">Cancelar</button><button class="btn" :disabled="!hist.archivo" @click="importarHist">Importar</button></template>
    </Modal>
  </div>
</template>
