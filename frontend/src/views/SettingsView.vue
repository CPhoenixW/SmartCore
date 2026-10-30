<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { useMutation, useQuery } from "@tanstack/vue-query";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import PageHeader from "@/components/base/PageHeader.vue";
import EmptyState from "@/components/base/EmptyState.vue";
import { authApi } from "@/api/auth";
import { useToast } from "@/composables/useToast";
import { adminApi } from "@/api/admin";
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
const currentPassword = ref("");
const newPassword = ref("");
const passwordConfirmation = ref("");
watch(() => store.user, (user) => Object.assign(form, user), { immediate: true, deep: true });
const initials = computed(() => form.displayName.trim().slice(0, 2).toUpperCase() || "SC");
const previewUrl = computed(() => localPreview.value || form.avatarUrl || "");
const isAdmin = computed(() => store.user.role === "admin");
const adminUsers = useQuery({ queryKey: ["adminUsers"], queryFn: adminApi.users, enabled: isAdmin });
const browserSessions = useQuery({ queryKey: ["browserSessions"], queryFn: authApi.sessions });
const accountSecurityAvailable = computed(() => {
  const current = browserSessions.data.value?.find((session) => session.current);
  return Boolean(current && current.actorUserId === store.user.userId);
});
const switchUser = useMutation({
  mutationFn: (userId: string) => adminApi.switchUser(userId),
  onSuccess: async () => { await store.load(); window.location.href = "/work"; },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});
const revokeSession = useMutation({
  mutationFn: (sessionId: string) => authApi.revokeSession(sessionId),
  onSuccess: async () => { await browserSessions.refetch(); toast.success(t("settings.sessionRevoked")); },
  onError: (error) => toast.error(error instanceof Error ? error.message : String(error)),
});

function sessionDevice(userAgent: string | null) {
  if (!userAgent) return t("settings.unknownDevice");
  if (/iphone|ipad/i.test(userAgent)) return "iPhone / iPad";
  if (/android/i.test(userAgent)) return "Android";
  if (/windows/i.test(userAgent)) return "Windows";
  if (/macintosh|mac os/i.test(userAgent)) return "Mac";
  return t("settings.browserSession");
}

function sessionTime(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

async function changePassword() {
  if (newPassword.value !== passwordConfirmation.value) {
    toast.error(t("settings.passwordMismatch"));
    return;
  }
  try {
    await authApi.changePassword(currentPassword.value, newPassword.value);
    currentPassword.value = "";
    newPassword.value = "";
    passwordConfirmation.value = "";
    await browserSessions.refetch();
    toast.success(t("settings.passwordChanged"));
  } catch (error) {
    toast.error(error instanceof Error ? error.message : String(error));
  }
}

async function logoutAll() {
  try { await authApi.logoutAll(); } finally { window.location.href = "/work/login"; }
}

async function save() {
  if (!form.displayName.trim() || saving.value) return;
  saving.value = true;
  try {
    await store.save({ ...form, displayName: form.displayName.trim(), avatarUrl: form.avatarUrl?.trim() ?? "" });
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
  <PageHeader :title="t('settings.title')" :subtitle="t('settings.subtitle')" />
  <section class="settings-scroll-layout">
    <div class="settings-scroll-column" data-staged-wheel-scroll>
      <BaseCard :title="t('settings.title')">
      <form class="form-grid" @submit.prevent="save">
        <label class="field field--wide"><span>{{ t("settings.displayName") }}</span><input v-model="form.displayName" required /></label>
        <label class="field"><span>{{ t("settings.language") }}</span><select v-model="form.language"><option value="zh">{{ t("settings.chinese") }}</option><option value="en">English</option></select></label>
        <label class="field"><span>{{ t("settings.reminderChannel") }}</span><select v-model="form.reminderChannel"><option value="screen">{{ t("settings.screenReminder") }}</option></select></label>
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
      <BaseCard v-if="accountSecurityAvailable" :title="t('settings.securityTitle')" :subtitle="t('settings.securityHint')">
        <form class="form-grid" @submit.prevent="changePassword">
          <label class="field"><span>{{ t("settings.currentPassword") }}</span><input v-model="currentPassword" type="password" autocomplete="current-password" minlength="8" required /></label>
          <label class="field"><span>{{ t("settings.newPassword") }}</span><input v-model="newPassword" type="password" autocomplete="new-password" minlength="8" required /></label>
          <label class="field"><span>{{ t("settings.confirmPassword") }}</span><input v-model="passwordConfirmation" type="password" autocomplete="new-password" minlength="8" required /></label>
          <div class="form-actions"><button class="button button--primary" type="submit">{{ t("settings.changePassword") }}</button></div>
        </form>
      </BaseCard>
      <BaseCard v-if="isAdmin" :title="t('settings.adminTitle')">
        <div class="admin-user-list"><button v-for="user in adminUsers.data.value ?? []" :key="user.userId" class="admin-user-row" type="button" :disabled="switchUser.isPending.value || user.userId === store.user.userId" @click="switchUser.mutate(user.userId)"><span><strong>{{ user.displayName }}</strong><small>{{ user.loginName || user.userId }} · {{ user.role }}</small></span><span>{{ user.userId === store.user.userId ? t('settings.currentUser') : t('settings.switchUser') }}</span></button></div>
      </BaseCard>
    </div>
    <aside class="settings-scroll-column settings-scroll-column--preview" data-staged-wheel-scroll>
      <BaseCard :title="t('settings.avatarPreview')"><div class="profile-preview"><div class="avatar large"><img v-if="previewUrl" :src="previewUrl" :alt="t('settings.avatarPreview')" /><span v-else>{{ initials }}</span></div><strong>{{ form.displayName || 'SmartCore' }}</strong><span>{{ form.language === 'en' ? 'English' : t('settings.chinese') }} · {{ t('settings.screenReminder') }}</span></div></BaseCard>
      <BaseCard v-if="accountSecurityAvailable" :title="t('settings.sessionsTitle')" :subtitle="t('settings.sessionsHint')">
        <div v-if="browserSessions.data.value?.length" class="browser-session-list">
          <article v-for="session in browserSessions.data.value" :key="session.sessionId">
            <div><strong>{{ sessionDevice(session.userAgent) }} <span v-if="session.current">{{ t("settings.currentSession") }}</span></strong><small>{{ t("settings.lastSeen", { time: sessionTime(session.lastSeenAt || session.createdAt) }) }}</small></div>
            <button v-if="!session.current" class="button button--ghost" type="button" :disabled="revokeSession.isPending.value" @click="revokeSession.mutate(session.sessionId)">{{ t("settings.revokeSession") }}</button>
          </article>
        </div>
        <EmptyState v-else :text="t('settings.noSessions')" />
        <button class="button button--danger logout-all-button" type="button" @click="logoutAll">{{ t("settings.logoutAll") }}</button>
      </BaseCard>
    </aside>
  </section>
</template>

<style scoped>
.browser-session-list { display: grid; gap: 8px; }
.browser-session-list article { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 11px; border: 1px solid var(--border-color); border-radius: 9px; }
.browser-session-list strong,.browser-session-list small { display: block; }
.browser-session-list strong span { margin-left: 5px; color: var(--color-primary); font-size: 10px; }
.browser-session-list small { margin-top: 4px; color: var(--color-text-muted); font-size: 10px; }
.logout-all-button { width: 100%; margin-top: 12px; }
</style>
