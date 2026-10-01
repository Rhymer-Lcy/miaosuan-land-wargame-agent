#!/usr/bin/env bash
# Play the registered evaluation plan: one isolated engine process (and session) per game.
#
# Usage: scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan gate1|suite|study|ab|residual516
#                                  [--evaluation NAME] [--engine-install DIR] [--workers N]
#                                  [--purpose diagnostic --work DIR [--games FILE]]
#
#   --plan gate1       the two Gate 1 games (registered scenario, mirror of the policy under test)
#   --plan suite       every registered suite game, in registered order; refused until Gate 1 passed
#   --plan study       every game of a registered variance study, in its registered schedule; the
#                      study's own manifest is re-derived as well, every game re-checks the pinned
#                      baseline-v1 digest, and the run stops after 3 consecutive games that did not
#                      complete (records are analysed by scripts/analyze_variance_study.py)
#   --plan ab          every game of the registered shoot-reservation experiment, both groups, in its
#                      registered schedule; its manifest is re-derived, both groups' digests are checked
#                      before the first and after the last game (group B must be baseline-v1-runtime-r1),
#                      every game re-checks its group's digest, and the run stops after 3 consecutive
#                      games that did not complete (records: scripts/analyze_shoot_experiment.py)
#   --plan residual516 every game of the registered residual-516 diagnostic, in registered order; its manifest
#                      is re-derived, the frozen baseline-v2 digest is checked before the first and after the
#                      last game and by every game, each game writes its private capture beside its record,
#                      and the run stops after 3 consecutive games that did not complete (records and
#                      captures: scripts/residual516_diagnostic.py)
#   --evaluation NAME  the registered evaluation: evaluation/NAME/manifest.json, records under
#                      local/evaluation/NAME (default baseline-v0). The baseline-v0 manifest is
#                      re-derived before every run; a candidate evaluation also re-derives its own.
#   --workers N        games played at once (default 1: the serial loop below, unchanged). N > 1 hands
#                      the plan's games, in registered order, to scripts/run_game_pool.py: shared engine
#                      sessions, a working directory per game, worker and batch recorded with every game.
#                      A registered evaluation must run with the worker count its manifest registers
#                      (execution.workers; a manifest without it registers 1).
#   --purpose diagnostic --work DIR [--games FILE] [--runtime ID]
#                      a diagnostic run: its own work directory, optionally only the registered games
#                      listed in FILE (kept in registered order), any worker count and any runtime
#                      identity; the engine ledger records the sessions as diagnostic.
#
# Every game runs on a runtime identity (src/miaosuan_agent/evaluation/execution.py): the manifest's
# execution.runtime (default baseline-v1-runtime-r1, which sets no numerical-thread variable), or for a
# diagnostic run --runtime. Its variables, and no others, are added to each game's empty environment,
# and a registered scheduler identity (execution.scheduler) must match the pool's.
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
WORKERS=1
PURPOSE=evaluation
WORK=""
GAMES_FILE=""
RUNTIME=""
TIMEOUT_SECONDS=${EVALUATION_GAME_TIMEOUT_SECONDS:-2100}
while [[ $# -gt 0 ]]; do
    case $1 in
        --python) PYTHON=$2; shift 2 ;;
        --sdk-archive) ARCHIVE=$2; shift 2 ;;
        --engine-install) INSTALL=$2; shift 2 ;;
        --plan) PLAN=$2; shift 2 ;;
        --evaluation) NAME=$2; shift 2 ;;
        --workers) WORKERS=$2; shift 2 ;;
        --purpose) PURPOSE=$2; shift 2 ;;
        --work) WORK=$2; shift 2 ;;
        --games) GAMES_FILE=$2; shift 2 ;;
        --runtime) RUNTIME=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [[ -z $PYTHON || -z $ARCHIVE || ( $PLAN != gate1 && $PLAN != suite && $PLAN != study && $PLAN != ab && $PLAN != residual516 ) ]]; then
    echo "usage: $0 --python PYTHON --sdk-archive ZIP --plan gate1|suite|study|ab|residual516 [--evaluation NAME] [--engine-install DIR] [--workers N] [--purpose diagnostic --work DIR [--games FILE]]" >&2
    exit 2
fi
if ! [[ $WORKERS =~ ^[1-9][0-9]*$ ]]; then
    echo "--workers must be a positive integer" >&2
    exit 2
fi
if [[ $PURPOSE != evaluation && $PURPOSE != diagnostic ]]; then
    echo "--purpose must be evaluation or diagnostic" >&2
    exit 2
fi
if [[ $PURPOSE == evaluation && ( -n $WORK || -n $GAMES_FILE || -n $RUNTIME ) ]]; then
    echo "--work, --games and --runtime are for diagnostic runs (--purpose diagnostic)" >&2
    exit 2
fi
if [[ $PURPOSE == diagnostic && -z $WORK ]]; then
    echo "a diagnostic run needs its own --work directory" >&2
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
if [[ -n $GAMES_FILE ]]; then
    GAMES_FILE=$(cd "$(dirname "$GAMES_FILE")" && pwd)/$(basename "$GAMES_FILE")
fi
WORK=${WORK:-$REPO/local/evaluation/$NAME}
MANIFEST="$REPO/evaluation/$NAME/manifest.json"
if [[ ! -f $MANIFEST ]]; then
    echo "no registered manifest at $MANIFEST" >&2
    exit 2
fi
mkdir -p "$WORK/games" "$WORK/started" "$WORK/logs" "$WORK/cwd/a/b"
WORK=$(cd "$WORK" && pwd)
mapfile -t REGISTERED < <(PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$RUNTIME" <<'PY'
import json, sys
from miaosuan_agent.evaluation import execution as ex
registered = ex.registered(json.load(open(sys.argv[1], encoding="utf-8")))
runtime = sys.argv[2] or registered["runtime"]
variables = ex.runtime_env(runtime)
print(registered["workers"]); print(registered["runtime"]); print(registered["scheduler"] or ""); print(runtime)
for name, value in sorted(variables.items()):
    print(f"{name}={value}")
PY
)
if [[ ${#REGISTERED[@]} -lt 4 ]]; then
    echo "REFUSED: the manifest's execution settings or the runtime '$RUNTIME' are not valid" >&2
    exit 2
fi
REGISTERED_WORKERS=${REGISTERED[0]}
REGISTERED_RUNTIME=${REGISTERED[1]}
REGISTERED_SCHEDULER=${REGISTERED[2]}
RUNTIME=${REGISTERED[3]}
THREAD_ENV=("${REGISTERED[@]:4}")
if [[ $PURPOSE == evaluation && $WORKERS != "$REGISTERED_WORKERS" ]]; then
    echo "REFUSED: the manifest registers $REGISTERED_WORKERS worker(s); a registered run cannot use --workers $WORKERS" >&2
    exit 2
fi
if [[ $PURPOSE == evaluation && $RUNTIME != "$REGISTERED_RUNTIME" ]]; then
    echo "REFUSED: the manifest registers runtime $REGISTERED_RUNTIME; a registered run cannot use $RUNTIME" >&2
    exit 2
fi

host() { PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$NAME" --work "$WORK" "$@"; }

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_evaluation_manifest.py" --sdk-archive "$ARCHIVE" --check
if [[ $NAME != baseline-v0 ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_candidate_manifest.py" --check
fi
if [[ $PLAN == study ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_variance_study_manifest.py" --check
fi
if [[ $PLAN == ab ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_shoot_experiment_manifest.py" --check
fi
if [[ $PLAN == residual516 ]]; then
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_residual516_manifest.py" --check
fi
diagnostic_digest_check() {
    PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$1" <<'PY'
import importlib.util, json, sys
from pathlib import Path
from miaosuan_agent.evaluation import residual516 as rd
spec = importlib.util.spec_from_file_location("rev", Path(sys.argv[1]).parents[2] / "scripts" / "run_evaluation.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if not rd.is_diagnostic(manifest):
    sys.exit("REFUSED: --plan residual516 needs the residual-516 diagnostic manifest")
source = rev.registered_policy_source(manifest)
if source != rd.BASELINE_V2_SOURCE_SHA256 or manifest["policy_source"]["sha256"] != rd.BASELINE_V2_SOURCE_SHA256:
    sys.exit(f"REFUSED at {sys.argv[2]}: the policy source is not baseline-v2 ({source})")
print(f"policy source at {sys.argv[2]}: {source} (baseline-v2)")
PY
}
if [[ $PLAN == residual516 ]]; then
    diagnostic_digest_check start
fi
experiment_digest_check() {
    PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$1" <<'PY'
import importlib.util, json, sys
from pathlib import Path
from miaosuan_agent.evaluation import shoot_experiment as sx
spec = importlib.util.spec_from_file_location("rev", Path(sys.argv[1]).parents[2] / "scripts" / "run_evaluation.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if not sx.is_experiment(manifest):
    sys.exit("REFUSED: --plan ab needs the shoot-reservation experiment manifest")
for group in sx.GROUPS:
    registered = manifest["groups"][group]["policy_source"]
    source = rev.registered_source_digest(registered)
    if source != registered["sha256"]:
        sys.exit(f"REFUSED at {sys.argv[2]}: group {group}'s policy source is not the registered one ({source})")
    if group == "B" and source != sx.RUNTIME_R1_SOURCE_SHA256:
        sys.exit(f"REFUSED at {sys.argv[2]}: group B is not baseline-v1-runtime-r1 ({source})")
    print(f"group {group} policy source at {sys.argv[2]}: {source}")
PY
}
if [[ $PLAN == ab ]]; then
    experiment_digest_check start
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

mapfile -t GAMES < <(PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$PLAN" "$GAMES_FILE" <<'PY'
import json, sys
from miaosuan_agent.evaluation import manifest as mf
from miaosuan_agent.evaluation import residual516 as rd
from miaosuan_agent.evaluation import shoot_experiment as sx
from miaosuan_agent.evaluation import variance_study as vs
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
if sys.argv[2] == "study":
    specs = vs.scheduled_games(manifest)
elif sys.argv[2] == "ab":
    specs = sx.scheduled_games(manifest)
elif sys.argv[2] == "residual516":
    specs = rd.scheduled_games(manifest)
else:
    specs = mf.gate1_games(manifest) if sys.argv[2] == "gate1" else mf.games(manifest)
ids = [spec.game_id for spec in specs]
if sys.argv[3]:
    wanted = [line.strip() for line in open(sys.argv[3], encoding="utf-8") if line.strip()]
    unknown = sorted(set(wanted) - set(ids))
    if unknown or len(set(wanted)) != len(wanted):
        sys.exit(f"REFUSED: the games file lists unknown or repeated games: {unknown}")
    ids = [game for game in ids if game in set(wanted)]
for game in ids:
    print(game)
PY
)
if [[ ${#GAMES[@]} -eq 0 ]]; then
    echo "no games to play" >&2
    exit 2
fi
COMMIT=$(git -C "$REPO" rev-parse HEAD)
DIRTY_ARGS=()
if [[ -n $(git -C "$REPO" status --porcelain) ]]; then
    DIRTY_ARGS=(--harness-dirty)
fi
echo "plan $PLAN: ${#GAMES[@]} games, harness $COMMIT${DIRTY_ARGS:+ (dirty)}, $WORKERS worker(s), purpose $PURPOSE, runtime $RUNTIME ${THREAD_ENV[*]}"

PLANNED=${#GAMES[@]}
failures=0
consecutive=0
if [[ $WORKERS -gt 1 ]]; then
    STOP_AFTER=0
    if [[ $PLAN == study || $PLAN == ab || $PLAN == residual516 ]]; then
        STOP_AFTER=3
    fi
    QUEUE="$WORK/logs/queue-$(date -u +%Y%m%dT%H%M%SZ).txt"
    printf '%s\n' "${GAMES[@]}" > "$QUEUE"
    SCHEDULER_ARGS=()
    if [[ $PURPOSE == evaluation && -n $REGISTERED_SCHEDULER ]]; then
        SCHEDULER_ARGS=(--expected-scheduler "$REGISTERED_SCHEDULER")
    fi
    set +e
    PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/run_game_pool.py" --evaluation "$NAME" --work "$WORK" \
        --engine-install "$INSTALL" --python "$PYTHON" --workers "$WORKERS" --games-file "$QUEUE" \
        --harness-commit "$COMMIT" "${DIRTY_ARGS[@]}" --purpose "$PURPOSE" --timeout "$TIMEOUT_SECONDS" \
        --stop-after-failures "$STOP_AFTER" --runtime "$RUNTIME" "${SCHEDULER_ARGS[@]}"
    status=$?
    set -e
    if [[ $status -ne 0 ]]; then
        echo "the parallel run stopped with status $status" >&2
        exit "$status"
    fi
    GAMES=()
fi
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
            "${THREAD_ENV[@]}" \
            timeout --signal=TERM --kill-after=30 "$TIMEOUT_SECONDS" \
            "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$NAME" --work "$WORK" game --game-id "$id" \
                --engine-install "$INSTALL" --purpose "$PURPOSE" --runtime "$RUNTIME" \
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
        if [[ ( $PLAN == study || $PLAN == ab || $PLAN == residual516 ) && $consecutive -ge 3 ]]; then
            echo "STOP: 3 consecutive games did not complete; the run stops as registered" >&2
            exit 1
        fi
    else
        consecutive=0
    fi
done

if [[ $PLAN == study ]]; then
    study_digest_check end
elif [[ $PLAN == ab ]]; then
    experiment_digest_check end
elif [[ $PLAN == residual516 ]]; then
    diagnostic_digest_check end
else
    host summarize
fi
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
if [[ $WORKERS -gt 1 ]]; then
    echo "plan $PLAN finished: $PLANNED games with $WORKERS workers (counts above)"
else
    echo "plan $PLAN finished: $PLANNED games, $failures not completed"
fi
