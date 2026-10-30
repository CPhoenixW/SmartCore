<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Bot, Send, Trash2, WifiOff } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import PageHeader from "@/components/base/PageHeader.vue";
import { assistantApi } from "@/api/assistant";
import type { AssistantStreamEvent } from "@/api/assistant";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
}

const SESSION_KEY = "smartcore-assistant-session";
const DRAFT_KEY = "smartcore-assistant-draft";
const MESSAGES_KEY = "smartcore-assistant-messages";
const { t } = useI18n();
const input = ref("");
const sessionId = ref("");
const messages = ref<Message[]>([]);
const sending = ref(false);
const error = ref("");
const activity = ref("");
const activeTool = ref("");
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
const messagesRoot = ref<HTMLElement | null>(null);

function storageGet(key: string): string {
  try { return window.localStorage.getItem(key) ?? ""; } catch { return ""; }
}
function storageSet(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); } catch { /* private mode or quota */ }
}
function persistMessages(): void { storageSet(MESSAGES_KEY, JSON.stringify(messages.value.slice(-40))); }
function scrollToLatest(): void {
  void nextTick(() => {
    if (messagesRoot.value) messagesRoot.value.scrollTop = messagesRoot.value.scrollHeight;
  });
}
function newSessionId(): string {
  return `pwa-${typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`;
}
function clearConversation(): void {
  sessionId.value = newSessionId();
  messages.value = [];
  storageSet(SESSION_KEY, sessionId.value);
  storageSet(MESSAGES_KEY, "[]");
  error.value = "";
}
async function send(): Promise<void> {
  const text = input.value.trim();
  if (!text || sending.value) return;
  if (!online.value) {
    error.value = t("assistant.offline");
    storageSet(DRAFT_KEY, text);
    return;
  }
  input.value = "";
  storageSet(DRAFT_KEY, "");
  error.value = "";
  messages.value.push({ id: `user-${Date.now()}`, role: "user", text });
  persistMessages();
  scrollToLatest();
  sending.value = true;
  activity.value = t("assistant.starting");
  activeTool.value = "";
  let receivedAssistant = false;
  try {
    const result = await assistantApi.stream(
      text,
      sessionId.value || undefined,
      (event: AssistantStreamEvent) => {
        if (event.type === "status") activity.value = event.message || t("assistant.thinking");
        if (event.type === "tool") {
          activity.value = event.message || t("assistant.toolWorking");
          activeTool.value = event.name || "";
        }
        if (event.type === "message" && event.text.trim()) {
          receivedAssistant = true;
          messages.value.push({ id: `assistant-${Date.now()}-${messages.value.length}`, role: "assistant", text: event.text });
          persistMessages();
          scrollToLatest();
        }
        if (event.type === "done") activity.value = t("assistant.done");
      },
    );
    sessionId.value = result.sessionId || sessionId.value;
    storageSet(SESSION_KEY, sessionId.value);
    if (!receivedAssistant && result.response) {
      messages.value.push({ id: `assistant-${Date.now()}`, role: "assistant", text: result.response });
    }
    persistMessages();
  } catch (requestError) {
    error.value = requestError instanceof Error && requestError.message ? requestError.message : t("assistant.error");
    storageSet(DRAFT_KEY, text);
  } finally {
    sending.value = false;
    activity.value = "";
    activeTool.value = "";
    scrollToLatest();
  }
}
function onOnline(): void { online.value = true; }
function onOffline(): void { online.value = false; }
onMounted(() => {
  sessionId.value = storageGet(SESSION_KEY) || newSessionId();
  storageSet(SESSION_KEY, sessionId.value);
  const savedMessages = storageGet(MESSAGES_KEY);
  if (savedMessages) {
    try {
      const parsed = JSON.parse(savedMessages);
      if (Array.isArray(parsed)) messages.value = parsed.filter((item): item is Message => item && (item.role === "user" || item.role === "assistant") && typeof item.text === "string");
    } catch { /* stale local state */ }
  }
  input.value = storageGet(DRAFT_KEY);
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  scrollToLatest();
});
onBeforeUnmount(() => {
  window.removeEventListener("online", onOnline);
  window.removeEventListener("offline", onOffline);
});
watch(messages, persistMessages, { deep: true });
</script>

<template>
  <div class="assistant-page">
    <PageHeader :title="t('assistant.title')" :subtitle="t('assistant.subtitle')">
      <button class="button button--ghost assistant-clear" type="button" @click="clearConversation">
        <Trash2 :size="15" aria-hidden="true" />{{ t("assistant.clear") }}
      </button>
    </PageHeader>
    <section class="assistant-shell card">
      <div class="assistant-status" :class="{ 'assistant-status--offline': !online }">
        <WifiOff v-if="!online" :size="15" aria-hidden="true" />
        <Bot v-else :size="15" aria-hidden="true" />
        <span>{{ online ? t("assistant.ready") : t("assistant.offline") }}</span>
      </div>
      <div ref="messagesRoot" class="assistant-messages" aria-live="polite">
        <div v-if="!messages.length" class="assistant-empty">
          <Bot :size="30" aria-hidden="true" />
          <strong>{{ t("assistant.empty") }}</strong>
          <span>{{ t("assistant.examples") }}</span>
        </div>
        <article v-for="message in messages" :key="message.id" class="assistant-message" :class="`assistant-message--${message.role}`">
          <span class="assistant-message__label">{{ message.role === "user" ? t("assistant.you") : t("assistant.bot") }}</span>
          <p>{{ message.text }}</p>
        </article>
        <div v-if="sending" class="assistant-typing" role="status"><span class="assistant-typing__dot" />{{ activity || t("assistant.thinking") }}<small v-if="activeTool">{{ activeTool }}</small></div>
      </div>
      <p v-if="error" class="assistant-error" role="alert">{{ error }}</p>
      <form class="assistant-composer" @submit.prevent="send">
        <textarea v-model="input" :disabled="sending" :placeholder="t('assistant.placeholder')" rows="2" @keydown.enter.exact.prevent="send" />
        <button class="button button--primary assistant-send" type="submit" :disabled="sending || !input.trim()">
          <Send :size="16" aria-hidden="true" />{{ sending ? t("assistant.sending") : t("assistant.send") }}
        </button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.assistant-page{display:grid;gap:18px}.assistant-shell{display:flex;min-height:calc(100vh - 190px);flex-direction:column}.assistant-status{display:flex;align-items:center;gap:7px;padding:13px 18px;border-bottom:1px solid var(--border-color);color:#166534;font-size:13px}.assistant-status--offline{color:#9a3412;background:#fff7ed}.assistant-messages{display:grid;align-content:start;gap:14px;min-height:0;flex:1;padding:20px;overflow-y:auto;background:#f8fafc}.assistant-empty{display:grid;justify-items:center;gap:9px;margin:auto;color:var(--color-text-muted);text-align:center}.assistant-empty svg{color:var(--color-primary)}.assistant-empty span{max-width:360px;font-size:13px}.assistant-message{max-width:min(760px,88%);padding:12px 14px;border-radius:14px;background:#fff;box-shadow:0 3px 10px rgb(15 23 42 / 6%)}.assistant-message--user{justify-self:end;background:#2563eb;color:#fff}.assistant-message__label{display:block;margin-bottom:5px;color:#64748b;font-size:11px;font-weight:700}.assistant-message--user .assistant-message__label{color:#dbeafe}.assistant-message p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.6}.assistant-typing{display:flex;align-items:center;gap:8px;justify-self:start;color:var(--color-text-muted);font-size:13px}.assistant-typing small{color:#2563eb}.assistant-typing__dot{width:8px;height:8px;border-radius:50%;background:#2563eb;box-shadow:0 0 0 0 rgb(37 99 235 / 50%);animation:assistant-pulse 1.35s infinite}.assistant-error{margin:0;padding:10px 18px;color:#991b1b;background:#fff1f2;font-size:13px}.assistant-composer{display:flex;align-items:flex-end;gap:10px;padding:14px;border-top:1px solid var(--border-color);background:#fff}.assistant-composer textarea{min-height:44px;max-height:160px;flex:1;resize:vertical;padding:11px;border:1px solid var(--border-color);border-radius:10px;outline:0;font:inherit}.assistant-composer textarea:focus{border-color:#60a5fa;box-shadow:0 0 0 3px rgb(96 165 250 / 15%)}.assistant-send{display:inline-flex;align-items:center;gap:7px;min-height:44px}.assistant-clear{display:inline-flex;align-items:center;gap:6px}@keyframes assistant-pulse{70%{box-shadow:0 0 0 7px rgb(37 99 235 / 0)}}@media(max-width:640px){.assistant-shell{min-height:calc(100vh - 150px);margin:0 -2px;border-radius:12px}.assistant-messages{padding:14px}.assistant-message{max-width:94%}.assistant-composer{padding:10px;align-items:stretch;flex-direction:column}.assistant-send{justify-content:center}.assistant-clear{align-self:flex-start}}
</style>
