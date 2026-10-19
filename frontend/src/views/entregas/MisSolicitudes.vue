<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import { useAuth } from '../../store'
import { fecha, money, toastError } from '../../util'

const auth = useAuth()
const router = useRouter()
const lista = ref(null)
onMounted(async () => { try { lista.value = await api.get('/entregas') } catch (e) { toastError(e) } })

const porLegalizar = computed(() => (lista.value || []).filter((e) => e.estado === 'ENTREGADA'))
const devueltas = computed(() => (lista.value || []).filter((e) => e.estado === 'DEVUELTA'))
</script>

<template>
  <div>
    <div class="page-head">
      <div><h1>Mis solicitudes de bienes</h1><div class="sub">Formato GIL-F-014 · {{ auth.usuario.coordinacion?.nombre }}</div></div>
      <router-link to="/instructor/solicitar" class="btn">+ Solicitar materiales</router-link>
    </div>
    <div v-if="!auth.usuario.documento" class="alert warn">Registre su número de identificación en <router-link to="/perfil">Mi perfil</router-link>: es obligatorio en el formato.</div>
    <div v-for="e in porLegalizar" :key="`l${e.id}`" class="alert" :class="e.extemporanea ? 'error' : 'warn'">
      <b>Solicitud N° {{ e.id }}:</b>
      <template v-if="e.extemporanea"> la legalización está <b>EXTEMPORÁNEA</b> (venció el {{ fecha(e.fecha_limite_legalizacion) }}). Cargue de inmediato el acta y las fotos.</template>
      <template v-else> recibió los materiales el {{ fecha(e.fecha_entrega) }}. Legalice antes del <b>{{ fecha(e.fecha_limite_legalizacion) }}</b> ({{ e.dias_habiles_restantes }} días hábiles).</template>
      <router-link :to="`/entregas/${e.id}`" style="margin-left:8px">Legalizar ›</router-link>
    </div>
    <div v-for="e in devueltas" :key="`d${e.id}`" class="alert warn"><b>Solicitud N° {{ e.id }} devuelta</b> por el coordinador. <router-link :to="`/entregas/${e.id}`">Ver observaciones y corregir ›</router-link></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>N°</th><th>Fecha</th><th>Lote</th><th>Ficha</th><th class="right">Bienes</th><th class="right">Valor</th><th>Estado</th><th>Entrega</th></tr></thead>
        <tbody>
          <tr v-for="e in lista || []" :key="e.id" class="click" @click="router.push(`/entregas/${e.id}`)">
            <td>#{{ e.id }}</td><td>{{ fecha(e.fecha_solicitud) }}</td>
            <td><span class="dot" :style="{ background: e.lote_color }" />{{ e.lote_numero }}. {{ e.lote }}</td><td>{{ e.ficha }}</td>
            <td class="right">{{ e.n_items }}</td><td class="right mono">{{ money(e.valor) }}</td>
            <td><Badge :estado="e.extemporanea ? 'EXTEMPORANEA' : e.estado" /></td><td>{{ fecha(e.fecha_entrega) }}</td>
          </tr>
          <tr v-if="lista && !lista.length"><td colspan="8" class="empty">Aún no ha solicitado materiales. <router-link to="/instructor/solicitar">Solicite el primero</router-link>.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
