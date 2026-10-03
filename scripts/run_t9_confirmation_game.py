"""Play one scheduled game of the registered T9 confirmatory study (``docs/T9_CONFIRMATION.md``).

    python scripts/run_t9_confirmation_game.py --evaluation t9-confirmation-1 --work DIR game --game-id ID
        --engine-install DIR --harness-commit SHA [--harness-dirty] --purpose evaluation --session-mode shared
        --workers N --worker W --batch B --scheduler ID --runtime RUNTIME

Started only by ``scripts/run_game_pool.py`` (the qualified scheduler, unchanged) through
``scripts/run_t9_confirmation.py``, with the pool's isolation: an empty environment, the persistent installation on
PYTHONPATH and its ``home/`` as HOME, the runtime's numerical-thread variables. The command line is the pool's own
game command line, so the pool is reused without any change. The registered evaluator, ``scripts/run_evaluation.py``
and ``.sh``, stays byte-identical (earlier registrations pin it); its helpers and the game loop
(``evaluation.game.play``) are reused by import, unchanged.

Before the engine is touched the game is refused (exit 2) when: the manifest is not the study's; the tree is dirty;
the record or a capture exists; a pinned implementation file differs from its registered digest; a policy's source
digest differs; the game's phase is not authorised by the committed gate of the previous phase; the sessions the
study has opened would exceed its cap; the session is not the registered shared mode, worker count, scheduler or
runtime; or the inputs do not match the manifest's digests. The game plays with two read-only observers, the
study's mechanism capture and the exploratory capture of Sprint 8 (unchanged), whose counts the analysis cross-checks.

Exit status: 0 the game completed, 1 it failed or hit a cap, 2 invalid input before the engine was touched, 4 an
installation guardrail refused the session.
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
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.experiments.t9_allocation import CANDIDATE_ID as T9_ID, AllocationAgent  # noqa: E402


def evaluator() -> Any:
    """The registered evaluator module, loaded unchanged for its helpers."""
    spec = importlib.util.spec_from_file_location("run_evaluation", REPO_ROOT / "scripts" / "run_evaluation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REV = evaluator()
FACTORIES = {**REV.FACTORIES, T9_ID: lambda: AllocationAgent()}


def refuse(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def phase_authorised(manifest: Dict[str, Any], phase: str) -> str:
    """Why ``phase`` may not run, or ''. Phase A needs nothing; a later phase needs the committed gate file of the
    previous phase to say CONTINUE and to permit it (the runner also regenerates that file from the records)."""
    index = tc.PHASE_ORDER.index(phase)
    if index == 0:
        return ""
    previous = tc.PHASE_ORDER[index - 1]
    path = REPO_ROOT / "evaluation" / tc.STUDY_ID / f"phase-{previous}.json"
    if not path.exists():
        return f"phase {phase} needs the committed gate of phase {previous}"
    gate = json.loads(path.read_text(encoding="utf-8")).get("gate") or {}
    if gate.get("decision") != "CONTINUE" or gate.get("permits") != phase:
        return f"the gate of phase {previous} does not permit phase {phase}"
    return ""


def pinned_problems(manifest: Dict[str, Any]) -> list:
    return [rel for rel, digest in sorted({**manifest["files"], **manifest["tests"]}.items())
            if not (REPO_ROOT / rel).exists() or tc.normalized_sha256(REPO_ROOT / rel) != digest]


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, REV._terminate)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not tc.is_study(manifest):
        return refuse("the manifest is not the T9 confirmatory study's")
    if args.harness_dirty:
        return refuse("a registered game runs only from a clean, committed tree")
    entry = {g["game_id"]: g for g in manifest["games"]}.get(args.game_id)
    if entry is None:
        return refuse(f"unknown game id {args.game_id}")
    spec = {s.game_id: s for s in tc.scheduled_games(manifest)}[args.game_id]
    execution = manifest["execution"]
    if (args.session_mode != "shared" or args.workers != execution["workers"] or args.scheduler != execution["scheduler"]
            or args.runtime != execution["runtime"] or args.purpose != "evaluation"):
        return refuse("the session is not the registered shared session (purpose, workers, scheduler, runtime)")
    out = args.work / "games" / f"{spec.game_id}.json"
    captures = (args.work / "capture" / f"{spec.game_id}.t9.json", args.work / "capture" / f"{spec.game_id}.explore.json",
                args.work / "capture" / f"{spec.game_id}.series.json.gz")
    if out.exists():
        return refuse(f"{out} exists; records are never overwritten")
    if any(path.exists() for path in captures):
        return refuse(f"capture files of {spec.game_id} exist; captures are never overwritten")
    pinned = pinned_problems(manifest)
    if pinned:
        return refuse(f"pinned files differ from the registration: {pinned}")
    sources: Dict[str, str] = {}
    for policy in tc.game_policies(spec):
        registered = manifest["policies"][policy]["policy_source"]
        sources[policy] = REV.registered_source_digest(registered)
        if sources[policy] != registered["sha256"]:
            return refuse(f"the policy source of {policy} differs from the registered one")
    problem = phase_authorised(manifest, entry["phase"])
    if problem:
        return refuse(problem)
    install = engine_install.EngineInstall(Path(args.engine_install).resolve())
    used = xp.sessions_after(install.ledger_path, manifest["budget"]["ledger_base_session"])
    if used + 1 > manifest["budget"]["session_cap"]:
        return refuse(f"{used} sessions already opened after session {manifest['budget']['ledger_base_session']}; one "
                      f"more would exceed the study's cap of {manifest['budget']['session_cap']}")
    problem = ex.check_thread_env(os.environ, execution["runtime"])
    if problem:
        return refuse(problem)
    try:
        REV.verify_inputs(manifest, args.work, spec.scenario_id, spec.map_id)
        inputs = sdk_data.load_inputs(REV.data_root(args.work, spec.scenario_id), spec.scenario_id, spec.map_id)
    except (sdk_data.SdkDataError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    randomness.seed_globals(int(manifest["randomness"]["global_seed"]))
    under_test = tc.CANDIDATE_ID if tc.CANDIDATE_ID in sources else tc.V2_ID
    harness = {"commit": args.harness_commit, "dirty": args.harness_dirty, "game_id": spec.game_id,
               "manifest_sha256": mf.digest(manifest), "policy_source_sha256": sources[under_test],
               "policy_sources": dict(sorted(sources.items())), "track": tc.TRACK, "study": tc.STUDY_ID,
               "phase": entry["phase"], "cell": entry["cell"], "runtime": execution["runtime"],
               "thread_env": ex.runtime_env(execution["runtime"]),
               "execution": {"mode": "shared", "workers": args.workers, "worker": args.worker, "batch": args.batch,
                             "scheduler": args.scheduler},
               "capture": {"schema": tc.CAPTURE_SCHEMA, "cross_check": xp.CAPTURE_SCHEMA}}
    construct = REV.engine_factory(install)
    mechanism = tc.T9Capture()
    explore = xp.ExploreCapture(tuple(tc.game_policies(spec)))
    try:
        with engine_install.shared_session(install, "evaluation", harness, str(args.worker)) as handle:
            record = play(construct, FACTORIES, spec, inputs, manifest["players"], rng_probe=randomness.fingerprint,
                          replay_policies=set(tc.game_policies(spec)), observer=tc.Tee(mechanism, explore))
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    files = [mechanism.file(), *explore.files()]
    captures[0].parent.mkdir(parents=True, exist_ok=True)
    for path, data in zip(captures, files):
        with open(path, "xb") as handle:
            handle.write(data)
    record["capture"] = {"schema": tc.CAPTURE_SCHEMA, "steps": mechanism.steps,
                         "t9_sha256": hashlib.sha256(files[0]).hexdigest(),
                         "explore_sha256": hashlib.sha256(files[1]).hexdigest(),
                         "series_sha256": hashlib.sha256(files[2]).hexdigest(),
                         "explore_observer_seconds": explore.seconds}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    seats = " ".join(f"{s['policy']}:{sum(s['actions_by_type'].values())}" for s in record.get("seats", []))
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} session={record.get('session')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s actions={seats}", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluation", required=True)
    parser.add_argument("--work", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", default="unknown")
    game.add_argument("--harness-dirty", action="store_true")
    game.add_argument("--purpose", default="evaluation", choices=("evaluation", "diagnostic"))
    game.add_argument("--session-mode", default="exclusive", choices=("exclusive", "shared"))
    game.add_argument("--workers", type=int)
    game.add_argument("--worker", type=int)
    game.add_argument("--batch", type=int)
    game.add_argument("--scheduler")
    game.add_argument("--runtime")
    game.set_defaults(func=cmd_game)
    args = parser.parse_args()
    if args.evaluation != tc.STUDY_ID:
        print(f"REFUSED: this entry point plays only {tc.STUDY_ID}", file=sys.stderr)
        return 2
    args.manifest = REPO_ROOT / "evaluation" / args.evaluation / "manifest.json"
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
