"""Full-agent equivalence of the routing candidate and baseline-v1 over the registered private corpus.

    python scripts/compare_routing_candidate.py [--check]

No engine is involved. Every file of ``evaluation/routing-remediation-1/corpus.json`` is verified
against its pinned digest, then:

* each recorded game of the replay corpus is replayed seat by seat in order, with one persistent
  baseline-v1 agent and one persistent candidate agent per seat (each memo evolves as in a game);
* each captured decision of the latency diagnostic (both seats) and each diagnostic state is decided
  once by a new agent of each kind, with the recorded memory.

The number of decisions compared must equal the pinned count, file by file and in total.

For every decision both agents receive the same observation. Compared: the emitted action lists
(content and order), the semantic traces (the trace without its ``policy`` field), the memory carried
to the next step, contract errors, move paths, chosen objectives with their costs, units left without
an action with their reasons, and that neither agent modified the observation. Differences are
written privately under ``local/diagnostics/routing/``; the public aggregate is
``evaluation/routing-remediation-1/equivalence.json``. ``--check`` rebuilds the aggregate and compares.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.decision.policy import Memory  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import ReservationAgent  # noqa: E402
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingAgent  # noqa: E402

DIRECTORY = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID
OUT = DIRECTORY / "equivalence.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "routing" / "equivalence-differences.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
SCHEMA = "miaosuan-routing-equivalence/1"


MOVE = 1
FIELDS = ("decisions", "identical", "different", "actions_equal", "semantic_traces_equal", "memory_equal",
          "moves", "move_paths_equal", "objective_choices", "objective_choices_equal", "no_op_decisions",
          "no_op_units", "no_op_units_equal", "contract_errors", "mutated_inputs")


def chosen_objectives(semantic: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    return [(u["obj_id"], u["detail"]["destination"], u["detail"]["cost"]) for u in semantic["units"]
            if u["action_type"] == MOVE and "destination" in u["detail"]]


def no_op_units(semantic: Dict[str, Any]) -> List[Tuple[Any, ...]]:
    return [(u["obj_id"], u["no_op_reason"]) for u in semantic["units"] if u["no_op_reason"] is not None]


class Tally:
    def __init__(self) -> None:
        self.by_role: Dict[str, Dict[str, int]] = {}
        self.differences: List[Dict[str, Any]] = []

    def add(self, role: str, where: str, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        counts = self.by_role.setdefault(role, dict.fromkeys(FIELDS, 0))
        old_paths = [a.get("move_path") for a in old["actions"] if a.get("type") == MOVE]
        new_paths = [a.get("move_path") for a in new["actions"] if a.get("type") == MOVE]
        old_choices, new_choices = chosen_objectives(old["semantic"]), chosen_objectives(new["semantic"])
        old_idle, new_idle = no_op_units(old["semantic"]), no_op_units(new["semantic"])
        checks = {"actions_equal": old["actions"] == new["actions"],
                  "semantic_traces_equal": old["semantic"] == new["semantic"],
                  "memory_equal": old["memory"] == new["memory"], "errors_equal": old["error"] == new["error"],
                  "move_paths_equal": old_paths == new_paths, "objective_choices_equal": old_choices == new_choices,
                  "no_op_units_equal": old_idle == new_idle,
                  "inputs_unmodified": not (old["mutated"] or new["mutated"])}
        same = all(checks.values())
        counts["decisions"] += 1
        counts["identical" if same else "different"] += 1
        for name in ("actions_equal", "semantic_traces_equal", "memory_equal"):
            counts[name] += checks[name]
        counts["moves"] += len(old_paths)
        counts["move_paths_equal"] += len(old_paths) if checks["move_paths_equal"] else 0
        counts["objective_choices"] += len(old_choices)
        counts["objective_choices_equal"] += len(old_choices) if checks["objective_choices_equal"] else 0
        counts["no_op_decisions"] += not old["actions"]
        counts["no_op_units"] += len(old_idle)
        counts["no_op_units_equal"] += len(old_idle) if checks["no_op_units_equal"] else 0
        counts["contract_errors"] += old["error"] is not None
        counts["mutated_inputs"] += not checks["inputs_unmodified"]
        if not same:
            self.differences.append({"where": where, "failed": sorted(k for k, v in checks.items() if not v),
                                     "errors": [old["error"], new["error"]]})


def decide(agent: Any, observation: Any) -> Dict[str, Any]:
    before = json.dumps(typed_json.encode(observation)[0], sort_keys=True)
    actions = [dict(a) for a in agent.step(observation)]
    mutated = json.dumps(typed_json.encode(observation)[0], sort_keys=True) != before
    trace = agent.last_trace
    return {"actions": actions, "semantic": rr.semantic_trace(trace), "memory": agent.memory,
            "error": None if trace.error is None else str(trace.error), "mutated": mutated}


def compare(tally: Tally, role: str, where: str, pair: Tuple[Any, Any], observation: Any) -> None:
    old_agent, new_agent = pair
    tally.add(role, where, decide(old_agent, observation), decide(new_agent, observation))


def agents_for(seat: int, faction: int, cost: Any, memory: Memory = None) -> Tuple[Any, Any]:
    pair = []
    for kind in (ReservationAgent, BoundedRoutingAgent):
        agent = kind()
        agent.setup({"seat": seat, "faction": faction, "cost_data": cost})
        if memory is not None:
            agent.memory = memory
        pair.append(agent)
    return pair[0], pair[1]


def costs_for(scenario_id: str, map_id: str) -> Any:
    return sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def build() -> Dict[str, Any]:
    if policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0] != rr.PARENT["policy_source_sha256"]:
        raise SystemExit("baseline-v1's policy source is not the frozen one")
    registration = json.loads((DIRECTORY / "registration.json").read_text(encoding="utf-8"))
    study = json.loads((REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1" / "manifest.json").read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in study["scenarios"]}
    plan = json.loads((REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json").read_text(encoding="utf-8"))
    tally = Tally()
    for entry in registration["corpus"]["files"]:
        path = REPO_ROOT / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        role = entry["role"]
        before = tally.by_role.get(role, {}).get("decisions", 0)
        if role == "replay corpus game":
            stream = lines(path)
            header = next(stream)
            cost = costs_for(header["scenario_id"], header["map_id"])
            seats: Dict[int, Tuple[Any, Any]] = {}
            for record in stream:
                if record["seat"] not in seats:
                    seats[record["seat"]] = agents_for(record["seat"], record["faction"], cost)
                compare(tally, role, f"{header['game_id']} seat {record['seat']} decision {record['step']}",
                        seats[record["seat"]], typed_json.decode(record["observation"]))
        elif role == "latency diagnostic captures":
            game = Path(entry["path"]).name.split(".")[0]
            planned = next(g for g in plan["games"] if g["id"] == game)
            cost = costs_for(planned["scenario_id"], maps[planned["scenario_id"]])
            for capture in lines(path):
                memory = Memory(deployment_sent=bool(capture["memory"]["deployment_sent"]))
                compare(tally, role, f"{game} seat {capture['seat']} decision {capture['decision']}",
                        agents_for(capture["seat"], capture["faction"], cost, memory),
                        typed_json.decode(capture["observation"]))
        else:
            state = json.loads(path.read_text(encoding="utf-8"))
            memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
            compare(tally, role, state["name"],
                    agents_for(state["seat"], state["faction"], costs_for(state["scenario_id"], state["map_id"]), memory),
                    typed_json.decode(state["observation"]))
        if tally.by_role[role]["decisions"] - before != entry["decisions"]:
            raise SystemExit(f"{entry['path']}: compared {tally.by_role[role]['decisions'] - before} decisions, "
                             f"pinned {entry['decisions']}")
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(tally.differences, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    totals = {k: sum(v[k] for v in tally.by_role.values()) for k in FIELDS}
    if totals["decisions"] != registration["corpus"]["decisions_total"]:
        raise SystemExit(f"compared {totals['decisions']} decisions, pinned {registration['corpus']['decisions_total']}")
    return {"schema": SCHEMA, "remediation_id": rr.REMEDIATION_ID, "corpus_sha256": registration["corpus_sha256"],
            "baseline_v1_source_sha256": rr.PARENT["policy_source_sha256"],
            "candidate_source_sha256": policy_source_digest(sources=rr.candidate_sources())[0],
            "semantic_trace": rr.SEMANTIC_TRACE, "by_role": dict(sorted(tally.by_role.items())), "totals": totals,
            "unexplained_differences": len(tally.differences)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    print(json.dumps(result["totals"]), "unexplained:", result["unexplained_differences"])
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0 if result["unexplained_differences"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
