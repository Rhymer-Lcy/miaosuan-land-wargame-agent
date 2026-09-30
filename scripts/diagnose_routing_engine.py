"""Play one game of the routing remediation's engine diagnostic with a live shadow comparison.

    python scripts/diagnose_routing_engine.py --game-id ID --engine-install DIR [--harness-commit C]

Diagnostic only: not an evaluation, and its games belong to no evaluation dataset; no outcome or score
is evidence. It must run inside the isolation prepared by ``scripts/run_routing_diagnostic.sh``. Before
the engine is touched it checks that the registration rebuilds from this checkout, that baseline-v1's
policy source and the study manifest are the registered ones, and that the equivalence replay of this
exact candidate is clean.

The game is played by the unchanged harness (``evaluation.game.play``). Every seat that the study
assigns to baseline-v1 runs the candidate (``BoundedRoutingAgent``) inside a wrapper that also holds a
shadow baseline-v1 agent (``ReservationAgent``) set up with the same information. For each decision
the wrapper times the candidate's ``step`` (wall, thread CPU, collection time), then lets the shadow
decide on the same observation outside that window and compares: emitted actions (content and order),
semantic trace, memory, contract error, and that the observation was not modified. Only the
candidate's actions reach the engine. The harness's own per-step time for such a seat includes the
shadow's decision; the wrapper's times are the ones to read. No collection setting is changed.

Per-decision rows are streamed to ``local/diagnostics/routing/engine/<id>.decisions.jsonl.gz``; the
summary with the session record is ``<id>.json.gz``. Neither is ever overwritten.
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
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.boundary import Stage  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.canonical import value_digest  # noqa: E402
from miaosuan_agent.evaluation.game import play  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import ReservationAgent  # noqa: E402
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingAgent  # noqa: E402

import run_evaluation as rev  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
STUDY = REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1"
WORK = REPO_ROOT / "local" / "diagnostics" / "routing" / "engine"
NEWLINE = chr(10)

_gc = {"start": 0.0, "seconds": 0.0}


def _gc_callback(phase: str, info: Mapping[str, Any]) -> None:
    if phase == "start":
        _gc["start"] = time.perf_counter()
    else:
        _gc["seconds"] += time.perf_counter() - _gc["start"]


def _timed(agent: Any, observation: Any) -> Dict[str, Any]:
    _gc["seconds"] = 0.0
    thread0, start = time.thread_time(), time.perf_counter()
    actions = agent.step(observation)
    wall, cpu = time.perf_counter() - start, time.thread_time() - thread0
    return {"actions": actions, "wall": wall, "cpu": cpu, "gc": _gc["seconds"]}


def new_tally() -> Dict[str, int]:
    return dict.fromkeys(("decisions", "different", "rejected_decisions", "shadow_rejected_decisions",
                          "contract_errors", "shadow_contract_errors"), 0)


class Shadowed:
    """The candidate for the engine; a shadow baseline-v1 agent decides on the same observation afterwards."""

    def __init__(self, sink: Dict[str, Any]) -> None:
        self.inner, self.shadow, self.sink = BoundedRoutingAgent(), ReservationAgent(), sink
        self.index = 0
        self.first_play = None

    def setup(self, info: Dict[str, Any]) -> None:
        self.inner.setup(info)
        self.shadow.setup(info)
        self.seat, self.faction = info["seat"], info["faction"]

    def step(self, observation: Any) -> List[Dict[str, Any]]:
        before = value_digest(dict(observation))
        candidate = _timed(self.inner, observation)
        after_candidate = value_digest(dict(observation))
        shadow = _timed(self.shadow, observation)
        new_trace, old_trace = self.inner.last_trace, self.shadow.last_trace
        checks = {"actions_equal": [dict(a) for a in candidate["actions"]] == [dict(a) for a in shadow["actions"]],
                  "semantic_equal": rr.semantic_trace(new_trace) == rr.semantic_trace(old_trace),
                  "memory_equal": self.inner.memory == self.shadow.memory,
                  "error_equal": new_trace.error == old_trace.error,
                  "observation_unmodified": before == after_candidate == value_digest(dict(observation))}
        row = {"seat": self.seat, "decision": self.index, "stage": new_trace.stage, "equal": all(checks.values()),
               "candidate": {k: candidate[k] for k in ("wall", "cpu", "gc")},
               "shadow": {k: shadow[k] for k in ("wall", "cpu", "gc")},
               "emitted": len(candidate["actions"]), "rejected": len(new_trace.rejected),
               "shadow_rejected": len(old_trace.rejected), "error": new_trace.error is not None,
               "shadow_error": old_trace.error is not None}
        if not row["equal"]:
            row["failed"] = sorted(k for k, v in checks.items() if not v)
        if self.first_play is None and new_trace.stage == Stage.PLAY:
            self.first_play = dict(row)
        self.sink["decisions"].write(json.dumps(row, sort_keys=True) + NEWLINE)
        tally = self.sink["tally"]
        tally["decisions"] += 1
        tally["different"] += not row["equal"]
        tally["rejected_decisions"] += row["rejected"] > 0
        tally["shadow_rejected_decisions"] += row["shadow_rejected"] > 0
        tally["contract_errors"] += row["error"]
        tally["shadow_contract_errors"] += row["shadow_error"]
        self.index += 1
        return candidate["actions"]

    def replay(self, observation: Any, memory: Any) -> Any:
        return self.inner.replay(observation, memory)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def refusal(message: str) -> int:
    print(f"REFUSED: {message}", file=sys.stderr)
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--engine-install", type=Path, required=True)
    parser.add_argument("--harness-commit", default="unknown")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, rev._terminate)
    registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))
    corpus = json.loads((DIRECTORY / "corpus.json").read_text(encoding="utf-8"))
    if rr.build(corpus) != registration:
        return refusal("the registration does not rebuild from this checkout")
    entry = next((g for g in registration["engine_diagnostic"]["games"] if g["id"] == args.game_id), None)
    if entry is None:
        return refusal(f"unknown diagnostic game {args.game_id}")
    study = json.loads((STUDY / "manifest.json").read_text(encoding="utf-8"))
    if mf.digest(study) != rr.PARENT["variance_study_manifest_sha256"]:
        return refusal("the study manifest is not the registered one")
    if rev.registered_policy_source(study) != rr.PARENT["policy_source_sha256"]:
        return refusal("baseline-v1's policy source is not the frozen one")
    candidate_sha = policy_source_digest(sources=rr.candidate_sources())[0]
    equivalence = json.loads((DIRECTORY / "equivalence.json").read_text(encoding="utf-8"))
    if equivalence["unexplained_differences"] != 0 or equivalence["candidate_source_sha256"] != candidate_sha:
        return refusal("the equivalence replay of this candidate is not clean")
    out = WORK / f"{args.game_id}.json.gz"
    decisions_path = WORK / f"{args.game_id}.decisions.jsonl.gz"
    if out.exists() or decisions_path.exists():
        return refusal(f"{out} exists; diagnostic records are never overwritten")
    scenario = next(s for s in study["scenarios"] if s["scenario_id"] == entry["scenario_id"])
    condition = next(c for c in study["conditions"] if c["id"] == entry["condition"])
    spec = mf.GameSpec(game_id=args.game_id, scenario_id=scenario["scenario_id"], map_id=scenario["map_id"],
                       condition=condition["id"], red=condition["red"], blue=condition["blue"], repetition=1,
                       max_time=int(scenario["max_time"]))
    work = REPO_ROOT / "local" / "evaluation" / study["study_id"]
    rev.verify_inputs(study, work, spec.scenario_id, spec.map_id)
    inputs = sdk_data.load_inputs(rev.data_root(work, spec.scenario_id), spec.scenario_id, spec.map_id)
    randomness.seed_globals(int(study["randomness"]["global_seed"]))
    WORK.mkdir(parents=True, exist_ok=True)
    sink: Dict[str, Any] = {"decisions": gzip.open(decisions_path, "wt", encoding="utf-8"), "tally": new_tally()}
    harness = {"script": "diagnose_routing_engine", "game_id": args.game_id, "commit": args.harness_commit,
               "baseline_v1_source_sha256": rr.PARENT["policy_source_sha256"],
               "candidate_source_sha256": candidate_sha, "registration_sha256": mf.digest(registration),
               "remediation_id": rr.REMEDIATION_ID}
    install = engine_install.EngineInstall(args.engine_install.resolve())
    shadowed: List[Shadowed] = []

    def made() -> Shadowed:
        agent = Shadowed(sink)
        shadowed.append(agent)
        return agent

    factories = dict(rev.FACTORIES)
    factories[study["policy_under_test"]] = made
    gc.callbacks.append(_gc_callback)
    try:
        with engine_install.session(install, "diagnostic", harness) as handle:
            record = play(rev.engine_factory(install), factories, spec, inputs, study["players"],
                          rng_probe=randomness.fingerprint, replay_policies={study["policy_under_test"]})
            handle.outcome = {"status": record["status"], "steps": record.get("steps"), "game_id": args.game_id}
    finally:
        gc.callbacks.remove(_gc_callback)
        sink["decisions"].close()
    record["session"] = handle.opened["session"]
    payload = {"registration_entry": entry, "harness": harness, "session": handle.opened["session"],
               "session_close": {k: handle.closed[k] for k in ("state_changed", "home_changed", "integrity")},
               "gc_thresholds": list(gc.get_threshold()), "python": sys.version.split()[0], "record": record,
               "decisions_file": decisions_path.name, "comparison": sink["tally"],
               "first_play": {str(agent.seat): agent.first_play for agent in shadowed}, "finished": time.time()}
    with gzip.open(out, "wt", encoding="utf-8") as handle_out:
        json.dump(payload, handle_out, sort_keys=True)
    tally = sink["tally"]
    print(f"DIAGNOSTIC {args.game_id} {record['status']} steps={record.get('steps')} "
          f"compared={tally['decisions']} different={tally['different']} "
          f"errors={tally['contract_errors']}/{tally['shadow_contract_errors']}", file=sys.__stdout__)
    return 0 if record["status"] == "COMPLETED" and tally["different"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
