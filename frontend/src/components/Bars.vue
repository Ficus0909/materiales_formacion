<script setup>
import { computed } from 'vue'
// Barras horizontales simples: [{ label, value, color, display }]
const p = defineProps({ datos: Array, max: Number })
const tope = computed(() => p.max || Math.max(1, ...p.datos.map((d) => d.value)))
</script>

<template>
  <div class="bars">
    <div v-for="d in datos" :key="d.label" class="bar-row" :title="`${d.label}: ${d.display ?? d.value}`">
      <span class="nowrap" style="overflow:hidden;text-overflow:ellipsis">{{ d.label }}</span>
      <div class="track"><div :style="{ width: `${(100 * d.value) / tope}%`, background: d.color || 'var(--verde)' }" /></div>
      <span class="right mono">{{ d.display ?? d.value }}</span>
    </div>
    <div v-if="!datos.length" class="empty">Sin datos</div>
  </div>
</template>
