"""Play one game of the Sprint 27 probe card (``docs/SPRINT27_T6S_PROBE.md``).

    python scripts/run_s27_game.py [--work DIR] game --game-id ID --engine-install DIR --harness-commit SHA

Started only by ``scripts/run_s27_probe.py``, inside the registered evaluator's isolation (empty environment, the
persistent installation on PYTHONPATH and its ``home/`` as HOME, the runtime's thread variables). The registered
evaluator, the exploratory runner and every earlier entry point stay byte-identical; their helpers, the game loop and
the observers are reused by import.

Before the engine is touched the game is refused (exit 2) when: the manifest is not the Sprint 27 card or does not
rebuild byte-identically; a frozen implementation file, the rules, the schedule or a policy identity differ from the
card's pins; the candidate's policy source is not the registered digest; the tree is dirty; the record or a capture
exists; the sessions opened after 2796 are not exactly the games before this one in schedule order (the session this
game opens must be 2796 + its position); the thread environment is not the runtime's; the inputs do not match; or, for
the stage B game, the committed stage-A game file is missing or does not authorize stage B. The session is always an
exclusive diagnostic session.

The game plays under three read-only observers: Sprint 9's ``T9Capture`` and the exploratory capture, both unchanged,
and the Sprint 27 full-step timeline, which re-decides both seats from their own observations and memories at every
decision, checks the memory chains and checks that every difference from ``baseline-v2`` is the rule's registered
withholding. Afterwards the game's structural stops S1, S4, S6 and S7 are evaluated from the record and captures
(``s27_probe.game_stops``); any of them makes the exit status 3. No endpoint is evaluated here.

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
import subprocess
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
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s27_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s27_probe as sp  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.experiments.t6s_column_stagger_p1 import StaggerAgent  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = load("run_evaluation")
CARDS = load("build_s27_card")
FACTORIES = {**REV.FACTORIES, sp.CANDIDATE_ID: lambda: StaggerAgent()}
CAPTURES = ("t9.json", "explore.json", "exploreseries.json.gz", "timeline.json", "timeline.pkl")


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def capture_paths(work: Path, game_id: str) -> List[Path]:
    return [work / "capture" / f"{game_id}.{suffix}" for suffix in CAPTURES]


def card_refusal(card: Dict[str, Any]) -> str:
    """Why this card may not be played from this checkout, or ''."""
    problems = sp.card_problems(card, REPO_ROOT)
    if problems:
        return "; ".join(problems)
    if sp.dump(CARDS.build()) != CARDS.CARD.read_text(encoding="utf-8"):
        return "the card does not rebuild byte-identically"
    return ""


def gate_file(position: int, repo: Path = REPO_ROOT) -> Path:
    return repo / "evaluation" / sp.STUDY_ID / f"game-p{position:02d}.json"


def committed_gate(repo: Path = REPO_ROOT) -> str:
    """Why the committed stage-A game file does not authorize stage B, or ''. The file must be tracked and unchanged
    in the checkout and say ``stage_b_authorized`` true; the runner also regenerates it from the stage-A capture."""
    path = gate_file(1, repo)
    if not path.exists():
        return "the stage-A game file is missing"
    rel = path.relative_to(repo).as_posix()
    tracked = subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", rel], capture_output=True)
    if tracked.returncode != 0:
        return "the stage-A game file is not committed"
    if subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", rel]).returncode != 0:
        return "the stage-A game file differs from the committed one"
    gate = (json.loads(path.read_text(encoding="utf-8")).get("stage_gate") or {})
    if gate.get("stage_b_authorized") is not True:
        return f"the stage-A game file does not authorize stage B: {gate.get('reasons')}"
    return ""


def game_stops(entry: Dict[str, Any], record: Dict[str, Any], files: List[bytes], windows: Any
               ) -> Dict[str, List[str]]:
    """The structural findings of one game from its record and capture files: S1, S4, S6, S7."""
    digests = {name: (record["capture"][name], hashlib.sha256(data).hexdigest()) for name, data in zip(CAPTURES, files)}
    timeline = json.loads(files[3])
    side = sp.candidate_side(entry)
    faction = 0 if side == "red" else 1
    seat = next(s["seat"] for s in record.get("seats", []) if s["policy"] == sp.CANDIDATE_ID)
    states, _ = tl.load_states(windows, seat, faction)
    max_step = next((s.max_step for s in states if s.max_step is not None), None)
    return sp.game_stops(entry, record, json.loads(files[0]), json.loads(files[1]), timeline, max_step, digests)


def recorded_stops(card: Dict[str, Any], entry: Dict[str, Any], work: Path) -> Dict[str, List[str]]:
    """The same checks from the files a finished game left (the runner's independent reading): a missing record or
    capture, a capture whose digest differs from the record, or a failure to analyse is an S7 finding."""
    record_path = work / "games" / f"{entry['game_id']}.json"
    if not record_path.exists():
        return {"S4": ["no record"]}
    record = json.loads(record_path.read_text(encoding="utf-8"))
    paths = capture_paths(work, entry["game_id"])
    missing = [p.name for p in paths if not p.exists()]
    if missing:
        return {"S7": [f"capture files missing: {missing}"]}
    files = [p.read_bytes() for p in paths]
    try:
        return game_stops(entry, record, files, pickle.loads(files[4]))
    except Exception as exc:  # noqa: BLE001 - an unreadable capture is an observer failure, never a pass
        return {"S7": [f"the game's captures could not be analysed: {type(exc).__name__}: {exc}"[:300]]}


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    card = json.loads(CARDS.CARD.read_text(encoding="utf-8"))
    if not xp.is_card(card) or card.get("card_id") != sp.CARD_ID:
        return refuse("the manifest is not the Sprint 27 card")
    if args.harness_dirty:
        return refuse("a probe game runs only from a clean, committed tree")
    problem = card_refusal(card)
    if problem:
        return refuse(problem)
    spec = {s.game_id: s for s in xp.scheduled_games(card)}.get(args.game_id)
    entry = next((g for g in card["games"] if g["game_id"] == args.game_id), None)
    if spec is None or entry is None:
        return refuse(f"unknown game id {args.game_id}")
    position = int(entry["screen_position"])
    if position == sp.STAGES["B"]:
        problem = committed_gate()
        if problem:
            return refuse(problem)
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
    if sources.get(sp.CANDIDATE_ID) != sp.CANDIDATE_DIGEST or sources.get(sp.V2_ID) != sp.V2_DIGEST:
        return refuse("a policy source is not the registered digest")
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
               "screen": sp.STUDY_ID, "stage": next(k for k, v in sp.STAGES.items() if v == position),
               "rules_sha256": sp.rules_digest(), "runtime": runtime, "thread_env": ex.runtime_env(runtime),
               "capture": {"t9": tc.CAPTURE_SCHEMA, "explore": xp.CAPTURE_SCHEMA, "timeline": cap.TIMELINE_SCHEMA,
                           "sample_every": 1}}
    construct = REV.engine_factory(install)
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    t9 = tc.T9Capture()
    explore = xp.ExploreCapture(tuple(xp.game_policies(spec)))
    timeline = cap.StaggerTimeline((sp.V2_ID, sp.CANDIDATE_ID), costs)
    try:
        with engine_install.session(install, "diagnostic", harness) as handle:
            record = play(construct, FACTORIES, spec, inputs, card["players"], rng_probe=randomness.fingerprint,
                          replay_policies=set(xp.game_policies(spec)), observer=tc.Tee(t9, explore, timeline))
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    timeline_compact, windows = timeline.files()
    files = [t9.file(), *explore.files(), timeline_compact, windows]
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, files):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = {name: hashlib.sha256(data).hexdigest() for name, data in zip(CAPTURES, files)}
    record["capture"]["observer_seconds"] = {"explore": explore.seconds, "timeline": timeline.seconds}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    stops = game_stops(entry, record, files, timeline.windows())
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
