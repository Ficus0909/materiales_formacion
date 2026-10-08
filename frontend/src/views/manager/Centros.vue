<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import Modal from '../../components/Modal.vue'
import { toast, toastError } from '../../util'

const centros = ref([])
const form = ref(null)
const carga = ref(null) // { centro, listado_desde }
const cargando = ref(false)
const cargar = async () => { centros.value = await api.get('/centros') }
onMounted(cargar)

async function guardar() {
  const eraActivo = centros.value.find((c) => c.id === form.value.id)?.activo
  if (form.value.id && eraActivo && !form.value.activo
    && !confirm(`¿Desactivar ${form.value.nombre}? Sus administradores y líderes no podrán ingresar hasta que lo reactive.`)) return
  try {
    let msg = 'Centro guardado'
    if (form.value.id) await api.put(`/centros/${form.value.id}`, form.value)
    else {
      const r = await api.post('/centros', { ...form.value, cargar_listado: form.value.listado_desde !== '', listado_desde: form.value.listado_desde || null })
      const l = r.listado_copiado
      msg = `Centro creado${l ? ` con el listado maestro de ${l.origen}: ${l.lotes} lotes y ${l.articulos} artículos` : ' sin listado maestro'}. Ahora cree su administrador en Usuarios.`
    }
    toast(msg, 'ok', 8000)
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
// Por defecto el centro nuevo recibe el listado maestro del centro por defecto ('' = empezar vacío)
function nuevo() {
  const origen = centros.value.find((c) => c.por_defecto && c.articulos) || centros.value.find((c) => c.articulos)
  form.value = { codigo: '', nombre: '', regional: '', activo: true, listado_desde: origen?.id ?? '' }
}
const origenes = (destino) => centros.value.filter((c) => c.articulos && c.id !== destino?.id)
function abrirCarga(c) {
  const o = origenes(c)
  carga.value = { centro: c, listado_desde: (o.find((x) => x.por_defecto) || o[0])?.id ?? '' }
}
async function cargarListado() {
  cargando.value = true
  try {
    const r = await api.post(`/centros/${carga.value.centro.id}/cargar-listado`, { listado_desde: carga.value.listado_desde })
    const l = r.listado_copiado
    toast(`${r.nombre} recibió el listado maestro de ${l.origen}: ${l.lotes} lotes y ${l.articulos} artículos`, 'ok', 8000)
    carga.value = null
    cargar()
  } catch (e) { toastError(e) } finally { cargando.value = false }
}
async function eliminar(c) {
  if (!confirm(`¿Eliminar el centro ${c.nombre}?`)) return
  try { await api.del(`/centros/${c.id}`); cargar() } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Centros de formación</h1><div class="sub">Cada centro tiene su listado maestro, lotes, líderes, cotizaciones y solicitudes. Su administrador gestiona los líderes del centro.</div></div>
      <button class="btn" @click="nuevo">+ Nuevo centro</button></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Código</th><th>Centro</th><th>Regional</th><th class="right">Lotes</th><th class="right">Artículos activos</th><th class="right">Administradores</th><th class="right">Líderes</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="c in centros" :key="c.id" :class="{ dis: !c.activo }">
            <td class="mono">{{ c.codigo }}</td><td>{{ c.nombre }}</td><td>{{ c.regional }}</td>
            <td class="right">{{ c.lotes }}</td><td class="right">{{ c.articulos }}</td>
            <td class="right"><span v-if="c.administradores">{{ c.administradores }}</span><span v-else class="badge" style="background:var(--naranja)">Sin administrador</span></td>
            <td class="right">{{ c.lideres }}</td>
            <td><span class="badge" :style="{ background: c.activo ? 'var(--verde)' : '#A0AEC0' }">{{ c.activo ? 'Activo' : 'Inactivo' }}</span></td>
            <td class="right nowrap">
              <router-link class="btn ghost sm" :to="`/admin/usuarios?centro_id=${c.id}`">Usuarios</router-link>
              <button v-if="!c.lotes" class="btn sm" @click="abrirCarga(c)">Cargar listado</button>
              <button class="btn ghost sm" @click="form = { ...c }">Editar</button>
              <button v-if="!c.lotes" class="btn ghost sm" style="color:var(--rojo)" @click="eliminar(c)">Eliminar</button>
            </td>
          </tr>
          <tr v-if="!centros.length"><td colspan="9" class="empty">No hay centros</td></tr>
        </tbody>
      </table>
    </div>
    <p class="small muted">Para poner en marcha un centro: créelo aquí (recibe el listado maestro predeterminado), cree su administrador en <router-link to="/admin/usuarios">Usuarios</router-link>, y el administrador ajusta el listado y crea los líderes.</p>
    <Modal v-if="carga" :titulo="`Cargar listado maestro · ${carga.centro.nombre}`" @cerrar="carga = null">
      <label v-if="origenes(carga.centro).length" class="f"><span>Copiar el listado maestro de</span>
        <select v-model="carga.listado_desde">
          <option v-for="c in origenes(carga.centro)" :key="c.id" :value="c.id">{{ c.nombre }} ({{ c.lotes }} lotes, {{ c.articulos }} artículos){{ c.por_defecto ? ' · predeterminado' : '' }}</option>
        </select></label>
      <div v-else class="alert warn">Ningún otro centro tiene artículos en su listado maestro. El administrador del centro puede importarlo desde Excel.</div>
      <p class="small muted">Se copian los lotes y los artículos activos. No se copian cotizaciones, precios históricos ni solicitudes: cada centro hace su propio estudio de mercados. Después, el administrador del centro puede editar el listado o actualizarlo con el importador.</p>
      <template #pie><button class="btn ghost" @click="carga = null">Cancelar</button><button class="btn" :disabled="cargando || !carga.listado_desde" @click="cargarListado">{{ cargando ? 'Cargando…' : 'Cargar listado' }}</button></template>
    </Modal>
    <Modal v-if="form" :titulo="form.id ? 'Editar centro' : 'Nuevo centro de formación'" @cerrar="form = null">
      <form id="fc" class="form-grid" @submit.prevent="guardar">
        <label class="f req"><span>Código</span><input v-model="form.codigo" maxlength="20" required placeholder="Ej. CASA" /></label>
        <label class="f"><span>Regional</span><input v-model="form.regional" placeholder="Ej. Santander" /></label>
        <label class="f req full"><span>Nombre</span><input v-model="form.nombre" required placeholder="Ej. Centro de Atención al Sector Agropecuario" /></label>
        <label v-if="!form.id" class="f full"><span>Listado maestro inicial</span>
          <select v-model="form.listado_desde">
            <option v-for="c in centros.filter((c) => c.articulos)" :key="c.id" :value="c.id">Copiar el de {{ c.nombre }} ({{ c.lotes }} lotes, {{ c.articulos }} artículos){{ c.por_defecto ? ' · predeterminado' : '' }}</option>
            <option value="">Sin listado (el administrador lo importará)</option>
          </select></label>
        <label v-if="form.id" class="f"><span>Estado</span><select v-model="form.activo"><option :value="true">Activo</option><option :value="false">Inactivo (bloquea el ingreso de sus usuarios)</option></select></label>
      </form>
      <p v-if="!form.id && form.listado_desde !== ''" class="small muted">Se copian los lotes y los artículos activos. No se copian cotizaciones, precios históricos ni solicitudes: cada centro hace su propio estudio de mercados. El administrador del centro podrá editar el listado o reemplazarlo con el importador.</p>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fc">Guardar</button></template>
    </Modal>
  </div>
</template>
