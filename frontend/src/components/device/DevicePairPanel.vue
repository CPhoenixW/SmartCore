<script setup lang="ts">
import { ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import BaseCard from "@/components/base/BaseCard.vue";
import { deviceRegistryApi } from "@/api/deviceRegistry";
import { useToast } from "@/composables/useToast";

const toast = useToast();
const queryClient = useQueryClient();
const deviceName = ref("");
const deviceKind = ref("screen");
const currentPair = ref<Awaited<ReturnType<typeof deviceRegistryApi.startPair>> | null>(null);
const devices = useQuery({ queryKey: ["lifeDevices"], queryFn: deviceRegistryApi.list, refetchInterval: 15_000 });
const start = useMutation({ mutationFn: () => deviceRegistryApi.startPair(deviceName.value, deviceKind.value), onSuccess: (pair) => { currentPair.value = pair; toast.success("配对码已生成，等待设备领取"); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const confirm = useMutation({ mutationFn: () => currentPair.value ? deviceRegistryApi.confirmPair(currentPair.value.pairId) : Promise.reject(new Error("请先生成配对码")), onSuccess: async (pair) => { currentPair.value = pair; await queryClient.invalidateQueries({ queryKey: ["lifeDevices"] }); toast.success("已确认，设备可完成激活"); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
async function refreshPair() { if (currentPair.value) currentPair.value = await deviceRegistryApi.readPair(currentPair.value.pairId); }
</script>

<template>
  <BaseCard title="已注册设备">
    <div class="device-pair-list">
      <div v-for="item in devices.data.value ?? []" :key="item.deviceId" class="device-pair-row"><div><strong>{{ item.deviceName }}</strong><small>{{ item.deviceKind }} · {{ item.stat }}</small></div><span>{{ item.lastSeenAt ? '在线记录已更新' : '尚未上报' }}</span></div>
      <p v-if="!(devices.data.value ?? []).length" class="muted">还没有已激活设备。</p>
    </div>
    <form class="device-pair-form" @submit.prevent="start.mutate()"><input v-model.trim="deviceName" required placeholder="设备名称，例如：书桌副屏" /><select v-model="deviceKind"><option value="screen">副屏</option><option value="pi">树莓派</option><option value="browser">电脑后台</option><option value="feishuBot">飞书机器人</option></select><button class="button button--primary" :disabled="start.isPending.value">开始配对</button></form>
    <div v-if="currentPair" class="pair-code"><div><strong>设备配对信息</strong><small>Pair ID</small><code>{{ currentPair.pairId }}</code><small>配对码</small><code>{{ currentPair.claimCode }}</code><small>设备端先领取，再回到这里确认；激活时两个值都需要使用。</small></div><span class="pair-stat">{{ currentPair.stat }}</span><button class="button button--ghost" type="button" @click="refreshPair">刷新</button><button v-if="currentPair.stat === 'claimed'" class="button button--primary" type="button" :disabled="confirm.isPending.value" @click="confirm.mutate()">确认此设备</button></div>
  </BaseCard>
</template>

<style scoped>
.device-pair-list{display:grid;gap:8px}.device-pair-row{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--border-subtle)}.device-pair-row small,.pair-code small{display:block;color:var(--text-muted);margin-top:3px}.device-pair-row span{color:var(--text-muted);font-size:13px}.device-pair-form{display:grid;grid-template-columns:minmax(0,1fr) 130px auto;gap:10px;margin-top:16px}.pair-code{display:flex;align-items:center;gap:10px;margin-top:14px;padding:12px;border:1px solid var(--border-subtle);border-radius:8px;background:var(--surface-subtle)}.pair-code>div{margin-right:auto}.pair-code code{display:block;font-size:14px;margin:5px 0;word-break:break-all}.pair-stat{font-size:12px;color:var(--text-muted)}@media(max-width:700px){.device-pair-form{grid-template-columns:1fr}.pair-code{align-items:flex-start;flex-wrap:wrap}}
</style>
