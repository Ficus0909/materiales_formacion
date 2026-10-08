<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, qs } from '../../api'
import Badge from '../../components/Badge.vue'
import { useAuth } from '../../store'
import { fecha, money, toastError } from '../../util'

const auth = useAuth()
const route = useRoute()
const router = useRouter()
const vigencias = ref([])
const lotes = ref([])
const lideres = ref([])
const estadosPost = ref([])
const centros = ref([])
const f = ref({ vigencia_id: '', centro_id: route.query.centro_id ? Number(route.query.centro_id) : '', lote_id: '', estado: route.query.estado || '', lider_id: '' })
const lista = ref(null)
const orden = ref({ col: 'fecha_envio', dir: -1 })

async function cargar() {
  try { lista.value = await api.get(`/solicitudes${qs(f.value)}`) } catch (e) { toastError(e) }
}
onMounted(async () => {
  ;[vigencias.value, lotes.value, lideres.value, estadosPost.value, centros.value] = await Promise.all([
    api.get('/vigencias'), api.get('/lotes'), api.get('/usuarios?rol=LIDER'), api.get('/estados-post'), api.get('/centros')])
  f.value.vigencia_id = auth.vigencia?.id || vigencias.value[0]?.id || ''
})
watch(f, cargar, { deep: true })
watch(() => f.value.centro_id, () => { f.value.lote_id = ''; f.value.lider_id = '' })
const lotesFiltro = computed(() => lotes.value.filter((l) => !f.value.centro_id || l.centro_id === f.value.centro_id))
const lideresFiltro = computed(() => lideres.value.filter((u) => !f.value.centro_id || u.centro_id === f.value.centro_id))

const ordenadas = computed(() => [...(lista.value || [])].sort((a, b) => {
  const x = a[orden.value.col] ?? ''
  const y = b[orden.value.col] ?? ''
  return (x > y ? 1 : x < y ? -1 : 0) * orden.value.dir
}))
const ordenar = (col) => { orden.value = { col, dir: orden.value.col === col ? -orden.value.dir : 1 } }
const total = computed(() => (lista.value || []).reduce((t, s) => t + (s.total || 0), 0))
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Bandeja de solicitudes</h1><div class="sub">{{ lista?.length ?? '…' }} solicitudes · {{ money(total) }}</div></div>
      <button v-if="f.vigencia_id" class="btn ghost" @click="api.descargar(`/solicitudes/consolidado/exportar${qs({ vigencia_id: f.vigencia_id, centro_id: f.centro_id })}`)">Exportar consolidado Excel</button>
    </div>
    <div class="row" style="margin-bottom:12px">
      <select v-model="f.vigencia_id"><option value="">Todas las vigencias</option><option v-for="v in vigencias" :key="v.id" :value="v.id">Vigencia {{ v.codigo }}</option></select>
      <select v-if="auth.esManager" v-model="f.centro_id"><option value="">Todos los centros</option><option v-for="c in centros" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
      <select v-model="f.lote_id"><option value="">Todos los lotes</option><option v-for="l in lotesFiltro" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}{{ auth.esManager && !f.centro_id ? ` (${l.centro})` : '' }}</option></select>
      <select v-model="f.estado">
        <option value="">Todos los estados</option><option value="PENDIENTES">Pendientes (enviadas + en revisión)</option>
        <option v-for="e in ['BORRADOR','ENVIADA','EN_REVISION','DEVUELTA','APROBADA','RECHAZADA','CANCELADA']" :key="e" :value="e">{{ e.replace('_', ' ').toLowerCase() }}</option>
        <option v-for="e in estadosPost" :key="e.id" :value="`POST:${e.id}`">{{ e.nombre }}</option>
      </select>
      <select v-model="f.lider_id"><option value="">Todos los líderes</option><option v-for="u in lideresFiltro" :key="u.id" :value="u.id">{{ u.nombre }}</option></select>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th class="sortable" @click="ordenar('id')">ID</th><th v-if="auth.esManager" class="sortable" @click="ordenar('centro')">Centro</th><th class="sortable" @click="ordenar('lote_numero')">Lote</th>
          <th class="sortable" @click="ordenar('lider')">Líder</th><th class="sortable right" @click="ordenar('n_items')">Artículos</th>
          <th class="sortable right" @click="ordenar('total')">Valor estimado</th><th class="sortable" @click="ordenar('estado_visible')">Estado</th>
          <th class="sortable" @click="ordenar('fecha_envio')">Fecha envío</th>
        </tr></thead>
        <tbody>
          <tr v-for="s in ordenadas" :key="s.id" class="click" @click="router.push(`/solicitudes/${s.id}`)">
            <td>#{{ s.id }}</td><td v-if="auth.esManager">{{ s.centro }}</td><td><span class="dot" :style="{ background: s.lote_color }" />{{ s.lote_numero }}. {{ s.lote }}</td><td>{{ s.lider }}</td>
            <td class="right">{{ s.n_items }}</td><td class="right mono">{{ money(s.total) }}</td>
            <td><Badge :estado="s.estado" :texto="s.estado_visible !== s.estado ? s.estado_visible : ''" :color="s.estado_post_color" /><span v-if="s.reenvios" class="small muted"> ↻{{ s.reenvios }}</span></td>
            <td>{{ fecha(s.fecha_envio) }}</td>
          </tr>
          <tr v-if="lista && !lista.length"><td :colspan="auth.esManager ? 8 : 7" class="empty">No hay solicitudes con estos filtros</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
