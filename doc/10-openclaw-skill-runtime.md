# OpenClaw Skill Runtime Plan

## Goal

SmartCore remains the reliable business system while OpenClaw becomes the agent orchestration layer. The runtime model is:

```text
Feishu -> SmartCore Gateway -> OpenClaw SmartCore skill -> SmartCore Agent API -> SmartCore DB/feedback
```

DeepSeek is the model provider used by OpenClaw. Claude Code and Codex are development tools only; they must not be production runtime agents that operate the SmartCore database.

## Boundaries

SmartCore owns:

- Feishu webhook validation, deduplication, and normalized event forwarding.
- Database CRUD authority through `/agent/db/*` APIs.
- The scheduler reminder loop and proactive Feishu reminder cards.
- The internal `/dashboard/*` web panel.
- Feishu card templates, confirmation flow, audit logs, backups, and deployment.

OpenClaw owns:

- Natural-language understanding, multi-step planning, ambiguity handling, and tool orchestration.
- Calling SmartCore only through authenticated Agent APIs.
- Using DeepSeek as its model backend.

OpenClaw must never access SQLite files, Docker volumes, backups, `.env`, or production secrets directly.

## Acceptance Criteria

- The repository contains an OpenClaw SmartCore skill under `openclaw/skills/smartcore/SKILL.md`.
- `/agent/tools` exposes query, create, update, delete, and feedback tools with input schemas and risk metadata.
- SmartCore keeps forwarding Feishu messages/card actions to OpenClaw when `OPENCLAW_EVENTS_ENDPOINT` is configured.
- SmartCore keeps scheduler reminders independent from OpenClaw and DeepSeek.
- The dashboard exposes an agent status page showing endpoint/token/scheduler configuration and recent OpenClaw forwarding logs.
