#!/usr/bin/env bash
# Run one controlled engine session against the persistent engine installation.
#
# Usage: scripts/run_engine_smoke_test.sh --python PYTHON --sdk-archive ZIP [--engine-install DIR]
#                                         [--scenario-id ID --map-id ID] [--capture]
#
#   --python          interpreter of the miaosuan-runtime environment
#   --sdk-archive     local copy of land_wargame_sdk.zip; only read, digest compared before and after
#   --engine-install  persistent installation made once by scripts/engine_install.py
#                     (default: local/engines/sdk-4.1.0)
#   --capture         also write private contract fixtures under local/contract-fixtures/
#
# The engine process gets an empty environment (env -i), the installation's persistent home/ as
# HOME, no user site-packages, no GPU and a hard timeout. This script never creates, repairs or
# reinstalls the installation; integrity and state continuity are enforced by the session ledger
# (docs/ENGINE_INSTALL.md). Run directories live under local/runtime/, which is git-ignored.
set -euo pipefail

PYTHON=""
ARCHIVE=""
INSTALL=""
SCENARIO_ID=201033019601
MAP_ID=9601
CAPTURE=0
TIMEOUT_SECONDS=${SMOKE_TIMEOUT_SECONDS:-900}
while [[ $# -gt 0 ]]; do
    case $1 in
        --python) PYTHON=$2; shift 2 ;;
        --sdk-archive) ARCHIVE=$2; shift 2 ;;
        --engine-install) INSTALL=$2; shift 2 ;;
        --scenario-id) SCENARIO_ID=$2; shift 2 ;;
        --map-id) MAP_ID=$2; shift 2 ;;
        --capture) CAPTURE=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [[ -z $PYTHON || -z $ARCHIVE ]]; then
    echo "usage: $0 --python PYTHON --sdk-archive ZIP [--engine-install DIR] [--scenario-id ID --map-id ID] [--capture]" >&2
    exit 2
fi
if [[ $(id -u) -eq 0 ]]; then
    echo "refusing to run the engine as root" >&2
    exit 2
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL=${INSTALL:-$REPO/local/engines/sdk-4.1.0}
if [[ ! -f $INSTALL/install-manifest.json ]]; then
    echo "no persistent engine installation at $INSTALL; create it once with scripts/engine_install.py install" >&2
    exit 2
fi
INSTALL=$(cd "$INSTALL" && pwd)
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN="$REPO/local/runtime/engine-session-$STAMP"
EVIDENCE="$RUN/evidence"
mkdir -p "$RUN/cwd/a/b" "$EVIDENCE"
CAPTURE_ARGS=()
if [[ $CAPTURE -eq 1 ]]; then
    CAPTURE_ARGS=(--capture-dir "$REPO/local/contract-fixtures/sdk-4.1.0/$STAMP")
fi
COMMIT=$(git -C "$REPO" rev-parse HEAD)
DIRTY_ARGS=()
if [[ -n $(git -C "$REPO" status --porcelain) ]]; then
    DIRTY_ARGS=(--harness-dirty)
fi

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
"$PYTHON" "$REPO/scripts/run_engine_smoke_test.py" stage --sdk-archive "$ARCHIVE" --dest "$RUN/assets" \
    --scenario-id "$SCENARIO_ID" --map-id "$MAP_ID" > "$EVIDENCE/stage.log" 2>&1

run_files() {
    (cd "$RUN" && find assets cwd -type f -print0 | sort -z | xargs -0 -r sha256sum) > "$1"
}
run_files "$EVIDENCE/run-files-before.txt"

started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set +e
(
    cd "$RUN/cwd/a/b" &&
    env -i \
        HOME="$INSTALL/home" \
        PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
        LANG=C.UTF-8 \
        PYTHONNOUSERSITE=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONHASHSEED=0 \
        CUDA_VISIBLE_DEVICES= \
        PYTHONPATH="$INSTALL/site:$REPO/src" \
        timeout --signal=TERM --kill-after=30 "$TIMEOUT_SECONDS" \
        "$PYTHON" "$REPO/scripts/run_engine_smoke_test.py" run \
            --engine-install "$INSTALL" --data-root "$RUN/assets/Data" \
            --scenario-id "$SCENARIO_ID" --map-id "$MAP_ID" --evidence-dir "$EVIDENCE" \
            --harness-commit "$COMMIT" "${DIRTY_ARGS[@]}" "${CAPTURE_ARGS[@]}" \
        > "$EVIDENCE/stdout.log" 2> "$EVIDENCE/stderr.log"
)
exit_code=$?
set -e
finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)

run_files "$EVIDENCE/run-files-after.txt"
diff "$EVIDENCE/run-files-before.txt" "$EVIDENCE/run-files-after.txt" > "$EVIDENCE/run-files-diff.txt" || true
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/engine_install.py" verify --install "$INSTALL" \
    > "$EVIDENCE/install-verify-after.json" 2>&1 || true
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)

{
    echo "scenario_id=$SCENARIO_ID"
    echo "map_id=$MAP_ID"
    echo "harness_commit=$COMMIT"
    echo "host_clock_started_utc=$started_utc"
    echo "host_clock_finished_utc=$finished_utc"
    echo "exit_code=$exit_code"
    echo "timeout_seconds=$TIMEOUT_SECONDS"
    echo "archive_sha256_before=$archive_sha_before"
    echo "archive_sha256_after=$archive_sha_after"
    echo "capture=$CAPTURE"
} > "$EVIDENCE/run-meta.txt"

echo "run directory: $RUN"
cat "$EVIDENCE/run-meta.txt"
tail -n 1 "$EVIDENCE/stdout.log" || true
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
exit "$exit_code"
