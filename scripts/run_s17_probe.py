"""Play the two games of the Sprint 17 probe card, one at a time (``docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md``).

    python scripts/run_s17_probe.py --python PYTHON --sdk-archive ZIP [--engine-install DIR] [--work DIR]

Before the first game: not root; a clean, committed tree with no untracked file outside the ignored tree; the card
committed and byte-identical to a fresh build; the card's pins (frozen files, rules, schedule, policy identities,
budget) equal to this checkout; the private prefix reference present with the digest ``inputs.json`` pins; the ledger
audited (every session after 2793 a game of this card in schedule order, none unclosed); the inputs staged and checked.
Then, for each game in card order: the ledger-counted ceiling (2 sessions after 2793) is checked, the game is played by
``scripts/run_s17_game.py`` in the registered evaluator's isolation (``run_s12_stage.isolated_env``, a hard timeout),
and before the next game starts the game's structural stops are checked: S1, S4, S6, S7 and the prefix check SP from
its record and captures, S1 and S2 from the ledger audit, and S3 (a file outside the ignored tree that appeared during
the game). Any non-zero game status or any structural stop ends the study at once. A game that was started earlier and
left no record stops the study; no game is retried or replaced. No mechanism endpoint is evaluated between games: the
second game never depends on the first game's tactical result.

Exit status: 0 both games completed without a structural stop; 3 a structural stop; 1 a game did not complete;
2 refused before any game.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import s17_probe as sp  # noqa: E402

TIMEOUT_SECONDS = 2100


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def git_dirty(repo: Path) -> bool:
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
                            capture_output=True, text=True, check=True)
    return bool(status.stdout.strip())


def outside_ignored(repo: Path) -> List[str]:
    """Untracked files outside the ignored tree (S3: evidence must stay under the ignored ``local/``)."""
    status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
                            capture_output=True, text=True, check=True)
    return sorted(line[3:] for line in status.stdout.splitlines() if line.startswith("??"))


def read_ledger(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def launch_subprocess(args: argparse.Namespace, card: Dict[str, Any], game_id: str, commit: str) -> int:
    stage = load("run_s12_stage")  # the registered evaluator's isolated game environment, reused unchanged
    cwd = args.work / "cwd" / "a" / "b"
    cwd.mkdir(parents=True, exist_ok=True)
    log = args.work / "logs" / f"{game_id}.log"
    command = ["timeout", "--signal=TERM", "--kill-after=30", str(TIMEOUT_SECONDS), args.python,
               str(REPO_ROOT / "scripts" / "run_s17_game.py"), "--work", str(args.work), "game", "--game-id",
               game_id, "--engine-install", str(args.engine_install), "--harness-commit", commit]
    with log.open("w", encoding="utf-8") as handle:
        status = subprocess.run(command, cwd=cwd, env=stage.isolated_env(args.engine_install, REPO_ROOT,
                                                                          ex.registered(card)["runtime"]),
                                stdout=handle, stderr=subprocess.STDOUT).returncode
    for line in log.read_text(encoding="utf-8").strip().splitlines()[-8:] or ["(no output)"]:
        print(line)
    return status


def run_probe(args: argparse.Namespace, launch: Callable[..., int] = launch_subprocess,
              stage_inputs: bool = True) -> int:
    """The runner. ``launch`` plays one game and returns its exit status (a stand-in rehearsal passes another)."""
    cards = load("build_s17_card")
    game = load("run_s17_game")
    if hasattr(os, "getuid") and os.getuid() == 0:
        return refuse("the engine never runs as root")
    if git_dirty(REPO_ROOT):
        return refuse("probe games run only from a clean, committed tree")
    untracked = outside_ignored(REPO_ROOT)
    if untracked:
        return refuse(f"untracked files outside the ignored tree before the first game: {untracked[:5]}")
    if not cards.CARD.exists():
        return refuse(f"no committed card {sp.CARD_ID}")
    if sp.dump(cards.build()) != cards.CARD.read_text(encoding="utf-8"):
        return refuse(f"{sp.CARD_ID} does not rebuild byte-identically")
    card = json.loads(cards.CARD.read_text(encoding="utf-8"))
    problems = sp.card_problems(card, REPO_ROOT)
    if problems:
        return refuse("; ".join(problems))
    if game.prefix_reference() is None:
        return refuse("the private prefix reference is missing or not the digest pinned in inputs.json")
    ledger = args.engine_install / "usage-ledger.jsonl"
    audit = sp.ledger_audit(read_ledger(ledger), card)
    if not audit["ok"]:
        return refuse(f"the ledger audit fails before the first game: {audit['problems']}")
    args.work.mkdir(parents=True, exist_ok=True)
    for sub in ("games", "started", "logs", "capture"):
        (args.work / sub).mkdir(exist_ok=True)
    if stage_inputs:
        subprocess.run([args.python, str(REPO_ROOT / "scripts" / "run_evaluation.py"), "--evaluation", sp.CARD_ID,
                        "--manifest", str(cards.CARD), "--work", str(args.work), "stage", "--sdk-archive",
                        str(args.sdk_archive)], check=True, capture_output=True)
    archive_before = sha256(args.sdk_archive) if stage_inputs else None
    commit = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True,
                            check=True).stdout.strip()
    for entry in card["games"]:
        game_id = entry["game_id"]
        if (args.work / "games" / f"{game_id}.json").exists():
            print(f"recorded already: {game_id}")
            continue
        if (args.work / "started" / game_id).exists():
            print(f"STOP: {game_id} was started earlier and left no record", file=sys.stderr)
            return 3
        problem = xp.budget_problem(card, ledger, 1)
        if problem:
            print(f"STOP: {problem}", file=sys.stderr)
            return 3
        (args.work / "started" / game_id).write_text(commit + "\n", encoding="utf-8")
        status = launch(args, card, game_id, commit)
        stops: Dict[str, List[str]] = {k: list(v) for k, v in game.recorded_stops(card, entry, args.work).items()}
        audit = sp.ledger_audit(read_ledger(ledger), card)
        for code, found in audit["problems"].items():
            stops.setdefault(code, []).extend(found)
        appeared = outside_ignored(REPO_ROOT)
        if appeared:
            stops.setdefault("S3", []).append(f"files outside the ignored tree appeared: {appeared[:5]}")
        if git_dirty(REPO_ROOT):
            stops.setdefault("S3", []).append("a tracked file changed during the game")
        codes = sp.structural_stops(stops)
        print(f"{game_id}: exit {status}, structural stops {codes or 'none'}, ledger sessions after "
              f"{sp.LEDGER_BASE_SESSION}: {audit['sessions']}")
        if codes:
            for code in codes:
                for found in stops[code][:5]:
                    print(f"  {code}: {found}", file=sys.stderr)
            print("STOP: a structural stop fired; the study stops and returns to the owner", file=sys.stderr)
            return 3
        if status != 0:
            print(f"STOP: {game_id} exited with status {status}", file=sys.stderr)
            return 1 if status == 1 else 3
    if stage_inputs and sha256(args.sdk_archive) != archive_before:
        print("STOP: the SDK archive changed during the study", file=sys.stderr)
        return 3
    problems = sp.card_problems(card, REPO_ROOT)
    if problems:
        print(f"STOP: after the games: {'; '.join(problems)}", file=sys.stderr)
        return 3
    print("both games recorded; run scripts/s17_analysis.py run")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--python", required=True)
    parser.add_argument("--sdk-archive", type=Path, required=True)
    parser.add_argument("--engine-install", type=Path, default=REPO_ROOT / "local" / "engines" / "sdk-4.1.0")
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    args.engine_install = args.engine_install.resolve()
    args.sdk_archive = args.sdk_archive.resolve()
    args.work = (args.work or REPO_ROOT / "local" / "evaluation" / sp.CARD_ID).resolve()
    if not (args.engine_install / "install-manifest.json").exists():
        return refuse(f"no persistent engine installation at {args.engine_install}")
    return run_probe(args)


if __name__ == "__main__":
    sys.exit(main())
