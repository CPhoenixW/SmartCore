<script setup lang="ts">defineProps<{ text?: string }>();</script>
<template><div class="empty-state"><span>◇</span><p>{{ text ?? $t("common.empty") }}</p></div></template>
