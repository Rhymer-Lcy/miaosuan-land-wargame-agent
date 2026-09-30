#!/usr/bin/env bash
# Play the registered latency-diagnostic plan: one isolated engine process (and diagnostic session) per game.
#
# Usage: scripts/run_latency_diagnostic.sh --python PYTHON [--engine-install DIR]
#
# Same isolation as scripts/run_evaluation.sh: an empty environment (env -i), the persistent
# installation's home/ as HOME, no user site-packages, PYTHONHASHSEED=0, no GPU and a hard timeout.
# A game with a record is skipped; a game started earlier without a record stops the run; any game
# that does not complete stops the run (diagnostic games are never rerun). Outputs stay under the
# git-ignored local/diagnostics/latency/engine/.
set -euo pipefail

PYTHON=""
INSTALL=""
TIMEOUT_SECONDS=${EVALUATION_GAME_TIMEOUT_SECONDS:-2100}
while [[ $# -gt 0 ]]; do
    case $1 in
        --python) PYTHON=$2; shift 2 ;;
        --engine-install) INSTALL=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [[ -z $PYTHON ]]; then
    echo "usage: $0 --python PYTHON [--engine-install DIR]" >&2
    exit 2
fi
if [[ $(id -u) -eq 0 ]]; then
    echo "refusing to run the engine as root" >&2
    exit 2
fi
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL=${INSTALL:-$REPO/local/engines/sdk-4.1.0}
INSTALL=$(cd "$INSTALL" && pwd)
WORK="$REPO/local/diagnostics/latency/engine"
PLAN="$REPO/evaluation/latency-diagnostic-1/plan.json"
mkdir -p "$WORK/started" "$WORK/logs" "$WORK/cwd/a/b"
COMMIT=$(git -C "$REPO" rev-parse HEAD)
if [[ -n $(git -C "$REPO" status --porcelain) ]]; then
    echo "refusing to run from a dirty checkout" >&2
    exit 2
fi
mapfile -t GAMES < <(PYTHONNOUSERSITE=1 "$PYTHON" -c 'import json,sys; [print(g["id"]) for g in json.load(open(sys.argv[1]))["games"]]' "$PLAN")
echo "latency diagnostic: ${#GAMES[@]} games, harness $COMMIT"
for id in "${GAMES[@]}"; do
    if [[ -f $WORK/$id.json.gz ]]; then
        echo "recorded already: $id"
        continue
    fi
    if [[ -e $WORK/started/$id ]]; then
        echo "STOP: $id was started earlier and left no record" >&2
        exit 1
    fi
    date -u +%Y-%m-%dT%H:%M:%SZ > "$WORK/started/$id"
    set +e
    (
        cd "$WORK/cwd/a/b" &&
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
            "$PYTHON" "$REPO/scripts/diagnose_latency_engine.py" --game-id "$id" \
                --engine-install "$INSTALL" --harness-commit "$COMMIT" \
            > "$WORK/logs/$id.log" 2>&1
    )
    status=$?
    set -e
    tail -n 1 "$WORK/logs/$id.log"
    if [[ $status -ne 0 ]]; then
        echo "STOP: $id exited with status $status" >&2
        exit "$status"
    fi
done
echo "latency diagnostic finished"
