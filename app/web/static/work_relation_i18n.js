import "./work_add_reminders.js";
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
  "默认提前一天和提前一小时，可关闭或调整具体时间。": "Defaults to one day and one hour before; each linked plan can be disabled or adjusted.",
  "模型解析中": "Model parsing",
  "模型解析完成": "Model parsing complete",
  "模型解析失败": "Model parsing failed",
  "请先输入内容": "Enter a description first",
  "正在解析...": "Parsing...",
  "没有返回可用解析结果": "The model returned no usable result",
  "已解析到表单": "Parsed into the form",
  "解析失败": "Parsing failed",
  "请填写标题": "Enter a title",
  "请设置截止时间": "Set the deadline time",
  "请设置开始时间": "Set the start time",
  "请设置已启用关联计划的开始时间": "Set a start time for every enabled linked plan",
  "创建成功，已清空表单": "Created successfully; the form has been cleared",
  "课程作业截止": "Course assignment deadline",
  "复习重点章节并完成例题": "Review key chapters and complete example problems",
  "检查阶段任务进展": "Review progress on the current project stage",
  "同时创建的计划": "Plans to create",
  "未启用关联计划": "No linked plans enabled",
  "等待填写标题": "Enter a title",
};

const ATTRIBUTE_ZH_EN = {
  "搜索标题、日期或时间，如 2026-09-01、08:00、星期二": "Search titles, dates or times, such as 2026-09-01, 08:00 or Tuesday",
  "例如：明天晚上八点复习热流体，持续 30 分钟，优先级高": "Example: Review heat transfer tomorrow at 8 PM for 30 minutes, high priority",
  "例如：复习热流体": "Example: Review heat transfer",
  "例如：提交课程报告": "Example: Submit the course report",
  "工作台导航": "Workspace navigation",
  "用户设置": "User settings",
};

const EN_ZH = Object.fromEntries(Object.entries(ZH_EN).map(([zh, en]) => [en, zh]));
const ATTRIBUTE_EN_ZH = Object.fromEntries(
  Object.entries(ATTRIBUTE_ZH_EN).map(([zh, en]) => [en, zh]),
);
const originals = new WeakMap();
const attributeOriginals = new WeakMap();

function excluded(node) {
  const parent = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
  return Boolean(parent?.closest?.(
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

function translateAttributes(element) {
  if (!(element instanceof Element) || excluded(element)) return;
  if (!attributeOriginals.has(element)) {
    attributeOriginals.set(element, {
      placeholder: element.getAttribute("placeholder"),
      title: element.getAttribute("title"),
      ariaLabel: element.getAttribute("aria-label"),
    });
  }
  const original = attributeOriginals.get(element);
  const source = getUiLanguage() === "en" ? ATTRIBUTE_ZH_EN : ATTRIBUTE_EN_ZH;
  for (const [key, attr] of [["placeholder", "placeholder"], ["title", "title"], ["ariaLabel", "aria-label"]]) {
    const value = original[key];
    if (value != null) element.setAttribute(attr, source[value] || value);
  }
}

function translatePage(root = document.body) {
  if (!root) return;
  if (root instanceof Element) translateAttributes(root);
  root.querySelectorAll?.("[placeholder], [title], [aria-label]").forEach(translateAttributes);
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

// The edit form accepts only concrete persisted statuses; "all" belongs to the list filter.
document.querySelector('#ideaEditForm select[name="handled"] option[value="all"]')?.remove();
translatePage();
observer.observe(document.body, { childList: true, subtree: true });
window.addEventListener("smartcore:languagechange", () => translatePage());
