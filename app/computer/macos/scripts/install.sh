#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.smartcore.monitor"
DEV_LABEL="com.smartcore.monitor.dev"
DOMAIN="gui/$(id -u)"
SUPPORT_DIR="$HOME/Library/Application Support/SmartCoreMonitor"
INSTALL_DIR="$SUPPORT_DIR/bin"
INSTALL_PATH="$INSTALL_DIR/SmartCoreMonitor"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

log() {
    printf '[smartcore-monitor] %s\n' "$*"
}

build_and_install() {
    log "building release executable"
    swift build --configuration release --package-path "$ROOT"
    local source_path="$ROOT/.build/arm64-apple-macosx/release/SmartCoreMonitor"
    if [[ ! -x "$source_path" ]]; then
        source_path="$(swift build --configuration release --package-path "$ROOT" --show-bin-path)/SmartCoreMonitor"
    fi
    [[ -x "$source_path" ]] || { log "release executable was not produced"; exit 1; }

    mkdir -p "$INSTALL_DIR" "$HOME/Library/LaunchAgents"
    chmod 700 "$SUPPORT_DIR" "$INSTALL_DIR"
    install -m 755 "$source_path" "$INSTALL_PATH"
    codesign --force --sign - --identifier "$LABEL" "$INSTALL_PATH"
    codesign --verify --strict "$INSTALL_PATH"

    local monitor_status
    monitor_status="$("$INSTALL_PATH" status 2>&1 || true)"
    printf '%s\n' "$monitor_status"
    if grep -q 'token=missing' <<<"$monitor_status"; then
        log "migrating the existing device token; macOS may request one-time Keychain approval"
        "$INSTALL_PATH" migrate-token
    fi
    if grep -q 'accessibility=missing' <<<"$monitor_status"; then
        log "Accessibility permission is missing for the installed executable"
        log "run: $INSTALL_PATH accessibility open"
    fi

    local plist_tmp
    plist_tmp="$(mktemp "$HOME/Library/LaunchAgents/$LABEL.XXXXXX")"
    plutil -create xml1 "$plist_tmp"
    plutil -insert Label -string "$LABEL" "$plist_tmp"
    plutil -insert ProgramArguments -json "[\"$INSTALL_PATH\",\"run\"]" "$plist_tmp"
    plutil -insert RunAtLoad -bool true "$plist_tmp"
    plutil -insert KeepAlive -bool true "$plist_tmp"
    plutil -insert ProcessType -string Background "$plist_tmp"
    chmod 600 "$plist_tmp"
    mv "$plist_tmp" "$PLIST_PATH"

    launchctl bootout "$DOMAIN/$DEV_LABEL" >/dev/null 2>&1 || true
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    local bootstrap_attempt
    for bootstrap_attempt in 1 2 3; do
        if launchctl bootstrap "$DOMAIN" "$PLIST_PATH"; then
            break
        fi
        if [[ "$bootstrap_attempt" -eq 3 ]]; then
            log "failed to bootstrap $LABEL after $bootstrap_attempt attempts"
            exit 1
        fi
        sleep 1
    done
    launchctl kickstart -k "$DOMAIN/$LABEL"
    log "installed and started $INSTALL_PATH"
}

uninstall() {
    launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
    if [[ -f "$PLIST_PATH" ]]; then
        mv "$PLIST_PATH" "$PLIST_PATH.disabled"
    fi
    log "stopped the agent; local queue, configuration, and token were preserved"
}

case "${1:-}" in
    "") build_and_install ;;
    --uninstall) uninstall ;;
    *) printf 'Usage: %s [--uninstall]\n' "$0" >&2; exit 2 ;;
esac
