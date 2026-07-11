<script setup lang="ts">
defineProps<{ title?: string; subtitle?: string }>();
</script>
<template>
  <section class="card">
    <header v-if="title || $slots.actions" class="card-header">
      <div><h2 v-if="title">{{ title }}</h2><p v-if="subtitle">{{ subtitle }}</p></div>
      <div class="card-actions"><slot name="actions" /></div>
    </header>
    <div class="card-body"><slot /></div>
    <footer v-if="$slots.footer" class="card-footer"><slot name="footer" /></footer>
  </section>
</template>
