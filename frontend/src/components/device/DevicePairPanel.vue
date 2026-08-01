<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import BaseCard from "@/components/base/BaseCard.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { feishuPairApi, type FeishuPair } from "@/api/feishuPair";
import { useToast } from "@/composables/useToast";
import type { DevicePair } from "@/api/deviceRegistry";

const props = withDefaults(defineProps<{ allowedKinds?: string[]; title?: string; embedded?: boolean }>(), { allowedKinds: () => ["screen", "pi", "computer", "browser", "feishuBot"], embedded: false });

const toast = useToast();
const { t } = useI18n();
const queryClient = useQueryClient();
const deviceName = ref("");
const deviceKind = ref(props.allowedKinds[0] ?? "screen");
const currentPair = ref<DevicePair | FeishuPair | null>(null);
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const supportsFeishu = computed(() => props.allowedKinds.includes("feishuBot"));
const feishuBindings = useQuery({ queryKey: ["userFeishuBindings"], queryFn: feishuPairApi.bindings, enabled: supportsFeishu });
const visibleDevices = computed(() => (devices.data.value ?? []).filter((item) => item.deviceKind !== "feishuBot" && props.allowedKinds.includes(item.deviceKind)));
const visibleFeishuBindings = computed(() => supportsFeishu.value ? feishuBindings.data.value ?? [] : []);
const start = useMutation({
  mutationFn: () => deviceKind.value === "feishuBot"
    ? feishuPairApi.start()
    : deviceRegistryApi.startPair(deviceName.value, deviceKind.value),
  onSuccess: (pair) => { currentPair.value = pair; toast.success(t("pair.created")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const confirm = useMutation({
  mutationFn: () => currentPair.value
    ? currentPair.value.deviceKind === "feishuBot"
      ? feishuPairApi.confirm(currentPair.value.pairId)
      : deviceRegistryApi.confirmPair(currentPair.value.pairId)
    : Promise.reject(new Error(t("pair.required"))),
  onSuccess: async (pair) => {
    currentPair.value = pair;
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }),
      queryClient.invalidateQueries({ queryKey: ["userFeishuBindings"] }),
    ]);
    toast.success(t("pair.confirmed"));
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const remove = useMutation({
  mutationFn: (deviceId: string) => deviceRegistryApi.remove(deviceId),
  onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }); toast.success(t("pair.deleted")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const removeFeishuBinding = useMutation({
  mutationFn: feishuPairApi.removeBinding,
  onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["userFeishuBindings"] }); toast.success(t("pair.deleted")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
async function refreshPair() {
  if (!currentPair.value) return;
  currentPair.value = currentPair.value.deviceKind === "feishuBot"
    ? await feishuPairApi.read(currentPair.value.pairId)
    : await deviceRegistryApi.readPair(currentPair.value.pairId);
}
const screenLink = computed(() => {
  if (currentPair.value?.deviceKind !== "screen") return "";
  const url = new URL("/screen", window.location.origin);
  url.searchParams.set("pairId", currentPair.value.pairId);
  url.searchParams.set("claimCode", currentPair.value.claimCode);
  return url.toString();
});
const computerPairingDocument = computed(() => {
  if (currentPair.value?.deviceKind !== "computer") return "";
  return JSON.stringify({ serverUrl: window.location.origin, pairId: currentPair.value.pairId, claimCode: currentPair.value.claimCode });
});
const guide = computed(() => {
  if (!currentPair.value) return "";
  if (currentPair.value.deviceKind === "feishuBot") return t("pair.feishuGuide", { code: currentPair.value.claimCode });
  if (currentPair.value.deviceKind === "screen") return t("pair.screenGuide");
  if (currentPair.value.deviceKind === "computer") return t("pair.computerGuide");
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
  <component :is="embedded ? 'section' : BaseCard" :title="embedded ? undefined : title ?? t('pair.title')" :class="{ 'device-pair-panel--embedded': embedded }">
    <header v-if="embedded" class="device-pair-panel__header"><h3>{{ title ?? t('pair.title') }}</h3></header>
    <div class="device-pair-list" data-staged-wheel-scroll>
      <article v-for="item in visibleDevices" :key="item.deviceId" class="device-pair-row">
        <div class="device-pair-identity"><strong>{{ item.deviceName }}</strong><small>{{ t(`pair.kind.${item.deviceKind}`) }} · {{ item.stat }}</small></div>
        <div class="device-pair-actions"><small>{{ item.deviceKind === 'feishuBot' ? t('pair.bound') : item.lastSeenAt ? t('pair.updated') : t('pair.notReported') }}</small><button class="icon-button" type="button" :aria-label="t('pair.delete')" :title="t('pair.delete')" :disabled="remove.isPending.value" @click="deleteDevice(item.deviceId, item.deviceName)">×</button></div>
      </article>
      <article v-for="binding in visibleFeishuBindings" :key="binding.bindId" class="device-pair-row">
        <div class="device-pair-identity"><strong>{{ binding.botName }}</strong><small>{{ t('pair.kind.feishuBot') }} · {{ binding.chatType }} {{ binding.chatHint }}</small></div>
        <div class="device-pair-actions"><small>{{ t('pair.bound') }}</small><button class="icon-button" type="button" :aria-label="t('pair.delete')" :title="t('pair.delete')" :disabled="removeFeishuBinding.isPending.value" @click="removeFeishuBinding.mutate(binding.bindId)">×</button></div>
      </article>
      <p v-if="!visibleDevices.length && !visibleFeishuBindings.length" class="muted">{{ t('pair.empty') }}</p>
    </div>
    <form class="device-pair-form" :class="{ 'device-pair-form--single': allowedKinds.length === 1 || deviceKind === 'feishuBot' }" @submit.prevent="start.mutate()"><input v-if="deviceKind !== 'feishuBot'" v-model.trim="deviceName" required :placeholder="t('pair.namePlaceholder')" /><select v-if="allowedKinds.length > 1" v-model="deviceKind"><option v-if="allowedKinds.includes('screen')" value="screen">{{ t('pair.kind.screen') }}</option><option v-if="allowedKinds.includes('pi')" value="pi">{{ t('pair.kind.pi') }}</option><option v-if="allowedKinds.includes('computer')" value="computer">{{ t('pair.kind.computer') }}</option><option v-if="allowedKinds.includes('browser')" value="browser">{{ t('pair.kind.browser') }}</option><option v-if="allowedKinds.includes('feishuBot')" value="feishuBot">{{ t('pair.kind.feishuBot') }}</option></select><button class="button button--primary" :disabled="start.isPending.value">{{ t('pair.start') }}</button></form>
    <section v-if="currentPair" class="pair-flow">
      <header><div><small>{{ t('pair.step') }}</small><strong>{{ currentPair.deviceName }}</strong></div><span class="pair-stat">{{ currentPair.stat }}</span></header>
      <p>{{ guide }}</p>
      <div v-if="currentPair.deviceKind === 'feishuBot'" class="pair-command"><code>绑定 {{ currentPair.claimCode }}</code><button class="button button--ghost" type="button" @click="copy(`绑定 ${currentPair.claimCode}`)">{{ t('pair.copyCommand') }}</button></div>
      <div v-if="computerPairingDocument" class="pair-command"><code>{{ computerPairingDocument }}</code><button class="button button--ghost" type="button" @click="copy(computerPairingDocument)">{{ t('pair.copyComputerConfig') }}</button></div>
      <div v-if="screenLink" class="pair-link"><span>{{ t('pair.screenLinkReady') }}</span><button class="button button--primary" type="button" @click="copy(screenLink)">{{ t('pair.copyScreenLink') }}</button></div>
      <footer><button class="button button--ghost" type="button" @click="refreshPair">{{ t('common.refresh') }}</button><button v-if="currentPair.stat === 'claimed'" class="button button--primary" type="button" :disabled="confirm.isPending.value" @click="confirm.mutate()">{{ t('pair.confirm') }}</button></footer>
    </section>
  </component>
</template>

<style scoped>
.device-pair-panel--embedded{display:grid;gap:16px}.device-pair-panel__header{padding-bottom:10px;border-bottom:1px solid var(--border-color)}.device-pair-panel__header h3{font-size:14px}.device-pair-list{display:grid;gap:4px}.device-pair-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px 2px;border-bottom:1px solid var(--border-color)}.device-pair-identity strong,.device-pair-identity small{display:block}.device-pair-identity small,.device-pair-actions small{margin-top:4px;color:var(--color-text-muted);font-size:12px}.device-pair-actions{display:flex;align-items:center;gap:10px}.icon-button{display:grid;place-items:center;width:30px;height:30px;border:1px solid var(--border-color);border-radius:6px;background:#fff;color:#94a3b8;font-size:21px;line-height:1}.icon-button:hover{border-color:#fecaca;background:#fff1f2;color:#dc2626}.device-pair-form{display:grid;grid-template-columns:minmax(0,1fr) 160px auto;gap:12px;margin-top:18px}.device-pair-form--single{grid-template-columns:minmax(0,1fr) auto}.device-pair-form input,.device-pair-form select{width:100%;min-height:42px;padding:0 12px;border:1px solid var(--border-color);border-radius:7px;background:#fff;font:inherit}.pair-flow{display:grid;gap:13px;margin-top:18px;padding:16px;border:1px solid #dbeafe;border-radius:8px;background:#f8fbff}.pair-flow header,.pair-flow footer,.pair-link,.pair-command{display:flex;align-items:center;justify-content:space-between;gap:12px}.pair-flow header small,.pair-flow header strong{display:block}.pair-flow header small{margin-bottom:3px;color:#64748b;font-size:12px}.pair-flow p{margin:0;color:#475569;line-height:1.55}.pair-stat{padding:5px 9px;border-radius:999px;background:#eff6ff;color:#2563eb;font-size:12px}.pair-command{padding:11px 12px;border-radius:7px;background:#f8fafc}.pair-command code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.pair-link{padding:11px 12px;border-radius:7px;background:#eff6ff;color:#1e40af}.pair-link span{font-size:13px}.pair-flow footer{justify-content:flex-end}@media(max-width:700px){.device-pair-form{grid-template-columns:1fr}.device-pair-row{align-items:flex-start}.device-pair-actions small{display:none}.pair-flow header,.pair-flow footer,.pair-link,.pair-command{align-items:flex-start;flex-direction:column}.pair-flow footer{align-items:stretch}.pair-flow footer .button{width:100%}}
</style>
