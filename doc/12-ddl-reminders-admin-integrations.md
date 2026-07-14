# DDL reminders and administrator integrations

## Acceptance criteria

1. A deadline can own any number of linked plans and any number of linked one-shot reminders.
2. `plans` represent timed work blocks; `ddlReminders` represent an exact notification and do not create plan start/end reminders.
3. Natural-language, web, OpenClaw, and Feishu event paths accept the same DDL contract.
4. The text "依依宝宝 2026 年 8 月 28 号过生日，提前一天需要提醒我买蛋糕，提前5天需要提醒我买礼物" produces a high-priority DDL with two linked reminders on 2026-08-27 and 2026-08-23 in Asia/Shanghai, using 09:00 only when no time was supplied.
5. Administrators can initiate and confirm a pairing for the server-configured SmartCore Feishu bot from Settings. Credentials remain server-side and are never returned to the browser.
6. A future multi-bot configuration stores bot credentials separately from user/device pairing. This change does not expose app credentials in the workbench.
7. Settings has independently scrollable left and right columns. Profile settings, account switching, and bot management are separated cards in the left column; avatar preview is in the right column.
8. Administrator account switching succeeds, records an audit event, and cannot be used by a normal user.

## Data and migration design

- Add nullable `ddlEvtId` to `remindEvt`. A reminder may belong to a plan, a deadline, or neither; it may not belong to both.
- Add an index on `remindEvt(ddlEvtId, triggerTime)`. Existing reminder rows remain unchanged.
- Rebuild legacy SQLite `actLog` only when its CHECK constraint lacks `user`, preserving every row.
- Keep the existing server-side Feishu application configuration as the sole active bot connection. Add multi-bot configuration only with an encrypted credential store and dedicated callback routing.

## API contract

DDL create/update accepts:

```json
{
  "plans": [{"planRole":"manual","title":"买礼物","stTime":"2026-08-23T19:00:00+08:00","durationMin":30}],
  "ddlReminders": [{"remindEvtId":null,"title":"买蛋糕","triggerTime":"2026-08-27T09:00:00+08:00","prio":"high","enabled":true}]
}
```

The administrator pairing view creates a normal `feishuBot` device-pair request against the existing server-side bot configuration. Credentials are not part of the browser API.

## Validation matrix

- DDL create/update/delete preserves and synchronizes linked plans and reminders.
- Parser produces explicit linked reminders for relative reminder phrases and no default plans when an explicit relation is present.
- Agent tool schemas and relation-write routes create/update the same relations.
- Feishu pairing binds an identity to the server-configured bot through the same device-pair contract.
- Admin/normal-user authorization, migration preservation, frontend build, full tests, and deployment health checks pass.
