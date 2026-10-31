<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Archive, ArrowLeft, Bot, MessageCircle, Plus, Search, Send, WifiOff, X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import PageHeader from "@/components/base/PageHeader.vue";
import { assistantApi } from "@/api/assistant";
import type {
  AssistantConversation,
  AssistantConversationSummary,
  AssistantImportMessage,
  AssistantMessage,
  AssistantSearchResult,
  AssistantStreamEvent,
} from "@/api/assistant";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const route = useRoute() as ReturnType<typeof useRoute> | undefined;
const input = ref("");
const conversations = ref<AssistantConversationSummary[]>([]);
const searchResults = ref<AssistantSearchResult[]>([]);
const searchQuery = ref("");
const historyLoading = ref(false);
const searchLoading = ref(false);
const historyVisible = ref(true);
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
const legacyImportMessages = ref<AssistantImportMessage[]>([]);
const legacyImporting = ref(false);
const LEGACY_MESSAGES_KEY = "smartcore-assistant-messages";

function newClientId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function dateLabel(value: string): string {
  return formatDateTime(value, locale.value === "en-US" ? "en-US" : "zh-CN");
}
function readLegacyMessages(): void {
  try {
    const raw = window.localStorage.getItem(LEGACY_MESSAGES_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return;
    legacyImportMessages.value = parsed
      .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
      .filter((item) => (item.role === "user" || item.role === "assistant") && typeof item.text === "string" && item.text.trim())
      .slice(-100)
      .map((item) => ({
        role: item.role as "user" | "assistant",
        text: String(item.text).trim(),
        messageId: typeof item.id === "string" ? item.id : undefined,
        createdAt: typeof item.createdAt === "string" ? item.createdAt : undefined,
      }));
  } catch {
    legacyImportMessages.value = [];
  }
}
async function importLegacyHistory(): Promise<void> {
  if (!legacyImportMessages.value.length || legacyImporting.value) return;
  legacyImporting.value = true;
  try {
    if (!activeConversationId.value) await startConversation();
    if (!activeConversationId.value) return;
    await assistantApi.importHistory(activeConversationId.value, legacyImportMessages.value);
    window.localStorage.removeItem(LEGACY_MESSAGES_KEY);
    legacyImportMessages.value = [];
    await loadConversation(activeConversationId.value);
    await refreshConversationList();
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    legacyImporting.value = false;
  }
}
function scrollToLatest(): void {
  void nextTick(() => {
    if (messagesRoot.value) messagesRoot.value.scrollTop = messagesRoot.value.scrollHeight;
  });
}
function scrollToMessage(messageId: string): void {
  void nextTick(() => document.getElementById(`assistant-message-${messageId}`)?.scrollIntoView({ block: "center", behavior: "smooth" }));
}
async function loadConversation(conversationId: string, messageId?: string): Promise<void> {
  historyLoading.value = true;
  error.value = "";
  try {
    const result = await assistantApi.read(conversationId);
    activeConversation.value = result;
    activeConversationId.value = result.conversationId;
    messages.value = result.messages;
    highlightMessageId.value = messageId ?? "";
    scrollToLatest();
    if (messageId) scrollToMessage(messageId);
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    historyLoading.value = false;
  }
}
async function loadConversations(): Promise<void> {
  historyLoading.value = true;
  try {
    const result = await assistantApi.list();
    conversations.value = result.items as AssistantConversationSummary[];
    if (activeConversationId.value && conversations.value.some((item) => item.conversationId === activeConversationId.value)) {
      await loadConversation(activeConversationId.value);
    } else if (conversations.value[0]) {
      await loadConversation(conversations.value[0].conversationId);
    } else {
      activeConversation.value = null;
      activeConversationId.value = "";
      messages.value = [];
      historyVisible.value = false;
    }
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    historyLoading.value = false;
  }
}
async function startConversation(): Promise<void> {
  try {
    const created = await assistantApi.create();
    conversations.value = [created, ...conversations.value.filter((item) => item.conversationId !== created.conversationId)];
    activeConversation.value = { ...created, messages: [] };
    activeConversationId.value = created.conversationId;
    messages.value = [];
    error.value = "";
    historyVisible.value = false;
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  }
}
async function runSearch(): Promise<void> {
  const query = searchQuery.value.trim();
  if (!query) {
    searchResults.value = [];
    return;
  }
  searchLoading.value = true;
  try {
    const result = await assistantApi.list(query);
    searchResults.value = result.items as AssistantSearchResult[];
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.searchError");
  } finally {
    searchLoading.value = false;
  }
}
function clearSearch(): void {
  searchQuery.value = "";
  searchResults.value = [];
}
async function openSearchResult(result: AssistantSearchResult): Promise<void> {
  await loadConversation(result.conversationId, result.messageId);
  historyVisible.value = false;
}
async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text || sending.value) return;
  if (!online.value) {
    error.value = t("assistant.offline");
    return;
  }
  if (!activeConversationId.value) await startConversation();
  if (!activeConversationId.value) return;
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
    await refreshConversationList();
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
async function refreshConversationList(): Promise<void> {
  try {
    const result = await assistantApi.list();
    conversations.value = result.items as AssistantConversationSummary[];
  } catch { /* The open conversation remains usable if the list refresh fails. */ }
}
function setQuickPrompt(value: string): void {
  input.value = value;
}
function onOnline(): void { online.value = true; }
function onOffline(): void { online.value = false; }

onMounted(() => {
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  input.value = String(route?.query?.prompt || "");
  readLegacyMessages();
  void loadConversations();
});
watch(() => route?.query?.prompt, (value) => {
  if (value) input.value = String(value);
});
onBeforeUnmount(() => {
  window.removeEventListener("online", onOnline);
  window.removeEventListener("offline", onOffline);
});
</script>

<template>
  <div class="assistant-page">
    <PageHeader :title="t('assistant.title')" :subtitle="t('assistant.subtitle')">
      <template #actions>
        <button class="button button--primary" type="button" @click="startConversation"><Plus :size="16" aria-hidden="true" />{{ t("assistant.newConversation") }}</button>
      </template>
    </PageHeader>
    <section v-if="legacyImportMessages.length" class="assistant-import card">
      <div><strong>{{ t("assistant.importTitle") }}</strong><p>{{ t("assistant.importHint", { count: legacyImportMessages.length }) }}</p></div>
      <button class="button button--ghost" type="button" :disabled="legacyImporting" @click="importLegacyHistory">{{ legacyImporting ? t("common.loading") : t("assistant.importAction") }}</button>
    </section>
    <section class="assistant-workspace">
      <aside class="assistant-history card" :class="{ 'assistant-history--mobile-visible': historyVisible }">
        <header class="assistant-history__header">
          <strong>{{ t("assistant.history") }}</strong>
          <button class="icon-button assistant-history__close" type="button" :aria-label="t('common.close')" @click="historyVisible = false"><X :size="16" aria-hidden="true" /></button>
        </header>
        <form class="assistant-search" @submit.prevent="runSearch">
          <Search :size="16" aria-hidden="true" />
          <input v-model="searchQuery" :placeholder="t('assistant.searchPlaceholder')" :aria-label="t('assistant.searchPlaceholder')" />
          <button v-if="searchQuery" class="assistant-search__clear" type="button" :aria-label="t('common.clear')" @click="clearSearch"><X :size="14" aria-hidden="true" /></button>
        </form>
        <div v-if="searchQuery" class="assistant-history__list">
          <button v-for="result in searchResults" :key="`${result.messageId}-${result.conversationId}`" class="assistant-search-result" type="button" @click="openSearchResult(result)">
            <span class="assistant-search-result__title">{{ result.title }}</span>
            <span class="assistant-search-result__snippet">{{ result.snippet }}</span>
            <time>{{ dateLabel(result.createdAt) }}</time>
          </button>
          <p v-if="searchLoading" class="assistant-history__empty">{{ t("common.loading") }}</p>
          <p v-else-if="!searchResults.length" class="assistant-history__empty">{{ t("assistant.noSearchResults") }}</p>
        </div>
        <div v-else class="assistant-history__list">
          <button v-for="conversation in conversations" :key="conversation.conversationId" class="assistant-conversation" :class="{ 'assistant-conversation--active': activeConversationId === conversation.conversationId }" type="button" @click="loadConversation(conversation.conversationId); historyVisible = false">
            <MessageCircle :size="17" aria-hidden="true" />
            <span><strong>{{ conversation.title }}</strong><small>{{ dateLabel(conversation.lastMessageAt || conversation.updatedAt) }}</small></span>
          </button>
          <p v-if="historyLoading" class="assistant-history__empty">{{ t("common.loading") }}</p>
          <p v-else-if="!conversations.length" class="assistant-history__empty">{{ t("assistant.noHistory") }}</p>
        </div>
      </aside>
      <section class="assistant-shell card">
        <header class="assistant-shell__header">
          <button class="icon-button assistant-history__open" type="button" :aria-label="t('assistant.openHistory')" @click="historyVisible = true"><ArrowLeft :size="17" aria-hidden="true" /></button>
          <div class="assistant-shell__title"><Bot :size="17" aria-hidden="true" /><strong>{{ activeConversation?.title || t("assistant.newConversation") }}</strong></div>
          <button v-if="activeConversationId" class="icon-button" type="button" :aria-label="t('assistant.archive')" @click="assistantApi.archive(activeConversationId).then(loadConversations)"><Archive :size="16" aria-hidden="true" /></button>
        </header>
        <div class="assistant-status" :class="{ 'assistant-status--offline': !online }">
          <WifiOff v-if="!online" :size="15" aria-hidden="true" />
          <Bot v-else :size="15" aria-hidden="true" />
          <span>{{ online ? (sending ? activity || t("assistant.thinking") : t("assistant.ready")) : t("assistant.offline") }}</span>
          <small v-if="activeTool">{{ activeTool }}</small>
        </div>
        <div ref="messagesRoot" class="assistant-messages" aria-live="polite">
          <div v-if="!messages.length && !historyLoading" class="assistant-empty">
            <Bot :size="30" aria-hidden="true" />
            <strong>{{ t("assistant.empty") }}</strong>
            <span>{{ t("assistant.examples") }}</span>
            <div class="assistant-quick-prompts">
              <button type="button" @click="setQuickPrompt(t('assistant.quickToday'))">{{ t("assistant.quickToday") }}</button>
              <button type="button" @click="setQuickPrompt(t('assistant.quickCapture'))">{{ t("assistant.quickCapture") }}</button>
              <button type="button" @click="setQuickPrompt(t('assistant.quickDeadline'))">{{ t("assistant.quickDeadline") }}</button>
            </div>
          </div>
          <article v-for="message in messages" :id="`assistant-message-${message.messageId}`" :key="message.messageId" class="assistant-message" :class="[`assistant-message--${message.role}`, { 'assistant-message--highlight': highlightMessageId === message.messageId, 'assistant-message--failed': message.stat === 'failed' }]">
            <span class="assistant-message__label">{{ message.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span>
            <p>{{ message.text || t("assistant.pending") }}</p>
            <time>{{ dateLabel(message.createdAt) }}</time>
          </article>
          <div v-if="sending" class="assistant-typing" role="status"><span class="assistant-typing__dot" />{{ activity || t("assistant.thinking") }}<small v-if="activeTool">{{ activeTool }}</small></div>
        </div>
        <p v-if="error" class="assistant-error" role="alert">{{ error }}</p>
        <form class="assistant-composer" @submit.prevent="send">
          <textarea v-model="input" :disabled="sending" :placeholder="t('assistant.placeholder')" rows="2" @keydown.enter.exact.prevent="send" />
          <button class="button button--primary assistant-send" type="submit" :disabled="sending || !input.trim()"><Send :size="16" aria-hidden="true" />{{ sending ? t("assistant.sending") : t("assistant.send") }}</button>
        </form>
      </section>
    </section>
  </div>
</template>

<style scoped>
.assistant-page{display:grid;gap:18px}.assistant-import{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:13px 16px;border-color:#bfdbfe;background:#eff6ff}.assistant-import p{margin:4px 0 0;color:#475569;font-size:13px}.assistant-workspace{display:grid;grid-template-columns:280px minmax(0,1fr);gap:16px;min-height:calc(100vh - 190px)}.assistant-history{display:flex;min-height:0;flex-direction:column}.assistant-history__header{display:flex;align-items:center;justify-content:space-between;padding:16px;border-bottom:1px solid var(--border-color)}.assistant-history__close,.assistant-history__open{display:none}.assistant-search{display:flex;align-items:center;gap:7px;margin:12px;padding:9px 10px;border:1px solid var(--border-color);border-radius:10px;background:var(--color-surface-muted)}.assistant-search input{min-width:0;flex:1;border:0;outline:0;background:transparent;font:inherit}.assistant-search__clear{display:grid;place-items:center;border:0;background:transparent;color:var(--color-text-muted)}.assistant-history__list{min-height:0;overflow-y:auto;padding:0 8px 10px}.assistant-conversation,.assistant-search-result{display:flex;width:100%;gap:10px;padding:11px 9px;border:0;border-radius:10px;background:transparent;color:var(--color-text);text-align:left;font:inherit}.assistant-conversation:hover,.assistant-conversation--active,.assistant-search-result:hover{background:var(--color-primary-soft)}.assistant-conversation span{display:grid;min-width:0;gap:4px}.assistant-conversation strong,.assistant-search-result__title{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.assistant-conversation small,.assistant-search-result time{color:var(--color-text-muted);font-size:11px}.assistant-search-result{display:grid;gap:5px}.assistant-search-result__snippet{display:-webkit-box;overflow:hidden;color:var(--color-text-muted);font-size:12px;-webkit-box-orient:vertical;-webkit-line-clamp:2}.assistant-history__empty{padding:22px 12px;color:var(--color-text-muted);font-size:13px;text-align:center}.assistant-shell{display:flex;min-height:calc(100vh - 190px);min-width:0;flex-direction:column}.assistant-shell__header{display:flex;align-items:center;gap:10px;padding:13px 16px;border-bottom:1px solid var(--border-color)}.assistant-shell__title{display:flex;align-items:center;gap:7px;min-width:0;flex:1}.assistant-shell__title strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.assistant-status{display:flex;align-items:center;gap:7px;padding:10px 16px;border-bottom:1px solid var(--border-color);color:#166534;font-size:13px}.assistant-status small{margin-left:auto;color:#2563eb}.assistant-status--offline{color:#9a3412;background:#fff7ed}.assistant-messages{display:grid;align-content:start;gap:14px;min-height:0;flex:1;padding:20px;overflow-y:auto;background:#f8fafc}.assistant-empty{display:grid;justify-items:center;gap:9px;margin:auto;color:var(--color-text-muted);text-align:center}.assistant-empty svg{color:var(--color-primary)}.assistant-empty span{max-width:360px;font-size:13px}.assistant-quick-prompts{display:flex;flex-wrap:wrap;justify-content:center;gap:7px;margin-top:6px}.assistant-quick-prompts button{padding:8px 10px;border:1px solid #bfdbfe;border-radius:999px;background:#eff6ff;color:#1d4ed8;font:inherit;font-size:12px}.assistant-message{position:relative;max-width:min(760px,88%);padding:12px 14px;border-radius:14px;background:#fff;box-shadow:0 3px 10px rgb(15 23 42 / 6%)}.assistant-message--user{justify-self:end;background:#2563eb;color:#fff}.assistant-message--highlight{outline:3px solid #93c5fd}.assistant-message--failed{border:1px solid #fecaca;background:#fff1f2;color:#991b1b}.assistant-message__label{display:block;margin-bottom:5px;color:#64748b;font-size:11px;font-weight:700}.assistant-message--user .assistant-message__label{color:#dbeafe}.assistant-message p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}.assistant-message time{display:block;margin-top:7px;color:#94a3b8;font-size:10px}.assistant-message--user time{color:#bfdbfe}.assistant-typing{display:flex;align-items:center;gap:8px;justify-self:start;color:var(--color-text-muted);font-size:13px}.assistant-typing small{color:#2563eb}.assistant-typing__dot{width:8px;height:8px;border-radius:50%;background:#2563eb;box-shadow:0 0 0 0 rgb(37 99 235 / 50%);animation:assistant-pulse 1.35s infinite}.assistant-error{margin:0;padding:10px 18px;color:#991b1b;background:#fff1f2;font-size:13px}.assistant-composer{display:flex;align-items:flex-end;gap:10px;padding:14px;border-top:1px solid var(--border-color);background:#fff}.assistant-composer textarea{min-height:44px;max-height:160px;flex:1;resize:vertical;padding:11px;border:1px solid var(--border-color);border-radius:10px;outline:0;font:inherit}.assistant-composer textarea:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgb(96 165 250 / 15%)}.assistant-send{display:inline-flex;align-items:center;gap:7px;min-height:44px}@keyframes assistant-pulse{70%{box-shadow:0 0 0 7px rgb(37 99 235 / 0)}}@media(max-width:760px){.assistant-workspace{display:block;min-height:calc(100vh - 150px)}.assistant-history{display:none}.assistant-history--mobile-visible{position:fixed;inset:0 18% 0 0;display:flex;z-index:40;border-radius:0;box-shadow:12px 0 28px rgb(15 23 42 / 18%)}.assistant-history__close,.assistant-history__open{display:grid}.assistant-shell{min-height:calc(100vh - 150px);margin:0 -2px;border-radius:12px}.assistant-messages{padding:14px}.assistant-message{max-width:94%}.assistant-composer{padding:10px;align-items:stretch;flex-direction:column}.assistant-send{justify-content:center}}
</style>
