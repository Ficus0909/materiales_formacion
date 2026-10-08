<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAuth } from '../store'
import { toast, toastError } from '../util'

const auth = useAuth()
const router = useRouter()
const f = ref({ actual: '', nueva: '', confirmar: '' })
const reglas = computed(() => [
  ['Mínimo 8 caracteres', f.value.nueva.length >= 8],
  ['Una mayúscula', /[A-Z]/.test(f.value.nueva)],
  ['Un número', /\d/.test(f.value.nueva)],
  ['Un carácter especial', /[^A-Za-z0-9]/.test(f.value.nueva)],
  ['Coincide la confirmación', f.value.nueva && f.value.nueva === f.value.confirmar],
])
const fuerza = computed(() => reglas.value.filter((r) => r[1]).length)

async function guardar() {
  try {
    await api.post('/auth/cambiar-password', { actual: f.value.actual, nueva: f.value.nueva })
    auth.usuario.debe_cambiar_password = false
    toast('Contraseña actualizada')
    router.push(auth.inicio)
  } catch (e) { toastError(e) }
}
</script>

<template>
  <div style="max-width:460px">
    <h1>Cambiar contraseña</h1>
    <div v-if="auth.usuario?.debe_cambiar_password" class="alert warn">Debe cambiar la contraseña temporal antes de continuar.</div>
    <form class="card grid" @submit.prevent="guardar">
      <label class="f req"><span>Contraseña actual</span><input v-model="f.actual" type="password" required autocomplete="current-password" /></label>
      <label class="f req"><span>Nueva contraseña</span><input v-model="f.nueva" type="password" required autocomplete="new-password" /></label>
      <label class="f req"><span>Confirmar nueva contraseña</span><input v-model="f.confirmar" type="password" required autocomplete="new-password" /></label>
      <div class="progress"><div :style="{ width: `${fuerza * 20}%`, background: fuerza < 3 ? 'var(--rojo)' : fuerza < 5 ? 'var(--naranja)' : 'var(--verde)' }" /></div>
      <ul class="small" style="margin:0;padding-left:18px">
        <li v-for="[t, ok] in reglas" :key="t" :style="{ color: ok ? 'var(--verde-osc)' : 'var(--texto2)' }">{{ ok ? '✓' : '○' }} {{ t }}</li>
      </ul>
      <button class="btn" :disabled="fuerza < 5">Guardar</button>
    </form>
  </div>
</template>
