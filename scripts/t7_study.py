"""T7 design study (``t7-design-1``, ``docs/T7_DESIGN.md``): the opportunity audit and the candidate pool, offline.

    python scripts/t7_study.py [--check]

No engine. Private inputs (git-ignored, on the evaluation server):

* H0, the replay corpus pinned by the routing remediation: 8 ``baseline-v0`` games under C1, both seats, every
  decision. ``baseline-v2``'s decisions on these states are reconstructed by replay and verified as in
  ``scripts/replay_launcher_counterfactual.py`` (``baseline-v0`` replays the recorded decision exactly; every unit on which
  ``baseline-v2`` differs carries its own reservation record);
* H1, Sprint 2 game ``b`` (``baseline-v2`` against the inert control) and H2, Sprint 2 game ``c`` and Sprint 4 game P2
  (the split candidate against the inert control): every pre-step snapshot (seat and all-seeing views, actions);
* H2r, Sprint 4 game P1 before its first stop, used only to check that it reproduces game ``c``;
* R, the game records of the registered experiments (issued actions by type), the ownership-prevalence study's
  excluded. Since a maintenance revision of 2026-10-03 R is read through the frozen file-level inventory
  ``evaluation/t7-design-1/record-inventory.json`` (a retrospective reconstruction of the 1,284 records the study read,
  validated against the published ``audit.json``), so records written later never enter it; a missing or changed
  inventory record, or a malformed inventory, stops the study.

Public outputs: ``evaluation/t7-design-1/audit.json`` and ``candidates.json`` (aggregates only). Private outputs:
``local/diagnostics/t7/`` (activation records with identifiers, transition episodes). ``--check`` rebuilds the public
outputs and compares them byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pickle
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.decision.routing import Router, move_mode  # noqa: E402
from miaosuan_agent.evaluation import t7_audit as ta  # noqa: E402
from miaosuan_agent.evaluation import t7_candidates as tc  # noqa: E402
from miaosuan_agent.evaluation.t7_crosscheck import CrossCount, agree  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

PLAN_ID = "t7-design-1"
OUT = REPO_ROOT / "evaluation" / PLAN_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "t7"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
CENSUS = REPO_ROOT / "evaluation" / "tactical-frontier-1" / "census.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
P1_RESULTS = REPO_ROOT / "evaluation" / "ps1-engine-probe-1" / "p1.json"
CAPTURES = {"H1": [("t1r-diagnosis-1", "1910631192.C3.b.x01")],
            "H2": [("t1r-diagnosis-1", "1910631192.C3.c.x01"), ("ps1-engine-probe-1", "1930331196.C2.p2")]}
H2R = ("ps1-engine-probe-1", "1910631192.C3.p1")
H2R_REFERENCE = ("t1r-diagnosis-1", "1910631192.C3.c.x01")
EXCLUDED_RECORDS = frozenset({"baseline-v2-target-ownership-prevalence-1"})
INVENTORY = OUT / "record-inventory.json"
INVENTORY_SCHEMA = "miaosuan-t7-record-inventory/1"
SCHEMA = "miaosuan-t7-design/1"
WINDOW = tc.TRANSITION
A1_WINDOW = 2 * tc.TRANSITION


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def lines(path: Path) -> Iterator[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def costs_for(scenario_id: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario_id / "Data", scenario_id, map_id).cost)


def capture_paths(folder: str, stem: str) -> Tuple[Path, Path]:
    base = LOCAL_EVAL / folder / "capture"
    return base / f"{stem}.capture.json", base / f"{stem}.windows.pkl"


def explained_against_v0(v0: Any, v2: Any) -> bool:
    """Every unit on which baseline-v2 differs from baseline-v0 carries baseline-v2's own reservation record."""
    old = {a.get("obj_id", "seat"): dict(a) for a in v0.actions}
    new = {a.get("obj_id", "seat"): dict(a) for a in v2.actions}
    payload = v2.trace.to_dict()
    marked = {s["obj_id"] for s in payload.get("suppressed", [])}
    marked |= {e["obj_id"] for e in payload.get("shoot_reserved", []) if e["effect"] != "unchanged"}
    return all(old.get(k) == new.get(k) or k in marked for k in set(old) | set(new))


# ------------------------------------------------------------------------------------------------
# Compact per-decision tables for the forward scans (exposure and benefit witnesses)


def compact(raw: Mapping[str, Any], faction: int, actions: List[Mapping[str, Any]]) -> Dict[str, Any]:
    units = ta.operators(raw)
    own = {}
    for unit_id, unit in units.items():
        if unit.get("color") == faction:
            own[unit_id] = (unit.get("cur_hex"), unit.get("stop"), ta.has_path(unit))
    enemies = {unit_id: (unit.get("cur_hex"), unit.get("type")) for unit_id, unit in units.items()
               if unit.get("color") != faction}
    judged = {r.get("target_obj_id") for r in raw.get("judge_info") or () if isinstance(r, Mapping)}
    acted = {a.get("obj_id") for a in actions if ta.integer(a.get("obj_id")) is not None}
    return {"cur_step": (raw.get("time") or {}).get("cur_step"), "own": own, "enemies": enemies, "judged": judged,
            "acted": acted, "listed_ids": set(units)}


def forward(game_rows: Mapping[int, Dict[str, Any]], step: int, horizon: int) -> Iterator[Tuple[int, Dict[str, Any]]]:
    for k in range(step + 1, step + 1 + horizon):
        if k in game_rows:
            yield k, game_rows[k]


def score(candidate: str, act: Dict[str, Any], mine: Mapping[int, Dict[str, Any]],
          theirs: Optional[Mapping[int, Dict[str, Any]]], horizon_end: int) -> Tuple[bool, Optional[bool]]:
    """(exposure, benefit witness) of one activation from the recorded trajectory; witness ``None`` if not observable."""
    unit, step = act["unit"], act["k"]
    if candidate == "A2":
        exposure = any(unit in row["acted"] for _, row in forward(mine, step, WINDOW))
        witness = False
        for k in range(step + 1, horizon_end + 1):
            row = mine.get(k)
            if row is None or unit not in row["own"]:
                break
            _, stop, path = row["own"][unit]
            if stop != 1 or path is not False or unit in row["acted"]:
                break
            other = theirs.get(k) if theirs is not None else None
            if unit in row["judged"] or (other is not None and (unit in other["listed_ids"] or unit in other["judged"])):
                witness = True
                break
        return exposure, witness
    if candidate == "A1":
        return any(row["enemies"] for _, row in forward(mine, step, A1_WINDOW)), act["record"]["saving"] > 0
    if candidate == "A3":
        return any(row["enemies"] for _, row in forward(mine, step, WINDOW)), True
    if candidate in ("B1", "B2"):
        exposure = act["path_ends_at_objective"]
        if candidate == "B1":
            enemy, reach, needed = act["record"]["enemy"], act["record"]["range"], act["hex_time"]
            if needed is None:
                return exposure, None
            ok = True
            for k in range(step + 1, step + 1 + int(needed) + WINDOW):
                row = mine.get(k)
                if row is None or unit not in row["own"] or enemy not in row["enemies"]:
                    ok = False
                    break
                here, there = row["own"][unit][0], row["enemies"][enemy][0]
                if tc.hex_distance(here, there) > reach:
                    ok = False
                    break
            return exposure, ok
        nxt = act["record"]["next"]
        if theirs is None:
            return exposure, None
        for k in range(step + 1, horizon_end + 1):
            row = mine.get(k)
            if row is None or unit not in row["own"]:
                return exposure, False
            if row["own"][unit][0] == nxt:
                other = theirs.get(k)
                return exposure, bool(other is not None and unit in other["listed_ids"])
        return exposure, False
    return False, None


def hex_time(unit: Mapping[str, Any], costs: MoveCosts) -> Optional[float]:
    mode = move_mode(unit.get("type"), unit.get("move_state"))
    path = unit.get("move_path") or ()
    speed = ta.number(unit.get("basic_speed"))
    if mode is None or not path or not speed:
        return None
    edges = costs.neighbours(mode, unit.get("cur_hex"))
    return None if path[0] not in edges else (720.0 / speed) * edges[path[0]]


def activation_rows(raw: Mapping[str, Any], faction: int, actions: List[Mapping[str, Any]], costs: MoveCosts,
                    router: Router, memory: tc.SeatMemory, where: Dict[str, Any]) -> List[Dict[str, Any]]:
    units = ta.operators(raw)
    listed = ta.listings(raw)
    seen = ta.enemy_seen(raw, faction)
    objectives = tc.cities(raw)
    out = []
    for candidate, unit_id, record in tc.evaluate(raw, faction, actions, costs, router, memory):
        unit = units[unit_id]
        family = "B" if candidate.startswith("B") else "A"
        path = list(unit.get("move_path") or ())
        out.append(dict(where, candidate=candidate, unit=unit_id, record=record, archetype=ta.archetype(unit),
                        fingerprint=ta.fingerprint(family, unit, listed.get(unit_id, {}), seen),
                        hex_time=hex_time(unit, costs) if candidate == "B1" else None,
                        path_ends_at_objective=bool(path) and path[-1] in objectives))
    return out


# ------------------------------------------------------------------------------------------------
# Populations


def h0(audit: ta.Audit, cross: CrossCount, transitions: List[ta.Transitions], fidelity: collections.Counter,
       activations: List[Dict[str, Any]], inputs: List[Dict[str, Any]]) -> None:
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        digest_now = sha256(path)
        inputs.append({"population": "H0", "file": path.name, "pinned_sha256": entry["sha256"],
                       "verified": digest_now == entry["sha256"]})
        if digest_now != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        stream = lines(path)
        header = next(stream)
        game, scenario = header["game_id"], header["scenario_id"]
        costs = costs_for(scenario, header["map_id"])
        router = Router(costs)
        seats: Dict[int, Dict[str, Any]] = {}
        tables: Dict[int, Dict[int, Dict[str, Any]]] = collections.defaultdict(dict)
        game_acts: List[Dict[str, Any]] = []
        for row in stream:
            seat, faction = row["seat"], row["faction"]
            if seat not in seats:
                seats[seat] = {"v0": BaselinePolicy(costs), "v2": ShootReservationPolicy(costs), "m0": Memory(),
                               "m2": Memory(), "memory": tc.SeatMemory(), "tr": ta.Transitions(), "faction": faction}
                transitions.append(seats[seat]["tr"])
            s = seats[seat]
            raw = typed_json.decode(row["observation"])
            actions = [dict(a) for a in row["actions"]]
            audit.add(game, faction, raw, actions)
            observation = Observation.from_raw(raw, Origin.ENGINE)
            cross.add(observation, faction)
            cur_step = (raw.get("time") or {}).get("cur_step")
            s["tr"].add(cur_step, faction, raw)
            tables[faction][row["step"]] = compact(raw, faction, actions)
            fidelity["H0 decisions"] += 1
            try:
                v0 = s["v0"].decide(observation, seat, faction, s["m0"])
            except ContractError:
                fidelity["H0 excluded: contract error"] += 1
                continue
            s["m0"] = v0.memory
            exact = [dict(a) for a in v0.actions] == actions and digest(v0.trace) == row["trace_digest"]
            fidelity["H0 baseline-v0 exact"] += exact
            v2 = s["v2"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["m2"])
            s["m2"] = v2.memory
            if not exact:
                fidelity["H0 excluded: baseline-v0 not reproduced"] += 1
                continue
            if not explained_against_v0(v0, v2):
                fidelity["H0 excluded: baseline-v2 difference unexplained"] += 1
                continue
            fidelity["H0 baseline-v2 reconstructed"] += 1
            fidelity["H0 baseline-v2 differs from baseline-v0"] += [dict(a) for a in v2.actions] != actions
            where = {"population": "H0", "game": game, "scenario": scenario, "seat": seat, "faction": faction,
                     "k": row["step"], "cur_step": cur_step}
            game_acts.extend(activation_rows(raw, faction, [dict(a) for a in v2.actions], costs, router,
                                             s["memory"], where))
        for s in seats.values():
            s["tr"].finish()
        last = {f: max(t) for f, t in tables.items()}
        for act in game_acts:
            mine, theirs = tables[act["faction"]], tables.get(1 - act["faction"])
            act["exposure"], act["witness"] = score(act["candidate"], act, mine, theirs, last[act["faction"]])
        activations.extend(game_acts)


def snapshots(windows: Path) -> List[Dict[str, Any]]:
    with windows.open("rb") as handle:
        data = pickle.load(handle)
    return sorted(data["samples"], key=lambda s: s["k"])


def seat_entry(snapshot: Mapping[str, Any]) -> Tuple[int, Mapping[str, Any]]:
    (seat, entry), = snapshot["seats"].items()
    return seat, entry


def t7_listing(raw: Mapping[str, Any], faction: int) -> Dict[int, Dict[int, Any]]:
    units = ta.operators(raw)
    out = {}
    for unit_id, actions in ta.listings(raw).items():
        unit = units.get(unit_id)
        if unit is not None and unit.get("color") != faction:
            continue
        mine = {t: ta.target_states(actions[t])[0] if t == 6 else None for t in ta.T7_TYPES if t in actions}
        if mine:
            out[unit_id] = mine
    return out


def captured(population: str, folder: str, stem: str, audit: ta.Audit, cross: CrossCount,
             transitions: List[ta.Transitions], checks: collections.Counter, activations: List[Dict[str, Any]],
             inputs: List[Dict[str, Any]]) -> None:
    compact_path, windows = capture_paths(folder, stem)
    inputs.append({"population": population, "file": windows.name, "sha256": sha256(windows)})
    inputs.append({"population": population, "file": compact_path.name, "sha256": sha256(compact_path)})
    meta = json.loads(compact_path.read_text(encoding="utf-8"))
    players = {p["seat"]: p for p in meta["setup"]["players"]}
    scenario = stem.split(".")[0]
    costs = None
    tr = ta.Transitions()
    transitions.append(tr)
    memory = tc.SeatMemory()
    tables: Dict[int, Dict[str, Any]] = {}
    acts: List[Dict[str, Any]] = []
    for snap in snapshots(windows):
        seat, entry = seat_entry(snap)
        faction = entry["faction"]
        raw = pickle.loads(entry["observation"])
        everything = pickle.loads(snap["global"])
        actions = [dict(a) for a in entry["actions"]]
        audit.add(stem, faction, raw, actions)
        cross.add(Observation.from_raw(raw, Origin.ENGINE), faction)
        tr.add(snap["cur_step"], faction, raw)
        tables[snap["k"]] = compact(raw, faction, actions)
        mine = t7_listing(raw, faction)
        whole = t7_listing({"operators": everything.get("operators"), "valid_actions": everything.get("valid_actions")},
                           faction)
        for unit_id, listing in mine.items():
            checks[f"{population} seat-vs-all-seeing unit listings"] += 1
            if unit_id not in whole:
                checks[f"{population} not listed in the all-seeing view"] += 1
            elif whole[unit_id] == listing:
                checks[f"{population} identical in the all-seeing view"] += 1
            else:
                checks[f"{population} DIFFERENT in the all-seeing view"] += 1
        for unit_id in whole:
            if unit_id not in mine:
                checks[f"{population} listed only in the all-seeing view"] += 1
        if costs is None:
            costs = costs_for(scenario, str(everything.get("terrain_id")))
            router = Router(costs)
        if players.get(seat, {}).get("policy") == "inert-v0":
            continue
        where = {"population": population, "game": stem, "scenario": scenario, "seat": seat, "faction": faction,
                 "k": snap["k"], "cur_step": snap["cur_step"]}
        acts.extend(activation_rows(raw, faction, actions, costs, router, memory, where))
    tr.finish()
    last = max(tables)
    for act in acts:
        act["exposure"], act["witness"] = score(act["candidate"], act, tables, None, last)
    activations.extend(acts)


def reproduction(trigger_k: int) -> Dict[str, Any]:
    """H2r: P1's T7 listings before the trigger against game c's at the same index."""
    _, p1 = capture_paths(*H2R)
    _, ref = capture_paths(*H2R_REFERENCE)
    reference = {s["k"]: s for s in snapshots(ref) if s["k"] < trigger_k}
    compared = equal = 0
    for snap in snapshots(p1):
        if snap["k"] >= trigger_k:
            continue
        other = reference.get(snap["k"])
        if other is None:
            continue
        (_, a), (_, b) = seat_entry(snap), seat_entry(other)
        ra, rb = pickle.loads(a["observation"]), pickle.loads(b["observation"])
        compared += 1
        equal += t7_listing(ra, a["faction"]) == t7_listing(rb, b["faction"])
    return {"decisions_compared": compared, "identical_t7_listings": equal, "before_k": trigger_k}


class InventoryError(Exception):
    """The frozen record inventory is malformed, or a record it names is missing or changed."""


def inventory_records(root: Path = LOCAL_EVAL, inventory: Path = INVENTORY) -> List[Path]:
    """The records of the frozen inventory under ``root``, in sorted path order; anything else is ignored.

    Each entry is ``<16 hex of SHA-256 of the path relative to root>:<32 hex of SHA-256 of the bytes>``; the inventory's
    count and digest must match its entries, which must be well formed and unique, and every entry must name exactly
    one present record with the same bytes."""
    spec = json.loads(inventory.read_text(encoding="utf-8"))
    entries = spec.get("entries")
    if spec.get("schema") != INVENTORY_SCHEMA or not isinstance(entries, list):
        raise InventoryError("not a record inventory")
    if any(not isinstance(e, str) or len(e) != 49 or e[16] != ":" or not all(c in "0123456789abcdef" for c in e[:16] + e[17:])
           for e in entries):
        raise InventoryError("malformed inventory entry")
    expected = {e[:16]: e[17:] for e in entries}
    if len(expected) != len(entries) or spec.get("count") != len(entries):
        raise InventoryError("duplicate inventory entries or a wrong count")
    if spec.get("inventory_sha256") != hashlib.sha256("\n".join(entries).encode("ascii")).hexdigest():
        raise InventoryError("the inventory digest does not match its entries")
    found: Dict[str, Path] = {}
    for path in root.glob("*/games/*.json"):
        key = hashlib.sha256(path.relative_to(root).as_posix().encode("utf-8")).hexdigest()[:16]
        if key in expected:
            found[key] = path
    missing = sorted(set(expected) - set(found))
    if missing:
        raise InventoryError(f"{len(missing)} inventory records are missing (first path digest {missing[0]})")
    changed = sorted(k for k, p in found.items() if hashlib.sha256(p.read_bytes()).hexdigest()[:32] != expected[k])
    if changed:
        raise InventoryError(f"{len(changed)} inventory records have changed (first path digest {changed[0]})")
    selected = sorted(found.values())
    if any(p.parts[-3] in EXCLUDED_RECORDS for p in selected):
        raise InventoryError("the inventory names a record of an excluded study")
    return selected


def records(root: Path = LOCAL_EVAL, inventory: Path = INVENTORY) -> Dict[str, Any]:
    issued: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    files = 0
    folders = set()
    for path in inventory_records(root, inventory):
        folder = path.parts[-3]
        record = json.loads(path.read_text(encoding="utf-8"))
        files += 1
        folders.add(folder)
        for seat in record.get("seats") or ():
            by_type = seat.get("actions_by_type") or {}
            for t in ta.T7_TYPES:
                issued[seat.get("policy", "?")][str(t)] += int(by_type.get(str(t), 0))
            issued[seat.get("policy", "?")]["seat-games"] += 1
    return {"files": files, "folders": sorted(folders),
            "t7_actions_by_policy": {p: dict(sorted(c.items())) for p, c in sorted(issued.items())}}


def capture_issued(folder: str, stem: str) -> Dict[str, int]:
    """Issued T7 actions in a captured game, from its record (R) and from its snapshots, for count 4's cross-check."""
    record = json.loads((LOCAL_EVAL / folder / "games" / f"{stem}.json").read_text(encoding="utf-8"))
    from_record = collections.Counter()
    for seat in record["seats"]:
        for t in ta.T7_TYPES:
            from_record[t] += int((seat.get("actions_by_type") or {}).get(str(t), 0))
    meta = json.loads(capture_paths(folder, stem)[0].read_text(encoding="utf-8"))
    from_batches = collections.Counter()
    for step in meta["steps"]:
        for item in step.get("submitted") or step.get("batch") or ():
            t = (item.get("action") or {}).get("type")
            if t in ta.T7_TYPES:
                from_batches[t] += 1
    return {"record": sum(from_record.values()), "compact_log": sum(from_batches.values()),
            "by_type_record": {str(t): from_record[t] for t in ta.T7_TYPES if from_record[t]}}


# ------------------------------------------------------------------------------------------------
# Summaries


def stats(values: List[float]) -> Optional[Dict[str, float]]:
    if not values:
        return None
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def transitions_summary(trs: List[ta.Transitions]) -> Dict[str, Any]:
    episodes: Dict[str, List[int]] = collections.defaultdict(list)
    changes: collections.Counter = collections.Counter()
    arrivals: Dict[str, Dict[str, List[int]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    arrival_ends: collections.Counter = collections.Counter()
    gaps = 0
    for tr in trs:
        gaps += tr.gaps
        changes.update(tr.changes)
        for ep in tr.episodes:
            episodes[f"{ep['field']}|{ep['archetype']}|{ep['end']}"].append(ep["steps"])
        for arr in tr.arrival_rows:
            arrival_ends[f"{arr['archetype']}|{arr['end']}"] += 1
            if arr["stop_after"] is not None:
                arrivals[arr["archetype"]]["stop_after"].append(arr["stop_after"])
            for name, age in arr["listed_after"].items():
                arrivals[arr["archetype"]][f"{name}_listed_after"].append(age)
    return {"gaps": gaps, "field_changes": dict(sorted(changes.items())),
            "episodes": {k: stats(v) for k, v in sorted(episodes.items())},
            "arrivals": {a: {k: stats(v) for k, v in sorted(d.items())} for a, d in sorted(arrivals.items())},
            "arrival_ends": dict(sorted(arrival_ends.items()))}


def candidates_summary(activations: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for population in ("H0", "H1", "H2"):
        rows = [a for a in activations if a["population"] == population]
        block = {}
        for candidate in tc.POOL:
            mine = [a for a in rows if a["candidate"] == candidate]
            witnessed = [a for a in mine if a["witness"] is True]
            entry = {"activations": len(mine),
                     "units": len({(a["game"], a["seat"], a["unit"]) for a in mine}),
                     "scenarios": sorted({a["scenario"] for a in mine}),
                     "archetypes": dict(sorted(collections.Counter(a["archetype"] for a in mine).items())),
                     "distinct_situations": len({a["fingerprint"] for a in mine}),
                     "exposure": sum(1 for a in mine if a["exposure"]),
                     "witness_true": len(witnessed),
                     "witness_unobservable": sum(1 for a in mine if a["witness"] is None),
                     "witness_units": len({(a["game"], a["seat"], a["unit"]) for a in witnessed}),
                     "witness_scenarios": sorted({a["scenario"] for a in witnessed})}
            if candidate == "A1":
                entry["saving_seconds"] = stats([a["record"]["saving"] for a in mine])
                entry["lock_listed"] = sum(1 for a in mine if a["record"]["lock_listed"])
                entry["march_option_listed"] = sum(1 for a in mine if a["record"]["march_option_listed"])
            if candidate == "A2":
                entry["first_activations"] = sum(1 for a in mine if not a["record"]["repeat"])
            if candidate == "B1":
                entry["distance"] = stats([a["record"]["distance"] for a in mine])
            block[candidate] = entry
        out[population] = block
    return out


def build() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    census_check = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "tactical_census.py"), "--check"],
                                  capture_output=True, text=True).stdout.strip()
    census = json.loads(CENSUS.read_text(encoding="utf-8"))["corpus"]["decisions_listing_type"]["play"]
    inputs: List[Dict[str, Any]] = []
    fidelity: collections.Counter = collections.Counter()
    checks: collections.Counter = collections.Counter()
    activations: List[Dict[str, Any]] = []
    populations, crosses, transitions = {}, {}, {}
    audit, cross, trs = ta.Audit(), CrossCount(), []
    h0(audit, cross, trs, fidelity, activations, inputs)
    populations["H0"], crosses["H0"], transitions["H0"] = audit, cross, trs
    for population, games in CAPTURES.items():
        audit, cross, trs = ta.Audit(), CrossCount(), []
        for folder, stem in games:
            captured(population, folder, stem, audit, cross, trs, checks, activations, inputs)
        populations[population], crosses[population], transitions[population] = audit, cross, trs
    summaries = {p: a.summary() for p, a in populations.items()}
    play = summaries["H0"]["decisions_listing"]
    reconciliation = {"census_check": census_check,
                      "h0_play_decisions_listing": {t: play.get(f"play:{t}", 0) for t in (6, 10, 11)},
                      "census_play_decisions_listing": {6: census["06 change state"], 10: census["10 stop"],
                                                        11: census["11 weapon lock"]}}
    reconciliation["equal"] = (census_check == "census identical" and
                               reconciliation["h0_play_decisions_listing"] == reconciliation["census_play_decisions_listing"])
    trigger_k = json.loads(P1_RESULTS.read_text(encoding="utf-8"))["premise"]["trigger_k"]
    issued_cross = {stem: capture_issued(folder, stem) for games in CAPTURES.values() for folder, stem in games}
    issued_cross[H2R[1]] = capture_issued(*H2R)
    audit_out = {
        "schema": SCHEMA, "study_id": PLAN_ID, "part": "audit",
        "inputs": inputs, "census_reconciliation": reconciliation, "baseline_v2_reconstruction": dict(sorted(fidelity.items())),
        "populations": summaries,
        "crosscheck": {p: agree(summaries[p], crosses[p].summary()) for p in populations},
        "seat_vs_all_seeing": dict(sorted(checks.items())),
        "transitions": {p: transitions_summary(t) for p, t in transitions.items()},
        "h2r_reproduction": reproduction(trigger_k),
        "issued_records": records(),
        "issued_capture_vs_record": issued_cross,
        "semantics_rows": {p: a.semantics_table() for p, a in populations.items()},
    }
    candidates_out = {"schema": SCHEMA, "study_id": PLAN_ID, "part": "candidates",
                      "pool": list(tc.POOL), "summary": candidates_summary(activations)}
    private = {"activations": activations,
               "episodes": {p: [ep for tr in t for ep in tr.episodes] for p, t in transitions.items()}}
    return audit_out, candidates_out, private


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True, default=str) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    audit_out, candidates_out, private = build()
    texts = {OUT / "audit.json": dump(audit_out), OUT / "candidates.json": dump(candidates_out)}
    if args.check:
        same = all(path.exists() and path.read_text(encoding="utf-8") == text for path, text in texts.items())
        print("outputs identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.mkdir(parents=True, exist_ok=True)
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for path, text in texts.items():
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
    (PRIVATE / "study-private.json").write_text(dump(private), encoding="utf-8", newline="\n")
    print("wrote local/diagnostics/t7/study-private.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
