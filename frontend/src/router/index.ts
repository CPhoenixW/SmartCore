import { createRouter, createWebHistory } from "vue-router";
import WorkLayout from "@/layouts/WorkLayout.vue";

export const router = createRouter({
  history: createWebHistory("/work/"),
  routes: [
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue") },
    {
      path: "/",
      component: WorkLayout,
      children: [
        { path: "", alias: "overview", name: "overview", component: () => import("@/views/OverviewView.vue") },
        { path: "assistant", name: "assistant", component: () => import("@/views/AssistantView.vue") },
        { path: "daily-summary", name: "dailySummary", component: () => import("@/views/DailySummaryView.vue") },
        { path: "add", name: "add", component: () => import("@/views/AddEventView.vue") },
        { path: "update", name: "update", component: () => import("@/views/UpdateEventView.vue") },
        { path: "course", name: "course", component: () => import("@/views/CourseView.vue") },
        {
          path: "device",
          name: "device",
          component: () => import("@/views/DeviceView.vue"),
          redirect: { name: "deviceComputer" },
          children: [
            { path: "raspberry-pi", name: "deviceRaspberryPi", component: () => import("@/views/RaspberryPiView.vue") },
            { path: "computer", name: "deviceComputer", component: () => import("@/views/ComputerView.vue") },
            { path: "screen", name: "deviceScreen", component: () => import("@/views/ScreenView.vue") },
          ],
        },
        { path: "ideas", alias: "inspire", name: "ideas", component: () => import("@/views/IdeaView.vue") },
        { path: "logs", alias: "log", name: "logs", component: () => import("@/views/LogView.vue") },
        { path: "settings", name: "settings", component: () => import("@/views/SettingsView.vue") },
      ],
    },
    { path: "/:pathMatch(.*)*", component: () => import("@/views/NotFoundView.vue") },
  ],
  scrollBehavior: () => ({ top: 0 }),
});
