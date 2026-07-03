# SmartCore Product Polish Acceptance

Date: 2026-07-03

This pass treats SmartCore as a daily workbench, not an admin console. The UI
must feel calm, fast, and useful at a desk, on a laptop, and on the Tailscale
phone side screen.

## Product Principles

- Light theme first. Avoid dark dashboard defaults for both `/work` and `/screen`.
- User-facing labels should be human-readable Chinese. Internal names such as
  `lifeEvt` and `ddlEvt` may remain in API/code, but should not dominate primary
  UI copy.
- Creation and review stay separated: `/work` keeps `添加事件` and `事项看板`
  as distinct views.
- Clear requests execute directly. Do not introduce pending-confirmation UX.
- State must feel live. The user should not need to refresh `/work` to see
  Pi-reported `working` / `away` changes.

## `/work` Acceptance

- Header includes a compact live work-state region showing current state,
  source device, and last-seen/freshness text.
- The state region updates whenever `/api/devState` polling returns a new Pi
  state, without a page reload.
- The device view and the global state region are both fed by the same parsed
  devState response, so they cannot drift.
- Input controls look like product controls, not raw browser defaults: consistent
  height, spacing, focus states, radius <= 8px, aligned textareas, and clear
  primary submit actions.
- The event board remains a scan-first board with visible counts, search, and
  inline edit controls.

## `/screen` Acceptance

- Designed for a horizontal phone side screen.
- Light, low-glare visual language with large clock and state.
- Connected/offline state is obvious without making the whole screen alarming.
- Work state transitions (`working` <-> `away`) update through WebSocket messages
  and apply CSS classes immediately.
- Reminder cards are legible from a distance and do not crowd the clock.

## OpenClaw Skill Acceptance

- Skill documentation remains thin and points only at `/agent/*` APIs.
- Agent token is required for protected endpoints.
- OpenClaw-compatible calls can perform a full database write loop: discover,
  create, query, update, delete/cancel, capture idea, and convert idea to event.
- Responses stay immediate and machine-stable: `{ok, stat, data}` with no
  mechanical confirmation step for clear requests.
