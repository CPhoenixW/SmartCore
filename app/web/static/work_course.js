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
    // User data is supplementary.
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
    ui(`第 ${course.startWeek || 1}-${course.endWeek || 16} 周`, `Weeks ${course.startWeek || 1}-${course.endWeek || 16}`),
  ];
  if (course.location) parts.push(course.location);
  if (course.teacher) parts.push(course.teacher);
  return parts.join(" · ");
}

function normalizeQuery(value) {
  let text = String(value || "").trim().toLowerCase();
  text = text.replace(/\//g, "-");
  text = text.replace(/(\d{1,2})点半/g, (_, hour) => `${String(Number(hour)).padStart(2, "0")}:30`);
  text = text.replace(/(\d{1,2})点(?:(\d{1,2})分?)?/g, (_, hour, minute) => `${String(Number(hour)).padStart(2, "0")}:${String(Number(minute || 0)).padStart(2, "0")}`);
  return text;
}

function dateTokens(value) {
  if (!value) return [];
  const date = new Date(String(value).includes("T") ? value : `${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return [String(value).toLowerCase()];
  const pad = (part) => String(part).padStart(2, "0");
  const isoDate = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}`;
  const day = date.getDay() === 0 ? 7 : date.getDay();
  return [
    isoDate,
    `${date.getFullYear()}/${pad(date.getMonth() + 1)}/${pad(date.getDate())}`,
    `${date.getMonth() + 1}月${date.getDate()}日`,
    time,
    weekdayLabel(day).toLowerCase(),
    weekdays[day]?.[0]?.toLowerCase() || "",
    weekdays[day]?.[1]?.toLowerCase() || "",
  ];
}

function courseSearchText(course) {
  const parts = [
    course.courseName,
    course.title,
    course.teacher,
    course.location,
    course.desc,
    course.stTime,
    course.endTime,
    course.semesterStart,
    course.stDate,
    course.computedEndDate,
    course.endDate,
    weekdayLabel(course.weekDay),
    weekdays[Number(course.weekDay)]?.[0],
    weekdays[Number(course.weekDay)]?.[1],
    weekModeLabel(course.weekMode || "all"),
    `第${course.startWeek || 1}周`,
    `第${course.endWeek || 16}周`,
  ];
  for (const value of [course.semesterStart, course.stDate, course.computedEndDate, course.endDate]) {
    parts.push(...dateTokens(value));
  }
  for (const plan of course.plans || []) {
    parts.push(plan.title, plan.stTime, plan.occurrenceDate, ...dateTokens(plan.stTime), ...dateTokens(plan.occurrenceDate));
  }
  return parts.filter(Boolean).join(" ").toLowerCase();
}

function renderTimetable() {
  const root = $("courseTimetable");
  if (!root) return;
  const query = normalizeQuery($("globalSearch")?.value);
  const active = state.courses.filter((course) => course.stat !== "cancelled" && (!query || courseSearchText(course).includes(query)));
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
          <span>${esc(ui(`第 ${course.startWeek || 1}-${course.endWeek || 16} 周 · 共 ${course.occurrenceCount || 0} 次`, `Weeks ${course.startWeek || 1}-${course.endWeek || 16} · ${course.occurrenceCount || 0} classes`))}</span>
        </button>`).join("")
      : `<div class="course-empty-day">${esc(ui("无课程", "No course"))}</div>`;
    return `<section class="timetable-day"><header class="timetable-day-head">${esc(weekdayLabel(day))}<span>${rows.length}</span></header><div class="timetable-day-body">${content}</div></section>`;
  }).join("");
}

function renderCourseList() {
  const root = $("courseTplList");
  if (!root) return;
  const query = normalizeQuery($("globalSearch")?.value);
  const rows = state.courses.filter((course) => !query || courseSearchText(course).includes(query));
  root.innerHTML = rows.length
    ? rows.map((course) => `
      <article class="row-card clickable ${state.selectedId === course.evtId ? "selected" : ""}" data-course-id="${esc(course.evtId)}" tabindex="0" role="button">
        <div class="row-title">${esc(course.courseName || course.title)}</div>
        <div class="row-meta">${esc(courseMeta(course))}</div>
        <div class="course-row-meta">
          <span class="tag blue">${esc(ui(`学期开始 ${course.semesterStart || course.stDate || "—"}`, `Semester starts ${course.semesterStart || course.stDate || "—"}`))}</span>
          <span class="tag course-count">${esc(ui(`${course.occurrenceCount || 0} 次课`, `${course.occurrenceCount || 0} classes`))}</span>
          ${course.nextOccurrence?.stTime ? `<span class="tag green">${esc(ui("下次", "Next"))} ${esc(formatDateTime(course.nextOccurrence.stTime))}</span>` : ""}
          ${course.stat === "cancelled" ? `<span class="tag red">${esc(ui("已取消", "Cancelled"))}</span>` : ""}
        </div>
      </article>`).join("")
    : `<div class="empty">${esc(ui("暂无匹配课程", "No matching courses"))}</div>`;
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
  const values = {
    courseName: course?.courseName,
    teacher: course?.teacher,
    location: course?.location,
    semesterStart: course?.semesterStart || course?.stDate,
    weekDay: course?.weekDay,
    stTime: course?.stTime,
    endTime: course?.endTime,
    startWeek: course?.startWeek,
    endWeek: course?.endWeek,
    weekMode: course?.weekMode,
    desc: course?.desc,
  };
  Object.entries(values).forEach(([key, value]) => {
    if (value != null && form.elements[key]) form.elements[key].value = value;
  });
  if (!course) {
    form.elements.weekDay.value = "1";
    form.elements.weekMode.value = "all";
    form.elements.startWeek.value = "1";
    form.elements.endWeek.value = "16";
  }
  $("courseEditorTitle").textContent = course ? ui("编辑课程", "Edit course") : ui("新建课程", "New course");
  $("deleteCourseTplBtn").disabled = !course;
  updateGeneratedSummary();
  renderAll();
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function estimateOccurrences() {
  const form = $("courseTplForm");
  const semesterStart = parseDate(formValue(form, "semesterStart"));
  const weekday = Number(formValue(form, "weekDay"));
  const mode = formValue(form, "weekMode") || "all";
  const startWeek = Number(formValue(form, "startWeek") || 1);
  const endWeek = Number(formValue(form, "endWeek") || 16);
  if (!semesterStart || !weekday || startWeek < 1 || endWeek < startWeek) return [];

  const anchorMonday = new Date(semesterStart);
  const isoDay = anchorMonday.getDay() === 0 ? 7 : anchorMonday.getDay();
  anchorMonday.setDate(anchorMonday.getDate() - (isoDay - 1));
  const rows = [];
  for (let week = startWeek; week <= endWeek; week += 1) {
    if (mode === "odd" && week % 2 === 0) continue;
    if (mode === "even" && week % 2 === 1) continue;
    const occurrence = new Date(anchorMonday);
    occurrence.setDate(anchorMonday.getDate() + (week - 1) * 7 + (weekday - 1));
    if (occurrence < semesterStart) continue;
    rows.push(occurrence);
  }
  return rows;
}

function updateGeneratedSummary() {
  const rows = estimateOccurrences();
  const el = $("courseGeneratedSummary");
  if (!el) return;
  if (!rows.length) {
    el.textContent = ui(
      "填写学期开始日期、星期和起止周后，将按周次顺序计算全部上课时间。",
      "Enter the semester start, weekday and week range to calculate all class dates.",
    );
    return;
  }
  const format = (date) => date.toLocaleDateString(getUiLanguage() === "en" ? "en-CA" : "zh-CN");
  el.textContent = ui(
    `预计生成 ${rows.length} 个上课计划和 ${rows.length * 2} 个提醒；首节 ${format(rows[0])}，末节 ${format(rows[rows.length - 1])}。`,
    `This will generate ${rows.length} class plans and ${rows.length * 2} reminders, from ${format(rows[0])} to ${format(rows[rows.length - 1])}.`,
  );
}

function payloadFromForm() {
  const form = $("courseTplForm");
  return {
    courseName: formValue(form, "courseName"),
    title: formValue(form, "courseName"),
    teacher: formValue(form, "teacher") || null,
    location: formValue(form, "location") || null,
    semesterStart: formValue(form, "semesterStart"),
    weekDay: Number(formValue(form, "weekDay")),
    stTime: formValue(form, "stTime"),
    endTime: formValue(form, "endTime"),
    startWeek: Number(formValue(form, "startWeek") || 1),
    endWeek: Number(formValue(form, "endWeek") || 16),
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
  if (!payload.courseName || !payload.semesterStart || !payload.stTime || !payload.endTime || !payload.weekDay) {
    return toast(ui("请完整填写课程名称、学期开始日期、星期和时间", "Complete the course name, semester start, weekday and times"));
  }
  if (payload.endWeek < payload.startWeek) {
    return toast(ui("结束周不能早于起始周", "End week cannot be earlier than start week"));
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
    semesterStart: parsed.semesterStart || parsed.stDate || parsed.startDate,
    weekDay: parsed.weekDay,
    stTime: parsed.stTime,
    endTime: parsed.endTime,
    startWeek: parsed.startWeek || 1,
    endWeek: parsed.endWeek || 16,
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
  $("globalSearch")?.addEventListener("input", renderAll);
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
