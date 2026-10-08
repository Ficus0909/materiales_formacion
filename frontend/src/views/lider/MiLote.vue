<script setup>
import { onMounted, ref, watch } from 'vue'
import { api, qs } from '../../api'
import Badge from '../../components/Badge.vue'
import Modal from '../../components/Modal.vue'
import { debounce, fecha, money, toast, toastError } from '../../util'

const q = ref('')
const datos = ref({ items: [], total: 0 })
const pagina = ref(1)
const detalle = ref(null)
const propuestas = ref([])
const nueva = ref(null)

async function cargar() {
  try { datos.value = await api.get(`/articulos${qs({ q: q.value, pagina: pagina.value, por_pagina: 50 })}`) } catch (e) { toastError(e) }
}
const buscar = debounce(() => { pagina.value = 1; cargar() }, 300)
watch(q, buscar)
async function ver(a) { try { detalle.value = await api.get(`/articulos/${a.id}`) } catch (e) { toastError(e) } }
async function cargarPropuestas() { propuestas.value = await api.get('/propuestas') }
async function proponer() {
  try {
    await api.post('/propuestas', nueva.value)
    toast('Propuesta enviada al administrador')
    nueva.value = null
    cargarPropuestas()
  } catch (e) { toastError(e) }
}
onMounted(() => { cargar(); cargarPropuestas() })
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Mi lote</h1><div class="sub">Listado maestro de fichas técnicas de su lote ({{ datos.total }} artículos activos)</div></div>
      <div class="row">
        <button class="btn ghost" @click="api.descargar('/articulos/exportar')">Exportar Excel</button>
        <button class="btn" @click="nueva = { nombre: '', unidad: 'UN', descripcion: '', justificacion: '' }">Proponer artículo nuevo</button>
      </div>
    </div>
    <div class="alert info">El listado maestro lo administra el analista (asigna el código UNSPSC de SECOP II). Si necesita un artículo que no está, propóngalo con su ficha técnica.</div>
    <input v-model="q" placeholder="Buscar por nombre o código UNSPSC…" style="width:100%;max-width:420px;margin-bottom:12px" />
    <div class="table-wrap">
      <table>
        <thead><tr><th>UNSPSC</th><th>Artículo</th><th>Unidad</th><th class="right">Cotizaciones (histórico)</th></tr></thead>
        <tbody>
          <tr v-for="a in datos.items" :key="a.id" class="click" @click="ver(a)">
            <td class="mono">{{ a.codigo_unspsc }}</td><td>{{ a.nombre }}</td><td>{{ a.unidad }}</td><td class="right">{{ a.cotizaciones }}</td>
          </tr>
          <tr v-if="!datos.items.length"><td colspan="4" class="empty">Sin resultados</td></tr>
        </tbody>
      </table>
    </div>
    <div class="pager">
      <button class="btn ghost sm" :disabled="pagina === 1" @click="pagina--; cargar()">‹ Anterior</button>
      Página {{ pagina }} de {{ Math.max(1, Math.ceil(datos.total / 50)) }}
      <button class="btn ghost sm" :disabled="pagina * 50 >= datos.total" @click="pagina++; cargar()">Siguiente ›</button>
    </div>

    <div v-if="propuestas.length" class="card" style="margin-top:16px">
      <h2>Mis propuestas de artículos</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Artículo</th><th>Fecha</th><th>Estado</th><th>Respuesta</th></tr></thead>
        <tbody><tr v-for="p in propuestas" :key="p.id"><td>{{ p.nombre }}</td><td>{{ fecha(p.creado) }}</td><td><Badge :estado="p.estado === 'APROBADA' ? 'APROBADA' : p.estado === 'RECHAZADA' ? 'RECHAZADA' : 'PENDIENTE'" /></td><td>{{ p.respuesta }}</td></tr></tbody>
      </table></div>
    </div>

    <Modal v-if="detalle" :titulo="detalle.nombre" ancho="760px" @cerrar="detalle = null">
      <p><b>UNSPSC:</b> {{ detalle.codigo_unspsc }} · <b>Unidad:</b> {{ detalle.unidad }} · <b>Lote:</b> {{ detalle.lote }}</p>
      <h3>Ficha técnica</h3>
      <p style="white-space:pre-line">{{ detalle.descripcion || '—' }}</p>
      <div class="cols-2">
        <div><h3>Precios históricos</h3>
          <table><tbody><tr v-for="h in detalle.historicos" :key="h.anio"><td>{{ h.anio }}</td><td class="right">{{ money(h.precio) }}</td></tr>
            <tr v-if="!detalle.historicos.length"><td class="muted">Sin históricos</td></tr></tbody></table>
        </div>
        <div><h3>Cotizaciones</h3>
          <table><tbody><tr v-for="(c, i) in detalle.cotizaciones" :key="i"><td>{{ c.vigencia }} {{ c.etiqueta }}</td><td>{{ c.proveedor }}</td><td class="right">{{ money(c.precio) }}</td></tr>
            <tr v-if="!detalle.cotizaciones.length"><td class="muted">Sin cotizaciones</td></tr></tbody></table>
        </div>
      </div>
    </Modal>

    <Modal v-if="nueva" titulo="Proponer artículo nuevo" @cerrar="nueva = null">
      <form id="fp" class="form-grid" @submit.prevent="proponer">
        <label class="f req full"><span>Nombre del producto</span><input v-model="nueva.nombre" required /></label>
        <label class="f req"><span>Unidad de medida (SECOP II)</span><input v-model="nueva.unidad" required placeholder="UN, KG, L, GAR…" /></label>
        <label class="f req full"><span>Ficha técnica</span><textarea v-model="nueva.descripcion" required rows="4" /></label>
        <label class="f full"><span>Justificación (uso en la formación)</span><textarea v-model="nueva.justificacion" rows="2" /></label>
      </form>
      <template #pie><button class="btn ghost" @click="nueva = null">Cancelar</button><button class="btn" form="fp">Enviar propuesta</button></template>
    </Modal>
  </div>
</template>
