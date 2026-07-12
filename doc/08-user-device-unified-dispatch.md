# User, Device, and Unified Dispatch Acceptance Specification

## Scope

This change replaces SmartCore's single-user, global-device-token behavior with an owned-device model. It covers browser users, Raspberry Pi, screen clients, desktop background agents, and Feishu logical bot endpoints. It does not deploy to production and it does not modify secrets or existing deployment settings.

The existing `appUser` table remains the account table. New names use compact camelCase with no underscores. Existing event table names remain unchanged when renaming has no behavioral value.

## Product Rules

1. Every device belongs to exactly one user. Devices are not shared and cannot be transferred. Reassignment means revoking the old device and pairing a new one.
2. Every root business record and every device communication record has a server-derived `userId`. Event subtype tables inherit ownership through `evtBase` and must not accept an independent client-supplied `userId`.
3. A browser session has an authenticated `actorUserId` and an `activeUserId`. For ordinary users they are identical. An administrator may switch only the active context, while audit records always preserve the actor.
4. A physical Feishu application is a system adapter, not a shared user device. Each user binding creates one user-owned logical `feishuBot` device linked to a Feishu external identity.
5. Devices never choose their owner by request body. Ownership comes only from a completed pairing or a verified external identity binding.

## Database Model

Extend `appUser`:

```text
appUser(
  userId, loginName, passwd, displayName, role, stat,
  language, avatarUrl, sessionVersion, lastLoginAt,
  createdAt, updatedAt
)
```

- `loginName` is unique and is the login identifier.
- `role` is `admin` or `user`; `stat` is `active` or `disabled`.
- Existing `default` user becomes the initial administrator during migration.

Add these tables:

```text
userSession(
  sessionId, actorUserId, activeUserId,
  createdAt, expiresAt, lastSeenAt, revokedAt
)

lifeDevice(
  deviceId, userId, deviceName, deviceKind, deviceState,
  deviceMeta, tailnetAddr, registeredAt, lastSeenAt, revokedAt
)

deviceKey(
  keyId, deviceId, tokenHash, keyScope,
  issuedAt, expiresAt, lastUsedAt, revokedAt
)

devicePair(
  pairId, userId, deviceId, pairCodeHash,
  deviceKind, deviceMeta, stat,
  requestedAt, claimedAt, userConfirmedAt,
  deviceConfirmedAt, expiresAt, cancelledAt
)

lifeIdentity(
  identityId, userId, deviceId,
  provider, identityKind, externalId, createdAt, revokedAt
)

deviceDispatch(
  dispatchId, userId, deviceId, sourceDeviceId,
  msgKind, payload, stat, dedupKey,
  notBeforeAt, expiresAt, deliveredAt, ackAt, createdAt
)

deviceReceipt(
  receiptId, dispatchId, deviceId, stat, detail, createdAt
)
```

Required constraints and indexes:

- `lifeDevice.userId` is non-null and references `appUser`; no membership or sharing table is allowed.
- A valid device key is stored only as `tokenHash`; plaintext tokens are only returned once after pairing.
- `devicePair.pairCodeHash` is never returned after creation. Pairing expires after ten minutes.
- `lifeIdentity` is unique for `(provider, identityKind, externalId)` and its `userId` must equal its linked device owner's `userId`.
- `deviceDispatch.dedupKey` is unique per device. `deviceReceipt` is append-only.
- Add direct immutable `userId` columns to `deviceStateLog` and `devicePhotoRequest`; they are populated by the server from the device owner.
- `actLog` records both `actorUserId` and `activeUserId` for all administrator context switches and all writes made while impersonating a user.
- `notifyLog`, `msgLog`, `deviceDispatch`, and device state/photo records must all be queryable by `userId` without a cross-user join.

The source-of-truth DDL belongs in `app/db/sql/schema.sql`. This change must add a separate, idempotent SQL migration under `app/db/sql/migrations/`; Python migration code may run that SQL but must not embed a second schema definition. The migration preserves existing user events and maps existing devices to the current default user only as historical rows. It revokes all old global device credentials, so Pi, screen, and Feishu must pair again before communicating.

## Authentication and Authorization

Replace the current stateless `userId` cookie payload with a signed session id that resolves a non-revoked `userSession`. A principal dependency returns:

```text
{ actorUserId, activeUserId, role }
```

- Browser CRUD reads and writes always scope to `activeUserId`.
- Non-admin users cannot set or change `activeUserId`.
- Admin-only APIs live under `/api/admin/*` and require `role=admin`.
- Disabled users cannot log in and existing sessions are rejected.
- Logout revokes the current `userSession`, not merely the browser cookie.
- Password changes increment `sessionVersion` and revoke older sessions.
- All normal browser APIs must require an authenticated principal. Health and Feishu signature validation remain public only where required.

No API may use a request body's `userId` or a query parameter to decide data ownership. Agent and Feishu calls resolve ownership from their verified credential or identity binding and pass the resolved context internally.

## Pairing and Device Protocol

The only way to create an active device is this two-sided sequence:

1. A logged-in user starts a pairing request in the device page. The server creates `devicePair(stat=created)` and displays a short code/QR.
2. The client claims the code with device kind, name, capability metadata, and a generated device fingerprint. The server changes it to `claimed`.
3. The browser shows that claimed device and the user explicitly confirms it. The server changes it to `userConfirmed`.
4. The device receives that result by poll or WebSocket and requires a local confirmation. Only then does the server mint a one-time device token and change the pairing to `paired`.
5. The device stores its token locally and acknowledges its first connection.

Required device API surface:

```text
POST /api/device/pair/start       authenticated user
POST /api/device/pair/claim       unpaired client + pairing code
POST /api/device/pair/confirm     authenticated user
POST /api/device/pair/activate    claimed client + local confirmation
GET  /api/device/pair/{pairId}    owner or claimed client

POST /api/device/connect          device token
GET  /api/device/dispatch         device token, long-poll fallback
POST /api/device/receipt          device token
WS   /ws/device                   device token in initial authenticated frame
```

Exact response payloads may follow existing API conventions, but every delivered command uses this normalized envelope:

```json
{
  "dispatchId": "...",
  "userId": "server-derived owner id",
  "deviceId": "...",
  "msgKind": "reminder|stateRequest|photoRequest|system",
  "payload": {},
  "dedupKey": "...",
  "expiresAt": "..."
}
```

The device must acknowledge with `dispatchId` and an outcome. WebSocket, long-poll, Pi heartbeat and Feishu outbound delivery all use `deviceDispatch` and `deviceReceipt`; transport selection is an implementation detail.

Remove the global `X-SmartCore-Device-Token` contract and remove automatic creation of unknown devices. An unpaired or revoked device must receive 401 or 403 and must never write state, photos, events, messages, or dispatch receipts.

## Feishu Binding

On a first Feishu private message, the service may reply with a pairing card. After the user supplies the pairing code, the server creates a logical `lifeDevice(deviceKind=feishuBot)` owned by that user and a `lifeIdentity` for the Feishu open id/private chat. Incoming text and card callbacks resolve that identity before forwarding to OpenClaw. The forwarded normalized event includes the resolved SmartCore user context and source device id. Unknown identities must not fall back to `default`.

## Frontend Requirements

Settings:

- Add a security section containing logout.
- Show a user switch control only for administrators. It lists active users, supports returning to the administrator's own account, and changes only the active context.
- When an administrator manages another account, show a persistent but subtle "currently managing" indicator. Every non-settings page otherwise behaves as it does for that normal user.

Devices:

- Replace the hard-coded `pi` view with the active user's device list.
- Add an "add device" pairing flow with type choice, code/QR, claim state, browser confirmation, device confirmation, expiry, retry, and cancel states.
- Device details show online state, last seen, capability metadata, recent dispatches, receipts, and revoke action.
- A user can never inspect another user's devices, photos, state history, or dispatches. Admin context switching is the only management route.

## Required Tests and Validation

Cursor may add `tests/test_user_device_dispatch.py` and only implementation tests strictly required for this change. Do not modify existing tests, fixtures, or acceptance documents. The new tests must prove:

1. A standard user cannot read or mutate another user's events, device state, photos, messages, or dispatches.
2. An administrator can switch active context, while audit records retain the administrator as actor and the selected user as active user.
3. Pairing requires both browser and device confirmation; expiry, cancel, and replayed code paths are rejected.
4. A device token is device-specific, hashed at rest, revocable, and cannot operate another user's device.
5. Unknown device ids and the retired global device token cannot auto-register or submit a heartbeat.
6. Dispatch is deduplicated per device and a receipt updates only its own dispatch.
7. A Feishu external identity maps to exactly one user-owned logical bot; unknown Feishu identities cannot create or modify default-user data.
8. Schema and migration tests verify all required foreign keys, uniqueness, direct `userId` columns, and idempotent migration behavior.

Required commands in the server worktree:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check app tests
cd frontend && npm run build
```

The PR must contain no `.env`, keys, SQLite files, uploads, backups, generated frontend artifacts, or production configuration changes. It must not deploy.
