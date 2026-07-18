#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_ROOT="${SMARTCORE_DEV_ROOT:-/opt/smartcore-dev}"
PROJECT_NAME="${SMARTCORE_DEV_COMPOSE_PROJECT:-smartcore-dev}"
COMPOSE_FILE="$ROOT/deploy/docker-compose.dev.yml"
STATE_DIR="${SMARTCORE_DEPLOY_STATE_DIR:-/var/lib/smartcore-deploy}"
CANDIDATE_FILE="$STATE_DIR/candidate"
LOCK_FILE="${SMARTCORE_DEPLOY_LOCK_FILE:-/var/lock/smartcore-deploy.lock}"
APP_IMAGE_REPO="${SMARTCORE_IMAGE_REPO:-smartcore}"
ADAPTER_IMAGE_REPO="${SMARTCORE_ADAPTER_IMAGE_REPO:-smartcore-openclaw-adapter}"

log() {
    printf '[smartcore-dev] %s\n' "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

compose_dev() {
    SMARTCORE_IMAGE_TAG="$1" \
        docker compose \
        --project-name "$PROJECT_NAME" \
        --project-directory "$ROOT/deploy" \
        --file "$COMPOSE_FILE" \
        "${@:2}"
}

wait_for_dev_health() {
    local tag="$1"
    local container_id status
    container_id="$(compose_dev "$tag" ps --quiet app)"
    [[ -n "$container_id" ]] || return 1

    for _ in $(seq 1 30); do
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}starting{{end}}' "$container_id")"
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

verify_runtime_image() (
    local tag="$1"
    local container_name="smartcore-candidate-${tag:0:12}-$$"

    docker run \
        --detach \
        --name "$container_name" \
        --network none \
        --tmpfs /app/data \
        --tmpfs /app/backups \
        --env DATABASE_URL=sqlite:////app/data/smartcore.sqlite \
        --env AUTH_SECRET=smartcore-candidate-only-secret \
        --env SCHEDULER_ENABLED=false \
        "$APP_IMAGE_REPO:$tag" >/dev/null

    cleanup_candidate() {
        docker rm --force "$container_name" >/dev/null 2>&1 || true
    }
    trap cleanup_candidate EXIT

    local status
    for _ in $(seq 1 30); do
        status="$(docker inspect --format '{{.State.Status}}' "$container_name")"
        [[ "$status" == running ]] || return 1
        if docker exec "$container_name" python -c \
            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)" \
            >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    return 1
)

write_candidate_state() {
    local sha="$1"
    local app_image_id="$2"
    local adapter_image_id="$3"
    local state_tmp
    mkdir -p "$STATE_DIR"
    state_tmp="$(mktemp "$STATE_DIR/candidate.XXXXXX")"
    {
        printf 'CANDIDATE=%q\n' "$sha"
        printf 'APP_IMAGE_ID=%q\n' "$app_image_id"
        printf 'ADAPTER_IMAGE_ID=%q\n' "$adapter_image_id"
        printf 'VERIFIED_AT=%q\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } >"$state_tmp"
    chmod 600 "$state_tmp"
    mv "$state_tmp" "$CANDIDATE_FILE"
}

main() {
    require_command docker
    require_command git
    require_command flock

    case "${1:-}" in
        "")
            ;;
        *)
            printf 'Usage: %s\n' "$0" >&2
            exit 2
            ;;
    esac

    [[ "$ROOT" == "$EXPECTED_ROOT" ]] || die "run this script from $EXPECTED_ROOT (got $ROOT)"
    [[ "$(git -C "$ROOT" branch --show-current)" == "dev" ]] || die "candidate checkout must be on dev"
    [[ -z "$(git -C "$ROOT" status --porcelain)" ]] || die "candidate checkout has uncommitted files"

    mkdir -p "$(dirname "$LOCK_FILE")"
    exec 9>"$LOCK_FILE"
    flock -n 9 || die "another SmartCore build or deployment is running"

    log "fetching origin/dev"
    git -C "$ROOT" fetch --prune origin dev main
    git -C "$ROOT" merge-base --is-ancestor HEAD origin/dev \
        || die "origin/dev cannot be fast-forwarded from this checkout"
    git -C "$ROOT" merge --ff-only origin/dev

    local sha app_image_id adapter_image_id
    sha="$(git -C "$ROOT" rev-parse HEAD)"

    log "running cached backend and frontend verification"
    docker build \
        --target verification \
        --file "$ROOT/deploy/Dockerfile" \
        --tag "smartcore-verification:$sha" \
        "$ROOT"
    log "building candidate application image $APP_IMAGE_REPO:$sha"
    docker build \
        --build-arg "VCS_REF=$sha" \
        --file "$ROOT/deploy/Dockerfile" \
        --tag "$APP_IMAGE_REPO:$sha" \
        "$ROOT"

    log "building candidate Adapter image $ADAPTER_IMAGE_REPO:$sha"
    docker build \
        --build-arg "VCS_REF=$sha" \
        --file "$ROOT/deploy/adapter.Dockerfile" \
        --tag "$ADAPTER_IMAGE_REPO:$sha" \
        "$ROOT"

    log "checking the candidate runtime without production data or network access"
    verify_runtime_image "$sha" || die "candidate runtime health check failed"

    log "starting isolated dev app on 127.0.0.1:${SMARTCORE_DEV_PORT:-18000}"
    compose_dev "$sha" up --detach --no-build
    wait_for_dev_health "$sha" || die "isolated dev app failed its health check"

    app_image_id="$(docker image inspect --format '{{.Id}}' "$APP_IMAGE_REPO:$sha")"
    adapter_image_id="$(docker image inspect --format '{{.Id}}' "$ADAPTER_IMAGE_REPO:$sha")"
    write_candidate_state "$sha" "$app_image_id" "$adapter_image_id"

    log "candidate verified: $sha"
    log "dev health: http://127.0.0.1:${SMARTCORE_DEV_PORT:-18000}/healthz"
    log "after manual confirmation run /opt/smartcore/scripts/promote_prod.sh"
}

main "$@"
