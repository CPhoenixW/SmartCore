<script setup lang="ts">
import type { EventStatus, EventType, Priority } from "@/types/event";
defineProps<{ status?: EventStatus; type?: EventType; priority?: Priority; text?: string }>();
</script>
<template><span class="tag" :class="[status && `tag--${status}`, type && `tag--${type}`, priority && `tag--prio-${priority}`]">{{ text }}</span></template>
