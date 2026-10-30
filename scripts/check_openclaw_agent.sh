#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SMARTCORE_BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${SMARTCORE_AGENT_TOKEN:-}"

headers=(-H "Content-Type: application/json")
if [[ -n "${TOKEN}" ]]; then
  headers+=(-H "X-SmartCore-Agent-Token: ${TOKEN}")
fi

echo "[1/3] healthz"
curl -fsS "${BASE_URL}/healthz" | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("status") == "ok", body
print("ok")
'

echo "[2/3] agent tools"
curl -fsS "${headers[@]}" "${BASE_URL}/agent/tools" | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("ok") is True, body
items = body.get("tools") or body.get("data", {}).get("tools") or []
names = {item.get("name") for item in items}
required = {
    "evtQuery",
    "evtCreate",
    "evtUpdate",
    "evtDelete",
    "ideaCapture",
    "ideaToEvt",
    "screenPush",
}
missing = required - names
assert not missing, {"missing": sorted(missing), "body": body}
print(f"ok: {len(items)} tools")
'

echo "[3/3] read-only event query"
curl -fsS "${headers[@]}" \
  -X POST "${BASE_URL}/agent/db/query_events" \
  -d '{"stat":"todo","includeLinkedPlans":true,"limit":5}' | python3 -c '
import json, sys
body = json.load(sys.stdin)
assert body.get("ok") is True, body
data = body.get("data") or {}
assert isinstance(data.get("events"), list), body
assert isinstance(data.get("count"), int), body
count = data.get("count")
print(f"ok: returned {count} events")
'

echo "Legacy agent contract smoke check passed."
