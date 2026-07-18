# Login session user ID fix

## Problem

The login endpoint accepts either an internal user ID or a login name. After
authenticating by login name, it stored the submitted login name in the signed
session cookie. Business APIs interpret the session value as the internal
`appUser.userId`, so profile loading failed and the frontend displayed its
`SmartCore` fallback identity.

## Acceptance criteria

- A normal user can sign in with `loginName`.
- The signed session always contains the matched internal `userId`.
- `/api/auth/me` and `/api/user/me` return the same normal user after login.
- Business records created after login remain scoped to that internal user ID.
- Signing in with the internal user ID remains supported.
- Invalid credentials remain rejected without setting an authenticated session.

## Design and security

Authentication lookup continues to accept either `userId` or `loginName`.
After password verification, the login route uses the matched database row's
`userId` as the session subject. Authorization and data ownership therefore use
one canonical identifier.

No API response contract or UI state changes. The frontend fallback remains
available for genuine network failures, but is no longer triggered by this
identity mismatch.

## Migration and rollback

No schema or data migration is required. Existing malformed sessions are fixed
by signing out and signing in again after deployment. Rollback is a code revert;
no persisted data needs restoration.

## Test matrix

- Normal user: register, sign out, sign in by login name, load both profile
  endpoints, and create an event owned by the internal user ID.
- Internal ID compatibility: sign in with the internal user ID and load profile.
- Invalid credentials: existing authentication rejection behavior.
- Full backend tests, Ruff, Vitest, frontend build, candidate health, and
  production `/healthz`.
