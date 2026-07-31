<script setup lang="ts">
import MarkdownContent from "@/components/base/MarkdownContent.vue";

withDefaults(defineProps<{
  title: string;
  description?: string | null;
  emptyDescription?: string;
  time?: string | null;
  datetime?: string | null;
}>(), {
  description: "",
  emptyDescription: "",
  time: "",
  datetime: "",
});
</script>

<template>
  <article class="detail-preview">
    <header class="detail-preview__header idea-detail-header">
      <div>
        <h2>{{ title }}</h2>
        <time v-if="time" class="detail-preview__time idea-time" :datetime="datetime || undefined">{{ time }}</time>
      </div>
      <div v-if="$slots.badge" class="detail-preview__badges"><slot name="badge" /></div>
    </header>
    <section class="detail-preview__copy idea-detail-copy">
      <MarkdownContent v-if="description?.trim()" :content="description" />
      <p v-else class="detail-preview__empty">{{ emptyDescription }}</p>
    </section>
    <slot />
  </article>
</template>

<style scoped>
.detail-preview { min-width: 0; }
.detail-preview__header > div:first-child { min-width: 0; }
.detail-preview__badges { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; flex: 0 0 auto; gap: 7px; }
.detail-preview__copy { min-height: 72px; }
.detail-preview__empty { margin: 0; color: var(--color-text-muted); }
@media (max-width: 640px) {
  .detail-preview__badges { justify-content: flex-start; }
}
</style>
