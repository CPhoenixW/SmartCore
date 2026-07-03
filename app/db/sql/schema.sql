-- SmartCore new-arch schema (SQLite). Source of truth for table DDL.

CREATE TABLE IF NOT EXISTS evtBase (
    evtId VARCHAR(32) PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    desc TEXT,
    evtType VARCHAR(20) NOT NULL,
    prio VARCHAR(10) NOT NULL DEFAULT 'mid',
    stat VARCHAR(20) NOT NULL DEFAULT 'todo',
    createdAt VARCHAR(64) NOT NULL,
    updatedAt VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS lifeEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    dueAt VARCHAR(64),
    doneAt VARCHAR(64),
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ddlEvt (
    evtId VARCHAR(32) PRIMARY KEY,
    ddlAt VARCHAR(64),
    hardDdl INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS courseTpl (
    tplId VARCHAR(32) PRIMARY KEY,
    courseName VARCHAR(200) NOT NULL,
    teacher VARCHAR(100),
    room VARCHAR(200),
    weekday INTEGER NOT NULL,
    startTime VARCHAR(8),
    endTime VARCHAR(8),
    startWeek INTEGER,
    endWeek INTEGER,
    weekMode VARCHAR(10) NOT NULL DEFAULT 'all',
    semester VARCHAR(50)
);

CREATE TABLE IF NOT EXISTS courseInst (
    evtId VARCHAR(32) PRIMARY KEY,
    tplId VARCHAR(32) NOT NULL,
    classDate VARCHAR(16),
    attendStat VARCHAR(20) NOT NULL DEFAULT 'unknown',
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE,
    FOREIGN KEY (tplId) REFERENCES courseTpl(tplId) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS idea (
    ideaId VARCHAR(32) PRIMARY KEY,
    content TEXT NOT NULL,
    srcType VARCHAR(20) NOT NULL DEFAULT 'text',
    mediaPath VARCHAR(500),
    handled INTEGER NOT NULL DEFAULT 0,
    createdAt VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS ideaToEvt (
    ideaId VARCHAR(32) PRIMARY KEY,
    evtId VARCHAR(32) NOT NULL,
    convertedAt VARCHAR(64) NOT NULL,
    FOREIGN KEY (ideaId) REFERENCES idea(ideaId) ON DELETE CASCADE,
    FOREIGN KEY (evtId) REFERENCES evtBase(evtId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS devState (
    stateId VARCHAR(32) PRIMARY KEY,
    devId VARCHAR(50) NOT NULL,
    state VARCHAR(20) NOT NULL,
    confidence REAL,
    seenAt VARCHAR(64) NOT NULL,
    meta JSON
);

CREATE TABLE IF NOT EXISTS notifyLog (
    notifyId VARCHAR(32) PRIMARY KEY,
    dedupKey VARCHAR(200) UNIQUE,
    targetKind VARCHAR(20) NOT NULL,
    targetId VARCHAR(100),
    title VARCHAR(300) NOT NULL,
    content TEXT NOT NULL,
    scheduledAt VARCHAR(64) NOT NULL,
    sentAt VARCHAR(64),
    stat VARCHAR(20) NOT NULL,
    failReason TEXT
);

CREATE TABLE IF NOT EXISTS msgLog (
    msgId VARCHAR(32) PRIMARY KEY,
    src VARCHAR(50) NOT NULL,
    externalId VARCHAR(200),
    rawText TEXT,
    intent VARCHAR(100),
    stat VARCHAR(50),
    createdAt VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS actLog (
    actId VARCHAR(32) PRIMARY KEY,
    src VARCHAR(50) NOT NULL,
    actor VARCHAR(100),
    actType VARCHAR(20) NOT NULL,
    targetKind VARCHAR(50),
    targetId VARCHAR(32),
    beforeData JSON,
    afterData JSON,
    undoToken VARCHAR(64) UNIQUE,
    createdAt VARCHAR(64) NOT NULL
);
