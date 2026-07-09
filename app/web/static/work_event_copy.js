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

applyEventPageCopy();
window.addEventListener("smartcore:languagechange", applyEventPageCopy);
