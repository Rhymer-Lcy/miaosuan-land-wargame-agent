"""Play one game of an EXPLORATORY run card (``docs/EXPLORATORY_TRACK.md``) and write its record and capture.

    python scripts/run_explore_game.py --card CARD --work DIR game --game-id ID --engine-install DIR
                                       --harness-commit SHA [--harness-dirty]

Started only by ``scripts/run_explore.sh``, inside the same isolation as the registered evaluator (persistent engine
installation on PYTHONPATH, empty environment, the installation's ``home/`` as HOME). This entry point exists so that
the registered evaluator, ``scripts/run_evaluation.py`` and ``scripts/run_evaluation.sh``, stays byte-identical: their
digests are pinned by earlier registrations. It reuses the evaluator's helpers by import (input verification, policy
source digests, the engine factory) and its game loop (``evaluation.game.play``) unchanged.

Before the engine is touched the game is refused (exit 2) when: the manifest is not a run card; the tree is dirty;
the record or a capture exists; a policy's source digest differs from the card's; the sessions opened after the
card's base session leave no room under the sprint's cap; the numerical-thread environment is not the card's
runtime's; or the inputs do not match the card's digests. The session is always an exclusive, diagnostic session of
the persistent installation's ledger; the record's harness names the track and the card.

Exit status: 0 the game completed, 1 it failed or hit a cap, 2 invalid input before the engine was touched, 4 an
installation guardrail refused the session.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.experiments.t4_artillery import CANDIDATE_ID as T4_ID, ArtilleryAgent  # noqa: E402
from miaosuan_agent.experiments.t4_artillery_v2 import CANDIDATE_ID as T4B_ID, ArtilleryV2Agent  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import CANDIDATE_ID as T9_ID, AllocationAgent  # noqa: E402


def evaluator() -> Any:
    """The registered evaluator module, loaded unchanged for its helpers."""
    spec = importlib.util.spec_from_file_location("run_evaluation", REPO_ROOT / "scripts" / "run_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = evaluator()
FACTORIES = {**REV.FACTORIES, T4_ID: lambda: ArtilleryAgent(), T4B_ID: lambda: ArtilleryV2Agent(),
             T9_ID: lambda: AllocationAgent()}


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    card = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not xp.is_card(card):
        return refuse("the manifest is not an exploratory run card")
    if args.harness_dirty:
        return refuse("an exploratory game runs only from a clean, committed tree")
    spec = {s.game_id: s for s in xp.scheduled_games(card)}.get(args.game_id)
    if spec is None:
        return refuse(f"unknown game id {args.game_id}")
    out = args.work / "games" / f"{spec.game_id}.json"
    captures = (args.work / "capture" / f"{spec.game_id}.explore.json",
                args.work / "capture" / f"{spec.game_id}.series.json.gz")
    if out.exists():
        return refuse(f"{out} exists; records are never overwritten")
    if any(path.exists() for path in captures):
        return refuse(f"capture files of {spec.game_id} exist; captures are never overwritten")
    sources: Dict[str, str] = {}
    for policy in xp.game_policies(spec):
        pinned = card["policies"][policy]["policy_source"]
        sources[policy] = REV.registered_source_digest(pinned)
        if sources[policy] != pinned["sha256"]:
            return refuse(f"the policy source of {policy} differs from the registered one; a changed candidate needs a "
                          "new identity and a new run card")
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
    policy_under_test = card["candidate"] if card["candidate"] in sources else sorted(sources)[0]
    harness = {"commit": args.harness_commit, "dirty": args.harness_dirty, "game_id": spec.game_id,
               "manifest_sha256": mf.digest(card), "policy_source_sha256": sources[policy_under_test],
               "policy_sources": dict(sorted(sources.items())), "track": xp.TRACK, "card": card["card_id"],
               "capture": {"schema": xp.CAPTURE_SCHEMA}}
    if runtime != ex.DEFAULT_RUNTIME:
        harness["runtime"] = runtime
        harness["thread_env"] = ex.runtime_env(runtime)
    construct = REV.engine_factory(install)
    observer = xp.ExploreCapture(tuple(xp.game_policies(spec)))
    try:
        with engine_install.session(install, "diagnostic", harness) as handle:
            record = play(construct, FACTORIES, spec, inputs, card["players"], rng_probe=randomness.fingerprint,
                          replay_policies=set(xp.game_policies(spec)), observer=observer)
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    compact, series = observer.files()
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, (compact, series)):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = observer.summary(compact, series)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    seats = " ".join(f"{s['policy']}:{sum(s['actions_by_type'].values())}" for s in record.get("seats", []))
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} session={record.get('session')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s actions={seats}", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", required=True, help="the run card: evaluation/CARD/manifest.json")
    parser.add_argument("--work", type=Path, help="work directory (default local/evaluation/CARD)")
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", default="unknown")
    game.add_argument("--harness-dirty", action="store_true")
    game.set_defaults(func=cmd_game)
    args = parser.parse_args()
    args.manifest = REPO_ROOT / "evaluation" / args.card / "manifest.json"
    args.work = args.work or REPO_ROOT / "local" / "evaluation" / args.card
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
