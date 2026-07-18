# GitHub 分支与服务器发布手册

## 日常流程

SmartCore 使用两个长期分支：

- `dev`：接收日常修改并在服务器验证。
- `main`：只保存已验证、正在发布或可以发布的版本。

服务器有两个隔离工作区：

- `/opt/smartcore-dev`：`dev` 分支和候选环境。
- `/opt/smartcore`：`main` 分支和生产环境。

## 第一次建立 dev 工作区

先确保 GitHub 已有与 `main` 同起点的 `dev` 分支，然后在服务器运行：

```bash
cd /opt/smartcore
./scripts/setup_server_dev.sh
```

该命令使用 Git worktree，不复制 Git 对象，也不读取或复制生产密钥。

## 构建并验证 dev

修改合入并推送 `dev` 后，在服务器运行：

```bash
cd /opt/smartcore-dev
./scripts/deploy_dev.sh
```

脚本依次完成：

1. 快进拉取 `origin/dev`。
2. 用 Docker 缓存运行 Ruff、pytest、前端类型检查、Vitest 和构建。
3. 构建带提交 SHA 的 app 与 Adapter 镜像。
4. 使用无外网、无生产数据的临时容器检查 app。
5. 在 `127.0.0.1:18000` 启动独立 dev app。
6. 记录候选 SHA 和不可替换的镜像 ID。

可从本机建立 SSH 隧道查看 dev：

```bash
ssh -L 18000:127.0.0.1:18000 server
```

然后访问 `http://127.0.0.1:18000/work/`。

## 晋升到 main 和生产

人工确认 dev 后：

```bash
cd /opt/smartcore
./scripts/promote_prod.sh
```

晋升脚本要求：

- 候选仍然等于 `origin/dev`；
- `origin/main` 可以快进到候选；
- app 和 Adapter 镜像 ID 与验证记录一致；
- 两个镜像的 revision 标签等于候选 SHA。

通过后脚本把同一个 SHA 快进到 `main`，直接切换已经验证的镜像，不运行
`docker build`。生产健康检查失败会自动恢复上一组镜像。

## 回滚

```bash
cd /opt/smartcore
./scripts/deploy_prod.sh --rollback
```

也可指定保留的历史 SHA：

```bash
./scripts/deploy_prod.sh --rollback <SHA>
```

回滚只切换镜像，不回滚 SQLite。每次晋升前都会创建数据库快照。

## GitHub CI 的职责

GitHub Actions 只运行快速结构检查：Shell/Python 语法和 Compose
配置。完整测试在服务器候选流程中运行，借此复用 Docker、pip 和 npm 层缓存。

## 约束

- 不直接向 `main` 开发。
- 不用普通 merge commit 合并 `dev -> main`；生产脚本执行 fast-forward。
- dev 不挂载生产 SQLite volume，也不启动 Cloudflared、调度器或生产 Adapter。
- 候选测试失败时不要手工给镜像重新打标签绕过验证。
- 生产或 dev 工作区不干净时，先确认修改来源，不使用 `git reset --hard`。
