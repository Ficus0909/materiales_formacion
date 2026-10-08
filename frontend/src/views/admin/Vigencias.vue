<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Badge from '../../components/Badge.vue'
import Modal from '../../components/Modal.vue'
import { useAuth } from '../../store'
import { fecha, toast, toastError } from '../../util'

const auth = useAuth()
const vigencias = ref([])
const form = ref(null)
const cargar = async () => { vigencias.value = await api.get('/vigencias'); auth.cargarVigencia() }
onMounted(cargar)

function nueva() {
  const anio = Math.max(new Date().getFullYear() + 1, ...vigencias.value.map((v) => v.anio + 1))
  form.value = { codigo: String(anio), anio, fecha_inicio: '', fecha_cierre: '' }
}
async function guardar() {
  try {
    if (form.value.id) await api.put(`/vigencias/${form.value.id}`, form.value)
    else await api.post('/vigencias', form.value)
    toast('Vigencia guardada')
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
async function accion(v, a) {
  const msg = a === 'abrir' ? `¿Abrir la vigencia ${v.codigo}? Se notificará a los líderes y administradores de todos los centros.`
    : `¿Cerrar la vigencia ${v.codigo} en TODOS los centros? Las solicitudes en borrador o devueltas se CANCELARÁN y no se podrán cargar más cotizaciones.`
  if (!confirm(msg)) return
  try {
    const r = await api.post(`/vigencias/${v.id}/${a}`)
    toast(a === 'abrir' ? 'Vigencia abierta' : `Vigencia cerrada (${r.canceladas} solicitudes canceladas)`)
    cargar()
  } catch (e) { toastError(e) }
}
async function eliminar(v) {
  if (!confirm(`¿Eliminar la vigencia ${v.codigo}?`)) return
  try { await api.del(`/vigencias/${v.id}`); cargar() } catch (e) { toastError(e) }
}
const borde = (e) => ({ ABIERTA: 'var(--verde)', CERRADA: 'var(--azul)' }[e] || 'var(--texto2)')
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Vigencias</h1><div class="sub">Períodos en los que los líderes de todos los centros cotizan y solicitan. Sólo puede haber una vigencia abierta.</div></div>
      <button v-if="auth.esManager" class="btn" @click="nueva">+ Nueva vigencia</button></div>
    <div v-if="!auth.esManager" class="alert info">Las vigencias son comunes a todos los centros: las crea, abre y cierra el manager. Los conteos corresponden a su centro.</div>
    <div class="cols-2">
      <div v-for="v in vigencias" :key="v.id" class="card" :style="{ borderTop: `4px solid ${borde(v.estado)}` }">
        <div class="row" style="justify-content:space-between"><h2 style="margin:0">Vigencia {{ v.codigo }}</h2><Badge :estado="v.estado" /></div>
        <p class="sub">{{ fecha(v.fecha_inicio) }} → {{ fecha(v.fecha_cierre) }} · año de precios {{ v.anio }}</p>
        <p>{{ v.solicitudes }} solicitudes · {{ v.cotizaciones }} cotizaciones</p>
        <div v-if="auth.esManager" class="row">
          <button v-if="v.estado !== 'CERRADA'" class="btn ghost sm" @click="form = { ...v }">{{ v.estado === 'ABIERTA' ? 'Extender cierre' : 'Editar' }}</button>
          <button v-if="v.estado === 'PROGRAMADA'" class="btn sm" @click="accion(v, 'abrir')">Abrir</button>
          <button v-if="v.estado === 'ABIERTA'" class="btn rojo sm" @click="accion(v, 'cerrar')">Cerrar</button>
          <router-link v-if="v.estado !== 'PROGRAMADA'" class="btn ghost sm" to="/admin/solicitudes">Ver solicitudes</router-link>
          <button v-if="!v.solicitudes && !v.cotizaciones" class="btn ghost sm" style="color:var(--rojo)" @click="eliminar(v)">Eliminar</button>
        </div>
      </div>
    </div>
    <div v-if="!vigencias.length" class="empty card">No hay vigencias. Cree la primera.</div>
    <Modal v-if="form" :titulo="form.id ? `Vigencia ${form.codigo}` : 'Nueva vigencia'" @cerrar="form = null">
      <form id="fv" class="form-grid" @submit.prevent="guardar">
        <label class="f req"><span>Código</span><input v-model="form.codigo" required :disabled="form.estado === 'ABIERTA'" /></label>
        <label class="f req"><span>Año de los precios</span><input v-model.number="form.anio" type="number" required :disabled="form.estado === 'ABIERTA'" /></label>
        <label class="f req"><span>Fecha de inicio</span><input v-model="form.fecha_inicio" type="date" required :disabled="form.estado === 'ABIERTA'" /></label>
        <label class="f req"><span>Fecha de cierre</span><input v-model="form.fecha_cierre" type="date" required /></label>
      </form>
      <p class="small muted">El año de precios se usa para indexar los históricos con IPC (ver Configuración).</p>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fv">Guardar</button></template>
    </Modal>
  </div>
</template>
