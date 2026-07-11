import { createI18n } from "vue-i18n";

import enUS from "./en-US.json";
import zhCN from "./zh-CN.json";

const storedLocale = window.localStorage.getItem("smartcore.locale");

export default createI18n({
  legacy: false,
  locale: storedLocale === "en-US" ? "en-US" : "zh-CN",
  fallbackLocale: "zh-CN",
  messages: {
    "zh-CN": zhCN,
    "en-US": enUS,
  },
});
