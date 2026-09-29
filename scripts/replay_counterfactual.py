"""Counterfactual replay: baseline-v0 and the occupation-reservation candidate on recorded inputs.

    python scripts/replay_counterfactual.py --corpus DIR [--fixtures DIR] --private FILE --public FILE

For every recorded start-of-step observation (the replay corpus written by
``capture_replay_corpus.py``, plus any private contract fixtures), both policies decide on the same
input with their own memory threaded through the game. First, baseline-v0 must reproduce the
actions and the trace digest recorded when the game was played (fidelity). Then the candidate is
compared with baseline-v0 through ``miaosuan_agent.evaluation.counterfactual``: every state is
identical, or differs exactly as the registered reservation predicts, or is an unexplained delta.
The private output lists every unexplained or unfaithful state; the public output holds aggregate
counts only. This is a comparison of policies, not of engine outcomes.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import BaselinePolicy, Memory, digest  # noqa: E402
from miaosuan_agent.evaluation import counterfactual as cf  # noqa: E402
from miaosuan_agent.evaluation.identity import OCCUPY_RESERVATION_SOURCES, policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.occupy_reservation import OccupyReservationPolicy  # noqa: E402

SCHEMA = "miaosuan-counterfactual-replay/1"


class Tally:
    def __init__(self) -> None:
        self.states = self.identical = self.differing = self.unexplained = 0
        self.fidelity_checked = self.fidelity_mismatches = 0
        self.suppressed = self.states_with_suppression = self.v0_duplicates = 0
        self.changed_types: Counter = Counter()
        self.problems: List[Dict[str, Any]] = []

    def add(self, label: str, comparison: cf.StateComparison) -> None:
        self.states += 1
        self.identical += comparison.identical
        self.differing += not comparison.identical
        self.suppressed += len(comparison.suppressed)
        self.states_with_suppression += bool(comparison.suppressed)
        self.v0_duplicates += len(comparison.duplicates)
        self.changed_types.update(str(t) for t in comparison.changed_types)
        if not comparison.explained:
            self.unexplained += 1
            self.problems.append({"state": label, "problem": comparison.problem})


def replay_sequence(records: Iterable[Mapping[str, Any]], costs: MoveCosts, tally: Tally, label: str,
                    check_fidelity: bool = True) -> None:
    """Replay one game's decisions (records in order, any number of seats) through both policies."""
    policies: Dict[int, Any] = {}
    for record in records:
        seat = record["seat"]
        if seat not in policies:
            policies[seat] = [BaselinePolicy(costs), OccupyReservationPolicy(costs), Memory(), Memory()]
        v0, candidate, m0, m1 = policies[seat]
        raw = typed_json.decode(record["observation"])
        comparison, first, second = cf.compare(raw, seat, record["faction"], v0, candidate, m0, m1)
        policies[seat][2], policies[seat][3] = first.memory, second.memory
        where = f"{label} step {record['step']} seat {seat}"
        tally.add(where, comparison)
        if check_fidelity:
            tally.fidelity_checked += 1
            if [dict(a) for a in first.actions] != record["actions"] or digest(first.trace) != record["trace_digest"]:
                tally.fidelity_mismatches += 1
                tally.problems.append({"state": where, "problem": "baseline-v0 did not reproduce the recorded decision"})


def read_corpus(path: Path) -> Iterator[Mapping[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def fixture_records(root: Path) -> Iterator[Mapping[str, Any]]:
    from miaosuan_agent.contract_capture import load_capture

    for capture in sorted(p.parent for p in root.glob("*/manifest.json")):
        loaded = load_capture(capture)
        for point, slots in sorted(loaded["states"].items()):
            for faction in (0, 1):
                raw = slots[faction]
                view = Observation.from_raw(raw, Origin.ENGINE)
                seat = next(s for s, info in view.role_and_grouping().items() if info.faction == faction)
                yield {"capture": capture.name, "point": point, "map_id": str(loaded["manifest"]["map_id"]),
                       "seat": seat, "faction": faction, "step": point, "observation": typed_json.encode(raw)[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / "baseline-v0",
                        help="work directory holding staged map inputs (for movement costs)")
    parser.add_argument("--private", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    args = parser.parse_args()

    def costs_for(scenario_id: str, map_id: str) -> MoveCosts:
        data = args.work / "data" / scenario_id / "Data"
        return MoveCosts.from_raw(sdk_data.load_cost(sdk_data.map_paths(data, map_id)["cost"]))

    tally = Tally()
    games, sessions = [], []
    for path in sorted(args.corpus.glob("*.jsonl.gz")):
        records = read_corpus(path)
        header = next(records)
        games.append(header["game_id"])
        sessions.append(header["session"])
        replay_sequence(records, costs_for(header["scenario_id"], header["map_id"]), tally, header["game_id"])
    game_states = tally.states
    if args.fixtures and args.fixtures.is_dir():
        by_capture: Dict[str, List[Mapping[str, Any]]] = {}
        for record in fixture_records(args.fixtures):
            by_capture.setdefault(record["capture"], []).append(record)
        for capture, records in sorted(by_capture.items()):
            scenario = json.loads((args.fixtures / capture / "manifest.json").read_text(encoding="utf-8"))["scenario_id"]
            for record in records:
                replay_sequence([record], costs_for(str(scenario), record["map_id"]), tally, f"fixture {capture}",
                                check_fidelity=False)
    public = {
        "schema": SCHEMA,
        "v0_policy_source_sha256": policy_source_digest()[0],
        "candidate_policy_source_sha256": policy_source_digest(sources=OCCUPY_RESERVATION_SOURCES)[0],
        "corpus": {"games": games, "capture_sessions": sessions, "decision_states_from_games": game_states,
                   "decision_states_from_fixtures": tally.states - game_states},
        "decision_states": tally.states,
        "fidelity_checked": tally.fidelity_checked,
        "fidelity_mismatches": tally.fidelity_mismatches,
        "identical": tally.identical,
        "differing": tally.differing,
        "unexplained": tally.unexplained,
        "suppressed_occupations": tally.suppressed,
        "states_with_suppression": tally.states_with_suppression,
        "v0_duplicate_occupation_commands": tally.v0_duplicates,
        "changed_v0_action_types": dict(sorted(tally.changed_types.items())),
    }
    args.private.parent.mkdir(parents=True, exist_ok=True)
    args.private.write_text(json.dumps(dict(public, problems=tally.problems), indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
    args.public.parent.mkdir(parents=True, exist_ok=True)
    args.public.write_text(json.dumps(public, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in public.items() if k != "corpus"}))
    return 0 if not tally.unexplained and not tally.fidelity_mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
