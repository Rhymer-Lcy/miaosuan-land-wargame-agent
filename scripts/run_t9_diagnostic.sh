#!/usr/bin/env bash
# Run Sprint 10's four frozen-policy T9 diagnostic games serially with full-step private capture.
set -euo pipefail

PYTHON=""
ARCHIVE=""
INSTALL=""
CARD="s10-t9-v1-diagnosis"
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
if [[ -z $PYTHON || -z $ARCHIVE ]]; then
    echo "usage: $0 --python PYTHON --sdk-archive ZIP [--engine-install DIR] [--work DIR] [--games FILE]" >&2
    exit 2
fi
if [[ $(id -u) -eq 0 ]]; then
    echo "refusing to run the engine as root" >&2
    exit 2
fi

REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL=${INSTALL:-$REPO/local/engines/sdk-4.1.0}
WORK=${WORK:-$REPO/local/evaluation/$CARD}
MANIFEST="$REPO/evaluation/$CARD/manifest.json"
if [[ ! -f $INSTALL/install-manifest.json || ! -f $MANIFEST ]]; then
    echo "missing persistent engine installation or run card" >&2
    exit 2
fi
INSTALL=$(cd "$INSTALL" && pwd)
ARCHIVE=$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")
if [[ -n $GAMES_FILE ]]; then
    GAMES_FILE=$(cd "$(dirname "$GAMES_FILE")" && pwd)/$(basename "$GAMES_FILE")
fi
if [[ -n $(git -C "$REPO" status --porcelain) ]]; then
    echo "REFUSED: diagnostic games run only from a clean, committed tree" >&2
    exit 2
fi
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/build_t9_diagnostic_card.py" --check --card "$CARD"
mkdir -p "$WORK/games" "$WORK/capture" "$WORK/started" "$WORK/logs" "$WORK/cwd/a/b"
WORK=$(cd "$WORK" && pwd)

card_check() {
    PYTHONNOUSERSITE=1 PYTHONPATH="$REPO/src" "$PYTHON" - "$MANIFEST" "$1" \
        "$INSTALL/usage-ledger.jsonl" "$WORK" "$GAMES_FILE" <<'PY'
import importlib.util, json, sys
from pathlib import Path
from miaosuan_agent.evaluation import execution as ex
from miaosuan_agent.evaluation import exploratory as xp
spec = importlib.util.spec_from_file_location("rev", Path(sys.argv[1]).parents[2] / "scripts" / "run_evaluation.py")
rev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rev)
card = json.load(open(sys.argv[1], encoding="utf-8"))
point, ledger, work, games_file = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
for policy, entry in sorted(card["policies"].items()):
    actual = rev.registered_source_digest(entry["policy_source"])
    if actual != entry["policy_source"]["sha256"]:
        sys.exit(f"REFUSED at {point}: source of {policy} differs ({actual})")
ids = [g["game_id"] for g in card["games"]]
if games_file:
    wanted = [line.strip() for line in open(games_file, encoding="utf-8") if line.strip()]
    if set(wanted) - set(ids) or len(set(wanted)) != len(wanted):
        sys.exit("REFUSED: games file contains an unknown or repeated id")
    ids = [game for game in ids if game in set(wanted)]
if point == "start":
    pending = [game for game in ids if not (work / "games" / f"{game}.json").exists()]
    problem = xp.budget_problem(card, ledger, len(pending))
    if problem:
        sys.exit(f"REFUSED: {problem}")
    print(f"session budget: {xp.sessions_after(ledger, card['budget']['ledger_base_session'])} used; "
          f"{len(pending)} pending; cap {card['budget']['sprint_session_cap']}", file=sys.stderr)
    runtime = ex.registered(card)["runtime"]
    print(f"RUNTIME {runtime}")
    for name, value in sorted(ex.runtime_env(runtime).items()):
        print(f"ENV {name}={value}")
    for game in ids:
        print(f"GAME {game}")
PY
}

mapfile -t PLAN < <(card_check start)
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
    echo "REFUSED: card check returned no runtime or games" >&2
    exit 2
fi

archive_sha_before=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
PYTHONNOUSERSITE=1 "$PYTHON" "$REPO/scripts/run_evaluation.py" --evaluation "$CARD" --manifest "$MANIFEST" \
    --work "$WORK" stage --sdk-archive "$ARCHIVE" > "$WORK/logs/stage.log"
COMMIT=$(git -C "$REPO" rev-parse HEAD)
echo "card $CARD: ${#GAMES[@]} games, harness $COMMIT, runtime $RUNTIME"

for id in "${GAMES[@]}"; do
    if [[ -f $WORK/games/$id.json ]]; then
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
        cd "$WORK/cwd/a/b"
        env -i HOME="$INSTALL/home" PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin LANG=C.UTF-8 \
            PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES= \
            PYTHONPATH="$INSTALL/site:$REPO/src" "${THREAD_ENV[@]}" \
            timeout --signal=TERM --kill-after=30 "$TIMEOUT_SECONDS" \
            "$PYTHON" "$REPO/scripts/run_t9_diagnostic_game.py" --card "$CARD" --work "$WORK" game \
                --game-id "$id" --engine-install "$INSTALL" --harness-commit "$COMMIT" \
            > "$WORK/logs/$id.log" 2>&1
    )
    status=$?
    set -e
    tail -n 1 "$WORK/logs/$id.log"
    if [[ $status -ne 0 ]]; then
        echo "STOP: game $id exited with status $status" >&2
        exit "$status"
    fi
done

card_check end > /dev/null
archive_sha_after=$(sha256sum "$ARCHIVE" | cut -d' ' -f1)
if [[ $archive_sha_before != "$archive_sha_after" ]]; then
    echo "SDK archive digest changed during the run" >&2
    exit 1
fi
echo "card $CARD finished: ${#GAMES[@]} games"
