import { spawn } from "node:child_process";
import { appendFile, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";

const OUTPUT_LIMIT = 200_000;
const WRITE_LIMIT = 32 * 1024 * 1024;

export function hostRoot() {
  return path.resolve(process.env.DSH_HOST_ROOT || "/host");
}

export function resolveHostPath(input) {
  const raw = String(input ?? "/").trim() || "/";
  if (raw.includes("\0")) throw new Error("path is invalid");
  const hostPath = path.posix.resolve(raw.startsWith("/") ? raw : `/${raw}`);
  const localPath = path.resolve(hostRoot(), hostPath.slice(1));
  const root = hostRoot();
  if (localPath !== root && !localPath.startsWith(`${root}${path.sep}`)) {
    throw new Error("path escapes host root");
  }
  return { hostPath, localPath };
}

function cap(text) {
  const value = String(text ?? "");
  if (value.length <= OUTPUT_LIMIT) return { text: value, truncated: false };
  return { text: value.slice(0, OUTPUT_LIMIT), truncated: true };
}

export async function listHost(input) {
  const { hostPath, localPath } = resolveHostPath(input);
  const info = await stat(localPath);
  if (!info.isDirectory()) throw new Error("path is not a directory");
  const names = await readdir(localPath);
  const entries = [];
  for (const name of names.slice(0, 500)) {
    try {
      const child = await stat(path.join(localPath, name));
      entries.push({ name, type: child.isDirectory() ? "dir" : "file", size: child.size });
    } catch {
      entries.push({ name, type: "unknown", size: 0 });
    }
  }
  return { path: hostPath, entries, truncated: names.length > 500 };
}

export async function readHost(input, maxBytes = OUTPUT_LIMIT) {
  const { hostPath, localPath } = resolveHostPath(input);
  const info = await stat(localPath);
  if (!info.isFile()) throw new Error("path is not a file");
  const limit = Math.min(Math.max(1, Number(maxBytes) || OUTPUT_LIMIT), OUTPUT_LIMIT);
  const bytes = await readFile(localPath);
  return {
    path: hostPath,
    size: bytes.byteLength,
    truncated: bytes.byteLength > limit,
    content: bytes.subarray(0, limit).toString("utf8"),
  };
}

export async function writeHost(input, content, append = false) {
  const { hostPath, localPath } = resolveHostPath(input);
  const text = String(content ?? "");
  const bytes = Buffer.byteLength(text);
  if (bytes > WRITE_LIMIT) throw new Error("write exceeds 32MB");
  await mkdir(path.dirname(localPath), { recursive: true });
  await writeFile(localPath, text, { flag: append ? "a" : "w" });
  return { path: hostPath, bytes };
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'\\''`)}'`;
}

export function execOnHost(command, cwd = "/", timeoutMs = 60_000) {
  const script = String(command ?? "").trim();
  if (!script) throw new Error("command is required");
  const { hostPath } = resolveHostPath(cwd || "/");
  const timeout = Math.min(Math.max(1000, Number(timeoutMs) || 60_000), 300_000);
  return new Promise((resolve, reject) => {
    const child = spawn(
      "nsenter",
      ["-t", "1", "-m", "-u", "-i", "-n", "--", "bash", "-lc", `cd ${shellQuote(hostPath)} && ${script}`],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => child.kill("SIGKILL"), timeout);
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const out = cap(stdout);
      const err = cap(stderr);
      resolve({
        cwd: hostPath,
        exitCode: code,
        stdout: out.text,
        stderr: err.text,
        truncated: out.truncated || err.truncated,
      });
    });
  });
}

export async function auditHost(entry) {
  try {
    const target = resolveHostPath("/var/log/smartcore-dsh-server.log");
    await mkdir(path.dirname(target.localPath), { recursive: true });
    await appendFile(target.localPath, `${JSON.stringify({ at: new Date().toISOString(), ...entry })}\n`);
  } catch {
    // Audit must not block a requested server operation.
  }
}
