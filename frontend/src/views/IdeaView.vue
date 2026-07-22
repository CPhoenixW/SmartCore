<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import MarkdownContent from "@/components/base/MarkdownContent.vue";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { Idea, IdeaUpload } from "@/types/idea";

const { t } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const selected = ref<Idea | null>(null);
const title = ref("");
const description = ref("");
const uploads = ref<IdeaUpload[]>([]);
const dragging = ref(false);
const processing = ref(false);
const lightbox = ref<string | null>(null);
const query = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const items = computed(() => [...(query.data.value ?? [])].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))));
const hasMedia = computed(() => uploads.value.length > 0);

function choose(idea: Idea) { selected.value = idea; title.value = idea.title; description.value = idea.description; uploads.value = []; }
function reset() { selected.value = null; title.value = ""; description.value = ""; uploads.value = []; processing.value = false; }
function attachmentLabel(idea: Idea) {
  const images = idea.attachments.filter((item) => item.mimeType.startsWith("image/")).length;
  return images ? `🖼️ ${images} ${t("ideas.images")}` : `📎 ${idea.attachments.length} ${t("ideas.attachments")}`;
}
async function refreshLater() {
  window.setTimeout(async () => { await queryClient.invalidateQueries({ queryKey: ["ideas"] }); processing.value = false; }, 5000);
}
async function addFiles(files: FileList | File[]) {
  try {
    const added = await ideaApi.upload(Array.from(files));
    uploads.value.push(...added);
    if (!selected.value && added.length && uploads.value.length === added.length) {
      processing.value = true;
      await ideaApi.processMedia({ uploadIds: uploads.value.map((file) => file.uploadId), text: description.value });
      uploads.value = [];
      title.value = "";
      description.value = "";
      toast.success(t("ideas.processing"));
      await refreshLater();
    }
  } catch (error) { toast.error(error instanceof Error ? error.message : t("ideas.uploadFailed")); processing.value = false; }
}
const save = useMutation({
  mutationFn: () => selected.value
    ? ideaApi.update(selected.value.ideaId, { title: title.value, description: description.value })
    : ideaApi.create({ title: title.value, description: description.value, uploadIds: uploads.value.map((item) => item.uploadId) }),
  onSuccess: async () => { reset(); await queryClient.invalidateQueries({ queryKey: ["ideas"] }); toast.success(t("ideas.saved")); },
});
const remove = useMutation({ mutationFn: (id: string) => ideaApi.remove(id), onSuccess: async () => { reset(); await queryClient.invalidateQueries({ queryKey: ["ideas"] }); } });
</script>

<template>
  <div class="dual-scroll-page idea-workspace">
    <section class="page-heading"><div><h1>{{ t("ideas.title") }}</h1><p>{{ t("ideas.subtitle") }}</p></div><button class="button button--primary" @click="reset">{{ t("ideas.new") }}</button></section>
    <section class="idea-layout">
      <div class="idea-list-pane"><BaseCard :title="`${t('ideas.title')} · ${items.length}`"><div class="idea-cards">
        <button v-for="idea in items" :key="idea.ideaId" class="idea-card" :class="{ selected: selected?.ideaId === idea.ideaId }" @click="choose(idea)">
          <strong>{{ idea.title }}</strong><p>{{ idea.description || t("ideas.noDescription") }}</p><footer><span v-if="idea.attachments.length">{{ attachmentLabel(idea) }}</span><time>{{ idea.createdAt }}</time></footer>
        </button><EmptyState v-if="!items.length" />
      </div></BaseCard></div>
      <aside class="idea-detail"><div class="stack">
        <BaseCard :title="t('ideas.detail')"><template v-if="selected"><h2>{{ selected.title }}</h2><time class="idea-time">{{ selected.createdAt }}</time><MarkdownContent :content="selected.description" />
          <div class="attachment-grid"><template v-for="file in selected.attachments" :key="file.attachmentId"><button v-if="file.mimeType.startsWith('image/')" class="image-thumb" @click="lightbox = file.url"><img :src="file.url" :alt="file.fileName" /></button><a v-else :href="file.url" class="document-file" download>📄 {{ file.fileName }}</a></template></div>
          <div class="form-actions"><button class="button button--danger" @click="remove.mutate(selected.ideaId)">{{ t("common.delete") }}</button></div>
        </template><EmptyState v-else :text="t('ideas.select')" /></BaseCard>
        <BaseCard :title="selected ? t('ideas.edit') : t('ideas.new')"><form class="form-grid" @submit.prevent="save.mutate()">
          <label class="field field--wide"><span>{{ t("ideas.titleLabel") }}</span><input v-model="title" :placeholder="t('ideas.titlePlaceholder')" :required="!hasMedia" /></label>
          <label class="field field--wide"><span>{{ t("ideas.description") }}</span><textarea v-model="description" rows="7" :placeholder="t('ideas.descriptionPlaceholder')" /></label>
          <div v-if="!selected" class="drop-zone field--wide" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dragging = false; addFiles($event.dataTransfer?.files || [])"><input type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain,application/zip" @change="addFiles(($event.target as HTMLInputElement).files || [])" /><span>{{ t("ideas.drop") }}</span><small v-for="file in uploads" :key="file.uploadId">📎 {{ file.fileName }}</small><small v-if="processing">{{ t("ideas.processing") }}</small></div>
          <div class="form-actions field--wide"><button class="button button--primary" :disabled="save.isPending.value || processing || (!title.trim() && !hasMedia)">{{ t("common.save") }}</button></div>
        </form></BaseCard>
      </div></aside>
    </section>
    <div v-if="lightbox" class="lightbox" @click="lightbox = null"><img :src="lightbox" :alt="t('ideas.imagePreview')" /></div>
  </div>
</template>
