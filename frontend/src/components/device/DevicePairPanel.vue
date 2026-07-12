<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import BaseCard from "@/components/base/BaseCard.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { useToast } from "@/composables/useToast";

const toast = useToast();
const { t } = useI18n();
const queryClient = useQueryClient();
const deviceName = ref("");
const deviceKind = ref("screen");
const currentPair = ref<Awaited<ReturnType<typeof deviceRegistryApi.startPair>> | null>(null);
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const start = useMutation({ mutationFn: () => deviceRegistryApi.startPair(deviceName.value, deviceKind.value), onSuccess: (pair) => { currentPair.value = pair; toast.success(t("pair.created")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const confirm = useMutation({ mutationFn: () => currentPair.value ? deviceRegistryApi.confirmPair(currentPair.value.pairId) : Promise.reject(new Error(t("pair.required"))), onSuccess: async (pair) => { currentPair.value = pair; await queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }); toast.success(t("pair.confirmed")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
async function refreshPair() { if (currentPair.value) currentPair.value = await deviceRegistryApi.readPair(currentPair.value.pairId); }
</script>

<template>
  <BaseCard :title="t('pair.title')">
    <div class="device-pair-list">
      <div v-for="item in devices.data.value ?? []" :key="item.deviceId" class="device-pair-row"><div><strong>{{ item.deviceName }}</strong><small>{{ t(`pair.kind.${item.deviceKind}`) }} · {{ item.stat }}</small></div><span>{{ item.lastSeenAt ? t('pair.updated') : t('pair.notReported') }}</span></div>
      <p v-if="!(devices.data.value ?? []).length" class="muted">{{ t('pair.empty') }}</p>
    </div>
    <form class="device-pair-form" @submit.prevent="start.mutate()"><input v-model.trim="deviceName" required :placeholder="t('pair.namePlaceholder')" /><select v-model="deviceKind"><option value="screen">{{ t('pair.kind.screen') }}</option><option value="pi">{{ t('pair.kind.pi') }}</option><option value="browser">{{ t('pair.kind.browser') }}</option><option value="feishuBot">{{ t('pair.kind.feishuBot') }}</option></select><button class="button button--primary" :disabled="start.isPending.value">{{ t('pair.start') }}</button></form>
    <div v-if="currentPair" class="pair-code"><div><strong>{{ t('pair.info') }}</strong><small>{{ t('pair.id') }}</small><code>{{ currentPair.pairId }}</code><small>{{ t('pair.code') }}</small><code>{{ currentPair.claimCode }}</code><small>{{ t('pair.hint') }}</small></div><span class="pair-stat">{{ currentPair.stat }}</span><button class="button button--ghost" type="button" @click="refreshPair">{{ t('common.refresh') }}</button><button v-if="currentPair.stat === 'claimed'" class="button button--primary" type="button" :disabled="confirm.isPending.value" @click="confirm.mutate()">{{ t('pair.confirm') }}</button></div>
  </BaseCard>
</template>

<style scoped>
.device-pair-list{display:grid;gap:8px}.device-pair-row{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--border-subtle)}.device-pair-row small,.pair-code small{display:block;color:var(--text-muted);margin-top:3px}.device-pair-row span{color:var(--text-muted);font-size:13px}.device-pair-form{display:grid;grid-template-columns:minmax(0,1fr) 160px auto;gap:12px;margin-top:16px}.device-pair-form input,.device-pair-form select{width:100%;min-height:48px;padding:0 15px;border:1px solid var(--border-color);border-radius:18px;background:#fff;font:inherit}.device-pair-form .button{border-radius:18px}.pair-code{display:flex;align-items:center;gap:10px;margin-top:14px;padding:12px;border:1px solid var(--border-subtle);border-radius:14px;background:var(--surface-subtle)}.pair-code>div{margin-right:auto}.pair-code code{display:block;font-size:14px;margin:5px 0;word-break:break-all}.pair-stat{font-size:12px;color:var(--text-muted)}@media(max-width:700px){.device-pair-form{grid-template-columns:1fr}.pair-code{align-items:flex-start;flex-wrap:wrap}}
</style>
