<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, qs } from '../../api'
import Modal from '../../components/Modal.vue'
import { useAuth } from '../../store'
import { toast, toastError } from '../../util'

const auth = useAuth()
const route = useRoute()
const ROLES = { MANAGER: 'Manager', ADMIN: 'Administrador', LIDER: 'Líder de lote' }
const usuarios = ref([])
const lotes = ref([])
const centros = ref([])
const centro = ref(route.query.centro_id ? Number(route.query.centro_id) : '')
const q = ref('')
const form = ref(null)
const pagina = ref(1)
const POR = 15

async function cargar() { usuarios.value = await api.get(`/usuarios${qs({ centro_id: centro.value })}`) }
onMounted(async () => {
  ;[lotes.value, centros.value] = await Promise.all([api.get('/lotes'), api.get('/centros')])
  cargar()
})
watch(centro, () => { pagina.value = 1; cargar() })
const filtrados = computed(() => usuarios.value.filter((u) => !q.value || `${u.nombre} ${u.email}`.toLowerCase().includes(q.value.toLowerCase())))
const visibles = computed(() => filtrados.value.slice((pagina.value - 1) * POR, pagina.value * POR))
// El administrador sólo gestiona los líderes de su centro; los administradores los gestiona el manager
const gestionable = (u) => auth.esManager || u.rol === 'LIDER'
const lotesDelCentro = computed(() => lotes.value.filter((l) => l.centro_id === form.value?.centro_id))

const nuevo = () => {
  form.value = { nombre: '', email: '', rol: auth.esManager ? 'ADMIN' : 'LIDER', centro_id: centro.value || auth.usuario.centro_id || centros.value[0]?.id || '', lote_id: '', activo: true, password: '' }
}
const editar = (u) => { form.value = { ...u, password: '' } }
watch(() => form.value?.centro_id, (n, o) => { if (o !== undefined && n !== o && form.value) form.value.lote_id = '' })
async function guardar() {
  const f = form.value
  const body = { ...f, centro_id: f.rol === 'MANAGER' ? null : f.centro_id || null, lote_id: f.rol === 'LIDER' ? f.lote_id || null : null, password: f.password || null }
  try {
    const r = f.id ? await api.put(`/usuarios/${f.id}`, body) : await api.post('/usuarios', body)
    toast(body.password
      ? `Usuario guardado. ${r.correo_enviado ? `Las credenciales se enviaron a ${r.email}.` : 'El correo no está configurado: entréguele las credenciales manualmente.'} Deberá cambiar la contraseña en su primer ingreso.`
      : 'Usuario guardado', 'ok', 7000)
    form.value = null
    cargar()
  } catch (e) { toastError(e) }
}
async function alternar(u) {
  try { await api.put(`/usuarios/${u.id}`, { ...u, activo: !u.activo, password: null }); cargar() } catch (e) { toastError(e) }
}
async function eliminar(u) {
  if (!confirm(`¿Eliminar a ${u.nombre}?`)) return
  try { await api.del(`/usuarios/${u.id}`); cargar() } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Usuarios</h1>
      <div class="sub">{{ usuarios.length }} usuarios · {{ auth.esManager ? 'el manager gestiona los administradores de cada centro' : `líderes del ${auth.usuario.centro?.nombre}` }}</div></div>
      <button class="btn" @click="nuevo">+ Nuevo {{ auth.esManager ? 'usuario' : 'líder' }}</button></div>
    <div class="row" style="margin-bottom:12px">
      <input v-model="q" placeholder="Buscar por nombre o correo…" style="max-width:360px;width:100%" @input="pagina = 1" />
      <select v-if="auth.esManager" v-model="centro"><option value="">Todos los centros</option><option v-for="c in centros" :key="c.id" :value="c.id">{{ c.nombre }}</option></select>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th v-if="auth.esManager">Centro</th><th>Lote</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in visibles" :key="u.id">
            <td>{{ u.nombre }}</td><td>{{ u.email }}</td><td>{{ ROLES[u.rol] }}</td><td v-if="auth.esManager">{{ u.centro?.nombre || '—' }}</td><td>{{ u.lote?.nombre || '—' }}</td>
            <td><span class="badge" :style="{ background: u.activo ? 'var(--verde)' : '#A0AEC0' }">{{ u.activo ? 'Activo' : 'Inactivo' }}</span></td>
            <td class="right nowrap">
              <template v-if="gestionable(u)"><button class="btn ghost sm" @click="editar(u)">Editar</button> <button v-if="u.id !== auth.usuario.id" class="btn ghost sm" @click="alternar(u)">{{ u.activo ? 'Desactivar' : 'Activar' }}</button> <button v-if="u.id !== auth.usuario.id" class="btn ghost sm" style="color:var(--rojo)" @click="eliminar(u)">Eliminar</button></template>
              <span v-else class="small muted">Lo gestiona el manager</span>
            </td>
          </tr>
          <tr v-if="!visibles.length"><td :colspan="auth.esManager ? 7 : 6" class="empty">Sin usuarios</td></tr>
        </tbody>
      </table>
    </div>
    <div class="pager"><button class="btn ghost sm" :disabled="pagina === 1" @click="pagina--">‹</button>{{ pagina }} / {{ Math.max(1, Math.ceil(filtrados.length / POR)) }}<button class="btn ghost sm" :disabled="pagina * POR >= filtrados.length" @click="pagina++">›</button></div>
    <Modal v-if="form" :titulo="form.id ? 'Editar usuario' : 'Nuevo usuario'" @cerrar="form = null">
      <form id="fu" class="form-grid" @submit.prevent="guardar">
        <label class="f req full"><span>Nombre completo</span><input v-model="form.nombre" required /></label>
        <label class="f req full"><span>Correo institucional</span><input v-model="form.email" type="email" required /></label>
        <label class="f req"><span>Rol</span>
          <select v-model="form.rol" :disabled="!auth.esManager || form.id === auth.usuario.id">
            <option v-if="auth.esManager" value="MANAGER">Manager (todos los centros)</option>
            <option v-if="auth.esManager" value="ADMIN">Administrador / Analista del centro</option>
            <option value="LIDER">Líder de lote</option>
          </select></label>
        <label v-if="auth.esManager && form.rol !== 'MANAGER'" class="f req"><span>Centro de formación</span>
          <select v-model="form.centro_id" required><option value="" disabled>Seleccione…</option><option v-for="c in centros.filter((c) => c.activo || c.id === form.centro_id)" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></label>
        <label v-if="form.rol === 'LIDER'" class="f req"><span>Lote asignado</span><select v-model="form.lote_id" required><option value="" disabled>{{ lotesDelCentro.length ? 'Seleccione…' : 'El centro no tiene lotes' }}</option><option v-for="l in lotesDelCentro" :key="l.id" :value="l.id">{{ l.numero }}. {{ l.nombre }}</option></select></label>
        <label class="f full" :class="{ req: !form.id }"><span>{{ form.id ? 'Nueva contraseña temporal (opcional)' : 'Contraseña temporal' }}</span><input v-model="form.password" type="text" :required="!form.id" placeholder="Mín. 8, mayúscula, número y especial" /></label>
      </form>
      <p v-if="form.rol === 'MANAGER'" class="small muted">El manager administra los centros, sus administradores, las vigencias y la configuración común, y consulta todos los centros.</p>
      <template #pie><button class="btn ghost" @click="form = null">Cancelar</button><button class="btn" form="fu">Guardar</button></template>
    </Modal>
  </div>
</template>
