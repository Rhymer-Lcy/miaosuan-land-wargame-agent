"""Counterfactual replay of the launcher-dependent shoot-reservation candidate against baseline-v2.

    python scripts/replay_launcher_counterfactual.py [--check]

No engine is involved. Inputs (private, git-ignored):

* D1, the residual-516 diagnostic's 32 games of 1930331196 C3 under baseline-v2 on runtime-r2: every captured
  pre-step snapshot (the policy seat's observation, memory, emitted actions and trace digest, and the all-seeing
  observation), and the compact log of every step (submitted batch, feedback, judge_info records, units gone);
* D2, the replay corpus pinned by the routing remediation: 8 recorded baseline-v0 games (C1, both seats), every
  decision's observation and recorded actions; baseline-v2's decisions on these states are reconstructed by
  replay and verified (baseline-v0 replays the recorded decision exactly; every unit on which baseline-v2 differs
  from baseline-v0 carries baseline-v2's own occupation-suppression or shoot-reservation record).

Two replays. The faithful candidate decides on each seat observation exactly as captured. The information-augmented
reference is NOT a candidate: it decides on the seat observation with every enemy operator's ``launcher`` taken
from a view the seat does not have (D1: the all-seeing snapshot; D2: the opposing seat's own view at the same
step), to measure what the rule would do if the relation were observable. Both are compared with baseline-v2 by
``miaosuan_agent.evaluation.launcher_counterfactual.compare``. For the reference, each suppressed baseline-v2 shot
is classified by what happened to its launcher in the recorded trajectory (O1 removed in that step, O2 survived,
O3 unavailable or not comparable), and D1's compact logs give the same exposure over every step. The public output
holds aggregate counts only; ``--check`` rebuilds it and compares.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.evaluation import launcher_counterfactual as lc  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402
from miaosuan_agent.experiments.launcher_reservation import CANDIDATE_ID, LauncherReservationPolicy  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

PLAN_ID = "launcher-dependency-counterfactual-1"
OUT = REPO_ROOT / "evaluation" / PLAN_ID / "counterfactual.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "launcher" / "counterfactual-private.json"
D1 = REPO_ROOT / "local" / "evaluation" / rd.DIAGNOSTIC_ID
CORPUS = REPO_ROOT / "evaluation" / rr.REMEDIATION_ID / "corpus.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
SCHEMA = "miaosuan-launcher-counterfactual/1"
V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
CANDIDATE_SOURCES = V2_SOURCES + ("experiments/launcher_reservation.py",)
SHOOT, MOVE, OCCUPY = 2, 1, 5


def costs_for(root: Path, scenario_id: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(root / scenario_id / "Data", scenario_id, map_id).cost)


def augmented(raw: Mapping[str, Any], faction: int, relations: Mapping[int, Any]) -> Dict[str, Any]:
    """The seat observation with each enemy operator's launcher taken from ``relations`` (not visible to the seat)."""
    result = dict(raw)
    result["operators"] = [dict(u, launcher=relations.get(u["obj_id"])) if u.get("color") != faction else u
                           for u in raw["operators"]]
    return result


def action_mix(actions: List[Mapping[str, Any]]) -> collections.Counter:
    return collections.Counter({SHOOT: "shoot", MOVE: "move", OCCUPY: "occupy"}.get(int(a["type"]), "other")
                               for a in actions if "obj_id" in a)


class Tally:
    """Counts of one replay over one corpus."""

    def __init__(self) -> None:
        self.counts: collections.Counter = collections.Counter()
        self.categories = {c: 0 for c in lc.CATEGORIES}
        self.units = collections.Counter()
        self.problems: List[Dict[str, Any]] = []
        self.direct: List[Dict[str, Any]] = []
        self.baseline_mix: collections.Counter = collections.Counter()
        self.candidate_mix: collections.Counter = collections.Counter()

    def add(self, where: Dict[str, Any], comparison: lc.LauncherComparison, first: Any, second: Any) -> None:
        self.counts["decisions"] += 1
        self.counts["changed"] += not comparison.identical
        self.counts["unexplained"] += not comparison.explained
        self.counts["excluded_options"] += comparison.excluded_options
        self.counts["units_with_unchanged_selection"] += comparison.unchanged_units_with_exclusions
        self.counts["contract_errors"] += second.trace.error is not None
        self.counts["gate_rejections"] += len(second.trace.rejected)
        self.counts["baseline_shots"] += comparison.baseline_shots
        self.counts["candidate_shots"] += comparison.candidate_shots
        if not comparison.identical:
            self.baseline_mix.update(action_mix(list(first.actions)))
            self.candidate_mix.update(action_mix(list(second.actions)))
        if comparison.category:
            self.categories[comparison.category] += 1
        for key, value in comparison.units.items():
            self.units[key] += value
        for item in comparison.direct:
            self.direct.append({**where, **item})
        if not comparison.explained:
            self.problems.append({**where, "problem": comparison.problem})

    def summary(self) -> Dict[str, Any]:
        return {**dict(sorted(self.counts.items())), "categories": dict(self.categories),
                "units": {k: self.units[k] for k in ("alternate-target", "fallback-occupy", "fallback-move", "fallback-none",
                                                      "secondary", "unexplained")},
                "suppressed_emitted_shots": len(self.direct),
                "action_mix_in_changed_decisions": {"baseline": dict(sorted(self.baseline_mix.items())),
                                                    "candidate": dict(sorted(self.candidate_mix.items()))}}


def compare(raw: Mapping[str, Any], seat: int, faction: int, costs: MoveCosts, policies: Tuple[Any, Any],
            memory: Memory) -> Tuple[lc.LauncherComparison, Any, Any]:
    return lc.compare(raw, seat, faction, policies[0], policies[1], lambda: ShootReservationPolicy(costs), memory)


# ----------------------------------------------------------------------------------------------
# D1: the residual-516 diagnostic


def d1_games() -> List[str]:
    manifest = json.loads((REPO_ROOT / "evaluation" / rd.DIAGNOSTIC_ID / "manifest.json").read_text(encoding="utf-8"))
    return [g["game_id"] for g in manifest["games"]], manifest


def d1(faithful: Tally, reference: Tally, fidelity: collections.Counter, h4: Dict[str, Any]) -> Dict[str, Any]:
    games, manifest = d1_games()
    scenario = manifest["scenarios"][0]
    costs = costs_for(D1 / "data", scenario["scenario_id"], scenario["map_id"])
    events = {(f["game"], f["k"]): f for f in json.loads((D1 / "analysis" / "facts.json").read_text(encoding="utf-8"))["facts"]}
    h4.update({"diagnostic_events": len(events), "replayable": 0, "faithful_suppressed": 0, "reference_suppressed": 0})
    outcome_counts: collections.Counter = collections.Counter()
    for game in games:
        windows = pickle.loads((D1 / "capture" / f"{game}.windows.pkl").read_bytes())
        compact = json.loads((D1 / "capture" / f"{game}.capture.json").read_text(encoding="utf-8"))
        snaps = {s["k"]: s for e in windows["events"] for s in e["window"]}
        snaps.update({s["k"]: s for s in windows["samples"]})
        for k, snap in sorted(snaps.items()):
            g = pickle.loads(snap["global"])
            relations = {u["obj_id"]: u.get("launcher") for u in g["operators"]}
            for seat, entry in sorted(snap["seats"].items()):
                raw = pickle.loads(entry["observation"])
                memory = pickle.loads(entry["memory"])
                where = {"corpus": "D1", "game": game, "k": k, "seat": seat}
                baseline = ShootReservationPolicy(costs).decide(Observation.from_raw(raw, Origin.ENGINE), seat,
                                                                entry["faction"], memory)
                exact = (rd.plain([dict(a) for a in baseline.actions]) == entry["actions"]
                         and digest(baseline.trace) == entry["trace"] and baseline.memory == memory)
                fidelity["D1 decisions"] += 1
                fidelity["D1 baseline-v2 exact"] += exact
                if not exact:
                    fidelity["D1 excluded: baseline-v2 not reproduced"] += 1
                    continue
                result = compare(raw, seat, entry["faction"], costs,
                                 (ShootReservationPolicy(costs), LauncherReservationPolicy(costs)), memory)
                faithful.add(where, *result)
                view = augmented(raw, entry["faction"], relations)
                other = compare(view, seat, entry["faction"], costs,
                                (ShootReservationPolicy(costs), LauncherReservationPolicy(costs)), memory)
                fidelity["D1 baseline-v2 unchanged by the augmentation"] += tuple(other[1].actions) == tuple(baseline.actions)
                reference.add(where, *other)
                step = compact["steps"][k]
                for item in other[0].direct:
                    o_class = "O1" if item["launcher"] in step["gone"] else "O2"
                    item["o_class"] = o_class
                    outcome_counts[o_class] += 1
                event = events.get((game, k))
                if event is not None:
                    h4["replayable"] += 1
                    refused = {"type": SHOOT, "obj_id": event["actor"], "target_obj_id": event["target"]}

                    def keeps(decision: Any) -> bool:
                        return any(int(a["type"]) == SHOOT and a.get("obj_id") == refused["obj_id"]
                                   and a.get("target_obj_id") == refused["target_obj_id"] for a in decision.actions)
                    h4["faithful_suppressed"] += not keeps(result[2])
                    h4["reference_suppressed"] += not keeps(other[2])
    return {"reference_o_classes": dict(sorted(outcome_counts.items()))}


def d1_exposure() -> Dict[str, Any]:
    """Every step of the 32 games: baseline-v2's emitted shots that the rule would meet, with the launcher's fate."""
    games, manifest = d1_games()
    scenario = manifest["scenarios"][0]
    units = json.loads((D1 / "data" / scenario["scenario_id"] / "Data" / "scenarios" /
                        f"{scenario['scenario_id']}.json").read_text(encoding="utf-8"))["operators"]
    counts: collections.Counter = collections.Counter()
    signals: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for game in games:
        compact = json.loads((D1 / "capture" / f"{game}.capture.json").read_text(encoding="utf-8"))
        launcher = {u["obj_id"]: u.get("launcher") for u in units}
        blood = {u["obj_id"]: u.get("blood") for u in units}
        counts["steps"] += len(compact["steps"])
        for step in compact["steps"]:
            reserved: Dict[int, Dict[str, Any]] = {}
            first = True
            for item in step["batch"]:
                action = item["action"]
                if action.get("type") != SHOOT:
                    continue
                target = action.get("target_obj_id")
                owner = launcher.get(target)
                if target not in reserved and owner in reserved:
                    counts["exposed shots"] += 1
                    counts["exposed shots, first in step" if first else "exposed shots, later in step"] += 1
                    first = False
                    o_class = "O1" if owner in step["gone"] else "O2"
                    counts[o_class] += 1
                    codes = [rd.feedback_code(f) for f in step["feedback"]
                             if rd.refusals.same_action(f.get("message") or {}, action)]
                    judged = any(r.get("target_obj_id") == target and r.get("att_obj_id") == action.get("obj_id")
                                 for r in step["judge_new"])
                    fate = ("refused 516" if codes and codes[0] == rd.TRIGGER_CODE else
                            f"refused {codes[0]}" if codes and codes[0] is not None else
                            "accepted, judged" if judged else "accepted, no record")
                    counts[f"{o_class}: dependent shot {fate}"] += 1
                    counts[f"{o_class}: dependent {'removed' if target in step['gone'] else 'survived'} in the step"] += 1
                    signals["launcher blood at step start"][f"{blood.get(owner)} -> {o_class}"] += 1
                    signals["weapon of the shot at the launcher"][f"{reserved[owner]['weapon_id']} -> {o_class}"] += 1
                if target not in reserved:
                    reserved[target] = action
            for unit, diff in step["changed"].items():
                if "launcher" in diff:
                    launcher[int(unit)] = diff["launcher"][1]
                if "blood" in diff:
                    blood[int(unit)] = diff["blood"][1]
    overlap = {}
    for name, table in signals.items():
        values = collections.defaultdict(set)
        for key in table:
            value, o_class = key.split(" -> ")
            values[value].add(o_class)
        overlap[name] = {"values": len(values), "values_with_both_outcomes": sum(1 for v in values.values() if len(v) > 1),
                         "values_with_one_outcome": sum(1 for v in values.values() if len(v) == 1)}
    by_blood: Dict[str, Dict[str, int]] = collections.defaultdict(dict)
    for key, n in signals["launcher blood at step start"].items():
        value, o_class = key.split(" -> ")
        by_blood[value][o_class] = n
    return {**dict(sorted(counts.items())), "signal_overlap": overlap,
            "launcher_blood_at_step_start": {v: dict(sorted(c.items())) for v, c in sorted(by_blood.items())}}


# ----------------------------------------------------------------------------------------------
# D2: the baseline-v0 replay corpus


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def explained_against_v0(v0: Any, v2: Any) -> bool:
    """Every unit on which baseline-v2 differs from baseline-v0 carries baseline-v2's own reservation record."""
    old = {a.get("obj_id", "seat"): dict(a) for a in v0.actions}
    new = {a.get("obj_id", "seat"): dict(a) for a in v2.actions}
    payload = v2.trace.to_dict()
    marked = {s["obj_id"] for s in payload.get("suppressed", [])}
    marked |= {e["obj_id"] for e in payload.get("shoot_reserved", []) if e["effect"] != "unchanged"}
    return all(old.get(k) == new.get(k) or k in marked for k in set(old) | set(new))


def d2(faithful: Tally, reference: Tally, fidelity: collections.Counter) -> Dict[str, Any]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    outcome: collections.Counter = collections.Counter()
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        stream = lines(path)
        header = next(stream)
        costs = costs_for(DATA, header["scenario_id"], header["map_id"])
        rows = list(stream)
        by_step: Dict[int, Dict[int, Dict[str, Any]]] = collections.defaultdict(dict)
        for row in rows:
            by_step[row["step"]][row["faction"]] = row
        state: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            seat, faction = row["seat"], row["faction"]
            if seat not in state:
                state[seat] = {"v0": BaselinePolicy(costs), "v2": ShootReservationPolicy(costs),
                               "candidate": LauncherReservationPolicy(costs), "reference": LauncherReservationPolicy(costs),
                               "v2_ref": ShootReservationPolicy(costs), "memory_v0": Memory(), "memory": Memory()}
            s = state[seat]
            raw = typed_json.decode(row["observation"])
            where = {"corpus": "D2", "game": header["game_id"], "step": row["step"], "seat": seat}
            fidelity["D2 decisions"] += 1
            try:
                v0 = s["v0"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["memory_v0"])
            except ContractError:
                fidelity["D2 excluded: contract error"] += 1
                continue
            s["memory_v0"] = v0.memory
            exact = [dict(a) for a in v0.actions] == [dict(a) for a in row["actions"]] and digest(v0.trace) == row["trace_digest"]
            fidelity["D2 baseline-v0 exact"] += exact
            if not exact:
                fidelity["D2 excluded: baseline-v0 not reproduced"] += 1
                continue
            result = compare(raw, seat, faction, costs, (s["v2"], s["candidate"]), s["memory"])
            v2_decision = result[1]
            explained = explained_against_v0(v0, v2_decision)
            fidelity["D2 baseline-v2 explained against baseline-v0"] += explained
            if not explained:
                fidelity["D2 excluded: baseline-v2 difference unexplained"] += 1
                s["memory"] = v2_decision.memory
                continue
            faithful.add(where, *result)
            opponent = by_step.get(row["step"], {}).get(1 - faction)
            relations = {}
            if opponent is not None:
                opp = typed_json.decode(opponent["observation"])
                relations = {u["obj_id"]: u.get("launcher") for u in opp["operators"] if u.get("color") == 1 - faction}
            view = augmented(raw, faction, relations)
            other = compare(view, seat, faction, costs, (s["v2_ref"], s["reference"]), s["memory"])
            fidelity["D2 baseline-v2 unchanged by the augmentation"] += tuple(other[1].actions) == tuple(v2_decision.actions)
            reference.add(where, *other)
            comparable = [dict(a) for a in row["actions"]] == [dict(a) for a in v2_decision.actions]
            after = by_step.get(row["step"] + 1, {}).get(1 - faction)
            present = None
            if after is not None:
                obs = typed_json.decode(after["observation"])
                present = {u["obj_id"] for u in obs["operators"]} | {u["obj_id"] for u in obs.get("passengers") or []}
            for item in other[0].direct:
                if not comparable or present is None:
                    o_class = "O3"
                else:
                    o_class = "O1" if item["launcher"] not in present else "O2"
                item["o_class"] = o_class
                outcome[o_class] += 1
                if o_class == "O2":
                    outcome["O2: dependent " + ("survived" if item["suppressed"]["target_obj_id"] in present
                                                else "removed") + " in the step"] += 1
            s["memory"] = v2_decision.memory
    return {"reference_o_classes": dict(sorted(outcome.items()))}


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    fidelity: collections.Counter = collections.Counter()
    tallies = {name: Tally() for name in ("D1 faithful", "D1 reference", "D2 faithful", "D2 reference")}
    h4: Dict[str, Any] = {}
    d1_out = d1(tallies["D1 faithful"], tallies["D1 reference"], fidelity, h4)
    exposure = d1_exposure()
    d2_out = d2(tallies["D2 faithful"], tallies["D2 reference"], fidelity)
    faithful = [tallies["D1 faithful"], tallies["D2 faithful"]]
    changed = sum(t.counts["changed"] for t in faithful)
    gate = {
        "G1 no secondary interaction (C6)": sum(t.categories["C6"] for t in faithful) == 0,
        "G2 nothing unexplained (C7)": sum(t.categories["C7"] + t.counts["unexplained"] for t in faithful) == 0,
        "G3 every replayable diagnostic H4 refusal suppressed": h4["replayable"] > 0 and h4["faithful_suppressed"] == h4["replayable"],
        "G4 no contract or gate regression": sum(t.counts["contract_errors"] + t.counts["gate_rejections"] for t in faithful) == 0,
        "G5 seat-local observation only": True,  # by construction; tests.test_launcher_reservation.IdentityTest
        "G6 opportunity cost measured": True,  # O1/O2/O3 below; vacuous for the faithful candidate when it never fires
        "G7 a meaningful A/B question remains": changed > 0,
    }
    fidelity_ok = (fidelity["D1 decisions"] > 0 and fidelity["D1 baseline-v2 exact"] == fidelity["D1 decisions"]
                   and fidelity["D2 baseline-v0 exact"] > 0)
    disposition = ("BLOCKED" if not fidelity_ok else "PREREGISTER" if all(gate.values()) else "DO NOT PREREGISTER")
    public = {
        "schema": SCHEMA, "plan_id": PLAN_ID,
        "baseline": {"identity": "baseline-v2", "policy_source_sha256": policy_source_digest(sources=V2_SOURCES)[0]},
        "candidate": {"identity": CANDIDATE_ID, "policy_source_sha256": policy_source_digest(sources=CANDIDATE_SOURCES)[0],
                      "pinned": False},
        "fidelity": dict(sorted(fidelity.items())),
        "faithful": {"D1": tallies["D1 faithful"].summary(), "D2": tallies["D2 faithful"].summary()},
        "information_augmented_reference": {"note": "not a candidate: uses relations the seat cannot observe",
                                            "D1": {**tallies["D1 reference"].summary(), **d1_out},
                                            "D2": {**tallies["D2 reference"].summary(), **d2_out},
                                            "D1_every_step": exposure},
        "h4": h4, "gate": gate, "disposition": disposition,
    }
    private = {"problems": [p for t in tallies.values() for p in t.problems],
               "reference_direct": tallies["D1 reference"].direct + tallies["D2 reference"].direct,
               "faithful_direct": tallies["D1 faithful"].direct + tallies["D2 faithful"].direct}
    return public, private


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    public, private = build()
    text = json.dumps(public, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("counterfactual identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_text(json.dumps(private, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}: {public['disposition']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
