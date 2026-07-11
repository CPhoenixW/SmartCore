<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { Idea } from "@/types/idea";

const { t } = useI18n(); const toast = useToast(); const queryClient = useQueryClient();
const filter = ref<"open" | "handled" | "all">("open"); const selected = ref<Idea | null>(null); const content = ref("");
const query = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const items = computed(() => (query.data.value ?? []).filter((idea) => filter.value === "all" || (filter.value === "handled") === idea.handled));
watch(selected, (idea) => { content.value = idea?.content ?? ""; });
const save = useMutation({ mutationFn: () => selected.value ? ideaApi.update(selected.value.ideaId, { content: content.value }) : ideaApi.create(content.value), onSuccess: async () => { toast.success(t("ideas.saved")); selected.value = null; content.value = ""; await queryClient.invalidateQueries({ queryKey: ["ideas"] }); } });
const toggle = useMutation({ mutationFn: (idea: Idea) => ideaApi.update(idea.ideaId, { handled: !idea.handled }), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ideas"] }) });
const remove = useMutation({ mutationFn: (id: string) => ideaApi.remove(id), onSuccess: async () => { selected.value = null; content.value = ""; await queryClient.invalidateQueries({ queryKey: ["ideas"] }); } });
</script>
<template>
  <section class="page-heading"><div><h1>{{ t("ideas.title") }}</h1><p>{{ t("ideas.subtitle") }}</p></div></section>
  <section class="editor-layout"><BaseCard :title="t('ideas.title')"><template #actions><select v-model="filter"><option value="open">{{ t("ideas.open") }}</option><option value="handled">{{ t("ideas.handled") }}</option><option value="all">{{ t("common.all") }}</option></select></template><div class="idea-list"><article v-for="idea in items" :key="idea.ideaId" :class="{ handled: idea.handled }"><button @click="selected = idea"><strong>{{ idea.content }}</strong><small>{{ idea.createdAt }}</small></button><button class="icon-button" @click="toggle.mutate(idea)">✓</button></article><EmptyState v-if="!items.length" /></div></BaseCard><BaseCard :title="selected ? t('common.edit') : t('ideas.new')"><form class="form-grid" @submit.prevent="save.mutate()"><label class="field field--wide"><span>{{ t("ideas.content") }}</span><textarea v-model="content" rows="10" required /></label><div class="form-actions field--wide"><button class="button button--primary" type="submit">{{ t("common.save") }}</button><button v-if="selected" class="button button--danger" type="button" @click="remove.mutate(selected.ideaId)">{{ t("common.delete") }}</button></div></form></BaseCard></section>
</template>
