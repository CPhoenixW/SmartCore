#!/usr/bin/env bash
set -Eeuo pipefail

# Remove only old SmartCore image tags and expired BuildKit cache. Docker volumes,
# databases, backups, and images referenced by running containers are always kept.
APP_IMAGE_REPO="${SMARTCORE_IMAGE_REPO:-smartcore}"
DSH_IMAGE_REPO="${SMARTCORE_DSH_IMAGE_REPO:-smartcore-dsh-runtime}"
VERIFICATION_IMAGE_REPO="${SMARTCORE_VERIFICATION_IMAGE_REPO:-smartcore-verification}"
RETENTION="${SMARTCORE_IMAGE_RETENTION:-3}"
VERIFY_RETENTION="${SMARTCORE_VERIFICATION_RETENTION:-1}"
CACHE_TTL="${SMARTCORE_BUILD_CACHE_TTL:-168h}"
PRUNE_BUILD_CACHE="${SMARTCORE_PRUNE_BUILD_CACHE:-1}"
DRY_RUN="${SMARTCORE_PRUNE_DRY_RUN:-0}"

log() { printf '[smartcore-prune] %s\n' "$*"; }
warn() { printf '[smartcore-prune] WARNING: %s\n' "$*" >&2; }

case "$RETENTION" in ''|*[!0-9]*) warn "invalid SMARTCORE_IMAGE_RETENTION=$RETENTION; using 3"; RETENTION=3;; esac
case "$VERIFY_RETENTION" in ''|*[!0-9]*) warn "invalid SMARTCORE_VERIFICATION_RETENTION=$VERIFY_RETENTION; using 1"; VERIFY_RETENTION=1;; esac

if ! command -v docker >/dev/null 2>&1; then
    warn "docker is not available; skipping cleanup"
    exit 0
fi

# Tags that must survive cleanup. Callers can add more via positional arguments.
protected_tags=()
while (($#)); do
    case "$1" in
        --keep-tag)
            [[ $# -ge 2 ]] || { warn '--keep-tag requires a value'; exit 2; }
            protected_tags+=("$2")
            shift 2
            ;;
        --no-build-cache)
            PRUNE_BUILD_CACHE=0
            shift
            ;;
        --help|-h)
            printf 'Usage: %s [--keep-tag SHA] [--no-build-cache]\n' "$0"
            exit 0
            ;;
        *)
            warn "unknown argument: $1"
            exit 2
            ;;
    esac
done

is_protected_tag() {
    local repo="$1" tag="$2" value
    for value in "${protected_tags[@]}"; do
        [[ "$tag" == "$value" || "$repo:$tag" == "$value" ]] && return 0
    done
    return 1
}

running_image_ids() {
    # Only running containers pin an image needed by the active release.
    # Stopped compose containers may otherwise keep every rollback layer alive
    # forever; removing a tag remains safe because rollback uses named images.
    docker ps -q 2>/dev/null | while read -r container; do
        [[ -n "$container" ]] || continue
        docker inspect --format '{{.Image}}' "$container" 2>/dev/null || true
    done
}

is_running_image() {
    local image_id="$1" running
    while read -r running; do
        [[ -n "$running" && "$running" == "$image_id" ]] && return 0
    done < <(running_image_ids)
    return 1
}

image_created_epoch() {
    docker image inspect --format '{{.Created}}' "$1" 2>/dev/null | sed 's/\.[0-9]*Z$/Z/' | xargs -I{} date -d '{}' +%s 2>/dev/null || printf '0\n'
}

prune_repo() {
    local repo="$1" keep_count="$2"
    local rows tag id created
    rows="$(docker image ls --format '{{.Tag}}\t{{.ID}}' "$repo" 2>/dev/null || true)"
    [[ -n "$rows" ]] || return 0

    # Keep the newest N tags, then remove older unreferenced tags. Sort by image
    # creation time rather than tag name because tags are commit SHAs.
    local sorted
    sorted="$(while IFS=$'\t' read -r tag id; do
        [[ -n "$tag" && "$tag" != '<none>' ]] || continue
        created="$(image_created_epoch "$repo:$tag")"
        printf '%s\t%s\t%s\n' "$created" "$tag" "$id"
    done <<<"$rows" | sort -rn -k1,1)"

    local index=0
    while IFS=$'\t' read -r created tag id; do
        [[ -n "$tag" ]] || continue
        index=$((index + 1))
        if ((index <= keep_count)) || is_protected_tag "$repo" "$tag"; then
            continue
        fi
        if is_running_image "$id"; then
            log "keeping running image $repo:$tag ($id)"
            continue
        fi
        if [[ "$DRY_RUN" == 1 ]]; then
            log "would remove $repo:$tag ($id)"
        else
            log "removing old image tag $repo:$tag ($id)"
            docker image rm "$repo:$tag" >/dev/null 2>&1 || warn "could not remove $repo:$tag"
        fi
    done <<<"$sorted"
}

prune_verification() {
    local rows tag id created sorted index=0
    rows="$(docker image ls --format '{{.Tag}}\t{{.ID}}' "$VERIFICATION_IMAGE_REPO" 2>/dev/null || true)"
    [[ -n "$rows" ]] || return 0
    sorted="$(while IFS=$'\t' read -r tag id; do
        [[ -n "$tag" && "$tag" != '<none>' ]] || continue
        created="$(image_created_epoch "$VERIFICATION_IMAGE_REPO:$tag")"
        printf '%s\t%s\t%s\n' "$created" "$tag" "$id"
    done <<<"$rows" | sort -rn -k1,1)"
    while IFS=$'\t' read -r created tag id; do
        [[ -n "$tag" ]] || continue
        index=$((index + 1))
        if ((index <= VERIFY_RETENTION)) || is_protected_tag "$VERIFICATION_IMAGE_REPO" "$tag"; then
            continue
        fi
        if is_running_image "$id"; then continue; fi
        if [[ "$DRY_RUN" == 1 ]]; then
            log "would remove $VERIFICATION_IMAGE_REPO:$tag ($id)"
        else
            log "removing old verification tag $VERIFICATION_IMAGE_REPO:$tag ($id)"
            docker image rm "$VERIFICATION_IMAGE_REPO:$tag" >/dev/null 2>&1 || warn "could not remove verification image $tag"
        fi
    done <<<"$sorted"
}

prune_build_cache() {
    [[ "$PRUNE_BUILD_CACHE" == 1 ]] || return 0
    if [[ "$DRY_RUN" == 1 ]]; then
        log "would prune BuildKit cache older than $CACHE_TTL"
        return 0
    fi
    docker builder prune --filter "until=$CACHE_TTL" --force >/dev/null 2>&1 || warn "BuildKit cache prune failed"
}

log "retaining newest $RETENTION tags for $APP_IMAGE_REPO and $DSH_IMAGE_REPO"
prune_repo "$APP_IMAGE_REPO" "$RETENTION"
prune_repo "$DSH_IMAGE_REPO" "$RETENTION"
prune_verification
# Dangling layers are safe to remove; this never touches named images or volumes.
if [[ "$DRY_RUN" == 1 ]]; then
    log "would remove dangling image layers"
elif ! docker image prune --force >/dev/null 2>&1; then
    warn "dangling image prune failed"
fi
prune_build_cache
log "cleanup complete"
