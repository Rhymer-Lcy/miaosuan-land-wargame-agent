#!/usr/bin/env bash
# Run the engine smoke test inside a fresh, disposable run directory.
#
# Usage: scripts/run_engine_smoke_test.sh PYTHON SDK_ARCHIVE [SCENARIO_ID MAP_ID]
#
#   PYTHON       interpreter of the platform runtime environment (CPython 3.10 with numpy/pandas)
#   SDK_ARCHIVE  local copy of land_wargame_sdk.zip; it is only read, and its digest is compared
#                before and after the run
#
# Isolation: the engine wheel is installed with `pip --target` into the run directory instead of
# the environment; the engine process gets an empty environment (`env -i`), a throwaway HOME
# inside the run directory, no user site-packages, no GPU, and a hard wall-clock timeout. Every
# file under the run directory is hashed before and after the engine runs, so any file the engine
# creates, modifies or deletes is recorded. Run directories live under local/runtime/, which is
# git-ignored.
set -euo pipefail

if [[ $# -lt 2 || $# -gt 4 ]]; then
    echo "usage: $0 PYTHON SDK_ARCHIVE [SCENARIO_ID MAP_ID]" >&2
    exit 2
fi
PYTHON=$1
ARCHIVE=$2
SCENARIO_ID=${3:-201033019601}
MAP_ID=${4:-9601}
TIMEOUT_SECONDS=${SMOKE_TIMEOUT_SECONDS:-900}

if [[ $(id -u) -eq 0 ]]; then
    echo "refusing to run the engine as root" >&2
    exit 2
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN="$REPO/local/runtime/engine-smoke-$STAMP"
EVIDENCE="$RUN/evidence"
mkdir -p "$RUN/home" "$RUN/cwd/a/b" "$EVIDENCE"
if [[ -n $(ls -A "$RUN/home") ]]; then
    echo "throwaway HOME $RUN/home is not empty" >&2
    exit 2
fi

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)

"$PYTHON" "$REPO/scripts/run_engine_smoke_test.py" stage \
    --sdk-archive "$ARCHIVE" --dest "$RUN/assets" --scenario-id "$SCENARIO_ID" --map-id "$MAP_ID" \
    > "$EVIDENCE/stage.log" 2>&1
"$PYTHON" -m pip install --no-deps --no-index --no-compile --target "$RUN/site" \
    "$RUN"/assets/wheels/*.whl > "$EVIDENCE/pip-target-install.log" 2>&1

manifest() {
    (cd "$RUN" && find home site assets cwd -type f -print0 | sort -z | xargs -0 -r sha256sum) > "$1"
}
manifest "$EVIDENCE/manifest-before.txt"

started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
set +e
(
    cd "$RUN/cwd/a/b" &&
    env -i \
        HOME="$RUN/home" \
        PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
        LANG=C.UTF-8 \
        PYTHONNOUSERSITE=1 \
        PYTHONDONTWRITEBYTECODE=1 \
        PYTHONHASHSEED=0 \
        CUDA_VISIBLE_DEVICES= \
        PYTHONPATH="$RUN/site:$REPO/src" \
        timeout --signal=TERM --kill-after=30 "$TIMEOUT_SECONDS" \
        "$PYTHON" "$REPO/scripts/run_engine_smoke_test.py" run \
            --data-root "$RUN/assets/Data" --scenario-id "$SCENARIO_ID" --map-id "$MAP_ID" \
            --evidence-dir "$EVIDENCE" \
        > "$EVIDENCE/stdout.log" 2> "$EVIDENCE/stderr.log"
)
exit_code=$?
set -e
finished_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)

manifest "$EVIDENCE/manifest-after.txt"
diff "$EVIDENCE/manifest-before.txt" "$EVIDENCE/manifest-after.txt" > "$EVIDENCE/manifest-diff.txt" || true
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)

{
    echo "scenario_id=$SCENARIO_ID"
    echo "map_id=$MAP_ID"
    echo "started_utc=$started_utc"
    echo "finished_utc=$finished_utc"
    echo "exit_code=$exit_code"
    echo "timeout_seconds=$TIMEOUT_SECONDS"
    echo "archive_sha256_before=$archive_sha_before"
    echo "archive_sha256_after=$archive_sha_after"
    echo "home_files_after=$(cd "$RUN/home" && find . -mindepth 1 | sort | tr '\n' ' ')"
} > "$EVIDENCE/run-meta.txt"

echo "run directory: $RUN"
cat "$EVIDENCE/run-meta.txt"
tail -n 1 "$EVIDENCE/stdout.log" || true
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
exit "$exit_code"
