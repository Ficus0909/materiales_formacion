<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAuth } from '../../store'
import { fecha, toast, toastError } from '../../util'

const auth = useAuth()
const lista = ref([])
const cargar = async () => { try { lista.value = await api.get('/instructores') } catch (e) { toastError(e) } }
onMounted(cargar)
const pendientes = computed(() => lista.value.filter((u) => !u.aprobado))
const activos = computed(() => lista.value.filter((u) => u.aprobado))

async function accion(u, que) {
  if (que === 'rechazar' && !confirm(`¿Rechazar el registro de ${u.nombre}? Se eliminará y se le avisará por correo.`)) return
  try {
    if (que === 'activo') await api.post(`/instructores/${u.id}/activo`, { activo: !u.activo })
    else await api.post(`/instructores/${u.id}/${que}`)
    toast({ aprobar: `${u.nombre} ya puede ingresar`, rechazar: 'Registro rechazado', activo: 'Cuenta actualizada' }[que])
    cargar()
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Instructores</h1>
      <div class="sub">{{ auth.esCoordinador ? auth.usuario.coordinacion?.nombre : 'Todas las coordinaciones del centro' }} · se registran solos y usted aprueba su cuenta</div></div></div>
    <div class="card">
      <h2>Registros pendientes de aprobación <span v-if="pendientes.length" class="badge" style="background:var(--naranja)">{{ pendientes.length }}</span></h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Nombre</th><th>Correo</th><th>Documento</th><th v-if="!auth.esCoordinador">Coordinación</th><th>Registrado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in pendientes" :key="u.id">
            <td>{{ u.nombre }}</td><td>{{ u.email }}</td><td class="mono">{{ u.documento }}</td><td v-if="!auth.esCoordinador">{{ u.coordinacion?.nombre }}</td>
            <td>{{ fecha(u.creado) }}</td>
            <td class="right nowrap"><button class="btn ghost sm" style="color:var(--rojo)" @click="accion(u, 'rechazar')">Rechazar</button> <button class="btn sm" @click="accion(u, 'aprobar')">Aprobar</button></td>
          </tr>
          <tr v-if="!pendientes.length"><td :colspan="auth.esCoordinador ? 5 : 6" class="empty">No hay registros pendientes</td></tr>
        </tbody>
      </table></div>
    </div>
    <div class="card">
      <h2>Instructores con cuenta</h2>
      <div class="table-wrap"><table>
        <thead><tr><th>Nombre</th><th>Correo</th><th>Documento</th><th v-if="!auth.esCoordinador">Coordinación</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          <tr v-for="u in activos" :key="u.id" :class="{ dis: !u.activo }">
            <td>{{ u.nombre }}</td><td>{{ u.email }}</td><td class="mono">{{ u.documento }}</td><td v-if="!auth.esCoordinador">{{ u.coordinacion?.nombre }}</td>
            <td><span class="badge" :style="{ background: u.activo ? 'var(--verde)' : '#A0AEC0' }">{{ u.activo ? 'Activo' : 'Inactivo' }}</span></td>
            <td class="right"><button class="btn ghost sm" @click="accion(u, 'activo')">{{ u.activo ? 'Desactivar' : 'Activar' }}</button></td>
          </tr>
          <tr v-if="!activos.length"><td :colspan="auth.esCoordinador ? 5 : 6" class="empty">Aún no hay instructores</td></tr>
        </tbody>
      </table></div>
      <p class="small muted">Los instructores se registran en la página de inicio de sesión («Regístrese aquí») con su correo institucional.</p>
    </div>
  </div>
</template>
