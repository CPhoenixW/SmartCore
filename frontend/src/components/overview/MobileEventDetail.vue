<script setup lang="ts">
import { computed } from "vue";
import { Check, Pencil, X } from "@lucide/vue";
import { useI18n } from "vue-i18n";
import type { PlanEvent, SmartCoreEvent } from "@/types/event";
import { getEventPrimaryTime } from "@/utils/date";

const props = defineProps<{ event: SmartCoreEvent; timezone: string }>();
const emit = defineEmits<{ close: []; edit: []; done: [] }>();
const { t, locale } = useI18n();

function parse(value: string): Date | null {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

function format(value: Date): string {
  return new Intl.DateTimeFormat(locale.value === "en-US" ? "en-US" : "zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: props.timezone,
  }).format(value);
}

const typeLabel = computed(() => t("event.type." + props.event.evtType));
const closeLabel = computed(() => t("common.close"));
const isTodo = computed(() => props.event.stat === "todo");
const statusLabel = computed(() => t("event.status." + props.event.stat));
const priorityLabel = computed(() => t("event.priority." + props.event.prio));
const timeCaption = computed(() => props.event.evtType === "plan" ? t("overview.timeRange") : t("event.form.triggerTime"));
const timeLabel = computed(() => {
  const start = parse(getEventPrimaryTime(props.event));
  if (!start) return t("preview.notSet");
  if (props.event.evtType !== "plan") return format(start);
  const duration = Math.max(1, Number((props.event as PlanEvent).durationMin) || 1);
  const end = new Date(start.getTime() + duration * 60_000);
  return format(start) + " – " + format(end);
});
function close(): void { emit("close"); }
function edit(): void { emit("edit"); }
function done(): void { emit("done"); }
</script>

<template>
  <Teleport to="body">
    <div class="mobile-event-detail__backdrop" role="presentation" @click.self="close">
      <section class="mobile-event-detail" role="dialog" aria-modal="true" :aria-label="event.title">
        <header class="mobile-event-detail__header">
          <span>{{ t("overview.mobileDetail") }}</span>
          <button class="mobile-event-detail__close" type="button" :aria-label="closeLabel" @click="close"><X :size="20" aria-hidden="true" /></button>
        </header>
        <div class="mobile-event-detail__body">
          <span class="mobile-event-detail__type">{{ typeLabel }}</span>
          <h2>{{ event.title }}</h2>
          <dl class="mobile-event-detail__facts">
            <div><dt>{{ timeCaption }}</dt><dd>{{ timeLabel }}</dd></div>
            <div><dt>{{ t("event.form.status") }}</dt><dd>{{ statusLabel }}</dd></div>
            <div><dt>{{ t("event.form.priority") }}</dt><dd>{{ priorityLabel }}</dd></div>
          </dl>
          <div class="mobile-event-detail__description">
            <h3>{{ t("event.form.description") }}</h3>
            <p>{{ event.desc || t("preview.noDescription") }}</p>
          </div>
        </div>
        <footer class="mobile-event-detail__actions">
          <button class="button" type="button" @click="edit"><Pencil :size="16" aria-hidden="true" />{{ t("overview.editWithAssistant") }}</button>
          <button v-if="isTodo" class="button button--primary" type="button" @click="done"><Check :size="16" aria-hidden="true" />{{ t("event.status.done") }}</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.mobile-event-detail__backdrop { position: fixed; inset: 0; z-index: 70; display: flex; align-items: flex-end; justify-content: center; padding: 16px; background: rgb(15 23 42 / 46%); }
.mobile-event-detail { width: min(100%, 520px); max-height: min(88vh, 680px); overflow: auto; border: 1px solid var(--border-color); border-radius: 18px; background: var(--color-surface); box-shadow: 0 22px 50px rgb(15 23 42 / 25%); }
.mobile-event-detail__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border-color); color: var(--color-text-muted); font-size: 13px; font-weight: 700; }
.mobile-event-detail__close { display: grid; place-items: center; width: 34px; height: 34px; border: 0; border-radius: 9px; background: var(--color-surface-muted); color: var(--color-text); }
.mobile-event-detail__body { display: grid; gap: 12px; padding: 18px 16px 16px; }
.mobile-event-detail__type { width: fit-content; padding: 5px 9px; border-radius: 999px; background: #dbeafe; color: #1d4ed8; font-size: 12px; font-weight: 700; }
.mobile-event-detail h2 { margin: 0; font-size: 23px; line-height: 1.28; overflow-wrap: anywhere; }
.mobile-event-detail__facts { display: grid; gap: 10px; margin: 0; }
.mobile-event-detail__facts div { display: grid; gap: 3px; padding: 10px 12px; border-radius: 10px; background: #f8fafc; }
.mobile-event-detail__facts dt { color: var(--color-text-muted); font-size: 12px; }
.mobile-event-detail__facts dd { margin: 0; color: var(--color-text); font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.mobile-event-detail__description { padding-top: 4px; }
.mobile-event-detail__description h3 { margin: 0 0 5px; font-size: 13px; }
.mobile-event-detail__description p { margin: 0; color: var(--color-text-muted); line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.mobile-event-detail__actions { display: flex; gap: 8px; padding: 12px 16px max(12px, env(safe-area-inset-bottom)); border-top: 1px solid var(--border-color); }
.mobile-event-detail__actions .button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 42px; flex: 1; }
@media (min-width: 761px) { .mobile-event-detail__backdrop { align-items: center; } }
</style>
