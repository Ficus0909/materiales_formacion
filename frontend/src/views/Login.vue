<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../store'

const auth = useAuth()
const router = useRouter()
const route = useRoute()
const email = ref('')
const password = ref('')
const ver = ref(false)
const error = ref('')
const cargando = ref(false)

async function entrar() {
  error.value = ''
  cargando.value = true
  try {
    await auth.login(email.value, password.value)
    router.push(route.query.r || auth.inicio)
  } catch (e) {
    error.value = e.message
  } finally {
    cargando.value = false
  }
}
</script>

<template>
  <div class="wrap">
    <section class="brand">
      <img src="/logo-sena-blanco.png" alt="SENA" class="logo" />
      <h1>Materiales de Formación</h1>
      <p>Estudio de mercados y solicitudes por lote</p>
      <p class="small" style="opacity:.85">SENA · Centros de formación</p>
    </section>
    <section class="form">
      <form class="card" @submit.prevent="entrar">
        <h2>Iniciar sesión</h2>
        <p class="sub" style="margin-top:-6px">Use su cuenta institucional asignada por el administrador.</p>
        <label class="f req"><span>Correo institucional</span>
          <input v-model="email" type="email" autocomplete="username" placeholder="usuario@sena.edu.co" required />
        </label>
        <label class="f req" style="margin-top:12px"><span>Contraseña</span>
          <div class="row" style="flex-wrap:nowrap;gap:6px">
            <input v-model="password" :type="ver ? 'text' : 'password'" autocomplete="current-password" required class="grow" />
            <button type="button" class="btn ghost sm" @click="ver = !ver">{{ ver ? 'Ocultar' : 'Mostrar' }}</button>
          </div>
        </label>
        <div v-if="error" class="alert error" style="margin-top:12px">{{ error }}</div>
        <button class="btn" style="width:100%;justify-content:center;margin-top:16px;padding:11px" :disabled="cargando">
          {{ cargando ? 'Ingresando…' : 'Iniciar sesión' }}
        </button>
        <p class="small muted" style="margin-top:14px">¿Olvidó su contraseña? Solicite al administrador del sistema una contraseña temporal.
          La cuenta se bloquea 15 minutos tras 3 intentos fallidos.</p>
      </form>
    </section>
  </div>
</template>

<style scoped>
.wrap { min-height: 100vh; display: grid; grid-template-columns: 1fr 1fr; }
.brand { background: linear-gradient(160deg, var(--verde), var(--verde-osc) 60%, var(--azul)); color: #fff; display: flex; flex-direction: column; justify-content: center; padding: 48px; }
.brand h1 { font-size: 34px; margin: 18px 0 6px; }
.brand p { font-size: 16px; margin: 4px 0; }
.logo { width: 110px; height: auto; display: block; }
.form { display: grid; place-items: center; padding: 24px 16px; }
.form .card { width: 100%; max-width: 400px; padding: 28px; }
@media (max-width: 800px) {
  .wrap { grid-template-columns: 1fr; }
  .brand { padding: 28px 20px; }
  .brand h1 { font-size: 24px; }
  .logo { width: 72px; }
}
</style>
