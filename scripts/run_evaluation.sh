#!/usr/bin/env bash
# Play the registered evaluation plan: one isolated engine process (and session) per game.
#
# Usage: scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan gate1|suite|study
#                                  [--evaluation NAME] [--engine-install DIR]
#
#   --plan gate1       the two Gate 1 games (registered scenario, mirror of the policy under test)
#   --plan suite       every registered suite game, in registered order; refused until Gate 1 passed
#   --plan study       every game of a registered variance study, in its registered schedule; the
#                      study's own manifest is re-derived as well, every game re-checks the pinned
#                      baseline-v1 digest, and the run stops after 3 consecutive games that did not
#                      complete (records are analysed by scripts/analyze_variance_study.py)
#   --evaluation NAME  the registered evaluation: evaluation/NAME/manifest.json, records under
#                      local/evaluation/NAME (default baseline-v0). The baseline-v0 manifest is
#                      re-derived before every run; a candidate evaluation also re-derives its own.
#
# Each game runs with the same isolation as scripts/run_engine_smoke_test.sh: an empty environment
# (env -i), the persistent installation's home/ as HOME, no user site-packages, PYTHONHASHSEED=0,
# no GPU and a hard timeout. Records are never overwritten: a game with a record is skipped, and a
# game that was started earlier but left no record stops the run, because rerunning it silently
# would select among outcomes. Everything is written under the git-ignored local/evaluation/.
set -euo pipefail

PYTHON=""
ARCHIVE=""
INSTALL=""
PLAN=""
NAME=baseline-v0
TIMEOUT_SECONDS=${EVALUATION_GAME_TIMEOUT_SECONDS:-2100}
while [[ $# -gt 0 ]]; do
    case $1 in
        --python) PYTHON=$2; shift 2 ;;
        --sdk-archive) ARCHIVE=$2; shift 2 ;;
        --engine-install) INSTALL=$2; shift 2 ;;
        --plan) PLAN=$2; shift 2 ;;
        --evaluation) NAME=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [[ -z $PYTHON || -z $ARCHIVE || ( $PLAN != gate1 && $PLAN != suite && $PLAN != study ) ]]; then
    echo "usage: $0 --python PYTHON --sdk-archive ZIP --plan gate1|suite|study [--evaluation NAME] [--engine-install DIR]" >&2
    exit 2
fi
if [[ $(id -u) -eq 0 ]]; then
    echo "refusing to run the engine as root" >&2
    exit 2
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL=${INSTALL:-$REPO/local/engines/sdk-4.1.0}
if [[ ! -f $INSTALL/install-manifest.json ]]; then
    echo "no persistent engine installation at $INSTALL" >&2
    exit 2
fi
INSTALL=$(cd "$INSTALL" && pwd)
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")
WORK="$REPO/local/evaluation/$NAME"
MANIFEST="$REPO/evaluation/$NAME/manifest.json"
if [[ ! -f $MANIFEST ]]; then
    echo "no registered manifest at $MANIFEST" >&2
    exit 2
fi
mkdir -p "$WORK/games" "$WORK/started" "$WORK/logs" "$WORK/cwd/a/b"

host() { PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$NAME" "$@"; }

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_evaluation_manifest.py" --sdk-archive "$ARCHIVE" --check
if [[ $NAME != baseline-v0 ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_candidate_manifest.py" --check
fi
if [[ $PLAN == study ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_variance_study_manifest.py" --check
fi
study_digest_check() {
    PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$1" <<'PY'
import importlib.util, json, sys
from pathlib import Path
from miaosuan_agent.evaluation import variance_study as vs
spec = importlib.util.spec_from_file_location("rev", Path(sys.argv[1]).parents[2] / "scripts" / "run_evaluation.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if not vs.is_study(manifest):
    sys.exit("REFUSED: --plan study needs a variance-study manifest")
source = rev.registered_policy_source(manifest)
if source != vs.BASELINE_V1_SOURCE_SHA256 or manifest["policy_source"]["sha256"] != vs.BASELINE_V1_SOURCE_SHA256:
    sys.exit(f"REFUSED at {sys.argv[2]}: the policy source is not baseline-v1 ({source})")
print(f"policy source at {sys.argv[2]}: {source} (baseline-v1)")
PY
}
if [[ $PLAN == study ]]; then
    study_digest_check start
fi
host stage --sdk-archive "$ARCHIVE" > "$WORK/logs/stage.log"

if [[ $PLAN == suite ]]; then
    host summarize > /dev/null
    PYTHONNOUSERSITE=1 "$PYTHON" - "$WORK/summary.json" "$MANIFEST" <<'PY'
import json, sys
criteria = (json.load(open(sys.argv[1], encoding="utf-8"))["gate1"] or {}).get("criteria")
required = json.load(open(sys.argv[2], encoding="utf-8")).get("gate1_required") or sorted(criteria or {})
decomposition = json.load(open(sys.argv[1], encoding="utf-8"))["gate1"].get("refusal_decomposition") or {}
passed = bool(criteria) and all(criteria[name]["pass"] for name in required)
if not passed or decomposition.get("project_gate_rejections", 0):
    sys.exit("REFUSED: Gate 1 has not passed; the suite may not start")
PY
fi

mapfile -t GAMES < <(PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$PLAN" <<'PY'
import json, sys
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import variance_study as vs
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] == "study":
    specs = vs.scheduled_games(manifest)
else:
    specs = mf.gate1_games(manifest) if sys.argv[2] == "gate1" else mf.games(manifest)
for spec in specs:
    print(spec.game_id)
PY
)
COMMIT=$(git -C "$REPO" rev-parse HEAD)
DIRTY_ARGS=()
if [[ -n $(git -C "$REPO" status --porcelain) ]]; then
    DIRTY_ARGS=(--harness-dirty)
fi
echo "plan $PLAN: ${#GAMES[@]} games, harness $COMMIT${DIRTY_ARGS:+ (dirty)}"

failures=0
consecutive=0
for id in "${GAMES[@]}"; do
    if [[ -f $WORK/games/$id.json ]]; then
        echo "recorded already: $id"
        continue
    fi
    if [[ -e $WORK/started/$id ]]; then
        echo "STOP: $id was started earlier and left no record; investigate and document before rerunning" >&2
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
            "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$NAME" game --game-id "$id" \
                --engine-install "$INSTALL" \
                --harness-commit "$COMMIT" "${DIRTY_ARGS[@]}" \
            > "$WORK/logs/$id.log" 2>&1
    )
    status=$?
    set -e
    tail -n 1 "$WORK/logs/$id.log"
    if [[ $status -ne 0 ]]; then
        failures=$((failures + 1))
        consecutive=$((consecutive + 1))
        echo "game $id exited with status $status" >&2
        if [[ $status -ne 1 ]]; then
            exit "$status"
        fi
        if [[ $PLAN == study && $consecutive -ge 3 ]]; then
            echo "STOP: 3 consecutive games did not complete; the study stops as registered" >&2
            exit 1
        fi
    else
        consecutive=0
    fi
done

if [[ $PLAN == study ]]; then
    study_digest_check end
else
    host summarize
fi
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
echo "plan $PLAN finished: ${#GAMES[@]} games, $failures not completed"
