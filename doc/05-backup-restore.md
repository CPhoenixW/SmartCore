# 备份与恢复

Server 使用 SQLite 一致性快照，文件名为
`smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz`。生产发布前自动备份；定时任务可将快照经
SSH/rsync 同步到 Pi。

默认保留策略：Server 30 天，Pi 90 天。配置项为 `BACKUP_DIR`、`PI_USER`、
`PI_HOST`、`PI_BACKUP_DIR`、`LOCAL_BACKUP_RETENTION_DAYS` 和
`PI_BACKUP_RETENTION_DAYS`。

手动备份：

```bash
./scripts/backup_now.sh
```

恢复会覆盖当前数据，必须明确指定快照：

```bash
cd /opt/smartcore
docker compose -f deploy/docker-compose.yml stop app
./scripts/restore_backup.sh /path/to/smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz
docker compose -f deploy/docker-compose.yml start app
```

恢复脚本先保存当前数据库副本。完成后必须检查容器健康、关键数据、待提醒事项和
重复投递情况。不得通过 Web 或公网接口提供恢复操作。
