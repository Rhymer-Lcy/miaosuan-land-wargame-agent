"""Play one game of the registered latency-diagnostic plan with per-decision instrumentation.

    python scripts/diagnose_latency_engine.py --game-id ID --engine-install DIR [--harness-commit C]

Diagnostic only: not an evaluation, and its games belong to no evaluation dataset. It must run inside
the isolation prepared by ``scripts/run_latency_diagnostic.sh``. The policy must be the frozen
baseline-v1 (checked by digest before the engine is touched). The game is played by the unchanged
harness (``evaluation.game.play``) with the unchanged agents; each agent is wrapped so that every
decision is measured by :class:`miaosuan_agent.diagnostics.instrument.Probe` (components, routing
workload, thread and process CPU time, overlapping garbage collections, resource-usage deltas).
Selected observations are captured for offline replay: decisions 0-3, every 500th, and any
decision slower than 100 ms. Decision records and captures are streamed to compressed files as the
game runs rather than kept in memory, so the instrumentation does not enlarge the heap the garbage
collector traverses. Every output is written under ``local/diagnostics/latency/engine/`` and is
never overwritten. A plan entry may request ``gc_in_decision: paused``, the labelled
diagnostic comparison in which collection is disabled for the duration of each agent step only.
"""

from __future__ import annotations

import argparse
import gc
import gzip
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent import engine_install, sdk_data, typed_json  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.diagnostics import instrument  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402

import run_evaluation as rev  # noqa: E402

PLAN = REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json"
STUDY = REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1"
WORK = REPO_ROOT / "local" / "diagnostics" / "latency" / "engine"
CAPTURE_EVERY = 500
CAPTURE_SLOWER_THAN = 0.100
HEAP_EVERY = 500
NEWLINE = chr(10)


class Instrumented:
    """Delegates to the real agent; measures each ``step``; captures selected observations."""

    def __init__(self, inner: Any, probe: instrument.Probe, sink: Dict[str, Any], pause_gc: bool) -> None:
        self.inner, self.probe, self.sink, self.pause_gc = inner, probe, sink, pause_gc
        self.index = 0
        self.slow = 0

    def setup(self, info: Dict[str, Any]) -> None:
        self.inner.setup(info)
        self.seat, self.faction = info["seat"], info["faction"]

    def step(self, observation: Any) -> List[Dict[str, Any]]:
        memory = self.inner.memory
        paused = self.pause_gc and gc.isenabled()
        with self.probe.decision({"seat": self.seat, "decision": self.index,
                                  "policy": self.inner.policy_id}) as measured:
            if paused:
                gc.disable()
            try:
                actions = self.inner.step(observation)
            finally:
                if paused:
                    gc.enable()
        measured["meta"]["trace_digest"] = digest(self.inner.last_trace)
        measured["meta"]["units"] = len(self.inner.last_trace.units)
        measured["meta"]["emitted"] = len(actions)
        if self.index in (0, 1, 2, 3) or self.index % CAPTURE_EVERY == 0 or measured["wall"] > CAPTURE_SLOWER_THAN:
            capture = {"seat": self.seat, "faction": self.faction, "decision": self.index, "wall": measured["wall"],
                       "memory": {"deployment_sent": memory.deployment_sent},
                       "observation": typed_json.encode(dict(observation))[0],
                       "expected_trace_digest": measured["meta"]["trace_digest"]}
            self.sink["captures"].write(json.dumps(capture, sort_keys=True) + NEWLINE)
            self.sink["captured"] += 1
        if self.index % HEAP_EVERY == 0:
            measured["meta"]["tracked_objects_after"] = len(gc.get_objects())
        self.sink["decisions"].write(json.dumps(measured, sort_keys=True) + NEWLINE)
        self.slow += measured["wall"] > 0.1
        self.index += 1
        return actions

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--engine-install", type=Path, required=True)
    parser.add_argument("--harness-commit", default="unknown")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, rev._terminate)
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    entry = next((g for g in plan["games"] if g["id"] == args.game_id), None)
    if entry is None:
        print(f"unknown diagnostic game {args.game_id}", file=sys.stderr)
        return 2
    study = json.loads((STUDY / "manifest.json").read_text(encoding="utf-8"))
    if mf.digest(study) != plan["study_manifest_sha256"]:
        print("REFUSED: the study manifest is not the one the plan names", file=sys.stderr)
        return 2
    source = rev.registered_policy_source(study)
    if source != plan["policy_source_sha256"]:
        print("REFUSED: the policy source is not the frozen baseline-v1", file=sys.stderr)
        return 2
    out = WORK / f"{args.game_id}.json.gz"
    decisions_path, captures_path = WORK / f"{args.game_id}.decisions.jsonl.gz", WORK / f"{args.game_id}.captures.jsonl.gz"
    if out.exists() or decisions_path.exists() or captures_path.exists():
        print(f"REFUSED: {out} exists; diagnostic records are never overwritten", file=sys.stderr)
        return 2
    scenario = next(s for s in study["scenarios"] if s["scenario_id"] == entry["scenario_id"])
    condition = next(c for c in study["conditions"] if c["id"] == entry["condition"])
    spec = mf.GameSpec(game_id=args.game_id, scenario_id=scenario["scenario_id"], map_id=scenario["map_id"],
                       condition=condition["id"], red=condition["red"], blue=condition["blue"], repetition=1,
                       max_time=int(scenario["max_time"]))
    work = REPO_ROOT / "local" / "evaluation" / study["study_id"]
    rev.verify_inputs(study, work, spec.scenario_id, spec.map_id)
    inputs = sdk_data.load_inputs(rev.data_root(work, spec.scenario_id), spec.scenario_id, spec.map_id)
    randomness.seed_globals(int(study["randomness"]["global_seed"]))
    probe = instrument.Probe(keep=False)
    WORK.mkdir(parents=True, exist_ok=True)
    sink: Dict[str, Any] = {"decisions": gzip.open(decisions_path, "wt", encoding="utf-8"),
                            "captures": gzip.open(captures_path, "wt", encoding="utf-8"), "captured": 0}
    pause = entry.get("gc_in_decision") == "paused"
    harness = {"script": "diagnose_latency_engine", "game_id": args.game_id, "commit": args.harness_commit,
               "policy_source_sha256": source, "plan": plan["plan_id"]}
    install = engine_install.EngineInstall(args.engine_install.resolve())
    load_start = Path("/proc/loadavg").read_text().split()[:3] if Path("/proc/loadavg").exists() else None
    agents: List[Instrumented] = []

    def made(name: str) -> Instrumented:
        agent = Instrumented(rev.FACTORIES[name](), probe, sink, pause)
        agents.append(agent)
        return agent

    factories = {name: (lambda name=name: made(name)) for name in rev.FACTORIES}
    try:
        with engine_install.session(install, "diagnostic", harness) as handle, probe.installed():
            record = play(rev.engine_factory(install), factories, spec, inputs, study["players"],
                          rng_probe=randomness.fingerprint, replay_policies={study["policy_under_test"]})
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": args.game_id}
    finally:
        sink["decisions"].close()
        sink["captures"].close()
    record["session"] = handle.opened["session"]
    load_end = Path("/proc/loadavg").read_text().split()[:3] if Path("/proc/loadavg").exists() else None
    payload = {"plan_entry": entry, "harness": harness, "session": handle.opened["session"],
               "session_close": {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")},
               "loadavg_start": load_start, "loadavg_end": load_end, "gc_thresholds": list(gc.get_threshold()),
               "python": sys.version.split()[0], "record": record, "decisions_file": decisions_path.name,
               "captures_file": captures_path.name, "captured": sink["captured"],
               "full_collections": probe.full_collections,
               "collections_outside_decisions": probe.collections_outside_decisions, "finished": time.time()}
    with gzip.open(out, "wt", encoding="utf-8") as handle_out:
        json.dump(payload, handle_out, sort_keys=True)
    print(f"DIAGNOSTIC {args.game_id} {record['status']} steps={record.get('steps')} "
          f"decisions={sum(a.index for a in agents)} over100ms={sum(a.slow for a in agents)} "
          f"full_collections={len(probe.full_collections)} captures={sink['captured']}", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
