<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import { toast, toastError } from '../../util'

const lotes = ref([])
const form = ref(null)
const cargar = async () => { lotes.value = await api.get('/lotes') }
onMounted(cargar)
async function guardar() {
  try {
    if (form.value.id) await api.put(`/lotes/${form.value.id}`, form.value)
    else await api.post('/lotes', form.value)
    toast('Lote guardado')
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Lotes</h1><div class="sub">Agrupaciones temáticas del estudio de mercados del centro. Cada lote tiene un líder responsable.</div></div>
      <button class="btn" @click="form = { numero: lotes.length + 1, nombre: '', abreviatura: '', color: '#39A909', activo: true }">+ Nuevo lote</button></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>N.</th><th>Lote</th><th>Abreviatura</th><th class="right">Artículos activos</th><th>Líder(es)</th><th></th></tr></thead>
        <tbody><tr v-for="l in lotes" :key="l.id" :class="{ dis: !l.activo }">
          <td>{{ l.numero }}</td><td><span class="dot" :style="{ background: l.color }" />{{ l.nombre }}</td><td>{{ l.abreviatura }}</td>
          <td class="right">{{ l.articulos }}</td>
          <td>{{ l.lideres.map((u) => u.nombre).join(', ') }}<span v-if="!l.lideres.length" class="badge" style="background:var(--naranja)">Sin líder</span></td>
          <td class="right"><button class="btn ghost sm" @click="form = { ...l }">Editar</button></td>
        </tr></tbody>
      </table>
    </div>
    <p class="small muted">Para asignar líderes, cree o edite el usuario en <router-link to="/admin/usuarios">Usuarios</router-link>.</p>
    <Modal v-if="form" :titulo="form.id ? 'Editar lote' : 'Nuevo lote'" @cerrar="form = null">
      <form id="fl" class="form-grid" @submit.prevent="guardar">
        <label class="f req"><span>Número</span><input v-model.number="form.numero" type="number" min="1" required /></label>
        <label class="f req"><span>Abreviatura</span><input v-model="form.abreviatura" maxlength="10" required /></label>
        <label class="f req full"><span>Nombre</span><input v-model="form.nombre" required /></label>
        <label class="f"><span>Color</span><input v-model="form.color" type="color" /></label>
        <label class="f"><span>Estado</span><select v-model="form.activo"><option :value="true">Activo</option><option :value="false">Inactivo</option></select></label>
      </form>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fl">Guardar</button></template>
    </Modal>
  </div>
</template>
