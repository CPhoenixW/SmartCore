<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import { useToast } from "@/composables/useToast";
import { useUserStore } from "@/stores/user";
import type { CurrentUser } from "@/types/user";

const { t } = useI18n();
const store = useUserStore();
const toast = useToast();
const form = reactive<CurrentUser>({ displayName: "", language: "zh", reminderChannel: "screen", avatarUrl: "" });
const saving = ref(false);
const uploading = ref(false);
const localPreview = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
watch(() => store.user, (user) => Object.assign(form, user), { immediate: true, deep: true });
const initials = computed(() => form.displayName.trim().slice(0, 2).toUpperCase() || "SC");
const previewUrl = computed(() => localPreview.value || form.avatarUrl || "");

async function save() {
  if (!form.displayName.trim() || saving.value) return;
  saving.value = true;
  try {
    await store.save({ ...form, displayName: form.displayName.trim(), avatarUrl: form.avatarUrl?.trim() || null });
    toast.success(t("settings.saved"));
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  } finally {
    saving.value = false;
  }
}

async function uploadAvatar(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    toast.error(t("settings.avatarTypeError"));
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    toast.error(t("settings.avatarSizeError"));
    return;
  }
  if (localPreview.value) URL.revokeObjectURL(localPreview.value);
  localPreview.value = URL.createObjectURL(file);
  uploading.value = true;
  try {
    const avatarUrl = await store.uploadAvatar(file);
    form.avatarUrl = avatarUrl ?? "";
    toast.success(t("settings.avatarUploaded"));
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  } finally {
    uploading.value = false;
    if (localPreview.value) URL.revokeObjectURL(localPreview.value);
    localPreview.value = "";
  }
}

function clearAvatar() {
  form.avatarUrl = "";
  localPreview.value = "";
}
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("settings.title") }}</h1><p>{{ t("settings.subtitle") }}</p></div></section>
  <section class="form-layout">
    <BaseCard :title="t('settings.title')">
      <form class="form-grid" @submit.prevent="save">
        <label class="field field--wide"><span>{{ t("settings.displayName") }}</span><input v-model="form.displayName" required /></label>
        <label class="field"><span>{{ t("settings.language") }}</span><select v-model="form.language"><option value="zh">{{ t("settings.chinese") }}</option><option value="en">English</option></select></label>
        <label class="field"><span>{{ t("settings.reminderChannel") }}</span><select v-model="form.reminderChannel"><option value="screen">{{ t("settings.screenReminder") }}</option><option value="feishu">{{ t("settings.feishuReminder") }}</option></select></label>
        <div class="field field--wide">
          <span>{{ t("settings.avatarUpload") }}</span>
          <div class="avatar-upload-row">
            <input ref="fileInput" class="visually-hidden" type="file" accept="image/jpeg,image/png,image/gif,image/webp" @change="uploadAvatar" />
            <button class="button" type="button" :disabled="uploading" @click="fileInput?.click()">{{ uploading ? t("settings.uploading") : t("settings.chooseImage") }}</button>
            <button class="button button--ghost" type="button" :disabled="!previewUrl" @click="clearAvatar">{{ t("settings.removeAvatar") }}</button>
            <small>{{ t("settings.avatarHint") }}</small>
          </div>
        </div>
        <label class="field field--wide"><span>{{ t("settings.avatarUrl") }}</span><input v-model="form.avatarUrl" :placeholder="t('settings.avatarUrlPlaceholder')" /></label>
        <div class="form-actions field--wide"><button class="button button--primary" type="submit" :disabled="saving || uploading">{{ saving ? t("common.saving") : t("common.save") }}</button></div>
      </form>
    </BaseCard>
    <BaseCard :title="t('settings.avatarPreview')"><div class="profile-preview"><div class="avatar large"><img v-if="previewUrl" :src="previewUrl" :alt="t('settings.avatarPreview')" /><span v-else>{{ initials }}</span></div><strong>{{ form.displayName || 'SmartCore' }}</strong><span>{{ form.language === 'en' ? 'English' : t('settings.chinese') }} · {{ form.reminderChannel === 'feishu' ? t('settings.feishuReminder') : t('settings.screenReminder') }}</span></div></BaseCard>
  </section>
</template>
