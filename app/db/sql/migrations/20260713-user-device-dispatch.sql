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
