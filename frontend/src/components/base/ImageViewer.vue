<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";

defineProps<{ src: string; alt: string; fileName: string }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const viewport = ref<HTMLElement | null>(null);
const image = ref<HTMLImageElement | null>(null);
const scale = ref(1);
const offset = ref({ x: 0, y: 0 });
const naturalSize = ref({ width: 1, height: 1 });
const pointers = new Map<number, { x: number; y: number }>();
let previousPinchDistance = 0;
let previousPinchCenter: { x: number; y: number } | null = null;
const zoomLabel = computed(() => `${Math.round(scale.value * 100)}%`);
const imageStyle = computed(() => ({
  width: `${naturalSize.value.width}px`,
  height: `${naturalSize.value.height}px`,
  transform: `scale(${scale.value})`,
}));
const stageStyle = computed(() => ({ transform: `translate(-50%, -50%) translate(${offset.value.x}px, ${offset.value.y}px)` }));

function clamp(value: number) { return Math.min(5, Math.max(0.1, value)); }

function setScale(value: number, clientX?: number, clientY?: number) {
  const next = clamp(value);
  const old = scale.value;
  if (next === old) return;
  const bounds = viewport.value?.getBoundingClientRect();
  if (bounds && clientX != null && clientY != null) {
    const point = { x: clientX - bounds.left - bounds.width / 2, y: clientY - bounds.top - bounds.height / 2 };
    const ratio = next / old;
    offset.value = {
      x: point.x - (point.x - offset.value.x) * ratio,
      y: point.y - (point.y - offset.value.y) * ratio,
    };
  }
  scale.value = next;
}

function fit() {
  const bounds = viewport.value?.getBoundingClientRect();
  if (!bounds) return;
  offset.value = { x: 0, y: 0 };
  scale.value = clamp(Math.min((bounds.width - 32) / naturalSize.value.width, (bounds.height - 32) / naturalSize.value.height, 1));
}

function originalSize() {
  offset.value = { x: 0, y: 0 };
  scale.value = 1;
}

function loaded() {
  if (!image.value) return;
  naturalSize.value = { width: image.value.naturalWidth || 1, height: image.value.naturalHeight || 1 };
  fit();
}

function wheel(event: WheelEvent) {
  event.preventDefault();
  setScale(scale.value * (event.deltaY < 0 ? 1.12 : 0.89), event.clientX, event.clientY);
}

function pointerDown(event: PointerEvent) {
  viewport.value?.setPointerCapture(event.pointerId);
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
}

function pointerMove(event: PointerEvent) {
  const previous = pointers.get(event.pointerId);
  if (!previous) return;
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  const values = [...pointers.values()];
  if (values.length === 1) {
    offset.value = { x: offset.value.x + event.clientX - previous.x, y: offset.value.y + event.clientY - previous.y };
    return;
  }
  const first = values[0]!;
  const second = values[1]!;
  const distance = Math.hypot(first.x - second.x, first.y - second.y);
  const center = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
  if (previousPinchDistance > 0) setScale(scale.value * distance / previousPinchDistance, center.x, center.y);
  if (previousPinchCenter) {
    offset.value = {
      x: offset.value.x + center.x - previousPinchCenter.x,
      y: offset.value.y + center.y - previousPinchCenter.y,
    };
  }
  previousPinchDistance = distance;
  previousPinchCenter = center;
}

function pointerEnd(event: PointerEvent) {
  pointers.delete(event.pointerId);
  previousPinchDistance = 0;
  previousPinchCenter = null;
}

function keydown(event: KeyboardEvent) {
  if (event.key === "Escape") emit("close");
  else if (event.key === "+" || event.key === "=") setScale(scale.value * 1.2);
  else if (event.key === "-") setScale(scale.value / 1.2);
  else if (event.key === "0") fit();
}

onMounted(() => window.addEventListener("keydown", keydown));
onBeforeUnmount(() => window.removeEventListener("keydown", keydown));
</script>

<template>
  <div class="image-viewer" role="dialog" aria-modal="true" :aria-label="t('ideas.imagePreview')" @click.self="emit('close')">
    <section class="image-viewer__panel">
      <header class="image-viewer__toolbar">
        <strong :title="fileName">{{ fileName }}</strong>
        <div class="image-viewer__tools">
          <button class="icon-button" type="button" :title="t('ideas.zoomOut')" :aria-label="t('ideas.zoomOut')" @click="setScale(scale / 1.2)">−</button>
          <output>{{ zoomLabel }}</output>
          <button class="icon-button" type="button" :title="t('ideas.zoomIn')" :aria-label="t('ideas.zoomIn')" @click="setScale(scale * 1.2)">+</button>
          <button class="button" type="button" @click="fit">{{ t("ideas.fitImage") }}</button>
          <button class="button" type="button" @click="originalSize">1:1</button>
          <a :href="src" class="button button--primary" download>{{ t("ideas.download") }}</a>
          <button class="icon-button" type="button" :title="t('ideas.closePreview')" :aria-label="t('ideas.closePreview')" @click="emit('close')">×</button>
        </div>
      </header>
      <div
        ref="viewport"
        class="image-viewer__viewport"
        @wheel="wheel"
        @dblclick="scale === 1 ? fit() : originalSize()"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="pointerEnd"
        @pointercancel="pointerEnd"
      >
        <div class="image-viewer__stage" :style="stageStyle">
          <img ref="image" :src="src" :alt="alt" draggable="false" :style="imageStyle" @load="loaded" />
        </div>
      </div>
    </section>
  </div>
</template>
