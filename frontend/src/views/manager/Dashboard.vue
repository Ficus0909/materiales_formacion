<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import Bars from '../../components/Bars.vue'
import { ESTADOS, fecha, fechaHora, money, toastError } from '../../util'

const router = useRouter()
const d = ref(null)
async function cargar() { try { d.value = await api.get('/dashboard/manager') } catch (e) { toastError(e) } }
let t
onMounted(() => { cargar(); t = setInterval(cargar, 60000) })
onUnmounted(() => clearInterval(t))

const activos = computed(() => (d.value?.centros || []).filter((c) => c.activo))
const enOperacion = computed(() => activos.value.filter((c) => c.lotes_operacion))
const cobertura = computed(() => enOperacion.value.map((c) => ({ label: c.nombre, value: c.cobertura, display: `${c.cobertura} %`,
  color: c.cobertura >= 80 ? 'var(--verde)' : c.cobertura >= 60 ? 'var(--amarillo)' : 'var(--rojo)' })))
const valor = computed(() => activos.value.map((c) => ({ label: c.nombre, value: c.valor_aprobado, display: money(c.valor_aprobado) })))
const enlace = (e) => (e || '').replace('/admin/solicitudes/', '/solicitudes/')
</script>

<template>
  <div v-if="d">
    <div class="page-head">
      <div><h1>Centros de formación</h1>
        <div class="sub" v-if="d.vigencia">Vigencia {{ d.vigencia.codigo }} ({{ ESTADOS[d.vigencia.estado].label.toLowerCase() }}) · cierre {{ fecha(d.vigencia.fecha_cierre) }}</div>
        <div class="sub" v-else>No hay vigencias creadas</div>
      </div>
      <router-link to="/manager/centros" class="btn">Administrar centros</router-link>
    </div>
    <div v-if="!d.vigencia || d.vigencia.estado !== 'ABIERTA'" class="alert warn">No hay vigencia abierta. Abra una en <router-link to="/admin/vigencias">Vigencias</router-link> para que los centros puedan cotizar y solicitar.</div>
    <div class="kpis">
      <router-link to="/manager/centros" class="card kpi"><div class="l">Centros activos</div><div class="v">{{ d.kpis.centros }}</div></router-link>
      <router-link to="/admin/usuarios" class="card kpi" style="border-color:var(--azul)"><div class="l">Administradores · líderes</div><div class="v">{{ d.kpis.administradores }} · {{ d.kpis.lideres }}</div></router-link>
      <router-link to="/admin/solicitudes?estado=PENDIENTES" class="card kpi" style="border-color:var(--naranja)"><div class="l">Solicitudes por revisar</div><div class="v">{{ d.kpis.pendientes }}</div></router-link>
      <div class="card kpi" style="border-color:var(--violeta)"><div class="l">Aprobadas · valor</div><div class="v" style="font-size:20px">{{ d.kpis.aprobadas }} · {{ money(d.kpis.valor_aprobado) }}</div></div>
    </div>
    <div class="card">
      <h2>Resumen por centro</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Centro</th><th class="right">Admins</th><th class="right">Líderes</th><th class="right" title="Lotes con líder / lotes del listado">Lotes en operación</th><th class="right">Artículos en operación</th>
            <th class="right">Cobertura de precios</th><th class="right">Enviadas</th><th class="right">Por revisar</th><th class="right">Aprobadas</th><th class="right">Valor aprobado</th></tr></thead>
          <tbody>
            <tr v-for="c in d.centros" :key="c.id" class="click" :class="{ dis: !c.activo }" @click="router.push(`/admin/solicitudes?centro_id=${c.id}`)">
              <td><b>{{ c.nombre }}</b><div class="small muted">{{ c.codigo }}<span v-if="c.regional"> · Regional {{ c.regional }}</span><span v-if="!c.activo"> · inactivo</span></div></td>
              <td class="right"><span :style="{ color: c.administradores ? '' : 'var(--rojo)' }">{{ c.administradores }}</span></td>
              <td class="right">{{ c.lideres }}</td><td class="right">{{ c.lotes_operacion }} / {{ c.lotes }}</td><td class="right">{{ c.articulos }}</td>
              <td class="right"><template v-if="c.lotes_operacion"><span class="dot" :style="{ background: c.cobertura >= 80 ? 'var(--verde)' : c.cobertura >= 60 ? 'var(--amarillo)' : 'var(--rojo)' }" />{{ c.cobertura }} %</template><span v-else class="muted">—</span></td>
              <td class="right">{{ c.enviadas }}</td><td class="right">{{ c.pendientes }}</td><td class="right">{{ c.aprobadas }}</td>
              <td class="right mono">{{ money(c.valor_aprobado) }}</td>
            </tr>
            <tr v-if="!d.centros.length"><td colspan="10" class="empty">No hay centros. <router-link to="/manager/centros">Cree el primero</router-link>.</td></tr>
          </tbody>
        </table>
      </div>
      <p class="small muted">Haga clic en un centro para ver sus solicitudes. Un centro sin administrador aparece con 0 en rojo.</p>
    </div>
    <div class="cols-2">
      <div class="card"><h2>Cobertura de precios por centro</h2><Bars :datos="cobertura" :max="100" />
        <div v-if="!cobertura.length" class="empty">Ningún centro tiene lotes con líder asignado</div>
        <div class="small muted" style="margin-top:8px">Artículos de los lotes con líder que tienen precio de referencia. Verde ≥ 80 % · Amarillo 60–79 % · Rojo &lt; 60 %</div></div>
      <div class="card"><h2>Valor aprobado por centro</h2><Bars :datos="valor" /></div>
    </div>
    <div class="card">
      <h2>Actividad reciente (todos los centros)</h2>
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
