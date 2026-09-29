"""Command-line entry points for the engine smoke test.

    stage  copy one scenario, one map and the engine wheel out of a verified local SDK archive
    run    import the engine, play one controlled game with inert agents, write a JSON report

``run`` must execute with the engine importable (for example with an isolated ``--target``
install on ``PYTHONPATH``); ``scripts/run_engine_smoke_test.sh`` prepares that isolation. The
report and raw observations are written to ``--evidence-dir`` and never belong in version control.

Exit status of ``run``: 0 PASS, 1 FAIL, 3 BLOCKED, 2 invalid input before the engine was touched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import sys
import time
from pathlib import Path
from typing import List, Optional, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import engine_smoke, sdk_data  # noqa: E402
from miaosuan_agent.smoke_agent import SmokeAgent  # noqa: E402

EXIT = {"PASS": 0, "FAIL": 1, "BLOCKED": 3}
BEIJING = dt.timezone(dt.timedelta(hours=8))


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


def _now() -> dict:
    moment = dt.datetime.now(dt.timezone.utc)
    return {"utc": moment.isoformat(timespec="seconds"),
            "beijing": moment.astimezone(BEIJING).isoformat(timespec="seconds")}


def cmd_stage(args: argparse.Namespace) -> int:
    staged = sdk_data.stage_runtime_assets(args.sdk_archive, args.dest, args.scenario_id, args.map_id)
    for key, path in staged.items():
        print(f"{key}: {path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    evidence_dir: Path = args.evidence_dir
    evidence_dir.mkdir(parents=True, exist_ok=True)
    out, err = Tee(sys.stdout), Tee(sys.stderr)
    sys.stdout, sys.stderr = out, err
    captured = lambda: out.text() + err.text()  # noqa: E731

    report: dict = {"started_at": _now(), "python": sys.version.split()[0]}
    try:
        inputs = sdk_data.load_inputs(args.data_root, args.scenario_id, args.map_id)
    except sdk_data.SdkDataError as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2
    report["see_data"] = engine_smoke.describe(inputs.see)

    started = time.perf_counter()
    try:
        import train_env  # the SDK engine; only importable inside the prepared runtime
    except Exception as exc:  # noqa: BLE001 - ABI or dependency failures must be reported
        report.update(status="FAIL", phase="import", reasons=[f"{type(exc).__name__} importing train_env: {exc}"])
        report["captured_output"] = captured()[-20000:]
        report["finished_at"] = _now()
        engine_smoke.write_json(evidence_dir / "report.json", report)
        return EXIT["FAIL"]
    report["import_seconds"] = time.perf_counter() - started
    report["engine_version"] = getattr(train_env, "__version__", None)
    report["engine_module_file"] = getattr(train_env, "__file__", None)

    limits = engine_smoke.SmokeLimits(max_steps=args.max_steps, max_seconds=args.max_seconds)
    wall_started = time.perf_counter()
    result = engine_smoke.run_smoke(train_env.TrainEnv, SmokeAgent, inputs, limits, evidence_dir, captured)
    report.update(result)
    report["wall_seconds_after_import"] = time.perf_counter() - wall_started
    report["captured_output"] = captured()[-20000:]
    report["finished_at"] = _now()
    engine_smoke.write_json(evidence_dir / "report.json", report)
    print(f"SMOKE {report['status']} phase={report.get('phase')} steps={report.get('steps')} "
          f"completion={report.get('completion')} reasons={report.get('reasons')}", file=sys.__stdout__)
    return EXIT[report["status"]]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    stage = sub.add_parser("stage", help="extract the inputs for one game from the SDK archive")
    stage.add_argument("--sdk-archive", type=Path, required=True)
    stage.add_argument("--dest", type=Path, required=True)
    stage.add_argument("--scenario-id", required=True)
    stage.add_argument("--map-id", required=True)
    stage.set_defaults(func=cmd_stage)

    run = sub.add_parser("run", help="play one controlled game and write the report")
    run.add_argument("--data-root", type=Path, required=True, help="an extracted SDK Data/ directory")
    run.add_argument("--scenario-id", required=True)
    run.add_argument("--map-id", required=True)
    run.add_argument("--evidence-dir", type=Path, required=True)
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
