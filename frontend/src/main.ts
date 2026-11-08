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

if (import.meta.env.PROD) {
  // A long-lived tab can still have the previous Vite entry chunk in memory
  // when a deploy removes its old hashed lazy chunk. Reload once so navigation
  // cannot leave the user on a blank route after a release.
  const assetReloadKey = "smartcore:asset-reload-once";
  window.addEventListener("vite:preloadError", (event) => {
    event.preventDefault();
    if (sessionStorage.getItem(assetReloadKey) === "1") return;
    sessionStorage.setItem(assetReloadKey, "1");
    window.location.reload();
  });
  window.addEventListener("load", () => sessionStorage.removeItem(assetReloadKey), { once: true });
}

createApp(App).use(createPinia()).use(i18n).use(VueQueryPlugin).use(router).mount("#app");

if (import.meta.env.PROD && "serviceWorker" in navigator) {
  void navigator.serviceWorker.register("/work/sw.js", { scope: "/work/" });
}
