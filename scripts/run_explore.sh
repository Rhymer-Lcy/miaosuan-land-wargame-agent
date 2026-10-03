#!/usr/bin/env bash
# Play the games of one EXPLORATORY run card (docs/EXPLORATORY_TRACK.md), serially: one isolated engine process and
# one exclusive diagnostic session per game.
#
# Usage: scripts/run_explore.sh --python PYTHON --sdk-archive ZIP --card CARD [--engine-install DIR] [--work DIR]
#                               [--games FILE]
#
#   --card CARD     evaluation/CARD/manifest.json, a run card built by scripts/build_run_card.py
#   --work DIR      records, captures and logs (default local/evaluation/CARD)
#   --games FILE    only the card's games listed in FILE (kept in card order)
#
# Checks before the first game: a clean, committed tree; the card rebuilds byte-identically; every policy's source
# digest equals the card's (again after the last game, and by every game); the games still to play fit under the
# sprint's ledger-counted session cap; the scenario inputs match the card's digests.
#
# Each game runs with the isolation of scripts/run_evaluation.sh, which stays unchanged: an empty environment (env -i),
# the persistent installation's home/ as HOME, no user site-packages, PYTHONHASHSEED=0, no GPU, the card's runtime
# variables and a hard timeout. Records are never overwritten: a game with a record is skipped, and a game that was
# started earlier but left no record stops the run. The run stops after 3 consecutive games that did not complete.
set -euo pipefail

PYTHON=""
ARCHIVE=""
INSTALL=""
CARD=""
WORK=""
GAMES_FILE=""
TIMEOUT_SECONDS=${EVALUATION_GAME_TIMEOUT_SECONDS:-2100}
while [[ $# -gt 0 ]]; do
    case $1 in
        --python) PYTHON=$2; shift 2 ;;
        --sdk-archive) ARCHIVE=$2; shift 2 ;;
        --engine-install) INSTALL=$2; shift 2 ;;
        --card) CARD=$2; shift 2 ;;
        --work) WORK=$2; shift 2 ;;
        --games) GAMES_FILE=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [[ -z $PYTHON || -z $ARCHIVE || -z $CARD ]]; then
    echo "usage: $0 --python PYTHON --sdk-archive ZIP --card CARD [--engine-install DIR] [--work DIR] [--games FILE]" >&2
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
MANIFEST="$REPO/evaluation/$CARD/manifest.json"
if [[ ! -f $MANIFEST ]]; then
    echo "no run card at $MANIFEST" >&2
    exit 2
fi
if [[ -n $(git -C "$REPO" status --porcelain --untracked-files=no) ]]; then
    echo "REFUSED: exploratory games run only from a clean, committed tree" >&2
    exit 2
fi
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_run_card.py" --card "$CARD" --check
WORK=${WORK:-$REPO/local/evaluation/$CARD}
mkdir -p "$WORK/games" "$WORK/started" "$WORK/logs" "$WORK/cwd/a/b"
WORK=$(cd "$WORK" && pwd)

card_check() {
    PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$1" "$INSTALL/usage-ledger.jsonl" "$WORK" \
        "$GAMES_FILE" <<'PY'
import importlib.util, json, sys
from pathlib import Path
from miaosuan_agent.evaluation import execution as ex
from miaosuan_agent.evaluation import exploratory as xp
spec = importlib.util.spec_from_file_location("rev", Path(sys.argv[1]).parents[2] / "scripts" / "run_evaluation.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)
card = json.load(open(sys.argv[1], encoding="utf-8"))
point, ledger, work, games_file = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
if not xp.is_card(card):
    sys.exit("REFUSED: not an exploratory run card")
for policy, entry in sorted(card["policies"].items()):
    source = rev.registered_source_digest(entry["policy_source"])
    if source != entry["policy_source"]["sha256"]:
        sys.exit(f"REFUSED at {point}: the policy source of {policy} is not the registered one ({source})")
    print(f"{policy} policy source at {point}: {source}", file=sys.stderr)
if point == "start":
    ids = [g["game_id"] for g in card["games"]]
    if games_file:
        wanted = [line.strip() for line in open(games_file, encoding="utf-8") if line.strip()]
        unknown = sorted(set(wanted) - set(ids))
        if unknown or len(set(wanted)) != len(wanted):
            sys.exit(f"REFUSED: the games file lists unknown or repeated games: {unknown}")
        ids = [g for g in ids if g in set(wanted)]
    pending = [g for g in ids if not (work / "games" / f"{g}.json").exists()]
    problem = xp.budget_problem(card, ledger, len(pending))
    if problem:
        sys.exit(f"REFUSED: {problem}")
    used = xp.sessions_after(ledger, card["budget"]["ledger_base_session"])
    print(f"session budget: {used} used after session {card['budget']['ledger_base_session']}, {len(pending)} planned, "
          f"cap {card['budget']['sprint_session_cap']}", file=sys.stderr)
    runtime = ex.registered(card)["runtime"]
    print(f"RUNTIME {runtime}")
    for name, value in sorted(ex.runtime_env(runtime).items()):
        print(f"ENV {name}={value}")
    for g in ids:
        print(f"GAME {g}")
PY
}

mapfile -t PLAN < <(card_check start)
if [[ ${#PLAN[@]} -eq 0 ]]; then
    echo "REFUSED: the card check did not pass" >&2
    exit 2
fi
RUNTIME=""
THREAD_ENV=()
GAMES=()
for line in "${PLAN[@]}"; do
    case $line in
        "RUNTIME "*) RUNTIME=${line#RUNTIME } ;;
        "ENV "*) THREAD_ENV+=("${line#ENV }") ;;
        "GAME "*) GAMES+=("${line#GAME }") ;;
    esac
done
if [[ -z $RUNTIME || ${#GAMES[@]} -eq 0 ]]; then
    echo "REFUSED: no runtime or no games from the card check" >&2
    exit 2
fi

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$CARD" --manifest "$MANIFEST" \
    --work "$WORK" stage --sdk-archive "$ARCHIVE" > "$WORK/logs/stage.log"
COMMIT=$(git -C "$REPO" rev-parse HEAD)
echo "card $CARD: ${#GAMES[@]} games, harness $COMMIT, runtime $RUNTIME ${THREAD_ENV[*]}"

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
            "${THREAD_ENV[@]}" \
            timeout --signal=TERM --kill-after=30 "$TIMEOUT_SECONDS" \
            "$PYTHON" "$REPO/scripts/run_explore_game.py" --card "$CARD" --work "$WORK" game --game-id "$id" \
                --engine-install "$INSTALL" --harness-commit "$COMMIT" \
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
        if [[ $consecutive -ge 3 ]]; then
            echo "STOP: 3 consecutive games did not complete" >&2
            exit 1
        fi
    else
        consecutive=0
    fi
done

card_check end > /dev/null
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
echo "card $CARD finished: ${#GAMES[@]} games, $failures not completed"
