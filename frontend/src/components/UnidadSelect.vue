<script setup>
import { computed } from 'vue'
import { UNIDADES_SECOP } from '../unidades'
const modelo = defineModel({ type: String, default: '' })
// Unidades ya guardadas que no están en el listado SECOP se conservan como opción.
const fuera = computed(() => modelo.value && !UNIDADES_SECOP.some(([c]) => c === modelo.value))
</script>

<template>
  <select v-model="modelo">
    <option value="" disabled>Seleccione la unidad…</option>
    <option v-if="fuera" :value="modelo">{{ modelo }} (no está en SECOP II)</option>
    <option v-for="[c, n] in UNIDADES_SECOP" :key="c" :value="c">{{ c }} — {{ n }}</option>
  </select>
</template>
