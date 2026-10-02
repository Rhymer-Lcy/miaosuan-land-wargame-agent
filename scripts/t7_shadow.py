"""T7 design study: offline checks of the ``t7-idle-concealment`` shadow (``docs/T7_DESIGN.md``, sections 10 and 14).

    python scripts/t7_shadow.py [--check]

No engine. Private inputs as in ``scripts/t7_study.py``, plus the study's private activation records. For every
decision of H0, H1 and H2 the shadow decides on the recorded seat observation, and:

* an independent ``baseline-v2`` instance decides on the same observation; the shadow's first actions must equal its
  actions exactly (baseline equivalence) and its trace digest must equal theirs;
* in H1 (``baseline-v2`` itself) the recorded actions and trace digest must equal ``baseline-v2``'s; in H2 (the split
  candidate, whose play stage is ``baseline-v2``'s) the recorded play actions must equal them;
* every added action is checked against the raw ``valid_actions`` of the decision (option listed, exact key set), no
  unit receives two actions, nothing is added in deployment;
* the set of activations (game, seat, step, unit) must equal the pool predicate's A2 activations recorded by
  ``scripts/t7_study.py``, an independently written implementation of the same trigger;
* H1 is decided a second time (determinism), once more with operators, options and ``valid_actions`` permuted, and once
  with every observation repeated (the repeat must add nothing); decision latency of the shadow and of the
  independent ``baseline-v2`` instance and the shadow's memory size are measured.

Public output ``evaluation/t7-design-1/shadow.json`` (aggregates; latency figures are measurements of one run and are
excluded from ``--check``).
"""

from __future__ import annotations

import argparse
import collections
import copy
import gzip
import hashlib
import json
import pickle
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.experiments import t7_idle_concealment as sh  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "t7-design-1" / "shadow.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "t7"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
CAPTURES = {"H1": [("t1r-diagnosis-1", "1910631192.C3.b.x01")],
            "H2": [("t1r-diagnosis-1", "1910631192.C3.c.x01"), ("ps1-engine-probe-1", "1930331196.C2.p2")]}
SCHEMA = "miaosuan-t7-shadow/1"
TIMING_KEYS = ("latency_ms",)


def costs_for(scenario_id: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost)


def contract_ok(action: Mapping[str, Any], raw: Mapping[str, Any]) -> bool:
    """Checked on the raw dictionary, independently of the boundary and of the shadow's own check."""
    if set(action) != {"actor", "obj_id", "type", "target_state"} or action["type"] != 6:
        return False
    options = ((raw.get("valid_actions") or {}).get(action["obj_id"]) or {}).get(6) or []
    return any(isinstance(o, dict) and o.get("target_state") == action["target_state"] for o in options)


class Tally:
    def __init__(self) -> None:
        self.c: collections.Counter = collections.Counter()
        self.skipped: collections.Counter = collections.Counter()
        self.activations: set = set()
        self.units: set = set()
        self.shadow_ms: List[float] = []
        self.v2_ms: List[float] = []
        self.max_memory = 0

    def add(self, key: Tuple[str, int, int], faction: int, raw: Mapping[str, Any], shadow: Any, base: Any,
            t_shadow: float, t_v2: float, recorded: Optional[List[Mapping[str, Any]]] = None,
            recorded_trace: Optional[str] = None) -> None:
        game, seat, k = key
        c = self.c
        c["decisions"] += 1
        stage = (raw.get("time") or {}).get("stage")
        c["play decisions" if stage == 2 else "other decisions"] += 1
        same = list(shadow.baseline.actions) == list(base.actions) and digest(shadow.baseline.trace) == digest(base.trace)
        c["baseline-v2 equal"] += same
        c["baseline-v2 differs"] += not same
        n = len(base.actions)
        c["prefix equal"] += list(shadow.actions[:n]) == list(base.actions)
        ids = [a.get("obj_id") for a in shadow.actions if a.get("obj_id") is not None]
        c["a unit with two actions"] += len(ids) != len(set(ids))
        base_units = {a.get("obj_id") for a in base.actions}
        for action in shadow.added:
            c["added"] += 1
            c["contract valid"] += contract_ok(action, raw)
            c["added to a unit baseline-v2 acted on"] += action["obj_id"] in base_units
            c["added outside the play stage"] += stage != 2
            self.activations.add((game, seat, k, action["obj_id"]))
            self.units.add((game, seat, action["obj_id"]))
        if recorded is not None and stage == 2:
            c["recorded play actions compared"] += 1
            c["recorded play actions equal"] += [dict(a) for a in recorded] == [dict(a) for a in base.actions]
        if recorded_trace is not None:
            c["recorded trace compared"] += 1
            c["recorded trace equal"] += recorded_trace == digest(base.trace)
        self.skipped.update(dict(shadow.skipped))
        self.shadow_ms.append(t_shadow * 1000)
        self.v2_ms.append(t_v2 * 1000)
        self.max_memory = max(self.max_memory, len(shadow.memory.last_order))

    def summary(self, pool: set) -> Dict[str, Any]:
        def q(values: List[float], p: float) -> float:
            values = sorted(values)
            return round(values[min(len(values) - 1, int(p * len(values)))], 3)
        return {"counts": dict(sorted(self.c.items())), "skipped_by_reason": dict(sorted(self.skipped.items())),
                "activations": len(self.activations), "units": len(self.units),
                "pool_predicate_activations": len(pool), "only_in_shadow": len(self.activations - pool),
                "only_in_pool_predicate": len(pool - self.activations), "max_memory_entries": self.max_memory,
                "latency_ms": {"shadow_median": q(self.shadow_ms, 0.5), "shadow_p99": q(self.shadow_ms, 0.99),
                               "shadow_max": round(max(self.shadow_ms), 3), "baseline_v2_median": q(self.v2_ms, 0.5),
                               "baseline_v2_p99": q(self.v2_ms, 0.99), "baseline_v2_max": round(max(self.v2_ms), 3),
                               "median_added": round(statistics.median(s - v for s, v in zip(self.shadow_ms, self.v2_ms)), 3)}}


def timed(policy: Any, raw: Mapping[str, Any], seat: int, faction: int, memory: Any) -> Tuple[Any, float]:
    start = time.perf_counter()
    decision = policy.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
    return decision, time.perf_counter() - start


def h0(tally: Tally) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            costs = costs_for(header["scenario_id"], header["map_id"])
            state: Dict[int, Dict[str, Any]] = {}
            for line in handle:
                row = json.loads(line)
                seat, faction = row["seat"], row["faction"]
                s = state.setdefault(seat, {"shadow": sh.IdleConcealmentShadow(costs), "m": sh.ShadowMemory(),
                                            "v2": ShootReservationPolicy(costs), "m2": Memory()})
                raw = typed_json.decode(row["observation"])
                shadow, t1 = timed(s["shadow"], raw, seat, faction, s["m"])
                base, t2 = timed(s["v2"], raw, seat, faction, s["m2"])
                s["m"], s["m2"] = shadow.memory, base.memory
                tally.add((header["game_id"], seat, row["step"]), faction, raw, shadow, base, t1, t2)


def snapshots(folder: str, stem: str) -> List[Dict[str, Any]]:
    with (LOCAL_EVAL / folder / "capture" / f"{stem}.windows.pkl").open("rb") as handle:
        return sorted(pickle.load(handle)["samples"], key=lambda s: s["k"])


def captured(folder: str, stem: str, tally: Tally, population: str, transform=None, repeat: bool = False,
             outputs: Optional[List[str]] = None) -> None:
    samples = snapshots(folder, stem)
    first_global = pickle.loads(samples[0]["global"])
    costs = costs_for(stem.split(".")[0], str(first_global["terrain_id"]))
    shadow_policy, v2 = sh.IdleConcealmentShadow(costs), ShootReservationPolicy(costs)
    memory, memory2 = sh.ShadowMemory(), Memory()
    for snap in samples:
        (seat, entry), = snap["seats"].items()
        faction = entry["faction"]
        raw = pickle.loads(entry["observation"])
        if transform is not None:
            raw = transform(raw)
        shadow, t1 = timed(shadow_policy, raw, seat, faction, memory)
        base, t2 = timed(v2, raw, seat, faction, memory2)
        if repeat:
            again = shadow_policy.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, shadow.memory)
            tally.c["repeated observation: decisions"] += 1
            tally.c["repeated observation: actions added"] += len(again.added)
            tally.c["repeated observation: baseline-v2 actions equal"] += list(again.baseline.actions) == list(base.actions)
        memory, memory2 = shadow.memory, base.memory
        recorded = [dict(a) for a in entry["actions"]]
        trace = entry.get("trace") if population == "H1" else None
        tally.add((stem, seat, snap["k"]), faction, raw, shadow, base, t1, t2, recorded, trace)
        if outputs is not None:
            outputs.append(json.dumps([snap["k"], [dict(a) for a in shadow.actions], list(shadow.skipped)],
                                      sort_keys=True, default=repr))


def permuted(seed: int):
    rng = random.Random(seed)

    def transform(raw: Mapping[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(dict(raw))
        rng.shuffle(out["operators"])
        items = list((out.get("valid_actions") or {}).items())
        rng.shuffle(items)
        for _, actions in items:
            for t in list(actions):
                if isinstance(actions[t], list):
                    rng.shuffle(actions[t])
        out["valid_actions"] = dict(items)
        return out
    return transform


def pool_activations() -> Dict[str, set]:
    private = json.loads((PRIVATE / "study-private.json").read_text(encoding="utf-8"))
    out: Dict[str, set] = collections.defaultdict(set)
    for act in private["activations"]:
        if act["candidate"] == "A2":
            out[act["population"]].add((act["game"], act["seat"], act["k"], act["unit"]))
    return out


def build() -> Dict[str, Any]:
    pool = pool_activations()
    tallies = {"H0": Tally(), "H1": Tally(), "H2": Tally()}
    h0(tallies["H0"])
    runs: Dict[str, List[str]] = {"first": [], "second": [], "permuted": []}
    for population, games in CAPTURES.items():
        for folder, stem in games:
            captured(folder, stem, tallies[population], population,
                     outputs=runs["first"] if population == "H1" else None)
    folder, stem = CAPTURES["H1"][0]
    extra = {"second": Tally(), "permuted": Tally(), "repeat": Tally()}
    captured(folder, stem, extra["second"], "H1", outputs=runs["second"])
    captured(folder, stem, extra["permuted"], "H1", transform=permuted(20261002), outputs=runs["permuted"])
    captured(folder, stem, extra["repeat"], "H1", repeat=True)

    def h(lines: List[str]) -> str:
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA, "study_id": "t7-design-1", "shadow": sh.SHADOW_ID,
        "populations": {p: t.summary(pool.get(p, set())) for p, t in tallies.items()},
        "determinism": {"h1_decisions": len(runs["first"]), "second_run_identical": h(runs["first"]) == h(runs["second"]),
                        "permuted_run_identical": h(runs["first"]) == h(runs["permuted"]),
                        "permuted_counts": dict(sorted(extra["permuted"].c.items()))},
        "repeated_observation": {k.split(": ")[1]: v for k, v in sorted(extra["repeat"].c.items())
                                 if k.startswith("repeated observation")},
    }


def strip_timing(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: strip_timing(v) for k, v in data.items() if k not in TIMING_KEYS}
    return data


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build()
    if args.check:
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
        same = old is not None and dump(strip_timing(old)) == dump(strip_timing(data))
        print("shadow identical (timing excluded)" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(dump(data), encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
