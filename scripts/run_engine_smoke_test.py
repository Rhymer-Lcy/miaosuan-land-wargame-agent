"""Command-line entry points for the engine smoke test and contract capture.

    stage  copy the data for one game out of a verified local SDK archive
    run    open a session on the persistent engine installation, play one controlled game with inert
           agents, optionally capture private contract fixtures, and write a JSON report

``run`` must execute with the persistent installation's ``site/`` on ``PYTHONPATH``;
``scripts/run_engine_smoke_test.sh`` prepares that isolation. Reports, raw observations and
captures are written under the git-ignored ``local/`` tree and never belong in version control.

Exit status of ``run``: 0 PASS, 1 FAIL, 2 invalid input before the engine was touched,
3 BLOCKED (the engine reported an authentication failure), 4 REFUSED (an installation guardrail
stopped the run before the engine was imported).
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_install, engine_smoke, sdk_data  # noqa: E402
from miaosuan_agent.boundary.profile import PROFILE_ID  # noqa: E402
from miaosuan_agent.contract_capture import CaptureWriter  # noqa: E402
from miaosuan_agent.smoke_agent import SmokeAgent  # noqa: E402

EXIT = {"PASS": 0, "FAIL": 1, "BLOCKED": 3, "REFUSED": 4}


class Tee(io.TextIOBase):
    """Write-through text stream that also keeps a copy of everything written."""

    def __init__(self, target: TextIO) -> None:
        self._target = target
        self._chunks: List[str] = []

    def write(self, text: str) -> int:
        self._chunks.append(text)
        self._target.write(text)
        return len(text)

    def flush(self) -> None:
        self._target.flush()

    def text(self) -> str:
        return "".join(self._chunks)


def _relative(path: Path) -> str:
    try:
        return os.path.relpath(Path(path).resolve(), REPO_ROOT)
    except ValueError:
        return str(path)


def _terminate(signum: int, frame: Any) -> None:
    raise SystemExit(128 + signum)  # lets the session ledger record the interruption


def cmd_stage(args: argparse.Namespace) -> int:
    print(f"data_root: {sdk_data.stage_game_data(args.sdk_archive, args.dest, args.scenario_id, args.map_id)}")
    return 0


def _run_engine(args: argparse.Namespace, report: Dict[str, Any], inputs: sdk_data.ScenarioInputs,
                install: engine_install.EngineInstall, session_id: str, captured: Callable[[], str]) -> str:
    started = time.perf_counter()
    try:
        import train_env  # the SDK engine; importable only inside the prepared runtime
    except Exception as exc:  # noqa: BLE001 - ABI or dependency failures must be reported
        report.update(status="FAIL", phase="import", reasons=[f"{type(exc).__name__} importing train_env: {exc}"])
        return "FAIL"
    report["import_seconds"] = time.perf_counter() - started
    module = Path(train_env.__file__).resolve()
    report["engine_module_file"] = _relative(module)
    report["engine_version"] = getattr(train_env, "__version__", None)
    if install.site.resolve() not in module.parents:
        report.update(status="FAIL", phase="import",
                      reasons=[f"train_env was imported from {module}, outside the persistent installation"])
        return "FAIL"

    writer = None
    if args.capture_dir:
        writer = CaptureWriter(args.capture_dir, {
            "engine_version": report["engine_version"], "profile_id": PROFILE_ID,
            "scenario_id": args.scenario_id, "map_id": args.map_id, "harness": report["harness"],
            "session": session_id, "created_at": engine_install.now(),
            "evidence_dir": _relative(args.evidence_dir), "engine_install": _relative(install.root),
        })
    limits = engine_smoke.SmokeLimits(max_steps=args.max_steps, max_seconds=args.max_seconds)
    wall_started = time.perf_counter()
    result = engine_smoke.run_smoke(train_env.TrainEnv, SmokeAgent, inputs, limits, args.evidence_dir, captured,
                                    capture=writer.capture if writer else None)
    report.update(result)
    report["seconds_after_import"] = time.perf_counter() - wall_started
    if writer:
        keys = ("status", "steps", "completion", "state_form", "state_object_reused_by_step",
                "setup_state_changed_by_first_step", "deployment_transition_matches_profile",
                "profile_deviation_count", "captured_points")
        report["capture_manifest"] = _relative(writer.finalize({f"run_{k}": result.get(k) for k in keys}))
    return report["status"]


def cmd_run(args: argparse.Namespace) -> int:
    signal.signal(signal.SIGTERM, _terminate)
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    out, err = Tee(sys.stdout), Tee(sys.stderr)
    sys.stdout, sys.stderr = out, err
    captured = lambda: out.text() + err.text()  # noqa: E731

    report: Dict[str, Any] = {"started_at": engine_install.now(), "python": sys.version.split()[0],
                              "harness": {"commit": args.harness_commit, "dirty": args.harness_dirty,
                                          "scenario_id": args.scenario_id, "map_id": args.map_id,
                                          "capture": bool(args.capture_dir)},
                              "engine_install": _relative(args.engine_install)}
    try:
        inputs = sdk_data.load_inputs(args.data_root, args.scenario_id, args.map_id)
    except sdk_data.SdkDataError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    report["see_data"] = {"dtype": str(inputs.see.dtype), "shape": list(inputs.see.shape)}

    install = engine_install.EngineInstall(args.engine_install.resolve())
    purpose = "capture" if args.capture_dir else "smoke"
    try:
        with engine_install.session(install, purpose, report["harness"]) as handle:
            report["session"] = {"id": handle.opened["session"], "kind": handle.opened["kind"]}
            print(f"engine installation: session {handle.opened['session']} ({handle.opened['kind']})")
            try:
                status = _run_engine(args, report, inputs, install, handle.opened["session"], captured)
            except Exception as exc:  # noqa: BLE001 - recorded in the report and the ledger
                report.update(status="FAIL", reasons=[f"{type(exc).__name__} in the harness: {exc}"])
                status = "FAIL"
            handle.outcome = {"status": status, "steps": report.get("steps"), "completion": report.get("completion")}
        report["session"]["close"] = {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")}
    except engine_install.InstallRefused as exc:
        report.update(status="REFUSED", reasons=[str(exc)])
        status = "REFUSED"
    report["captured_output"] = captured()[-20000:]
    report["finished_at"] = engine_install.now()
    engine_smoke.write_json(args.evidence_dir / "report.json", report)
    print(f"SMOKE {report['status']} phase={report.get('phase')} steps={report.get('steps')} "
          f"completion={report.get('completion')} session={report.get('session', {}).get('id')} "
          f"reasons={report.get('reasons')}", file=sys.__stdout__)
    return EXIT[status]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    stage = sub.add_parser("stage", help="extract the data for one game from the SDK archive")
    stage.add_argument("--sdk-archive", type=Path, required=True)
    stage.add_argument("--dest", type=Path, required=True)
    stage.add_argument("--scenario-id", required=True)
    stage.add_argument("--map-id", required=True)
    stage.set_defaults(func=cmd_stage)

    run = sub.add_parser("run", help="play one controlled game on the persistent installation")
    run.add_argument("--engine-install", type=Path, required=True)
    run.add_argument("--data-root", type=Path, required=True, help="an extracted SDK Data/ directory")
    run.add_argument("--scenario-id", required=True)
    run.add_argument("--map-id", required=True)
    run.add_argument("--evidence-dir", type=Path, required=True)
    run.add_argument("--capture-dir", type=Path, help="write private contract fixtures here")
    run.add_argument("--harness-commit", default="unknown")
    run.add_argument("--harness-dirty", action="store_true")
    run.add_argument("--max-steps", type=int, default=1200)
    run.add_argument("--max-seconds", type=float, default=600.0)
    run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except sdk_data.SdkDataError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
