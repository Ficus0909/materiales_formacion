<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import { fecha, money, toastError } from '../../util'
import DetalleSolicitud from '../DetalleSolicitud.vue'

const lista = ref(null)
const sel = ref(null)
onMounted(async () => {
  try {
    lista.value = await api.get('/solicitudes')
    sel.value = lista.value[0]?.id || null
  } catch (e) { toastError(e) }
})
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Seguimiento</h1><div class="sub">Estado e historial de las solicitudes de su lote (sólo lectura)</div></div></div>
    <div v-if="lista && !lista.length" class="alert info">Su lote aún no tiene solicitudes.</div>
    <div v-if="lista?.length > 1" class="table-wrap" style="margin-bottom:16px">
      <table>
        <thead><tr><th>Vigencia</th><th>Estado</th><th class="right">Artículos</th><th class="right">Valor</th><th>Enviada</th></tr></thead>
        <tbody><tr v-for="s in lista" :key="s.id" class="click" :style="sel === s.id ? 'background:#EEF6EA' : ''" @click="sel = s.id">
          <td><b>{{ s.vigencia }}</b></td><td><Badge :estado="s.estado" :texto="s.estado_visible !== s.estado ? s.estado_visible : ''" :color="s.estado_post_color" /></td>
          <td class="right">{{ s.n_items }}</td><td class="right mono">{{ money(s.total) }}</td><td>{{ fecha(s.fecha_envio) }}</td>
        </tr></tbody>
      </table>
    </div>
    <DetalleSolicitud v-if="sel" :id="sel" :key="sel" />
  </div>
</template>
