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
const lista = ref(null)
const lotes = ref([])
const coordinaciones = ref([])
// Por defecto cada rol ve lo que tiene por hacer
const porHacer = auth.esCoordinador ? 'ENVIADA' : auth.esLider ? 'APROBADA' : ''
const f = ref({ estado: route.query.estado ?? porHacer, lote_id: '', coordinacion_id: '' })

async function cargar() { try { lista.value = await api.get(`/entregas${qs(f.value)}`) } catch (e) { toastError(e) } }
onMounted(async () => {
  if (auth.esAdmin || auth.esManager) {
    ;[lotes.value, coordinaciones.value] = await Promise.all([api.get('/lotes'), api.get('/coordinaciones')])
  }
  cargar()
})
watch(f, cargar, { deep: true })

const titulo = computed(() => (auth.esCoordinador ? `Solicitudes de bienes · ${auth.usuario.coordinacion?.nombre}`
  : auth.esLider ? `Entregas a instructores · Lote ${auth.usuario.lote?.nombre}` : 'Entrega de materiales'))
const total = computed(() => (lista.value || []).reduce((t, e) => t + e.valor, 0))
const ESTADOS_FILTRO = [['ENVIADA', 'Por aprobar'], ['DEVUELTA', 'Devueltas'], ['APROBADA', 'Por entregar'], ['ENTREGADA', 'Por legalizar'],
  ['EXTEMPORANEA', 'Legalización extemporánea'], ['LEGALIZADA', 'Legalizadas']]
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>{{ titulo }}</h1><div class="sub">{{ lista?.length ?? '…' }} solicitudes · {{ money(total) }} · formato GIL-F-014</div></div>
      <router-link v-if="auth.esLider" to="/lider/inventario" class="btn ghost">Inventario e informe</router-link>
    </div>
    <div class="row" style="margin-bottom:12px">
      <select v-model="f.estado"><option value="">Todos los estados</option><option v-for="[k, t] in ESTADOS_FILTRO" :key="k" :value="k">{{ t }}</option></select>
      <select v-if="lotes.length" v-model="f.lote_id"><option value="">Todos los lotes</option><option v-for="l in lotes" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}{{ auth.esManager ? ` (${l.centro})` : '' }}</option></select>
      <select v-if="coordinaciones.length" v-model="f.coordinacion_id"><option value="">Todas las coordinaciones</option><option v-for="c in coordinaciones" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>N°</th><th>Fecha</th><th>Instructor</th><th v-if="!auth.esCoordinador">Coordinación</th><th v-if="!auth.esLider">Lote</th>
          <th>Ficha</th><th class="right">Bienes</th><th class="right">Valor</th><th>Estado</th><th>Legalización</th></tr></thead>
        <tbody>
          <tr v-for="e in lista || []" :key="e.id" class="click" @click="router.push(`/entregas/${e.id}`)">
            <td>#{{ e.id }}</td><td>{{ fecha(e.fecha_solicitud) }}</td><td>{{ e.instructor }}</td>
            <td v-if="!auth.esCoordinador">{{ e.coordinacion }}</td>
            <td v-if="!auth.esLider"><span class="dot" :style="{ background: e.lote_color }" />{{ e.lote_numero }}. {{ e.lote }}<span v-if="auth.esManager" class="small muted"> · {{ e.centro }}</span></td>
            <td>{{ e.ficha }}</td><td class="right">{{ e.n_items }}</td><td class="right mono">{{ money(e.valor) }}</td>
            <td><Badge :estado="e.estado" /></td>
            <td class="small">
              <span v-if="e.estado === 'LEGALIZADA'">✓ {{ fecha(e.fecha_legalizacion) }}</span>
              <span v-else-if="e.extemporanea" style="color:var(--rojo);font-weight:600">Vencida {{ fecha(e.fecha_limite_legalizacion) }}</span>
              <span v-else-if="e.estado === 'ENTREGADA'">Hasta {{ fecha(e.fecha_limite_legalizacion) }} ({{ e.dias_habiles_restantes }} d. háb.)</span>
              <span v-else class="muted">—</span>
            </td>
          </tr>
          <tr v-if="lista && !lista.length"><td colspan="10" class="empty">No hay solicitudes con estos filtros</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
