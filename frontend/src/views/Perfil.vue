<script setup>
import { ref } from 'vue'
import { api } from '../api'
import { useAuth } from '../store'
import { toast, toastError } from '../util'

const auth = useAuth()
const documento = ref(auth.usuario?.documento || '')
const cargo = ref(auth.usuario?.cargo || '')
const version = ref(Date.now())
const subiendo = ref(false)
const ROL = { MANAGER: 'Manager', ADMIN: 'Administrador / Analista', LIDER: 'Líder de lote', COORDINADOR: 'Coordinador', INSTRUCTOR: 'Instructor' }

async function guardarDocumento() {
  try { auth.usuario = await api.put('/auth/perfil', { documento: documento.value, cargo: auth.esCoordinador ? cargo.value : null }); toast('Datos guardados') } catch (e) { toastError(e) }
}
async function subirFirma(ev) {
  const archivo = ev.target.files[0]
  if (!archivo) return
  const fd = new FormData()
  fd.append('archivo', archivo)
  subiendo.value = true
  try {
    auth.usuario = await api.post('/auth/firma', fd)
    version.value = Date.now()
    toast('Firma cargada: se estampará en los formatos GIL-F-014 que apruebe')
  } catch (e) { toastError(e) } finally { subiendo.value = false; ev.target.value = '' }
}
</script>

<template>
  <div>
    <div class="page-head"><div><h1>Mi perfil</h1><div class="sub">{{ auth.usuario.nombre }} · {{ auth.usuario.email }}</div></div></div>
    <div class="cols-2">
      <div class="card">
        <h2>Datos</h2>
        <p><b>Rol:</b> {{ ROL[auth.usuario.rol] }}<span v-if="auth.usuario.centro"> · {{ auth.usuario.centro.nombre }}</span></p>
        <p v-if="auth.usuario.coordinacion"><b>Coordinación:</b> {{ auth.usuario.coordinacion.nombre }}</p>
        <form class="form-grid" style="align-items:end" @submit.prevent="guardarDocumento">
          <label class="f"><span>N° de identificación (formato GIL-F-014)</span><input v-model="documento" inputmode="numeric" :required="auth.esInstructor" /></label>
          <label v-if="auth.esCoordinador" class="f"><span>Cargo (formato GIL-F-014)</span><input v-model="cargo" maxlength="120" placeholder="Ej. Coordinador Académico" /></label>
          <div><button class="btn">Guardar</button></div>
        </form>
        <p class="small muted"><router-link to="/cambiar-password">Cambiar contraseña</router-link></p>
      </div>
      <div v-if="auth.esCoordinador" class="card">
        <h2>Mi firma digital</h2>
        <p class="sub">Se estampa en el campo FIRMA del formato GIL-F-014 de cada solicitud que apruebe. Las solicitudes ya aprobadas conservan la firma con la que se aprobaron.</p>
        <div class="firma">
          <img v-if="auth.usuario.tiene_firma" :src="api.archivoUrl(`/auth/firma?v=${version}`)" alt="Mi firma" />
          <span v-else class="muted">Aún no ha cargado su firma: no podrá aprobar solicitudes hasta hacerlo.</span>
        </div>
        <label class="btn" :class="{ ghost: auth.usuario.tiene_firma }" style="margin-top:12px">
          {{ subiendo ? 'Cargando…' : auth.usuario.tiene_firma ? 'Reemplazar firma' : 'Cargar firma' }}
          <input type="file" accept="image/png,image/jpeg" hidden :disabled="subiendo" @change="subirFirma" />
        </label>
        <p class="small muted">Imagen PNG o JPG de su firma sobre fondo blanco o transparente (máx. 10 MB). Recórtela para que la firma ocupe casi toda la imagen.</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.firma { border: 1px dashed var(--borde); border-radius: 8px; min-height: 110px; display: grid; place-items: center; padding: 12px; background: #fff; }
.firma img { max-height: 110px; max-width: 100%; }
</style>
