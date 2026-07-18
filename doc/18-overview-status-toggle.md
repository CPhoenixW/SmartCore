# Overview 一键状态切换

## 交互规则

- Overview 的日期事项列表仅展示 `todo` 与 `done`，已取消事项不参与二态复选框。
- 未勾选表示 `todo`；勾选表示 `done`。
- 点击复选框只更新状态，不触发事项卡片的编辑跳转。
- 请求进行中禁用当前复选框，失败时保留原状态并显示错误提示。

## 技术方案

- 复用现有 `PATCH /api/evt/{evtId}`，请求体仅包含 `stat`。
- 成功后刷新 `events` 查询缓存，使 Overview 统计、日期列表及其他页面保持一致。
- 无数据库迁移、无新增依赖；回滚只需回退应用镜像。

## 验收

- `todo → done` 和 `done → todo` 均可一次点击完成。
- 点击复选框不会打开 Update Event。
- 当前请求期间不会重复提交。
- Ruff、pytest、Vitest、前端构建和 `/healthz` 通过。
