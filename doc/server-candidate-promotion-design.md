# 服务器候选镜像验证与生产晋升设计

## 目标

- 日常修改进入长期 `dev` 分支，不直接修改 `main`。
- 服务器复用 Docker BuildKit 缓存构建候选镜像。
- 候选镜像先通过静态检查、单元测试、前端测试、镜像启动和健康检查。
- 人工确认后，将已经验证的同一镜像晋升到生产，不再次构建。
- `main` 只允许快进到已验证的 `dev` 提交；生产失败自动回滚。
- GitHub 只保留轻量脚本检查，完整检查不再占用 GitHub 临时运行器。

## 验收标准

1. `scripts/deploy_dev.sh` 只接受干净的 `dev` 工作区，快进拉取 `origin/dev`。
2. dev 流程构建带 Git SHA 的 app 和 Adapter 镜像，并复用锁文件对应的 Docker 层。
3. 后端 Ruff、pytest、Vitest 和前端构建均在服务器容器中执行。
4. 候选 app 镜像使用独立临时 SQLite 数据启动并通过 `/healthz`，不挂载生产 volume。
5. 验证结果记录镜像 ID、提交 SHA 和时间；镜像被替换后不能晋升。
6. `scripts/promote_prod.sh` 只晋升已验证且等于 `origin/dev` 的提交。
7. 晋升前要求 `origin/main` 是候选提交的祖先，并以快进方式把该提交写入 `main`。
8. 生产切换直接使用候选镜像，不运行 `docker build`。
9. 生产切换前备份 SQLite；健康检查失败自动恢复上一组 app/Adapter 镜像。
10. dev、测试和生产使用不同的 Compose 项目、端口和数据卷。

## 分支与发布流程

```text
feature commit -> dev
                   |
                   v
          deploy_dev.sh -- 构建、测试、记录候选
                   |
            人工访问 dev 确认
                   |
                   v
          promote_prod.sh -- dev 快进 main
                   |        同一镜像切换生产
                   v
             健康检查 / 自动回滚
```

`dev` 是长期集成分支。生产晋升使用 fast-forward，因此被测试的提交 SHA 与
`main`、生产镜像完全一致，不创建一个未经测试的新 merge commit。

## 数据、API 与 UI

- 不修改数据库结构、API 合约或 UI。
- 无数据迁移。
- 候选启动使用一次性 tmpfs；结束后删除测试容器。
- 可选的常驻 dev app 使用独立的 `smartcore-dev-data` volume 和
  `127.0.0.1:18000`，不会访问生产数据库。

## 安全边界

- dev 检查不读取生产 `.env`，使用生成的非敏感测试配置。
- 不启动 dev Cloudflared、Caddy、调度器或外部消息集成。
- Adapter 只做离线语法/启动参数检查；不会连接生产 OpenClaw Gateway。
- 晋升命令不打印 env 文件或令牌。
- Git 推送仅允许 `origin/main` 快进到已经验证的 `origin/dev`。
- 不删除生产 volume，不重写 Git 历史。

## 回滚

- 切换前为正在运行的 app 和 Adapter 镜像保留提交标签。
- 新版本健康检查失败时恢复上一组镜像。
- 手工回滚继续使用 `scripts/deploy_prod.sh --rollback [SHA]`。
- 回滚只切换镜像，不倒退数据库；本次没有 schema 变更。

## 测试矩阵

| 场景 | 预期 |
| --- | --- |
| 仅业务源码变化 | pip/npm 依赖层命中缓存 |
| 锁文件变化 | 只重建对应依赖层 |
| 后端或前端核心检查失败 | 不记录候选，不能晋升 |
| 候选镜像无法健康启动 | 删除临时资源，不能晋升 |
| 候选镜像 ID 被覆盖 | 晋升拒绝 |
| `main` 不能快进到 `dev` | 晋升拒绝 |
| 生产健康检查失败 | 自动恢复上一镜像 |
| 重复晋升当前健康版本 | 无操作成功 |

## 性能检查

本次不改变请求处理路径，因此不做接口负载测试。验证重点是两次相同提交构建时
Docker 依赖层命中缓存，以及生产晋升阶段没有 `docker build`。
