import { createApp } from "vue";

import App from "./App.vue";
import i18n from "./locales";
import router from "./router";
import "./styles/reset.css";
import "./styles/tokens.css";
import "./styles/global.css";

createApp(App).use(router).use(i18n).mount("#app");
