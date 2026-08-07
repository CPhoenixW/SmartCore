# 模型路由与 WorkBlock 返回契约改造计划

创建时间：2026-08-07 20:07:31 +08

状态：实施完成，等待后续部署授权

验证结果：`.venv/bin/pytest -q`（278 passed）、Ruff、`bash -n` 和 `git diff --check`
均通过；本次未执行候选容器验证或生产部署。

## 一、已确认的需求

1. OpenClaw 没有图片的任务，使用
   `tokendance/deepseek-v4-flash-0731`。纯文本和只有文件的消息都属于这一路径。
   文件仍然只保存，不读取文件内容。
2. 只要任务中包含至少一张受支持的图片，就使用
   `tokendance/qwen3.7-plus`，并把图片作为原生多模态输入。文字、图片、文件混合时也走
   Qwen。
3. 文本任务遇到超时、网络/API 错误、OpenClaw 非零退出或空的最终答案时，可以回退一次
   Qwen。内容格式校验失败时不能切换模型，直接失败。图片任务的 Qwen 失败时不能回退
   DeepSeek。
4. 工作台的 Server 模型（`LLM_MODEL`）改为 `deepseek-v4-flash-0731`。
5. 连续 Computer WorkBlock 分析继续由 Server 直接调用一次
   `deepseek-v4-flash-0731`。模型返回格式错误时直接将本次分析标记为失败，不发送修复请求，
   也不额外调用模型。上下文中的 Plan 如果缺少语义匹配，Server 补为
   `unclear + low confidence`。
6. WorkBlock 的 `action` 完全由 Server 规则决定。模型只返回标题、总结、进展、结果、阻碍、
   下一步和 Plan 语义匹配。现有 API/数据库中的 action 字段继续保留，用于审计和兼容，但不
   再接受模型决定或否决动作。
7. 每日用户工作日报使用现有 `daily_summary` 流程，走无图片的 DeepSeek 路径。
   `dailyWorkContext` 返回的 Codex 汇报、Plan 和当天 Computer WorkBlock 都是日报事实来源的
   一部分。旧的 `computer_daily_work_log` 不作为日报前置条件。
8. 不再使用 `deepseek-ocr-2`。保留的 Server 图片兼容函数改用 Qwen；目前没有发现它的
   活跃业务调用方。
9. “今日”按 `Asia/Shanghai` 计算，聚合当前用户全部 Computer 设备；当天仍开放的 WorkBlock
   也可以进入日报。

## 二、范围与授权边界

- 计划确认后，允许修改本地源代码、测试、文档和部署模板。
- 工作区中已有的 Computer 模型默认值、输出预算等未提交改动属于用户改动，必须保留并在其
  基础上继续工作。
- 本次不做数据库迁移、不重写数据、不访问或编辑生产 checkout、不部署、不提升生产、不创建
  分支、不提交、不推送、不创建 PR。
- 不编辑生产 `.env`，不把真实密钥、数据库、日志或附件加入 Git。
- 后续生产启用必须另行授权，并遵守候选构建、验证、提升和回滚流程。

## 三、环境核对结果

- 本地仓库：`/Users/phoenixw/SmartCore`，分支 `dev`，基线提交 `40f4287`。
- 本地环境：macOS arm64；已有 `.venv`、Python、Node/npm；本机没有 Docker CLI，因此不能
  在本机运行候选容器验证。
- 生产主机：`hcss-ecs-ad51`，Ubuntu x86_64。
- `/opt/smartcore` 为 `main` 分支、提交 `40f4287`，工作树干净；生产 App 与 Adapter 镜像
  都来自该提交。
- 生产 App、Adapter、Caddy、Cloudflared、Tunnel Boundary 五个 Compose 服务均为 healthy。
- 生产容器内 `Settings()` 实际解析为：
  - `llm_model=deepseek-v4-pro`
  - `vision_model=deepseek-ocr-2`
  - `computer_analysis_model=deepseek-v4-flash`
  - Computer 直连分析开启，OpenClaw fallback 关闭
  - `daily_summary_enabled=true`
- 生产 OpenClaw 当前只有 `smartcore` profile，固定为
  `tokendance/qwen3.7-plus`。
- 当前 OpenClaw TokenDance 模型目录有 `deepseek-v4-pro`、`kimi-k3` 和 `qwen3.7-plus`，还
  没有 `deepseek-v4-flash-0731`；候选配置必须先注册该模型。
- `openclaw-gateway.service` 当前 active，但状态命令报告 scope/pairing approval 警告。该
  警告属于现有运维前置条件，不能在业务代码中绕过；候选发布时单独验证。
- 直接调用 OpenClaw 二进制会遇到宿主机 Node.js 20.20.2，而该二进制要求 22.19+；运维检查
  必须通过仓库脚本，让脚本先使用 OpenClaw 自带的 Node runtime。

## 四、总体设计

### 4.1 OpenClaw 模型分流

本地无法验证 OpenClaw 是否支持未文档化的单次 `--model` 参数，而 Adapter 已经在使用确定可用
的 `--agent` 参数。因此使用两个固定 profile：

- `smartcore`：文本 profile，模型为 `tokendance/deepseek-v4-flash-0731`，保留为默认和兼容
  Agent ID。
- `smartcore-vision`：图片 profile，模型为 `tokendance/qwen3.7-plus`，使用相同的
  SmartCore skill 和受限 `exec` 工具。

Adapter 增加一个基于图片 MIME 类型的判断函数，在创建 session key 前选择 profile：

- 没有图片：选择文本 profile。
- 有图片：选择图片 profile。

这样文本和图片任务不会复用错误模型的对话 session。日志只记录事件 ID、选择的 profile、模型、
是否回退和失败类型，不记录 scope、token、附件路径或正文。

现有 `configure_openclaw_qwen.sh` 改成同时配置两个 profile，并保留现有备份、配置校验、Gateway
重启失败自动恢复机制。若新增名称更准确的通用脚本，旧脚本保留兼容入口。

### 4.2 Server 文本和图片模型

- `Settings.llm_model` 和 `deploy/env.example` 中的 `LLM_MODEL` 改为
  `deepseek-v4-flash-0731`。
- `Settings.vision_model` 和 `deploy/env.example` 中的 `VISION_MODEL` 改为
  `qwen3.7-plus`。
- 保留 `analyze_image()` 作为兼容函数，但更新注释、错误信息、测试和文档，不再称为 OCR
  模型。

### 4.3 Computer WorkBlock 分析

Server 继续负责活动采集、边界识别、触发器、租约、重试和最终动作。模型只负责解释脱敏证据。

Server 根据触发器固定生成 action：

```text
start       -> start
switch      -> switch
complete    -> complete
plan_change -> extend
refresh     -> extend
```

实现要点：

- 从模型推理 Schema 中移除 action。
- `WorkBlockAnalysisBody.action` 暂时保留为兼容/审计字段，由 Server 注入；调用方提交的值不
  得改变 Server 推导结果。
- JSON 无法解析、枚举非法、证据 ID 越权、Plan ID 不在上下文中等错误仍然严格失败。
- 只对“遗漏的、但属于上下文的 Plan 语义匹配”补 `unclear/low`；不放宽错误字段和越权 ID
  校验。
- OpenClaw fallback skill 和 Adapter 提示词不再要求模型选择 action。

### 4.4 每日工作日报

不新增 Computer 日报接口，也不让 OpenClaw 读取数据库。现有 `dailyWorkContext` 已经聚合：

- Codex 当日项目汇报；
- 当天 Computer WorkBlock；
- Plan 及其人工结果。

只需强化日报提示词和测试，明确 WorkBlock 是事实来源之一，并确认当天已生成的标题、总结、
进展和结果字段能传给日报模型。日报事件没有图片，因此由文本 profile 使用 DeepSeek；只有
传输级失败才允许 Qwen 回退。

## 五、预计修改的文件

- `openclaw/adapter/adapter.py`、`deploy/adapter.env.example`、
  `tests/unit/test_openclaw_adapter.py`：模型/profile 选择、session 隔离、回退和日志。
- `scripts/configure_openclaw_qwen.sh`（必要时增加通用脚本）、`deploy.md`、OpenClaw 集成文档：
  两个 profile、模型注册和候选操作说明。
- `app/server/config.py`、`deploy/env.example`、`app/server/llm/gateway.py`、
  `tests/unit/test_llm_gateway.py`：DeepSeek 文本默认和 Qwen 图片兼容入口。
- `app/server/computer/contracts.py`、`app/server/computer/llm_analysis.py`、
  `app/server/computer/work_blocks.py`、Computer Agent skill/契约及相关测试：Server-owned
  action 和缺失 Plan 匹配补全。
- `docs/architecture.md`、`docs/integrations.md`、`docs/media.md`、`docs/devices.md`、
  `docs/api-contracts.md`、`docs/decisions.md`、`docs/delivery-history.md`：只更新已经稳定的
  当前行为。

## 六、实施顺序

1. 先补 Adapter 路由函数和单元测试，覆盖文本、文件、图片和混合附件。
2. 更新 OpenClaw 两个 profile 的配置脚本和模板变量，不触碰真实服务器配置。
3. 更新 Server 默认模型和 Qwen 图片兼容函数，再调整 Gateway 测试。
4. 重构 WorkBlock 推理和保存边界，让 action 完全由 Server 生成；补齐严格失败和 Plan 默认
   匹配测试。
5. 强化日报提示词和 `dailyWorkContext` 回归测试。
6. 对照代码、`GET /agent/tools` 和测试，更新现行领域文档。
7. 检查完整 diff，运行验证并报告不能在本地执行的候选/生产检查。

## 七、验证矩阵

- `tests/unit/test_openclaw_adapter.py`：
  - 无图片和只有文件时选择 DeepSeek；
  - 有图片和混合附件时选择 Qwen；
  - 文本传输错误只回退一次；
  - 格式错误不切模型；
  - 图片 Qwen 失败不走 DeepSeek；
  - session 和日志不泄露敏感字段。
- `tests/unit/test_llm_gateway.py`：工作台默认模型为 0731，图片请求模型为 Qwen。
- `tests/unit/test_computer_llm_analysis.py`、`tests/unit/test_computer_work_blocks.py`：
  - 每次直接分析只调用一次模型；
  - 所有触发器的 action 都由 Server 固定生成；
  - malformed JSON 严格失败；
  - 缺失 Plan 匹配补为 `unclear/low`。
- `tests/api/test_daily_work_context.py`、`tests/api/test_reports_weather.py`、
  `tests/contract/test_agent_api.py`：用户隔离、WorkBlock 出现在日报上下文、Agent 契约不破坏。
- 迭代期间先跑聚焦测试，完成后至少运行：
  - `.venv/bin/pytest -q`
  - `.venv/bin/ruff check app/server tests`
  - 修改后的 Shell 脚本执行 `bash -n`
- 本地没有 Docker，候选启动、OpenClaw profile 实际解析、Gateway pairing 状态和 `/healthz`
  只在得到部署授权后验证；本次不声称这些检查已通过。

## 八、性能评估

本地没有适合的远程模型性能基线，也不会未经授权调用付费模型或压测生产。此次重点验证：

- Computer 每个触发器仍然只产生一次 Server LLM 请求；
- OpenClaw 只有明确允许的文本传输失败才产生第二次请求；
- 图片任务不会错误地调用文本模型。

因此本次不做吞吐压测；会把无法测量的候选/生产延迟列为剩余风险，而不是声称性能通过。

## 九、风险、数据影响与回滚

- 不新增数据库表、不迁移数据、不重写历史 WorkBlock；已有 action 值保持不变。
- Qwen profile 或 DeepSeek 0731 注册错误由配置脚本现有的 0600 备份和回滚机制隔离；只能在
  单独授权的候选阶段验证。
- 所有模型输出和附件元数据继续视为不可信数据，保持 scope、媒体隔离、owner 校验和文件只
  保存不读取的边界。
- 本地回滚只通过审阅并手动撤销本次作用域 diff，不使用 destructive Git 命令。
- 生产回滚仍使用 `deploy_prod.sh --rollback` 和 OpenClaw 配置备份路径，本次不执行。
