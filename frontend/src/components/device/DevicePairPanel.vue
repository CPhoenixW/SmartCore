<script setup lang="ts">
import { computed, ref } from "vue";
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
const start = useMutation({
  mutationFn: () => deviceRegistryApi.startPair(deviceName.value, deviceKind.value),
  onSuccess: (pair) => { currentPair.value = pair; toast.success(t("pair.created")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const confirm = useMutation({
  mutationFn: () => currentPair.value ? deviceRegistryApi.confirmPair(currentPair.value.pairId) : Promise.reject(new Error(t("pair.required"))),
  onSuccess: async (pair) => { currentPair.value = pair; await queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }); toast.success(t("pair.confirmed")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const remove = useMutation({
  mutationFn: (deviceId: string) => deviceRegistryApi.remove(deviceId),
  onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }); toast.success(t("pair.deleted")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
async function refreshPair() { if (currentPair.value) currentPair.value = await deviceRegistryApi.readPair(currentPair.value.pairId); }
const screenLink = computed(() => {
  if (currentPair.value?.deviceKind !== "screen") return "";
  const url = new URL("/screen", window.location.origin);
  url.searchParams.set("pairId", currentPair.value.pairId);
  url.searchParams.set("claimCode", currentPair.value.claimCode);
  return url.toString();
});
const guide = computed(() => {
  if (!currentPair.value) return "";
  if (currentPair.value.deviceKind === "feishuBot") return t("pair.feishuGuide", { code: currentPair.value.claimCode });
  if (currentPair.value.deviceKind === "screen") return t("pair.screenGuide");
  return t("pair.hint");
});
async function copy(value: string) {
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) await navigator.clipboard.writeText(value);
    else {
      const input = document.createElement("textarea");
      input.value = value;
      input.setAttribute("readonly", "");
      input.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(input);
      input.select();
      if (!document.execCommand("copy")) throw new Error("copy command failed");
      input.remove();
    }
    toast.success(t("pair.copied"));
  } catch { toast.error(t("pair.copyFailed")); }
}
function deleteDevice(deviceId: string, name: string) {
  if (window.confirm(t("pair.deleteConfirm", { name }))) remove.mutate(deviceId);
}
</script>

<template>
  <BaseCard :title="t('pair.title')">
    <div class="device-pair-list">
      <article v-for="item in devices.data.value ?? []" :key="item.deviceId" class="device-pair-row">
        <div class="device-pair-identity"><strong>{{ item.deviceName }}</strong><small>{{ t(`pair.kind.${item.deviceKind}`) }} · {{ item.stat }}</small></div>
        <div class="device-pair-actions"><small>{{ item.lastSeenAt ? t('pair.updated') : t('pair.notReported') }}</small><button class="icon-button" type="button" :aria-label="t('pair.delete')" :title="t('pair.delete')" :disabled="remove.isPending.value" @click="deleteDevice(item.deviceId, item.deviceName)">×</button></div>
      </article>
      <p v-if="!(devices.data.value ?? []).length" class="muted">{{ t('pair.empty') }}</p>
    </div>
    <form class="device-pair-form" @submit.prevent="start.mutate()"><input v-model.trim="deviceName" required :placeholder="t('pair.namePlaceholder')" /><select v-model="deviceKind"><option value="screen">{{ t('pair.kind.screen') }}</option><option value="pi">{{ t('pair.kind.pi') }}</option><option value="browser">{{ t('pair.kind.browser') }}</option><option value="feishuBot">{{ t('pair.kind.feishuBot') }}</option></select><button class="button button--primary" :disabled="start.isPending.value">{{ t('pair.start') }}</button></form>
    <section v-if="currentPair" class="pair-flow">
      <header><div><small>{{ t('pair.step') }}</small><strong>{{ currentPair.deviceName }}</strong></div><span class="pair-stat">{{ currentPair.stat }}</span></header>
      <p>{{ guide }}</p>
      <div v-if="currentPair.deviceKind === 'feishuBot'" class="pair-command"><code>绑定 {{ currentPair.claimCode }}</code><button class="button button--ghost" type="button" @click="copy(`绑定 ${currentPair.claimCode}`)">{{ t('pair.copyCommand') }}</button></div>
      <div v-if="screenLink" class="pair-link"><span>{{ t('pair.screenLinkReady') }}</span><button class="button button--primary" type="button" @click="copy(screenLink)">{{ t('pair.copyScreenLink') }}</button></div>
      <footer><button class="button button--ghost" type="button" @click="refreshPair">{{ t('common.refresh') }}</button><button v-if="currentPair.stat === 'claimed'" class="button button--primary" type="button" :disabled="confirm.isPending.value" @click="confirm.mutate()">{{ t('pair.confirm') }}</button></footer>
    </section>
  </BaseCard>
</template>

<style scoped>
.device-pair-list{display:grid;gap:4px}.device-pair-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 2px;border-bottom:1px solid var(--border-subtle)}.device-pair-identity strong,.device-pair-identity small{display:block}.device-pair-identity small,.device-pair-actions small{margin-top:4px;color:var(--text-muted);font-size:12px}.device-pair-actions{display:flex;align-items:center;gap:10px}.icon-button{display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--border-color);border-radius:50%;background:#fff;color:#94a3b8;font-size:21px;line-height:1}.icon-button:hover{border-color:#fecaca;background:#fff1f2;color:#dc2626}.device-pair-form{display:grid;grid-template-columns:minmax(0,1fr) 160px auto;gap:12px;margin-top:18px}.device-pair-form input,.device-pair-form select{width:100%;min-height:46px;padding:0 15px;border:1px solid var(--border-color);border-radius:18px;background:#fff;font:inherit}.device-pair-form .button{border-radius:18px}.pair-flow{display:grid;gap:13px;margin-top:18px;padding:18px;border:1px solid #dbeafe;border-radius:16px;background:linear-gradient(135deg,#f8fbff,#fff)}.pair-flow header,.pair-flow footer,.pair-link,.pair-command{display:flex;align-items:center;justify-content:space-between;gap:12px}.pair-flow header small,.pair-flow header strong{display:block}.pair-flow header small{margin-bottom:3px;color:#64748b;font-size:12px}.pair-flow p{margin:0;color:#475569;line-height:1.55}.pair-stat{padding:5px 9px;border-radius:999px;background:#eff6ff;color:#2563eb;font-size:12px}.pair-command{padding:11px 12px;border-radius:12px;background:#f8fafc}.pair-command code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pair-link{padding:11px 12px;border-radius:12px;background:#eff6ff;color:#1e40af}.pair-link span{font-size:13px}.pair-flow footer{justify-content:flex-end}@media(max-width:700px){.device-pair-form{grid-template-columns:1fr}.device-pair-row{align-items:flex-start}.device-pair-actions small{display:none}.pair-flow header,.pair-flow footer,.pair-link,.pair-command{align-items:flex-start;flex-direction:column}.pair-flow footer{align-items:stretch}.pair-flow footer .button{width:100%}}
</style>
