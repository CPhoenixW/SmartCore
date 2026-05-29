# 数据备份与恢复

本文档描述 SmartCore v1 的 SQLite 快照备份、同步到树莓派和手动恢复方案。

## 为什么需要备份

SmartCore 的代码和配置可以用 Git 恢复，但个人数据不能只靠 Git。

个人数据包括：

- 课表。
- 作业和 DDL。
- 生活事项。
- 提醒队列。
- 飞书消息日志。
- 用户偏好。

这些数据保存在 SQLite 数据库中。数据库不应该直接提交到 Git，而应该通过快照备份。

## 备份目标

v1 备份目标：

- 服务器每天生成一次 SQLite 一致性快照。
- 快照压缩保存。
- 服务器本地保留最近 30 天。
- 快照通过 `rsync over SSH` 同步到树莓派。
- 树莓派保留最近 90 天。
- 恢复时使用手动脚本，避免误操作。

## 推荐目录

服务器：

```text
/opt/smartcore/data/smartcore.sqlite
/opt/smartcore/backups
```

树莓派：

```text
/home/pi/smartcore-backups
```

如果用户名或路径不同，通过本地配置文件覆盖。

## 快照命名

推荐命名格式：

```text
smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz
```

示例：

```text
smartcore-2026-05-29-030000.sqlite.gz
```

## SQLite 一致性快照

不要在数据库运行时直接复制 SQLite 文件。推荐使用 SQLite 的备份能力生成一致性快照。

实现思路：

```text
sqlite3 /opt/smartcore/data/smartcore.sqlite ".backup '/tmp/smartcore-backup.sqlite'"
gzip /tmp/smartcore-backup.sqlite
mv /tmp/smartcore-backup.sqlite.gz /opt/smartcore/backups/smartcore-YYYY-MM-DD-HHMMSS.sqlite.gz
```

后续可以封装为 Python 脚本或 shell 脚本。

## 同步到树莓派

使用 `rsync over SSH`：

```text
rsync -av --ignore-existing /opt/smartcore/backups/ pi@raspberrypi:/home/pi/smartcore-backups/
```

推荐通过配置文件提供：

```text
PI_USER=pi
PI_HOST=raspberrypi
PI_BACKUP_DIR=/home/pi/smartcore-backups
```

这里的 `PI_HOST` 可以是 Tailscale 主机名，也可以是 Tailnet 内 IP。优先使用主机名，便于设备更换。

## 备份保留策略

服务器本地：

```text
保留最近 30 天
```

树莓派：

```text
保留最近 90 天
```

清理逻辑：

```text
服务器删除 30 天以前的 smartcore-*.sqlite.gz
树莓派删除 90 天以前的 smartcore-*.sqlite.gz
```

## 自动执行时间

推荐每天凌晨执行：

```text
03:00 生成本地快照
03:05 同步到树莓派
03:10 清理过期备份
```

调度方式可选：

- 服务器宿主机 cron。
- app 容器内调度器。
- 独立 backup 容器。

v1 推荐先用宿主机 cron 或 app 内部调度，减少服务数量。

## 手动恢复流程

恢复时必须先停止应用，避免数据库被同时写入。

流程：

```text
停止 FastAPI app
选择要恢复的备份文件
解压备份
备份当前损坏或错误的数据库
用快照替换当前数据库
启动 FastAPI app
检查今日计划、课表和提醒状态
```

示例：

```text
docker compose stop app
cp /opt/smartcore/data/smartcore.sqlite /opt/smartcore/data/smartcore.sqlite.before-restore
gunzip -c /opt/smartcore/backups/smartcore-2026-05-29-030000.sqlite.gz > /opt/smartcore/data/smartcore.sqlite
docker compose start app
```

## 恢复注意事项

- 恢复会把数据库回滚到某个时间点。
- 回滚后，恢复时间点之后添加的作业、事项和提醒状态会丢失。
- 恢复前要保存当前数据库副本。
- 恢复后要检查是否有重复提醒或已过期提醒。
- 不建议提供 Web 面板一键恢复，避免误点导致数据回滚。

