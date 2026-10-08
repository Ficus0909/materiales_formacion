<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api'
import Bars from '../../components/Bars.vue'
import { useAuth } from '../../store'
import { ESTADOS, fecha, fechaHora, number, toastError } from '../../util'

const auth = useAuth()

const d = ref(null)
async function cargar() { try { d.value = await api.get('/dashboard/admin') } catch (e) { toastError(e) } }
let t
onMounted(() => { cargar(); t = setInterval(cargar, 30000) })
onUnmounted(() => clearInterval(t))

const porEstado = computed(() => (d.value?.por_estado || []).map((e) => ({ label: ESTADOS[e.estado]?.label || e.estado, value: e.cantidad, color: ESTADOS[e.estado]?.color || '#71277A' })))
const cobertura = computed(() => (d.value?.cobertura || []).map((c) => ({ label: `${c.numero}. ${c.lote}`, value: c.porcentaje, display: `${c.porcentaje} %`,
  color: c.porcentaje >= 80 ? 'var(--verde)' : c.porcentaje >= 60 ? 'var(--amarillo)' : 'var(--rojo)' })))
const enlace = (e) => (e || '').replace('/admin/solicitudes/', '/solicitudes/')
</script>

<template>
  <div v-if="d">
    <div class="page-head">
      <div><h1>Dashboard · {{ auth.usuario?.centro?.nombre }}</h1>
        <div class="sub" v-if="d.vigencia">Vigencia {{ d.vigencia.codigo }} ({{ ESTADOS[d.vigencia.estado].label.toLowerCase() }}) · cierre {{ fecha(d.vigencia.fecha_cierre) }}</div>
        <div class="sub" v-else>No hay vigencias creadas</div>
      </div>
    </div>
    <div v-if="!d.vigencia || d.vigencia.estado !== 'ABIERTA'" class="alert warn">No hay vigencia abierta. El manager la abre para todos los centros; mientras tanto los líderes no pueden cotizar ni solicitar.</div>
    <div class="kpis">
      <router-link to="/admin/listado-maestro" class="card kpi"><div class="l">Artículos en el listado maestro</div><div class="v">{{ number(d.kpis.articulos) }}</div></router-link>
      <router-link to="/admin/solicitudes?estado=PENDIENTES" class="card kpi" style="border-color:var(--naranja)"><div class="l">Solicitudes por revisar</div><div class="v">{{ d.kpis.pendientes }}</div></router-link>
      <router-link to="/admin/analisis" class="card kpi" style="border-color:var(--cyan)"><div class="l">Cotizaciones (documentos)</div><div class="v">{{ d.kpis.cotizaciones }}</div><div class="small muted">{{ number(d.kpis.precios_cotizados) }} precios cotizados</div></router-link>
      <router-link to="/admin/usuarios" class="card kpi" style="border-color:var(--azul)"><div class="l">Líderes activos</div><div class="v">{{ d.kpis.lideres }}</div></router-link>
      <router-link to="/admin/propuestas" class="card kpi" style="border-color:var(--violeta)"><div class="l">Artículos propuestos</div><div class="v">{{ d.kpis.propuestas }}</div></router-link>
    </div>
    <div class="cols-2">
      <div class="card"><h2>Solicitudes por estado</h2><Bars :datos="porEstado" />
        <div v-if="d.lotes_sin_solicitud.length" class="small muted" style="margin-top:12px">Lotes que aún no envían solicitud: {{ d.lotes_sin_solicitud.join(', ') }}</div>
      </div>
      <div class="card"><h2>Cobertura de precios por lote</h2>
        <template v-if="cobertura.length"><Bars :datos="cobertura" :max="100" />
          <div class="small muted" style="margin-top:8px">Lotes con líder asignado. Verde ≥ 80 % · Amarillo 60–79 % · Rojo &lt; 60 % (requiere atención)</div></template>
        <div v-else class="empty">Aún no hay lotes en operación. Los lotes aparecen aquí cuando les asigna un líder en <router-link to="/admin/usuarios">Usuarios</router-link>.</div>
      </div>
    </div>
    <div class="card">
      <h2>Actividad reciente</h2>
      <div v-for="(a, i) in d.actividad" :key="i" class="act">
        <span class="small muted nowrap">{{ fechaHora(a.fecha) }}</span>
        <span><b>{{ a.usuario }}</b> · <router-link v-if="a.enlace" :to="enlace(a.enlace)">{{ a.accion }}</router-link><span v-else>{{ a.accion }}</span></span>
      </div>
      <div v-if="!d.actividad.length" class="empty">Sin actividad</div>
    </div>
  </div>
  <div v-else class="card"><div class="skeleton" v-for="i in 6" :key="i" /></div>
</template>

<style scoped>
.act { display: grid; grid-template-columns: 120px 1fr; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--borde); font-size: 13px; }
</style>
