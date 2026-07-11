import { createRouter, createWebHistory } from "vue-router";
import WorkLayout from "@/layouts/WorkLayout.vue";

export const router = createRouter({
  history: createWebHistory("/work/"),
  routes: [{ path: "/", component: WorkLayout, children: [
    { path: "", name: "overview", component: () => import("@/views/OverviewView.vue") },
    { path: "add", name: "add", component: () => import("@/views/AddEventView.vue") },
    { path: "update", name: "update", component: () => import("@/views/UpdateEventView.vue") },
    { path: "course", name: "course", component: () => import("@/views/CourseView.vue") },
    { path: "device", name: "device", component: () => import("@/views/DeviceView.vue") },
    { path: "ideas", name: "ideas", component: () => import("@/views/IdeaView.vue") },
    { path: "logs", name: "logs", component: () => import("@/views/LogView.vue") },
    { path: "settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
  ] }, { path: "/:pathMatch(.*)*", component: () => import("@/views/NotFoundView.vue") }],
});
