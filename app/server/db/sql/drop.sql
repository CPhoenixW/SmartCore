-- Drop all SmartCore work tables (reverse dependency order).

DROP TABLE IF EXISTS msgLog;
DROP TABLE IF EXISTS notifyLog;
DROP TABLE IF EXISTS actLog;
DROP TABLE IF EXISTS devicePhotoRequest;
DROP TABLE IF EXISTS deviceStateLog;
DROP TABLE IF EXISTS device;
DROP TABLE IF EXISTS idea;
DROP TABLE IF EXISTS ddlPlan;
DROP TABLE IF EXISTS courseEvt;
DROP TABLE IF EXISTS ddlEvt;
DROP TABLE IF EXISTS planEvt;
DROP TABLE IF EXISTS evtBase;
DROP TABLE IF EXISTS appUser;

-- Legacy tables from the previous work schema.
DROP TABLE IF EXISTS devState;
DROP TABLE IF EXISTS ideaToEvt;
DROP TABLE IF EXISTS courseInst;
DROP TABLE IF EXISTS courseTpl;
DROP TABLE IF EXISTS lifeEvt;
