#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/docker-compose.yml"
ENV_FILE="$ROOT/deploy/.env"
PROJECT_NAME="${SMARTCORE_COMPOSE_PROJECT:-deploy}"
EXPECTED_ROOT="${SMARTCORE_DEPLOY_ROOT:-/opt/smartcore}"
LOCK_FILE="${SMARTCORE_DEPLOY_LOCK_FILE:-/var/lock/smartcore-deploy.lock}"
STATE_DIR="${SMARTCORE_DEPLOY_STATE_DIR:-/var/lib/smartcore-deploy}"
STATE_FILE="$STATE_DIR/state"
CANDIDATE_FILE="$STATE_DIR/candidate"
APP_IMAGE_REPO="${SMARTCORE_IMAGE_REPO:-smartcore}"
DSH_IMAGE_REPO="${SMARTCORE_DSH_IMAGE_REPO:-smartcore-dsh-runtime}"

log() {
    printf '[smartcore-deploy] %s\n' "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

compose() {
    SMARTCORE_IMAGE_TAG="${SMARTCORE_IMAGE_TAG:-latest}" \
        docker compose \
        --project-name "$PROJECT_NAME" \
        --project-directory "$ROOT/deploy" \
        --env-file "$ENV_FILE" \
        --file "$COMPOSE_FILE" \
        "$@"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

acquire_lock() {
    mkdir -p "$(dirname "$LOCK_FILE")"
    exec 9>"$LOCK_FILE"
    flock -n 9 || die "another deployment is already running"
}

verify_environment() {
    [[ "$ROOT" == "$EXPECTED_ROOT" ]] || die "run this script from $EXPECTED_ROOT (got $ROOT)"
    [[ -f "$ENV_FILE" ]] || die "missing production environment file: $ENV_FILE"
    [[ -f "$ROOT/deploy/dsh.env" ]] || die "missing DSH environment file"
    [[ -f "$ROOT/deploy/cloudflared.env" ]] || die "missing Cloudflared environment file"
    [[ "$(git -C "$ROOT" branch --show-current)" == "main" ]] || die "production checkout must be on main"
    [[ -z "$(git -C "$ROOT" status --porcelain)" ]] || die "production checkout has uncommitted files"
    compose config --quiet
}

tag_running_image() {
    local service="$1"
    local image_repo="$2"
    local tag="$3"
    local container_id image_id
    container_id="$(compose ps --quiet "$service")"
    [[ -n "$container_id" ]] || return 0
    image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
    [[ -n "$image_id" ]] || return 0
    if docker image inspect "$image_id" >/dev/null 2>&1; then
        docker image tag "$image_id" "$image_repo:$tag"
        return 0
    fi
    if docker image inspect "$image_repo:$tag" >/dev/null 2>&1; then
        log "$service backing image metadata was pruned; keeping existing rollback tag $image_repo:$tag"
        return 0
    fi
    die "$service backing image metadata was pruned and rollback image is missing: $image_repo:$tag"
}

running_revision() {
    local service="$1"
    local container_id revision
    container_id="$(compose ps --quiet "$service")"
    [[ -n "$container_id" ]] || return 1
    revision="$(docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$container_id" 2>/dev/null || true)"
    if [[ "$revision" =~ ^[0-9a-f]{7,40}$ ]]; then
        printf '%s\n' "$revision"
        return 0
    fi
    return 1
}

backup_database() {
    if [[ -z "$(compose ps --quiet app)" ]]; then
        log "app is not running; skipping pre-deploy database backup"
        return 0
    fi
    log "creating pre-deploy SQLite snapshot"
    compose exec --no-TTY app python -c \
        'from app.server.backup.snapshot import run_local_backup; print(run_local_backup())'
}

wait_for_health() {
    local service="$1"
    local container_id status
    container_id="$(compose ps --quiet "$service")"
    [[ -n "$container_id" ]] || return 1

    for _ in $(seq 1 45); do
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{if .State.Running}}healthy{{else}}unhealthy{{end}}{{end}}' "$container_id")"
        case "$status" in
            healthy)
                return 0
                ;;
            unhealthy|exited|dead)
                return 1
                ;;
        esac
        sleep 2
    done
    return 1
}

wait_for_release() {
    local cloudflared_id
    wait_for_health app || return 1
    wait_for_health dsh-runtime || return 1
    cloudflared_id="$(compose ps --quiet cloudflared)"
    [[ -n "$cloudflared_id" ]] || return 1
    [[ "$(docker inspect --format '{{.State.Running}}' "$cloudflared_id")" == true ]]
}

activate_release() {
    local tag="$1"
    SMARTCORE_IMAGE_TAG="$tag" compose up --detach --no-build
}

write_state() {
    local current="$1"
    local previous="$2"
    mkdir -p "$STATE_DIR"
    {
        printf 'CURRENT=%q\n' "$current"
        printf 'PREVIOUS=%q\n' "$previous"
        printf 'DEPLOYED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$STATE_FILE"
}

rollback_to() {
    local target="$1"
    local current="${2:-unknown}"
    docker image inspect "$APP_IMAGE_REPO:$target" >/dev/null 2>&1 \
        || die "rollback image does not exist: $APP_IMAGE_REPO:$target"
    docker image inspect "$DSH_IMAGE_REPO:$target" >/dev/null 2>&1 \
        || die "rollback image does not exist: $DSH_IMAGE_REPO:$target"

    log "rolling back application and DSH images to $target"
    activate_release "$target"
    wait_for_release || die "rollback release failed its health check"
    write_state "$target" "$current"
    log "rollback complete: release $target"
}

manual_rollback() {
    verify_environment
    [[ -f "$STATE_FILE" ]] || die "deployment state file is missing: $STATE_FILE"
    # The state file is generated by this script and contains shell-escaped values only.
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    local target="${1:-${PREVIOUS:-}}"
    [[ -n "$target" ]] || die "no previous image is recorded"
    rollback_to "$target" "${CURRENT:-unknown}"
}

load_verified_candidate() {
    [[ -f "$CANDIDATE_FILE" ]] || die "no verified candidate; run /opt/smartcore-dev/scripts/deploy_dev.sh first"
    # The candidate file is generated by deploy_dev.sh and contains shell-escaped values only.
    # shellcheck disable=SC1090
    source "$CANDIDATE_FILE"
    [[ "${CANDIDATE:-}" =~ ^[0-9a-f]{40}$ ]] || die "candidate state contains an invalid revision"
    [[ "${APP_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] || die "candidate state contains an invalid app image ID"
    [[ "${DSH_IMAGE_ID:-}" =~ ^sha256:[0-9a-f]{64}$ ]] || die "candidate state contains an invalid DSH image ID"
}

verify_candidate_images() {
    local sha="$1"
    local actual_app_id actual_dsh_id app_revision dsh_revision

    actual_app_id="$(docker image inspect --format '{{.Id}}' "$APP_IMAGE_REPO:$sha" 2>/dev/null)" \
        || die "verified app image is missing: $APP_IMAGE_REPO:$sha"
    actual_dsh_id="$(docker image inspect --format '{{.Id}}' "$DSH_IMAGE_REPO:$sha" 2>/dev/null)" \
        || die "verified DSH image is missing: $DSH_IMAGE_REPO:$sha"
    [[ "$actual_app_id" == "$APP_IMAGE_ID" ]] || die "app image changed after verification"
    [[ "$actual_dsh_id" == "$DSH_IMAGE_ID" ]] || die "DSH image changed after verification"

    app_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$APP_IMAGE_REPO:$sha")"
    dsh_revision="$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$DSH_IMAGE_REPO:$sha")"
    [[ "$app_revision" == "$sha" ]] || die "app image revision label does not match candidate"
    [[ "$dsh_revision" == "$sha" ]] || die "DSH image revision label does not match candidate"
}

promote() {
    verify_environment
    load_verified_candidate

    local checkout_sha deployed_sha dsh_sha new_sha candidate_already_published=false
    local deployed_revision_known=false
    checkout_sha="$(git -C "$ROOT" rev-parse HEAD)"
    if deployed_sha="$(running_revision app)"; then
        if dsh_sha="$(running_revision dsh-runtime)" \
            && [[ "$dsh_sha" == "$deployed_sha" ]]; then
            deployed_revision_known=true
        fi
    else
        deployed_sha="$checkout_sha"
    fi
    tag_running_image app "$APP_IMAGE_REPO" "$deployed_sha"
    tag_running_image dsh-runtime "$DSH_IMAGE_REPO" "$deployed_sha"

    log "checking verified dev candidate against origin"
    git -C "$ROOT" fetch --prune origin main dev
    [[ "$checkout_sha" == "$(git -C "$ROOT" rev-parse origin/main)" ]] \
        || die "production checkout is not aligned with origin/main"
    [[ "$CANDIDATE" == "$(git -C "$ROOT" rev-parse origin/dev)" ]] \
        || die "verified candidate is no longer the tip of origin/dev"
    if git -C "$ROOT" merge-base --is-ancestor origin/main "$CANDIDATE"; then
        :
    elif git -C "$ROOT" merge-base --is-ancestor "$CANDIDATE" origin/main \
        && git -C "$ROOT" diff --quiet "$CANDIDATE" origin/main; then
        candidate_already_published=true
    else
        die "main and the verified dev candidate do not have an identical release tree"
    fi
    if [[ "$checkout_sha" != "$CANDIDATE" ]] \
        && git -C "$ROOT" merge-base --is-ancestor "$CANDIDATE" "$checkout_sha" \
        && git -C "$ROOT" diff --quiet "$CANDIDATE" "$checkout_sha"; then
        # A protected-branch PR may have already published the candidate as a
        # merge commit. The image tag remains the verified candidate SHA when
        # the resulting tree is identical, so do not move main backwards.
        candidate_already_published=true
    fi
    verify_candidate_images "$CANDIDATE"
    new_sha="$CANDIDATE"

    if [[ "$checkout_sha" != "$new_sha" && "$candidate_already_published" != true ]]; then
        log "fast-forwarding origin/main to verified candidate $new_sha"
        git -C "$ROOT" push origin "$new_sha:refs/heads/main"
        git -C "$ROOT" merge --ff-only "$new_sha"
    elif [[ "$candidate_already_published" == true ]]; then
        log "verified candidate $new_sha is already published in origin/main"
    fi

    compose config --quiet
    if [[ "$deployed_revision_known" == true && "$new_sha" == "$deployed_sha" ]] \
        && wait_for_release; then
        log "revision $new_sha is already running and healthy"
        return 0
    fi

    backup_database

    log "activating already-verified release $new_sha without rebuilding"
    if ! activate_release "$new_sha" || ! wait_for_release; then
        log "new release failed; restoring release $deployed_sha"
        rollback_to "$deployed_sha" "$new_sha"
        die "deployment failed and the previous image was restored"
    fi

    write_state "$new_sha" "$deployed_sha"
    log "deployment complete"
    log "revision: $new_sha"
    compose ps
}

usage() {
    printf 'Usage: %s [--promote | --rollback [IMAGE_TAG]]\n' "$0"
}

main() {
    require_command docker
    require_command git
    require_command flock
    acquire_lock

    case "${1:-}" in
        "")
            promote
            ;;
        --promote)
            promote
            ;;
        --rollback)
            manual_rollback "${2:-}"
            ;;
        -h|--help)
            usage
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
}

main "$@"
