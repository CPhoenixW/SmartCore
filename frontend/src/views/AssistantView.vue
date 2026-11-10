<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { Bell, Bot, Copy, FileText, Plus, Quote, Search, Send, Square, WifiOff, X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import { useRoute } from "vue-router";
import { assistantApi } from "@/api/assistant";
import type {
  AssistantConversation,
  AssistantAttachment,
  AssistantMessage,
  AssistantSearchResult,
  AssistantStreamEvent,
} from "@/api/assistant";
import MarkdownContent from "@/components/base/MarkdownContent.vue";
import { formatDateTime } from "@/utils/date";

const { t, locale } = useI18n();
const route = useRoute() as ReturnType<typeof useRoute> | undefined;
const queryClient = useQueryClient();
const input = ref("");
const pendingAttachments = ref<AssistantAttachment[]>([]);
const quotedMessage = ref<{ messageId: string; text: string; role: "user" | "assistant" } | null>(null);
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
const stopping = ref(false);
type ComposerDraft = {
  text: string;
  attachments: AssistantAttachment[];
  quote: { messageId: string; text: string; role: "user" | "assistant" } | null;
};
const queuedDrafts = ref<ComposerDraft[]>([]);
const hasComposerContent = computed(() => Boolean(input.value.trim() || pendingAttachments.value.length));
const error = ref("");
const activity = ref("");
const activeTool = ref("");
const streamingText = ref("");
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const messagesRoot = ref<HTMLElement | null>(null);
const messagesContent = ref<HTMLElement | null>(null);
const composerRoot = ref<HTMLElement | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const highlightMessageId = ref("");
const INITIAL_HISTORY_MESSAGES = 40;
const HISTORY_PAGE_SIZE = 40;
const historyVisibleCount = ref(INITIAL_HISTORY_MESSAGES);
const loadingEarlierMessages = ref(false);
const historyInitialized = ref(false);
const historyExpanded = ref(false);
let syncTimer: ReturnType<typeof setInterval> | undefined;
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let activeAbortController: AbortController | null = null;
let followLatest = true;
let latestScrollFrame: number | undefined;
let messagesResizeObserver: ResizeObserver | undefined;
const ASSISTANT_CACHE_KEY = "smartcore:assistant:primary:v2";

function newClientId(): string {
  return typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function dateLabel(value: string): string {
  return formatDateTime(value, locale.value === "en-US" ? "en-US" : "zh-CN");
}
const visibleMessages = computed(() => messages.value.slice(Math.max(0, messages.value.length - historyVisibleCount.value)));
const earlierMessageCount = computed(() => Math.max(0, messages.value.length - historyVisibleCount.value));
const hasEarlierMessages = computed(() => earlierMessageCount.value > 0);
function scrollToLatest(): void {
  followLatest = true;
  void nextTick(() => {
    const node = messagesRoot.value;
    if (!node || !followLatest) return;
    node.scrollTop = node.scrollHeight;
    if (typeof requestAnimationFrame === "function") {
      if (latestScrollFrame !== undefined) cancelAnimationFrame(latestScrollFrame);
      latestScrollFrame = requestAnimationFrame(() => {
        latestScrollFrame = undefined;
        if (followLatest) node.scrollTop = node.scrollHeight;
      });
    }
  });
}
function scrollToMessage(messageId: string): void {
  const index = messages.value.findIndex((message) => message.messageId === messageId);
  if (index < 0) return;
  followLatest = false;
  historyVisibleCount.value = Math.max(historyVisibleCount.value, messages.value.length - index);
  historyExpanded.value = true;
  highlightMessageId.value = messageId;
  void nextTick(() => {
    const node = messagesRoot.value;
    const target = Array.from(node?.querySelectorAll<HTMLElement>(".assistant-message") ?? [])
      .find((message) => message.id === `assistant-message-${messageId}`);
    if (!node || !target) return;
    const targetBounds = target.getBoundingClientRect();
    node.scrollTop += targetBounds.top - node.getBoundingClientRect().top - (node.clientHeight - targetBounds.height) / 2;
  });
}
function followResizedMessages(): void {
  if (followLatest) scrollToLatest();
}
function isReportMessage(message: AssistantMessage): boolean {
  return message.role === "assistant" && /(每日工作汇报|每日总结|工作汇报|daily summary)/i.test(message.text);
}
type ReminderCard = {
  title: string;
  targetLabel: string;
  relativeLabel: string;
  detail: string;
  phaseLabel: string;
};

function localDateKey(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function reminderTargetLabel(target: Date): string {
  const now = new Date();
  const today = localDateKey(now);
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const targetKey = localDateKey(target);
  const day = targetKey === today
    ? t("assistant.reminderToday")
    : targetKey === localDateKey(tomorrow)
      ? t("assistant.reminderTomorrow")
      : new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", { month: "numeric", day: "numeric" }).format(target);
  const clock = new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(target);
  return `${day} ${clock}`;
}

function reminderRelativeLabel(target: Date): string {
  const delta = target.getTime() - Date.now();
  if (delta < -60_000) return t("assistant.reminderStarted");
  if (delta < 60_000) return t("assistant.reminderInMinute");
  const minutes = Math.max(1, Math.ceil(delta / 60_000));
  if (minutes < 60) return t("assistant.reminderInMinutes", { count: minutes });
  return t("assistant.reminderInHours", { count: Math.ceil(minutes / 60) });
}

function reminderCard(message: AssistantMessage): ReminderCard | null {
  if (message.role !== "assistant") return null;
  const text = message.text.trim();
  if (!text || (!/^🔔/.test(text) && !/(?:计划将在|plan (?:starts|ends)|starts in|ends in)/i.test(text))) return null;
  const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
  const title = (lines.shift() || t("assistant.reminderTitle")).replace(/^🔔\s*/, "").trim();
  const body = lines.join(" ");
  const iso = body.match(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?/i)?.[0];
  let target: Date | null = iso ? new Date(iso) : null;
  if (!target || Number.isNaN(target.getTime())) {
    const clock = body.match(/(?:今天|明天|today|tomorrow)?\s*(\d{1,2}):(\d{2})/i);
    if (clock) {
      target = new Date();
      target.setHours(Number(clock[1]), Number(clock[2]), 0, 0);
      if (/明天|tomorrow/i.test(clock[0] || "")) target.setDate(target.getDate() + 1);
    }
  }
  const ending = /(结束|ends?|end)/i.test(body);
  const normalizedDetail = body
    .replace(iso || "", "")
    .replace(/计划将在\s*10\s*分钟后(?:开始|结束)\s*[：:]?/i, "")
    .replace(/the plan\s+(?:starts|ends)\s+in\s+10\s+minutes\s*[：:]?/i, "")
    .trim();
  const detail = target && !Number.isNaN(target.getTime()) ? "" : normalizedDetail;
  return {
    title,
    targetLabel: target && !Number.isNaN(target.getTime()) ? reminderTargetLabel(target) : t("assistant.reminderScheduled"),
    relativeLabel: target && !Number.isNaN(target.getTime()) ? reminderRelativeLabel(target) : (body.match(/(?:还有\s*[^，。]+|in\s+[^,.]+)/i)?.[0] || t("assistant.reminderPending")),
    detail,
    phaseLabel: ending ? t("assistant.reminderEnd") : t("assistant.reminderStart"),
  };
}

const reminderCards = computed(() => new Map(messages.value.map((message) => [message.messageId, reminderCard(message)])));
function messageDayKey(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : localDateKey(date);
}

function shouldShowDateDivider(index: number): boolean {
  if (index === 0) return true;
  const current = visibleMessages.value[index];
  const previous = visibleMessages.value[index - 1];
  return Boolean(current && previous && messageDayKey(current.createdAt) !== messageDayKey(previous.createdAt));
}

function dateDividerLabel(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const now = new Date();
  const today = localDateKey(now);
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const key = localDateKey(date);
  if (key === today) return t("assistant.dateToday");
  if (key === localDateKey(yesterday)) return t("assistant.dateYesterday");
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", {
    month: "numeric",
    day: "numeric",
    weekday: "short",
  }).format(date);
}
function attachmentUrl(attachment: AssistantAttachment): string {
  return attachment.url || assistantApi.attachmentUrl(attachment.uploadId);
}
function attachmentLabel(attachment: AssistantAttachment): string {
  return attachment.fileName || (attachment.mimeType.startsWith("image/") ? "图片" : "附件");
}
function formatAttachmentSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / 1024 / 1024).toFixed(1)} MB`;
}
function quoteMessage(message: AssistantMessage): void {
  const text = message.text.trim();
  if (!text) return;
  quotedMessage.value = { messageId: message.messageId, text: text.slice(0, 300), role: message.role };
  ensureComposerVisible();
}
function clearQuote(): void { quotedMessage.value = null; }
async function copyMessage(message: AssistantMessage): Promise<void> {
  if (!navigator.clipboard) return;
  await navigator.clipboard.writeText(message.text);
}
function openFilePicker(): void { fileInput.value?.click(); }
async function addAttachments(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files || []);
  target.value = "";
  if (!files.length) return;
  if (pendingAttachments.value.length + files.length > 10) {
    error.value = "一条消息最多附加 10 个文件";
    return;
  }
  try {
    const added = await assistantApi.uploadAttachments(files);
    pendingAttachments.value.push(...added);
    error.value = "";
    ensureComposerVisible();
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : "附件上传失败";
  }
}
async function removeAttachment(attachment: AssistantAttachment): Promise<void> {
  pendingAttachments.value = pendingAttachments.value.filter((item) => item.uploadId !== attachment.uploadId);
  try { await assistantApi.removeAttachment(attachment.uploadId); } catch { /* cleanup will remove abandoned uploads */ }
}
function persistConversation(conversation: AssistantConversation | null = activeConversation.value): void {
  if (typeof window === "undefined" || !conversation?.conversationId) return;
  const cached = {
    ...conversation,
    conversationId: conversation.conversationId,
    messages: messages.value.slice(-80),
  };
  try { window.localStorage.setItem(ASSISTANT_CACHE_KEY, JSON.stringify(cached)); } catch {}
}
function replaceMessages(next: AssistantMessage[], resetHistory = false): void {
  const firstVisibleId = visibleMessages.value[0]?.messageId;
  messages.value = next;
  if (resetHistory || !historyInitialized.value) {
    historyVisibleCount.value = Math.min(INITIAL_HISTORY_MESSAGES, next.length);
    historyExpanded.value = false;
  } else if (historyExpanded.value || !followLatest) {
    const firstVisibleIndex = next.findIndex((message) => message.messageId === firstVisibleId);
    historyVisibleCount.value = firstVisibleIndex < 0
      ? Math.min(next.length, Math.max(INITIAL_HISTORY_MESSAGES, historyVisibleCount.value))
      : next.length - firstVisibleIndex;
  } else {
    historyVisibleCount.value = Math.min(INITIAL_HISTORY_MESSAGES, next.length);
  }
  historyInitialized.value = true;
}
function appendMessage(message: AssistantMessage): void {
  const wasFullyVisible = historyVisibleCount.value >= messages.value.length;
  messages.value.push(message);
  if (wasFullyVisible) historyVisibleCount.value = messages.value.length;
}
function restoreCachedConversation(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(ASSISTANT_CACHE_KEY);
    if (!raw) return false;
    const cached = JSON.parse(raw) as AssistantConversation;
    if (!cached?.conversationId || !Array.isArray(cached.messages)) return false;
    activeConversation.value = cached;
    activeConversationId.value = cached.conversationId;
    replaceMessages(cached.messages, true);
    loading.value = false;
    scrollToLatest();
    return true;
  } catch { return false; }
}
function ensureComposerVisible(): void {
  void nextTick(() => {
    const node = composerRoot.value as (HTMLElement & { scrollIntoView?: (arg?: ScrollIntoViewOptions) => void }) | null;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ block: "end", behavior: "auto" });
    }
  });
}
async function loadEarlierMessages(): Promise<void> {
  if (loadingEarlierMessages.value || !hasEarlierMessages.value) return;
  const node = messagesRoot.value;
  const previousHeight = node?.scrollHeight ?? 0;
  const previousTop = node?.scrollTop ?? 0;
  followLatest = false;
  loadingEarlierMessages.value = true;
  historyExpanded.value = true;
  historyVisibleCount.value = Math.min(messages.value.length, historyVisibleCount.value + HISTORY_PAGE_SIZE);
  await nextTick();
  if (node) node.scrollTop = previousTop + node.scrollHeight - previousHeight;
  loadingEarlierMessages.value = false;
}
function handleMessagesScroll(): void {
  const node = messagesRoot.value;
  if (!node) return;
  followLatest = node.scrollHeight - node.clientHeight - node.scrollTop <= 48;
  if (node.scrollTop > 40 || loading.value || loadingEarlierMessages.value || !hasEarlierMessages.value) return;
  void loadEarlierMessages();
}
async function loadConversation(conversationId: string, messageId?: string, silent = false): Promise<void> {
  if (!silent) loading.value = true;
  try {
    const result = await assistantApi.read(conversationId);
    activeConversation.value = result;
    activeConversationId.value = result.conversationId;
    replaceMessages(result.messages);
    persistConversation(result);
    highlightMessageId.value = messageId ?? "";
    if (messageId) scrollToMessage(messageId);
    else if (followLatest) scrollToLatest();
  } catch (requestError) {
    if (!silent) error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    if (!silent) loading.value = false;
  }
}
async function loadPrimaryConversation(): Promise<void> {
  const restored = restoreCachedConversation();
  if (!restored) loading.value = true;
  error.value = "";
  try {
    const result = await assistantApi.list();
    const primary = result.items[0] as AssistantConversation | undefined;
    if (!primary) throw new Error(t("assistant.historyError"));
    await loadConversation(primary.conversationId, String(route?.query?.messageId || "") || undefined, restored);
  } catch (requestError) {
    error.value = requestError instanceof Error ? requestError.message : t("assistant.historyError");
  } finally {
    if (!restored) loading.value = false;
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
  if (followLatest) scrollToLatest();
}
async function openSearchResult(result: AssistantSearchResult): Promise<void> {
  closeSearch();
  if (result.conversationId !== activeConversationId.value) await loadPrimaryConversation();
  highlightMessageId.value = result.messageId;
  scrollToMessage(result.messageId);
}
async function stopGeneration(): Promise<void> {
  if (!sending.value || stopping.value || !activeAbortController) return;
  stopping.value = true;
  activeAbortController.abort();
}

function readComposerDraft(): ComposerDraft | null {
  const text = input.value.trim() || (pendingAttachments.value.length ? t("assistant.attachmentPrompt") : "");
  if (!text) return null;
  return {
    text,
    attachments: pendingAttachments.value.slice(),
    quote: quotedMessage.value,
  };
}

function clearComposerDraft(): void {
  input.value = "";
  pendingAttachments.value = [];
  quotedMessage.value = null;
}

async function send(): Promise<void> {
  const draft = readComposerDraft();
  if (!draft) return;
  if (!online.value) {
    error.value = t("assistant.offline");
    return;
  }
  if (sending.value) {
    queuedDrafts.value.push(draft);
    clearComposerDraft();
    error.value = "";
    activity.value = t("assistant.queued", { count: queuedDrafts.value.length });
    ensureComposerVisible();
    return;
  }
  clearComposerDraft();
  await runSend(draft);
}

async function runSend(draft: ComposerDraft): Promise<void> {
  if (!activeConversationId.value) {
    await loadPrimaryConversation();
    if (!activeConversationId.value) return;
  }
  error.value = "";
  const outgoingAttachments = draft.attachments;
  const outgoingQuote = draft.quote;
  const text = draft.text;
  const clientMessageId = newClientId();
  const optimistic: AssistantMessage = {
    messageId: "local-" + clientMessageId,
    conversationId: activeConversationId.value,
    role: "user",
    text,
    replyToMessageId: outgoingQuote?.messageId,
    replyToText: outgoingQuote?.text,
    attachments: outgoingAttachments,
    stat: "complete",
    createdAt: new Date().toISOString(),
  };
  appendMessage(optimistic);
  persistConversation();
  scrollToLatest();
  ensureComposerVisible();
  sending.value = true;
  stopping.value = false;
  activity.value = t("assistant.starting");
  activeTool.value = "";
  streamingText.value = "";
  const abortController = new AbortController();
  activeAbortController = abortController;
  try {
    const onEvent = (event: AssistantStreamEvent) => {
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
      };
    const streamOptions = {
      attachmentIds: outgoingAttachments.map((item) => item.uploadId),
      replyToMessageId: outgoingQuote?.messageId,
      signal: abortController.signal,
    };
    const result = await assistantApi.stream(text, activeConversationId.value, onEvent, clientMessageId, streamOptions);
    activeConversationId.value = result.conversationId || result.sessionId || activeConversationId.value;
    await loadConversation(activeConversationId.value, undefined, true);
  } catch (requestError) {
    const aborted = abortController.signal.aborted
      || (typeof DOMException !== "undefined" && requestError instanceof DOMException && requestError.name === "AbortError");
    if (!aborted) {
      error.value = requestError instanceof Error && requestError.message ? requestError.message : t("assistant.error");
    } else {
      error.value = "";
      activity.value = t("assistant.stopped");
      // Let the server finalize the partial stream before reloading history.
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    await loadConversation(activeConversationId.value, undefined, true);
  } finally {
    // Mark tool-owned views stale even after a stop; never delay the composer or queue on their network requests.
    void Promise.allSettled(["overview", "events", "schedule", "ideas", "notifications"].map(
      (key) => queryClient.invalidateQueries({ queryKey: [key], refetchType: "none" }),
    ));
    if (activeAbortController === abortController) activeAbortController = null;
    stopping.value = false;
    activity.value = "";
    activeTool.value = "";
    streamingText.value = "";
    const nextDraft = queuedDrafts.value.shift();
    if (nextDraft) {
      await runSend(nextDraft);
    } else {
      sending.value = false;
    }
    if (followLatest) scrollToLatest();
    ensureComposerVisible();
  }
}
function onOnline(): void { online.value = true; }
function onOffline(): void { online.value = false; }
function onVisibilityChange(): void { if (document.visibilityState === "visible") void syncConversation(); }
function onViewportResize(): void {
  followResizedMessages();
  if (sending.value) ensureComposerVisible();
}

onMounted(() => {
  if (typeof ResizeObserver !== "undefined") {
    messagesResizeObserver = new ResizeObserver(followResizedMessages);
    if (messagesContent.value) messagesResizeObserver.observe(messagesContent.value);
    if (messagesRoot.value) messagesResizeObserver.observe(messagesRoot.value);
  }
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
watch(() => route?.query?.messageId, (value) => {
  if (value) scrollToMessage(String(value));
});
onBeforeUnmount(() => {
  messagesResizeObserver?.disconnect();
  if (latestScrollFrame !== undefined) cancelAnimationFrame(latestScrollFrame);
  activeAbortController?.abort();
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
        <div class="assistant-identity">
          <span class="assistant-identity__avatar" aria-hidden="true"><Bot :size="18" :stroke-width="2" /></span>
          <span class="assistant-identity__copy"><strong>{{ t("assistant.title") }}</strong><small>{{ t("assistant.ready") }}</small></span>
        </div>
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
      <div ref="messagesRoot" class="assistant-messages" aria-live="polite" @scroll="handleMessagesScroll">
        <div ref="messagesContent" class="assistant-messages__content" @load.capture="followResizedMessages">
        <div v-if="loading" class="assistant-loading" role="status"><span class="assistant-progress__spinner" aria-hidden="true" />{{ t("assistant.loading") }}</div>
        <div v-else-if="!messages.length && !sending" class="assistant-empty"><strong>{{ t("assistant.empty") }}</strong></div>
        <button
          v-if="hasEarlierMessages"
          class="assistant-history-load"
          type="button"
          :aria-label="t('assistant.historyLoadEarlier', { count: earlierMessageCount })"
          :disabled="loadingEarlierMessages"
          @click="loadEarlierMessages"
        >
          <span>{{ loadingEarlierMessages ? t("assistant.historyLoading") : t("assistant.historyLoadEarlier", { count: earlierMessageCount }) }}</span>
        </button>
        <template v-for="(message, index) in visibleMessages" :key="message.messageId">
          <div v-if="shouldShowDateDivider(index)" class="assistant-date-divider"><span>{{ dateDividerLabel(message.createdAt) }}</span></div>
          <article
            :id="`assistant-message-${message.messageId}`"
            class="assistant-message"
            :class="[`assistant-message--${message.role}`, { 'assistant-message--report': isReportMessage(message), 'assistant-message--reminder': Boolean(reminderCards.get(message.messageId)), 'assistant-message--highlight': highlightMessageId === message.messageId, 'assistant-message--failed': message.stat === 'failed', 'assistant-message--pending': message.stat === 'pending' }]"
          >
          <header class="assistant-message__header">
            <div class="assistant-message__identity">
              <span class="assistant-message__label">{{ message.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span>
              <span v-if="isReportMessage(message)" class="assistant-message__kind"><FileText :size="13" aria-hidden="true" />{{ t("assistant.dailyReport") }}</span>
            </div>
            <div class="assistant-message__meta">
              <time>{{ dateLabel(message.createdAt) }}</time>
              <button class="assistant-message__action" type="button" :title="t('assistant.quote')" :aria-label="t('assistant.quote')" @click.stop="quoteMessage(message)"><Quote :size="14" aria-hidden="true" /></button>
              <button class="assistant-message__action" type="button" :title="t('assistant.copy')" :aria-label="t('assistant.copy')" @click.stop="copyMessage(message)"><Copy :size="14" aria-hidden="true" /></button>
            </div>
          </header>
          <div v-if="message.replyToText" class="assistant-message__quote" @click="message.replyToMessageId && scrollToMessage(message.replyToMessageId)">
            <span>{{ t("assistant.quotedMessage") }}</span>
            <p>{{ message.replyToText }}</p>
          </div>
          <div class="assistant-message__body">
            <div v-if="reminderCards.get(message.messageId)" class="assistant-reminder-card">
              <div class="assistant-reminder-card__top">
                <span class="assistant-reminder-card__icon" aria-hidden="true"><Bell :size="17" /></span>
                <div class="assistant-reminder-card__main"><strong>{{ reminderCards.get(message.messageId)?.title }}</strong><small>{{ reminderCards.get(message.messageId)?.phaseLabel }}</small></div>
                <span class="assistant-reminder-card__relative">{{ reminderCards.get(message.messageId)?.relativeLabel }}</span>
              </div>
              <div class="assistant-reminder-card__time"><time>{{ reminderCards.get(message.messageId)?.targetLabel }}</time><span aria-hidden="true">·</span><span>{{ reminderCards.get(message.messageId)?.relativeLabel }}</span></div>
              <p v-if="reminderCards.get(message.messageId)?.detail" class="assistant-reminder-card__detail">{{ reminderCards.get(message.messageId)?.detail }}</p>
            </div>
            <MarkdownContent v-else-if="message.role === 'assistant'" :content="message.text || t('assistant.pending')" />
            <p v-else>{{ message.text || t("assistant.pending") }}</p>
          </div>
          <div v-if="message.attachments?.length" class="assistant-attachments" :aria-label="t('assistant.attachments')">
            <a v-for="attachment in message.attachments" :key="attachment.uploadId" class="assistant-attachment" :href="attachmentUrl(attachment)" target="_blank" rel="noopener noreferrer">
              <img v-if="attachment.mimeType.startsWith('image/')" :src="attachmentUrl(attachment)" :alt="attachmentLabel(attachment)" />
              <FileText v-else :size="20" aria-hidden="true" />
              <span><strong>{{ attachmentLabel(attachment) }}</strong><small>{{ formatAttachmentSize(attachment.sizeBytes) }}</small></span>
            </a>
          </div>
          </article>
        </template>
        <article v-if="streamingText" class="assistant-message assistant-message--assistant assistant-message--streaming">
          <header class="assistant-message__header"><span class="assistant-message__label">{{ t("assistant.bot") }}</span></header>
          <div class="assistant-message__body"><MarkdownContent :content="streamingText" /></div>
        </article>
        <div v-if="sending || !online" class="assistant-progress" :class="{ 'assistant-progress--offline': !online }" role="status" aria-live="polite">
          <span class="assistant-progress__spinner" aria-hidden="true"><WifiOff v-if="!online" :size="14" /></span>
          <span class="assistant-progress__text">{{ online ? (activity || activeTool || t("assistant.thinking")) : t("assistant.offline") }}</span>
        </div>
        </div>
      </div>
      <p v-if="error" class="assistant-error" role="alert">{{ error }}</p>
      <form ref="composerRoot" class="assistant-composer" @submit.prevent="send">
        <div v-if="quotedMessage" class="assistant-quote-preview">
          <Quote :size="14" aria-hidden="true" />
          <span><strong>{{ t("assistant.quotedMessage") }}</strong>{{ quotedMessage.text }}</span>
          <button type="button" class="assistant-composer__clear" :aria-label="t('common.close')" @click="clearQuote"><X :size="15" aria-hidden="true" /></button>
        </div>
        <div v-if="pendingAttachments.length" class="assistant-attachment-strip">
          <span v-for="attachment in pendingAttachments" :key="attachment.uploadId" class="assistant-attachment-chip">
            <img v-if="attachment.mimeType.startsWith('image/')" :src="attachmentUrl(attachment)" :alt="attachmentLabel(attachment)" />
            <FileText v-else :size="15" aria-hidden="true" />
            <span>{{ attachmentLabel(attachment) }}</span>
            <button type="button" :aria-label="`${t('common.delete')} ${attachmentLabel(attachment)}`" @click="removeAttachment(attachment)"><X :size="13" aria-hidden="true" /></button>
          </span>
        </div>
        <div class="assistant-composer__row">
          <button class="assistant-attach" type="button" :aria-label="t('assistant.addAttachment')" :title="t('assistant.addAttachment')" :disabled="sending || loading" @click="openFilePicker"><Plus :size="19" :stroke-width="2.2" aria-hidden="true" /></button>
          <input ref="fileInput" class="assistant-file-input" type="file" multiple accept="image/*,.pdf,.txt,.md,.csv,.docx,.zip" @change="addAttachments" />
        <textarea
          v-model="input"
          :disabled="loading"
          :placeholder="sending ? t('assistant.placeholderBusy') : t('assistant.placeholder')"
          rows="1"
          @keydown.enter.exact.prevent="send"
          @focus="ensureComposerVisible"
        />
        <button
          v-if="sending && !hasComposerContent"
          class="button assistant-send assistant-stop"
          type="button"
          :aria-label="stopping ? t('assistant.stopping') : t('assistant.stop')"
          :title="stopping ? t('assistant.stopping') : t('assistant.stop')"
          :disabled="stopping"
          @click="stopGeneration"
        >
          <Square :size="15" :stroke-width="2.4" fill="currentColor" aria-hidden="true" />
        </button>
        <button
          v-else
          class="button button--primary assistant-send"
          type="submit"
          :aria-label="t('assistant.send')"
          :disabled="loading || stopping || !hasComposerContent"
        >
          <Send :size="16" aria-hidden="true" />
          <span>{{ t("assistant.send") }}</span>
        </button>
        </div>
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
  align-items: stretch;
  gap: 10px;
  flex: 0 0 auto;
  padding: 14px;
  border-top: 1px solid var(--border-color);
  background: #fff;
}
.assistant-composer textarea {
  box-sizing: border-box;
  min-width: 0;
  height: 46px;
  min-height: 46px;
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
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 46px;
  min-height: 46px;
  align-self: stretch;
}
@keyframes assistant-spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 760px) {
  .assistant-page {
    height: calc(100dvh - 56px - var(--mobile-tabbar-height, 0px));
    max-height: calc(100dvh - 56px - var(--mobile-tabbar-height, 0px));
    min-height: 0;
    margin: -18px -14px calc(-24px - var(--mobile-tabbar-height, 0px));
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
    padding: 8px 10px;
    gap: 8px;
    background: rgb(255 255 255 / 96%);
    backdrop-filter: blur(10px);
  }
  .assistant-composer textarea {
    box-sizing: border-box;
    height: auto;
    min-height: 46px;
    max-height: 120px;
    resize: none;
  }
  .assistant-send {
    box-sizing: border-box;
    width: auto;
    min-width: 46px;
    height: auto;
    min-height: 46px;
    align-self: stretch;
    padding: 0 12px;
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
.assistant-page{height:calc(100dvh - 72px);min-height:calc(100dvh - 72px)}
.assistant-shell{height:100%;min-height:100%;border:0;border-radius:0;box-shadow:none}
.assistant-messages{padding:30px clamp(18px,5vw,88px) 34px}
.assistant-message{max-width:min(900px,88%);user-select:none;-webkit-user-select:none}
.assistant-message__header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:8px}
.assistant-message__identity,.assistant-message__meta{display:flex;align-items:center;gap:8px;min-width:0}
.assistant-message__meta{color:#94a3b8;font-size:10px}
.assistant-message__label{margin:0}
.assistant-message__kind{display:inline-flex;align-items:center;gap:4px;padding:3px 7px;border-radius:999px;background:#ecfdf5;color:#047857;font-size:10px;font-weight:700}
.assistant-message__action{display:grid;place-items:center;width:24px;height:24px;padding:0;border:0;border-radius:7px;background:transparent;color:#94a3b8}
.assistant-message__action:hover{background:#eff6ff;color:#1d4ed8}
.assistant-message__body{min-width:0}
.assistant-message__quote,.assistant-quote-preview{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:start;gap:6px 8px;margin:0 0 10px;padding:8px 10px;border-left:3px solid #93c5fd;border-radius:0 8px 8px 0;background:#f8fafc;color:#475569;font-size:12px}
.assistant-message__quote{cursor:pointer}
.assistant-message__quote>span,.assistant-quote-preview strong{color:#1d4ed8;font-size:11px}
.assistant-message__quote p{grid-column:2;margin:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.assistant-message--user .assistant-message__quote{border-left-color:#bfdbfe;background:rgb(255 255 255 / 12%);color:#dbeafe}
.assistant-message--user .assistant-message__quote>span{color:#dbeafe}
.assistant-message--report{max-width:min(980px,94%);border-color:#bbf7d0;background:linear-gradient(145deg,#f0fdf4,#fff 62%);box-shadow:0 8px 24px rgb(22 101 52 / 7%)}
.assistant-message--report::before{position:absolute;inset:0 auto 0 0;width:4px;border-radius:18px 0 0 18px;background:#22c55e;content:""}
.assistant-message--user .assistant-message__meta{color:#bfdbfe}
.assistant-message--user .assistant-message__action{color:#dbeafe}
.assistant-message--user .assistant-message__action:hover{background:rgb(255 255 255 / 16%);color:#fff}
.assistant-attachments,.assistant-attachment-strip{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.assistant-attachment{display:inline-flex;align-items:center;gap:8px;min-width:0;max-width:280px;padding:7px 9px;border:1px solid #dbe4ef;border-radius:10px;background:#f8fafc;color:inherit;text-decoration:none}
.assistant-attachment:hover{border-color:#93c5fd;background:#eff6ff}
.assistant-attachment img{width:48px;height:38px;border-radius:6px;object-fit:cover}
.assistant-attachment span{display:grid;min-width:0;gap:2px}
.assistant-attachment strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
.assistant-attachment small{color:#64748b;font-size:10px}
.assistant-composer{flex-direction:column;padding:12px clamp(14px,5vw,88px) 16px}
.assistant-composer__row{display:flex;align-items:stretch;gap:10px;width:100%}
.assistant-composer__row textarea{min-width:0}
.assistant-attach{display:grid;place-items:center;width:44px;flex:0 0 44px;border:1px solid var(--border-color);border-radius:11px;background:#f8fafc;color:#475569}
.assistant-attach:hover{border-color:#93c5fd;color:#1d4ed8;background:#eff6ff}
.assistant-file-input{display:none}
.assistant-quote-preview{width:100%;grid-template-columns:auto minmax(0,1fr) auto;margin:0}
.assistant-quote-preview>span{display:grid;gap:2px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.assistant-composer__clear,.assistant-attachment-chip button{display:grid;place-items:center;border:0;background:transparent;color:#64748b}
.assistant-composer__clear:hover,.assistant-attachment-chip button:hover{color:#dc2626}
.assistant-attachment-chip{display:inline-flex;align-items:center;gap:6px;max-width:230px;padding:5px 7px;border:1px solid #dbe4ef;border-radius:8px;background:#fff;color:#475569;font-size:11px}
.assistant-attachment-chip img{width:24px;height:22px;border-radius:4px;object-fit:cover}
.assistant-attachment-chip>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media (max-width:760px){.assistant-messages{padding:14px 12px 18px}.assistant-message__meta time{display:none}.assistant-message__header{gap:8px}.assistant-message--report{max-width:96%}.assistant-composer{padding:8px 10px 10px}}
/* Final responsive layer: keep the chat surface consistent on every viewport. */
.assistant-page {
  display: flex;
  width: 100%;
  height: calc(100dvh - 72px);
  min-height: calc(100dvh - 72px);
  margin: 0;
  overflow: hidden;
  background: #f6f8fc;
}
.assistant-shell {
  position: relative;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100%;
  border: 0;
  border-radius: 0;
  background: #f6f8fc;
  box-shadow: none;
  overflow: hidden;
}
.assistant-shell__header {
  position: relative;
  inset: auto;
  z-index: 5;
  display: flex;
  flex: 0 0 48px;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-height: 48px;
  padding: 8px clamp(16px, 4vw, 64px) 6px;
  border: 0;
  border-bottom: 1px solid #e8edf5;
  background: rgb(246 248 252 / 94%);
  pointer-events: auto;
  backdrop-filter: blur(12px);
}
.assistant-shell__header > * { pointer-events: auto; }
.assistant-search-toggle {
  width: 36px;
  height: 36px;
  border: 1px solid #d8e0ec;
  border-radius: 12px;
  background: #fff;
  color: #52627a;
  box-shadow: 0 2px 8px rgb(15 23 42 / 6%);
}
.assistant-search-toggle:hover,
.assistant-search__clear:hover,
.assistant-search__close:hover {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
}
.assistant-search {
  width: min(440px, 100%);
  min-height: 36px;
  padding: 7px 10px;
  border: 1px solid #d8e0ec;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 2px 8px rgb(15 23 42 / 6%);
}
.assistant-search input { color: #1e293b; }
.assistant-search-results {
  top: 52px;
  right: clamp(16px, 4vw, 64px);
  width: min(440px, calc(100% - 32px));
  padding: 6px;
  border: 1px solid #d8e0ec;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 16px 36px rgb(15 23 42 / 14%);
}
.assistant-search-results button { padding: 10px; border-radius: 10px; }
.assistant-search-results button:hover { background: #f1f5f9; }
.assistant-messages {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  align-items: stretch;
  gap: 12px;
  min-width: 0;
  min-height: 0;
  padding: 18px clamp(16px, 4vw, 64px) 22px;
  overflow-x: hidden;
  overflow-y: auto;
  background: #f6f8fc;
  overscroll-behavior: contain;
  scroll-behavior: auto;
  -webkit-overflow-scrolling: touch;
}
.assistant-loading,
.assistant-empty { min-height: 56px; color: #718096; }
.assistant-empty { margin: auto; padding: 42px 16px; }
.assistant-progress {
  max-width: min(760px, 92%);
  margin: 2px 2px 0;
  color: #718096;
  font-size: 13px;
}
.assistant-message {
  align-self: flex-start;
  width: fit-content;
  max-width: min(860px, 92%);
  min-width: 0;
  padding: 14px 16px;
  border: 1px solid #e4eaf2;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 3px 12px rgb(15 23 42 / 5%);
  color: #1f2937;
  user-select: text;
  -webkit-user-select: text;
}
.assistant-message--user {
  align-self: flex-end;
  max-width: min(720px, 86%);
  border-color: #2563eb;
  border-radius: 18px 18px 6px 18px;
  background: #2563eb;
  color: #fff;
  box-shadow: 0 5px 14px rgb(37 99 235 / 17%);
}
.assistant-message--assistant { border-radius: 6px 18px 18px 18px; }
.assistant-message--report {
  align-self: flex-start;
  width: min(980px, 100%);
  max-width: 100%;
  border-color: #c8ead8;
  border-radius: 16px;
  background: linear-gradient(145deg, #f1fcf5, #fff 72%);
  box-shadow: 0 5px 16px rgb(22 101 52 / 7%);
}
.assistant-message--report::before {
  width: 3px;
  border-radius: 16px 0 0 16px;
  background: #22a06b;
}
.assistant-message--highlight { outline: 3px solid rgb(96 165 250 / 42%); outline-offset: 2px; }
.assistant-message--failed { border-color: #fecaca; background: #fff1f2; color: #991b1b; }
.assistant-message--pending { border-color: #bfdbfe; }
.assistant-message__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 24px;
  margin-bottom: 8px;
}
.assistant-message__identity,
.assistant-message__meta { display: flex; align-items: center; gap: 7px; min-width: 0; }
.assistant-message__label {
  display: inline-flex;
  align-items: center;
  margin: 0;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .01em;
}
.assistant-message--user .assistant-message__label { color: #dbeafe; }
.assistant-message__kind {
  padding: 3px 7px;
  border-radius: 999px;
  background: #dff7e8;
  color: #087443;
  font-size: 10px;
  font-weight: 700;
}
.assistant-message__meta { color: #94a3b8; font-size: 10px; }
.assistant-message__meta time { display: inline; margin: 0; color: inherit; font-size: inherit; }
.assistant-message__action {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #94a3b8;
  transition: background .15s ease, color .15s ease;
}
.assistant-message__action:hover { background: #eef4ff; color: #1d4ed8; }
.assistant-message--user .assistant-message__meta,
.assistant-message--user .assistant-message__action { color: #dbeafe; }
.assistant-message--user .assistant-message__action:hover { background: rgb(255 255 255 / 16%); color: #fff; }
.assistant-message__body { min-width: 0; }
.assistant-message p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.6; }
.assistant-message :deep(.markdown-content) {
  max-width: 100%;
  color: inherit;
  font-size: 15px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
.assistant-message :deep(.markdown-content p) { margin: 0 0 .72em; white-space: normal; }
.assistant-message :deep(.markdown-content p:last-child) { margin-bottom: 0; }
.assistant-message :deep(.markdown-content h1),
.assistant-message :deep(.markdown-content h2),
.assistant-message :deep(.markdown-content h3) { margin: .9em 0 .42em; line-height: 1.35; font-weight: 750; }
.assistant-message :deep(.markdown-content h1:first-child),
.assistant-message :deep(.markdown-content h2:first-child),
.assistant-message :deep(.markdown-content h3:first-child) { margin-top: 0; }
.assistant-message :deep(.markdown-content ul),
.assistant-message :deep(.markdown-content ol) { margin: .35em 0 .72em; padding-left: 1.35em; }
.assistant-message :deep(.markdown-content li) { margin: .18em 0; }
.assistant-message :deep(.markdown-content pre) { max-width: 100%; margin: .65em 0; overflow-x: auto; border-radius: 10px; }
.assistant-message :deep(.markdown-content code) { font-size: .9em; }
.assistant-message :deep(.markdown-content a) { color: #1d4ed8; }
.assistant-message :deep(.markdown-table-wrap) { margin: .72em 0; border-color: #dce5f0; border-radius: 10px; }
.assistant-message :deep(.markdown-table-wrap table) { min-width: 440px; font-size: .92em; }
.assistant-message :deep(.markdown-table-wrap th),
.assistant-message :deep(.markdown-table-wrap td) { padding: 8px 10px; }
.assistant-attachments,
.assistant-attachment-strip { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 11px; }
.assistant-attachment {
  max-width: min(280px, 100%);
  padding: 7px 9px;
  border-color: #dce5f0;
  border-radius: 10px;
  background: #f8fafc;
}
.assistant-attachment:hover { border-color: #93c5fd; background: #eff6ff; }
.assistant-attachment img { width: 44px; height: 36px; }
.assistant-error {
  margin: 0;
  padding: 9px clamp(16px, 4vw, 64px);
  border-top: 1px solid #fecaca;
  background: #fff1f2;
  color: #991b1b;
  font-size: 13px;
}
.assistant-composer {
  position: relative;
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  padding: 10px clamp(16px, 4vw, 64px) max(12px, env(safe-area-inset-bottom));
  border-top: 1px solid #e1e8f1;
  background: rgb(255 255 255 / 96%);
  backdrop-filter: blur(14px);
}
.assistant-composer__row {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr) 48px;
  align-items: end;
  gap: 8px;
  width: 100%;
}
.assistant-composer textarea {
  width: 100%;
  height: 48px;
  min-height: 48px;
  max-height: 152px;
  padding: 12px 14px;
  border: 1px solid #d6e0ec;
  border-radius: 14px;
  background: #f8fafc;
  color: #1e293b;
  line-height: 1.4;
  resize: vertical;
  transition: border-color .15s ease, box-shadow .15s ease, background .15s ease;
}
.assistant-composer textarea:focus { border-color: #60a5fa; background: #fff; box-shadow: 0 0 0 3px rgb(96 165 250 / 14%); }
.assistant-composer textarea:disabled { opacity: .72; }
.assistant-attach,
.assistant-send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  min-width: 44px;
  min-height: 44px;
  padding: 0;
  border-radius: 13px;
}
.assistant-attach { border: 1px solid #d6e0ec; background: #fff; color: #52627a; }
.assistant-attach:hover { border-color: #93c5fd; background: #eff6ff; color: #1d4ed8; }
.assistant-send {
  width: 48px;
  min-width: 48px;
  border-color: #2563eb;
  background: #2563eb;
  box-shadow: 0 4px 10px rgb(37 99 235 / 17%);
}
.assistant-send:hover:not(:disabled) { border-color: #1d4ed8; background: #1d4ed8; }
.assistant-send span { display: none; }
.assistant-file-input { display: none; }
.assistant-quote-preview {
  width: 100%;
  max-width: 100%;
  margin: 0;
  padding: 8px 10px;
  border-left-color: #60a5fa;
  border-radius: 0 10px 10px 0;
  background: #f1f5f9;
  color: #475569;
}
.assistant-quote-preview > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.assistant-attachment-chip { max-width: 240px; border-color: #dce5f0; background: #f8fafc; }
.assistant-composer__clear,
.assistant-attachment-chip button { display: grid; place-items: center; border: 0; background: transparent; color: #64748b; }
@media (max-width: 760px) {
  .assistant-page {
    height: calc(100dvh - 56px - var(--mobile-tabbar-height, 0px));
    min-height: calc(100dvh - 56px - var(--mobile-tabbar-height, 0px));
    margin: 0;
  }
  .assistant-shell { height: 100%; min-height: 0; }
  .assistant-shell__header {
    flex-basis: 44px;
    min-height: 44px;
    padding: 5px 12px;
    border-bottom-color: #edf1f6;
  }
  .assistant-search-results { top: 48px; right: 12px; width: calc(100% - 24px); }
  .assistant-messages { gap: 10px; padding: 14px 12px 18px; }
  .assistant-message { max-width: 94%; padding: 12px 13px; border-radius: 15px; }
  .assistant-message--user { max-width: 92%; border-radius: 16px 16px 5px 16px; }
  .assistant-message--assistant { border-radius: 5px 16px 16px 16px; }
  .assistant-message--report { width: 100%; max-width: 100%; }
  .assistant-message__header { gap: 8px; margin-bottom: 6px; }
  .assistant-message__meta time { display: none; }
  .assistant-message :deep(.markdown-content) { font-size: 15px; line-height: 1.62; }
  .assistant-message :deep(.markdown-table-wrap) { margin-right: -2px; margin-left: -2px; }
  .assistant-composer { gap: 7px; padding: 8px 10px max(10px, env(safe-area-inset-bottom)); }
  .assistant-composer__row { grid-template-columns: 42px minmax(0, 1fr) 44px; gap: 7px; }
  .assistant-composer textarea { height: 46px; min-height: 46px; max-height: 120px; padding: 11px 12px; resize: none; }
  .assistant-attach,
  .assistant-send { width: 42px; min-width: 42px; height: 42px; min-height: 42px; border-radius: 12px; }
  .assistant-send { width: 44px; min-width: 44px; }
  .assistant-quote-preview > span { max-width: calc(100vw - 86px); }
}
.assistant-identity {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
  margin-right: auto;
}
.assistant-identity__avatar {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  border: 1px solid #bfdbfe;
  border-radius: 11px;
  background: linear-gradient(145deg, #e0ecff, #fff);
  color: #2563eb;
}
.assistant-identity__copy {
  display: grid;
  min-width: 0;
  gap: 1px;
}
.assistant-identity__copy strong {
  overflow: hidden;
  color: #1e293b;
  font-size: 13px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.assistant-identity__copy small {
  overflow: hidden;
  color: #8a98aa;
  font-size: 10px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.assistant-messages {
  gap: 14px;
  background: #f8fafc;
}
.assistant-message {
  max-width: min(820px, 88%);
  border-color: #e6ebf2;
  box-shadow: 0 2px 9px rgb(15 23 42 / 4%);
}
.assistant-message--user { max-width: min(680px, 82%); }
.assistant-message--report { width: min(900px, 100%); }
.assistant-reminder-card {
  display: grid;
  gap: 9px;
  min-width: min(300px, 100%);
  max-width: 100%;
  padding: 12px 13px;
  border: 1px solid #d8e5f3;
  border-radius: 13px;
  background: linear-gradient(145deg, #f5f9ff, #fff 76%);
  color: #1e293b;
}
.assistant-reminder-card__top {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.assistant-reminder-card__icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border-radius: 10px;
  background: #e0ecff;
  color: #2563eb;
}
.assistant-reminder-card__main {
  display: grid;
  min-width: 0;
  flex: 1 1 auto;
  gap: 2px;
}
.assistant-reminder-card__main strong {
  overflow: hidden;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.assistant-reminder-card__main small {
  color: #718096;
  font-size: 11px;
}
.assistant-reminder-card__relative {
  flex: 0 0 auto;
  padding: 4px 7px;
  border-radius: 999px;
  background: #eaf2ff;
  color: #2563eb;
  font-size: 10px;
  font-weight: 700;
  white-space: nowrap;
}
.assistant-reminder-card__time {
  display: flex;
  align-items: center;
  gap: 7px;
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}
.assistant-reminder-card__time span:last-child { color: #2563eb; font-weight: 600; }
.assistant-reminder-card__detail { color: #718096; font-size: 11px; line-height: 1.45; }
@media (max-width: 760px) {
  .assistant-identity__copy strong { font-size: 12px; }
  .assistant-identity__copy small { display: none; }
  .assistant-messages { gap: 12px; background: #f8fafc; }
  .assistant-message { max-width: 91%; }
  .assistant-message--user { max-width: 88%; }
  .assistant-message--report { width: 100%; max-width: 100%; }
  .assistant-reminder-card { min-width: 0; padding: 11px 12px; }
  .assistant-reminder-card__main strong { white-space: normal; }
}
.assistant-page,
.assistant-shell { background: #f7f8fa; }
.assistant-shell__header {
  flex-basis: 56px;
  min-height: 56px;
  padding: 8px max(14px, calc((100% - 760px) / 2));
  border-bottom: 1px solid #edf0f4;
  background: #fff;
}
.assistant-identity__avatar { width: 30px; height: 30px; flex-basis: 30px; border-radius: 10px; }
.assistant-identity__copy strong { font-size: 14px; font-weight: 700; }
.assistant-identity__copy small { color: #97a1b0; font-size: 10px; }
.assistant-search-toggle { width: 34px; height: 34px; border-color: #e2e7ee; border-radius: 10px; box-shadow: none; }
.assistant-search { border-color: #e2e7ee; border-radius: 10px; box-shadow: none; }
.assistant-search-results { top: 58px; right: max(14px, calc((100% - 760px) / 2)); }
.assistant-messages {
  align-items: stretch;
  gap: 10px;
  padding: 12px max(14px, calc((100% - 760px) / 2)) 24px;
  background: #f7f8fa;
}
.assistant-date-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  margin: 7px 0 2px;
  color: #9aa4b2;
  font-size: 10px;
  letter-spacing: .02em;
  text-align: center;
}
.assistant-date-divider::before,
.assistant-date-divider::after { height: 1px; flex: 1 1 auto; background: #e5e9ef; content: ""; }
.assistant-message {
  max-width: 84%;
  padding: 10px 13px;
  border: 0;
  border-radius: 14px;
  background: #fff;
  box-shadow: none;
}
.assistant-message--assistant { border-radius: 5px 14px 14px 14px; }
.assistant-message--user {
  max-width: 78%;
  border-radius: 14px 14px 5px 14px;
  background: #2f6fed;
  box-shadow: none;
}
.assistant-message--report { width: 100%; max-width: 100%; border: 1px solid #e8edf2; background: #fff; }
.assistant-message__header { min-height: 20px; margin-bottom: 5px; }
.assistant-message__label { color: #8b96a5; font-size: 10px; font-weight: 650; }
.assistant-message__action { width: 24px; height: 24px; color: #a2acb9; }
.assistant-message__meta { gap: 4px; }
.assistant-message__kind { padding: 2px 6px; font-size: 9px; }
.assistant-message__body { line-height: 1.55; }
.assistant-message :deep(.markdown-content) { font-size: 15px; line-height: 1.58; }
.assistant-message :deep(.markdown-content p) { margin-bottom: .58em; }
.assistant-message--reminder {
  width: fit-content;
  max-width: min(100%, 390px);
  padding: 0;
  border: 0;
  background: transparent;
}
.assistant-message--reminder .assistant-message__header { padding: 0 3px; }
.assistant-reminder-card {
  width: min(100%, 360px);
  min-width: 0;
  gap: 7px;
  padding: 10px 11px;
  border-color: #e1e7ee;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 3px rgb(15 23 42 / 3%);
}
.assistant-reminder-card__icon { width: 28px; height: 28px; flex-basis: 28px; border-radius: 9px; }
.assistant-reminder-card__main strong { font-size: 12px; }
.assistant-reminder-card__main small { font-size: 10px; }
.assistant-reminder-card__relative { padding: 3px 6px; font-size: 9px; }
.assistant-reminder-card__time { font-size: 12px; }
.assistant-composer {
  gap: 0;
  padding: 8px max(14px, calc((100% - 760px) / 2)) max(10px, env(safe-area-inset-bottom));
  border-top: 1px solid #e9edf2;
  background: #fff;
  backdrop-filter: none;
}
.assistant-composer__row { grid-template-columns: 42px minmax(0, 1fr) 44px; gap: 7px; }
.assistant-composer textarea {
  height: 44px;
  min-height: 44px;
  padding: 10px 12px;
  border-color: #e0e5eb;
  border-radius: 12px;
  background: #f8fafc;
  box-shadow: none;
}
.assistant-attach,
.assistant-send { width: 42px; min-width: 42px; height: 42px; min-height: 42px; border-radius: 11px; box-shadow: none; }
.assistant-send { width: 44px; min-width: 44px; }
@media (max-width: 760px) {
  .assistant-shell__header { flex-basis: 52px; min-height: 52px; padding: 8px 14px; }
  .assistant-search-results { top: 56px; right: 14px; }
  .assistant-messages { gap: 9px; padding: 10px 14px 18px; }
  .assistant-message { max-width: 88%; padding: 9px 11px; }
  .assistant-message--user { max-width: 88%; }
  .assistant-message--report { width: 100%; max-width: 100%; }
  .assistant-message--reminder { max-width: 96%; }
  .assistant-date-divider { margin: 6px 0 1px; }
  .assistant-composer { padding: 8px 10px max(10px, env(safe-area-inset-bottom)); }
}
.assistant-composer {
  position: sticky;
  bottom: 0;
  z-index: 8;
  width: 100%;
  padding: 10px max(14px, calc((100% - 760px) / 2)) max(12px, env(safe-area-inset-bottom));
  border-top: 0;
  background: transparent;
  backdrop-filter: none;
}
.assistant-composer__row {
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) 44px;
  align-items: center;
  gap: 7px;
  width: min(100%, 760px);
  margin: 0 auto;
  padding: 5px;
  border: 1px solid rgb(210 218 229 / 88%);
  border-radius: 25px;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 8px 24px rgb(15 23 42 / 10%), 0 1px 3px rgb(15 23 42 / 7%);
  -webkit-backdrop-filter: blur(18px);
  backdrop-filter: blur(18px);
}
.assistant-composer__row textarea {
  width: 100%;
  height: 42px;
  min-height: 42px;
  max-height: 120px;
  padding: 10px 5px;
  border: 0;
  border-radius: 0;
  outline: 0;
  background: transparent;
  box-shadow: none;
  resize: none;
  border: 0 !important;
  border-inline: 0 !important;
  background-image: none !important;
}
.assistant-composer__row::before,
.assistant-composer__row::after { display: none; content: none; }
.assistant-composer__row textarea:focus {
  border-color: transparent;
  background: transparent;
  box-shadow: none;
}
.assistant-attach,
.assistant-send {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  min-width: 42px;
  min-height: 42px;
  padding: 0;
  border-radius: 50%;
  box-shadow: none;
}
.assistant-attach {
  border: 1px solid #e1e6ed;
  background: #f7f8fa;
  color: #667487;
}
.assistant-attach:hover:not(:disabled) { border-color: #cbd5e1; background: #eef2f6; color: #334155; }
.assistant-send {
  width: 44px;
  min-width: 44px;
  border-color: #334155;
  background: #334155;
  color: #fff;
}
.assistant-send:disabled {
  border-color: #e2e8f0;
  background: #e2e8f0;
  color: #94a3b8;
  box-shadow: none;
}
.assistant-send:hover:not(:disabled) { border-color: #1f2937; background: #1f2937; }
.assistant-send span { display: none; }
.assistant-stop { border-color: #cbd5e1; background: #f8fafc; color: #334155; }
.assistant-stop:hover:not(:disabled) { border-color: #94a3b8; background: #eef2f7; color: #1f2937; }
.assistant-stop:disabled { opacity: .62; }
.assistant-history-load {
  align-self: center;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 32px;
  max-width: min(100%, 360px);
  margin: 0 auto 2px;
  padding: 6px 12px;
  border: 1px solid #d8e0ec;
  border-radius: 999px;
  background: rgb(255 255 255 / 82%);
  color: #64748b;
  font-size: 12px;
  line-height: 1.2;
  box-shadow: 0 2px 8px rgb(15 23 42 / 5%);
}
.assistant-history-load:hover:not(:disabled) { border-color: #b8c5d6; background: #fff; color: #334155; }
.assistant-history-load:disabled { cursor: wait; opacity: .68; }
.assistant-messages__content {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  align-items: stretch;
  gap: inherit;
  min-width: 0;
  min-height: 100%;
}
@media (max-width: 760px) {
  .assistant-composer {
    padding: 8px 10px max(12px, env(safe-area-inset-bottom));
  }
  .assistant-composer__row {
    width: 100%;
    border-radius: 24px;
  }
  .assistant-composer__row textarea { height: 40px; min-height: 40px; padding: 9px 4px; }
  .assistant-attach,
  .assistant-send { width: 40px; min-width: 40px; height: 40px; min-height: 40px; }
  .assistant-send { width: 42px; min-width: 42px; }
  .assistant-history-load { min-height: 30px; margin-bottom: 0; padding: 5px 10px; font-size: 11px; }
}
</style>
