import { getUiLanguage } from "./work_shared.js";

function applyEventPageCopy() {
  const page = document.body.dataset.page;
  const subtitle = document.querySelector(".page-head p");
  if (!subtitle) return;
  const english = getUiLanguage() === "en";
  if (page === "add") {
    subtitle.textContent = english
      ? "Create plans, standalone reminders or deadlines"
      : "创建计划、单独提醒或截止事项";
  }
  if (page === "update") {
    subtitle.textContent = english
      ? "View and edit plans, reminders and deadlines by date"
      : "按日期查看和修改计划、提醒与截止事项";
  }
}

function selectParsedEventTab(parsed) {
  const type = String(parsed?.evtType || parsed?.tab || "").toLowerCase();
  if (type !== "plan" && type !== "ddl") return;
  document.querySelector(`[data-create-tab="${type}"]`)?.click();
}

function installAddPageTabSync() {
  if (document.body.dataset.page !== "add") return;
  document.querySelectorAll(".template[data-template]").forEach((button) => {
    button.addEventListener("click", () => {
      const template = button.dataset.template;
      const type = template === "homework" || template === "exam" ? "ddl" : "plan";
      document.querySelector(`[data-create-tab="${type}"]`)?.click();
    });
  });

  if (window.__smartcoreEventCopyFetchInstalled) return;
  window.__smartcoreEventCopyFetchInstalled = true;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init = undefined) => {
    const response = await nativeFetch(input, init);
    const url = typeof input === "string" ? input : input?.url || "";
    const method = String(init?.method || (typeof input !== "string" ? input?.method : "GET") || "GET").toUpperCase();
    if (method === "POST" && url.includes("/api/llm/parse")) {
      response.clone().json().then((body) => {
        setTimeout(() => selectParsedEventTab(body?.data?.parsed || {}), 0);
      }).catch(() => {});
    }
    return response;
  };
}

applyEventPageCopy();
installAddPageTabSync();
window.addEventListener("smartcore:languagechange", applyEventPageCopy);
