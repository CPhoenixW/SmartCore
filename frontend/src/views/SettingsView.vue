<script setup lang="ts">
import { reactive, watch } from "vue";
import { useI18n } from "vue-i18n";
import BaseCard from "@/components/base/BaseCard.vue";
import { useToast } from "@/composables/useToast";
import { useUserStore } from "@/stores/user";
import type { CurrentUser } from "@/types/user";
const { t } = useI18n(); const store = useUserStore(); const toast = useToast();
const form = reactive<CurrentUser>({ displayName: "", language: "zh", reminderChannel: "screen", avatarUrl: "" });
watch(() => store.user, (user) => Object.assign(form, user), { immediate: true, deep: true });
async function save() { await store.save(form); toast.success(t("settings.saved")); }
</script>
<template><section class="page-heading"><div><h1>{{ t("settings.title") }}</h1><p>{{ t("settings.subtitle") }}</p></div></section><section class="form-layout"><BaseCard :title="t('settings.title')"><form class="form-grid" @submit.prevent="save"><label class="field field--wide"><span>{{ t("settings.displayName") }}</span><input v-model="form.displayName" required /></label><label class="field"><span>{{ t("settings.language") }}</span><select v-model="form.language"><option value="zh">中文</option><option value="en">English</option></select></label><label class="field"><span>{{ t("settings.reminderChannel") }}</span><select v-model="form.reminderChannel"><option value="screen">Screen</option><option value="feishu">Feishu</option></select></label><label class="field field--wide"><span>{{ t("settings.avatar") }}</span><input v-model="form.avatarUrl" /></label><div class="form-actions field--wide"><button class="button button--primary" type="submit">{{ t("common.save") }}</button></div></form></BaseCard><BaseCard title="Preview"><div class="profile-preview"><div class="avatar large"><img v-if="form.avatarUrl" :src="form.avatarUrl" alt="" /><span v-else>{{ form.displayName.slice(0, 2).toUpperCase() || 'SC' }}</span></div><strong>{{ form.displayName }}</strong><span>{{ form.language }} · {{ form.reminderChannel }}</span></div></BaseCard></section></template>
