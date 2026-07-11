import { createRouter, createWebHistory } from "vue-router";

import MigrationStatusView from "@/views/MigrationStatusView.vue";
import OverviewView from "@/views/OverviewView.vue";

const router = createRouter({
  history: createWebHistory("/work-v2/"),
  routes: [
    { path: "/", name: "overview", component: OverviewView },
    { path: "/add", name: "add", component: MigrationStatusView, props: { legacyPath: "/work/add" } },
    { path: "/update", name: "update", component: MigrationStatusView, props: { legacyPath: "/work/update" } },
    { path: "/course", name: "course", component: MigrationStatusView, props: { legacyPath: "/work/course" } },
    { path: "/device", name: "device", component: MigrationStatusView, props: { legacyPath: "/work/device" } },
    { path: "/ideas", name: "ideas", component: MigrationStatusView, props: { legacyPath: "/work/inspire" } },
    { path: "/logs", name: "logs", component: MigrationStatusView, props: { legacyPath: "/work/log" } },
    { path: "/settings", name: "settings", component: MigrationStatusView, props: { legacyPath: "/work/settings" } },
    { path: "/:pathMatch(.*)*", redirect: "/" }
  ],
});

export default router;
