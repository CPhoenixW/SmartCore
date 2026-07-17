<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import { adminApi, type FeishuBot, type FeishuBotInput } from "@/api/admin";
import { useToast } from "@/composables/useToast";

const toast = useToast();
const { t } = useI18n();
const queryClient = useQueryClient();
const form = reactive<FeishuBotInput>({ botName: "", appId: "", appSecret: "", verificationToken: "", encryptKey: "", defaultChatId: "", isDefault: false });
const editing = ref<FeishuBot | null>(null);
const pair = ref<{ pairId: string; claimCode: string; stat: string; botId: string } | null>(null);
const bots = useQuery({ queryKey: ["feishuBots"], queryFn: adminApi.feishuBots });
const refresh = () => queryClient.invalidateQueries({ queryKey: ["feishuBots"] });
const activeBotId = computed(() => (bots.data.value ?? [])[0]?.botId ?? "");
const binds = useQuery({ queryKey: ["feishuBinds", activeBotId], queryFn: () => adminApi.feishuBinds(activeBotId.value), enabled: computed(() => Boolean(activeBotId.value)) });
const refreshBinds = async () => { await queryClient.invalidateQueries({ queryKey: ["feishuBinds"] }); await refresh(); };

const save = useMutation({
  mutationFn: () => {
    if (!editing.value) return adminApi.createFeishuBot({ ...form });
    const update: Partial<FeishuBotInput> = { botName: form.botName, isDefault: form.isDefault };
    if (form.appId) update.appId = form.appId;
    if (form.appSecret) update.appSecret = form.appSecret;
    if (form.verificationToken) update.verificationToken = form.verificationToken;
    if (form.encryptKey) update.encryptKey = form.encryptKey;
    if (form.defaultChatId) update.defaultChatId = form.defaultChatId;
    return adminApi.updateFeishuBot(editing.value.botId, update);
  },
  onSuccess: async () => { editing.value = null; Object.assign(form, { botName: "", appId: "", appSecret: "", verificationToken: "", encryptKey: "", defaultChatId: "", isDefault: false }); await refresh(); toast.success(t("feishuBot.saved")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const toggle = useMutation({ mutationFn: adminApi.toggleFeishuBot, onSuccess: refresh, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const test = useMutation({ mutationFn: adminApi.testFeishuBot, onSuccess: async () => { await refresh(); toast.success(t("feishuBot.testSent")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const start = useMutation({ mutationFn: adminApi.startFeishuPair, onSuccess: (data) => { pair.value = data; toast.success(t("feishuBot.pairCreated")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const confirm = useMutation({ mutationFn: () => pair.value ? adminApi.confirmFeishuPair(pair.value.botId, pair.value.pairId) : Promise.reject(new Error(t("feishuBot.noPair"))), onSuccess: async () => { pair.value = null; await refresh(); toast.success(t("feishuBot.activated")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const remove = useMutation({ mutationFn: adminApi.deleteFeishuBot, onSuccess: async () => { await refresh(); toast.success(t("feishuBot.deleted")); }, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const makePrimary = useMutation({ mutationFn: ({ botId, bindId }: { botId: string; bindId: string }) => adminApi.setPrimaryFeishuBind(botId, bindId), onSuccess: refreshBinds, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });
const removeBind = useMutation({ mutationFn: ({ botId, bindId }: { botId: string; bindId: string }) => adminApi.deleteFeishuBind(botId, bindId), onSuccess: refreshBinds, onError: (error) => toast.error(error instanceof Error ? error.message : String(error)) });

function edit(bot: FeishuBot) { editing.value = bot; Object.assign(form, { botName: bot.botName, appId: "", appSecret: "", verificationToken: "", encryptKey: "", defaultChatId: "", isDefault: bot.isDefault }); }
function reset() { editing.value = null; Object.assign(form, { botName: "", appId: "", appSecret: "", verificationToken: "", encryptKey: "", defaultChatId: "", isDefault: false }); }
async function copyCode() {
  if (!pair.value) return;
  const text = `绑定 ${pair.value.claimCode}`;
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {
      const input = document.createElement("textarea");
      input.value = text;
      input.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(input);
      input.select();
      if (!document.execCommand("copy")) throw new Error("copy failed");
      input.remove();
    }
    toast.success(t("feishuBot.copied"));
  } catch { toast.error(t("pair.copyFailed")); }
}
</script>

<template>
  <BaseCard :title="t('feishuBot.title')">
    <div class="bot-list">
      <article v-for="bot in bots.data.value ?? []" :key="bot.botId" class="bot-row">
        <div><strong>{{ bot.botName }}</strong><small>{{ bot.appIdHint }} · {{ bot.enabled ? t('feishuBot.enabled') : t('feishuBot.disabled') }}{{ bot.hasRecipient ? ` · ${t('feishuBot.bound')}` : ` · ${t('feishuBot.unbound')}` }}</small></div>
        <div class="bot-actions"><button class="text-button" type="button" @click="start.mutate(bot.botId)">{{ t('feishuBot.pair') }}</button><button class="text-button" type="button" :disabled="!bot.hasRecipient || test.isPending.value" @click="test.mutate(bot.botId)">{{ t('feishuBot.test') }}</button><button class="text-button" type="button" @click="edit(bot)">{{ t('common.edit') }}</button><button class="text-button" type="button" @click="toggle.mutate(bot.botId)">{{ bot.enabled ? t('feishuBot.disable') : t('feishuBot.enable') }}</button><button class="text-button text-button--danger" type="button" @click="remove.mutate(bot.botId)">{{ t('common.delete') }}</button></div>
      </article>
      <p v-if="!(bots.data.value ?? []).length" class="muted">{{ t('feishuBot.empty') }}</p>
    </div>
    <section v-if="pair" class="bot-pair-flow"><strong>{{ t('feishuBot.sendCommand') }}</strong><code>绑定 {{ pair.claimCode }}</code><div><button class="button button--ghost" type="button" @click="copyCode">{{ t('feishuBot.copyCommand') }}</button><button class="button button--primary" type="button" :disabled="confirm.isPending.value" @click="confirm.mutate()">{{ t('feishuBot.confirm') }}</button></div></section>
    <section v-if="activeBotId" class="bind-list">
      <h3>已绑定聊天会话</h3>
      <div v-for="bind in binds.data.value ?? []" :key="bind.bindId" class="bind-row">
        <div><strong>{{ bind.chatType }} · {{ bind.chatId }}</strong><small>{{ bind.isPrimary ? '提醒主会话' : '仅接收输入' }}</small></div>
        <div class="bot-actions"><button v-if="!bind.isPrimary" class="text-button" type="button" @click="makePrimary.mutate({ botId: activeBotId, bindId: bind.bindId })">设为主会话</button><button class="text-button text-button--danger" type="button" @click="removeBind.mutate({ botId: activeBotId, bindId: bind.bindId })">解绑</button></div>
      </div>
    </section>
    <form class="bot-form" @submit.prevent="save.mutate()">
      <h3>{{ editing ? t('feishuBot.editTitle') : t('feishuBot.addTitle') }}</h3>
      <label><span>{{ t('feishuBot.name') }}</span><input v-model.trim="form.botName" required /></label>
      <label><span>App ID</span><input v-model.trim="form.appId" :required="!editing" :placeholder="editing ? '留空则不修改' : ''" /></label>
      <label><span>App Secret</span><input v-model.trim="form.appSecret" type="password" :required="!editing" :placeholder="editing ? '留空则不修改' : ''" /></label>
      <label><span>Verification Token</span><input v-model.trim="form.verificationToken" type="password" :required="!editing" :placeholder="editing ? '留空则不修改' : ''" /></label>
      <label><span>Encrypt Key</span><input v-model.trim="form.encryptKey" type="password" :required="!editing" :placeholder="editing ? '留空则不修改' : ''" /></label>
      <label class="bot-default"><input v-model="form.isDefault" type="checkbox" /> {{ t('feishuBot.default') }}</label>
      <div><button class="button button--primary" type="submit" :disabled="save.isPending.value">{{ t('feishuBot.save') }}</button><button v-if="editing" class="button button--ghost" type="button" @click="reset">{{ t('common.cancel') }}</button></div>
    </form>
  </BaseCard>
</template>

<style scoped>
.bot-list,.bind-list{display:grid;gap:2px}.bind-list{margin:18px 0;padding:16px 0;border-top:1px solid var(--border-subtle);border-bottom:1px solid var(--border-subtle)}.bind-list h3{margin:0 0 4px}.bot-row,.bind-row{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 0;border-bottom:1px solid var(--border-subtle)}.bot-row strong,.bot-row small,.bind-row strong,.bind-row small{display:block}.bot-row small,.bind-row small{margin-top:4px;color:var(--text-muted)}.bot-actions{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:10px}.text-button{border:0;background:transparent;color:var(--accent);font:inherit;cursor:pointer}.text-button--danger{color:#dc2626}.bot-pair-flow{display:grid;gap:10px;margin:18px 0;padding:16px;border:1px solid #bfdbfe;border-radius:16px;background:#f8fbff}.bot-pair-flow code{width:max-content;max-width:100%;overflow:hidden;text-overflow:ellipsis;padding:8px 10px;border-radius:8px;background:#fff;color:#1e3a8a}.bot-pair-flow>div{display:flex;gap:10px}.bot-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:20px;padding-top:20px;border-top:1px solid var(--border-subtle)}.bot-form h3,.bot-form>div,.bot-default{grid-column:1/-1}.bot-form label{display:grid;gap:7px;color:var(--text-secondary)}.bot-form input{min-width:0;padding:11px 13px;border:1px solid var(--border-color);border-radius:14px;font:inherit}.bot-default{display:flex!important;align-items:center;gap:8px}.bot-default input{min-width:auto;padding:0}@media(max-width:700px){.bot-row,.bind-row{align-items:flex-start;flex-direction:column}.bot-actions{justify-content:flex-start}.bot-form{grid-template-columns:1fr}}
</style>
