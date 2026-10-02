"""PS-1 design study driver: reconstruction, observation audit, fidelity, counterfactuals, generalisation.

    PYTHON scripts/ps1_study.py [--work DIR] [--private DIR] [--public DIR] [--corpus-root DIR] [--smoke DIR]

DESIGN STUDY (``docs/PS1_DESIGN.md``); offline, no engine. Inputs are immutable and checked by SHA-256 before and after:
the two captured Sprint 2 games of scenario 1910631192 (``local/evaluation/t1r-diagnosis-1``), the staged map cost data
of the screen manifest, the pinned replay corpus and the Sprint 1 smoke captures. Two independent channels (the
all-seeing state and the seat observation, with the observation's own score counters) reconstruct the failure; the
model (``evaluation/ps1_model.py``) must reproduce both games (fidelity F1 with the recorded orders, F2 with the
baseline surrogate) before any counterfactual is called model-derived. Private outputs (unit ids, hexes) go to
``--private``; the public summary holds counts, step indices and objective labels only.
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
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.decision.routing import move_mode  # noqa: E402
from miaosuan_agent.evaluation import ps1_model as pm  # noqa: E402

SCREEN = "tactical-screen-deployment-split-1"
SCENARIO = "1910631192"
BASELINE_GAME = "1910631192.C3.b.x01"
CANDIDATE_GAME = "1910631192.C3.c.x01"
MOVE, OCCUPY, STOP = 1, 5, 10
GROUND = (1, 2)
OBSERVED_FIELDS = ("can_to_move", "flag_force_stop", "stop", "move_state")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ----------------------------------------------------------------------------------------------
# captures


class Capture:
    """One captured game: record, compact log and the per-decision snapshots (all-seeing state, seat observation)."""

    def __init__(self, record: Mapping[str, Any], compact: Mapping[str, Any], windows: Mapping[str, Any]) -> None:
        self.record, self.compact = record, compact
        self.steps: List[Mapping[str, Any]] = list(compact["steps"])
        self.snapshots: Dict[int, Mapping[str, Any]] = {s["k"]: s for s in windows["samples"]}
        seat = next(s for s in record["seats"] if s["policy"] != "inert-v0")
        self.seat, self.faction, self.policy = seat["seat"], seat["faction"], seat["policy"]
        self.colour = "red" if self.faction == 0 else "blue"
        self._global: Dict[int, Mapping[str, Any]] = {}
        self._obs: Dict[int, Mapping[str, Any]] = {}

    @classmethod
    def read(cls, work: Path, game: str) -> "Capture":
        return cls(load(work / "games" / f"{game}.json"), load(work / "capture" / f"{game}.capture.json"),
                   pickle.loads((work / "capture" / f"{game}.windows.pkl").read_bytes()))

    def ks(self) -> List[int]:
        return sorted(self.snapshots)

    def global_state(self, k: int) -> Mapping[str, Any]:
        if k not in self._global:
            self._global[k] = pickle.loads(self.snapshots[k]["global"])
        return self._global[k]

    def observation(self, k: int) -> Mapping[str, Any]:
        if k not in self._obs:
            seats = self.snapshots[k]["seats"]
            entry = seats.get(self.seat) or seats.get(str(self.seat))
            self._obs[k] = pickle.loads(entry["observation"])
        return self._obs[k]

    def own_actions(self, k: int) -> List[Mapping[str, Any]]:
        return [i["action"] for i in self.steps[k]["batch"] if i["seat"] == self.seat] if k < len(self.steps) else []


def channel_a(state: Mapping[str, Any], faction: int) -> Dict[int, Tuple[int, Tuple[int, ...]]]:
    """All-seeing state: own ground units on the map -> (hex, remaining path)."""
    out = {}
    for u in state.get("operators") or ():
        if u.get("color") == faction and u.get("type") in GROUND and not u.get("on_board"):
            out[int(u["obj_id"])] = (int(u["cur_hex"]), tuple(int(h) for h in (u.get("move_path") or ())))
    return out


def channel_b(observation: Mapping[str, Any], seat: int) -> Dict[int, Tuple[int, Tuple[int, ...]]]:
    """Seat observation (written separately from channel_a): units the seat lists, of a ground type, not on board."""
    info = observation.get("role_and_grouping_info") or {}
    listed = set((info.get(seat) or info.get(str(seat)) or {}).get("operators") or ())
    units: Dict[int, Tuple[int, Tuple[int, ...]]] = {}
    for record in observation.get("operators") or []:
        oid = record.get("obj_id")
        if oid in listed and record.get("type") in GROUND and record.get("on_board") in (0, None, False):
            path = record.get("move_path") or []
            units[oid] = (record.get("cur_hex"), tuple(path))
    return units


def flags_points(state: Mapping[str, Any], faction: int) -> int:
    return sum(int(c["value"]) for c in state.get("cities") or () if c.get("flag") == faction)


# ----------------------------------------------------------------------------------------------
# reconstruction and audit (G1, O1 to O6)


def unit_static(state: Mapping[str, Any], faction: int) -> Dict[int, Dict[str, Any]]:
    return {int(u["obj_id"]): {"type": u["type"], "speed": float(u["basic_speed"]), "move_state": u.get("move_state")}
            for u in state.get("operators") or () if u.get("color") == faction and u.get("type") in GROUND}


def model_units(cap: Capture, k: int, history: Mapping[int, int]) -> List[pm.Unit]:
    """Model view of the observed state before decision k; ``history`` gives each unit's last progress step."""
    state = cap.global_state(k)
    statics = unit_static(state, cap.faction)
    units = []
    for oid, (hex_, path) in channel_a(state, cap.faction).items():
        s = statics[oid]
        units.append(pm.Unit(uid=oid, hex=hex_, speed=s["speed"], mode=int(move_mode(s["type"], s["move_state"])),
                             path=path, last_progress=history.get(oid, 0)))
    return units


def unit_mode(static: Mapping[str, Any]) -> int:
    return int(move_mode(static["type"], static["move_state"]))


def reconstruct(cap: Capture, costs: MoveCosts) -> Dict[str, Any]:
    """Two-channel reconstruction of one game, with the observation audit O1 to O6 and the declared PS-1B trigger."""
    edges = {int(m): costs.edges[m] for m in range(len(costs.edges))}
    ks = cap.ks()
    problems: List[str] = []
    a_prev: Optional[Dict[int, Tuple[int, Tuple[int, ...]]]] = None
    last_progress: Dict[int, int] = {}
    ready: Dict[int, int] = {}
    waited: Dict[int, bool] = {}
    entries: List[Tuple[int, int, int]] = []
    orders: List[Tuple[int, int, Tuple[int, ...]]] = []
    occupations: List[Tuple[int, int]] = []
    o2, o3, o5, o6 = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    o5_offsets: List[int] = []
    o4: Dict[str, Dict[str, collections.Counter]] = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    o4b: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    o4c: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    entered: Dict[int, int] = {}
    timeline: List[Tuple[int, int, int]] = []  # k, blocked units, deadlocked units
    detections: List[int] = []
    flags_vs_scores = collections.Counter()
    for k in ks:
        state, obs = cap.global_state(k), cap.observation(k)
        a, b = channel_a(state, cap.faction), channel_b(obs, cap.seat)
        if a != b:
            problems.append(f"k {k}: channels disagree on {len(set(a.items()) ^ set(b.items()))} unit entries")
        flags_vs_scores["equal" if flags_points(state, cap.faction) == (obs.get("scores") or {}).get(f"{cap.colour}_occupy")
                        else "different"] += 1
        statics = unit_static(state, cap.faction)
        if a_prev is not None:
            occ_prev = collections.Counter(h for h, _ in a_prev.values())
            left = collections.Counter(a_prev[o][0] for o in a_prev if o in a and a[o][0] != a_prev[o][0])
            for oid, (hex_, path) in sorted(a.items()):
                ph, pp = a_prev.get(oid, (None, ()))
                if ph is None or hex_ == ph:
                    continue
                entries.append((k, oid, hex_))
                entered[oid] = k
                o2["path advanced by one" if pp and pp[0] == hex_ and path == pp[1:] else "path not advanced by one"] += 1
                if oid in ready:
                    if waited.get(oid):
                        if occ_prev[hex_] < pm.K:
                            o6["entered after waiting: room at the previous step"] += 1
                        elif left[hex_]:
                            o6["entered after waiting: a unit left the hex in the same step"] += 1
                        else:
                            o6["entered after waiting: the hex was full and nobody left"] += 1
                    else:
                        o5_offsets.append(k - ready[oid])
                        o5["exact" if k == ready[oid] else "within 1" if abs(k - ready[oid]) <= 1 else "off"] += 1
                last_progress[oid] = k
                waited[oid] = False
                cost = edges[unit_mode(statics[oid])].get(hex_, {}).get(path[0]) if path else None
                if path and cost is None:
                    o2["path inconsistent with the cost graph"] += 1
                if cost is not None:
                    ready[oid] = k + pm.hex_time(statics[oid]["speed"], cost)
                else:
                    ready.pop(oid, None)
        units = model_units(cap, k, last_progress)
        full = pm.full_hexes(units)
        blocked = pm.blocked_units(units)
        dead = pm.deadlocked(units)
        timeline.append((k, len(blocked), len(dead)))
        speeds = {int(x["obj_id"]): x.get("speed") for x in state.get("operators") or () if x.get("color") == cap.faction}
        for u in units:  # O6: a unit with a path and observed speed 0 is waiting; it should face a full next hex
            if u.moving and speeds.get(u.uid) == 0:
                waited[u.uid] = True
                o6["waiting unit-steps (speed 0): next hex full" if u.next_hex in full else
                   "waiting unit-steps (speed 0): next hex not full"] += 1
        if dead and all(pm.stalled(u, k, edges) for u in units if u.uid in dead):
            detections.append(k)
        valid = obs.get("valid_actions") or {}
        raw = {int(x["obj_id"]): x for x in state.get("operators") or () if x.get("color") == cap.faction}
        for u in units:
            klass = "blocked" if u.uid in blocked else "moving" if u.moving else "stationary"
            listed = tuple(sorted(int(t) for t in (valid.get(u.uid) or valid.get(str(u.uid)) or {})))
            if klass == "blocked":
                o3[str(listed)] += 1
            for name in OBSERVED_FIELDS:
                o4[name][klass][str(raw[u.uid].get(name))] += 1
            # speed (hex per second) against the model's 1 / tau, and stationary_count against steps in the hex
            speed = raw[u.uid].get("speed")
            tau = pm.expected_hex_time(u, edges)
            if tau is not None and isinstance(speed, (int, float)):
                o4b[klass]["speed equals 1/tau" if speed > 0 and abs(1.0 / speed - tau) <= 0.5 else
                           "speed is 0" if speed == 0 else "speed differs from 1/tau"] += 1
            count = raw[u.uid].get("stationary_count")
            since = k - entered.get(u.uid, ks[0])
            if isinstance(count, int):
                o4c[klass]["stationary_count equals steps since the hex was entered" if count == since else
                           "stationary_count equals steps plus one" if count == since + 1 else "stationary_count differs"] += 1
        for act in cap.own_actions(k):
            if act.get("type") == MOVE:
                oid = int(act["obj_id"])
                path = tuple(act["move_path"])
                orders.append((k, oid, path))
                last_progress[oid] = k
                waited[oid] = False
                cost = edges[unit_mode(statics[oid])].get(a[oid][0], {}).get(path[0]) if oid in a else None
                if cost is not None:
                    ready[oid] = k + pm.hex_time(statics[oid]["speed"], cost)
            elif act.get("type") == OCCUPY:
                occupations.append((k, int(act["obj_id"])))
        a_prev = a
    order_echo = collections.Counter()
    for k, oid, path in orders:  # L1: the recorded order must reappear as the unit's remaining path next step
        nxt = channel_a(cap.global_state(k + 1), cap.faction).get(oid) if k + 1 in cap.snapshots else None
        order_echo["next state carries the path" if nxt and nxt[1] == path else "next state differs"] += 1
    seat_rec = next(s for s in cap.record["seats"] if s["seat"] == cap.seat)
    count_check = {"moves": [len(orders), seat_rec["actions_by_type"].get(str(MOVE), 0)],
                   "occupations": [len(occupations), seat_rec["actions_by_type"].get(str(OCCUPY), 0)]}
    for label, (mine, recorded) in count_check.items():
        if mine != recorded:
            raise SystemExit(f"REFUSED: {cap.record['game_id']}: {mine} {label} in the capture, {recorded} in the record")
    persistent = None
    for k, _, nd in reversed(timeline):
        if nd == 0:
            break
        persistent = k
    detail = None
    first_detection = None
    if persistent is not None:
        first_detection = next((k for k in detections if k >= persistent), None)
        units = model_units(cap, persistent, {})
        dead = pm.deadlocked(units)
        by_uid = {u.uid: u for u in units}
        groups = collections.Counter(by_uid[d].hex for d in dead)
        cyc = pm.cycles(units)
        cities = {int(c["coord"]): c for c in cap.global_state(persistent).get("cities") or ()}
        detail = {"k": persistent, "cur_step": cap.global_state(persistent)["time"]["cur_step"],
                  "deadlocked_units": len(dead), "vehicle_units": sum(1 for d in dead if by_uid[d].mode in (0, 1)),
                  "group_sizes": sorted(groups.values(), reverse=True), "cycles": len(cyc),
                  "cycle_lengths": [len(c) for c in cyc],
                  "cycle_includes_an_objective": any(h in cities for c in cyc for h in c),
                  "steps_to_end": len(cap.steps) - persistent,
                  "private": {"groups": dict(groups), "cycles": cyc}}
    first_blocked = next((k for k, nb, _ in timeline if nb), None)
    final = cap.record["final_scores"]
    other = "blue" if cap.colour == "red" else "red"
    return {"game": cap.record["game_id"], "policy": cap.policy, "snapshots": len(ks),
            "channel_disagreements": len(problems), "flags_vs_observation_scores": dict(flags_vs_scores),
            "orders": len(orders), "occupations": len(occupations), "record_counts": count_check,
            "order_echo": dict(order_echo), "entries": len(entries), "O2": dict(o2),
            "O3_blocked_valid_actions": dict(o3), "O4": {n: {c: dict(v) for c, v in d.items()} for n, d in o4.items()},
            "O4_speed": {c: dict(v) for c, v in o4b.items()}, "O4_stationary_count": {c: dict(v) for c, v in o4c.items()},
            "O5": dict(o5), "O5_offset_range": [min(o5_offsets), max(o5_offsets)] if o5_offsets else None,
            "O6": dict(o6), "first_blocked_k": first_blocked,
            "blocked_unit_steps": sum(nb for _, nb, _ in timeline), "deadlocked_unit_steps": sum(nd for _, _, nd in timeline),
            "persistent_deadlock": detail, "first_detection_k": first_detection, "trigger_steps": len(detections),
            "scores": {"total": final[f"{cap.colour}_total"], "win": final[f"{cap.colour}_win"],
                       "other_total": final[f"{other}_total"], "occupy": final[f"{cap.colour}_occupy"],
                       "remain": final[f"{cap.colour}_remain"], "attack": final[f"{cap.colour}_attack"]},
            "private": {"entries": entries, "orders": [(k, o, list(p)) for k, o, p in orders], "occupations": occupations,
                        "problems": problems[:20], "detections": detections[:20]}}


# ----------------------------------------------------------------------------------------------
# fidelity (F1, F2) and counterfactuals


def objectives_at(cap: Capture, k: int) -> Dict[int, int]:
    return {int(c["coord"]): int(c["flag"]) for c in cap.global_state(k).get("cities") or ()}


def observed_speed(cap: Capture, k: int, oid: int) -> float:
    for u in cap.global_state(k).get("operators") or ():
        if int(u["obj_id"]) == oid:
            return float(u.get("speed") or 0)
    raise KeyError(oid)


def start_simulation(cap: Capture, k: int, costs: MoveCosts, recon: Mapping[str, Any], restart: bool = False) -> pm.Simulation:
    """The observed state before decision k, with each unit's hex timing rebuilt from the observed history.

    Under M1b (``restart``), a unit with a path and observed speed 0 is waiting; a unit in transit that waited after its
    last entry or order restarted its traversal in the first step after its last waiting step (``tau - 1`` to go).
    """
    edges = {int(m): costs.edges[m] for m in range(len(costs.edges))}
    last: Dict[int, int] = {}
    for kk, oid, _ in recon["private"]["entries"]:
        if kk <= k:
            last[oid] = kk
    for kk, oid, _ in recon["private"]["orders"]:
        if kk < k and kk >= last.get(oid, -1):
            last[oid] = kk
    units = []
    for u in model_units(cap, k, last):
        ready, waiting = None, False
        if u.moving:
            tau = pm.hex_time(u.speed, edges[u.mode][u.hex][u.next_hex])
            ready = last.get(u.uid, 0) + tau
            if restart:
                if observed_speed(cap, k, u.uid) == 0:
                    ready, waiting = None, True
                else:
                    waited = [kk for kk in range(last.get(u.uid, k), k) if observed_speed(cap, kk, u.uid) == 0]
                    if waited:
                        ready = max(waited) + 1 + tau - 1
        units.append(pm.Unit(uid=u.uid, hex=u.hex, speed=u.speed, mode=u.mode, path=u.path, ready_at=ready,
                             last_progress=last.get(u.uid, 0), waiting=waiting))
    return pm.Simulation(units=units, edges_by_mode=edges, step=k, objectives=objectives_at(cap, k), faction=cap.faction,
                         end_step=len(cap.steps), restart_after_wait=restart)


def compare_entries(simulated: Sequence[Tuple[int, int, int]], observed: Sequence[Tuple[int, int, int]], start: int) -> Dict[str, Any]:
    obs = collections.defaultdict(list)
    for k, oid, h in observed:
        if k > start:
            obs[oid].append((k, h))
    sim = collections.defaultdict(list)
    for k, oid, h in simulated:
        sim[oid].append((k, h))
    worst, mismatched = 0, []
    for oid in sorted(set(obs) | set(sim)):
        a, b = obs.get(oid, []), sim.get(oid, [])
        if [h for _, h in a] != [h for _, h in b]:
            mismatched.append(oid)
            continue
        for (ka, _), (kb, _) in zip(a, b):
            worst = max(worst, abs(ka - kb))
    return {"units": len(set(obs) | set(sim)), "hex_sequences_differ": len(mismatched), "worst_step_offset": worst,
            "observed_entries": sum(len(v) for v in obs.values()), "simulated_entries": sum(len(v) for v in sim.values()),
            "private": {"mismatched_units": mismatched}}


def first_play_k(cap: Capture) -> int:
    return next(s["k"] for s in cap.steps if s.get("stage") == 2)


def fidelity(cap: Capture, costs: MoveCosts, recon: Mapping[str, Any], restart: bool = False) -> Dict[str, Any]:
    k0 = first_play_k(cap)
    out: Dict[str, Any] = {"start_k": k0, "model": "M1b" if restart else "M1"}
    recorded: Dict[int, List[Tuple[str, int, Tuple[int, ...]]]] = collections.defaultdict(list)
    for k, oid, path in recon["private"]["orders"]:
        recorded[k].append(("move", oid, tuple(path)))
    for k, oid in recon["private"]["occupations"]:
        recorded[k].append(("occupy", oid, ()))
    for label, policy in (("F1", pm.recorded_orders(recorded)), ("F2", pm.surrogate)):
        sim = start_simulation(cap, k0, costs, recon, restart)
        try:
            sim.run(policy)
        except pm.ModelError as exc:
            out[label] = {"error": str(exc)}
            continue
        simulated = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"]
        res = compare_entries(simulated, recon["private"]["entries"], k0)
        dead = pm.deadlocked(sim.units)
        res["deadlocked_at_end"] = len(dead)
        res["cycles_at_end"] = len(pm.cycles(sim.units))
        res["objectives_held_at_end"] = sum(1 for f in sim.objectives.values() if f == cap.faction)
        if label == "F2":
            sim_orders = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "order"]
            rec_orders = [(k, oid, path[-1]) for k, oid, path in recon["private"]["orders"]]
            matched = sum(1 for k, oid, d in rec_orders if any(oid == o and d == dd and abs(k - kk) <= 1 for kk, o, dd in sim_orders))
            res["orders"] = {"recorded": len(rec_orders), "simulated": len(sim_orders), "recorded_matched": matched}
            sim_occ = sorted(e.step for e in sim.events if e.kind == "occupy")
            res["occupation_steps"] = {"recorded": sorted(k for k, _ in recon["private"]["occupations"]), "simulated": sim_occ}
        out[label] = res
    f1, f2 = out.get("F1", {}), out.get("F2", {})
    out["F1_pass"] = "error" not in f1 and f1["hex_sequences_differ"] == 0 and f1["worst_step_offset"] <= 1
    out["F2_pass"] = ("error" not in f2 and f2["hex_sequences_differ"] == 0 and f2["worst_step_offset"] <= 1
                      and f2["orders"]["recorded_matched"] == f2["orders"]["recorded"] == f2["orders"]["simulated"])
    return out


def retarget_policy() -> Any:
    """A4 sequencing: stop units still en route to an objective that has become own-held (stale destination), then let
    the surrogate re-order them after the transition; everything else as the surrogate."""
    def policy(sim: pm.Simulation) -> None:
        for u in sorted(sim.units, key=lambda x: x.uid):
            if u.moving and u.destination in sim.objectives and sim.objectives[u.destination] == sim.faction \
                    and u.hex != u.destination and not u.stop_after_entry:
                sim.order_stop(u.uid)
        pm.surrogate(sim)
    return policy


def certificate(label: str, intervention: str, cap: Capture, costs: MoveCosts, recon: Mapping[str, Any], k: int,
                policy_factory: Any, assumptions: Sequence[str], unverified: Sequence[str]) -> Dict[str, Any]:
    sim = start_simulation(cap, k, costs, recon, restart=True)
    before = list(sim.units)
    cyc0 = pm.cycles(before)
    state = None
    if policy_factory == "ps1b-back-off":
        state = pm.Recovery(option="back-off")
        policy = pm.ps1b(state)
    elif policy_factory == "ps1b-bypass":
        state = pm.Recovery(option="bypass")
        policy = pm.ps1b(state)
    elif policy_factory == "ps1a":
        policy = pm.ps1a
    elif policy_factory == "retarget":
        policy = retarget_policy()
    else:
        raise ValueError(policy_factory)
    error = None
    cycle_absent_from = None
    try:
        while sim.step < sim.end_step:
            policy(sim)
            sim.advance()
            if cycle_absent_from is None and cyc0 and not any(c in pm.cycles(sim.units) for c in cyc0):
                cycle_absent_from = sim.step
    except pm.ModelError as exc:
        error = str(exc)
    entries = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"]
    start = {u.uid: u.hex for u in before}
    edges = sim.edges_by_mode
    mode = {u.uid: u.mode for u in before}
    violations = pm.validate_trajectory(start, entries, lambda uid, a, b: b in edges[mode[uid]].get(a, {}), {})
    commands = [e for e in sim.events if e.kind in ("stop", "order", "hold", "recover", "no-escape", "occupy")]
    labels = {h: f"objective_value_{v}" for h, v in ((int(c["coord"]), c["value"]) for c in cap.global_state(k).get("cities") or ())}
    dead_end = pm.deadlocked(sim.units)
    cyc_end = pm.cycles(sim.units)
    affected = {uid for c in cyc0 for u in before if u.hex in c for uid in [u.uid]}
    affected_end = {u.uid: u for u in sim.units if u.uid in affected}
    stuck = sorted(uid for uid in affected if uid in dead_end)
    feasible = (error is None and not violations and (not cyc0 or cycle_absent_from is not None) and not cyc_end
                and not dead_end)
    verdict = "feasible" if feasible else ("unsupported" if error else "infeasible" if cyc_end or (cyc0 and cycle_absent_from is None)
                                          else "cycle broken, unresolved residual")
    public = {
        "alternative": label, "intervention": intervention, "start_k": k,
        "start_cur_step": cap.global_state(k)["time"]["cur_step"],
        "evidence": {"start state": "observed", "orders and trajectory after start": "model-derived",
                     "engine acceptance of the orders": "unverified"},
        "model": "M1b (protocol amendment 1)", "assumptions": list(assumptions), "unverified": list(unverified),
        "observable_inputs": ["own units' cur_hex, move_path, type, basic_speed, on_board (seat observation)",
                              "objective flags (seat observation)", "setup cost graph", "the policy's own step history"],
        "commands": dict(collections.Counter(e.kind for e in commands)),
        "first_command_k": min((e.step for e in commands if e.kind in ("stop", "order")), default=None),
        "capacity_violations": len(violations), "model_error": error,
        "initial_cycles": len(cyc0), "cycle_broken_at_k": cycle_absent_from,
        "cycles_at_end": len(cyc_end), "deadlocked_at_end": len(dead_end),
        "affected_units": len(affected), "affected_units_deadlocked_at_end": len(stuck),
        "affected_units_moving_at_end": sum(1 for u in affected_end.values() if u.moving),
        "objectives_held_at_end": sorted(labels[h] for h, f in sim.objectives.items() if f == cap.faction),
        "occupy_points_at_end": sum(int(lbl.rsplit("_", 1)[1]) for lbl in
                                    (labels[h] for h, f in sim.objectives.items() if f == cap.faction)),
        "flag_steps": {labels[e.detail[0]]: e.step for e in sim.events if e.kind == "flag"},
        "witnesses": len(state.witnesses) if state is not None else 0,
        "verdict": verdict,
    }
    private = dict(public, events=[(e.step, e.kind, e.uid, list(e.detail)) for e in sim.events],
                   witnesses_detail=state.witnesses if state is not None else [],
                   end_state=[(u.uid, u.hex, list(u.path)) for u in sim.units], cycles_initial=cyc0, violations=violations)
    return {"public": public, "private": private}


def synthetic_no_escape() -> Dict[str, Any]:
    """A6: a dead-end corridor where neither group has a free hex or a bypass (failure witness, model only)."""
    edges = {1: {2: 1.0}, 2: {1: 1.0, 3: 1.0}, 3: {2: 1.0, 4: 1.0}, 4: {3: 1.0}}
    units = [pm.Unit(i, 1, 36.0, 0, (2, 3), ready_at=0) for i in (1, 2, 3, 4)] + \
            [pm.Unit(i, 2, 36.0, 0, (1,), ready_at=0) for i in (5, 6, 7, 8)]
    sim = pm.Simulation(units, {0: edges}, step=100, objectives={1: 0, 4: -1}, faction=0, end_step=400)
    state = pm.Recovery()
    sim.run(pm.ps1b(state))
    return {"alternative": "A6", "intervention": "PS-1B on a dead-end corridor (synthetic)",
            "evidence": {"everything": "model-derived (synthetic graph)"}, "recoveries": sum(1 for e in sim.events if e.kind == "recover"),
            "no_escape_events": sum(1 for e in sim.events if e.kind == "no-escape"), "witnesses": state.witnesses,
            "deadlocked_at_end": len(pm.deadlocked(sim.units)), "verdict": "no escape (failure witness)"}


def restart_episodes(sequence: Sequence[Tuple[int, Mapping[str, Any]]], seat: int, faction: int,
                     edges: Mapping[int, pm.Edges]) -> List[Dict[str, Any]]:
    """Amendment 1's independent check: episodes of a unit with a path standing at speed 0 in front of a hex holding
    four own ground units, keeping its path, then seeing room and entering. ``d`` = entry step - first step with room."""
    episodes: List[Dict[str, Any]] = []
    open_: Dict[int, Dict[str, Any]] = {}
    for step, obs in sequence:
        info = obs.get("role_and_grouping_info") or {}
        listed = set((info.get(seat) or info.get(str(seat)) or {}).get("operators") or ())
        own = {r["obj_id"]: r for r in obs.get("operators") or [] if r.get("obj_id") in listed
               and r.get("type") in GROUND and not r.get("on_board")}
        occ = collections.Counter(r["cur_hex"] for r in own.values())
        for oid, ep in list(open_.items()):
            r = own.get(oid)
            if r is None or tuple(r.get("move_path") or ()) not in (ep["path"], ep["path"][1:]):
                del open_[oid]  # gone, or a new order: excluded
                continue
            if r["cur_hex"] == ep["target"]:
                # an entry in the very step the hex got room (no room seen before) is d = 0: M1's behaviour must be
                # observable, or the check could only ever confirm M1b
                episodes.append({"d": step - (ep["room"] if ep["room"] is not None else step), "tau": ep["tau"]})
                del open_[oid]
                continue
            if ep["room"] is None and occ[ep["target"]] < pm.K:
                ep["room"] = step
        for oid, r in own.items():
            path = tuple(r.get("move_path") or ())
            if oid in open_ or not path or (r.get("speed") or 0) != 0 or occ[path[0]] < pm.K:
                continue
            mode = move_mode(r["type"], r.get("move_state"))
            cost = edges[int(mode)].get(r["cur_hex"], {}).get(path[0]) if mode is not None else None
            if cost is None:
                continue
            open_[oid] = {"target": path[0], "path": path, "room": None, "tau": pm.hex_time(float(r["basic_speed"]), cost)}
    return episodes


def classify_restarts(episodes: Sequence[Mapping[str, int]]) -> Dict[str, Any]:
    m1 = sum(1 for e in episodes if e["d"] in (0, 1))
    m1b = sum(1 for e in episodes if abs(e["d"] - (e["tau"] - 1)) <= 1)
    n = len(episodes)
    verdict = ("insufficient" if n < 10 else "supports M1b" if m1b >= 0.9 * n and m1 <= 0.1 * n else "does not support M1b")
    return {"episodes": n, "in_M1_window": m1, "in_M1b_window": m1b, "other": n - len({i for i, e in enumerate(episodes)
            if e["d"] in (0, 1) or abs(e["d"] - (e["tau"] - 1)) <= 1}), "verdict": verdict,
            "d_minus_tau_histogram": dict(sorted(collections.Counter(e["d"] - e["tau"] for e in episodes).items()))}


# ----------------------------------------------------------------------------------------------
# generalisation (G4): trigger census over historical observations


def census_sequence(observations: Iterable[Tuple[int, Mapping[str, Any], Sequence[Mapping[str, Any]]]], seat: int, faction: int,
                    edges: Mapping[int, pm.Edges]) -> Dict[str, Any]:
    """Run the PS-1 triggers over a sequence of (step, seat observation, own actions) of one seat."""
    last: Dict[int, int] = {}
    prev: Dict[int, int] = {}
    prev_dest: Dict[int, Optional[int]] = {}
    c = collections.Counter()
    firings: List[Dict[str, Any]] = []
    for step, obs, actions in observations:
        statics = {}
        units = []
        info = obs.get("role_and_grouping_info") or {}
        listed = set((info.get(seat) or info.get(str(seat)) or {}).get("operators") or ())
        for r in obs.get("operators") or []:
            if r.get("obj_id") in listed and r.get("type") in GROUND and not r.get("on_board"):
                oid = r["obj_id"]
                path = tuple(r.get("move_path") or ())
                if prev.get(oid) != r["cur_hex"] or (path and prev_dest.get(oid) != path[-1]):
                    last[oid] = step  # a hex change or a new order is progress
                prev[oid] = r["cur_hex"]
                prev_dest[oid] = path[-1] if path else None
                mode = move_mode(r["type"], r.get("move_state"))
                if mode is None:
                    continue
                statics[oid] = r
                units.append(pm.Unit(oid, r["cur_hex"], float(r["basic_speed"]), int(mode),
                                     tuple(r.get("move_path") or ()), last_progress=last.get(oid, step)))
        c["unit_steps"] += len(units)
        c["unit_steps_moving"] += sum(1 for u in units if u.moving)
        blocked = pm.blocked_units(units)
        c["unit_steps_blocked"] += len(blocked)
        dead = pm.deadlocked(units)
        c["unit_steps_deadlocked"] += len(dead)
        stalled = [u for u in units if pm.stalled(u, step, edges)]
        c["unit_steps_stalled"] += len(stalled)
        c["unit_steps_stalled_not_blocked"] += sum(1 for u in stalled if u.uid not in blocked)
        if dead and all(pm.stalled(next(u for u in units if u.uid == d), step, edges) for d in dead):
            c["ps1b_trigger_steps"] += 1
            if len(firings) < 50:
                firings.append({"step": step, "deadlocked": len(dead), "cycles": len(pm.cycles(units))})
        cities = {int(x["coord"]): int(x["flag"]) for x in obs.get("cities") or ()}
        stale = [u for u in units if u.moving and u.destination in cities and cities[u.destination] == faction
                 and u.hex != u.destination]
        c["retarget_trigger_unit_steps"] += len(stale)
        # PS-1A admission over the orders actually issued this step, counting earlier orders of the step
        sim = pm.Simulation(units=list(units), edges_by_mode=edges, step=step, objectives=cities, faction=faction)
        for act in actions:
            if act.get("type") == MOVE and act.get("obj_id") in statics:
                path = tuple(act["move_path"])
                c["orders"] += 1
                u = next((x for x in sim.units if x.uid == act["obj_id"]), None)
                if u is None or u.moving:
                    continue
                verdict = pm.ps1a_admit(sim, u, path)
                if verdict != path:
                    c["ps1a_would_change_order"] += 1
                sim.units = [pm.Unit(x.uid, x.hex, x.speed, x.mode, path if x.uid == u.uid else x.path,
                                     last_progress=x.last_progress) for x in sim.units]
    return {"counts": dict(c), "private": {"firings": firings}}


def corpus_games(root: Path) -> Iterable[Tuple[str, Dict[int, List[Tuple[int, Mapping[str, Any], List[Mapping[str, Any]]]]], Dict[int, int]]]:
    for path in sorted(root.glob("*.jsonl.gz")):
        seqs: Dict[int, List] = collections.defaultdict(list)
        factions: Dict[int, int] = {}
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            header = json.loads(handle.readline())
            for line in handle:
                rec = json.loads(line)
                obs = typed_json.decode(rec["observation"])
                if not isinstance(obs, dict) or obs.get("time", {}).get("stage") != 2:
                    continue
                seqs[rec["seat"]].append((obs["time"]["cur_step"], obs, [typed_json.decode(a) for a in rec["actions"]]))
                factions[rec["seat"]] = rec["faction"]
        yield header.get("game_id", path.name), seqs, factions


def load_costs(work: Path, manifest: Mapping[str, Any], scenario: str) -> Tuple[MoveCosts, str]:
    entry = next(s for s in manifest["scenarios"] if s["scenario_id"] == scenario)
    path = sdk_data.map_paths(work / "data" / scenario / "Data", entry["map_id"])["cost"]
    digest = sha256(path)
    if digest != entry["inputs_sha256"]["cost"]:
        raise SystemExit(f"REFUSED: {path} does not match the manifest's cost digest")
    return MoveCosts.from_raw(sdk_data.load_cost(path), Origin.ENGINE), digest


def inputs_digest(work: Path) -> Dict[str, str]:
    files = sorted(list((work / "games").glob("*.json")) + list((work / "capture").glob("*")))
    return {f.relative_to(work).as_posix(): sha256(f) for f in files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--private", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1")
    parser.add_argument("--public", type=Path, default=REPO_ROOT / "evaluation" / "ps1-design-1")
    parser.add_argument("--corpus-root", type=Path, default=REPO_ROOT / "local" / "replay-corpus")
    parser.add_argument("--smoke", type=Path, default=REPO_ROOT / "local" / "evaluation" / f"{SCREEN}-smoke")
    parser.add_argument("--skip-generalisation", action="store_true")
    parser.add_argument("--stage", choices=("observed", "all"), default="all",
                        help="observed: reconstruction, audit and fidelity only (no counterfactual is computed)")
    args = parser.parse_args()
    manifest = load(REPO_ROOT / "evaluation" / SCREEN / "manifest.json")
    before = inputs_digest(args.work)
    costs, cost_digest = load_costs(args.work, manifest, SCENARIO)
    edges = {int(m): costs.edges[m] for m in range(len(costs.edges))}
    caps = {g: Capture.read(args.work, g) for g in (BASELINE_GAME, CANDIDATE_GAME)}
    recon = {g: reconstruct(c, costs) for g, c in caps.items()}
    fid = {g: {"M1": fidelity(caps[g], costs, recon[g]), "M1b": fidelity(caps[g], costs, recon[g], restart=True)}
           for g in caps}
    restart_sprint2 = []
    for g, cap in caps.items():
        restart_sprint2 += restart_episodes([(k, cap.observation(k)) for k in cap.ks()], cap.seat, cap.faction, edges)
    cand, rc = caps[CANDIDATE_GAME], recon[CANDIDATE_GAME]
    k_detect = rc["first_detection_k"]
    k_play = first_play_k(cand)
    k_flip = next((k for k in cand.ks() if objectives_at(cand, k) != objectives_at(cand, k_play)), None)
    base = ["M1", "M2", "M4", "M5", "M6", "M7"]
    certs = {}
    plans = [("A1", "PS-1A capacity-aware dispatch from the first play decision", k_play, "ps1a", base, ["E5"])]
    if k_flip is not None:
        plans.append(("A4", "sequencing: stop units bound for an objective that became own-held, then re-order", k_flip,
                      "retarget", base + ["M3"], ["E5", "C2 for a moving unit (documented)", "E3", "E4"]))
    if k_detect is not None:
        stop = base + ["M3"]
        e_all = ["E1", "E2", "E3", "E4", "E5"]
        plans += [("A2", "PS-1B: stop the waiting group and back it off to free hexes", k_detect, "ps1b-back-off", stop, e_all),
                  ("A3", "PS-1B: stop the occupying group and re-route it around the full corridor", k_detect, "ps1b-bypass", stop, e_all),
                  ("A5a", "PS-1B (back-off or bypass) 300 steps after first detection", min(k_detect + 300, len(cand.steps) - 1), "ps1b-back-off", stop, e_all),
                  ("A5b", "PS-1B (back-off or bypass) 900 steps after first detection", min(k_detect + 900, len(cand.steps) - 1), "ps1b-back-off", stop, e_all)]
    if args.stage == "observed":
        plans = []
    for label, text, k, factory, assumptions, unverified in plans:
        certs[label] = certificate(label, text, cand, costs, rc, k, factory, assumptions, unverified)
    a6 = synthetic_no_escape() if args.stage == "all" else {"verdict": "not computed"}
    general: Dict[str, Any] = {}
    corpus_restarts_result: Optional[Dict[str, Any]] = None
    if not args.skip_generalisation and args.stage == "all":
        for g, cap in caps.items():
            seq = [(k, cap.observation(k), cap.own_actions(k)) for k in cap.ks() if cap.observation(k)["time"]["stage"] == 2]
            general[g] = census_sequence(seq, cap.seat, cap.faction, edges)
        corpus_costs: Dict[str, Any] = {}
        corpus_restarts: List[Dict[str, int]] = []
        for game, seqs, factions in corpus_games(args.corpus_root):
            sid = game.split(".")[0]
            if sid not in corpus_costs:
                corpus_costs[sid] = load_costs(REPO_ROOT / "local" / "evaluation" / SCREEN, manifest, sid)[0]
            ce = {int(m): corpus_costs[sid].edges[m] for m in range(len(corpus_costs[sid].edges))}
            for seat, seq in sorted(seqs.items()):
                general[f"corpus {game} seat {seat}"] = census_sequence(seq, seat, factions[seat], ce)
                corpus_restarts.extend(restart_episodes([(st, ob) for st, ob, _ in seq], seat, factions[seat], ce))
        smoke_totals = collections.Counter()
        smoke_files = sorted((args.smoke / "games").glob("*.json")) if (args.smoke / "games").exists() else []
        for rec_path in smoke_files:
            game = rec_path.stem
            cap = Capture.read(args.smoke, game)
            sid = game.split(".")[0]
            if sid not in corpus_costs:
                corpus_costs[sid] = load_costs(REPO_ROOT / "local" / "evaluation" / SCREEN, manifest, sid)[0]
            ce = {int(m): corpus_costs[sid].edges[m] for m in range(len(corpus_costs[sid].edges))}
            seq = [(k, cap.observation(k), cap.own_actions(k)) for k in cap.ks() if cap.observation(k)["time"]["stage"] == 2]
            res = census_sequence(seq, cap.seat, cap.faction, ce)
            general[f"smoke {game}"] = res
            smoke_totals.update(res["counts"])
        general["smoke totals"] = {"counts": dict(smoke_totals), "private": {}}
        corpus_restarts_result = classify_restarts(corpus_restarts)
    after = inputs_digest(args.work)
    if before != after:
        raise SystemExit("REFUSED: an input file changed during the study")
    args.private.mkdir(parents=True, exist_ok=True)
    (args.private / "certificates").mkdir(exist_ok=True)
    private = {"inputs_sha256": before, "cost_sha256": cost_digest,
               "reconstruction": recon, "fidelity": fid, "generalisation": general}
    (args.private / "study.json").write_text(json.dumps(private, indent=1, sort_keys=True, default=list) + "\n", encoding="utf-8")
    for label, cert in certs.items():
        (args.private / "certificates" / f"{label}.json").write_text(json.dumps(cert["private"], indent=1, sort_keys=True, default=list) + "\n",
                                                                     encoding="utf-8")
    (args.private / "certificates" / "A6.json").write_text(json.dumps(a6, indent=1, sort_keys=True, default=list) + "\n", encoding="utf-8")

    def strip(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k != "private"}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    corpus_totals = collections.Counter()
    for key, val in general.items():
        if key.startswith("corpus"):
            corpus_totals.update(val["counts"])
    public = {"schema": "miaosuan-ps1-design/1", "status": "DESIGN STUDY", "inputs_unchanged": True,
              "input_files": len(before), "reconstruction": strip(recon), "fidelity": strip(fid),
              "restart_check": {"sprint2 games (not independent)": classify_restarts(restart_sprint2),
                                "replay corpus (independent, amendment 1)": corpus_restarts_result},
              "certificates": {k: v["public"] for k, v in certs.items()},
              "A6": {k: v for k, v in a6.items() if k != "witnesses"} | {"witnesses": len(a6.get("witnesses", []))},
              "generalisation": {k: v["counts"] for k, v in general.items() if not k.startswith(("corpus", "smoke 1", "smoke 2"))}
              | {"replay corpus (8 games, both seats)": dict(corpus_totals),
                 "replay corpus seat-sequences": sum(1 for k in general if k.startswith("corpus"))}}
    args.public.mkdir(parents=True, exist_ok=True)
    text = json.dumps(public, indent=1, sort_keys=True, default=list) + "\n"
    for forbidden in ("obj_id", "cur_hex"):
        if forbidden in text:
            raise SystemExit(f"REFUSED: the public summary contains {forbidden}")
    (args.public / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.public / 'summary.json'} and {args.private}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
