"""Counterfactual replay: baseline-v1 on runtime r1 against the shoot-target-reservation candidate.

    python scripts/replay_shoot_counterfactual.py [--check]

No engine is involved. The inputs are the private canonical corpus pinned by the routing remediation
(``evaluation/routing-remediation-1/corpus.json``, every file checked against its digest): the recorded
games of the replay corpus, replayed seat by seat with persistent policies and memory as in a game; the
captured decisions of the latency diagnostic (both seats); the latency diagnostic's states. For every
decision both policies decide on the same observation, and
``miaosuan_agent.evaluation.shoot_counterfactual.compare`` checks the candidate against the oracle and
classifies every changed unit. The public output holds aggregate counts only
(``evaluation/baseline-v2-candidate-shoot-target-reservation/counterfactual-replay.json``); the private
output lists every unexplained state. ``--check`` rebuilds the public output and compares.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts  # noqa: E402
from miaosuan_agent.decision import Memory  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import shoot_counterfactual as sc  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.routing_bounded import BoundedRoutingPolicy  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import CANDIDATE_ID, ShootReservationPolicy  # noqa: E402

CORPUS = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID / "corpus.json"
OUT = REPO_ROOT / "evaluation" / CANDIDATE_ID / "counterfactual-replay.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "shoot" / "counterfactual-problems.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
SCHEMA = "miaosuan-shoot-counterfactual-replay/1"
CANDIDATE_FILE = "experiments/shoot_reservation.py"


class Tally:
    def __init__(self) -> None:
        self.by_role: Dict[str, Counter] = {}
        self.problems: List[Dict[str, Any]] = []

    def add(self, role: str, where: str, comparison: sc.ShootComparison) -> None:
        counts = self.by_role.setdefault(role, Counter())
        counts["states"] += 1
        counts["identical"] += comparison.identical
        counts["changed"] += not comparison.identical
        counts["unexplained_states"] += not comparison.explained
        for key in ("baseline_shots", "baseline_duplicate_shots", "candidate_shots", "candidate_duplicate_shots",
                    "displaced_units", "unchanged_units_with_exclusions", "excluded_options", "non_shoot_differences"):
            counts[key] += getattr(comparison, key)
        counts["states_with_baseline_duplicates"] += bool(comparison.baseline_duplicate_shots)
        counts["states_with_exclusions"] += bool(comparison.displaced_units or comparison.unchanged_units_with_exclusions)
        counts["first_shot_changed"] += comparison.first_shot_changed
        for label, n in comparison.classes.items():
            counts[f"class_{label}"] += n
        for kind in comparison.changed_types:
            counts[f"changed_baseline_type_{kind}"] += 1
        if not comparison.explained:
            self.problems.append({"state": where, "problem": comparison.problem})


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def costs_for(scenario_id: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost)


def pair(costs: MoveCosts) -> Tuple[Any, Any]:
    return BoundedRoutingPolicy(costs), ShootReservationPolicy(costs)


def decide(tally: Tally, role: str, where: str, raw: Any, seat: int, faction: int, policies: Tuple[Any, Any],
           costs: MoveCosts, memories: Tuple[Memory, Memory]) -> Tuple[Memory, Memory]:
    comparison, first, second = sc.compare(raw, seat, faction, policies[0], policies[1],
                                           lambda: BoundedRoutingPolicy(costs), memories[0], memories[1])
    tally.add(role, where, comparison)
    return first.memory, second.memory


def build() -> Dict[str, Any]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    study = json.loads((REPO_ROOT / "evaluation" / "baseline-v1-variance-study-1" / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((REPO_ROOT / "evaluation" / "latency-diagnostic-1" / "plan.json").read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in study["scenarios"]}
    tally = Tally()
    for entry in corpus["files"]:
        path = REPO_ROOT / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        role = entry["role"]
        before = tally.by_role.get(role, Counter())["states"]
        if role == "replay corpus game":
            stream = lines(path)
            header = next(stream)
            costs = costs_for(header["scenario_id"], header["map_id"])
            seats: Dict[int, List[Any]] = {}
            for record in stream:
                if record["seat"] not in seats:
                    seats[record["seat"]] = [pair(costs), (Memory(), Memory())]
                policies, memories = seats[record["seat"]]
                seats[record["seat"]][1] = decide(tally, role, f"{header['game_id']} seat {record['seat']} decision "
                                                  f"{record['step']}", typed_json.decode(record["observation"]),
                                                  record["seat"], record["faction"], policies, costs, memories)
        elif role == "latency diagnostic captures":
            game = Path(entry["path"]).name.split(".")[0]
            planned = next(g for g in plan["games"] if g["id"] == game)
            costs = costs_for(planned["scenario_id"], maps[planned["scenario_id"]])
            for capture in lines(path):
                memory = Memory(deployment_sent=bool(capture["memory"]["deployment_sent"]))
                decide(tally, role, f"{game} seat {capture['seat']} decision {capture['decision']}",
                       typed_json.decode(capture["observation"]), capture["seat"], capture["faction"], pair(costs),
                       costs, (memory, memory))
        else:
            state = json.loads(path.read_text(encoding="utf-8"))
            costs = costs_for(state["scenario_id"], state["map_id"])
            memory = Memory(deployment_sent=bool(state["memory"]["deployment_sent"]))
            decide(tally, role, state["name"], typed_json.decode(state["observation"]), state["seat"], state["faction"],
                   pair(costs), costs, (memory, memory))
        if tally.by_role[role]["states"] - before != entry["decisions"]:
            raise SystemExit(f"{entry['path']}: replayed {tally.by_role[role]['states'] - before} decisions, "
                             f"pinned {entry['decisions']}")
    totals = Counter()
    for counts in tally.by_role.values():
        totals.update(counts)
    if totals["states"] != corpus["decisions_total"]:
        raise SystemExit(f"replayed {totals['states']} decisions, pinned {corpus['decisions_total']}")
    for label in sc.CLASSES:
        totals.setdefault(f"class_{label}", 0)
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(tally.problems, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"schema": SCHEMA, "corpus": {"file": "evaluation/routing-remediation-1/corpus.json",
                                         "sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
                                         "decisions_total": corpus["decisions_total"]},
            "baseline": {"identity": "baseline-v1 on baseline-v1-runtime-r1",
                         "policy_source_sha256": policy_source_digest(sources=rr.candidate_sources())[0]},
            "candidate": {"identity": CANDIDATE_ID, "policy_source_sha256": policy_source_digest(
                sources=rr.candidate_sources() + (CANDIDATE_FILE,))[0]},
            "classes": {"A": "displaced; another, unreserved target shot", "B": "displaced; occupation",
                        "C": "displaced; movement", "D": "displaced; no action",
                        "I": "induced: the inherited occupation reservation reacting to an earlier unit's fallback "
                             "occupation", "E": "unexplained"},
            "by_role": {role: dict(sorted(counts.items())) for role, counts in sorted(tally.by_role.items())},
            "totals": dict(sorted(totals.items())), "unexplained_states": len(tally.problems)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build()
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    print(json.dumps({k: result["totals"][k] for k in ("states", "identical", "changed", "baseline_duplicate_shots",
                                                       "displaced_units", "class_A", "class_B", "class_C", "class_D",
                                                       "class_I", "class_E", "candidate_duplicate_shots")}),
          "unexplained states:", result["unexplained_states"])
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("OK" if same else "MISMATCH", OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0 if result["unexplained_states"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
