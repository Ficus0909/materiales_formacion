<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'

const opciones = ref({ centros: [], dominios: [] })
const f = ref({ nombre: '', email: '', documento: '', password: '', confirmar: '', centro_id: '', coordinacion_id: '' })
const ver = ref(false)
const error = ref('')
const enviando = ref(false)
const listo = ref(false)

onMounted(async () => {
  try { opciones.value = await api.get('/auth/registro/opciones') } catch (e) { error.value = e.message }
  if (opciones.value.centros.length === 1) f.value.centro_id = opciones.value.centros[0].id
})
const coordinaciones = computed(() => opciones.value.centros.find((c) => c.id === f.value.centro_id)?.coordinaciones || [])
watch(() => f.value.centro_id, () => { f.value.coordinacion_id = '' })
const dominios = computed(() => opciones.value.dominios.map((d) => `@${d}`).join(', '))

async function registrar() {
  error.value = ''
  if (f.value.password !== f.value.confirmar) { error.value = 'Las contraseñas no coinciden'; return }
  enviando.value = true
  try {
    const { confirmar, ...body } = f.value
    await api.post('/auth/registro', body)
    listo.value = true
  } catch (e) {
    error.value = e.errores?.length ? `${e.message}: ${e.errores.join(' · ')}` : e.message
  } finally { enviando.value = false }
}
</script>

<template>
  <div class="wrap">
    <section class="brand">
      <img src="/logo-sena-blanco.png" alt="SENA" class="logo" />
      <h1>Registro de instructores</h1>
      <p>Solicite los materiales de formación de su área con el formato GIL-F-014.</p>
      <p class="small" style="opacity:.85">Su cuenta queda activa cuando el coordinador de su coordinación la aprueba.</p>
    </section>
    <section class="form">
      <div v-if="listo" class="card">
        <h2>Registro recibido</h2>
        <div class="alert ok">Su registro quedó <b>pendiente de aprobación</b>. Le enviaremos un correo a <b>{{ f.email }}</b> cuando el coordinador active su cuenta.</div>
        <router-link to="/login" class="btn" style="margin-top:14px">Volver al inicio de sesión</router-link>
      </div>
      <form v-else class="card" @submit.prevent="registrar">
        <h2>Crear cuenta de instructor</h2>
        <div class="form-grid">
          <label class="f req full"><span>Nombre completo</span><input v-model="f.nombre" required autocomplete="name" /></label>
          <label class="f req full"><span>Correo institucional</span>
            <input v-model="f.email" type="email" required autocomplete="username" :placeholder="opciones.dominios[0] ? `usuario@${opciones.dominios[0]}` : 'usuario@sena.edu.co'" />
            <small v-if="dominios" class="muted">Sólo se aceptan correos {{ dominios }}</small></label>
          <label class="f req full"><span>N° de identificación</span><input v-model="f.documento" inputmode="numeric" required placeholder="Sin puntos" /></label>
          <label class="f req full"><span>Centro de formación</span>
            <select v-model="f.centro_id" required><option value="" disabled>Seleccione…</option><option v-for="c in opciones.centros" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></label>
          <label class="f req full"><span>Coordinación a la que pertenece</span>
            <select v-model="f.coordinacion_id" required :disabled="!f.centro_id"><option value="" disabled>Seleccione…</option><option v-for="c in coordinaciones" :key="c.id" :value="c.id">{{ c.nombre }}</option></select></label>
          <label class="f req"><span>Contraseña</span><input v-model="f.password" :type="ver ? 'text' : 'password'" required autocomplete="new-password" /></label>
          <label class="f req"><span>Confirmar contraseña</span><input v-model="f.confirmar" :type="ver ? 'text' : 'password'" required autocomplete="new-password" /></label>
        </div>
        <label class="row small" style="gap:6px;margin-top:6px"><input v-model="ver" type="checkbox" /> Mostrar contraseñas</label>
        <p class="small muted">Mínimo 8 caracteres, con una mayúscula, un número y un carácter especial.</p>
        <div v-if="error" class="alert error">{{ error }}</div>
        <button class="btn" style="width:100%;justify-content:center;margin-top:8px;padding:11px" :disabled="enviando">{{ enviando ? 'Registrando…' : 'Registrarme' }}</button>
        <div class="registro">¿Ya tiene cuenta? <router-link to="/login">Inicie sesión</router-link></div>
      </form>
    </section>
  </div>
</template>

<style scoped>
.wrap { min-height: 100vh; display: grid; grid-template-columns: 1fr 1fr; }
.brand { background: linear-gradient(160deg, var(--verde), var(--verde-osc) 60%, var(--azul)); color: #fff; display: flex; flex-direction: column; justify-content: center; padding: 48px; }
.brand h1 { font-size: 32px; margin: 18px 0 6px; }
.brand p { font-size: 16px; margin: 4px 0; }
.logo { width: 110px; height: auto; display: block; }
.form { display: grid; place-items: center; padding: 24px 16px; }
.form .card { width: 100%; max-width: 480px; padding: 28px; }
.registro { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--borde); font-size: 13px; text-align: center; }
@media (max-width: 800px) {
  .wrap { grid-template-columns: 1fr; }
  .brand { padding: 28px 20px; }
  .brand h1 { font-size: 24px; }
  .logo { width: 72px; }
}
</style>
