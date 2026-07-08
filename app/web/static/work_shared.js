let currentLanguage = localStorage.getItem("smartcoreLanguage") || "zh";
const textOriginals = new WeakMap();
const attrOriginals = new WeakMap();
let observerStarted = false;

const EN = {
  "总览": "Overview",
  "添加事件": "Add Event",
  "更新事件": "Update Event",
  "灵感": "Ideas",
  "课表": "Courses",
  "日志": "Logs",
  "设备": "Devices",
  "设置": "Settings",
  "学生智能助手": "Student Assistant",
  "待办、DDL、灵感": "Tasks, deadlines and ideas",
  "创建计划事项或截止事项": "Create plans or deadlines",
  "查看和修改事项": "View and edit events",
  "记录、筛选和修改灵感": "Capture, filter and edit ideas",
  "课程事件管理": "Course event management",
  "日志追踪": "Activity tracking",
  "用户与偏好": "Profile and preferences",
  "待办事项": "Open tasks",
  "今日事项": "Today",
  "未来 72 小时": "Next 72 hours",
  "灵感 Inbox": "Idea inbox",
  "即将截止": "Upcoming deadlines",
  "最近灵感": "Recent ideas",
  "快捷入口": "Quick access",
  "全部事件": "All events",
  "整理": "Organize",
  "记录灵感": "Capture idea",
  "课表管理": "Course management",
  "设备状态": "Device status",
  "树莓派状态": "Raspberry Pi status",
  "设备详情": "Device details",
  "人物": "Person",
  "状态置信度": "State confidence",
  "是否有人": "Presence",
  "自然语言录入": "Natural-language input",
  "解析到表单": "Parse into form",
  "事件表单": "Event form",
  "计划事项": "Plan",
  "截止事项": "Deadline",
  "标题": "Title",
  "描述": "Description",
  "开始时间": "Start time",
  "持续时间（分钟）": "Duration (minutes)",
  "优先级": "Priority",
  "截止时间": "Deadline time",
  "硬性截止": "Hard deadline",
  "创建前预览": "Preview",
  "创建计划事项": "Create plan",
  "创建截止事项及计划": "Create deadline and plans",
  "常用模板": "Templates",
  "作业 DDL": "Assignment deadline",
  "考试复习": "Exam review",
  "项目跟进": "Project follow-up",
  "关联计划": "Linked plans",
  "提前一天": "One day before",
  "提前一小时": "One hour before",
  "同时创建的计划": "Plans to create",
  "未启用关联计划": "No linked plans enabled",
  "事件列表": "Event list",
  "编辑事件": "Edit event",
  "状态": "Status",
  "时间": "Time",
  "保存": "Save",
  "完成": "Complete",
  "取消": "Cancel",
  "待办": "Open",
  "已取消": "Cancelled",
  "全部": "All",
  "灵感列表": "Idea list",
  "编辑灵感": "Edit idea",
  "内容": "Content",
  "保存灵感": "Save idea",
  "保存新灵感": "Save new idea",
  "保存修改": "Save changes",
  "新建": "New",
  "删除": "Delete",
  "课程事件": "Course events",
  "新建课程": "New course",
  "编辑课程": "Edit course",
  "课程名称": "Course name",
  "教师": "Teacher",
  "地点": "Location",
  "开始日期": "Start date",
  "结束日期": "End date",
  "星期": "Weekday",
  "周属性": "Week pattern",
  "开始": "Start",
  "结束": "End",
  "起始周": "First week",
  "结束周": "Last week",
  "保存课程": "Save course",
  "删除课程": "Delete course",
  "操作日志": "Activity logs",
  "事件操作": "Event actions",
  "提醒": "Notifications",
  "消息": "Messages",
  "全部状态": "All statuses",
  "用户设置": "User settings",
  "保存设置": "Save settings",
  "用户名称": "Display name",
  "语言": "Language",
  "头像 URL": "Avatar URL",
  "提醒方式": "Notification channel",
  "面板提醒": "Panel notification",
  "飞书提醒": "Feishu notification",
  "头像预览": "Avatar preview",
  "中文": "Chinese",
  "工作中": "Working",
  "离开": "Away",
  "离线": "Offline",
  "未知": "Unknown",
  "有人": "Present",
  "无人": "No one",
  "未识别": "Not identified",
  "等待状态": "Waiting for state",
  "尚未收到树莓派回传": "No Raspberry Pi report received",
  "API 待命": "API idle",
  "API 在线": "API online",
  "API 请求中": "API loading",
  "API 异常": "API error",
  "未刷新": "Not refreshed",
  "刷新": "Refresh",
  "树莓派当前状态": "Current Raspberry Pi state",
  "识别人物": "Identified people",
  "时钟偏差": "Clock offset",
  "识别模型": "Recognition model",
  "摄像头": "Camera",
  "树莓派识别日志": "Raspberry Pi recognition logs",
  "当前摄像头画面": "Current camera frame",
  "请求当前画面": "Request current frame",
  "等待请求当前画面": "Ready to request a frame",
  "当前没有进行中的画面请求": "No camera request in progress",
  "近 24 小时使用分析": "Last 24 hours analysis",
  "基于状态日志样本": "Based on state samples",
  "状态记录": "State samples",
  "工作状态占比": "Working share",
  "有人占比": "Presence share",
  "平均置信度": "Average confidence",
  "最常识别人": "Most identified person",
  "状态最活跃时段": "Most active hour",
  "今日每小时使用时长": "Hourly usage today",
  "今日使用时长": "Usage today",
  "峰值时段": "Peak hour",
  "暂无数据": "No data",
  "暂无识别": "No identification",
  "高": "High",
  "中": "Medium",
  "低": "Low"
};

const PLACEHOLDERS_EN = {
  "搜索事项、DDL、灵感、日志...": "Search events, deadlines, ideas and logs...",
  "搜索人物、状态、模型信息...": "Search people, states and model details...",
  "搜索日志...": "Search logs...",
  "例如：明天晚上八点复习热流体，持续 30 分钟，优先级高": "Example: Review heat transfer tomorrow at 8 PM for 30 minutes, high priority",
  "例如：复习热流体": "Example: Review heat transfer",
  "例如：提交课程报告": "Example: Submit course report",
  "选择左侧灵感进行修改，或直接输入新灵感...": "Select an idea to edit, or enter a new one...",
  "默认用户": "Default user",
  "https://... 或留空使用文字头像": "https://... or leave blank for initials"
};

function translated(text) {
  if (currentLanguage !== "en") return text;
  return EN[text] || text;
}

function translateTextNode(node) {
  if (!textOriginals.has(node)) textOriginals.set(node, node.nodeValue);
  const original = textOriginals.get(node);
  const leading = original.match(/^\s*/)?.[0] || "";
  const trailing = original.match(/\s*$/)?.[0] || "";
  const core = original.trim();
  if (!core) return;
  node.nodeValue = `${leading}${translated(core)}${trailing}`;
}

function translateAttributes(element) {
  if (!(element instanceof Element)) return;
  let originals = attrOriginals.get(element);
  if (!originals) {
    originals = {};
    attrOriginals.set(element, originals);
  }
  for (const attr of ["placeholder", "title", "aria-label"]) {
    if (!element.hasAttribute(attr)) continue;
    if (!(attr in originals)) originals[attr] = element.getAttribute(attr);
    const original = originals[attr] || "";
    if (attr === "placeholder" && currentLanguage === "en") {
      element.setAttribute(attr, PLACEHOLDERS_EN[original] || EN[original] || original);
    } else {
      element.setAttribute(attr, translated(original));
    }
  }
}

function translateTree(root) {
  if (!root) return;
  if (root.nodeType === Node.TEXT_NODE) {
    translateTextNode(root);
    return;
  }
  if (!(root instanceof Element) && root !== document.body) return;
  if (root instanceof Element) translateAttributes(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
    else translateAttributes(node);
    node = walker.nextNode();
  }
}

export function setUiLanguage(language) {
  currentLanguage = language === "en" ? "en" : "zh";
  localStorage.setItem("smartcoreLanguage", currentLanguage);
  document.documentElement.lang = currentLanguage === "en" ? "en" : "zh-CN";
  translateTree(document.body);
}

export function getUiLanguage() {
  return currentLanguage;
}

function startObserver() {
  if (observerStarted || !document.body) return;
  observerStarted = true;
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      mutation.addedNodes.forEach((node) => translateTree(node));
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

async function loadUiPreferences() {
  try {
    const response = await fetch("/api/user/me");
    const body = await response.json();
    const user = body?.data || {};
    setUiLanguage(user.language || currentLanguage);
    const languageSelect = document.querySelector('select[name="language"]');
    if (languageSelect) languageSelect.value = user.language || "zh";
    const reminderSelect = document.querySelector('select[name="reminderChannel"]');
    if (reminderSelect) reminderSelect.value = user.reminderChannel || "screen";
  } catch {
    setUiLanguage(currentLanguage);
  }
}

function bindPreferenceControls() {
  document.addEventListener("change", async (event) => {
    const target = event.target;
    if (!(target instanceof HTMLSelectElement)) return;
    if (target.name === "language") {
      setUiLanguage(target.value);
    }
    if (target.name === "reminderChannel") {
      try {
        await fetch("/api/user/me", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reminderChannel: target.value }),
        });
      } catch {
        // The main settings form remains available for a later retry.
      }
    }
  });
}

function initSharedUi() {
  startObserver();
  bindPreferenceControls();
  setUiLanguage(currentLanguage);
  loadUiPreferences();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSharedUi, { once: true });
} else {
  initSharedUi();
}

export function ensureDeviceNav(active = false) {
  const nav = document.querySelector(".work-nav");
  if (!nav || nav.querySelector('[href="/work/device"]')) return;
  const link = document.createElement("a");
  link.className = `nav-link${active ? " active" : ""}`;
  link.href = "/work/device";
  link.innerHTML = '<span class="nav-ico">◉</span>设备';
  const settings = nav.querySelector('[href="/work/settings"]');
  nav.insertBefore(link, settings || null);
  translateTree(link);
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(currentLanguage === "en" ? "en-US" : "zh-CN", { hour12: false });
}

export function deviceStateView(row, staleSeconds = 35) {
  if (!row) {
    return {
      state: "offline",
      label: currentLanguage === "en" ? "Offline" : "离线",
      stale: true,
      seenAt: null,
      confidence: null,
      present: false,
      persons: [],
      meta: {},
    };
  }
  const seen = row.seenAt ? new Date(row.seenAt) : null;
  const stale = !seen || Number.isNaN(seen.getTime()) || Date.now() - seen.getTime() > staleSeconds * 1000;
  const state = stale ? "offline" : (row.state || "unknown");
  const labels = currentLanguage === "en"
    ? { working: "Working", away: "Away", offline: "Offline", unknown: "Unknown" }
    : { working: "工作中", away: "离开", offline: "离线", unknown: "未知" };
  const meta = row.meta && typeof row.meta === "object" ? row.meta : {};
  return {
    state,
    label: labels[state] || state,
    stale,
    seenAt: row.seenAt || null,
    confidence: row.confidence,
    present: Boolean(meta.present),
    persons: Array.isArray(meta.persons) ? meta.persons : [],
    meta,
  };
}
