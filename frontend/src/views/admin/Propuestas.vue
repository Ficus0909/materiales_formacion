<script setup>
import { onMounted, ref, watch } from 'vue'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import Modal from '../../components/Modal.vue'
import { fecha, toast, toastError } from '../../util'

const estado = ref('PENDIENTE')
const lista = ref([])
const resp = ref(null)
const cargar = async () => { lista.value = await api.get(`/propuestas?estado=${estado.value}`) }
onMounted(cargar)
watch(estado, cargar)
function responder(p, aprobar) {
  resp.value = { p, aprobar, respuesta: '', codigo_unspsc: '', nombre: p.nombre, unidad: p.unidad, descripcion: p.descripcion }
}
async function enviar() {
  const { p, ...body } = resp.value
  try {
    await api.post(`/propuestas/${p.id}/responder`, body)
    toast(body.aprobar ? 'Artículo creado en el listado maestro' : 'Propuesta rechazada')
    resp.value = null
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Artículos propuestos por líderes</h1><div class="sub">El administrador asigna el código UNSPSC y decide si se incorpora al listado maestro.</div></div>
      <select v-model="estado"><option value="PENDIENTE">Pendientes</option><option value="APROBADA">Aprobadas</option><option value="RECHAZADA">Rechazadas</option><option value="">Todas</option></select></div>
    <div class="grid">
      <div v-for="p in lista" :key="p.id" class="card">
        <div class="row" style="justify-content:space-between"><h2 style="margin:0">{{ p.nombre }}</h2><Badge :estado="p.estado" /></div>
        <p class="sub">{{ p.lote }} · {{ p.lider }} · {{ fecha(p.creado) }} · Unidad {{ p.unidad }}</p>
        <p style="white-space:pre-line">{{ p.descripcion }}</p>
        <p v-if="p.justificacion" class="small"><b>Justificación:</b> {{ p.justificacion }}</p>
        <p v-if="p.respuesta" class="small"><b>Respuesta:</b> {{ p.respuesta }}</p>
        <div v-if="p.estado === 'PENDIENTE'" class="row"><button class="btn" @click="responder(p, true)">Aprobar y crear</button><button class="btn rojo" @click="responder(p, false)">Rechazar</button></div>
      </div>
      <div v-if="!lista.length" class="card empty">No hay propuestas</div>
    </div>
    <Modal v-if="resp" :titulo="resp.aprobar ? 'Crear artículo' : 'Rechazar propuesta'" @cerrar="resp = null">
      <form id="fr" class="form-grid" @submit.prevent="enviar">
        <template v-if="resp.aprobar">
          <label class="f req"><span>Código UNSPSC</span><input v-model="resp.codigo_unspsc" required pattern="\d{8}" maxlength="8" /></label>
          <label class="f req"><span>Unidad SECOP II</span><input v-model="resp.unidad" required /></label>
          <label class="f req full"><span>Nombre</span><input v-model="resp.nombre" required /></label>
          <label class="f full"><span>Ficha técnica</span><textarea v-model="resp.descripcion" rows="4" /></label>
        </template>
        <label class="f full" :class="{ req: !resp.aprobar }"><span>Mensaje al líder</span><textarea v-model="resp.respuesta" :required="!resp.aprobar" rows="2" /></label>
      </form>
      <template #pie><button class="btn ghost" @click="resp = null">Cancelar</button><button class="btn" :class="{ rojo: !resp.aprobar }" form="fr">{{ resp.aprobar ? 'Crear artículo' : 'Rechazar' }}</button></template>
    </Modal>
  </div>
</template>
