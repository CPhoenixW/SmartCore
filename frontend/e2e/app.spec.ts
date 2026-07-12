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

test("shows independent panes and a live graphical create preview", async ({ page }) => {
  await page.goto("./add");
  await expect(page.locator(".split-scroll-layout")).toBeVisible();
  await expect(page.locator(".split-scroll-column")).toHaveCount(2);
  await page.getByLabel("标题").fill("复习传热学");
  await expect(page.locator(".visual-preview")).toContainText("复习传热学");
  await expect(page.getByRole("heading", { name: "预览" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "常用模板" })).toBeVisible();
});

test("keeps legacy inspire and log URLs compatible", async ({ page }) => {
  await page.goto("./inspire");
  await expect(page.getByRole("heading", { name: "灵感" })).toBeVisible();
  await page.goto("./log");
  await expect(page.getByRole("heading", { name: "日志" })).toBeVisible();
});
