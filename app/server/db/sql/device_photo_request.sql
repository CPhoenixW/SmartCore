PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS devicePhotoRequest (
    requestId VARCHAR(32) PRIMARY KEY,
    deviceId VARCHAR(50) NOT NULL,
    stat VARCHAR(20) NOT NULL DEFAULT 'pending',
    reason TEXT,
    requestedAt VARCHAR(64) NOT NULL,
    expiresAt VARCHAR(64) NOT NULL,
    dispatchedAt VARCHAR(64),
    capturedAt VARCHAR(64),
    completedAt VARCHAR(64),
    imagePath VARCHAR(500),
    mimeType VARCHAR(100),
    imageSize INTEGER,
    recognition JSON,
    errorMessage TEXT,
    FOREIGN KEY (deviceId) REFERENCES device(deviceId) ON DELETE CASCADE,
    CHECK (stat IN ('pending', 'uploaded', 'failed', 'expired', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_devicePhotoRequest_device_stat
ON devicePhotoRequest(deviceId, stat, requestedAt);

CREATE INDEX IF NOT EXISTS idx_devicePhotoRequest_expires
ON devicePhotoRequest(expiresAt);

-- SmartCore uses soft deletion for events. Cancelling a DDL must also cancel
-- every generated or manually linked plan so it cannot remain on dashboards
-- or trigger an orphan reminder.
CREATE TRIGGER IF NOT EXISTS trg_cancel_ddl_linked_plans
AFTER UPDATE OF stat ON evtBase
WHEN NEW.evtType = 'ddl' AND NEW.stat = 'cancelled' AND OLD.stat <> 'cancelled'
BEGIN
    UPDATE evtBase
    SET stat = 'cancelled', updatedAt = NEW.updatedAt
    WHERE evtId IN (
        SELECT planEvtId FROM ddlPlan WHERE ddlEvtId = NEW.evtId
    );
END;
