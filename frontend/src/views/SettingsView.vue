<script setup lang="ts">
import { computed, reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import { useToast } from "@/composables/useToast";
import { useUserStore } from "@/stores/user";
import type { CurrentUser } from "@/types/user";

const { t } = useI18n();
const store = useUserStore();
const toast = useToast();
const form = reactive<CurrentUser>({ displayName: "", language: "zh", reminderChannel: "screen", avatarUrl: "" });
const saving = reactive({ value: false });
watch(() => store.user, (user) => Object.assign(form, user), { immediate: true, deep: true });
const initials = computed(() => form.displayName.trim().slice(0, 2).toUpperCase() || "SC");

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
</script>

<template>
  <section class="page-heading"><div><h1>{{ t("settings.title") }}</h1><p>{{ t("settings.subtitle") }}</p></div></section>
  <section class="form-layout">
    <BaseCard :title="t('settings.title')"><form class="form-grid" @submit.prevent="save"><label class="field field--wide"><span>{{ t("settings.displayName") }}</span><input v-model="form.displayName" required /></label><label class="field"><span>{{ t("settings.language") }}</span><select v-model="form.language"><option value="zh">中文</option><option value="en">English</option></select></label><label class="field"><span>{{ t("settings.reminderChannel") }}</span><select v-model="form.reminderChannel"><option value="screen">面板提醒</option><option value="feishu">飞书提醒</option></select></label><label class="field field--wide"><span>{{ t("settings.avatar") }}</span><input v-model="form.avatarUrl" placeholder="https://..." /></label><div class="form-actions field--wide"><button class="button button--primary" type="submit" :disabled="saving.value">{{ saving.value ? t('common.loading') : t('common.save') }}</button></div></form></BaseCard>
    <BaseCard title="头像预览"><div class="profile-preview"><div class="avatar large"><img v-if="form.avatarUrl" :src="form.avatarUrl" alt="" /><span v-else>{{ initials }}</span></div><strong>{{ form.displayName || 'SmartCore' }}</strong><span>{{ form.language === 'en' ? 'English' : '中文' }} · {{ form.reminderChannel === 'feishu' ? '飞书提醒' : '面板提醒' }}</span></div></BaseCard>
  </section>
</template>
