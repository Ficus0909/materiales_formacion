<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api, qs } from '../api'
import Bars from '../components/Bars.vue'
import { useAuth } from '../store'
import { ESTADOS, money, toastError } from '../util'

const auth = useAuth()
const vigencias = ref([])
const vig = ref('')
const centros = ref([])
const centro = ref('')
const r = ref(null)
const historico = ref([])

async function cargarHistorico() { historico.value = await api.get(`/reportes/historico${qs({ centro_id: centro.value })}`) }
onMounted(async () => {
  vigencias.value = await api.get('/vigencias')
  if (auth.esManager) centros.value = await api.get('/centros')
  vig.value = auth.vigencia?.id || vigencias.value[0]?.id || ''
  cargarHistorico()
})
watch([vig, centro], async () => {
  if (!vig.value) return
  try { r.value = await api.get(`/reportes/vigencia${qs({ vigencia_id: vig.value, centro_id: centro.value })}`) } catch (e) { toastError(e) }
})
watch(centro, cargarHistorico)
const alcance = computed(() => {
  if (auth.esManager) return centro.value ? centros.value.find((c) => c.id === centro.value)?.nombre : 'Todos los centros'
  if (auth.esAdmin) return `Todos los lotes · ${auth.usuario.centro?.nombre}`
  return `Lote ${auth.usuario.lote?.nombre}`
})

const valor = computed(() => (r.value?.por_lote || []).map((l) => ({ label: l.lote, value: l.valor, display: money(l.valor), color: l.color })))
const articulos = computed(() => (r.value?.por_lote || []).map((l) => ({ label: l.lote, value: l.articulos, color: l.color })))
const estados = computed(() => (r.value?.por_estado || []).map((e) => ({ label: ESTADOS[e.estado]?.label || e.estado, value: e.cantidad, color: ESTADOS[e.estado]?.color || '#71277A' })))
const cobertura = computed(() => (r.value?.cobertura || []).map((c) => ({ label: `${c.numero}. ${c.lote}`, value: c.porcentaje_cotizado, display: `${c.porcentaje_cotizado} %`,
  color: c.porcentaje_cotizado >= 80 ? 'var(--verde)' : c.porcentaje_cotizado >= 60 ? 'var(--amarillo)' : 'var(--rojo)' })))
const totalValor = computed(() => (r.value?.por_lote || []).reduce((t, l) => t + l.valor, 0))
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Reportes</h1><div class="sub">{{ alcance }}</div></div>
      <div class="row">
        <select v-if="auth.esManager" v-model="centro"><option value="">Todos los centros</option><option v-for="c in centros" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
        <select v-model="vig"><option v-for="v in vigencias" :key="v.id" :value="v.id">Vigencia {{ v.codigo }}</option></select>
        <button v-if="(auth.esAdmin || auth.esManager) && vig" class="btn" @click="api.descargar(`/solicitudes/consolidado/exportar${qs({ vigencia_id: vig, centro_id: centro })}`)">Exportar consolidado</button>
        <button v-else-if="vig" class="btn" @click="api.descargar(`/analisis/exportar${qs({ vigencia_id: vig })}`)">Exportar análisis de mi lote</button>
      </div>
    </div>
    <template v-if="r">
      <div class="kpis">
        <div class="card kpi"><div class="l">Solicitudes</div><div class="v">{{ r.por_lote.length }}</div></div>
        <div class="card kpi"><div class="l">Artículos solicitados</div><div class="v">{{ r.por_lote.reduce((t, l) => t + l.articulos, 0) }}</div></div>
        <div class="card kpi" style="border-color:var(--azul)"><div class="l">Valor estimado</div><div class="v" style="font-size:20px">{{ money(totalValor) }}</div></div>
      </div>
      <div class="cols-2">
        <div class="card"><h2>Valor estimado por lote</h2><Bars :datos="valor" /></div>
        <div class="card"><h2>Artículos solicitados por lote</h2><Bars :datos="articulos" /></div>
        <div class="card"><h2>Solicitudes por estado</h2><Bars :datos="estados" /></div>
        <div class="card"><h2>Cobertura de cotizaciones</h2><Bars v-if="cobertura.length" :datos="cobertura" :max="100" />
          <div v-else class="empty">Aún no hay lotes con líder asignado</div>
          <p class="small muted">Porcentaje de artículos del lote con al menos una cotización válida (sólo lotes con líder). &lt; 60 % requiere atención.</p></div>
      </div>
      <div class="card">
        <h2>Detalle por lote</h2>
        <div class="table-wrap"><table>
          <thead><tr><th v-if="auth.esManager && !centro">Centro</th><th>Lote</th><th>Líder</th><th>Estado</th><th class="right">Artículos</th><th class="right">Reenvíos</th><th class="right">Valor</th></tr></thead>
          <tbody><tr v-for="l in r.por_lote" :key="l.lote"><td v-if="auth.esManager && !centro">{{ l.centro }}</td><td>{{ l.lote }}</td><td>{{ l.lider }}</td><td>{{ ESTADOS[l.estado]?.label || l.estado }}</td><td class="right">{{ l.articulos }}</td><td class="right">{{ l.reenvios }}</td><td class="right mono">{{ money(l.valor) }}</td></tr></tbody>
        </table></div>
      </div>
    </template>
    <div class="card">
      <h2>Histórico por vigencia</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Vigencia</th><th class="right">Solicitudes</th><th class="right">Aprobadas</th><th class="right">Artículos aprobados</th><th class="right">Valor aprobado</th></tr></thead>
        <tbody><tr v-for="h in historico" :key="h.vigencia"><td>{{ h.vigencia }}</td><td class="right">{{ h.solicitudes }}</td><td class="right">{{ h.aprobadas }}</td><td class="right">{{ h.articulos }}</td><td class="right mono">{{ money(h.valor) }}</td></tr></tbody>
      </table></div>
    </div>
  </div>
</template>
