import { defineStore } from "pinia";
import { ref } from "vue";
import { userApi } from "@/api/user";
import { i18n } from "@/locales";
import type { CurrentUser } from "@/types/user";

const fallback: CurrentUser = { displayName: "SmartCore", language: "zh", reminderChannel: "screen", avatarUrl: null };

export const useUserStore = defineStore("user", () => {
  const user = ref<CurrentUser>({ ...fallback });
  const loaded = ref(false);
  async function load() {
    try { user.value = await userApi.me(); } catch { user.value = { ...fallback }; }
    i18n.global.locale.value = user.value.language === "en" ? "en-US" : "zh-CN";
    loaded.value = true;
  }
  async function save(payload: Partial<CurrentUser>) {
    user.value = await userApi.update(payload);
    i18n.global.locale.value = user.value.language === "en" ? "en-US" : "zh-CN";
    return user.value;
  }
  async function uploadAvatar(file: File) {
    const result = await userApi.uploadAvatar(file);
    user.value = { ...user.value, avatarUrl: result.avatarUrl ?? null };
    return user.value.avatarUrl;
  }
  return { user, loaded, load, save, uploadAvatar };
});
