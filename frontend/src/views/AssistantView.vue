<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Search, Send, WifiOff, X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { assistantApi } from "@/api/assistant";
import type {
  AssistantConversation,
  AssistantMessage,
  AssistantSearchResult,
  AssistantStreamEvent,
} from "@/api/assistant";
import MarkdownContent from "@/components/base/MarkdownContent.vue";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const route = useRoute() as ReturnType<typeof useRoute> | undefined;
const input = ref("");
const searchQuery = ref("");
const searchResults = ref<AssistantSearchResult[]>([]);
const searchOpen = ref(false);
const searchExpanded = ref(false);
const searchLoading = ref(false);
const loading = ref(true);
const activeConversationId = ref("");
const activeConversation = ref<AssistantConversation | null>(null);
const messages = ref<AssistantMessage[]>([]);
const sending = ref(false);
const error = ref("");
const activity = ref("");
const activeTool = ref("");
const streamingText = ref("");
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const messagesRoot = ref<HTMLElement | null>(null);
const composerRoot = ref<HTMLElement | null>(null);
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
function ensureComposerVisible(): void {
  void nextTick(() => {
    const node = composerRoot.value as (HTMLElement & { scrollIntoView?: (arg?: ScrollIntoViewOptions) => void }) | null;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "end", behavior: "auto" });
    }
  });
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
  searchExpanded.value = true;
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
function closeSearch(): void {
  clearSearch();
  searchExpanded.value = false;
}
function appendStreamingText(value: string, mode?: string): void {
  const next = value.trim();
  if (!next) return;
  const normalizedMode = (mode || "").trim().toLowerCase();
  const current = streamingText.value.trim();
  if (!current || normalizedMode === "new" || next.startsWith(current)) {
    streamingText.value = next;
  } else if (next === current || current.endsWith(next)) {
    return;
  } else {
    // Delta-style chunk without mode=new.
    streamingText.value = `${current}${next}`;
  }
  scrollToLatest();
}
async function openSearchResult(result: AssistantSearchResult): Promise<void> {
  closeSearch();
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
  ensureComposerVisible();
  sending.value = true;
  activity.value = t("assistant.starting");
  activeTool.value = "";
  streamingText.value = "";
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
          appendStreamingText(event.text, event.mode);
        }
        if (event.type === "done") {
          if (event.response?.trim()) appendStreamingText(event.response, "new");
          activity.value = t("assistant.done");
        }
      },
      clientMessageId,
    );
    activeConversationId.value = result.conversationId || result.sessionId || activeConversationId.value;
    await loadConversation(activeConversationId.value, undefined, true);
  } catch (requestError) {
    error.value = requestError instanceof Error && requestError.message ? requestError.message : t("assistant.error");
    await loadConversation(activeConversationId.value, undefined, true);
  } finally {
    sending.value = false;
    activity.value = "";
    activeTool.value = "";
    streamingText.value = "";
    scrollToLatest();
    ensureComposerVisible();
  }
}
function onOnline(): void { online.value = true; }
function onOffline(): void { online.value = false; }
function onVisibilityChange(): void { if (document.visibilityState === "visible") void syncConversation(); }
function onViewportResize(): void {
  if (sending.value) ensureComposerVisible();
}

onMounted(() => {
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  document.addEventListener("visibilitychange", onVisibilityChange);
  window.addEventListener("focus", syncConversation);
  window.visualViewport?.addEventListener("resize", onViewportResize);
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
  window.visualViewport?.removeEventListener("resize", onViewportResize);
  if (syncTimer) clearInterval(syncTimer);
  if (searchTimer) clearTimeout(searchTimer);
});
</script>

<template>
  <div class="assistant-page">
    <section class="assistant-shell card">
      <header class="assistant-shell__header">
        <button v-if="!searchExpanded" class="assistant-search-toggle" type="button" :aria-label="t('assistant.openSearch')" :title="t('assistant.openSearch')" @click="searchExpanded = true"><Search :size="17" aria-hidden="true" /></button>
        <form v-else class="assistant-search" role="search" @submit.prevent="runSearch">
          <Search :size="16" aria-hidden="true" />
          <input v-model="searchQuery" autofocus :placeholder="t('assistant.searchPlaceholder')" :aria-label="t('assistant.searchPlaceholder')" @input="scheduleSearch" @focus="searchOpen = Boolean(searchQuery)" />
          <button v-if="searchQuery" class="assistant-search__clear" type="button" :aria-label="t('common.clear')" @click="clearSearch"><X :size="14" aria-hidden="true" /></button>
          <button v-else class="assistant-search__close" type="button" :aria-label="t('assistant.closeSearch')" @click="closeSearch"><X :size="15" aria-hidden="true" /></button>
        </form>
      </header>
      <div v-if="searchOpen" class="assistant-search-results">
        <button v-for="result in searchResults" :key="`${result.messageId}-${result.conversationId}`" type="button" @click="openSearchResult(result)"><span>{{ result.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span><strong>{{ result.snippet }}</strong><time>{{ dateLabel(result.createdAt) }}</time></button>
        <p v-if="searchLoading" class="assistant-search-results__empty">{{ t("common.loading") }}</p>
        <p v-else-if="!searchResults.length" class="assistant-search-results__empty">{{ t("assistant.noSearchResults") }}</p>
      </div>
      <div ref="messagesRoot" class="assistant-messages" aria-live="polite">
        <div v-if="loading" class="assistant-loading" role="status"><span class="assistant-progress__spinner" aria-hidden="true" />{{ t("assistant.loading") }}</div>
        <div v-else-if="!messages.length && !sending" class="assistant-empty"><strong>{{ t("assistant.empty") }}</strong></div>
        <article
          v-for="message in messages"
          :id="`assistant-message-${message.messageId}`"
          :key="message.messageId"
          class="assistant-message"
          :class="[`assistant-message--${message.role}`, { 'assistant-message--highlight': highlightMessageId === message.messageId, 'assistant-message--failed': message.stat === 'failed', 'assistant-message--pending': message.stat === 'pending' }]"
        >
          <span class="assistant-message__label">{{ message.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span>
          <MarkdownContent v-if="message.role === 'assistant'" :content="message.text || t('assistant.pending')" />
          <p v-else>{{ message.text || t("assistant.pending") }}</p>
          <time>{{ dateLabel(message.createdAt) }}</time>
        </article>
        <article v-if="streamingText" class="assistant-message assistant-message--assistant assistant-message--streaming">
          <span class="assistant-message__label">{{ t("assistant.bot") }}</span>
          <MarkdownContent :content="streamingText" />
        </article>
        <div v-if="sending || !online" class="assistant-progress" :class="{ 'assistant-progress--offline': !online }" role="status" aria-live="polite">
          <span class="assistant-progress__spinner" aria-hidden="true"><WifiOff v-if="!online" :size="14" /></span>
          <span class="assistant-progress__text">{{ online ? (activity || activeTool || t("assistant.thinking")) : t("assistant.offline") }}</span>
        </div>
      </div>
      <p v-if="error" class="assistant-error" role="alert">{{ error }}</p>
      <form ref="composerRoot" class="assistant-composer" @submit.prevent="send">
        <textarea
          v-model="input"
          :disabled="loading"
          :placeholder="sending ? t('assistant.placeholderBusy') : t('assistant.placeholder')"
          rows="2"
          @keydown.enter.exact.prevent="send"
          @focus="ensureComposerVisible"
        />
        <button
          class="button button--primary assistant-send"
          type="submit"
          :aria-label="sending ? t('assistant.sending') : t('assistant.send')"
          :disabled="sending || loading || !input.trim()"
        >
          <Send :size="16" aria-hidden="true" />
          <span>{{ sending ? t("assistant.sending") : t("assistant.send") }}</span>
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.assistant-page {
  display: flex;
  flex-direction: column;
  min-height: calc(100dvh - 120px);
}
.assistant-search {
  display: flex;
  align-items: center;
  gap: 8px;
  width: min(420px, 100%);
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--color-surface-muted);
}
.assistant-search input {
  min-width: 0;
  flex: 1;
  border: 0;
  outline: 0;
  background: transparent;
  font: inherit;
}
.assistant-search-toggle,
.assistant-search__clear,
.assistant-search__close {
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--color-text-muted);
}
.assistant-search-toggle {
  width: 34px;
  height: 34px;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  background: #fff;
  box-shadow: 0 2px 8px rgb(15 23 42 / 8%);
}
.assistant-search-toggle:hover,
.assistant-search__clear:hover,
.assistant-search__close:hover {
  background: #eff6ff;
  color: #1d4ed8;
}
.assistant-search__clear,
.assistant-search__close {
  padding: 4px;
}
.assistant-shell {
  position: relative;
  display: flex;
  min-height: calc(100dvh - 160px);
  min-width: 0;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
}
.assistant-shell__header {
  position: absolute;
  z-index: 4;
  top: 12px;
  right: 16px;
  left: 16px;
  display: flex;
  align-items: center;
  min-height: 0;
  padding: 0;
  justify-content: flex-end;
  border: 0;
  pointer-events: none;
}
.assistant-shell__header > * {
  pointer-events: auto;
}
.assistant-search-results {
  position: absolute;
  z-index: 5;
  top: 58px;
  right: 18px;
  width: min(420px, calc(100% - 36px));
  padding: 7px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 30px rgb(15 23 42 / 14%);
}
.assistant-search-results button {
  display: grid;
  width: 100%;
  gap: 4px;
  padding: 9px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  font: inherit;
}
.assistant-search-results button:hover {
  background: #eff6ff;
}
.assistant-search-results button span,
.assistant-search-results button time {
  color: var(--color-text-muted);
  font-size: 11px;
}
.assistant-search-results button strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.assistant-search-results__empty {
  padding: 12px;
  color: var(--color-text-muted);
  font-size: 12px;
  text-align: center;
}
.assistant-messages {
  display: grid;
  align-content: start;
  gap: 14px;
  min-width: 0;
  min-height: 0;
  flex: 1;
  padding: 22px;
  overflow-x: hidden;
  overflow-y: auto;
  background: #f4f7fb;
  overscroll-behavior: contain;
}
.assistant-loading,
.assistant-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 56px;
  color: var(--color-text-muted);
  font-size: 13px;
}
.assistant-empty {
  padding: 42px 16px;
}
.assistant-progress {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  justify-self: start;
  min-width: 0;
  max-width: min(720px, 92%);
  margin: 2px 2px 0;
  padding: 0;
  border: 0;
  background: transparent;
  box-shadow: none;
  color: #64748b;
  font-size: 13px;
  line-height: 1.4;
}
.assistant-progress--offline {
  color: #c2410c;
}
.assistant-progress__spinner {
  display: grid;
  place-items: center;
  flex: 0 0 14px;
  width: 14px;
  height: 14px;
  border: 2px solid #cbd5e1;
  border-top-color: #64748b;
  border-radius: 50%;
  animation: assistant-spin .8s linear infinite;
}
.assistant-progress--offline .assistant-progress__spinner {
  border-color: #fdba74;
  border-top-color: #c2410c;
  animation: none;
}
.assistant-progress__text {
  min-width: 0;
  overflow-wrap: anywhere;
}
.assistant-message {
  position: relative;
  min-width: 0;
  max-width: min(720px, 88%);
  padding: 14px 16px;
  border: 1px solid #e8eef5;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 1px 2px rgb(15 23 42 / 4%);
}
.assistant-message--user {
  justify-self: end;
  border-color: transparent;
  background: #2563eb;
  color: #fff;
  box-shadow: none;
}
.assistant-message--assistant {
  justify-self: start;
}
.assistant-message--highlight {
  outline: 3px solid #93c5fd;
}
.assistant-message--failed {
  border: 1px solid #fecaca;
  background: #fff1f2;
  color: #991b1b;
}
.assistant-message--pending {
  border-color: #dbeafe;
}
.assistant-message--streaming {
  border-color: #e8eef5;
}
.assistant-message__label {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}
.assistant-message--user .assistant-message__label {
  color: #dbeafe;
}
.assistant-message p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.65;
}
.assistant-message :deep(.markdown-content) {
  color: inherit;
  font-size: 15px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.assistant-message :deep(.markdown-content p) {
  margin: 0 0 0.7em;
  white-space: normal;
}
.assistant-message :deep(.markdown-content p:last-child) {
  margin-bottom: 0;
}
.assistant-message :deep(.markdown-content h1),
.assistant-message :deep(.markdown-content h2),
.assistant-message :deep(.markdown-content h3) {
  margin: 0.9em 0 0.4em;
  line-height: 1.35;
  font-weight: 700;
}
.assistant-message :deep(.markdown-content h1:first-child),
.assistant-message :deep(.markdown-content h2:first-child),
.assistant-message :deep(.markdown-content h3:first-child) {
  margin-top: 0;
}
.assistant-message :deep(.markdown-content ul) {
  margin: 0.35em 0 0.7em;
  padding-left: 1.25em;
}
.assistant-message :deep(.markdown-content li) {
  margin: 0.2em 0;
}
.assistant-message :deep(.markdown-content pre) {
  margin: 0.55em 0;
  border-radius: 12px;
}
.assistant-message :deep(.markdown-content code) {
  font-size: 0.92em;
}
.assistant-message :deep(.markdown-content a) {
  color: #1d4ed8;
}
.assistant-message time {
  display: block;
  margin-top: 8px;
  color: #94a3b8;
  font-size: 10px;
}
.assistant-message--user time {
  color: #bfdbfe;
}
.assistant-error {
  margin: 0;
  padding: 10px 18px;
  color: #991b1b;
  background: #fff1f2;
  font-size: 13px;
}
.assistant-composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  flex: 0 0 auto;
  padding: 14px;
  border-top: 1px solid var(--border-color);
  background: #fff;
}
.assistant-composer textarea {
  min-width: 0;
  min-height: 44px;
  max-height: 160px;
  flex: 1;
  resize: vertical;
  padding: 11px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  outline: 0;
  font: inherit;
  background: #fff;
}
.assistant-composer textarea:focus {
  border-color: #60a5fa;
  box-shadow: 0 0 0 3px rgb(96 165 250 / 15%);
}
.assistant-composer textarea:disabled {
  opacity: 0.72;
  background: #f8fafc;
}
.assistant-send {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 44px;
}
@keyframes assistant-spin {
  to { transform: rotate(360deg); }
}
}
@media (max-width: 760px) {
  .assistant-page {
    height: calc(100dvh - 56px);
    max-height: calc(100dvh - 56px);
    min-height: 0;
    margin: -18px -14px -24px;
    overflow: hidden;
  }
  .assistant-shell {
    height: 100%;
    max-height: 100%;
    min-height: 0;
    border: 0;
    border-radius: 0;
    box-shadow: none;
    overflow: hidden;
  }
  .assistant-shell__header {
    top: 8px;
    right: 10px;
    left: 10px;
  }
  .assistant-search {
    min-width: 0;
    width: 100%;
    padding: 6px 8px;
    border-radius: 9px;
    font-size: 13px;
  }
  .assistant-messages {
    padding: 12px 12px 16px;
    gap: 10px;
    -webkit-overflow-scrolling: touch;
  }
  .assistant-message {
    max-width: 94%;
    padding: 12px 13px;
    border-radius: 16px;
  }
  .assistant-message__label,
  .assistant-message time {
    display: none;
  }
  .assistant-message :deep(.markdown-content) {
    font-size: 15px;
  }
  .assistant-progress {
    max-width: 94%;
    margin-left: 2px;
    font-size: 12px;
  }
  .assistant-composer {
    position: sticky;
    bottom: 0;
    z-index: 6;
    padding: 8px 10px calc(8px + env(safe-area-inset-bottom));
    gap: 8px;
    background: rgb(255 255 255 / 96%);
    backdrop-filter: blur(10px);
  }
  .assistant-composer textarea {
    min-height: 44px;
    max-height: 120px;
    resize: none;
  }
  .assistant-send {
    width: 46px;
    min-width: 46px;
    height: 46px;
    padding: 0;
    justify-content: center;
  }
  .assistant-send span {
    display: none;
  }
  .assistant-search-results {
    top: 52px;
    right: 10px;
    width: calc(100% - 20px);
  }
}
</style>
