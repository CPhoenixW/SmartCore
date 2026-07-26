<script setup lang="ts">
import { computed } from "vue";
import { usageChartPosition, usageSmoothPath } from "@/utils/usageChart";

export interface CurveChartSeries {
  key: string;
  name: string;
  color: string;
  values: number[];
  displayValues?: string[];
}

const props = defineProps<{
  labels: string[];
  details?: string[];
  series: CurveChartSeries[];
  label: string;
}>();

const maximum = computed(() => Math.max(1, ...props.series.flatMap((item) => item.values)));
const paths = computed(() => props.series.map((item) => ({
  ...item,
  path: usageSmoothPath(item.values, maximum.value),
})));

function pointPosition(value: number, index: number) {
  return usageChartPosition(index, props.labels.length, value, maximum.value);
}

function markerStyle(value: number, index: number, color: string) {
  const point = pointPosition(value, index);
  return { left: `${point.x}%`, top: `${point.y}%`, background: color };
}

function hoverStyle(index: number) {
  return { left: `${pointPosition(0, index).x}%` };
}

function tooltip(index: number) {
  const heading = props.details?.[index] ?? props.labels[index] ?? "";
  const values = props.series.map((item) => `${item.name}: ${item.displayValues?.[index] ?? item.values[index] ?? 0}`);
  return [heading, ...values].filter(Boolean).join(" · ");
}
</script>

<template>
  <div class="curve-chart-scroll" tabindex="0">
    <div class="curve-chart" :class="{ 'curve-chart--multi': series.length > 1 }">
      <div v-if="series.length > 1" class="curve-chart__legend">
        <span v-for="item in series" :key="item.key"><i :style="{ background: item.color }" />{{ item.name }}</span>
      </div>
      <div class="curve-chart__canvas">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" :aria-label="label">
          <line v-for="line in [8, 50, 92]" :key="line" class="curve-chart__grid" x1="3" :y1="line" x2="97" :y2="line" />
          <path v-for="item in paths" :key="item.key" class="curve-chart__path" :d="item.path" :style="{ stroke: item.color }" />
        </svg>
        <template v-for="item in series" :key="`markers-${item.key}`">
          <i v-for="(value, index) in item.values" :key="`${item.key}-${index}`" class="curve-chart__marker" :style="markerStyle(value, index, item.color)" />
        </template>
        <button v-for="(_, index) in labels" :key="`hover-${index}`" class="curve-chart__hover" type="button" :style="hoverStyle(index)" :aria-label="tooltip(index)" :data-tooltip="tooltip(index)" />
      </div>
      <div class="curve-chart__labels" :style="{ gridTemplateColumns: `repeat(${Math.max(1, labels.length)}, minmax(0, 1fr))` }">
        <span v-for="(label, index) in labels" :key="`${label}-${index}`">{{ label }}</span>
      </div>
    </div>
  </div>
</template>
