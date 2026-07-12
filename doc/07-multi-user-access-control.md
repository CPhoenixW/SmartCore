# SmartCore 多用户与管理员权限模型调整建议

## 1. 当前模型的基础

当前数据库已经具备一部分多租户基础：`evtBase`、`idea`、`device`、`actLog`、`notifyLog`、`msgLog` 均包含 `userId`；设备状态和照片请求通过 `deviceId` 间接归属用户。因此，不需要推翻事件、课程、提醒关系模型，核心工作是把当前代码中的固定 `DEFAULT_USER_ID` 改成由登录会话提供的用户上下文，并在每次查询和写入时执行所有权校验。

本次登录实现只完成单用户工作台认证和 `passwd` 哈希存储，尚未宣称完成多用户数据隔离。

## 2. `appUser` 建议增加的字段

建议最终将用户表扩展为：

```text
appUser
- userId             主键，内部稳定标识
- username           唯一登录名，不使用 displayName 登录
- passwd             密码哈希；当前实现使用 scrypt
- displayName        展示名称
- role               admin | user
- status             active | disabled | locked
- language
- avatarUrl
- lastLoginAt
- passwordChangedAt
- createdAt
- updatedAt
```

`passwd` 必须存密码哈希而不是明文。`username` 应建立唯一索引。`role` 可先使用枚举字段；只有当角色和权限种类明显增加时，再拆成 `role`、`permission`、`userRole` 三张 RBAC 表。

## 3. 设备关系

当前 `device.userId` 表达“一台设备只有一个所有者”，适合个人设备。如果未来设备需要共享给家人、同学或运维人员，应改为：

```text
device
- deviceId
- ownerUserId
- deviceName
- deviceKind
- isActive
- registeredAt

deviceMember
- deviceId
- userId
- memberRole          owner | manager | viewer
- createdAt
PRIMARY KEY (deviceId, userId)
```

普通用户只能读取自己拥有或在 `deviceMember` 中被授权的设备；管理员可以读取全部设备。若确定永远不共享设备，可继续保留 `device.userId`，不必增加中间表。

## 4. 事件与信息关系

`evtBase.userId`、`idea.userId` 已能作为租户边界。子表 `planEvt`、`ddlEvt`、`courseEvt`、`remindEvt` 不必重复增加 `userId`，它们通过 `evtBase` 获得所有者。服务层必须遵守以下规则：

1. 普通用户查询必须附加 `WHERE evtBase.userId = currentUserId`。
2. 按 `evtId` 更新或删除前，必须先验证该事件属于当前用户。
3. DDL 关联计划和课程 occurrence 必须校验父子事件属于同一用户。
4. 日志查询必须按 `userId` 过滤；管理员查询可以显式传入目标用户。
5. 不允许前端提交任意 `userId` 决定数据归属，归属必须由服务端会话注入。

## 5. 外部身份关系

飞书、OpenClaw 和设备令牌不应直接依赖显示名称。建议增加：

```text
externalIdentity
- identityId
- userId
- provider            feishu | openclaw | oauth
- externalUserId
- externalTenantId
- createdAt
UNIQUE(provider, externalTenantId, externalUserId)
```

这样飞书消息才能稳定映射到正确 SmartCore 用户。

## 6. 授权层设计

建议在 FastAPI 中建立统一依赖：

```text
getCurrentPrincipal() -> { userId, role }
requireAdmin()
requireDeviceAccess(deviceId, minimumRole)
requireEventOwner(evtId)
```

普通业务函数不再使用 `DEFAULT_USER_ID`。管理员接口建议单独放在 `/api/admin/*`，避免普通接口通过可选参数意外越权。

管理员典型权限：

- 查看、禁用和重置用户；
- 查看全部设备、状态、照片请求和日志；
- 将设备转移给其他用户；
- 查看审计日志；
- 不应直接读取密码哈希。

普通用户权限：

- 维护自己的资料、事件、灵感和课程；
- 管理自己拥有或被授权的设备；
- 查看自己的日志与提醒；
- 不可指定其他用户的 `userId`。

## 7. 审计与安全

建议补充：

- 登录失败计数和短时锁定；
- `lastLoginAt`、密码修改时间；
- 管理员操作写入不可修改的审计日志；
- 会话撤销表或 `sessionVersion`，用于修改密码后使旧会话失效；
- CSRF 防护，尤其是未来通过公网 Cookie 登录时；
- HTTPS 环境设置 `AUTH_COOKIE_SECURE=true`；
- API、设备和浏览器使用不同凭证，不共用一个长期 Token。

## 8. 推荐迁移顺序

1. 完成当前单用户登录和密码哈希。
2. 增加 `username`、`role`、`status`，创建首个管理员。
3. 将所有 CRUD 和事件服务从 `DEFAULT_USER_ID` 改为显式 `userId` 参数。
4. 给所有浏览器 API 注入登录用户并增加所有权校验。
5. 增加 `/api/admin/users` 与 `/api/admin/devices`。
6. 根据是否需要设备共享，决定是否引入 `deviceMember`。
7. 增加外部身份映射和完整审计。

最关键的不是单纯增加 `role` 字段，而是确保每一条查询、写入、关联创建和后台任务都携带正确的 `userId` 边界。否则即使前端隐藏了管理员入口，仍然会发生横向越权。
