import { createPinia } from "pinia";
import { VueQueryPlugin } from "@tanstack/vue-query";
import { createApp } from "vue";
import App from "./App.vue";
import { i18n } from "./locales";
import { router } from "./router";
import "./styles/reset.css";
import "./styles/tokens.css";
import "./styles/global.css";
import "./styles/regressions.css";
import "./styles/workbench.css";

createApp(App).use(createPinia()).use(i18n).use(VueQueryPlugin).use(router).mount("#app");

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  void navigator.serviceWorker.register("/work/sw.js", { scope: "/work/" });
}
