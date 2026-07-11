<script setup lang="ts">import { useToast } from "@/composables/useToast"; const { messages } = useToast();</script>
<template><div class="toast-host" aria-live="polite"><div v-for="item in messages" :key="item.id" class="toast" :class="`toast--${item.kind}`">{{ item.text }}</div></div></template>
