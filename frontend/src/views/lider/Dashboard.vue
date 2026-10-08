<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import { useAuth } from '../../store'
import { fecha, fechaHora, toastError } from '../../util'

const auth = useAuth()
const d = ref(null)
onMounted(async () => { try { d.value = await api.get('/dashboard/lider') } catch (e) { toastError(e) } })
const avance = computed(() => (d.value?.articulos ? Math.round((100 * d.value.con_precio) / d.value.articulos) : 0))
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>Hola, {{ auth.usuario.nombre }}</h1>
        <div class="sub">Lote {{ auth.usuario.lote?.numero }} · {{ auth.usuario.lote?.nombre }}</div>
      </div>
    </div>
    <template v-if="d">
      <div v-if="!d.vigencia" class="alert info">No hay una vigencia abierta. Cuando el administrador abra la próxima vigencia podrá cargar cotizaciones y crear su solicitud.</div>
      <div v-else class="alert info">Vigencia <b>{{ d.vigencia.codigo }}</b> abierta hasta el <b>{{ fecha(d.vigencia.fecha_cierre) }}</b>. Al cierre, las solicitudes no enviadas se cancelan.</div>

      <div class="kpis">
        <router-link to="/lider/mi-lote" class="card kpi"><div class="l">Artículos del lote</div><div class="v">{{ d.articulos }}</div></router-link>
        <router-link to="/lider/cotizaciones" class="card kpi" style="border-color:var(--cyan)"><div class="l">Cotizaciones cargadas</div><div class="v">{{ d.cotizaciones }}</div><div class="small muted">{{ d.con_cotizacion }} artículos cotizados</div></router-link>
        <router-link to="/lider/mi-solicitud" class="card kpi" style="border-color:var(--azul)">
          <div class="l">Mi solicitud</div>
          <div class="v" style="font-size:16px;margin-top:10px"><Badge v-if="d.solicitud" :estado="d.solicitud.estado" :texto="d.solicitud.estado_visible !== d.solicitud.estado ? d.solicitud.estado_visible : ''" /><span v-else class="muted">Sin crear</span></div>
          <div v-if="d.solicitud" class="small muted">{{ d.solicitud.n_items }} artículos</div>
        </router-link>
      </div>

      <div v-if="d.vigencia" class="cols-2">
        <div class="card">
          <h2>Artículos con precio de referencia</h2>
          <div class="row" style="justify-content:space-between"><span class="sub">{{ d.con_precio }} de {{ d.articulos }}</span><b>{{ avance }} %</b></div>
          <div class="progress" style="margin:8px 0 12px"><div :style="{ width: `${avance}%`, background: avance >= 80 ? 'var(--verde)' : avance >= 60 ? 'var(--amarillo)' : 'var(--rojo)' }" /></div>
          <div v-if="d.sin_precio" class="alert warn">{{ d.sin_precio }} artículos no tienen cotización ni precio histórico, por lo que <b>no se pueden incluir</b> en la solicitud hasta que cargue una cotización.</div>
          <div class="row">
            <router-link to="/lider/cotizaciones" class="btn">Cargar cotización</router-link>
            <router-link to="/lider/mi-solicitud" class="btn azul">{{ d.solicitud?.n_items ? 'Continuar solicitud' : 'Crear solicitud' }}</router-link>
          </div>
        </div>
        <div v-if="d.solicitud" class="card">
          <h2>Estado de mi solicitud</h2>
          <p><Badge :estado="d.solicitud.estado" :texto="d.solicitud.estado_visible !== d.solicitud.estado ? d.solicitud.estado_visible : ''" /> · {{ d.solicitud.n_items }} artículos</p>
          <p class="small muted">Última modificación: {{ fechaHora(d.solicitud.actualizado) }}</p>
          <div v-if="d.solicitud.estado === 'DEVUELTA'" class="alert warn"><b>Devuelta por el administrador:</b> {{ d.solicitud.observaciones_admin }}</div>
          <router-link to="/lider/seguimiento" class="btn ghost">Ver seguimiento</router-link>
        </div>
      </div>
    </template>
    <div v-else class="card"><div class="skeleton" v-for="i in 4" :key="i" /></div>
  </div>
</template>
