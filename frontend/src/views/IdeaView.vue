<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { Idea } from "@/types/idea";

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const filter = ref<"open" | "handled" | "all">("open");
const search = ref("");
const selected = ref<Idea | null>(null);
const content = ref("");
const handled = ref(false);
const query = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });

const items = computed(() => (query.data.value ?? [])
  .filter((idea) => filter.value === "all" || (filter.value === "handled") === idea.handled)
  .filter((idea) => !search.value.trim() || idea.content.toLowerCase().includes(search.value.trim().toLowerCase()))
  .sort((a, b) => String(b.createdAt ?? "").localeCompare(String(a.createdAt ?? ""))));

watch(selected, (idea) => { content.value = idea?.content ?? ""; handled.value = Boolean(idea?.handled); });
function reset() { selected.value = null; content.value = ""; handled.value = false; }

const save = useMutation({
  mutationFn: () => selected.value
    ? ideaApi.update(selected.value.ideaId, { content: content.value.trim(), handled: handled.value })
    : ideaApi.create(content.value.trim()),
  onSuccess: async () => { toast.success(t("ideas.saved")); reset(); await queryClient.invalidateQueries({ queryKey: ["ideas"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const toggle = useMutation({
  mutationFn: (idea: Idea) => ideaApi.update(idea.ideaId, { handled: !idea.handled }),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ideas"] }),
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const remove = useMutation({
  mutationFn: (id: string) => ideaApi.remove(id),
  onSuccess: async () => { reset(); await queryClient.invalidateQueries({ queryKey: ["ideas"] }); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const busy = computed(() => save.isPending.value || toggle.isPending.value || remove.isPending.value);
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("ideas.title") }}</h1><p>{{ t("ideas.subtitle") }}</p></div><button class="button button--primary" @click="reset">{{ t("ideas.new") }}</button></section>
  <section class="editor-layout">
    <BaseCard :title="`${t('ideas.title')} · ${items.length}`"><template #actions><div class="inline-filters"><input v-model="search" class="compact-search" :placeholder="t('common.search')" /><select v-model="filter"><option value="open">{{ t("ideas.open") }}</option><option value="handled">{{ t("ideas.handled") }}</option><option value="all">{{ t("common.all") }}</option></select></div></template><div class="idea-list"><article v-for="idea in items" :key="idea.ideaId" :class="{ handled: idea.handled, selected: selected?.ideaId === idea.ideaId }"><button @click="selected = idea"><strong>{{ idea.content }}</strong><small>{{ idea.createdAt }}</small></button><button class="icon-button" :disabled="busy" :title="idea.handled ? '标记为未处理' : '标记为已处理'" @click="toggle.mutate(idea)">✓</button></article><EmptyState v-if="!items.length" /></div></BaseCard>
    <BaseCard :title="selected ? t('common.edit') : t('ideas.new')"><form class="form-grid" @submit.prevent="save.mutate()"><label class="field field--wide"><span>{{ t("ideas.content") }}</span><textarea v-model="content" rows="10" required /></label><label v-if="selected" class="check-field field--wide"><input v-model="handled" type="checkbox" />{{ t("ideas.handled") }}</label><div class="form-actions field--wide"><button class="button button--primary" type="submit" :disabled="busy || !content.trim()">{{ t("common.save") }}</button><button v-if="selected" class="button button--danger" type="button" :disabled="busy" @click="remove.mutate(selected.ideaId)">{{ t("common.delete") }}</button></div></form></BaseCard>
  </section>
</template>
