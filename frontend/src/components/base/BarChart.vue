<script setup lang="ts">
import { computed } from "vue";

export interface BarChartSeries {
  key: string;
  name: string;
  color: string;
  values: number[];
  displayValues?: string[];
}

const props = defineProps<{
  labels: string[];
  details?: string[];
  series: BarChartSeries[];
  label: string;
}>();

const maximum = computed(() => Math.max(1, ...props.series.flatMap((item) => item.values)));
const chartStyle = computed(() => ({ minWidth: `${Math.max(620, props.labels.length * 54)}px` }));

function barStyle(value: number, color: string) {
  const height = value <= 0 ? 1 : Math.max(3, value / maximum.value * 100);
  return { height: `${height}%`, background: color };
}

function tooltip(index: number, item: BarChartSeries) {
  const heading = props.details?.[index] ?? props.labels[index] ?? "";
  const value = item.displayValues?.[index] ?? item.values[index] ?? 0;
  return [heading, `${item.name}: ${value}`].filter(Boolean).join(" · ");
}
</script>

<template>
  <div class="bar-chart-scroll" tabindex="0">
    <div class="bar-chart" :style="chartStyle">
      <div v-if="series.length > 1" class="bar-chart__legend">
        <span v-for="item in series" :key="item.key"><i :style="{ background: item.color }" />{{ item.name }}</span>
      </div>
      <div class="bar-chart__canvas" :style="{ gridTemplateColumns: `repeat(${Math.max(1, labels.length)}, minmax(36px, 1fr))` }" role="group" :aria-label="label">
        <div v-for="(_, index) in labels" :key="`group-${index}`" class="bar-chart__group">
          <button
            v-for="item in series"
            :key="item.key"
            class="bar-chart__bar"
            type="button"
            :style="barStyle(item.values[index] ?? 0, item.color)"
            :aria-label="tooltip(index, item)"
            :data-tooltip="tooltip(index, item)"
          />
        </div>
      </div>
      <div class="bar-chart__labels" :style="{ gridTemplateColumns: `repeat(${Math.max(1, labels.length)}, minmax(36px, 1fr))` }">
        <span v-for="(itemLabel, index) in labels" :key="`${itemLabel}-${index}`">{{ itemLabel }}</span>
      </div>
    </div>
  </div>
</template>
