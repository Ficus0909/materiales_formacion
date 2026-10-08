<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import { toast, toastError } from '../../util'

const lista = ref([])
const q = ref('')
const form = ref(null)
const cargar = async () => { lista.value = await api.get('/proveedores') }
onMounted(cargar)
const filtrados = computed(() => lista.value.filter((p) => !q.value || `${p.razon_social} ${p.nit}`.toLowerCase().includes(q.value.toLowerCase())))
async function guardar() {
  try {
    if (form.value.id) await api.put(`/proveedores/${form.value.id}`, form.value)
    else await api.post('/proveedores', form.value)
    toast('Proveedor guardado')
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Proveedores</h1><div class="sub">Empresas cotizantes. Los líderes también pueden registrarlas al cargar una cotización.</div></div>
      <button class="btn" @click="form = { nit: '', razon_social: '', contacto: '', email: '', telefono: '', activo: true }">+ Nuevo proveedor</button></div>
    <input v-model="q" placeholder="Buscar por razón social o NIT…" style="max-width:360px;width:100%;margin-bottom:12px" />
    <div class="table-wrap">
      <table>
        <thead><tr><th>NIT</th><th>Razón social</th><th>Contacto</th><th>Correo</th><th>Teléfono</th><th>Estado</th><th></th></tr></thead>
        <tbody><tr v-for="p in filtrados" :key="p.id" :class="{ dis: !p.activo }">
          <td class="mono">{{ p.nit }}</td><td>{{ p.razon_social }}</td><td>{{ p.contacto }}</td><td>{{ p.email }}</td><td>{{ p.telefono }}</td>
          <td>{{ p.activo ? 'Activo' : 'Inactivo' }}</td><td class="right"><button class="btn ghost sm" @click="form = { ...p }">Editar</button></td>
        </tr>
        <tr v-if="!filtrados.length"><td colspan="7" class="empty">Sin proveedores</td></tr></tbody>
      </table>
    </div>
    <Modal v-if="form" :titulo="form.id ? 'Editar proveedor' : 'Nuevo proveedor'" @cerrar="form = null">
      <form id="fpr" class="form-grid" @submit.prevent="guardar">
        <label class="f req"><span>NIT</span><input v-model="form.nit" required /></label>
        <label class="f req"><span>Razón social</span><input v-model="form.razon_social" required /></label>
        <label class="f"><span>Contacto</span><input v-model="form.contacto" /></label>
        <label class="f"><span>Correo</span><input v-model="form.email" type="email" /></label>
        <label class="f"><span>Teléfono</span><input v-model="form.telefono" /></label>
        <label class="f"><span>Estado</span><select v-model="form.activo"><option :value="true">Activo</option><option :value="false">Inactivo</option></select></label>
      </form>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fpr">Guardar</button></template>
    </Modal>
  </div>
</template>
