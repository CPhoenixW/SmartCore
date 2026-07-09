import { ensureDeviceNav, formatDateTime, getUiLanguage, t } from "./work_shared.js";

const $ = (id) => document.getElementById(id);
const state = { courses: [], selectedId: null };
const weekdays = {
  1: ["星期一", "Monday"],
  2: ["星期二", "Tuesday"],
  3: ["星期三", "Wednesday"],
  4: ["星期四", "Thursday"],
  5: ["星期五", "Friday"],
  6: ["星期六", "Saturday"],
  7: ["星期日", "Sunday"],
};

function ui(zh, en) {
  return getUiLanguage() === "en" ? en : zh;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;");
}

function toast(text) {
  const el = $("toast");
  if (!el) return;
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

function setApi(kind, text) {
  const el = $("apiStatus");
  if (!el) return;
  el.className = `status-pill ${kind || ""}`.trim();
  el.textContent = text;
}

function touchRefresh() {
  if ($("lastRefresh")) {
    $("lastRefresh").textContent = ui(
      `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`,
      `Updated at ${new Date().toLocaleTimeString("en-US", { hour12: false })}`,
    );
  }
}

async function api(path, options = undefined) {
  setApi("busy", t("API 请求中"));
  const response = await fetch(path, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok === false) {
    setApi("err", t("API 异常"));
    throw new Error(body.detail || body.msg || `HTTP ${response.status}`);
  }
  setApi("ok", t("API 在线"));
  touchRefresh();
  return body.data;
}

function formValue(form, name) {
  return form?.elements[name]?.value?.trim() || "";
}

function numberOrNull(value) {
  return value === "" || value == null ? null : Number(value);
}

function avatarText(name) {
  return String(name || "SC").trim().slice(0, 2).toUpperCase() || "SC";
}

async function loadUser() {
  try {
    const user = await api("/api/user/me");
    const text = $("topAvatarText");
    const img = $("topAvatarImg");
    if (text) text.textContent = avatarText(user?.displayName);
    if (img && user?.avatarUrl) {
      img.src = user.avatarUrl;
      img.hidden = false;
      if (text) text.hidden = true;
    }
  } catch {
    // The course page remains usable without the avatar request.
  }
}

function weekdayLabel(value) {
  const pair = weekdays[Number(value)] || [String(value), String(value)];
  return pair[getUiLanguage() === "en" ? 1 : 0];
}

function weekModeLabel(value) {
  const labels = {
    all: ["每周", "Every week"],
    odd: ["单周", "Odd weeks"],
    even: ["双周", "Even weeks"],
  };
  const pair = labels[value] || [value, value];
  return pair[getUiLanguage() === "en" ? 1 : 0];
}

function courseMeta(course) {
  const parts = [
    weekdayLabel(course.weekDay),
    `${course.stTime || "—"}–${course.endTime || "—"}`,
    weekModeLabel(course.weekMode || "all"),
  ];
  if (course.location) parts.push(course.location);
  if (course.teacher) parts.push(course.teacher);
  return parts.join(" · ");
}

function renderTimetable() {
  const root = $("courseTimetable");
  if (!root) return;
  const active = state.courses.filter((course) => course.stat !== "cancelled");
  root.innerHTML = Array.from({ length: 7 }, (_, index) => {
    const day = index + 1;
    const rows = active
      .filter((course) => Number(course.weekDay) === day)
      .sort((a, b) => String(a.stTime).localeCompare(String(b.stTime)));
    const content = rows.length
      ? rows.map((course) => `
        <button class="course-block ${state.selectedId === course.evtId ? "selected" : ""}" type="button" data-course-id="${esc(course.evtId)}">
          <strong>${esc(course.courseName || course.title)}</strong>
          <span class="course-time">${esc(course.stTime)}–${esc(course.endTime)}</span>
          <span>${esc([course.location, course.teacher].filter(Boolean).join(" · ") || ui("未填写地点和教师", "No room or teacher"))}</span>
          <span>${esc(ui(`共 ${course.occurrenceCount || 0} 次课`, `${course.occurrenceCount || 0} classes`))}</span>
        </button>`).join("")
      : `<div class="course-empty-day">${esc(ui("无课程", "No course"))}</div>`;
    return `<section class="timetable-day"><header class="timetable-day-head">${esc(weekdayLabel(day))}<span>${rows.length}</span></header><div class="timetable-day-body">${content}</div></section>`;
  }).join("");
}

function renderCourseList() {
  const root = $("courseTplList");
  if (!root) return;
  const query = $("globalSearch")?.value.trim().toLowerCase() || "";
  const rows = state.courses.filter((course) => {
    if (!query) return true;
    return `${course.courseName} ${course.teacher || ""} ${course.location || ""}`.toLowerCase().includes(query);
  });
  root.innerHTML = rows.length
    ? rows.map((course) => `
      <article class="row-card clickable ${state.selectedId === course.evtId ? "selected" : ""}" data-course-id="${esc(course.evtId)}" tabindex="0" role="button">
        <div class="row-title">${esc(course.courseName || course.title)}</div>
        <div class="row-meta">${esc(courseMeta(course))}</div>
        <div class="course-row-meta">
          <span class="tag blue">${esc(course.stDate)} – ${esc(course.endDate)}</span>
          <span class="tag course-count">${esc(ui(`${course.occurrenceCount || 0} 次课`, `${course.occurrenceCount || 0} classes`))}</span>
          ${course.nextOccurrence?.stTime ? `<span class="tag green">${esc(ui("下次", "Next"))} ${esc(formatDateTime(course.nextOccurrence.stTime))}</span>` : ""}
          ${course.stat === "cancelled" ? `<span class="tag red">${esc(ui("已取消", "Cancelled"))}</span>` : ""}
        </div>
      </article>`).join("")
    : `<div class="empty">${esc(ui("暂无课程", "No courses"))}</div>`;
}

function renderAll() {
  renderTimetable();
  renderCourseList();
}

function setForm(course = null) {
  const form = $("courseTplForm");
  if (!form) return;
  form.reset();
  state.selectedId = course?.evtId || null;
  form.elements.evtId.value = course?.evtId || "";
  for (const key of [
    "courseName", "teacher", "location", "stDate", "endDate", "weekDay",
    "stTime", "endTime", "startWeek", "endWeek", "weekMode", "desc",
  ]) {
    if (course?.[key] != null) form.elements[key].value = course[key];
  }
  if (!course) {
    form.elements.weekDay.value = "1";
    form.elements.weekMode.value = "all";
  }
  $("courseEditorTitle").textContent = course
    ? ui("编辑课程", "Edit course")
    : ui("新建课程", "New course");
  $("deleteCourseTplBtn").disabled = !course;
  updateGeneratedSummary();
  renderAll();
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function estimateOccurrenceCount() {
  const form = $("courseTplForm");
  const start = parseDate(formValue(form, "stDate"));
  const end = parseDate(formValue(form, "endDate"));
  const weekday = Number(formValue(form, "weekDay"));
  const mode = formValue(form, "weekMode") || "all";
  const startWeek = numberOrNull(formValue(form, "startWeek"));
  const endWeek = numberOrNull(formValue(form, "endWeek"));
  if (!start || !end || !weekday || end < start) return 0;
  const first = new Date(start);
  const isoDay = first.getDay() === 0 ? 7 : first.getDay();
  first.setDate(first.getDate() + ((weekday - isoDay + 7) % 7));
  let count = 0;
  let weekNo = 1;
  for (let cursor = new Date(first); cursor <= end; cursor.setDate(cursor.getDate() + 7), weekNo += 1) {
    if (startWeek && weekNo < startWeek) continue;
    if (endWeek && weekNo > endWeek) continue;
    if (mode === "odd" && weekNo % 2 === 0) continue;
    if (mode === "even" && weekNo % 2 === 1) continue;
    count += 1;
  }
  return count;
}

function updateGeneratedSummary() {
  const count = estimateOccurrenceCount();
  const el = $("courseGeneratedSummary");
  if (!el) return;
  el.textContent = count
    ? ui(
      `预计生成 ${count} 个上课计划和 ${count * 2} 个提醒；每次课在开始前 10 分钟和结束前 10 分钟提醒。`,
      `This will generate ${count} class plans and ${count * 2} reminders, 10 minutes before class starts and ends.`,
    )
    : ui(
      "填写日期、星期和上课时间后，将自动计算全部上课日期。",
      "Enter the date range, weekday and class time to calculate all occurrences.",
    );
}

function payloadFromForm() {
  const form = $("courseTplForm");
  return {
    courseName: formValue(form, "courseName"),
    title: formValue(form, "courseName"),
    teacher: formValue(form, "teacher") || null,
    location: formValue(form, "location") || null,
    stDate: formValue(form, "stDate"),
    endDate: formValue(form, "endDate"),
    weekDay: Number(formValue(form, "weekDay")),
    stTime: formValue(form, "stTime"),
    endTime: formValue(form, "endTime"),
    startWeek: numberOrNull(formValue(form, "startWeek")),
    endWeek: numberOrNull(formValue(form, "endWeek")),
    weekMode: formValue(form, "weekMode") || "all",
    desc: formValue(form, "desc") || null,
  };
}

async function loadCourses({ keepSelection = true } = {}) {
  const selected = keepSelection ? state.selectedId : null;
  state.courses = await api("/api/courseEvt");
  state.selectedId = selected;
  renderAll();
  if (selected) {
    const current = state.courses.find((course) => course.evtId === selected);
    if (current) setForm(current);
  }
}

async function saveCourse(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const id = formValue(form, "evtId");
  const payload = payloadFromForm();
  if (!payload.courseName || !payload.stDate || !payload.endDate || !payload.stTime || !payload.endTime) {
    return toast(ui("请完整填写课程名称、日期和时间", "Complete the course name, dates and times"));
  }
  try {
    const saved = await api(id ? `/api/evt/${id}` : "/api/courseEvt", {
      method: id ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.selectedId = saved.evtId;
    await loadCourses();
    toast(ui("课程及全部上课计划已保存", "Course and class plans saved"));
  } catch (error) {
    toast(error.message);
  }
}

async function deleteCourse() {
  const id = formValue($("courseTplForm"), "evtId");
  if (!id) return;
  try {
    await api(`/api/evt/${id}`, { method: "DELETE" });
    state.selectedId = null;
    setForm(null);
    await loadCourses({ keepSelection: false });
    toast(ui("课程及未完成计划已取消", "Course and pending plans cancelled"));
  } catch (error) {
    toast(error.message);
  }
}

function applyParsedCourse(parsed) {
  const form = $("courseTplForm");
  setForm(null);
  const aliases = {
    courseName: parsed.courseName || parsed.title,
    teacher: parsed.teacher,
    location: parsed.location || parsed.room,
    stDate: parsed.stDate || parsed.startDate,
    endDate: parsed.endDate || parsed.finishDate,
    weekDay: parsed.weekDay,
    stTime: parsed.stTime,
    endTime: parsed.endTime,
    startWeek: parsed.startWeek,
    endWeek: parsed.endWeek,
    weekMode: parsed.weekMode || "all",
    desc: parsed.desc || parsed.description,
  };
  Object.entries(aliases).forEach(([key, value]) => {
    if (value != null && form.elements[key]) form.elements[key].value = value;
  });
  updateGeneratedSummary();
}

async function parseCourse() {
  const text = $("courseNaturalText")?.value.trim();
  if (!text) return toast(ui("请先输入课程描述", "Enter a course description first"));
  try {
    const data = await api("/api/llm/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, scene: "create_course" }),
    });
    if (!data?.parsed) throw new Error(ui("模型没有返回可用结果", "The model returned no usable result"));
    applyParsedCourse(data.parsed);
    toast(ui("课程信息已填入表单", "Course data filled into the form"));
  } catch (error) {
    toast(error.message);
  }
}

async function syncAllCourses() {
  try {
    for (const course of state.courses.filter((item) => item.stat !== "cancelled")) {
      await api(`/api/courseEvt/${course.evtId}/sync`, { method: "POST" });
    }
    await loadCourses();
    toast(ui("上课计划和提醒已重新生成", "Class plans and reminders regenerated"));
  } catch (error) {
    toast(error.message);
  }
}

function selectFromElement(element) {
  const course = state.courses.find((item) => item.evtId === element.dataset.courseId);
  if (course) setForm(course);
}

function bind() {
  $("courseTplForm")?.addEventListener("submit", saveCourse);
  $("courseTplForm")?.addEventListener("input", updateGeneratedSummary);
  $("courseTplForm")?.addEventListener("change", updateGeneratedSummary);
  $("newCourseBtn")?.addEventListener("click", () => setForm(null));
  $("deleteCourseTplBtn")?.addEventListener("click", deleteCourse);
  $("parseCourseBtn")?.addEventListener("click", parseCourse);
  $("syncCoursesBtn")?.addEventListener("click", syncAllCourses);
  $("globalSearch")?.addEventListener("input", renderCourseList);
  document.body.addEventListener("click", (event) => {
    const element = event.target.closest("[data-course-id]");
    if (element) selectFromElement(element);
  });
  document.body.addEventListener("keydown", (event) => {
    const element = event.target.closest?.("[data-course-id]");
    if (element && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      selectFromElement(element);
    }
  });
  window.addEventListener("smartcore:languagechange", renderAll);
}

ensureDeviceNav(false);
bind();
setForm(null);
loadUser();
loadCourses({ keepSelection: false }).catch((error) => toast(error.message));
