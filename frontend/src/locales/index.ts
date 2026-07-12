import { createI18n } from "vue-i18n";
import enUS from "./en-US.json";
import zhCN from "./zh-CN.json";

const messages = {
  "zh-CN": {
    ...zhCN,
    device: {
      ...zhCN.device,
      state: { working: "工作中", away: "离开", offline: "离线", unknown: "未知" },
    },
  },
  "en-US": {
    ...enUS,
    device: {
      ...enUS.device,
      state: { working: "Working", away: "Away", offline: "Offline", unknown: "Unknown" },
    },
  },
};

export const i18n = createI18n({ legacy: false, locale: "zh-CN", fallbackLocale: "zh-CN", messages });
