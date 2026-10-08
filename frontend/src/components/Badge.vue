<script setup>
import { computed } from 'vue'
import { ESTADOS } from '../util'
const p = defineProps({ estado: String, color: String, texto: String })
const info = computed(() => ESTADOS[p.estado] || { label: p.estado, color: '#71277A' })
</script>

<template>
  <span class="badge" :style="{ background: color || info.color }">{{ texto || info.label }}</span>
</template>
