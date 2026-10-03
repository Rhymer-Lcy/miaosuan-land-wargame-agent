"""Run one game from Sprint 10's frozen T9-v1 full-capture diagnostic card."""

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
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.evaluation.t9_diagnostic import CAPTURE_SCHEMA, T9DiagnosticCapture  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import CANDIDATE_ID as T9_ID, AllocationAgent  # noqa: E402


def evaluator() -> Any:
    spec = importlib.util.spec_from_file_location("run_evaluation", REPO_ROOT / "scripts" / "run_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = evaluator()
FACTORIES = {**REV.FACTORIES, T9_ID: lambda: AllocationAgent()}


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    card = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    if not xp.is_card(card):
        return refuse("manifest is not an exploratory run card")
    if args.harness_dirty:
        return refuse("diagnostic games run only from a clean, committed tree")
    spec = {s.game_id: s for s in xp.scheduled_games(card)}.get(args.game_id)
    if spec is None:
        return refuse(f"unknown game id {args.game_id}")
    out = args.work / "games" / f"{spec.game_id}.json"
    captures = (args.work / "capture" / f"{spec.game_id}.diagnostic.json",
                args.work / "capture" / f"{spec.game_id}.windows.pkl")
    if out.exists() or any(path.exists() for path in captures):
        return refuse(f"record or capture of {spec.game_id} exists; diagnostic evidence is never overwritten")
    sources: Dict[str, str] = {}
    for policy in xp.game_policies(spec):
        pinned = card["policies"][policy]["policy_source"]
        sources[policy] = REV.registered_source_digest(pinned)
        if sources[policy] != pinned["sha256"]:
            return refuse(f"policy source of {policy} differs from the run card")
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
               "manifest_sha256": mf.digest(card), "policy_sources": dict(sorted(sources.items())),
               "track": xp.TRACK, "card": card["card_id"], "capture": {"schema": CAPTURE_SCHEMA, "sample_every": 1},
               "runtime": runtime, "thread_env": ex.runtime_env(runtime)}
    construct = REV.engine_factory(install)
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")
    observer = T9DiagnosticCapture((INERT_ID, spec.red, spec.blue), costs)
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
    compact, windows = observer.files()
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, (compact, windows)):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = observer.summary(compact, windows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} session={record.get('session')} "
          f"consistency_errors={record['capture']['consistency_errors']} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" and not observer.consistency_errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True)
    parser.add_argument("--work", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", required=True)
    game.add_argument("--harness-dirty", action="store_true")
    game.set_defaults(func=cmd_game)
    args = parser.parse_args()
    args.manifest = REPO_ROOT / "evaluation" / args.card / "manifest.json"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
