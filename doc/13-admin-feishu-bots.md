# Administrator users and Feishu bots

## Acceptance criteria

1. The administrator can switch to every active user without a 500 response; the action is audited.
2. `loginName` is unique in SQLite. The known generated shadow account (`userId=user001`, no password and no owned rows) is disabled and its duplicate login name is cleared; the registered `test` account is preserved.
3. A Feishu identity binding is shown as bound rather than as a device heartbeat. Its last inbound/outbound activity is visible when available.
4. Administrators can create, edit, enable/disable, test, pair, and delete Feishu bot configurations. Plaintext credentials are accepted only on write and are never returned by any endpoint.
5. Existing environment-backed Feishu configuration is migrated once into a managed default bot without exposing or changing the environment values.
6. A bot test first obtains a tenant token and, when a chat ID is configured, sends a test text. A failed test changes no credentials or bindings.

## Data and security

- `feishuBot` stores owner user, display name, encrypted application credentials, optional default chat, enabled/default flags, pairing device, and last test result.
- Encryption uses a Fernet key derived from the server's existing private authentication secret. Credentials are only decrypted in server memory for callback verification, sending, or testing.
- Exactly one enabled default bot may exist for a user. Removing a bot revokes its paired device credentials and deletes its Feishu identity mapping.
- Existing `FEISHU_*` values remain a fallback until the one-time seed creates `environment-default`.

## API

- `GET/POST /api/admin/feishuBots`
- `PATCH/DELETE /api/admin/feishuBots/{botId}`
- `POST /api/admin/feishuBots/{botId}/toggle`
- `POST /api/admin/feishuBots/{botId}/test`
- `POST /api/admin/feishuBots/{botId}/pair`, followed by the existing confirm endpoint.

## Validation and rollback

- Unit-test legacy `actLog` and duplicate-login migrations, authorization, encryption round-trip, and bot test failure behavior.
- Verify the full frontend build and administrator UI tests.
- Production smoke tests use health/OpenAPI and database metadata only; no credentials are printed.
- Rollback is a code/image rollback. The new tables are additive; disabled shadow accounts can be restored manually by setting `stat=active` and a unique login name.
