#!/usr/bin/env bash
# Root-disk guard for rllm native-docker runs on a shared host.
#
# Each `docker build` of a task image (FROM --platform=linux/x86_64 ... with
# the containerd image store) leaves an untagged copy of the image next to the
# tagged rllm-task-<id>; `docker rmi rllm-task-<id>` removes the tag but that
# untagged image keeps the layers alive. They show up as dangling images with
# WorkingDir=/testbed. This guard removes those once they are old enough not
# to be an in-progress build, and reports free space.
#
# Scope: only dangling images with WorkingDir=/testbed, younger than MAX_AGE_H
# (ours; the SWE-Factory pipeline uses the same convention and its own guard
# applies the same 24h rule) and older than MIN_AGE_MIN. Never touches tagged
# images, other users' images, or anything with `prune -a`.
#
#   bash disk_guard_rllm.sh sweep        # once
#   bash disk_guard_rllm.sh watch        # loop every INTERVAL seconds
#
# Env: GUARD_PATH (/), INTERVAL (120), MIN_AGE_MIN (15), MAX_AGE_H (24)
#      MIN_FREE_GB (0): in watch mode, sweep only when free space is below this.
#      CACHE_PRUNE_BELOW_GB (120): `docker builder prune -af` when free space is below this.
#
# Caution: the legacy builder (no buildx in the rllm container) keeps each
# build step as a dangling image until the build finishes, so sweeping while
# builds run can delete a layer a build still needs ("content digest ... not
# found"). Between batches MIN_AGE_MIN=0 is safe; during a run keep the age
# gate above the longest build and gate on MIN_FREE_GB as an emergency only.

set -uo pipefail
GUARD_PATH="${GUARD_PATH:-/}"
INTERVAL="${INTERVAL:-120}"
MIN_AGE_MIN="${MIN_AGE_MIN:-15}"
MAX_AGE_H="${MAX_AGE_H:-24}"
MIN_FREE_GB="${MIN_FREE_GB:-0}"
CACHE_PRUNE_BELOW_GB="${CACHE_PRUNE_BELOW_GB:-120}"

free_gb() { df --output=avail -BG "$GUARD_PATH" | tail -1 | tr -dc '0-9'; }

sweep() {
    local now before after ids
    now=$(date +%s)
    before=$(free_gb)
    ids=$(docker images -f dangling=true --format '{{.ID}}' \
        | xargs -r docker image inspect --format '{{.Id}} {{.Config.WorkingDir}} {{.Created}}' 2>/dev/null \
        | awk '$2=="/testbed"{print $1, $3}' \
        | while read -r id created; do
            # Go RFC3339Nano has a variable-width fraction; drop it before parsing.
            ts=$(date -u -d "$(echo "$created" | sed -E 's/\.[0-9]+//')" +%s 2>/dev/null || echo 0)
            age=$(( now - ts ))
            if [ "$age" -ge $(( MIN_AGE_MIN * 60 )) ] && [ "$age" -le $(( MAX_AGE_H * 3600 )) ]; then echo "$id"; fi
        done)
    local n=0
    if [ -n "$ids" ]; then
        n=$(echo "$ids" | wc -l)
        # No -f: an image a running container still uses is skipped, not untagged.
        echo "$ids" | xargs -r -n20 docker rmi >/dev/null 2>&1
    fi
    # BuildKit build cache (containerd store) is the other root-disk consumer:
    # a batch of 16 x 5 GB images carried 127 GB of cache. Records still in
    # use by a running build are never reclaimable, so -a is safe mid-build;
    # it is daemon-wide (other users rebuild slower), hence the free-space gate.
    if [ "$(free_gb)" -lt "$CACHE_PRUNE_BELOW_GB" ]; then
        timeout 600 docker builder prune -af 2>&1 | tail -1 | sed "s/^/[disk-guard-rllm $(date '+%F %T')] builder prune -af: /"
        # Task images of one batch can exceed the root-disk budget on their own
        # (measured: 34 images = 140 GB). An image no running sandbox uses is
        # either finished for this batch or not started yet; dropping it costs
        # at most a rebuild (the builder reuses an existing image, else rebuilds).
        # Only images older than IDLE_IMAGE_MIN_AGE_MIN: a freshly built image has
        # no container yet for a few seconds while rllm creates the sandbox, and
        # removing it there fails the rollout with ImageNotFound (seen once).
        local idle=0 now img created ts
        now=$(date +%s)
        for img in $(docker images --format '{{.Repository}}' | grep '^rllm-task-'); do
            if [ -z "$(docker ps -q --filter "ancestor=$img" | head -1)" ]; then
                created=$(docker image inspect --format '{{.Created}}' "$img" 2>/dev/null | sed -E 's/\.[0-9]+//')
                ts=$(date -u -d "$created" +%s 2>/dev/null || echo "$now")
                if [ $(( now - ts )) -ge $(( ${IDLE_IMAGE_MIN_AGE_MIN:-20} * 60 )) ]; then
                    docker rmi -f "$img" >/dev/null 2>&1 && idle=$((idle + 1))
                fi
            fi
        done
        echo "[disk-guard-rllm $(date '+%F %T')] removed ${idle} idle rllm-task images"
    else
        timeout 300 docker builder prune -f >/dev/null 2>&1
    fi
    after=$(free_gb)
    echo "[disk-guard-rllm $(date '+%F %T')] removed ${n} dangling /testbed images: ${before}G -> ${after}G"
}

case "${1:-sweep}" in
    sweep) sweep ;;
    watch)
        while true; do
            if [ "$(free_gb)" -lt "$MIN_FREE_GB" ] || [ "$MIN_FREE_GB" = 0 ]; then sweep; else echo "[disk-guard-rllm $(date '+%F %T')] free $(free_gb)G >= ${MIN_FREE_GB}G, idle"; fi
            sleep "$INTERVAL"
        done ;;
    *) echo "usage: $0 {sweep|watch}"; exit 1 ;;
esac
