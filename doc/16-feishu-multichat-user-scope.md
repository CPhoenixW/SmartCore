# Feishu Multichat User Scope

## Acceptance

- One SmartCore user owns at most one Feishu bot. The same Feishu identity may bind that bot from more than one chat.
- A Feishu identity cannot claim a pairing code for a different SmartCore user.
- Inbound Feishu messages are accepted only from an active `(bot, identity, chat)` binding.
- Every OpenClaw request carries a ten-minute signed scope containing `userId`, `botId`, and `chatId`. Database reads, writes, and feedback use that scope rather than caller-supplied routing fields.
- Proactive reminders use only the user bot's primary active binding. A managed bot without such a binding never falls back to a global environment chat.
- Screen reminders are broadcast only to sockets owned by the event user.

## Data Migration

`feishuBind` stores `(userId, botId, identityId, chatId, chatType, stat, isPrimary)` and is unique per bot/identity/chat. `feishuChatPair` stores the pending claim and confirmation state. Existing legacy `defaultChatCipher` values are migrated once into a primary binding where a matching Feishu identity exists. `uq_feishuBot_user` prevents new duplicate bot ownership without deleting records.

## API Contract

- `POST /api/admin/feishuBots/{botId}/pair/start` creates a short-lived chat pairing code.
- The target Feishu chat sends `绑定 <code>`; `POST /api/admin/feishuBots/{botId}/pair/{pairId}/confirm` activates it.
- OpenClaw calls `/agent/*` with `X-SmartCore-Agent-Token` and `X-SmartCore-Agent-Scope`. The scope is issued only after an active inbound binding is found.

## Security And Rollback

The scope is HMAC signed with the existing server auth secret and expires after ten minutes. Feedback ignores caller-provided recipient fields and uses the scoped bot/chat. Roll back application code by redeploying the preceding revision; the additive tables and indexes are safe to retain, and legacy default-chat data remains untouched.

## Verification

Focused tests cover two chats for one identity, binding ownership, scoped feedback recipient pinning, unscoped rejection, reminder routing, and event ownership. Full backend tests, frontend build, container build, health checks, and a production pairing smoke check are required before release.
