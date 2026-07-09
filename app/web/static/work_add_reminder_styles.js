import "./work_event_copy.js";

if (!document.querySelector('link[href="/static/work/work_add_reminders.css"]')) {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/static/work/work_add_reminders.css";
  document.head.appendChild(link);
}
