# SmartCore 架构与清理审计报告

> 审计日期：2026-07-17（Asia/Singapore）
> 范围：本地仓库、GitHub `CPhoenixW/SmartCore`、`ssh server` 的 `/opt` 与运行中的容器/systemd。
> 本次仅检查，**未删除**代码、服务器文件、Docker 资源或 GitHub 分支。

## 结论摘要

SmartCore 当前是一个以服务器为权威节点的单体 FastAPI 应用。生产链路可运行，但代码、文档和部署工作目录均保留了多轮重构与临时验证的遗留物，造成了明显的认知和磁盘冗余。

最优先的清理不是删除业务功能，而是：

1. 清除已合并/已废弃的 GitHub 远端分支；
2. 清除服务器上没有被运行时引用的 PR 工作目录与 Docker 测试镜像/构建缓存；
3. 处理两个有未提交改动的工作目录后，再决定是否清除；
4. 将文档收敛为一套与现行实现一致的架构和部署说明，再逐步移除代码里的 legacy 路由。

## 当前实际架构

```text
外部 Feishu
  -> Cloudflare Tunnel（宿主机容器）
  -> tunnel-boundary Caddy（172.17.0.1:8000，仅 /feishu/event）
  -> FastAPI app

公网 HTTPS
  -> Caddy（80/443，仅 /feishu/event）
  -> FastAPI app

Tailscale 客户端
  -> FastAPI app（100.65.243.93:8000）
  -> /work、/screen、/api、/agent 等内部功能

FastAPI app
  -> SQLite Docker volume（10.85 MB）
  -> APScheduler
  -> Feishu API
  -> WebSocket 副屏
  -> LLM gateway

独立 systemd 服务：smartcore-openclaw-adapter
  -> 读取 /opt/smartcore-openclaw-adapter/.env
  -> 对接 OpenClaw/SmartCore
```

生产 Compose 项目为 `/opt/smartcore/deploy/docker-compose.yml`，运行 `app`、`caddy`、`tunnel-boundary` 三个服务。`app` 容器仅挂载 Docker volumes（数据与备份），**没有挂载其它 `/opt/smartcore-*` 工作目录**。另有运行中的 `cloudflared` 与 `derper` 容器，它们不属于 SmartCore Compose 栈。

## 代码层架构观察

### 有效核心

- `app/main.py` 是唯一组装点：注册认证、管理、事件、设备、Feishu、Agent、副屏和前端静态路由。
- `app/new_core/` 是业务和数据主干：SQLAlchemy 模型、CRUD、事项关系、DDL、课程、提醒、通知与维护任务。
- `app/feishu/` 处理回调验签、消息、机器人配置、卡片和 Feishu API。
- `app/device/`、`app/screen/` 实现设备状态、照片请求、副屏 WebSocket 与通知。
- `app/scheduler/service.py` 使用 APScheduler 定时调用提醒扫描。
- Vue 前端位于 `frontend/`，构建产物由 `app/web/dist` 提供 `/work`。

### 复杂度来源与待收敛点

1. `app/agent/` 同时存在 `routes.py`、`v2_routes.py`、`legacy_time_routes.py`、关系读写与反馈路由；`main.py` 全部注册。这是最明确的“新旧并行”边界，应先列出实际调用方和 OpenAPI 使用情况，再移除 `legacy_time_routes.py` 及被新 Agent API 覆盖的端点。
2. `app/api/`、`app/device/`、`app/user_device/`、`app/agent/routes.py` 都暴露设备相关能力，路由边界不清晰。建议按 `identity`、`device`、`event`、`agent`、`admin` 五个域收口，并建立端点清单。
3. `app/new_core/event_relations.py`（约 1,032 行）、`app/agent/routes.py`（约 739 行）、`app/new_core/crud.py`（约 699 行）已成为高耦合模块。它们不是“可直接删”的冗余，而是应按事务边界拆分为事件、课程、提醒、审计等服务。
4. `app/new_core/relation_compat.py` 表明仍有兼容层；而重构文档声明“不做旧表兼容”。应先验证数据库中是否仍存在旧表/旧客户端请求，再删除该层。

## 文档与实现漂移

- 根 `README.md` 仍以“v1 学生秘书”和 `/dashboard/` 为中心；当前前端实际入口为 `/work`。
- `doc/README.md` 将编号文档定义为历史记录，将 `doc/refactor/` 定义为唯一有效架构；但根 README 和 `deploy.md` 仍保留大量旧部署/交互描述。
- 目标架构要求删除旧 OpenClaw skill 和旧确认卡片，并直接使用新表；实际仓库仍含 `openclaw/skills/smartcore/`、Agent legacy 路由和兼容模块。

建议指定 `doc/refactor/target-arch.md` 为产品设计基线，但另建一页“当前已部署架构”，明确哪些目标已经落地、哪些仍是计划；不要让 README 同时承担历史、目标和运维手册三种角色。

## 服务器 `/opt` 清理评估

### 必须保留

| 路径/资源 | 原因 |
| --- | --- |
| `/opt/smartcore` | 当前生产 Compose 源目录，`main`，干净，部署 HEAD 为 `fec862e`。 |
| Docker volumes `deploy_smartcore-data`、`deploy_smartcore-backups` | 生产 SQLite 数据和备份，不能以 Docker 清理命令删除。 |
| `/opt/smartcore-openclaw-adapter` | 被 `smartcore-openclaw-adapter.service` 的 `WorkingDirectory` 和 `ExecStart` 直接引用。 |
| `cloudflared`、`derper` | 正在运行，但归属需另行确认，不能作为 SmartCore 冗余直接处理。 |

### 可删除候选（运行时未引用，删除前仍应二次核验）

下列目录均是历史 PR/验证工作目录，当前 Compose 容器没有挂载它们，且 Git 工作区干净：

- `/opt/smartcore-admin-feishu`
- `/opt/smartcore-board-work`
- `/opt/smartcore-course-query`
- `/opt/smartcore-feishu-multichat`
- `/opt/smartcore-feishu-pairing`
- `/opt/smartcore-settings-layout`
- `/opt/smartcore-user-device`

总量约 19 MB；容量不大，但会误导后续排障和部署操作。

### 暂不删除

| 路径 | 原因 | 建议 |
| --- | --- | --- |
| `/opt/smartcore-dev`（约 140 MB） | 有 6 个未提交改动，当前分支落后生产。 | 先查看 diff，必要时提交/导出补丁；确认无价值后删除。 |
| `/opt/smartcore-feishu-processing-ack`（约 146 MB） | 有 1 个未提交改动。 | 同上。 |
| `/opt/smartcore-openclaw-adapter` | 运行中的 systemd 服务依赖。 | 先纳入仓库或替换为正式 OpenClaw 集成后才可移除。 |

### Docker 冗余

- 有一个已退出的测试容器 `smartcore-feishu-tests`；
- 有至少 5 个无容器引用的 SmartCore 测试镜像，约 0.8–1.0 GB 独占层；
- Docker BuildKit 构建缓存为 **12.4 GB**，是服务器上最主要的可回收空间。

建议先执行可预览操作，再按确认后的保留窗口清理：`docker builder prune --filter until=168h`。不要使用带 `--volumes` 的全量 `docker system prune`，以免误删生产数据卷。

## GitHub 分支清理评估

远端目前有 24 个分支（含 `main`），其中 23 个非主分支均可归档清理：

- 已合并 PR 关联分支：`agent/add-login-and-avatar-fix`、`agent/complete-vue-migration`、`agent/fix-vue-regressions`、`agent/remove-legacy-ui`、`agent/restore-split-workbench`、`codex/admin-feishu-bot-runtime`、`codex/ddl-reminders-admin-feishu`、`codex/settings-layout-fit`、`fix/user-lang-ddl-device-chart-20260708`、`ui/work-screen-refine-20260706`。
- 已被 `main` 完全包含的临时/直推分支：`agent/vue-frontend-foundation`、`apply-to-default-branch`、`default-direct-test`、`feature/course-occurrences-reminders-20260709`、`main-apply-test`、`main-default-direct`、`main-direct-apply`、`no-pr-main-apply`、`screen-overrides-main-check`、`test-temp-123`、`tmp-direct-main-fix-20260709`、`update-file-main-needed`。
- `agent/verify-frontend-build` 对应 PR #5，已关闭未合并；它仅比旧提交多 1 个提交，且当前 `main` 已领先 35 个提交。作为历史验证分支，建议删除；若担心内容遗漏，先打 tag 或导出补丁。

有些“已合并 PR”分支在 Git 历史上看似未合并，是因为 PR 使用 squash/rebase 合并；这是正常现象。本报告按 GitHub PR 状态与提交关系共同判断。

推荐策略：保留 `main` 作为唯一长期分支；短期工作一律以 PR 分支进行，并在合并后自动删除远端 head branch。删除前为尚未合并的分支创建临时 tag 的做法仅在确有保留价值时采用。

## 推荐执行顺序

1. 对 `/opt/smartcore-dev` 和 `/opt/smartcore-feishu-processing-ack` 导出 `git diff`，确定未提交改动是否有价值。
2. 确认上表 7 个干净工作目录无外部脚本/cron 引用后删除。
3. 删除 23 个 GitHub 非主分支，并启用仓库“自动删除已合并 head branch”。
4. 删除已退出测试容器和无引用测试镜像；以保守时间窗口清理 BuildKit cache。
5. 整合 README、部署手册和重构文档；建立 API/路由清单后，再实施 legacy Agent 与兼容层删除。

## 风险控制

- 删除 `/opt` 目录前，需确认 systemd、cron、Docker Compose、Cloudflare 配置没有引用；本次已确认运行容器无挂载，但未替代完整引用审计。
- 删除 Docker 资源时绝不删除 `deploy_smartcore-data`、`deploy_smartcore-backups`、Caddy volumes。
- 删除 GitHub 分支不会删除已合并提交；对关闭未合并的 `agent/verify-frontend-build`，可先导出补丁以防遗漏。
- 当前生产 SQLite 位于 Docker volume，而不是 `/opt/smartcore/data`；清理工作目录不等于清理生产数据，但任何部署前仍应保留数据库备份。
