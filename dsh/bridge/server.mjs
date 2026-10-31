import { createServer } from "node:http";
import { mkdir, readdir, unlink, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { spawn } from "node:child_process";
import crypto from "node:crypto";

const HOST = process.env.HOST || "0.0.0.0";
const PORT = Number(process.env.PORT || 18790);
const EVENT_TOKEN = String(process.env.DSH_EVENTS_TOKEN || "");
const SMARTCORE_BASE_URL = String(process.env.SMARTCORE_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const SMARTCORE_AGENT_TOKEN = String(process.env.SMARTCORE_AGENT_TOKEN || process.env.AGENT_API_TOKEN || "");
const DSH_HOME_ROOT = resolve(process.env.DSH_HOME_ROOT || "/data/dsh-home");
const SCOPE_ROOT = resolve(process.env.DSH_SCOPE_ROOT || "/data/scopes");
const PATCH_FILE = resolve(process.env.DSH_PATCH_FILE || "/runtime/dsh/bridge/patch.yml");
const MCP_SERVER_FILE = resolve(process.env.DSH_MCP_SERVER_FILE || "/runtime/dsh/bridge/mcp-server.mjs");
const DSH_BIN = resolve(process.env.DSH_BIN || "/runtime/dsh/node_modules/.bin/dsh");
const DSH_CWD = resolve(process.env.DSH_CWD || "/runtime");
const MODEL_PROVIDER = String(process.env.DSH_PROVIDER || process.env.LLM_PROVIDER || "tokendance");
const TEXT_MODEL = String(process.env.DSH_MODEL || process.env.LLM_MODEL || "deepseek-v4.1-flash-1017");
const VISION_MODEL = String(process.env.DSH_VISION_MODEL || process.env.VISION_MODEL || TEXT_MODEL);
const STARTUP_TIMEOUT_MS = Number(process.env.DSH_STARTUP_TIMEOUT_MS || 30000);
const REQUEST_TIMEOUT_MS = Number(process.env.DSH_REQUEST_TIMEOUT_MS || 600000);
const MAX_BODY_BYTES = 2 * 1024 * 1024;

const runtimes = new Map();
const safePart = (value) => String(value || "unknown").replace(/[^A-Za-z0-9_.:-]+/g, "-").slice(0, 120) || "unknown";
const sessionPart = (value) => safePart(value).slice(0, 100);

async function clearStaleSessionLocks(directory) {
  let entries;
  try { entries = await readdir(directory, { withFileTypes: true }); }
  catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return clearStaleSessionLocks(path);
    if (entry.isFile() && entry.name === "session.lock") {
      try { await unlink(path); } catch (error) { if (error?.code !== "ENOENT") throw error; }
    }
  }));
}

function isMissingSessionError(error) {
  const message = String(error?.message || error || "").toLowerCase();
  return message.includes("session_not_found") || (message.includes("session ") && message.includes("not found"));
}

function equalSecret(actual, expected) {
  if (!expected) return false;
  const a = Buffer.from(String(actual || ""));
  const b = Buffer.from(expected);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function requestBody(request) {
  return new Promise((resolveBody, reject) => {
    let size = 0;
    const chunks = [];
    request.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) { reject(new Error("request body too large")); request.destroy(); return; }
      chunks.push(chunk);
    });
    request.on("end", () => {
      try { resolveBody(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}")); }
      catch { reject(new Error("invalid JSON body")); }
    });
    request.on("error", reject);
  });
}

function send(response, status, body) {
  const payload = JSON.stringify(body);
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(payload), "Cache-Control": "no-store" });
  response.end(payload);
}

function sendSse(response, body) {
  response.write(`data: ${JSON.stringify(body)}\n\n`);
}

function safeToolName(value) {
  const raw = String(value || "").trim();
  if (!raw) return "SmartCore 工具";
  return raw.replace(/^mcp__smartcore__/, "").replace(/^smartcore_/, "").slice(0, 120);
}

function toolStatus(name) {
  const normalized = safeToolName(name).toLowerCase();
  if (normalized.includes("query") || normalized.includes("search")) return "正在查询你的安排…";
  if (normalized.includes("create") || normalized.includes("capture")) return "正在帮你记录…";
  if (normalized.includes("update") || normalized.includes("complete") || normalized.includes("delete")) return "正在更新你的事项…";
  if (normalized.includes("media") || normalized.includes("image")) return "正在处理附件…";
  return "正在调用 SmartCore…";
}

function eventText(event) {
  if (typeof event.text === "string" && event.text.trim()) return event.text.trim();
  if (event.message && typeof event.message.text === "string") return event.message.text.trim();
  if (event.request && typeof event.request.prompt === "string") return event.request.prompt.trim();
  return "请根据事件上下文完成 SmartCore 工作流。";
}

function safePrompt(event) {
  const omit = new Set(["agentScope", "attachments"]);
  const context = {};
  for (const [key, value] of Object.entries(event || {})) {
    if (!omit.has(key) && ["string", "number", "boolean"].includes(typeof value)) context[key] = value;
  }
  if (event.request && typeof event.request === "object") context.request = event.request;
  if (Array.isArray(event.conversationHistory) && event.conversationHistory.length) {
    context.conversationHistory = event.conversationHistory;
  }
  if (event.attachments && Array.isArray(event.attachments)) context.attachments = event.attachments.map((item) => ({ uploadId: item.uploadId, fileName: item.fileName, mimeType: item.mimeType, sizeBytes: item.sizeBytes }));
  const mediaInstruction = event.event_type === "idea_media_edit" && event.jobId
    ? `这是一个图片媒体任务。先调用 mcp__smartcore__smartcore_media_job_context，读取图片后再调用 mcp__smartcore__smartcore_media_job_complete 或 mcp__smartcore__smartcore_media_job_fail。`
    : Array.isArray(event.attachments) && event.attachments.length
      ? "上下文包含图片附件。需要理解图片时先调用 mcp__smartcore__smartcore_media_context，并传入上下文中的 uploadId 列表；不要猜测图片内容。"
      : "";
  return [
    "你是 SmartCore 的个人工作助手。请用中文，简洁、直接地帮助用户完成当前请求。",
    "你只能通过 mcp__smartcore__* 工具读写 SmartCore；不要猜测事件 id，不要访问文件系统、shell 或数据库。",
    "涉及日期时间时，绝对以事件上下文中的 serverNow 和 timezone 为准，禁止自行猜测年份或当前日期；向 Server 传入带时区的绝对 ISO 8601 时间。先查询再修改；完成、删除或转化前确认目标明确。",
    "这是一个连续的个人助手对话。若事件上下文包含 conversationHistory，把它当作最近的对话背景；当前用户输入优先，不要重复旧操作。",
    "需要调用工具时，先用一句自然语言告诉用户你将查询或修改什么，再调用工具；工具完成后再给出简短结果。不要让用户在工具调用期间长时间无反馈。",
    mediaInstruction,
    "工具操作成功后用一句话说明结果；如果无法安全执行，说明缺少的字段。",
    `用户输入：${eventText(event)}`,
    `事件上下文：${JSON.stringify(context, null, 2)}`,
  ].join("\n\n").slice(0, 24000);
}

function sessionIdFor(event) {
  const source = safePart(event.source || "unknown");
  // The PWA owns one durable conversation, but a DSH session must stay
  // bounded. Use one fresh model turn per message and pass a small server-side
  // history window in safePrompt instead of replaying an ever-growing DSH log.
  const isPwaAssistant = event.source === "web" && event.event_type === "assistant_message";
  const turn = isPwaAssistant
    ? (event.clientMessageId || event.event_id || event.eventId || event.messageId || event.conversationId || "default")
    : (event.conversationId || event.chat_id || event.sessionId || event.deviceId || event.jobId || event.reportDate || event.event_type || "default");
  return `smartcore-${safePart(event.userId)}-${source}-${sessionPart(turn)}`;
}

class RpcClient {
  constructor(child) {
    this.child = child;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Set();
    this.buffer = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => this.read(chunk));
    child.on("exit", (code, signal) => {
      const detail = `DSH runtime exited (${code ?? "?"}/${signal ?? ""})`;
      for (const pending of this.pending.values()) pending.reject(new Error(detail));
      this.pending.clear();
    });
    child.on("error", (error) => {
      for (const pending of this.pending.values()) pending.reject(error);
      this.pending.clear();
    });
  }
  read(chunk) {
    this.buffer += chunk;
    let index;
    while ((index = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, index).trim(); this.buffer = this.buffer.slice(index + 1);
      if (!line) continue;
      let message; try { message = JSON.parse(line); } catch { continue; }
      if (message.id !== undefined && (message.result !== undefined || message.error !== undefined)) {
        const pending = this.pending.get(message.id); if (!pending) continue; this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(String(message.error.message || "DSH request failed"))); else pending.resolve(message.result); continue;
      }
      if (message.method) for (const listener of this.listeners) listener(message.method, message.params || {});
    }
  }
  notify(method, params) { this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", method, params })}\n`); }
  request(method, params = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
    const id = this.nextId++;
    return new Promise((resolveRequest, rejectRequest) => {
      const timer = setTimeout(() => { this.pending.delete(id); rejectRequest(new Error(`DSH request timed out: ${method}`)); }, timeoutMs);
      this.pending.set(id, { resolve: (value) => { clearTimeout(timer); resolveRequest(value); }, reject: (error) => { clearTimeout(timer); rejectRequest(error); } });
      this.child.stdin.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    });
  }
  close() { try { this.child.stdin.end(); } catch {} }
}

class DshRuntime {
  constructor(userId, profile = "text") {
    this.userId = userId;
    this.profile = profile;
    this.key = safePart(`${userId}-${profile}`);
    this.model = profile === "vision" ? VISION_MODEL : TEXT_MODEL;
    this.scopeFile = join(SCOPE_ROOT, `${this.key}.json`);
    this.home = join(DSH_HOME_ROOT, this.key);
    this.child = null;
    this.rpc = null;
    this.ready = null;
    this.queue = Promise.resolve();
    this.sessions = new Set();
    this.lastUsed = Date.now();
  }
  async updateScope(token) {
    if (!token) throw new Error("missing SmartCore Agent scope");
    await mkdir(SCOPE_ROOT, { recursive: true });
    await writeFile(this.scopeFile, JSON.stringify({ userId: this.userId, token, updatedAt: new Date().toISOString() }) + "\n", { mode: 0o600 });
  }
  async start() {
    if (this.ready) return this.ready;
    this.ready = (async () => {
      await mkdir(this.home, { recursive: true });
      // DSH persists session content and its lock file in the home volume. A
      // container restart cannot leave the previous child process holding the
      // lock, so remove only stale locks before creating the new child.
      await clearStaleSessionLocks(join(this.home, "sessions"));
      const env = {
        ...process.env,
        DSH_HOME: this.home,
        DSH_SYSTEM_PROMPT: "你是 SmartCore 的个人工作助手。只使用 mcp__smartcore__* 工具完成工作事项，不访问本地文件、shell 或数据库。",
        SMARTCORE_BASE_URL,
        SMARTCORE_AGENT_TOKEN,
        SMARTCORE_SCOPE_FILE: this.scopeFile,
        SMARTCORE_MCP_SERVER: MCP_SERVER_FILE,
        LLM_MODEL: this.model,
        DSH_MODEL: this.model,
      };
      this.child = spawn(DSH_BIN, ["--profile", "sdk-minimal", "--patch", PATCH_FILE], { cwd: DSH_CWD, env, stdio: ["pipe", "pipe", "pipe"] });
      let stderr = "";
      this.child.stderr.setEncoding("utf8");
      this.child.stderr.on("data", (chunk) => { stderr = (stderr + chunk).slice(-4000); });
      this.rpc = new RpcClient(this.child);
      const init = await Promise.race([
        this.rpc.request("initialize", { cwd: DSH_CWD, provider: MODEL_PROVIDER, model: this.model }),
        new Promise((_, reject) => setTimeout(() => reject(new Error(`DSH startup timed out${stderr ? `: ${stderr}` : ""}`)), STARTUP_TIMEOUT_MS)),
      ]);
      if (!init?.serverInfo) throw new Error("DSH runtime returned an invalid initialize response");
      return init;
    })().catch((error) => { this.ready = null; try { this.child?.kill("SIGTERM"); } catch {} throw error; });
    return this.ready;
  }
  async query(sessionId, prompt, scopeToken, onUpdate) {
    const prior = this.queue;
    const run = prior.catch(() => {}).then(async () => {
      await this.updateScope(scopeToken);
      return this._query(sessionId, prompt, onUpdate);
    });
    const queued = run.finally(() => { if (this.queue === queued) this.queue = Promise.resolve(); });
    this.queue = queued;
    return run;
  }
  async _query(sessionId, prompt, onUpdate = () => {}) {
    await this.start();
    const rpc = this.rpc;
    const textParts = [];
    const toolNames = new Map();
    const emit = (update) => {
      try { onUpdate(update); } catch {}
    };
    const listener = (method, params) => {
      if (params.sessionId !== sessionId) return;
      if (method === "session.status") {
        if (params.status === "running") emit({ type: "status", phase: "thinking", message: "正在理解你的请求…" });
        return;
      }
      if (method !== "session.event") return;
      const event = params.event || {};
      const data = event.data || event;
      if (event.type === "assistant/message") {
        const content = data.message?.content || [];
        const text = content.filter((block) => block?.type === "text").map((block) => block.text || "").join("");
        if (text) {
          textParts.push(text);
          emit({ type: "message", text, mode: "new" });
          emit({ type: "status", phase: content.some((block) => block?.type === "tool-call") ? "tool" : "responding", message: content.some((block) => block?.type === "tool-call") ? "准备查询你的资料…" : "正在整理答案…" });
        }
      } else if (event.type === "tool/call") {
        const name = safeToolName(data.name || data.toolName || data.call?.name);
        if (data.callId) toolNames.set(String(data.callId), name);
        emit({ type: "tool", state: "start", name, message: toolStatus(name) });
      } else if (event.type === "tool/result") {
        const name = toolNames.get(String(data.callId || data.message?.callId || "")) || "SmartCore 工具";
        emit({ type: "tool", state: "done", name, message: "资料已返回，继续整理…" });
        emit({ type: "status", phase: "thinking", message: "正在根据结果整理答案…" });
      }
    };
    rpc.listeners.add(listener);
    try {
      if (!this.sessions.has(sessionId)) {
        try { await rpc.request("session/resume", { sessionId }); }
        catch (error) { if (!isMissingSessionError(error)) throw error; }
      }
      await rpc.request("session/prompt", { sessionId, contentBlocks: [{ type: "text", text: prompt }] });
      await rpc.request("session/wait", { sessionId }, REQUEST_TIMEOUT_MS);
      this.sessions.add(sessionId);
      return textParts.join("").trim();
    } finally { rpc.listeners.delete(listener); }
  }
  async stop() { try { await this.rpc?.request("shutdown", {}, 10000); } catch {} try { this.child?.kill("SIGTERM"); } catch {} }
}

function runtimeFor(userId, profile = "text") {
  const key = safePart(`${userId}-${profile}`);
  let runtime = runtimes.get(key);
  if (!runtime) { runtime = new DshRuntime(userId, profile); runtimes.set(key, runtime); }
  runtime.lastUsed = Date.now();
  return runtime;
}

async function handleEvent(event, { waitForResult = false } = {}) {
  if (!event || typeof event !== "object" || !String(event.userId || "").trim()) throw new Error("event userId is required");
  const hasImage = Array.isArray(event.attachments) && event.attachments.some((item) => String(item?.mimeType || "").startsWith("image/"));
  const runtime = runtimeFor(String(event.userId), hasImage ? "vision" : "text");
  const scopeToken = String(event.agentScope || "");
  const sessionId = sessionIdFor(event);
  const work = runtime.query(sessionId, safePrompt(event), scopeToken);
  if (!waitForResult) { void work.catch((error) => console.error("DSH event failed", error)); return { accepted: true, sessionId }; }
  const response = await work;
  return { accepted: true, sessionId, response: response || "已处理。" };
}

async function streamEvent(event, response) {
  if (!event || typeof event !== "object" || !String(event.userId || "").trim()) throw new Error("event userId is required");
  const hasImage = Array.isArray(event.attachments) && event.attachments.some((item) => String(item?.mimeType || "").startsWith("image/"));
  const runtime = runtimeFor(String(event.userId), hasImage ? "vision" : "text");
  const scopeToken = String(event.agentScope || "");
  const sessionId = sessionIdFor(event);
  const queue = [];
  let wake;
  let finished = false;
  const push = (item) => { queue.push(item); if (wake) { const resolve = wake; wake = undefined; resolve(); } };
  const work = runtime.query(sessionId, safePrompt(event), scopeToken, push)
    .then((result) => push({ type: "done", sessionId, response: result || "已处理。" }))
    .catch((error) => push({ type: "error", message: "助手暂时不可用，请稍后重试。" }))
    .finally(() => { finished = true; if (wake) { const resolve = wake; wake = undefined; resolve(); } });

  response.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
  });
  sendSse(response, { type: "status", phase: "thinking", message: "正在连接助手…" });
  while (!finished || queue.length) {
    if (!queue.length) await new Promise((resolve) => { wake = resolve; });
    while (queue.length) sendSse(response, queue.shift());
  }
  await work;
  sendSse(response, { type: "end" });
  response.end();
}

const server = createServer(async (request, response) => {
  try {
    if (request.method === "GET" && request.url === "/healthz") return send(response, 200, { status: "ok", runtimeCount: runtimes.size, provider: MODEL_PROVIDER, model: TEXT_MODEL, visionModel: VISION_MODEL });
    const authorization = String(request.headers.authorization || "");
    if (!equalSecret(authorization.startsWith("Bearer ") ? authorization.slice(7) : "", EVENT_TOKEN)) return send(response, 401, { detail: "invalid or missing DSH event token" });
    if (request.method !== "POST" || !["/api/smartcore/events", "/api/smartcore/query", "/api/smartcore/stream"].includes(request.url)) return send(response, 404, { detail: "not found" });
    const event = await requestBody(request);
    if (request.url === "/api/smartcore/stream") return await streamEvent(event, response);
    const result = await handleEvent(event, { waitForResult: request.url === "/api/smartcore/query" });
    return send(response, request.url === "/api/smartcore/events" ? 202 : 200, result);
  } catch (error) {
    console.error("DSH bridge request failed", error);
    return send(response, 503, { detail: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(PORT, HOST, () => console.error(`SmartCore DSH bridge listening on ${HOST}:${PORT}`));
const shutdown = async () => { server.close(); await Promise.all([...runtimes.values()].map((runtime) => runtime.stop())); process.exit(0); };
process.on("SIGTERM", shutdown); process.on("SIGINT", shutdown);
