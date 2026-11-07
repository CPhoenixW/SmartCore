import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { after, before, test } from "node:test";
import assert from "node:assert/strict";

let root = "";

before(async () => {
  root = await mkdtemp(path.join(tmpdir(), "smartcore-host-"));
  process.env.DSH_HOST_ROOT = root;
});

after(async () => {
  if (root) await rm(root, { recursive: true, force: true });
});

test("host tools read and write inside the mounted root", async () => {
  const { listHost, readHost, resolveHostPath, writeHost } = await import("./host-access.mjs");
  const written = await writeHost("/opt/smartcore/note.txt", "hello");
  assert.equal(written.bytes, 5);
  const read = await readHost("/opt/smartcore/note.txt");
  assert.equal(read.content, "hello");
  assert.equal(read.truncated, false);
  const listed = await listHost("/opt/smartcore");
  assert.deepEqual(listed.entries.map((item) => item.name), ["note.txt"]);
  const resolved = resolveHostPath("/opt/smartcore/note.txt");
  assert.equal(await readFile(resolved.localPath, "utf8"), "hello");
});

test("host path cannot escape the mount", async () => {
  const { resolveHostPath } = await import("./host-access.mjs");
  const resolved = resolveHostPath("/../../etc/passwd");
  assert.equal(resolved.hostPath, "/etc/passwd");
  assert.ok(resolved.localPath.startsWith(root));
});
