-- SmartCore work schema (SQLite). Source of truth for table DDL.
-- This schema intentionally keeps writes simple and serial: no rowVersion/requestLog layer.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS appUser (
    userId VARCHAR(32) PRIMARY KEY,
    displayName VARCHAR(100) NOT NULL,
    createdAt VARCHAR(64) NOT NULL
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
    CHECK (evtType IN ('plan', 'ddl', 'course')),
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
    UNIQUE (ddlEvtId, planRole),
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
    CHECK (deviceKind IN ('screen', 'browser', 'mobile', 'bot', 'server'))
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
    CHECK (targetKind IN ('evt', 'planEvt', 'ddlEvt', 'courseEvt', 'idea', 'device')),
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
CREATE INDEX IF NOT EXISTS idx_idea_user_created ON idea(userId, createdAt);
CREATE INDEX IF NOT EXISTS idx_device_user_kind ON device(userId, deviceKind);
CREATE INDEX IF NOT EXISTS idx_deviceStateLog_device_seen ON deviceStateLog(deviceId, seenAt);
CREATE INDEX IF NOT EXISTS idx_actLog_user_created ON actLog(userId, createdAt);
CREATE INDEX IF NOT EXISTS idx_actLog_target ON actLog(targetKind, targetId);
CREATE INDEX IF NOT EXISTS idx_notifyLog_user_scheduled ON notifyLog(userId, scheduledAt);
CREATE INDEX IF NOT EXISTS idx_msgLog_user_created ON msgLog(userId, createdAt);
