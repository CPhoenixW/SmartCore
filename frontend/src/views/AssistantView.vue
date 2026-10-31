<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Bot, Check, Search, Send, WifiOff, X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import PageHeader from "@/components/base/PageHeader.vue";
import { assistantApi } from "@/api/assistant";
import type {
  AssistantConversation,
  AssistantMessage,
  AssistantSearchResult,
  AssistantStreamEvent,
} from "@/api/assistant";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const route = useRoute() as ReturnType<typeof useRoute> | undefined;
const input = ref("");
const searchQuery = ref("");
const searchResults = ref<AssistantSearchResult[]>([]);
const searchOpen = ref(false);
const searchLoading = ref(false);
const loading = ref(true);
const activeConversationId = ref("");
const activeConversation = ref<AssistantConversation | null>(null);
const messages = ref<AssistantMessage[]>([]);
const sending = ref(false);
const error = ref("");
const activity = ref("");
const activeTool = ref("");
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const messagesRoot = ref<HTMLElement | null>(null);
const highlightMessageId = ref("");
let syncTimer: ReturnType<typeof setInterval> | undefined;
let searchTimer: ReturnType<typeof setTimeout> | undefined;

function newClientId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function dateLabel(value: string): string {
  return formatDateTime(value, locale.value === "en-US" ? "en-US" : "zh-CN");
}
function scrollToLatest(): void {
  void nextTick(() => {
    if (messagesRoot.value) messagesRoot.value.scrollTop = messagesRoot.value.scrollHeight;
  });
}
function scrollToMessage(messageId: string): void {
  void nextTick(() => document.getElementById(`assistant-message-${messageId}`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
}
async function loadConversation(conversationId: string, messageId?: string, silent = false): Promise<void> {
  if (!silent) loading.value = true;
  try {
    const result = await assistantApi.read(conversationId);
    activeConversation.value = result;
    activeConversationId.value = result.conversationId;
    messages.value = result.messages;
    highlightMessageId.value = messageId ?? "";
    if (!silent) scrollToLatest();
    if (messageId) scrollToMessage(messageId);
  } catch (requestError) {
    if (!silent) error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    if (!silent) loading.value = false;
  }
}
async function loadPrimaryConversation(): Promise<void> {
  loading.value = true;
  error.value = "";
  try {
    const result = await assistantApi.list();
    const primary = result.items[0] as AssistantConversation | undefined;
    if (!primary) throw new Error(t("assistant.historyError"));
    await loadConversation(primary.conversationId);
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    loading.value = false;
  }
}
async function syncConversation(): Promise<void> {
  if (sending.value || !activeConversationId.value || document.visibilityState === "hidden") return;
  await loadConversation(activeConversationId.value, undefined, true);
}
async function runSearch(): Promise<void> {
  const query = searchQuery.value.trim();
  if (!query) {
    searchResults.value = [];
    searchOpen.value = false;
    return;
  }
  searchLoading.value = true;
  searchOpen.value = true;
  try {
    const result = await assistantApi.list(query);
    searchResults.value = result.items as AssistantSearchResult[];
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.searchError");
  } finally {
    searchLoading.value = false;
  }
}
function scheduleSearch(): void {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => void runSearch(), 220);
}
function clearSearch(): void {
  searchQuery.value = "";
  searchResults.value = [];
  searchOpen.value = false;
}
async function openSearchResult(result: AssistantSearchResult): Promise<void> {
  searchOpen.value = false;
  if (result.conversationId !== activeConversationId.value) await loadPrimaryConversation();
  highlightMessageId.value = result.messageId;
  scrollToMessage(result.messageId);
}
async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text || sending.value) return;
  if (!online.value) {
    error.value = t("assistant.offline");
    return;
  }
  if (!activeConversationId.value) {
    await loadPrimaryConversation();
    if (!activeConversationId.value) return;
  }
  input.value = "";
  error.value = "";
  const clientMessageId = newClientId();
  const optimistic: AssistantMessage = {
    messageId: `local-${clientMessageId}`,
    conversationId: activeConversationId.value,
    role: "user",
    text,
    stat: "complete",
    createdAt: new Date().toISOString(),
  };
  messages.value.push(optimistic);
  scrollToLatest();
  sending.value = true;
  activity.value = t("assistant.starting");
  activeTool.value = "";
  try {
    const result = await assistantApi.stream(
      text,
      activeConversationId.value,
      (event: AssistantStreamEvent) => {
        if (event.type === "status") activity.value = event.message || t("assistant.thinking");
        if (event.type === "tool") {
          activity.value = event.message || t("assistant.toolWorking");
          activeTool.value = event.name || "";
        }
        if (event.type === "message" && event.text.trim()) {
          const live: AssistantMessage = {
            messageId: `live-${clientMessageId}`,
            conversationId: activeConversationId.value,
            role: "assistant",
            text: event.text,
            stat: "pending",
            createdAt: new Date().toISOString(),
          };
          const index = messages.value.findIndex((item) => item.messageId === live.messageId);
          if (index >= 0) messages.value[index] = live;
          else messages.value.push(live);
          scrollToLatest();
        }
        if (event.type === "done") activity.value = t("assistant.done");
      },
      clientMessageId,
    );
    activeConversationId.value = result.conversationId || result.sessionId || activeConversationId.value;
    await loadConversation(activeConversationId.value);
  } catch (requestError) {
    error.value = requestError instanceof Error && requestError.message ? requestError.message : t("assistant.error");
    await loadConversation(activeConversationId.value);
  } finally {
    sending.value = false;
    activity.value = "";
    activeTool.value = "";
    scrollToLatest();
  }
}
function setQuickPrompt(value: string): void {
  input.value = value;
}
function onOnline(): void { online.value = true; }
function onOffline(): void { online.value = false; }
function onVisibilityChange(): void { if (document.visibilityState === "visible") void syncConversation(); }

onMounted(() => {
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  document.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("focus", syncConversation);
  input.value = String(route?.query?.prompt || "");
  void loadPrimaryConversation();
  syncTimer = setInterval(() => void syncConversation(), 20000);
});
watch(() => route?.query?.prompt, (value) => {
  if (value) input.value = String(value);
});
onBeforeUnmount(() => {
  window.removeEventListener("online", onOnline);
  window.removeEventListener("offline", onOffline);
  document.removeEventListener("visibilitychange", onVisibilityChange);
  window.removeEventListener("focus", syncConversation);
  if (syncTimer) clearInterval(syncTimer);
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <div class="assistant-page">
    <PageHeader :title="t('assistant.title')" :subtitle="t('assistant.subtitle')">
      <template #actions>
        <form class="assistant-search" role="search" @submit.prevent="runSearch">
          <Search :size="16" aria-hidden="true" />
          <input v-model="searchQuery" :placeholder="t('assistant.searchPlaceholder')" :aria-label="t('assistant.searchPlaceholder')" @input="scheduleSearch" @focus="searchOpen = Boolean(searchQuery)" />
          <button v-if="searchQuery" class="assistant-search__clear" type="button" :aria-label="t('common.clear')" @click="clearSearch"><X :size="14" aria-hidden="true" /></button>
        </form>
      </template>
    </PageHeader>
    <section class="assistant-shell card">
      <header class="assistant-shell__header">
        <div class="assistant-shell__title"><Bot :size="19" aria-hidden="true" /><div><strong>{{ t("assistant.bot") }}</strong><small>{{ t("assistant.syncHint") }}</small></div></div>
        <span class="assistant-sync" :class="{ 'assistant-sync--ready': !loading && online }"><Check v-if="!loading && online" :size="14" aria-hidden="true" /><WifiOff v-else-if="!online" :size="14" aria-hidden="true" /><span>{{ !online ? t("assistant.offlineShort") : loading ? t("assistant.syncing") : t("assistant.synced") }}</span></span>
      </header>
      <div v-if="searchOpen" class="assistant-search-results">
        <button v-for="result in searchResults" :key="`${result.messageId}-${result.conversationId}`" type="button" @click="openSearchResult(result)"><span>{{ result.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span><strong>{{ result.snippet }}</strong><time>{{ dateLabel(result.createdAt) }}</time></button>
        <p v-if="searchLoading" class="assistant-search-results__empty">{{ t("common.loading") }}</p>
        <p v-else-if="!searchResults.length" class="assistant-search-results__empty">{{ t("assistant.noSearchResults") }}</p>
      </div>
      <div class="assistant-status" :class="{ 'assistant-status--offline': !online }">
        <WifiOff v-if="!online" :size="15" aria-hidden="true" />
        <Bot v-else :size="15" aria-hidden="true" />
        <span>{{ online ? (sending ? activity || t("assistant.thinking") : t("assistant.ready")) : t("assistant.offline") }}</span>
        <small v-if="activeTool">{{ activeTool }}</small>
      </div>
      <div ref="messagesRoot" class="assistant-messages" aria-live="polite">
        <div v-if="!messages.length && !loading" class="assistant-empty"><Bot :size="30" aria-hidden="true" /><strong>{{ t("assistant.empty") }}</strong><span>{{ t("assistant.examples") }}</span><div class="assistant-quick-prompts"><button type="button" @click="setQuickPrompt(t('assistant.quickToday'))">{{ t("assistant.quickToday") }}</button><button type="button" @click="setQuickPrompt(t('assistant.quickCapture'))">{{ t("assistant.quickCapture") }}</button><button type="button" @click="setQuickPrompt(t('assistant.quickDeadline'))">{{ t("assistant.quickDeadline") }}</button></div></div>
        <article v-for="message in messages" :id="`assistant-message-${message.messageId}`" :key="message.messageId" class="assistant-message" :class="[`assistant-message--${message.role}`, { 'assistant-message--highlight': highlightMessageId === message.messageId, 'assistant-message--failed': message.stat === 'failed' }]">
          <span class="assistant-message__label">{{ message.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span><p>{{ message.text || t("assistant.pending") }}</p><time>{{ dateLabel(message.createdAt) }}</time>
        </article>
        <div v-if="sending" class="assistant-typing" role="status"><span class="assistant-typing__dot" />{{ activity || t("assistant.thinking") }}<small v-if="activeTool">{{ activeTool }}</small></div>
      </div>
      <p v-if="error" class="assistant-error" role="alert">{{ error }}</p>
      <form class="assistant-composer" @submit.prevent="send"><textarea v-model="input" :disabled="sending || loading" :placeholder="t('assistant.placeholder')" rows="2" @keydown.enter.exact.prevent="send" /><button class="button button--primary assistant-send" type="submit" :disabled="sending || loading || !input.trim()"><Send :size="16" aria-hidden="true" />{{ sending ? t("assistant.sending") : t("assistant.send") }}</button></form>
    </section>
  </div>
</template>

<style scoped>
.assistant-page{display:grid;gap:16px;min-height:calc(100dvh - 120px)}.assistant-search{display:flex;align-items:center;gap:8px;width:min(360px,42vw);padding:9px 11px;border:1px solid var(--border-color);border-radius:12px;background:var(--color-surface-muted)}.assistant-search input{min-width:0;flex:1;border:0;outline:0;background:transparent;font:inherit}.assistant-search__clear{display:grid;place-items:center;border:0;background:transparent;color:var(--color-text-muted)}.assistant-shell{display:flex;min-height:calc(100dvh - 220px);min-width:0;flex-direction:column}.assistant-shell__header{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid var(--border-color)}.assistant-shell__title{display:flex;align-items:center;gap:9px;min-width:0;flex:1}.assistant-shell__title>div{display:grid;gap:2px;min-width:0}.assistant-shell__title strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.assistant-shell__title small{color:var(--color-text-muted);font-size:11px}.assistant-sync{display:flex;align-items:center;gap:5px;color:#64748b;font-size:12px;white-space:nowrap}.assistant-sync--ready{color:#15803d}.assistant-status{display:flex;align-items:center;gap:7px;padding:10px 18px;border-bottom:1px solid var(--border-color);color:#166534;font-size:13px}.assistant-status small{margin-left:auto;color:#2563eb}.assistant-status--offline{color:#9a3412;background:#fff7ed}.assistant-search-results{position:absolute;z-index:5;top:72px;right:28px;width:min(420px,calc(100% - 56px));padding:7px;border:1px solid var(--border-color);border-radius:12px;background:#fff;box-shadow:0 12px 30px rgb(15 23 42 / 14%)}.assistant-search-results button{display:grid;width:100%;gap:4px;padding:9px;border:0;border-radius:8px;background:transparent;text-align:left;font:inherit}.assistant-search-results button:hover{background:#eff6ff}.assistant-search-results button span,.assistant-search-results button time{color:var(--color-text-muted);font-size:11px}.assistant-search-results button strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.assistant-search-results__empty{padding:12px;color:var(--color-text-muted);font-size:12px;text-align:center}.assistant-messages{display:grid;align-content:start;gap:14px;min-height:0;flex:1;padding:22px;overflow-y:auto;background:#f8fafc;overscroll-behavior:contain}.assistant-empty{display:grid;justify-items:center;gap:9px;margin:auto;color:var(--color-text-muted);text-align:center}.assistant-empty svg{color:var(--color-primary)}.assistant-empty span{max-width:360px;font-size:13px}.assistant-quick-prompts{display:flex;flex-wrap:wrap;justify-content:center;gap:7px;margin-top:6px}.assistant-quick-prompts button{padding:8px 10px;border:1px solid #bfdbfe;border-radius:999px;background:#eff6ff;color:#1d4ed8;font:inherit;font-size:12px}.assistant-message{position:relative;max-width:min(760px,88%);padding:12px 14px;border-radius:14px;background:#fff;box-shadow:0 3px 10px rgb(15 23 42 / 6%)}.assistant-message--user{justify-self:end;background:#2563eb;color:#fff}.assistant-message--highlight{outline:3px solid #93c5fd}.assistant-message--failed{border:1px solid #fecaca;background:#fff1f2;color:#991b1b}.assistant-message__label{display:block;margin-bottom:5px;color:#64748b;font-size:11px;font-weight:700}.assistant-message--user .assistant-message__label{color:#dbeafe}.assistant-message p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}.assistant-message time{display:block;margin-top:7px;color:#94a3b8;font-size:10px}.assistant-message--user time{color:#bfdbfe}.assistant-typing{display:flex;align-items:center;gap:8px;justify-self:start;color:var(--color-text-muted);font-size:13px}.assistant-typing small{color:#2563eb}.assistant-typing__dot{width:8px;height:8px;border-radius:50%;background:#2563eb;box-shadow:0 0 0 0 rgb(37 99 235 / 50%);animation:assistant-pulse 1.35s infinite}.assistant-error{margin:0;padding:10px 18px;color:#991b1b;background:#fff1f2;font-size:13px}.assistant-composer{display:flex;align-items:flex-end;gap:10px;padding:14px;border-top:1px solid var(--border-color);background:#fff}.assistant-composer textarea{min-height:44px;max-height:160px;flex:1;resize:vertical;padding:11px;border:1px solid var(--border-color);border-radius:10px;outline:0;font:inherit}.assistant-composer textarea:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgb(96 165 250 / 15%)}.assistant-send{display:inline-flex;align-items:center;gap:7px;min-height:44px}@keyframes assistant-pulse{70%{box-shadow:0 0 0 7px rgb(37 99 235 / 0)}}
@media(max-width:760px){.assistant-page{gap:10px;min-height:calc(100dvh - 105px)}.assistant-page :deep(.page-heading){align-items:flex-start;gap:10px;margin-bottom:6px}.assistant-page :deep(.page-heading h1){font-size:24px}.assistant-page :deep(.page-heading p){max-width:48vw;font-size:12px;line-height:1.35}.assistant-page :deep(.page-heading__actions){flex:1}.assistant-search{width:100%;padding:8px 9px;border-radius:10px}.assistant-shell{min-height:calc(100dvh - 180px);margin:0 -2px;border-radius:12px}.assistant-shell__header{padding:12px 13px}.assistant-shell__title small{max-width:38vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.assistant-sync{font-size:11px}.assistant-status{padding:9px 13px;font-size:12px}.assistant-messages{padding:14px 12px 18px}.assistant-message{max-width:94%;padding:11px 12px}.assistant-composer{padding:10px 10px calc(10px + env(safe-area-inset-bottom));align-items:stretch;flex-direction:column;gap:8px}.assistant-composer textarea{width:100%;min-height:48px;max-height:130px;resize:none}.assistant-send{justify-content:center;width:100%}.assistant-search-results{position:fixed;top:142px;right:12px;width:calc(100% - 24px)}}
</style>
