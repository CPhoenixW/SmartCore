#!/usr/bin/env bash
set -Eeuo pipefail

OPENCLAW_HOME_DIR="${OPENCLAW_HOME:-/root/.openclaw}"
CONFIG_PATH="$OPENCLAW_HOME_DIR/openclaw.json"
BACKUP_DIR="$OPENCLAW_HOME_DIR/backups"
SERVICE_NAME="${OPENCLAW_SERVICE_NAME:-openclaw-gateway.service}"
MODEL_REF="tokendance/qwen3.7-plus"

log() {
    printf '[smartcore-openclaw] %s\n' "$*"
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

openclaw_bin() {
    local candidate
    candidate="$OPENCLAW_HOME_DIR/bin/openclaw"
    [[ -x "$candidate" ]] || die "OpenClaw CLI is missing: $candidate"
    printf '%s\n' "$candidate"
}

prepare_path() {
    local node_bin
    node_bin="$(find "$OPENCLAW_HOME_DIR/tools" -maxdepth 2 -type d -path '*/node-*/bin' -print 2>/dev/null | sort -r | head -n 1)"
    [[ -n "$node_bin" ]] || die "OpenClaw Node.js runtime is missing"
    export PATH="$node_bin:$PATH"
}

validate_active_config() {
    "$(openclaw_bin)" config validate >/dev/null
}

restart_gateway() {
    systemctl --user restart "$SERVICE_NAME"
    for _ in $(seq 1 20); do
        if systemctl --user is-active --quiet "$SERVICE_NAME"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

status() {
    prepare_path
    command -v jq >/dev/null 2>&1 || die "jq is required"
    [[ -f "$CONFIG_PATH" ]] || die "OpenClaw config is missing: $CONFIG_PATH"
    validate_active_config
    local model input
    model="$("$(openclaw_bin)" models --agent smartcore status --json | jq -r '.resolvedDefault // empty')"
    input="$("$(openclaw_bin)" models --agent smartcore list --json | jq -r '.models[] | select(.key == "tokendance/qwen3.7-plus") | .input')"
    log "smartcore_model=${model:-missing} qwen_input=${input:-missing} gateway=$(systemctl --user is-active "$SERVICE_NAME" 2>/dev/null || true)"
}

apply_config() {
    prepare_path
    command -v jq >/dev/null 2>&1 || die "jq is required"
    [[ -f "$CONFIG_PATH" ]] || die "OpenClaw config is missing: $CONFIG_PATH"
    jq -e '.models.providers.tokendance and any(.agents.list[]?; .id == "smartcore")' "$CONFIG_PATH" >/dev/null \
        || die "Tokendance provider or smartcore agent is not configured"

    mkdir -p "$BACKUP_DIR"
    chmod 700 "$BACKUP_DIR"
    local backup temporary
    backup="$BACKUP_DIR/openclaw-before-qwen-$(date -u +%Y%m%dT%H%M%SZ).json"
    install -m 600 "$CONFIG_PATH" "$backup"
    temporary="$(mktemp "$OPENCLAW_HOME_DIR/openclaw.json.qwen.XXXXXX")"
    trap 'rm -f -- "${temporary:-}"' RETURN
    jq --arg model "$MODEL_REF" '
        .models.mode = "merge"
        | .models.providers.tokendance.models = (
            ((.models.providers.tokendance.models // [])
            | map(select(.id != "qwen3.7-plus")))
            + [{
                id: "qwen3.7-plus",
                name: "Qwen3.7 Plus via Tokendance",
                input: ["text", "image"],
                contextWindow: 1000000
            }]
        )
        | .agents.defaults.models[$model] = (.agents.defaults.models[$model] // {})
        | .agents.list = (.agents.list | map(if .id == "smartcore" then .model = $model else . end))
        | .tools.fs.workspaceOnly = true
    ' "$CONFIG_PATH" >"$temporary"
    chmod 600 "$temporary"
    install -m 600 "$temporary" "$CONFIG_PATH"
    rm -f -- "$temporary"
    temporary=""
    if ! validate_active_config || ! restart_gateway; then
        install -m 600 "$backup" "$CONFIG_PATH"
        restart_gateway || true
        die "Qwen configuration failed; restored $backup"
    fi
    log "configured $MODEL_REF; backup=$backup"
    status
}

rollback() {
    prepare_path
    local requested resolved
    requested="${1:-}"
    [[ -n "$requested" ]] || die "rollback requires an explicit backup path"
    [[ -f "$requested" ]] || die "backup does not exist: $requested"
    resolved="$(realpath "$requested")"
    [[ "$resolved" == "$BACKUP_DIR"/openclaw-before-qwen-*.json ]] \
        || die "backup must be an OpenClaw Qwen backup under $BACKUP_DIR"
    install -m 600 "$resolved" "$CONFIG_PATH"
    validate_active_config || die "restored config is invalid"
    restart_gateway || die "gateway did not restart after rollback"
    log "restored $resolved"
    status
}

case "${1:-}" in
    ""|--apply) apply_config ;;
    --status) status ;;
    --rollback) rollback "${2:-}" ;;
    *) printf 'Usage: %s [--apply | --status | --rollback BACKUP]\n' "$0" >&2; exit 2 ;;
esac
