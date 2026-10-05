"""Play one game of a Sprint 12 stage card (``docs/SPRINT12_V3_SCREEN.md``) and write its record and captures.

    python scripts/run_s12_game.py --card CARD --work DIR game --game-id ID --engine-install DIR --harness-commit SHA

Started only by ``scripts/run_s12_stage.py``, inside the registered evaluator's isolation (empty environment, the
persistent installation on PYTHONPATH and its ``home/`` as HOME, the runtime's thread variables). The registered
evaluator and the exploratory runner stay byte-identical; their helpers and the game loop are reused by import.

Before the engine is touched the game is refused (exit 2) when: the card is not a Sprint 12 stage card or does not
rebuild byte-identically from the committed reports; a frozen implementation file, the rules or a policy identity
differ from the card's pins; the card's prerequisite report is missing or not the pinned file; the tree is dirty;
the record or a capture exists; the sessions opened after 2786 leave no room under the ceiling of 12; the thread
environment is not the runtime's; or the inputs do not match. The session is always an exclusive diagnostic session.

The game plays under three read-only observers (Sprint 9's ``T9Capture`` unchanged, the compact v3 capture and the
full-step private timeline). Afterwards the game's own immediate stops (S4 to S13) are checked from the record and
the captures; any of them makes the exit status 3.

Exit status: 0 completed without a stop, 1 the game did not complete, 2 refused before the engine was touched,
3 an immediate stop, 4 an installation guardrail refused the session.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation import s12_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.experiments.t9_batch import BatchAgent  # noqa: E402


def load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = load("run_evaluation")
CARDS = load("build_s12_card")
ANALYSIS = load("s12_screen_analysis")
FACTORIES = {**REV.FACTORIES, sc.V3_ID: lambda: BatchAgent()}
CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def capture_paths(work: Path, game_id: str) -> List[Path]:
    return [work / "capture" / f"{game_id}.{suffix}" for suffix in CAPTURES]


def card_refusal(card: Dict[str, Any], card_id: str) -> str:
    """Why this card may not be played from this checkout, or ''."""
    problems = sc.card_problems(card, REPO_ROOT)
    if problems:
        return "; ".join(problems)
    try:
        fresh = CARDS.build_stage(sc.STAGE_OF_CARD[card_id])
    except sc.NotPermitted as exc:
        return f"the committed reports do not permit this card: {exc}"
    if sc.dump(fresh) != (REPO_ROOT / "evaluation" / card_id / "manifest.json").read_text(encoding="utf-8"):
        return "the card does not rebuild byte-identically from the committed reports"
    return ""


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    card = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not xp.is_card(card) or card.get("card_id") != args.card:
        return refuse("the manifest is not this Sprint 12 stage card")
    if args.harness_dirty:
        return refuse("a screen game runs only from a clean, committed tree")
    problem = card_refusal(card, args.card)
    if problem:
        return refuse(problem)
    spec = {s.game_id: s for s in xp.scheduled_games(card)}.get(args.game_id)
    if spec is None:
        return refuse(f"unknown game id {args.game_id}")
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
    install = engine_install.EngineInstall(Path(args.engine_install).resolve())
    problem = xp.budget_problem(card, install.ledger_path, 1)
    if problem:
        return refuse(problem)
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
               "manifest_sha256": mf.digest(card), "policy_source_sha256": sources[sc.V3_ID],
               "policy_sources": dict(sorted(sources.items())), "track": xp.TRACK, "card": card["card_id"],
               "screen": sc.SCREEN_ID, "stage": card["screen"]["stage"], "rules_sha256": sc.rules_digest(),
               "runtime": runtime, "thread_env": ex.runtime_env(runtime),
               "capture": {"t9": tc.CAPTURE_SCHEMA, "v3": cap.COMPACT_SCHEMA, "timeline": cap.TIMELINE_SCHEMA,
                           "sample_every": 1}}
    construct = REV.engine_factory(install)
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    t9 = tc.T9Capture()
    compact = cap.V3CompactCapture(tuple(xp.game_policies(spec)))
    timeline = cap.V3Timeline((INERT_ID, spec.red, spec.blue), costs)
    try:
        with engine_install.session(install, "diagnostic", harness) as handle:
            record = play(construct, FACTORIES, spec, inputs, card["players"], rng_probe=randomness.fingerprint,
                          replay_policies=set(xp.game_policies(spec)), observer=tc.Tee(t9, compact, timeline))
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    timeline_compact, windows = timeline.files()
    files = [t9.file(), *compact.files(), timeline_compact, windows]
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, files):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = {name: hashlib.sha256(data).hexdigest() for name, data in zip(CAPTURES, files)}
    record["capture"]["observer_seconds"] = {"v3": compact.seconds, "timeline": timeline.seconds}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    entry = next(g for g in card["games"] if g["game_id"] == spec.game_id)
    facts = tl.analyze(entry, card["card_id"], record, json.loads(files[0]), json.loads(files[1]),
                       json.loads(timeline_compact), timeline.windows(), costs,
                       capture_digests={name: (record["capture"][name], hashlib.sha256(data).hexdigest())
                                        for name, data in zip(CAPTURES, files)},
                       extra_known=ANALYSIS.baseline_classes(entry["screen_position"], REPO_ROOT))
    codes = sc.stop_codes(facts)
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} session={record.get('session')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s stops={codes or 'none'}", file=sys.__stdout__)
    if record["status"] != "COMPLETED":
        return 1
    return 3 if codes else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", required=True, choices=sorted(sc.STAGE_OF_CARD))
    parser.add_argument("--work", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", required=True)
    game.add_argument("--harness-dirty", action="store_true")
    game.set_defaults(func=cmd_game)
    args = parser.parse_args()
    args.manifest = REPO_ROOT / "evaluation" / args.card / "manifest.json"
    args.work = args.work or REPO_ROOT / "local" / "evaluation" / args.card
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
