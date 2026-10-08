<script setup>
import { toasts } from './util'
</script>

<template>
  <router-view />
  <div class="toasts" role="status" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.tipo">{{ t.msg }}</div>
  </div>
</template>
