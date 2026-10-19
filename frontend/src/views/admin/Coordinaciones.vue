<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import { toast, toastError } from '../../util'

const lista = ref([])
const form = ref(null)
const cargar = async () => { lista.value = await api.get('/coordinaciones') }
onMounted(cargar)
async function guardar() {
  try {
    if (form.value.id) await api.put(`/coordinaciones/${form.value.id}`, form.value)
    else await api.post('/coordinaciones', form.value)
    toast('Coordinación guardada')
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Coordinaciones</h1><div class="sub">Áreas del centro a las que pertenecen instructores y coordinadores (campo ÁREA del formato GIL-F-014).</div></div>
      <button class="btn" @click="form = { nombre: '', activo: true }">+ Nueva coordinación</button></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Coordinación</th><th class="right">Coordinadores</th><th class="right">Instructores</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="c in lista" :key="c.id" :class="{ dis: !c.activo }">
            <td>{{ c.nombre }}</td>
            <td class="right"><span v-if="c.coordinadores">{{ c.coordinadores }}</span><span v-else class="badge" style="background:var(--naranja)">Sin coordinador</span></td>
            <td class="right">{{ c.instructores }}</td>
            <td>{{ c.activo ? 'Activa' : 'Inactiva' }}</td>
            <td class="right"><button class="btn ghost sm" @click="form = { ...c }">Editar</button></td>
          </tr>
          <tr v-if="!lista.length"><td colspan="5" class="empty">No hay coordinaciones</td></tr>
        </tbody>
      </table>
    </div>
    <p class="small muted">Los coordinadores se crean en <router-link to="/admin/usuarios">Usuarios</router-link> (rol Coordinador). Mientras una coordinación no tenga coordinador, el administrador aprueba el registro de sus instructores.</p>
    <Modal v-if="form" :titulo="form.id ? 'Editar coordinación' : 'Nueva coordinación'" @cerrar="form = null">
      <form id="fco" class="form-grid" @submit.prevent="guardar">
        <label class="f req full"><span>Nombre</span><input v-model="form.nombre" required placeholder="Ej. Coordinación Académica" /></label>
        <label class="f"><span>Estado</span><select v-model="form.activo"><option :value="true">Activa</option><option :value="false">Inactiva</option></select></label>
      </form>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fco">Guardar</button></template>
    </Modal>
  </div>
</template>
