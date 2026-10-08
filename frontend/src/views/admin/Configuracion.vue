<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../../api'
import { useAuth } from '../../store'
import { toast, toastError } from '../../util'

const auth = useAuth()
const tab = ref('estados')
const estados = ref([])
const nuevoEstado = ref({ nombre: '', color: '#71277A' })
const parametros = ref([])
const indices = ref([])
const correo = ref(null)
const probando = ref(false)
const nuevoIndice = ref({ anio: new Date().getFullYear(), ipc: '', puntos_adicionales: 0.02 })

async function cargar() {
  ;[estados.value, parametros.value, indices.value, correo.value] = await Promise.all([
    api.get('/estados-post'), api.get('/parametros'), api.get('/indices'), api.get('/correo/estado')])
}
onMounted(cargar)

async function crearEstado() {
  try { estados.value = await api.post('/estados-post', { ...nuevoEstado.value, activo: true }); nuevoEstado.value = { nombre: '', color: '#71277A' } } catch (e) { toastError(e) }
}
async function guardarEstado(e) {
  try { estados.value = await api.put(`/estados-post/${e.id}`, e); toast('Estado actualizado') } catch (err) { toastError(err) }
}
async function mover(i, d) {
  const ids = estados.value.map((e) => e.id)
  ;[ids[i], ids[i + d]] = [ids[i + d], ids[i]]
  try { estados.value = await api.post('/estados-post/reordenar', ids) } catch (e) { toastError(e) }
}
async function guardarParametros() {
  try {
    parametros.value = await api.put('/parametros', Object.fromEntries(parametros.value.map((p) => [p.clave, String(p.valor)])))
    toast('Parámetros guardados: el análisis de precios se recalcula con estos valores')
  } catch (e) { toastError(e) }
}
async function probarCorreo() {
  probando.value = true
  try { const r = await api.post('/correo/prueba'); toast(`Correo de prueba enviado a ${r.para}`) } catch (e) { toastError(e) } finally { probando.value = false }
}
async function guardarIndice(i) {
  try { indices.value = await api.put('/indices', { ...i, ipc: Number(i.ipc), puntos_adicionales: Number(i.puntos_adicionales) }); toast('Índice guardado') } catch (e) { toastError(e) }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Configuración</h1><div class="sub">Reglas parametrizables del proceso, comunes a todos los centros</div></div></div>
    <div v-if="!auth.esManager" class="alert info">Estos parámetros aplican a todos los centros y sólo el manager los modifica. Aquí puede consultarlos y probar el correo.</div>
    <div class="tabs">
      <button :class="{ on: tab === 'estados' }" @click="tab = 'estados'">Estados post-aprobación</button>
      <button :class="{ on: tab === 'parametros' }" @click="tab = 'parametros'">Análisis de precios</button>
      <button :class="{ on: tab === 'indices' }" @click="tab = 'indices'">IPC / indexación</button>
      <button :class="{ on: tab === 'correo' }" @click="tab = 'correo'">Correo</button>
    </div>

    <fieldset :disabled="!auth.esManager" class="plano">
    <div v-if="tab === 'estados'" class="card" style="max-width:760px">
      <p class="sub">Etapas del ciclo de compra tras aprobar una solicitud. Sólo avanzan en el orden definido aquí.</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Orden</th><th>Nombre</th><th>Color</th><th>Activo</th><th></th></tr></thead>
          <tbody><tr v-for="(e, i) in estados" :key="e.id">
            <td class="nowrap">{{ i + 1 }} <button class="btn ghost sm" :disabled="i === 0" @click="mover(i, -1)">↑</button><button class="btn ghost sm" :disabled="i === estados.length - 1" @click="mover(i, 1)">↓</button></td>
            <td><input v-model="e.nombre" /></td><td><input v-model="e.color" type="color" /></td>
            <td><input v-model="e.activo" type="checkbox" /></td><td><button class="btn ghost sm" @click="guardarEstado(e)">Guardar</button></td>
          </tr></tbody>
        </table>
      </div>
      <form class="row" style="margin-top:12px" @submit.prevent="crearEstado">
        <input v-model="nuevoEstado.nombre" placeholder="Nuevo estado (ej. Entregado al ambiente)" required class="grow" />
        <input v-model="nuevoEstado.color" type="color" /><button class="btn">Agregar</button>
      </form>
    </div>

    <div v-if="tab === 'parametros'" class="card" style="max-width:860px">
      <div class="form-grid">
        <label v-for="p in parametros" :key="p.clave" class="f"><span>{{ p.descripcion }}</span><input v-model="p.valor" inputmode="decimal" /></label>
      </div>
      <p class="small muted">Los umbrales se expresan en decimal (0.25 = 25 %). Valor 1/0 para sí/no.</p>
      <button class="btn" @click="guardarParametros">Guardar parámetros</button>
    </div>

    <div v-if="tab === 'indices'" class="card" style="max-width:760px">
      <p class="sub">Los precios históricos se indexan con VF = VP × Π(1 + IPC + puntos) desde el año del precio hasta el año anterior a la vigencia (Porcentaje de Ajuste Año Gravable).</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Año</th><th>IPC (decimal)</th><th>Puntos adicionales</th><th>Factor anual</th><th></th></tr></thead>
          <tbody>
            <tr v-for="i in indices" :key="i.anio">
              <td>{{ i.anio }}</td><td><input v-model="i.ipc" style="width:100px" /></td><td><input v-model="i.puntos_adicionales" style="width:100px" /></td>
              <td class="mono">{{ (1 + Number(i.ipc) + Number(i.puntos_adicionales)).toFixed(4) }}</td>
              <td><button class="btn ghost sm" @click="guardarIndice(i)">Guardar</button></td>
            </tr>
            <tr>
              <td><input v-model.number="nuevoIndice.anio" type="number" style="width:90px" /></td>
              <td><input v-model="nuevoIndice.ipc" placeholder="0.051" style="width:100px" /></td>
              <td><input v-model="nuevoIndice.puntos_adicionales" style="width:100px" /></td><td></td>
              <td><button class="btn sm" :disabled="nuevoIndice.ipc === ''" @click="guardarIndice(nuevoIndice)">Agregar</button></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="small muted">Si un año no tiene índice registrado se usan los parámetros «IPC por defecto» y «puntos adicionales por defecto».</p>
    </div>

    </fieldset>

    <div v-if="tab === 'correo' && correo" class="card" style="max-width:760px">
      <div v-if="correo.habilitado" class="alert ok">Correo activo: las notificaciones se envían desde <b>{{ correo.remitente }}</b> ({{ correo.servidor }}:{{ correo.puerto }}).</div>
      <div v-else class="alert warn">El correo no está configurado: las notificaciones sólo se ven en la aplicación. Defina las variables <code>SMTP_HOST</code>, <code>SMTP_PORT</code>, <code>SMTP_USER</code>, <code>SMTP_PASSWORD</code> y <code>SMTP_FROM</code> en el archivo <code>.env</code> del servidor y reinicie.</div>
      <p class="sub">Se envía correo a la persona notificada cuando:</p>
      <ul class="small">
        <li>El manager o el administrador crea un usuario o le restablece la contraseña (credenciales temporales).</li>
        <li>El manager abre una vigencia (a los líderes y administradores de todos los centros).</li>
        <li>Un líder envía o reenvía su solicitud, o propone un artículo (a los administradores de su centro).</li>
        <li>Una solicitud pasa a revisión, se aprueba, se devuelve, se rechaza, se cancela al cerrar la vigencia o avanza en el ciclo de compra (al líder).</li>
        <li>Se responde una propuesta de artículo (al líder).</li>
      </ul>
      <p class="small muted">Los enlaces de los correos apuntan a {{ correo.app_url }} (variable <code>APP_URL</code>).</p>
      <button class="btn" :disabled="!correo.habilitado || probando" @click="probarCorreo">{{ probando ? 'Enviando…' : 'Enviarme un correo de prueba' }}</button>
    </div>
  </div>
</template>

<style scoped>
.plano { border: 0; padding: 0; margin: 0; min-width: 0; }
</style>
