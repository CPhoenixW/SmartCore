import { readFile } from "node:fs/promises";
import process from "node:process";

import { auditHost, execOnHost, listHost, readHost, writeHost } from "./host-access.mjs";

const baseUrl = String(process.env.SMARTCORE_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const agentToken = String(process.env.SMARTCORE_AGENT_TOKEN || "");
const scopeFile = String(process.env.SMARTCORE_SCOPE_FILE || "");
const mode = String(process.env.SMARTCORE_MCP_MODE || "automation").trim().toLowerCase();
const serverBaseUrl = String(process.env.DSH_SERVER_BASE_URL || baseUrl).replace(/\/$/, "");
const serverAllowedPaths = String(process.env.DSH_SERVER_ALLOWED_PATHS || "/healthz")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);
const serverAllowedMethods = new Set(String(process.env.DSH_SERVER_ALLOWED_METHODS || "GET")
  .split(",")
  .map((value) => value.trim().toUpperCase())
  .filter(Boolean));
let serverHeaders = {};
try {
  const parsed = JSON.parse(String(process.env.DSH_SERVER_HEADERS_JSON || "{}"));
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) serverHeaders = parsed;
} catch {}

const textSchema = { type: "string" };
const objectSchema = (properties = {}, required = []) => ({
  type: "object",
  properties,
  required,
  additionalProperties: false,
});
const eventProperties = {
  evtType: textSchema,
  evtId: textSchema, title: textSchema, desc: textSchema, prio: textSchema,
  stat: textSchema, stTime: textSchema, endTime: textSchema, dueAt: textSchema,
  ddlAt: textSchema, durationMin: { type: "integer", minimum: 1 }, hardDdl: { type: "boolean" },
};

const mediaToolNames = new Set(["smartcore_media_context", "smartcore_media_job_context"]);

const internalTools = [
  {
    name: "smartcore_today",
    description: "Read the user's day context, current plans, deadlines, and reminders.",
    method: "GET", path: "/agent/daily-work-context",
    inputSchema: objectSchema({ date: { type: "string", description: "YYYY-MM-DD" }, timezone: { type: "string" } }, ["date"]),
  },
  {
    name: "smartcore_events_query",
    description: "Query the user's plans, deadlines, courses, and reminders.",
    method: "POST", path: "/agent/db/query_events",
    inputSchema: objectSchema({
      evtId: textSchema, evtType: { oneOf: [textSchema, { type: "array", items: textSchema }] },
      stat: { oneOf: [textSchema, { type: "array", items: textSchema }] }, text: textSchema,
      timeRange: { type: "object" }, includeLinkedPlans: { type: "boolean" }, includePlans: { type: "boolean" }, limit: { type: "integer" },
    }),
  },
  {
    name: "smartcore_event_create",
    description: "Create one owned plan, deadline, course, or reminder event. Use absolute ISO date-times.",
    method: "POST", path: "/agent/db/create_event",
    inputSchema: objectSchema(eventProperties, ["evtType", "title"]),
  },
  {
    name: "smartcore_event_update",
    description: "Update one owned event by id.",
    method: "POST", path: "/agent/db/update_event",
    inputSchema: objectSchema(eventProperties, ["evtId"]),
  },
  {
    name: "smartcore_event_complete",
    description: "Mark one owned event complete and append the user's outcome or reflection.",
    method: "POST", path: "/agent/db/complete_event",
    inputSchema: objectSchema({ evtId: textSchema, summary: { type: "string", minLength: 1, maxLength: 4000 } }, ["evtId", "summary"]),
  },
  {
    name: "smartcore_event_delete",
    description: "Cancel one owned event by id after the user clearly asks to remove it.",
    method: "POST", path: "/agent/db/delete_event",
    inputSchema: objectSchema({ evtId: textSchema }, ["evtId"]),
  },
  {
    name: "smartcore_idea_capture",
    description: "Capture an idea into the user's Inbox for later processing.",
    method: "POST", path: "/agent/idea/capture",
    inputSchema: objectSchema({ title: { type: "string", minLength: 1, maxLength: 300 }, description: { type: "string" }, srcType: { type: "string" }, uploadIds: { type: "array", items: textSchema } }, ["title"]),
  },
  {
    name: "smartcore_media_context",
    description: "Load owner-scoped image attachments for a new media idea. The result includes the images for native vision analysis.",
    method: "GET", path: "/agent/idea/media-context",
    inputSchema: objectSchema({ uploadIds: { type: "array", minItems: 1, maxItems: 10, items: textSchema } }, ["uploadIds"]),
  },
  {
    name: "smartcore_media_job_context",
    description: "Load an owner-scoped media job and its image for native vision analysis before completing or failing the job.",
    method: "GET", path: "/agent/idea/media-job/context",
    inputSchema: objectSchema({ jobId: textSchema }, ["jobId"]),
  },
  {
    name: "smartcore_media_job_complete",
    description: "Mark an image media job ready after inspecting its image and write a short summary.",
    method: "POST", path: "/agent/idea/media-job/complete",
    inputSchema: objectSchema({ jobId: textSchema, summary: { type: "string", minLength: 1, maxLength: 100 } }, ["jobId", "summary"]),
  },
  {
    name: "smartcore_media_job_fail",
    description: "Mark an image media job failed when the image cannot be safely interpreted.",
    method: "POST", path: "/agent/idea/media-job/fail",
    inputSchema: objectSchema({ jobId: textSchema, errorMessage: { type: "string", minLength: 1, maxLength: 300 } }, ["jobId", "errorMessage"]),
  },
  {
    name: "smartcore_idea_to_event",
    description: "Turn one captured idea into an owned plan or deadline.",
    method: "POST", path: "/agent/idea/to_event",
    inputSchema: objectSchema({ ideaId: textSchema, evtType: textSchema, title: textSchema, desc: textSchema, stTime: textSchema, endTime: textSchema, durationMin: { type: "integer" }, hardDdl: { type: "boolean" }, prio: textSchema }, ["ideaId"]),
  },
  {
    name: "smartcore_daily_summary_context",
    description: "Read the daily-summary context for the requested date.",
    method: "GET", path: "/agent/daily-work-context",
    inputSchema: objectSchema({ date: { type: "string" }, timezone: { type: "string" } }, ["date"]),
  },
  {
    name: "smartcore_daily_summary_save",
    description: "Persist the generated daily summary before any external delivery.",
    method: "POST", path: "/agent/daily-summary",
    inputSchema: objectSchema({ reportDate: { type: "string" }, content: { type: "string", maxLength: 20000 }, stat: { type: "string", enum: ["complete", "failed"] }, errorMessage: { type: "string" } }, ["reportDate", "stat"]),
  },
  {
    name: "smartcore_computer_work_block_context",
    description: "Read one scheduled Computer work-block analysis context.",
    method: "GET", path: "/agent/computer/work-block-context",
    inputSchema: objectSchema({ runId: textSchema }, ["runId"]),
  },
  {
    name: "smartcore_computer_work_block_complete",
    description: "Persist one scheduled Computer work-block analysis result.",
    method: "POST", path: "/agent/computer/work-block-analysis",
    inputSchema: objectSchema({ runId: textSchema, status: textSchema, action: textSchema, topicKey: textSchema, title: textSchema, summary: textSchema, progress: textSchema, outcome: textSchema, blocker: textSchema, nextStep: textSchema, planSemanticAssessments: { type: "array" }, evidenceContextIds: { type: "array" }, model: textSchema, promptVersion: textSchema, errorMessage: textSchema }, ["runId", "status"]),
  },
  {
    name: "smartcore_computer_hour_context",
    description: "Read one scheduled Computer hourly context.",
    method: "GET", path: "/agent/computer/hourly-context",
    inputSchema: objectSchema({ deviceId: textSchema, hourStart: textSchema, timezone: textSchema }, ["deviceId", "hourStart"]),
  },
  {
    name: "smartcore_computer_hour_complete",
    description: "Persist one scheduled Computer hourly analysis result.",
    method: "POST", path: "/agent/computer/hourly-analysis",
    inputSchema: objectSchema({ deviceId: textSchema, hourStart: textSchema, status: textSchema, title: textSchema, summary: textSchema, planAssessments: { type: "array" }, topics: { type: "array" }, evidence: { type: "object" }, model: textSchema, promptVersion: textSchema }, ["deviceId", "hourStart", "status"]),
  },
  {
    name: "smartcore_computer_daily_context",
    description: "Read one scheduled Computer daily context.",
    method: "GET", path: "/agent/computer/daily-context",
    inputSchema: objectSchema({ deviceId: textSchema, date: textSchema }, ["deviceId", "date"]),
  },
  {
    name: "smartcore_computer_daily_complete",
    description: "Persist one scheduled Computer daily log.",
    method: "POST", path: "/agent/computer/daily-log",
    inputSchema: objectSchema({ deviceId: textSchema, logDate: textSchema, status: textSchema, title: textSchema, summary: textSchema, topics: { type: "array" }, planAssessments: { type: "array" }, reminderSummary: { type: "array" }, hourlyAnalysisIds: { type: "array" }, workBlockIds: { type: "array" }, phase: textSchema, model: textSchema, promptVersion: textSchema }, ["deviceId", "logDate", "status"]),
  },
 ];

const assistantTool = (name, description, method, path, inputSchema) => ({ name, description, method, path, inputSchema });
const assistantTools = [
  internalTools.find((tool) => tool.name === "smartcore_today"),
  assistantTool(
    "smartcore_plan_query",
    "Query the user's plans. A course request is represented as a plan with course details in its description.",
    "POST",
    "/agent/db/query_events",
    objectSchema({ evtId: textSchema, text: textSchema, stat: { oneOf: [textSchema, { type: "array", items: textSchema }] }, timeRange: { type: "object" }, limit: { type: "integer" } }),
  ),
  assistantTool(
    "smartcore_plan_create",
    "Create one owned plan. Use absolute ISO date-times. For a course, include courseName, teacher, location, weekday, semesterStart, startWeek, and endWeek and it will be stored as plan context.",
    "POST",
    "/agent/db/create_event",
    objectSchema({ title: textSchema, desc: textSchema, stTime: textSchema, durationMin: { type: "integer", minimum: 1 }, prio: textSchema, courseName: textSchema, teacher: textSchema, location: textSchema, weekday: { type: "integer", minimum: 1, maximum: 7 }, semesterStart: textSchema, startWeek: { type: "integer", minimum: 1 }, endWeek: { type: "integer", minimum: 1 } }, ["title", "stTime"]),
  ),
  assistantTool(
    "smartcore_plan_update",
    "Update one owned plan by id.",
    "POST",
    "/agent/db/update_event",
    objectSchema({ evtId: textSchema, title: textSchema, desc: textSchema, stTime: textSchema, durationMin: { type: "integer", minimum: 1 }, prio: textSchema, stat: textSchema }, ["evtId"]),
  ),
  assistantTool(
    "smartcore_plan_complete",
    "Mark one owned plan complete and save the user's outcome.",
    "POST",
    "/agent/db/complete_event",
    objectSchema({ evtId: textSchema, summary: { type: "string", minLength: 1, maxLength: 4000 } }, ["evtId", "summary"]),
  ),
  assistantTool(
    "smartcore_plan_delete",
    "Cancel one owned plan after the user clearly asks to remove it.",
    "POST",
    "/agent/db/delete_event",
    objectSchema({ evtId: textSchema }, ["evtId"]),
  ),
  assistantTool(
    "smartcore_remind_query",
    "Query the user's standalone reminders.",
    "POST",
    "/agent/db/query_events",
    objectSchema({ evtId: textSchema, text: textSchema, stat: { oneOf: [textSchema, { type: "array", items: textSchema }] }, timeRange: { type: "object" }, limit: { type: "integer" } }),
  ),
  assistantTool(
    "smartcore_remind_create",
    "Create one standalone reminder at an absolute ISO date-time.",
    "POST",
    "/agent/db/create_event",
    objectSchema({ title: textSchema, desc: textSchema, triggerTime: textSchema, prio: textSchema }, ["title", "triggerTime"]),
  ),
  assistantTool(
    "smartcore_remind_update",
    "Update one owned reminder by id.",
    "POST",
    "/agent/db/update_event",
    objectSchema({ evtId: textSchema, title: textSchema, desc: textSchema, triggerTime: textSchema, prio: textSchema, stat: textSchema }, ["evtId"]),
  ),
  assistantTool(
    "smartcore_remind_complete",
    "Mark one owned reminder complete and save the user's outcome.",
    "POST",
    "/agent/db/complete_event",
    objectSchema({ evtId: textSchema, summary: { type: "string", minLength: 1, maxLength: 4000 } }, ["evtId", "summary"]),
  ),
  assistantTool(
    "smartcore_remind_delete",
    "Cancel one owned reminder after the user clearly asks to remove it.",
    "POST",
    "/agent/db/delete_event",
    objectSchema({ evtId: textSchema }, ["evtId"]),
  ),
  internalTools.find((tool) => tool.name === "smartcore_media_context"),
  internalTools.find((tool) => tool.name === "smartcore_media_job_context"),
  internalTools.find((tool) => tool.name === "smartcore_media_job_complete"),
  internalTools.find((tool) => tool.name === "smartcore_media_job_fail"),
].filter(Boolean);
const directServerTool = {
  name: "smartcore_server_request",
  description: "Call an allowlisted HTTP endpoint on the configured SmartCore server. Read-only GET is enabled by default. Never use it to bypass SmartCore ownership rules.",
  method: "DIRECT",
  inputSchema: objectSchema({ path: { type: "string", pattern: "^/" }, method: { type: "string", enum: ["GET", "POST", "PUT", "PATCH"] }, body: { type: "object" } }, ["path"]),
};
const hostTools = [
  {
    name: "server_list",
    description: "List a directory on the SmartCore host. Use only when the user asks to inspect the server.",
    inputSchema: objectSchema({ path: textSchema }, ["path"]),
  },
  {
    name: "server_read",
    description: "Read a file on the SmartCore host. Output is capped at 200000 characters.",
    inputSchema: objectSchema({ path: textSchema, maxBytes: { type: "integer", minimum: 1 } }, ["path"]),
  },
  {
    name: "server_write",
    description: "Create or overwrite a file on the SmartCore host. Set append true to add to the file.",
    inputSchema: objectSchema({ path: textSchema, content: textSchema, append: { type: "boolean" } }, ["path", "content"]),
  },
  {
    name: "server_exec",
    description: "Run a shell command on the SmartCore host. Ordinary plans and reminders must use SmartCore tools instead.",
    inputSchema: objectSchema({ command: textSchema, cwd: textSchema, timeoutMs: { type: "integer", minimum: 1000, maximum: 300000 } }, ["command"]),
  },
];
const allTools = [...internalTools, ...assistantTools.filter((tool) => !internalTools.some((item) => item.name === tool.name)), directServerTool];
const visibleTools = mode === "assistant" ? [...assistantTools, directServerTool, ...hostTools] : allTools;

async function scopeToken() {
  if (!scopeFile) throw new Error("SmartCore scope file is not configured");
  const raw = await readFile(scopeFile, "utf8");
  const value = JSON.parse(raw);
  if (!value || typeof value.token !== "string" || value.token.length < 20) throw new Error("SmartCore scope is unavailable");
  return value.token;
}

function pathAllowed(path) {
  return serverAllowedPaths.some((prefix) => path === prefix || path.startsWith(prefix.endsWith("/") ? prefix : `${prefix}/`));
}

async function callDirectServer(args = {}) {
  const path = String(args.path || "").trim();
  const method = String(args.method || "GET").trim().toUpperCase();
  if (!path.startsWith("/") || path.includes("\0") || !pathAllowed(path)) throw new Error("server path is not allowlisted");
  if (!serverAllowedMethods.has(method)) throw new Error(`server method is not allowed: ${method}`);
  const url = new URL(path, `${serverBaseUrl}/`);
  const options = { method, headers: { Accept: "application/json", ...serverHeaders } };
  if (["POST", "PUT", "PATCH"].includes(method)) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(args.body || {});
  }
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(15000) });
  const raw = (await response.text()).slice(0, 256 * 1024);
  let body;
  try { body = raw ? JSON.parse(raw) : null; } catch { body = raw; }
  if (!response.ok) throw new Error(`server ${response.status}: ${typeof body === "string" ? body : JSON.stringify(body)}`);
  return { status: response.status, path, data: body };
}

function normalizeAssistantArgs(name, args = {}) {
  const value = { ...args };
  if (name === "smartcore_plan_query") return { ...value, evtType: "plan", includeLinkedPlans: true };
  if (name === "smartcore_remind_query") return { ...value, evtType: "remind", includeReminders: true };
  if (name.startsWith("smartcore_plan_")) value.evtType = "plan";
  if (name.startsWith("smartcore_remind_")) value.evtType = "remind";
  if (name === "smartcore_plan_create" && value.courseName) {
    const details = [
      `课程：${value.courseName}`,
      value.teacher ? `教师：${value.teacher}` : "",
      value.location ? `地点：${value.location}` : "",
      value.weekday ? `星期：${value.weekday}` : "",
      value.semesterStart ? `学期开始：${value.semesterStart}` : "",
      value.startWeek ? `第${value.startWeek}-${value.endWeek || value.startWeek}周` : "",
    ].filter(Boolean).join("，");
    value.desc = [value.desc, details].filter(Boolean).join("\n");
  }
  return value;
}

async function callHostTool(name, args = {}) {
  let value;
  if (name === "server_list") value = await listHost(args.path);
  else if (name === "server_read") value = await readHost(args.path, args.maxBytes);
  else if (name === "server_write") value = await writeHost(args.path, args.content, Boolean(args.append));
  else if (name === "server_exec") value = await execOnHost(args.command, args.cwd, args.timeoutMs);
  else throw new Error(`unknown SmartCore tool: ${name}`);
  await auditHost({ tool: name, path: value.path || value.cwd || "", command: name === "server_exec" ? String(args.command || "").slice(0, 500) : undefined });
  return value;
}

async function callTool(name, args = {}) {
  if (hostTools.some((tool) => tool.name === name)) {
    if (mode !== "assistant") throw new Error("server tools are only available to the assistant");
    return callHostTool(name, args);
  }
  const tool = allTools.find((item) => item.name === name);
  if (!tool) throw new Error(`unknown SmartCore tool: ${name}`);
  if (name === directServerTool.name) return callDirectServer(args);
  const token = await scopeToken();
  args = normalizeAssistantArgs(name, args);
  const url = new URL(baseUrl + tool.path);
  const options = { method: tool.method, headers: { "X-SmartCore-Agent-Token": agentToken, "X-SmartCore-Agent-Scope": token } };
  if (tool.method === "GET") {
    for (const [key, value] of Object.entries(args || {})) {
      if (Array.isArray(value)) {
        for (const item of value) if (item !== undefined && item !== null && item !== "") url.searchParams.append(key, String(item));
      } else if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
    }
  } else {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(args || {});
  }
  const response = await fetch(url, options);
  const raw = await response.text();
  let body;
  try { body = raw ? JSON.parse(raw) : null; } catch { body = raw; }
  if (!response.ok) throw new Error(`SmartCore ${response.status}: ${typeof body === "string" ? body : JSON.stringify(body)}`);
  if (body?.ok === false) throw new Error((body.errors || ["SmartCore action failed"]).join("; "));
  const value = body?.data ?? body;
  if (!mediaToolNames.has(name)) return value;
  const attachments = Array.isArray(value?.attachments) ? value.attachments : [];
  const content = [{ type: "text", text: JSON.stringify({ ...value, attachments }, null, 2) }];
  for (const attachment of attachments) {
    if (!String(attachment?.mimeType || "").startsWith("image/")) continue;
    const imageUrl = new URL(`/agent/idea/media-context/${encodeURIComponent(String(attachment.uploadId || ""))}`, baseUrl);
    const imageResponse = await fetch(imageUrl, { headers: { "X-SmartCore-Agent-Token": agentToken, "X-SmartCore-Agent-Scope": token } });
    if (!imageResponse.ok) throw new Error(`SmartCore image ${imageResponse.status}: ${attachment.fileName || attachment.uploadId}`);
    const bytes = Buffer.from(await imageResponse.arrayBuffer());
    if (bytes.byteLength > 10 * 1024 * 1024) throw new Error(`image attachment is too large: ${attachment.fileName || attachment.uploadId}`);
    content.push({ type: "image", data: bytes.toString("base64"), mimeType: String(attachment.mimeType) });
  }
  return { __mcpContent: content };
}

function reply(id, result) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, result })}\n`);
}
function error(id, message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", id, error: { code: -32000, message } })}\n`);
}

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let index;
  while ((index = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, index).trim();
    buffer = buffer.slice(index + 1);
    if (!line) continue;
    void (async () => {
      let message;
      try { message = JSON.parse(line); } catch { return; }
      const { id, method, params = {} } = message;
      if (method === "notifications/initialized") return;
      try {
        if (method === "initialize") {
          reply(id, { protocolVersion: "2025-06-18", capabilities: { tools: { listChanged: false } }, serverInfo: { name: "smartcore", version: "1.0.0" } });
        } else if (method === "tools/list") {
          reply(id, { tools: visibleTools });
        } else if (method === "tools/call") {
          const value = await callTool(params.name, params.arguments || {});
          reply(id, value?.__mcpContent ? { content: value.__mcpContent } : { content: [{ type: "text", text: JSON.stringify(value, null, 2) }] });
        } else if (id !== undefined) {
          error(id, `Unsupported MCP method: ${method}`);
        }
      } catch (cause) {
        if (id !== undefined) error(id, cause instanceof Error ? cause.message : String(cause));
      }
    })();
  }
});
