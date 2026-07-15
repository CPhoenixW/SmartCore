# Feishu Processing Acknowledgement

## Goal

Give a Feishu user visible feedback immediately after SmartCore accepts a normal text message and before the OpenClaw turn completes.

## Acceptance criteria

- A new, non-empty `im.message.receive_v1` text event sends `已收到，正在处理…` to the event chat before forwarding to OpenClaw.
- The acknowledgement uses the exact managed bot that authenticated the incoming request.
- Pairing commands retain their existing reply and never receive the processing acknowledgement.
- Reminder card actions and duplicate message IDs do not send the acknowledgement.
- A Feishu acknowledgement failure is logged but does not prevent forwarding, message logging, or the later OpenClaw reply.

## Design

The acknowledgement is a normal Feishu text message sent from `FeishuEventHandler._forwardTextMessage`. It is intentionally emitted after idempotency validation and before `_postOpenclaw`, so retries cannot create duplicate acknowledgements and the user is not told that work is running when the event is discarded.

`_forwardTextMessage` receives the matched `BotRuntime`; this keeps multi-bot tenants isolated and avoids selecting a default bot after the webhook has already been authenticated. No schema migration or API contract change is required.

## Security and rollback

No credentials, user records, or delivery routing are changed. The same runtime used to validate the webhook is used to reply. Rollback is a revert of this commit and a normal app redeploy.

## Test matrix

- Successful acknowledgement precedes OpenClaw forwarding.
- Acknowledgement delivery failure still forwards and logs the event.
- Duplicate and pairing messages do not receive acknowledgement.
