<script setup lang="ts">
import { computed } from "vue";
import { useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { formatDateTime } from "@/utils/date";

const { t } = useI18n();
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const screens = computed(() => (devices.data.value ?? []).filter((item) => item.deviceKind === "screen"));
const lastSeenAt = computed(() => {
  const values = screens.value.map((item) => item.lastSeenAt).filter((value): value is string => Boolean(value)).sort();
  return values[values.length - 1] ?? null;
});
</script>

<template>
  <section class="device-section-heading">
    <div><h2>{{ t("screenDevice.title") }}</h2><p>{{ t("screenDevice.subtitle") }}</p></div>
  </section>
  <section class="device-domain-grid">
    <DevicePairPanel :allowed-kinds="['screen']" :title="t('screenDevice.pairTitle')" />
    <BaseCard :title="t('screenDevice.parameters')">
      <div class="parameter-grid">
        <div><span>{{ t("screenDevice.registered") }}</span><strong>{{ screens.length }}</strong></div>
        <div><span>{{ t("screenDevice.lastConnection") }}</span><strong>{{ lastSeenAt ? formatDateTime(lastSeenAt) : t("pair.notReported") }}</strong></div>
        <div><span>{{ t("screenDevice.path") }}</span><strong>/screen</strong></div>
        <div><span>{{ t("screenDevice.transport") }}</span><strong>WebSocket</strong></div>
        <div><span>{{ t("screenDevice.channel") }}</span><strong>screen</strong></div>
        <div><span>{{ t("screenDevice.credential") }}</span><strong>{{ t("screenDevice.deviceToken") }}</strong></div>
      </div>
    </BaseCard>
  </section>
</template>
