# Work Board Interaction Acceptance

Date: 2026-07-04

This pass refines the `/work` event board from an inline-editing surface into a
scan-first workbench.

## Product Direction

- The board is for review, triage, and opening detail. It should not behave like
  a spreadsheet.
- Event cards should be readable summaries: title, type, priority, status,
  relevant time, and short description.
- Editing belongs in a focused detail drawer. The user clicks a card to inspect
  and modify it.
- Accidental changes should be harder than reading. No inline inputs, selects,
  or textareas should appear inside board cards.
- The interaction must work with mouse and keyboard.

## Board Acceptance

- The `事项看板` view keeps the three status columns and search.
- Each card is a button-like article with `data-action="openEvtDetail"`,
  `tabindex="0"`, and `aria-label`.
- Board cards contain no direct editable controls:
  - no `data-action="fieldEdit"`
  - no inline title input
  - no inline description textarea
  - no status or priority select
- Card metadata uses human-readable labels for status, priority, and event type.
- Card actions are limited to opening detail; direct completion/cancel controls
  may live in the detail drawer, not in the card itself.

## Detail Drawer Acceptance

- `/work` includes one reusable event detail drawer with:
  - `id="evtDetailDrawer"`
  - `id="evtDetailForm"`
  - fields for title, description, status, priority
  - a close action
  - save, complete, and cancel actions
- Opening a card populates the drawer from `evtCache`.
- Saving the drawer calls the existing `PATCH /api/evt/{evtId}` path.
- Complete/cancel in the drawer reuse existing update/delete behavior.
- The drawer may be closed by close button, Escape, or after a successful save.
- Auto-refresh should not overwrite a detail drawer while the user is editing.

## Visual Direction

- Keep the light workbench tone.
- Cards should be denser and calmer than forms: no large inputs, no heavy chrome.
- The selected/open card should have a clear active state.
- The drawer should feel like a focused editor, not another nested dashboard.
