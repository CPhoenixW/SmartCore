# Event type colors and reminder actions

## Acceptance criteria

- Overview and Update Event use the same visible color mapping: plan blue,
  reminder purple, DDL orange, and course cyan.
- Done and cancelled opacity, selection, and overdue styling still work.
- A `plan_start_10m` Feishu card contains reminder content but no completion or
  snooze actions.
- End-of-plan, DDL, and standalone reminder cards keep their existing actions.

## Boundaries and rollback

- No API, authorization, database, or migration changes.
- The reminder phase is derived from the existing `remindKind`; ownership and
  delivery routing are unchanged.
- Roll back by reverting this change and redeploying the previous image.

## Validation

- Component test for every event type class.
- Scheduler test for start/end phases.
- Card and bound-chat delivery tests for action visibility.
- Ruff, pytest, Vitest, frontend build, and production health smoke check.
