"""Command-line entry points for the registered evaluation.

    stage      copy each registered scenario's inputs out of the verified SDK archive and check them
               against the manifest's digests
    game       play one registered game (one engine session, one process) and write its record
    summarize  derive the gate report, the private summary and the public results from the records

``game`` must run inside the isolation prepared by ``scripts/run_evaluation.sh`` (persistent engine
installation on PYTHONPATH, empty environment). It refuses to play when the policy source differs
from the one recorded in the manifest, so the registered policy cannot change silently; a game of
the variance study also refuses unless that digest is the frozen baseline-v1 digest. The study's
games are its registered schedule; its analysis is ``scripts/analyze_variance_study.py``. A game of
the shoot-reservation experiment checks the registered digest of its own group, and group B's must
be the baseline-v1-runtime-r1 digest; its analysis is ``scripts/analyze_shoot_experiment.py``. A game of
the residual-516 diagnostic must run the frozen baseline-v2 digest and plays with the diagnostic's read-only
observer, whose capture files it writes beside the record (``capture/``); its analysis is
``scripts/residual516_diagnostic.py``. Records
and summaries live under the git-ignored ``local/evaluation/``; only the sanitized public results
file is meant for version control.

Exit status of ``game``: 0 the game completed, 1 it failed or hit a cap, 2 invalid input before the
engine was touched, 4 an installation guardrail refused the session.

``game --session-mode shared`` is how ``scripts/run_game_pool.py`` (``run_evaluation.sh --workers N``)
starts a game: a shared engine session instead of the exclusive one, and the record's harness names the
worker count, the worker, the batch and the scheduler identity. Without it the game, its session and its
record are exactly the serial ones.

Every game runs on a runtime identity (``src/miaosuan_agent/evaluation/execution.py``): the one its manifest
registers, ``baseline-v1-runtime-r1`` by default, or for a diagnostic run the one ``--runtime`` names. The game
refuses to play unless its numerical-thread variables are exactly that runtime's; a game on another runtime than
``baseline-v1-runtime-r1`` records the runtime and its variables in its harness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.agent import PolicyAgent  # noqa: E402
from miaosuan_agent.decision import BASELINE_ID, INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import execution as ex  # noqa: E402
from miaosuan_agent.evaluation import metrics, randomness  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation import variance_study as vs  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.evaluation.identity import POLICY_SOURCES, digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID, ReservationAgent  # noqa: E402
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingAgent  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationAgent  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "evaluation" / "baseline-v0" / "manifest.json"
FACTORIES = {BASELINE_ID: lambda: PolicyAgent(BASELINE_ID), INERT_ID: lambda: PolicyAgent(INERT_ID),
             CANDIDATE_ID: lambda: ReservationAgent(), sx.RUNTIME_R1_CODE_ID: lambda: BoundedRoutingAgent(),
             sx.CANDIDATE_ID: lambda: ShootReservationAgent()}


def registered_source_digest(registered: Dict[str, Any]) -> str:
    """The digest of a registered policy source, recomputed from this checkout.

    The files are the registration's own list; they must also be exactly what its source set yields now,
    so a file added to a covered directory is caught.
    """
    sources = tuple(registered.get("sources", POLICY_SOURCES))
    if policy_source_files(sources=sources) != list(registered["files"]):
        return "file list differs from the registered one"
    return digest_of_files(registered["files"])


def registered_policy_source(manifest: Dict[str, Any]) -> str:
    """The digest of the policy source the manifest registered, recomputed from this checkout."""
    return registered_source_digest(manifest["policy_source"])


def load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_games(manifest: Dict[str, Any]) -> Dict[str, mf.GameSpec]:
    if vs.is_study(manifest):
        return {spec.game_id: spec for spec in vs.scheduled_games(manifest)}
    if sx.is_experiment(manifest):
        return {spec.game_id: spec for spec in sx.scheduled_games(manifest)}
    if rd.is_diagnostic(manifest):
        return {spec.game_id: spec for spec in rd.scheduled_games(manifest)}
    return {spec.game_id: spec for spec in mf.gate1_games(manifest) + mf.games(manifest)}


def data_root(work: Path, scenario_id: str) -> Path:
    return work / "data" / scenario_id / "Data"


def verify_inputs(manifest: Dict[str, Any], work: Path, scenario_id: str, map_id: str) -> None:
    expected = next(s for s in manifest["scenarios"] if s["scenario_id"] == scenario_id)["inputs_sha256"]
    root = data_root(work, scenario_id)
    files = {"scenario": sdk_data.scenario_path(root, scenario_id), **sdk_data.map_paths(root, map_id)}
    for role, path in files.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected[role]:
            raise sdk_data.SdkDataError(f"{path} does not match the manifest digest for {role}")


def cmd_stage(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    for scenario in manifest["scenarios"]:
        root = data_root(args.work, scenario["scenario_id"])
        if not root.exists():
            sdk_data.stage_game_data(args.sdk_archive, root.parent, scenario["scenario_id"], scenario["map_id"])
        verify_inputs(manifest, args.work, scenario["scenario_id"], scenario["map_id"])
        print(f"staged and verified {scenario['scenario_id']} (map {scenario['map_id']})")
    return 0


def _terminate(signum: int, frame: Any) -> None:
    raise SystemExit(128 + signum)  # lets the session ledger record the interruption


def engine_factory(install: engine_install.EngineInstall) -> Any:
    """Construct ``TrainEnv`` from the persistent installation; import failures surface as engine failures."""
    def construct() -> Any:
        import train_env  # the SDK engine; importable only inside the prepared runtime
        module = Path(train_env.__file__).resolve()
        if install.site.resolve() not in module.parents:
            raise RuntimeError(f"train_env was imported from {module}, outside the persistent installation")
        construct.version = getattr(train_env, "__version__", None)
        return train_env.TrainEnv()
    construct.version = None
    return construct


def cmd_game(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, _terminate)
    mode = getattr(args, "session_mode", "exclusive")
    execution = {"workers": getattr(args, "workers", None), "worker": getattr(args, "worker", None),
                 "batch": getattr(args, "batch", None), "scheduler": getattr(args, "scheduler", None)}
    if mode == "shared" and None in execution.values():
        print("a shared session needs --workers, --worker, --batch and --scheduler", file=sys.stderr)
        return 2
    manifest = load_manifest(args.manifest)
    spec = all_games(manifest).get(args.game_id)
    if spec is None:
        print(f"unknown game id {args.game_id}", file=sys.stderr)
        return 2
    group = sx.group_of(manifest, spec.game_id) if sx.is_experiment(manifest) else None
    registered = manifest["groups"][group]["policy_source"] if group else manifest["policy_source"]
    policy_under_test = manifest["groups"][group]["policy"] if group else manifest["policy_under_test"]
    source = registered_source_digest(registered)
    if source != registered["sha256"]:
        print("REFUSED: the policy source differs from the registered one; a policy change needs a new "
              "registration and a complete rerun", file=sys.stderr)
        return 2
    if vs.is_study(manifest) and source != vs.BASELINE_V1_SOURCE_SHA256:
        print("REFUSED: the variance study runs baseline-v1 only; the policy source digest differs from it",
              file=sys.stderr)
        return 2
    if group == "B" and source != sx.RUNTIME_R1_SOURCE_SHA256:
        print("REFUSED: group B runs baseline-v1 on baseline-v1-runtime-r1 only; the digest differs from it",
              file=sys.stderr)
        return 2
    diagnostic = rd.is_diagnostic(manifest)
    if diagnostic and source != rd.BASELINE_V2_SOURCE_SHA256:
        print("REFUSED: the residual-516 diagnostic runs baseline-v2 only; the policy source digest differs from it",
              file=sys.stderr)
        return 2
    out = args.work / "games" / f"{spec.game_id}.json"
    if out.exists():
        print(f"REFUSED: {out} exists; records are never overwritten", file=sys.stderr)
        return 2
    captures = (args.work / "capture" / f"{spec.game_id}.capture.json", args.work / "capture" / f"{spec.game_id}.windows.pkl")
    if diagnostic and any(path.exists() for path in captures):
        print(f"REFUSED: capture files of {spec.game_id} exist; captures are never overwritten", file=sys.stderr)
        return 2
    registered_runtime = ex.registered(manifest)["runtime"]
    runtime = getattr(args, "runtime", None) or registered_runtime
    if args.purpose == "evaluation" and runtime != registered_runtime:
        print(f"REFUSED: a registered run uses the runtime its manifest registers ({registered_runtime}), not {runtime}",
              file=sys.stderr)
        return 2
    try:
        problem = ex.check_thread_env(os.environ, runtime)
    except ValueError as exc:
        problem = str(exc)
    if problem:
        print(f"REFUSED: {problem}", file=sys.stderr)
        return 2
    try:
        verify_inputs(manifest, args.work, spec.scenario_id, spec.map_id)
        inputs = sdk_data.load_inputs(data_root(args.work, spec.scenario_id), spec.scenario_id, spec.map_id)
    except (sdk_data.SdkDataError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    randomness.seed_globals(int(manifest["randomness"]["global_seed"]))
    harness = {"commit": args.harness_commit, "dirty": args.harness_dirty, "game_id": spec.game_id,
               "manifest_sha256": mf.digest(manifest), "policy_source_sha256": source}
    if group:
        harness["group"] = group
    if mode == "shared":
        harness["execution"] = {"mode": mode, **execution}
    if runtime != ex.DEFAULT_RUNTIME:
        harness["runtime"] = runtime
        harness["thread_env"] = ex.runtime_env(runtime)
    install = engine_install.EngineInstall(args.engine_install.resolve())
    construct = engine_factory(install)
    opener = (engine_install.session(install, args.purpose, harness) if mode == "exclusive"
              else engine_install.shared_session(install, args.purpose, harness, str(execution["worker"])))
    observer = rd.Capture((policy_under_test,)) if diagnostic else None
    try:
        with opener as handle:
            record = play(construct, FACTORIES, spec, inputs, manifest["players"], rng_probe=randomness.fingerprint,
                          replay_policies={policy_under_test}, observer=observer)
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
    if observer is not None:
        compact, windows = observer.files()
        captures[0].parent.mkdir(parents=True, exist_ok=True)
        for path, data in zip(captures, (compact, windows)):
            with open(path, "xb") as handle:
                handle.write(data)
        record["capture"] = observer.summary(compact, windows)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    seats = " ".join(f"{s['policy']}:{sum(s['actions_by_type'].values())}" for s in record.get("seats", []))
    print(f"GAME {spec.game_id} {record['status']} steps={record.get('steps')} "
          f"wall={record.get('timings_seconds', {}).get('wall', 0):.1f}s actions={seats}", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" else 1


def read_records(work: Path, specs: List[mf.GameSpec]) -> Dict[str, Dict[str, Any]]:
    records = {}
    for spec in specs:
        path = work / "games" / f"{spec.game_id}.json"
        if path.exists():
            records[spec.game_id] = json.loads(path.read_text(encoding="utf-8"))
    return records


def cmd_summarize(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if vs.is_study(manifest):
        print("the variance study is analysed by scripts/analyze_variance_study.py", file=sys.stderr)
        return 2
    if sx.is_experiment(manifest):
        print("the shoot-reservation experiment is analysed by scripts/analyze_shoot_experiment.py", file=sys.stderr)
        return 2
    if rd.is_diagnostic(manifest):
        print("the residual-516 diagnostic is analysed by scripts/residual516_diagnostic.py", file=sys.stderr)
        return 2
    digest = mf.digest(manifest)
    gate_specs, suite_specs = mf.gate1_games(manifest), mf.games(manifest)
    gate_records = read_records(args.work, gate_specs)
    policy = manifest["policy_under_test"]
    extra = tuple(manifest.get("registered_seat_metrics", ()))
    extended = policy != BASELINE_ID
    gate = (metrics.gate_check([gate_records[s.game_id] for s in gate_specs], policy, extra)
            if len(gate_records) == len(gate_specs) else None)
    suite_records = read_records(args.work, suite_specs)
    summary: Dict[str, Any] = {"manifest_sha256": digest, "evaluation_id": manifest["evaluation_id"],
                               "policy_source_sha256": manifest["policy_source"]["sha256"],
                               "gate1": {"games": [metrics.public_game(gate_records[s.game_id]) for s in gate_specs
                                                   if s.game_id in gate_records],
                                         "criteria": gate},
                               "suite": {"registered_games": len(suite_specs), "recorded_games": len(suite_records)}}
    policies = {r["harness"]["policy_source_sha256"] for r in list(gate_records.values()) + list(suite_records.values())}
    summary["policy_source_consistent"] = policies <= {manifest["policy_source"]["sha256"]}
    if suite_records:
        by_condition: Dict[str, List[Dict[str, Any]]] = {}
        for spec in suite_specs:
            if spec.game_id in suite_records:
                by_condition.setdefault(spec.condition, []).append(suite_records[spec.game_id])
        repetitions = []
        for spec in suite_specs:
            if spec.repetition != 1:
                continue
            others = [suite_records.get(f"{spec.scenario_id}.{spec.condition}.r{r}")
                      for r in range(1, int(manifest["repetitions"]) + 1)]
            if all(others):
                repetitions.append({"scenario_id": spec.scenario_id, "condition": spec.condition,
                                    **metrics.compare(others[0], others[1])})
        summary["suite"].update(
            games=[metrics.public_game(suite_records[s.game_id]) for s in suite_specs if s.game_id in suite_records],
            conditions={c: metrics.condition_summary(r, policy, extended) for c, r in sorted(by_condition.items())},
            repetition_agreement=repetitions,
            criteria_by_configuration={
                f"{s.scenario_id}.{s.condition}": metrics.gate_check(
                    [suite_records[f"{s.scenario_id}.{s.condition}.r{r}"] for r in range(1, int(manifest["repetitions"]) + 1)],
                    policy, extra)
                for s in suite_specs if s.repetition == 1 and all(
                    f"{s.scenario_id}.{s.condition}.r{r}" in suite_records for r in range(1, int(manifest["repetitions"]) + 1))
            })
    if "refusal_taxonomy" in manifest:
        taxonomy = manifest["refusal_taxonomy"]["codes"]
        summary["gate1"]["refusal_decomposition"] = metrics.refusal_decomposition(
            list(gate_records.values()), policy, taxonomy)
        if suite_records:
            summary["suite"]["refusal_decomposition"] = metrics.refusal_decomposition(
                list(suite_records.values()), policy, taxonomy)
    text = json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    (args.work / "summary.json").write_text(text, encoding="utf-8")
    if args.public:
        args.public.parent.mkdir(parents=True, exist_ok=True)
        args.public.write_text(text, encoding="utf-8", newline="\n")
    if gate:
        print("GATE1 " + " ".join(f"{k}={'PASS' if v['pass'] else 'FAIL'}" for k, v in gate.items()))
    print(f"suite records {len(suite_records)}/{len(suite_specs)}; policy source consistent: "
          f"{summary['policy_source_consistent']}; manifest {digest}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evaluation", default="baseline-v0",
                        help="registered evaluation name: evaluation/NAME/manifest.json, work in local/evaluation/NAME")
    parser.add_argument("--manifest", type=Path, help="override the manifest path")
    parser.add_argument("--work", type=Path, help="override the work directory")
    sub = parser.add_subparsers(dest="command", required=True)
    stage = sub.add_parser("stage")
    stage.add_argument("--sdk-archive", type=Path, required=True)
    stage.set_defaults(func=cmd_stage)
    game = sub.add_parser("game")
    game.add_argument("--game-id", required=True)
    game.add_argument("--engine-install", type=Path, required=True)
    game.add_argument("--harness-commit", default="unknown")
    game.add_argument("--harness-dirty", action="store_true")
    game.add_argument("--purpose", default="evaluation", choices=("evaluation", "diagnostic"),
                      help="session purpose recorded in the engine ledger; a diagnostic run uses its own --work")
    game.add_argument("--session-mode", default="exclusive", choices=("exclusive", "shared"),
                      help="shared: one of several concurrent games started by scripts/run_game_pool.py")
    game.add_argument("--workers", type=int, help="shared mode: the run's worker count")
    game.add_argument("--worker", type=int, help="shared mode: this game's worker slot")
    game.add_argument("--batch", type=int, help="shared mode: this game's dispatch wave")
    game.add_argument("--scheduler", help="shared mode: the scheduler identity (id@sha256 of its sources)")
    game.add_argument("--runtime", help="the runtime identity (default: the manifest's registered runtime); a "
                                        "registered run may not change it, and the game's numerical-thread "
                                        "variables must be exactly that runtime's")
    game.set_defaults(func=cmd_game)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--public", type=Path, help="also write the sanitized summary here")
    summarize.set_defaults(func=cmd_summarize)
    args = parser.parse_args()
    args.manifest = args.manifest or REPO_ROOT / "evaluation" / args.evaluation / "manifest.json"
    args.work = args.work or REPO_ROOT / "local" / "evaluation" / args.evaluation
    started = time.perf_counter()
    status = args.func(args)
    if args.command != "game":
        print(f"done in {time.perf_counter() - started:.1f}s")
    return status


if __name__ == "__main__":
    sys.exit(main())
