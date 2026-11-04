<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { memoryApi } from "@/api/memory";
import { useToast } from "@/composables/useToast";
import { useViewport } from "@/composables/useViewport";
import type { MemoryItem, MemoryType } from "@/types/memory";
import { formatDateTime } from "@/utils/date";

const MEMORY_TYPES: MemoryType[] = ["profile", "preference", "habit", "goal", "relationship", "fact"];

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const { isMobile } = useViewport();
const query = useQuery({ queryKey: ["memories"], queryFn: memoryApi.list });
const filter = ref<MemoryType | "">("");
const draft = reactive<{ content: string; type: MemoryType | "" }>({ content: "", type: "" });
const editing = reactive<{ id: string; content: string; type: MemoryType }>({ id: "", content: "", type: "fact" });

const items = computed<MemoryItem[]>(() => query.data.value?.items ?? []);
const visible = computed(() => (filter.value ? items.value.filter((item) => item.type === filter.value) : items.value));
const enabled = computed(() => query.data.value?.enabled ?? true);

function invalidate() {
  void queryClient.invalidateQueries({ queryKey: ["memories"] });
}

function fail(error: unknown) {
  toast.error(error instanceof Error ? error.message : String(error));
}

const createMutation = useMutation({
  mutationFn: () =>
    memoryApi.create({ content: draft.content.trim(), type: draft.type || undefined }),
  onSuccess: () => {
    draft.content = "";
    draft.type = "";
    toast.success(t("memory.saved"));
    invalidate();
  },
  onError: fail,
});

const updateMutation = useMutation({
  mutationFn: () => memoryApi.update(editing.id, { content: editing.content.trim(), type: editing.type }),
  onSuccess: () => {
    editing.id = "";
    toast.success(t("memory.updated"));
    invalidate();
  },
  onError: fail,
});

const deleteMutation = useMutation({
  mutationFn: (memoryId: string) => memoryApi.remove(memoryId),
  onSuccess: () => {
    toast.success(t("memory.deleted"));
    invalidate();
  },
  onError: fail,
});

function submitDraft() {
  if (!draft.content.trim() || createMutation.isPending.value) return;
  createMutation.mutate();
}

function startEdit(item: MemoryItem) {
  editing.id = item.memoryId;
  editing.content = item.content;
  editing.type = item.type;
}

function saveEdit() {
  if (!editing.id || !editing.content.trim() || updateMutation.isPending.value) return;
  updateMutation.mutate();
}

function removeItem(item: MemoryItem) {
  if (typeof window !== "undefined" && typeof window.confirm === "function") {
    if (!window.confirm(t("memory.confirmDelete", { content: item.content }))) return;
  }
  deleteMutation.mutate(item.memoryId);
}

function sourceLabel(item: MemoryItem): string {
  return item.source === "user_explicit" ? t("memory.sourceExplicit") : t("memory.sourceAuto");
}
</script>

<template>
  <div class="memory-page" :class="{ 'memory-page--mobile': isMobile }">
    <PageHeader :title="t('memory.title')" :subtitle="t('memory.subtitle')">
      <template #actions>
        <button class="button" type="button" @click="query.refetch()">{{ t("common.refresh") }}</button>
      </template>
    </PageHeader>

    <p v-if="!enabled" class="memory-disabled">{{ t("memory.disabled") }}</p>

    <BaseCard :title="t('memory.addTitle')" :subtitle="t('memory.addHint')">
      <form class="memory-form" @submit.prevent="submitDraft">
        <input
          v-model="draft.content"
          class="wide-input"
          maxlength="120"
          :placeholder="t('memory.placeholder')"
          :aria-label="t('memory.addTitle')"
        />
        <select v-model="draft.type" :aria-label="t('memory.type')">
          <option value="">{{ t("memory.autoType") }}</option>
          <option v-for="kind in MEMORY_TYPES" :key="kind" :value="kind">{{ t(`memory.types.${kind}`) }}</option>
        </select>
        <button class="button button--primary" type="submit" :disabled="!draft.content.trim() || createMutation.isPending.value">
          {{ t("memory.add") }}
        </button>
      </form>
    </BaseCard>

    <BaseCard class="memory-list-card" :title="t('memory.listTitle', { count: items.length })">
      <div class="memory-filters" role="tablist">
        <button class="tab" :class="{ 'tab--active': filter === '' }" type="button" @click="filter = ''">{{ t("memory.all") }}</button>
        <button
          v-for="kind in MEMORY_TYPES"
          :key="kind"
          class="tab"
          :class="{ 'tab--active': filter === kind }"
          type="button"
          @click="filter = kind"
        >
          {{ t(`memory.types.${kind}`) }}
        </button>
      </div>
      <p v-if="query.isPending.value" class="muted-text">{{ t("common.loading") }}</p>
      <ul v-else-if="visible.length" class="memory-list">
        <li v-for="item in visible" :key="item.memoryId" class="memory-item">
          <form v-if="editing.id === item.memoryId" class="memory-edit" @submit.prevent="saveEdit">
            <input v-model="editing.content" class="wide-input" maxlength="120" :aria-label="t('common.edit')" />
            <select v-model="editing.type" :aria-label="t('memory.type')">
              <option v-for="kind in MEMORY_TYPES" :key="kind" :value="kind">{{ t(`memory.types.${kind}`) }}</option>
            </select>
            <div class="memory-item__actions">
              <button class="button button--primary" type="submit" :disabled="!editing.content.trim()">{{ t("common.save") }}</button>
              <button class="button" type="button" @click="editing.id = ''">{{ t("common.cancel") }}</button>
            </div>
          </form>
          <template v-else>
            <div class="memory-item__main">
              <p class="memory-item__content">{{ item.content }}</p>
              <div class="memory-item__meta">
                <span class="tag">{{ t(`memory.types.${item.type}`) }}</span>
                <span class="tag" :class="item.source === 'user_explicit' ? 'tag--done' : 'tag--prio-low'">{{ sourceLabel(item) }}</span>
                <small>{{ t("memory.updatedAt") }} {{ formatDateTime(item.updatedAt) }}</small>
                <small v-if="item.lastUsedAt">· {{ t("memory.lastUsed") }} {{ formatDateTime(item.lastUsedAt) }}</small>
                <small v-if="item.expiresAt">· {{ t("memory.expiresAt") }} {{ formatDateTime(item.expiresAt) }}</small>
              </div>
            </div>
            <div class="memory-item__actions">
              <button class="button" type="button" @click="startEdit(item)">{{ t("common.edit") }}</button>
              <button class="button button--danger" type="button" :disabled="deleteMutation.isPending.value" @click="removeItem(item)">
                {{ t("common.delete") }}
              </button>
            </div>
          </template>
        </li>
      </ul>
      <EmptyState v-else :text="t('memory.empty')" />
    </BaseCard>
  </div>
</template>

<style scoped>
.memory-page {
  display: grid;
  gap: 18px;
  max-width: 980px;
}
.memory-disabled {
  padding: 10px 14px;
  border-radius: 10px;
  background: #fef3c7;
  color: #92400e;
  font-size: 13px;
}
.memory-form,
.memory-edit {
  display: flex;
  gap: 10px;
  align-items: center;
}
.memory-form .wide-input,
.memory-edit .wide-input {
  flex: 1;
}
.memory-form select,
.memory-edit select {
  padding: 10px 11px;
  border: 1px solid var(--border-color);
  border-radius: 9px;
  background: #fff;
}
.memory-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-bottom: 14px;
}
.memory-list {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.memory-item {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 13px 14px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: #fff;
}
.memory-item__main {
  min-width: 0;
}
.memory-item__content {
  font-size: 15px;
  line-height: 1.55;
  word-break: break-word;
}
.memory-item__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  color: var(--color-text-muted);
  font-size: 12px;
}
.memory-item__actions {
  display: flex;
  flex-shrink: 0;
  align-items: flex-start;
  gap: 8px;
}
.memory-page--mobile .memory-form,
.memory-page--mobile .memory-edit,
.memory-page--mobile .memory-item {
  flex-direction: column;
  align-items: stretch;
}
.memory-page--mobile .memory-filters {
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: 4px;
}
.memory-page--mobile .memory-filters .tab {
  flex-shrink: 0;
}
.memory-page--mobile .memory-item__actions .button {
  flex: 1;
}
</style>
