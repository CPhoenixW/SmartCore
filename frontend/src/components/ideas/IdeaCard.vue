<script setup lang="ts">
import { computed } from "vue";
import { Images, Paperclip } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import type { Idea } from "@/types/idea";
import { formatDateTime } from "@/utils/date";

const props = defineProps<{ idea: Idea; selected?: boolean }>();
defineEmits<{ select: [idea: Idea]; edit: [idea: Idea] }>();
const { t, locale } = useI18n();
const imageCount = computed(() => props.idea.attachments.filter((item) => item.mimeType.startsWith("image/")).length);
const attachmentLabel = computed(() => imageCount.value
  ? `${imageCount.value} ${t("ideas.images")}`
  : `${props.idea.attachments.length} ${t("ideas.attachments")}`);
const displayTime = computed(() => formatDateTime(props.idea.createdAt, locale.value === "en-US" ? "en-US" : "zh-CN"));
</script>

<template>
  <button class="idea-card" :class="{ selected }" type="button" @click="$emit('select', idea)" @dblclick="$emit('edit', idea)">
    <strong>{{ idea.title }}</strong>
    <p>{{ idea.description || t("ideas.noDescription") }}</p>
    <footer>
      <span v-if="idea.attachments.length" class="idea-card__attachments">
        <Images v-if="imageCount" :size="13" aria-hidden="true" />
        <Paperclip v-else :size="13" aria-hidden="true" />
        {{ attachmentLabel }}
      </span>
      <time :datetime="idea.createdAt">{{ displayTime }}</time>
    </footer>
  </button>
</template>

<style scoped>
.idea-card__attachments { display: inline-flex; align-items: center; gap: 5px; }
</style>
