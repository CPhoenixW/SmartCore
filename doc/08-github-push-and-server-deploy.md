# Git 与服务器发布

长期分支为 `dev` 和 `main`：`dev` 构建候选，`main` 对应已验证生产版本。服务器
目录分别为 `/opt/smartcore-dev` 和 `/opt/smartcore`。

```bash
git push origin dev
ssh server 'cd /opt/smartcore-dev && ./scripts/deploy_dev.sh'
ssh server 'cd /opt/smartcore && ./scripts/promote_prod.sh'
```

提升脚本只使用已验证镜像，快进 `main`，备份数据库并检查健康；失败自动恢复上一
镜像。回滚使用：

```bash
ssh server 'cd /opt/smartcore && ./scripts/deploy_prod.sh --rollback'
```

不得直接修改生产目录、绕过候选校验、删除生产卷或用强制 Git 操作修复工作区。
完整步骤见 [deploy.md](../deploy.md)。
