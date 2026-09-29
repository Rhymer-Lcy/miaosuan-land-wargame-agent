"""Command-line entry points for the registered evaluation.

    stage      copy each registered scenario's inputs out of the verified SDK archive and check them
               against the manifest's digests
    game       play one registered game (one engine session, one process) and write its record
    summarize  derive the gate report, the private summary and the public results from the records

``game`` must run inside the isolation prepared by ``scripts/run_evaluation.sh`` (persistent engine
installation on PYTHONPATH, empty environment). It refuses to play when the policy source differs
from the one recorded in the manifest, so the registered policy cannot change silently. Records
and summaries live under the git-ignored ``local/evaluation/``; only the sanitized public results
file is meant for version control.

Exit status of ``game``: 0 the game completed, 1 it failed or hit a cap, 2 invalid input before the
engine was touched, 4 an installation guardrail refused the session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
from miaosuan_agent.evaluation import metrics, randomness  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.evaluation.identity import POLICY_SOURCES, digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import CANDIDATE_ID, ReservationAgent  # noqa: E402

DEFAULT_MANIFEST = REPO_ROOT / "evaluation" / "baseline-v0" / "manifest.json"
FACTORIES = {BASELINE_ID: lambda: PolicyAgent(BASELINE_ID), INERT_ID: lambda: PolicyAgent(INERT_ID),
             CANDIDATE_ID: lambda: ReservationAgent()}


def registered_policy_source(manifest: Dict[str, Any]) -> str:
    """The digest of the policy source the manifest registered, recomputed from this checkout.

    The files are the manifest's own list; they must also be exactly what its source set yields now,
    so a file added to a covered directory is caught.
    """
    registered = manifest["policy_source"]
    sources = tuple(registered.get("sources", POLICY_SOURCES))
    if policy_source_files(sources=sources) != list(registered["files"]):
        return "file list differs from the registered one"
    return digest_of_files(registered["files"])


def load_manifest(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def all_games(manifest: Dict[str, Any]) -> Dict[str, mf.GameSpec]:
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
    manifest = load_manifest(args.manifest)
    spec = all_games(manifest).get(args.game_id)
    if spec is None:
        print(f"unknown game id {args.game_id}", file=sys.stderr)
        return 2
    source = registered_policy_source(manifest)
    if source != manifest["policy_source"]["sha256"]:
        print("REFUSED: the policy source differs from the registered one; a policy change needs a new "
              "registration and a complete rerun", file=sys.stderr)
        return 2
    out = args.work / "games" / f"{spec.game_id}.json"
    if out.exists():
        print(f"REFUSED: {out} exists; records are never overwritten", file=sys.stderr)
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
    install = engine_install.EngineInstall(args.engine_install.resolve())
    construct = engine_factory(install)
    try:
        with engine_install.session(install, args.purpose, harness) as handle:
            record = play(construct, FACTORIES, spec, inputs, manifest["players"], rng_probe=randomness.fingerprint,
                          replay_policies={manifest["policy_under_test"]})
            record["session"] = handle.opened["session"]
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": spec.game_id}
        record["session_close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 4
    record.update(harness=harness, engine_version=construct.version, python=sys.version.split()[0],
                  host_clock_finished=engine_install.now())
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
