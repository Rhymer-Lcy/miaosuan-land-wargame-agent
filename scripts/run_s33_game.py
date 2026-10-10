"""Play one game of the Sprint 33 mechanism-check card (``docs/SPRINT33_T7_B1_LIVE.md``).

    python scripts/run_s33_game.py [--work DIR] game --game-id ID --engine-install DIR --harness-commit SHA

Started only by ``scripts/run_s33_pilot.py``, inside the registered evaluator's isolation (empty environment, the
persistent installation on PYTHONPATH and its ``home/`` as HOME, the runtime's thread variables). The registered
evaluator and every earlier entry point stay byte-identical; their helpers, the game loop and the exploratory capture
are reused by import (Sprint 31's runner, ``scripts/run_s31_game.py``, with the Sprint 33 card, candidate and observer).

Before the engine is touched the game is refused (exit 2) when: the manifest is not the Sprint 33 card or does not
rebuild byte-identically; a frozen implementation file, the rules, the schedule, the committed controls or preflight,
or a policy identity differ from the card's pins; the candidate's policy source is not the registered digest; the tree
is dirty; the record or a capture exists; the sessions opened after 2800 are not exactly the games before this one in
schedule order; the thread environment is not the runtime's; or the inputs do not match. The session is always an
exclusive diagnostic session.

The game plays under two read-only observers: the exploratory capture, unchanged, and the Sprint 33 full-step timeline,
which re-decides the candidate seat from its own observation and memory at every decision, checks the memory chains,
checks that every live action list is ``baseline-v2``'s followed by exactly the rule's documented stops, and runs the
independent check. Afterwards the structural stops S1, S4, S6 and S7 are evaluated from the record and captures; any of
them makes the exit status 3.

Exit status: 0 completed without a structural stop, 1 the game did not complete, 2 refused before the engine was
touched, 3 a structural stop, 4 an installation guardrail refused the session.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation import s33_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s33_pilot as sp  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.experiments.t7_b1_stop_engage import StopEngageAgent  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s33_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = load("run_evaluation")
CARDS = load("build_s33_card")
FACTORIES = {**REV.FACTORIES, sp.CANDIDATE_ID: lambda: StopEngageAgent()}
CAPTURES = ("explore.json", "exploreseries.json.gz", "timeline.json", "timeline.pkl")


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def capture_paths(work: Path, game_id: str) -> List[Path]:
    return [work / "capture" / f"{game_id}.{suffix}" for suffix in CAPTURES]


def card_refusal(card: Dict[str, Any], repo: Path = REPO_ROOT) -> str:
    """Why this card may not be played from this checkout, or ''."""
    problems = sp.card_problems(card, repo)
    if problems:
        return "; ".join(problems)
    if sp.dump(CARDS.build(repo)) != CARDS.CARD.read_text(encoding="utf-8"):
        return "the card does not rebuild byte-identically"
    return ""


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    card = json.loads(CARDS.CARD.read_text(encoding="utf-8"))
    if not xp.is_card(card) or card.get("card_id") != sp.CARD_ID:
        return refuse("the manifest is not the Sprint 33 card")
    if args.harness_dirty:
        return refuse("a mechanism-check game runs only from a clean, committed tree")
    problem = card_refusal(card)
    if problem:
        return refuse(problem)
    spec = {s.game_id: s for s in xp.scheduled_games(card)}.get(args.game_id)
    entry = next((g for g in card["games"] if g["game_id"] == args.game_id), None)
    if spec is None or entry is None:
        return refuse(f"unknown game id {args.game_id}")
    position = int(entry["screen_position"])
    out = args.work / "games" / f"{spec.game_id}.json"
    captures = capture_paths(args.work, spec.game_id)
    if out.exists() or any(path.exists() for path in captures):
        return refuse(f"the record or a capture of {spec.game_id} exists; evidence is never overwritten")
    sources: Dict[str, str] = {}
    for policy in xp.game_policies(spec):
        pinned = card["policies"][policy]["policy_source"]
        sources[policy] = REV.registered_source_digest(pinned)
        if sources[policy] != pinned["sha256"]:
            return refuse(f"the policy source of {policy} differs from the card")
    if sources.get(sp.CANDIDATE_ID) != sp.CANDIDATE_DIGEST:
        return refuse("the candidate's policy source is not the registered digest")
    install = engine_install.EngineInstall(Path(args.engine_install).resolve())
    problem = xp.budget_problem(card, install.ledger_path, 1)
    if problem:
        return refuse(problem)
    used = xp.sessions_after(install.ledger_path, sp.LEDGER_BASE_SESSION)
    if used != position - 1:
        return refuse(f"{used} sessions after {sp.LEDGER_BASE_SESSION}; this game (position {position}) must open "
                      f"session {sp.LEDGER_BASE_SESSION + position}")
    runtime = ex.registered(card)["runtime"]
    problem = ex.check_thread_env(os.environ, runtime)
    if problem:
        return refuse(problem)
    try:
        REV.verify_inputs(card, args.work, spec.scenario_id, spec.map_id)
        inputs = sdk_data.load_inputs(REV.data_root(args.work, spec.scenario_id), spec.scenario_id, spec.map_id)
    except (sdk_data.SdkDataError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    randomness.seed_globals(int(card["randomness"]["global_seed"]))
    harness = {"commit": args.harness_commit, "dirty": False, "game_id": spec.game_id,
               "manifest_sha256": mf.digest(card), "policy_source_sha256": sources[sp.CANDIDATE_ID],
               "policy_sources": dict(sorted(sources.items())), "track": xp.TRACK, "card": card["card_id"],
               "screen": sp.STUDY_ID, "position": position, "rules_sha256": sp.rules_digest(), "runtime": runtime,
               "thread_env": ex.runtime_env(runtime),
               "capture": {"explore": xp.CAPTURE_SCHEMA, "timeline": cap.TIMELINE_SCHEMA, "sample_every": 1}}
    construct = REV.engine_factory(install)
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    policies = tuple(xp.game_policies(spec))
    explore = xp.ExploreCapture(policies)
    timeline = cap.StopTimeline(policies, costs)
    try:
        with engine_install.session(install, "diagnostic", harness) as handle:
            record = play(construct, FACTORIES, spec, inputs, card["players"], rng_probe=randomness.fingerprint,
                          replay_policies=set(policies), observer=tc.Tee(explore, timeline))
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    timeline_compact, windows = timeline.files()
    files = [*explore.files(), timeline_compact, windows]
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, files):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = {name: hashlib.sha256(data).hexdigest() for name, data in zip(CAPTURES, files)}
    record["capture"]["observer_seconds"] = {"explore": explore.seconds, "timeline": timeline.seconds}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    analysis = load("s33_analysis")
    stops = analysis.structural(entry, record, files, pickle.loads(windows))
    codes = sp.structural_stops(stops)
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} session={record.get('session')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s structural_stops={codes or 'none'}",
          file=sys.__stdout__)
    for code in codes:
        for problem in stops[code][:5]:
            print(f"  {code}: {problem}", file=sys.__stdout__)
    if record["status"] != "COMPLETED":
        return 1
    return 3 if codes else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", required=True)
    game.add_argument("--harness-dirty", action="store_true")
    game.set_defaults(func=cmd_game)
    args = parser.parse_args()
    args.work = args.work or REPO_ROOT / "local" / "evaluation" / sp.CARD_ID
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
