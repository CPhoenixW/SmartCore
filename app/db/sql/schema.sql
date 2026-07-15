-- SmartCore work schema (SQLite). Source of truth for table DDL.
-- This schema intentionally keeps writes simple and serial: no rowVersion/requestLog layer.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS appUser (
    userId VARCHAR(32) PRIMARY KEY,
    loginName VARCHAR(100) UNIQUE,
    passwd VARCHAR(500),
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    stat VARCHAR(20) NOT NULL DEFAULT 'active',
    sessionVersion INTEGER NOT NULL DEFAULT 1,
    lastLoginAt VARCHAR(64),
    displayName VARCHAR(100) NOT NULL,
    language VARCHAR(10) NOT NULL DEFAULT 'zh',
    avatarUrl VARCHAR(500),
    createdAt VARCHAR(64) NOT NULL,
    updatedAt VARCHAR(64) NOT NULL,
    CHECK (language IN ('zh', 'en'))
);

CREATE TABLE IF NOT EXISTS evtBase (
    evtId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    title VARCHAR(300) NOT NULL,
    desc TEXT,
    evtType VARCHAR(20) NOT NULL,
    prio VARCHAR(10) NOT NULL DEFAULT 'mid',
    stat VARCHAR(20) NOT NULL DEFAULT 'todo',
    createdAt VARCHAR(64) NOT NULL,
    updatedAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
    CHECK (evtType IN ('plan', 'ddl', 'course', 'remind')),
    CHECK (prio IN ('low', 'mid', 'high')),
    CHECK (stat IN ('todo', 'done', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS planEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    stTime VARCHAR(64) NOT NULL,
    durationMin INTEGER NOT NULL,
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE,
    CHECK (durationMin > 0)
);

CREATE TABLE IF NOT EXISTS ddlEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    endTime VARCHAR(64) NOT NULL,
    hardDdl INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ddlPlan (
    ddlEvtId VARCHAR(32) NOT NULL,
    planEvtId VARCHAR(32) NOT NULL,
    planRole VARCHAR(30) NOT NULL,
    sortOrder INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (ddlEvtId, planEvtId),
    FOREIGN KEY (ddlEvtId) REFERENCES ddlEvt(evtId) ON DELETE CASCADE,
    FOREIGN KEY (planEvtId) REFERENCES planEvt(evtId) ON DELETE CASCADE,
    UNIQUE (planEvtId),
    CHECK (planRole IN ('one_day_before', 'one_hour_before', 'manual'))
);

CREATE TABLE IF NOT EXISTS courseEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    courseName VARCHAR(200) NOT NULL,
    teacher VARCHAR(100),
    location VARCHAR(200),
    stTime VARCHAR(8) NOT NULL,
    endTime VARCHAR(8) NOT NULL,
    stDate VARCHAR(16) NOT NULL,
    endDate VARCHAR(16) NOT NULL,
    weekDay INTEGER NOT NULL,
    startWeek INTEGER,
    endWeek INTEGER,
    weekMode VARCHAR(10) NOT NULL DEFAULT 'all',
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE,
    CHECK (weekDay BETWEEN 1 AND 7),
    CHECK (weekMode IN ('all', 'odd', 'even'))
);

CREATE TABLE IF NOT EXISTS coursePlan (
    courseEvtId VARCHAR(32) NOT NULL,
    planEvtId VARCHAR(32) NOT NULL,
    occurrenceDate VARCHAR(16) NOT NULL,
    sequenceNo INTEGER NOT NULL,
    PRIMARY KEY (courseEvtId, planEvtId),
    FOREIGN KEY (courseEvtId) REFERENCES courseEvt(evtId) ON DELETE CASCADE,
    FOREIGN KEY (planEvtId) REFERENCES planEvt(evtId) ON DELETE CASCADE,
    UNIQUE (courseEvtId, occurrenceDate),
    UNIQUE (planEvtId),
    CHECK (sequenceNo > 0)
);

CREATE TABLE IF NOT EXISTS remindEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    planEvtId VARCHAR(32),
    ddlEvtId VARCHAR(32),
    remindKind VARCHAR(30) NOT NULL,
    triggerTime VARCHAR(64) NOT NULL,
    offsetMin INTEGER NOT NULL DEFAULT 0,
    firedAt VARCHAR(64),
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE,
    FOREIGN KEY (planEvtId) REFERENCES planEvt(evtId) ON DELETE CASCADE,
  FOREIGN KEY (ddlEvtId) REFERENCES ddlEvt(evtId) ON DELETE CASCADE,
  UNIQUE (planEvtId, remindKind),
  CHECK (offsetMin >= 0),
  CHECK (planEvtId IS NULL OR ddlEvtId IS NULL)
);

CREATE TABLE IF NOT EXISTS idea (
    ideaId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    srcType VARCHAR(20) NOT NULL DEFAULT 'text',
    mediaPath VARCHAR(500),
    handled INTEGER NOT NULL DEFAULT 0,
    createdAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS device (
    deviceId VARCHAR(50) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    deviceName VARCHAR(100) NOT NULL,
    deviceKind VARCHAR(30) NOT NULL,
    isActive INTEGER NOT NULL DEFAULT 1,
    registeredAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
    CHECK (deviceKind IN ('screen', 'browser', 'mobile', 'bot', 'server', 'pi'))
);

CREATE TABLE IF NOT EXISTS deviceStateLog (
    stateLogId VARCHAR(32) PRIMARY KEY,
    deviceId VARCHAR(50) NOT NULL,
    state VARCHAR(20) NOT NULL,
    confidence REAL,
    seenAt VARCHAR(64) NOT NULL,
    meta JSON,
    FOREIGN KEY (deviceId) REFERENCES device(deviceId) ON DELETE CASCADE,
    UNIQUE (deviceId, seenAt),
    CHECK (state IN ('working', 'away', 'offline', 'unknown'))
);

CREATE TABLE IF NOT EXISTS actLog (
    actId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    actorKind VARCHAR(20) NOT NULL,
    actorId VARCHAR(100),
    action VARCHAR(30) NOT NULL,
    targetKind VARCHAR(30) NOT NULL,
    targetId VARCHAR(32) NOT NULL,
    sourceDeviceId VARCHAR(50),
    result VARCHAR(20) NOT NULL DEFAULT 'ok',
    errorMessage TEXT,
    createdAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
    FOREIGN KEY (sourceDeviceId) REFERENCES device(deviceId) ON DELETE SET NULL,
    CHECK (actorKind IN ('user', 'system', 'device', 'llm')),
    CHECK (action IN ('create', 'update', 'delete', 'complete', 'cancel', 'auto_create', 'link', 'notify')),
    CHECK (targetKind IN ('user', 'evt', 'planEvt', 'ddlEvt', 'courseEvt', 'remindEvt', 'coursePlan', 'idea', 'device')),
    CHECK (result IN ('ok', 'failed'))
);

CREATE TABLE IF NOT EXISTS notifyLog (
    notifyId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    evtId VARCHAR(32),
    channel VARCHAR(20) NOT NULL,
    receiver VARCHAR(100),
    sourceDeviceId VARCHAR(50),
    routeReason VARCHAR(50),
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    scheduledAt VARCHAR(64) NOT NULL,
    sentAt VARCHAR(64),
    stat VARCHAR(20) NOT NULL,
    failReason TEXT,
    dedupKey VARCHAR(200) UNIQUE,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE SET NULL,
    FOREIGN KEY (sourceDeviceId) REFERENCES device(deviceId) ON DELETE SET NULL,
    CHECK (channel IN ('feishu', 'screen', 'browser', 'system')),
    CHECK (stat IN ('pending', 'sent', 'failed', 'skipped', 'fallback'))
);

CREATE TABLE IF NOT EXISTS msgLog (
    msgId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL,
    channel VARCHAR(30) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    externalId VARCHAR(200),
    sourceDeviceId VARCHAR(50),
    rawText TEXT,
    intent VARCHAR(100),
    stat VARCHAR(50),
    createdAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (userId) REFERENCES appUser(userId) ON DELETE CASCADE,
    FOREIGN KEY (sourceDeviceId) REFERENCES device(deviceId) ON DELETE SET NULL,
    UNIQUE (channel, externalId),
    CHECK (channel IN ('web', 'feishu', 'llm', 'system')),
    CHECK (direction IN ('in', 'out'))
);

CREATE INDEX IF NOT EXISTS idx_evtBase_user_stat_time ON evtBase(userId, stat, updatedAt);
CREATE INDEX IF NOT EXISTS idx_evtBase_user_type ON evtBase(userId, evtType);
CREATE INDEX IF NOT EXISTS idx_planEvt_stTime ON planEvt(stTime);
CREATE INDEX IF NOT EXISTS idx_ddlEvt_endTime ON ddlEvt(endTime);
CREATE INDEX IF NOT EXISTS idx_courseEvt_weekDay ON courseEvt(weekDay);
CREATE INDEX IF NOT EXISTS idx_coursePlan_course_date ON coursePlan(courseEvtId, occurrenceDate);
CREATE INDEX IF NOT EXISTS idx_coursePlan_plan ON coursePlan(planEvtId);
CREATE INDEX IF NOT EXISTS idx_remindEvt_trigger ON remindEvt(triggerTime);
CREATE INDEX IF NOT EXISTS idx_remindEvt_plan ON remindEvt(planEvtId);
CREATE INDEX IF NOT EXISTS idx_remindEvt_ddl_trigger ON remindEvt(ddlEvtId, triggerTime);
CREATE INDEX IF NOT EXISTS idx_ddlPlan_ddl_order ON ddlPlan(ddlEvtId, sortOrder);
CREATE INDEX IF NOT EXISTS idx_idea_user_created ON idea(userId, createdAt);
CREATE INDEX IF NOT EXISTS idx_device_user_kind ON device(userId, deviceKind);
CREATE INDEX IF NOT EXISTS idx_deviceStateLog_device_seen ON deviceStateLog(deviceId, seenAt);
CREATE INDEX IF NOT EXISTS idx_actLog_user_created ON actLog(userId, createdAt);
CREATE INDEX IF NOT EXISTS idx_actLog_target ON actLog(targetKind, targetId);
CREATE INDEX IF NOT EXISTS idx_notifyLog_user_scheduled ON notifyLog(userId, scheduledAt);
CREATE INDEX IF NOT EXISTS idx_msgLog_user_created ON msgLog(userId, createdAt);
-- User and device unified dispatch. This file is the auditable DDL source for
-- the new tables; the SQLite migration runner applies it only once to an
-- existing database.
CREATE TABLE IF NOT EXISTS userSession (
    sessionId VARCHAR(32) PRIMARY KEY,
    actorUserId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    activeUserId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    expiresAt VARCHAR(64) NOT NULL,
    revokedAt VARCHAR(64),
    createdAt VARCHAR(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS lifeDevice (
    deviceId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    deviceName VARCHAR(100) NOT NULL,
    deviceKind VARCHAR(30) NOT NULL,
    stat VARCHAR(20) NOT NULL DEFAULT 'active',
    lastSeenAt VARCHAR(64),
    createdAt VARCHAR(64) NOT NULL,
    updatedAt VARCHAR(64) NOT NULL,
    CHECK (stat IN ('active', 'disabled'))
);
CREATE TABLE IF NOT EXISTS deviceKey (
    keyId VARCHAR(32) PRIMARY KEY,
    deviceId VARCHAR(32) NOT NULL REFERENCES lifeDevice(deviceId) ON DELETE CASCADE,
    tokenHash VARCHAR(64) NOT NULL UNIQUE,
    createdAt VARCHAR(64) NOT NULL,
    lastUsedAt VARCHAR(64),
    revokedAt VARCHAR(64)
);
CREATE TABLE IF NOT EXISTS devicePair (
    pairId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    deviceId VARCHAR(32) REFERENCES lifeDevice(deviceId) ON DELETE SET NULL,
    botId VARCHAR(32) REFERENCES feishuBot(botId) ON DELETE SET NULL,
    deviceName VARCHAR(100) NOT NULL,
    deviceKind VARCHAR(30) NOT NULL,
    claimCode VARCHAR(100) NOT NULL UNIQUE,
    stat VARCHAR(20) NOT NULL DEFAULT 'created',
    expiresAt VARCHAR(64) NOT NULL,
    claimedAt VARCHAR(64),
    confirmedAt VARCHAR(64),
    activatedAt VARCHAR(64),
    createdAt VARCHAR(64) NOT NULL,
    CHECK (stat IN ('created', 'claimed', 'userConfirmed', 'paired', 'expired', 'cancelled'))
);
CREATE TABLE IF NOT EXISTS feishuBot (
    botId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    deviceId VARCHAR(32) REFERENCES lifeDevice(deviceId) ON DELETE SET NULL,
    botName VARCHAR(100) NOT NULL,
    appId VARCHAR(200) NOT NULL,
    appSecretCipher TEXT NOT NULL,
    verificationTokenCipher TEXT NOT NULL,
    encryptKeyCipher TEXT NOT NULL,
    defaultChatCipher TEXT,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    isDefault BOOLEAN NOT NULL DEFAULT 0,
    lastTestAt VARCHAR(64),
    lastTestStat VARCHAR(20),
    lastTestMessage VARCHAR(300),
    createdAt VARCHAR(64) NOT NULL,
    updatedAt VARCHAR(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS lifeIdentity (
    identityId VARCHAR(32) PRIMARY KEY,
    userId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    deviceId VARCHAR(32) REFERENCES lifeDevice(deviceId) ON DELETE SET NULL,
    provider VARCHAR(30) NOT NULL,
    externalId VARCHAR(200) NOT NULL,
    createdAt VARCHAR(64) NOT NULL,
    UNIQUE (provider, externalId)
);
CREATE TABLE IF NOT EXISTS deviceDispatch (
    dispatchId VARCHAR(32) PRIMARY KEY,
    deviceId VARCHAR(32) NOT NULL REFERENCES lifeDevice(deviceId) ON DELETE CASCADE,
    userId VARCHAR(32) NOT NULL REFERENCES appUser(userId) ON DELETE CASCADE,
    kind VARCHAR(50) NOT NULL,
    payload JSON NOT NULL,
    stat VARCHAR(20) NOT NULL DEFAULT 'pending',
    createdAt VARCHAR(64) NOT NULL,
    deliveredAt VARCHAR(64),
    acknowledgedAt VARCHAR(64),
    CHECK (stat IN ('pending', 'delivered', 'acknowledged', 'failed'))
);
CREATE TABLE IF NOT EXISTS deviceReceipt (
    receiptId VARCHAR(32) PRIMARY KEY,
    dispatchId VARCHAR(32) NOT NULL UNIQUE REFERENCES deviceDispatch(dispatchId) ON DELETE CASCADE,
    deviceId VARCHAR(32) NOT NULL REFERENCES lifeDevice(deviceId) ON DELETE CASCADE,
    result VARCHAR(30) NOT NULL,
    detail JSON,
    createdAt VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lifeDevice_user ON lifeDevice(userId, stat);
CREATE INDEX IF NOT EXISTS idx_deviceDispatch_pending ON deviceDispatch(deviceId, stat, createdAt);
CREATE INDEX IF NOT EXISTS idx_feishuBot_user_enabled ON feishuBot(userId, enabled);
