import { expect, test } from "@playwright/test";

const empty = { ok: true, data: [] };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/user/me", (route) => route.fulfill({ json: { ok: true, data: { displayName: "Test", language: "zh", reminderChannel: "screen" } } }));
  await page.route("**/api/evt**", (route) => route.fulfill({ json: empty }));
  await page.route("**/api/idea", (route) => route.fulfill({ json: empty }));
  await page.route("**/api/devState/latest**", (route) => route.fulfill({ json: { ok: true, data: null } }));
});

test("navigates across the Vue workbench", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByRole("heading", { name: "总览" })).toBeVisible();
  await page.getByRole("link", { name: "添加事件" }).click();
  await expect(page.getByRole("heading", { name: "添加事件" })).toBeVisible();
  await page.getByRole("button", { name: "提醒" }).click();
  await expect(page.getByText("提醒时间")).toBeVisible();
});

test("keeps legacy inspire and log URLs compatible", async ({ page }) => {
  await page.goto("./inspire");
  await expect(page.getByRole("heading", { name: "灵感" })).toBeVisible();
  await page.goto("./log");
  await expect(page.getByRole("heading", { name: "日志" })).toBeVisible();
});
