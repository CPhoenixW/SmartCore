<script setup lang="ts">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import DevicePairPanel from "@/components/device/DevicePairPanel.vue";
import FeishuBotManager from "@/components/device/FeishuBotManager.vue";
import { useUserStore } from "@/stores/user";

const { t } = useI18n();
const userStore = useUserStore();
const isAdmin = computed(() => userStore.user.role === "admin");
</script>

<template>
  <section class="device-section-heading">
    <div><h2>{{ t("feishuDevice.title") }}</h2><p>{{ t("feishuDevice.subtitle") }}</p></div>
  </section>
  <section class="device-domain-grid">
    <DevicePairPanel :allowed-kinds="['feishuBot']" :title="t('feishuDevice.pairTitle')" />
    <FeishuBotManager v-if="isAdmin" />
    <BaseCard v-else :title="t('feishuDevice.parameters')">
      <div class="parameter-grid">
        <div><span>{{ t("feishuDevice.scope") }}</span><strong>{{ t("feishuDevice.currentUser") }}</strong></div>
        <div><span>{{ t("feishuDevice.management") }}</span><strong>{{ t("feishuDevice.adminManaged") }}</strong></div>
        <div><span>{{ t("feishuDevice.delivery") }}</span><strong>Feishu</strong></div>
      </div>
    </BaseCard>
  </section>
</template>
