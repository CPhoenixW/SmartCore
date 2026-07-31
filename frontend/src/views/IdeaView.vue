<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import MarkdownContent from "@/components/base/MarkdownContent.vue";
import ImageViewer from "@/components/base/ImageViewer.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import { ideaApi } from "@/api/idea";
import { useToast } from "@/composables/useToast";
import type { Idea, IdeaAttachment, IdeaMediaJob, IdeaUpload } from "@/types/idea";
import { formatDateTime } from "@/utils/date";

type UploadState = "ready" | "queued" | "processing" | "ocr_ready" | "failed";
type StagedUpload = IdeaUpload & {
  jobId?: string;
  stat: UploadState;
  summary?: string;
  errorMessage?: string;
};

const { t, locale } = useI18n();
const toast = useToast();
const queryClient = useQueryClient();
const selected = ref<Idea | null>(null);
const editing = ref(true);
const title = ref("");
const description = ref("");
const uploads = ref<StagedUpload[]>([]);
const removedAttachmentIds = ref<string[]>([]);
const dragging = ref(false);
const processing = ref(false);
const lightbox = ref<IdeaAttachment | null>(null);
const query = useQuery({ queryKey: ["ideas"], queryFn: ideaApi.list });
const items = computed(() => [...(query.data.value ?? [])].sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt))));
const visibleAttachments = computed(() => selected.value?.attachments.filter((item) => !removedAttachmentIds.value.includes(item.attachmentId)) ?? []);
const hasMedia = computed(() => uploads.value.length > 0);
const hasBlockingUploads = computed(() => uploads.value.some((item) => item.stat !== "ready"));

function choose(idea: Idea) {
  selected.value = idea;
  editing.value = false;
  title.value = idea.title;
  description.value = idea.description;
  uploads.value = [];
  removedAttachmentIds.value = [];
}

function reset() {
  selected.value = null;
  editing.value = true;
  title.value = "";
  description.value = "";
  uploads.value = [];
  removedAttachmentIds.value = [];
  processing.value = false;
  lightbox.value = null;
}

function startEdit() {
  if (!selected.value) return;
  title.value = selected.value.title;
  description.value = selected.value.description;
  uploads.value = [];
  removedAttachmentIds.value = [];
  editing.value = true;
}

function cancelEdit() {
  if (!selected.value) return;
  choose(selected.value);
}

function attachmentLabel(idea: Idea) {
  const images = idea.attachments.filter((item) => item.mimeType.startsWith("image/")).length;
  return images ? `🖼️ ${images} ${t("ideas.images")}` : `📎 ${idea.attachments.length} ${t("ideas.attachments")}`;
}

function displayTime(value?: string | null) {
  return formatDateTime(value, locale.value === "en-US" ? "en-US" : "zh-CN");
}

function markAttachmentRemoved(id: string) {
  if (!removedAttachmentIds.value.includes(id)) removedAttachmentIds.value.push(id);
}

function restoreAttachment(id: string) {
  removedAttachmentIds.value = removedAttachmentIds.value.filter((item) => item !== id);
}

function applyJob(upload: StagedUpload, job: IdeaMediaJob) {
  upload.jobId = job.jobId;
  upload.stat = job.stat === "consumed" ? "ready" : job.stat;
  upload.summary = job.summary ?? upload.summary;
  upload.errorMessage = job.errorMessage ?? undefined;
}

async function pollMediaJob(upload: StagedUpload) {
  if (!upload.jobId) return;
  for (let attempt = 0; attempt < 240; attempt += 1) {
    const job = await ideaApi.getMediaJob(upload.jobId);
    applyJob(upload, job);
    if (job.stat === "ready" || job.stat === "failed") return;
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  upload.stat = "failed";
  upload.errorMessage = t("ideas.processingTimeout");
}

async function startMediaJob(upload: StagedUpload) {
  if (!selected.value) return;
  upload.stat = "queued";
  const job = await ideaApi.createMediaJob({
    ideaId: selected.value.ideaId,
    uploadId: upload.uploadId,
    contextText: `${title.value}\n${description.value}`.trim(),
  });
  applyJob(upload, job);
  await pollMediaJob(upload);
}

async function retryMediaJob(upload: StagedUpload) {
  if (!upload.jobId) return;
  try {
    applyJob(upload, await ideaApi.retryMediaJob(upload.jobId));
    await pollMediaJob(upload);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : t("ideas.uploadFailed"));
  }
}

async function addFiles(files: FileList | File[]) {
  const values = Array.from(files);
  if (!values.length) return;
  const existingCount = visibleAttachments.value.length + uploads.value.length;
  if (existingCount + values.length > 10) {
    toast.error(t("ideas.tooManyAttachments"));
    return;
  }
  try {
    const added = await ideaApi.upload(values);
    if (!selected.value) {
      processing.value = true;
      await ideaApi.processMedia({ uploadIds: added.map((file) => file.uploadId), text: description.value });
      title.value = "";
      description.value = "";
      toast.success(t("ideas.processing"));
      window.setTimeout(async () => {
        await queryClient.invalidateQueries({ queryKey: ["ideas"] });
        processing.value = false;
      }, 5000);
      return;
    }
    const staged = added.map<StagedUpload>((item) => ({ ...item, stat: "ready" }));
    uploads.value.push(...staged);
    await Promise.all(staged.filter((item) => item.mimeType.startsWith("image/")).map(startMediaJob));
  } catch (error) {
    toast.error(error instanceof Error ? error.message : t("ideas.uploadFailed"));
    processing.value = false;
  }
}

async function discardUpload(upload: StagedUpload) {
  try { await ideaApi.deleteUpload(upload.uploadId); } catch { /* Expiry cleanup is the fallback. */ }
  uploads.value = uploads.value.filter((item) => item.uploadId !== upload.uploadId);
}

function addSummary(upload: StagedUpload) {
  const summary = upload.summary?.trim();
  if (!summary) return;
  const block = `### ${t("ideas.attachmentSummary")}\n${summary}`;
  if (!description.value.includes(block)) description.value = `${description.value.trim()}\n\n${block}`.trim();
}

const save = useMutation({
  mutationFn: () => selected.value
    ? ideaApi.update(selected.value.ideaId, {
        expectedRevision: selected.value.revision,
        title: title.value,
        description: description.value,
        addUploadIds: uploads.value.map((item) => item.uploadId),
        removeAttachmentIds: removedAttachmentIds.value,
      })
    : ideaApi.create({ title: title.value, description: description.value, uploadIds: uploads.value.map((item) => item.uploadId) }),
  onSuccess: async () => {
    reset();
    await queryClient.invalidateQueries({ queryKey: ["ideas"] });
    toast.success(t("ideas.saved"));
  },
  onError: (error) => toast.error(error instanceof Error ? error.message : t("ideas.saveFailed")),
});

const remove = useMutation({
  mutationFn: (id: string) => ideaApi.remove(id),
  onSuccess: async () => { reset(); await queryClient.invalidateQueries({ queryKey: ["ideas"] }); },
});
</script>

<template>
  <div class="dual-scroll-page idea-workspace">
    <PageHeader :title="t('ideas.title')" :subtitle="t('ideas.subtitle')"><template #actions><button class="button button--primary" @click="reset">{{ t("ideas.new") }}</button></template></PageHeader>
    <section class="idea-layout">
      <div class="idea-list-pane">
        <BaseCard :title="`${t('ideas.title')} · ${items.length}`">
          <div class="idea-cards">
            <button v-for="idea in items" :key="idea.ideaId" class="idea-card" :class="{ selected: selected?.ideaId === idea.ideaId }" @click="choose(idea)">
              <strong>{{ idea.title }}</strong><p>{{ idea.description || t("ideas.noDescription") }}</p>
              <footer><span v-if="idea.attachments.length">{{ attachmentLabel(idea) }}</span><time :datetime="idea.createdAt">{{ displayTime(idea.createdAt) }}</time></footer>
            </button>
            <EmptyState v-if="!items.length" />
          </div>
        </BaseCard>
      </div>
      <aside class="idea-detail"><div class="stack">
        <BaseCard v-if="selected && !editing" :title="t('ideas.detail')">
          <template #actions><button class="button" type="button" @click="startEdit">{{ t("ideas.edit") }}</button></template>
          <template v-if="selected">
            <header class="idea-detail-header">
              <div><h2>{{ selected.title }}</h2><time class="idea-time" :datetime="selected.createdAt">{{ displayTime(selected.createdAt) }}</time></div>
              <span v-if="selected.attachments.length" class="idea-attachment-count">{{ attachmentLabel(selected) }}</span>
            </header>
            <section class="idea-detail-copy"><MarkdownContent :content="selected.description" /></section>
            <section v-if="selected.attachments.length" class="idea-attachment-section" :aria-label="t('ideas.existingAttachments')">
              <h3>{{ t("ideas.existingAttachments") }}</h3>
              <div class="attachment-grid">
                <template v-for="file in selected.attachments" :key="file.attachmentId">
                  <div v-if="file.mimeType.startsWith('image/')" class="image-file">
                    <button class="image-thumb" :aria-label="t('ideas.enlargeImage', { name: file.fileName })" @click="lightbox = file"><img :src="file.url" :alt="file.fileName" /></button>
                    <div class="image-file__meta"><span>{{ file.fileName }}</span><a :href="file.url" class="attachment-download" download>{{ t("ideas.download") }}</a></div>
                  </div>
                  <a v-else :href="file.url" class="document-file" download>📄 {{ file.fileName }} · {{ t("ideas.download") }}</a>
                </template>
              </div>
            </section>
            <div class="idea-danger-zone"><button class="button button--danger" @click="remove.mutate(selected.ideaId)">{{ t("common.delete") }}</button></div>
          </template>
        </BaseCard>

        <BaseCard v-else :title="selected ? t('ideas.edit') : t('ideas.new')">
          <form class="form-grid" @submit.prevent="save.mutate()">
            <label class="field field--wide"><span>{{ t("ideas.titleLabel") }}</span><input v-model="title" :placeholder="t('ideas.titlePlaceholder')" :required="!hasMedia" /></label>
            <label class="field field--wide"><span>{{ t("ideas.description") }}</span><textarea v-model="description" rows="7" :placeholder="t('ideas.descriptionPlaceholder')" /></label>

            <section v-if="selected?.attachments.length" class="attachment-editor field--wide" :aria-label="t('ideas.existingAttachments')">
              <strong>{{ t("ideas.existingAttachments") }}</strong>
              <div v-for="file in selected.attachments" :key="file.attachmentId" class="attachment-edit-row" :class="{ removed: removedAttachmentIds.includes(file.attachmentId) }">
                <span>{{ file.mimeType.startsWith("image/") ? "🖼️" : "📄" }} {{ file.fileName }}</span>
                <button v-if="!removedAttachmentIds.includes(file.attachmentId)" type="button" class="icon-action icon-action--danger" :title="t('ideas.removeAttachment')" :aria-label="t('ideas.removeAttachment')" @click="markAttachmentRemoved(file.attachmentId)">×</button>
                <button v-else type="button" class="icon-action" :title="t('ideas.undoRemove')" :aria-label="t('ideas.undoRemove')" @click="restoreAttachment(file.attachmentId)">↶</button>
              </div>
            </section>

            <div class="drop-zone field--wide" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave="dragging = false" @drop.prevent="dragging = false; addFiles($event.dataTransfer?.files || [])">
              <input type="file" multiple accept="image/png,image/jpeg,image/webp,application/pdf,text/plain,application/zip" @change="addFiles(($event.target as HTMLInputElement).files || [])" />
              <span>{{ t("ideas.drop") }}</span>
            </div>

            <section v-if="uploads.length" class="staged-uploads field--wide" :aria-label="t('ideas.newAttachments')">
              <strong>{{ t("ideas.newAttachments") }}</strong>
              <div v-for="file in uploads" :key="file.uploadId" class="staged-upload">
                <div><span>{{ file.mimeType.startsWith("image/") ? "🖼️" : "📄" }} {{ file.fileName }}</span><small :class="`media-stat media-stat--${file.stat}`">{{ t(`ideas.mediaStatus.${file.stat}`) }}</small></div>
                <button type="button" class="icon-action icon-action--danger" :title="t('ideas.removeAttachment')" :aria-label="t('ideas.removeAttachment')" @click="discardUpload(file)">×</button>
                <div v-if="file.summary" class="media-summary"><textarea v-model="file.summary" rows="2" /><button type="button" class="button" @click="addSummary(file)">{{ t("ideas.addSummary") }}</button></div>
                <div v-if="file.stat === 'failed'" class="media-recovery"><small class="field-error">{{ file.errorMessage }}</small><button type="button" class="button" @click="retryMediaJob(file)">{{ t("ideas.retryProcessing") }}</button></div>
              </div>
            </section>

            <small v-if="processing" class="field--wide">{{ t("ideas.processing") }}</small>
            <div class="form-actions field--wide">
              <button v-if="selected" class="button" type="button" @click="cancelEdit">{{ t("common.cancel") }}</button>
              <button class="button button--primary" :disabled="save.isPending.value || processing || hasBlockingUploads || (!title.trim() && !hasMedia)">{{ t("common.save") }}</button>
            </div>
          </form>
        </BaseCard>
      </div></aside>
    </section>
    <ImageViewer v-if="lightbox" :src="lightbox.url" :alt="lightbox.fileName" :file-name="lightbox.fileName" @close="lightbox = null" />
  </div>
</template>
