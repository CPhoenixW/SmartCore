<script setup lang="ts">
import { useI18n } from "vue-i18n";

withDefaults(defineProps<{
  content?: string;
  handled?: boolean;
  createdAt?: string | null;
}>(), {
  content: "",
  handled: false,
  createdAt: "",
});
const { t } = useI18n();
</script>

<template>
  <article class="idea-preview-card" :class="{ 'idea-preview-card--handled': handled }">
    <div class="idea-preview-card__pin">◆</div>
    <p>{{ content.trim() || t("ideas.previewPlaceholder") }}</p>
    <footer>
      <span>{{ handled ? t("ideas.handled") : t("ideas.open") }}</span>
      <time v-if="createdAt">{{ createdAt }}</time>
    </footer>
  </article>
</template>
