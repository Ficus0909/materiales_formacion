<script setup>
defineProps({ titulo: String, ancho: { type: String, default: '640px' } })
const emit = defineEmits(['cerrar'])
</script>

<template>
  <div class="ov" @mousedown.self="emit('cerrar')" @keydown.esc="emit('cerrar')">
    <div class="md" :style="{ maxWidth: ancho }" role="dialog" aria-modal="true" :aria-label="titulo">
      <header>
        <h2>{{ titulo }}</h2>
        <button class="x" aria-label="Cerrar" @click="emit('cerrar')">×</button>
      </header>
      <div class="body"><slot /></div>
      <footer v-if="$slots.pie"><slot name="pie" /></footer>
    </div>
  </div>
</template>

<style scoped>
.ov { position: fixed; inset: 0; background: rgba(15, 23, 42, .45); display: grid; place-items: center; z-index: 50; padding: 16px; }
.md { background: #fff; border-radius: 10px; width: 100%; max-height: calc(100vh - 32px); display: flex; flex-direction: column; box-shadow: 0 20px 50px rgba(0,0,0,.25); }
header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--borde); border-top: 4px solid var(--verde); border-radius: 10px 10px 0 0; }
header h2 { margin: 0; }
.x { background: none; border: 0; font-size: 24px; cursor: pointer; color: var(--texto2); line-height: 1; }
.body { padding: 18px; overflow: auto; }
footer { padding: 12px 18px; border-top: 1px solid var(--borde); display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
</style>
