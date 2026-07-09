import { getUiLanguage } from "./work_shared.js";

const ZH_EN = {
  "按日期查看和修改计划事项": "View and edit plans by date",
  "按学期开始日期和周次生成上课计划": "Generate class plans from semester start and week numbers",
  "上一天": "Previous day",
  "下一天": "Next day",
  "查看日期": "Date",
  "当天事件": "Events for the day",
  "0 个事项": "0 events",
  "自然语言添加课程": "Add course with natural language",
  "解析课程": "Parse course",
  "周课表": "Weekly timetable",
  "点击课程块可直接编辑课程模板": "Click a class block to edit its course",
  "课程计划": "Class plan",
  "课程列表": "Course list",
  "重新生成上课计划": "Regenerate class plans",
  "编辑课程": "Edit course",
  "新建课程": "New course",
  "新建": "New",
  "课程名称": "Course name",
  "教师": "Teacher",
  "地点": "Room",
  "学期开始日期": "Semester start",
  "星期": "Weekday",
  "周属性": "Week pattern",
  "上课时间": "Class starts",
  "下课时间": "Class ends",
  "起始周": "First week",
  "结束周": "Last week",
  "课程说明": "Course notes",
  "保存并生成计划": "Save and generate plans",
  "删除课程": "Delete course",
  "每周": "Every week",
  "单周": "Odd weeks",
  "双周": "Even weeks",
  "星期一": "Monday",
  "星期二": "Tuesday",
  "星期三": "Wednesday",
  "星期四": "Thursday",
  "星期五": "Friday",
  "星期六": "Saturday",
  "星期日": "Sunday",
  "以学期开始日期为第 1 周，按照星期和起止周自动计算全部上课时间。": "Treat the semester start as week 1 and calculate class dates from weekday and week range.",
};

const EN_ZH = Object.fromEntries(Object.entries(ZH_EN).map(([zh, en]) => [en, zh]));
const originals = new WeakMap();

function excluded(node) {
  return Boolean(node.parentElement?.closest(
    ".task-title, .task-desc, .row-title, .log-json, [data-no-translate]",
  ));
}

function translateNode(node) {
  if (excluded(node)) return;
  if (!originals.has(node)) originals.set(node, node.nodeValue || "");
  const original = originals.get(node) || "";
  const leading = original.match(/^\s*/)?.[0] || "";
  const trailing = original.match(/\s*$/)?.[0] || "";
  const text = original.trim();
  if (!text) return;
  const translated = getUiLanguage() === "en"
    ? (ZH_EN[text] || text)
    : (EN_ZH[text] || text);
  const next = `${leading}${translated}${trailing}`;
  if (node.nodeValue !== next) node.nodeValue = next;
}

function translatePage(root = document.body) {
  if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    translateNode(node);
    node = walker.nextNode();
  }
}

const observer = new MutationObserver((mutations) => {
  for (const mutation of mutations) {
    mutation.addedNodes.forEach((node) => {
      if (node.nodeType === Node.TEXT_NODE) translateNode(node);
      else if (node instanceof Element) translatePage(node);
    });
  }
});

translatePage();
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener("smartcore:languagechange", () => translatePage());
