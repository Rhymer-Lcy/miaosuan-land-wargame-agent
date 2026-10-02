"""T7 design study: POST HOC descriptions after the selection (``docs/T7_DESIGN.md``); they change no score or gate.

    python scripts/t7_posthoc.py [--check]

Private inputs as in ``scripts/t7_study.py`` (H0 and the study's private activation records). Three descriptions:

1. trigger funnels of A1 and A3 on H0: how many ``baseline-v2`` move orders pass each condition in turn, to tell an
   empty trigger from a defect (a diagnostic of the implementation);
2. A2's H0 activations: how long each first-activated unit then stays idle and stationary in the recorded trajectory,
   and when and by which channel its benefit witness occurs;
3. DERIVED: over each first-activated unit's idle period, from 75 steps after the activation (a documented transition
   complete) to its end, the steps in which the opposing view lists the unit, and of these the steps in which an
   opposing unit stands within the documented concealed observation distance. Documented distances: ground and
   helicopter observers see infantry at 10 and vehicles at 25 hexes, halved against a concealed unit; unmanned aerial
   vehicles and loitering munitions see ground units at 2, halved only for concealed infantry; concealment does not
   help a vehicle lower than its observer (map elevation). Assumptions: line of sight unchanged; terrain halving
   ignored on both sides (whether it stacks with concealment is undocumented); the opponent as recorded.

Public output ``evaluation/t7-design-1/posthoc.json`` (aggregates); private rows in ``local/diagnostics/t7/``.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, MoveMode, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory  # noqa: E402
from miaosuan_agent.decision.routing import Router  # noqa: E402
from miaosuan_agent.evaluation import t7_audit as ta  # noqa: E402
from miaosuan_agent.evaluation import t7_candidates as tc  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "t7-design-1" / "posthoc.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "t7"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"


def games() -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    out = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            out.append((header, [json.loads(line) for line in handle]))
    return out


def funnels(corpus: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]) -> Dict[str, Any]:
    a1: collections.Counter = collections.Counter()
    a3: collections.Counter = collections.Counter()
    savings: List[float] = []
    for header, rows in corpus:
        sid = header["scenario_id"]
        costs = MoveCosts.from_raw(sdk_data.load_inputs(DATA / sid / "Data", sid, header["map_id"]).cost)
        router = Router(costs)
        policies: Dict[int, Any] = {}
        memories: Dict[int, Memory] = {}
        for row in rows:
            seat, faction = row["seat"], row["faction"]
            policies.setdefault(seat, ShootReservationPolicy(costs))
            raw = typed_json.decode(row["observation"])
            decision = policies[seat].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction,
                                             memories.get(seat, Memory()))
            memories[seat] = decision.memory
            units, listed, seen = ta.operators(raw), ta.listings(raw), ta.enemy_seen(raw, faction)
            for act in decision.actions:
                unit = units.get(act.get("obj_id"))
                if act.get("type") != 1 or unit is None:
                    continue
                path = list(act["move_path"])
                if unit.get("type") == 2 and unit.get("sub_type") != 3:
                    a1["1 vehicle move orders"] += 1
                    if seen:
                        a1["2 stopped: an enemy seen"] += 1
                        continue
                    if unit.get("passenger_ids"):
                        a1["3 stopped: carries passengers"] += 1
                        continue
                    march = router.shortest_paths(unit["cur_hex"], MoveMode.VEHICLE_MARCH, tc.roadblocks(raw))
                    if path[-1] not in march.cost:
                        a1["4 stopped: destination not reachable in march mode"] += 1
                        continue
                    t0 = tc.path_seconds(costs, MoveMode.VEHICLE, unit["cur_hex"], path, 720.0 / unit["basic_speed"])
                    saving = t0 - (tc.MARCH_SECONDS_PER_COST * march.cost[path[-1]] + tc.A1_OVERHEAD)
                    savings.append(saving)
                    a1["5 reached the saving test"] += 1
                    a1["6 saving positive"] += saving > 0
                if unit.get("type") == 1:
                    a3["1 infantry move orders"] += 1
                    states, _ = ta.target_states(listed.get(unit["obj_id"], {}).get(6))
                    if 2 not in states:
                        a3["2 stopped: charge not listed"] += 1
                    elif len(path) > tc.A3_MAX_HEXES:
                        a3["3 stopped: more than two hexes"] += 1
                    elif path[-1] not in tc.cities(raw):
                        a3["4 stopped: not to an objective"] += 1
                    elif unit.get("tire") != 0 or seen:
                        a3["5 stopped: tired or an enemy seen"] += 1
                    else:
                        a3["6 would activate"] += 1
    savings.sort()
    return {"A1": dict(sorted(a1.items())), "A3": dict(sorted(a3.items())),
            "A1_savings_seconds": {"n": len(savings), "min": savings[0], "max": savings[-1]} if savings else None}


def concealed_distance(observer: Mapping[str, Any], target: Mapping[str, Any], elev) -> Any:
    d = tc.observation_distance(observer, target.get("type"))
    if d is None:
        return None
    if target.get("type") == 2:
        if (observer.get("type"), observer.get("sub_type")) in tc.SHORT_SIGHTED:
            return d
        if elev(target["cur_hex"]) < elev(observer["cur_hex"]):
            return d
    return d // 2


def a2(corpus: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]],
       activations: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    acts = [a for a in activations if a["population"] == "H0" and a["candidate"] == "A2"]
    by_game = collections.defaultdict(list)
    for act in acts:
        by_game[act["game"]].append(act)
    rows_out: List[Dict[str, Any]] = []
    for header, rows in corpus:
        if header["game_id"] not in by_game:
            continue
        sid = header["scenario_id"]
        grid = sdk_data.load_inputs(DATA / sid / "Data", sid, header["map_id"]).basic["map_data"]

        def elev(h: int, grid=grid) -> Any:
            return grid[h // 100][h % 100]["elev"]

        steps: Dict[int, Dict[int, Tuple[Dict[str, Any], set]]] = collections.defaultdict(dict)
        for row in rows:
            steps[row["faction"]][row["step"]] = (typed_json.decode(row["observation"]),
                                                  {x.get("obj_id") for x in row["actions"]})
        for act in by_game[header["game_id"]]:
            mine, theirs = steps[act["faction"]], steps[1 - act["faction"]]
            idle, witness_after, channel, observed, still = 0, None, None, 0, 0
            k = act["k"] + 1
            ended = "game end"
            while k in mine:
                raw, acted = mine[k]
                unit = ta.operators(raw).get(act["unit"])
                if unit is None:
                    ended = "unit gone"
                    break
                if unit.get("stop") != 1 or ta.has_path(unit) is not False or act["unit"] in acted:
                    ended = "acted or moved"
                    break
                idle += 1
                other = theirs.get(k)
                judged = {r.get("target_obj_id") for r in (raw.get("judge_info") or ())}
                if other is not None:
                    judged |= {r.get("target_obj_id") for r in (other[0].get("judge_info") or ())}
                listed_by_them = other is not None and act["unit"] in ta.operators(other[0])
                if witness_after is None and (act["unit"] in judged or listed_by_them):
                    witness_after = k - act["k"]
                    channel = "judge_info" if act["unit"] in judged else "opposing view"
                if listed_by_them and k - act["k"] >= tc.TRANSITION and not act["record"]["repeat"]:
                    observed += 1
                    observers = [u for u in ta.operators(other[0]).values() if u.get("color") == 1 - act["faction"]]
                    if any((r := concealed_distance(o, unit, elev)) is not None
                           and tc.hex_distance(o["cur_hex"], unit["cur_hex"]) <= r for o in observers):
                        still += 1
                k += 1
            rows_out.append({"game": act["game"], "unit": act["unit"], "k": act["k"], "repeat": act["record"]["repeat"],
                             "archetype": act["archetype"], "idle_after": idle, "ended": ended,
                             "witness_after": witness_after, "channel": channel, "witness": act["witness"],
                             "observed_after_transition": observed, "still_observable_if_concealed": still})
    first = [r for r in rows_out if not r["repeat"]]
    idle = sorted(r["idle_after"] for r in first)
    seen_units = [r for r in first if r["observed_after_transition"]]
    summary = {
        "activations": len(rows_out), "first_activations": len(first),
        "first_idle_after_steps": {"min": idle[0], "max": idle[-1]} if idle else None,
        "first_idle_at_least_75_steps": sum(1 for v in idle if v >= tc.TRANSITION),
        "first_ended_by": dict(sorted(collections.Counter(r["ended"] for r in first).items())),
        "witness_activations": sum(1 for r in rows_out if r["witness"]),
        "witness_recomputed_agrees": all((r["witness_after"] is not None) == bool(r["witness"]) for r in rows_out),
        "witness_at_or_after_75_steps": sum(1 for r in rows_out if r["witness_after"] is not None
                                            and r["witness_after"] >= tc.TRANSITION),
        "witness_channels": dict(sorted(collections.Counter(r["channel"] for r in rows_out if r["channel"]).items())),
        "derived": {"observed_unit_steps_after_transition": sum(r["observed_after_transition"] for r in first),
                    "still_observable_if_concealed": sum(r["still_observable_if_concealed"] for r in first),
                    "units_observed_after_transition": len(seen_units),
                    "units_never_observable_if_concealed": sum(1 for r in seen_units
                                                               if r["still_observable_if_concealed"] == 0),
                    "units_always_observable_if_concealed": sum(1 for r in seen_units if r["still_observable_if_concealed"]
                                                                == r["observed_after_transition"])},
    }
    return summary, rows_out


def build() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    private = json.loads((PRIVATE / "study-private.json").read_text(encoding="utf-8"))
    corpus = games()
    summary, rows = a2(corpus, private["activations"])
    public = {"schema": "miaosuan-t7-posthoc/1", "study_id": "t7-design-1",
              "status": "POST HOC: after the selection; changes no score, gate or disposition",
              "funnels": funnels(corpus), "a2_h0": summary}
    return public, {"a2_rows": rows}


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    public, private = build()
    text = dump(public)
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("posthoc identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    (PRIVATE / "posthoc-private.json").write_text(dump(private), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
