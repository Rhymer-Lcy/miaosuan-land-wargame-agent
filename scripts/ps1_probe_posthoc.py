"""PS-1 engine probe, POST-HOC descriptions; written after every registered verdict was computed, changes none.

    PYTHON scripts/ps1_probe_posthoc.py [--work DIR] [--t1r DIR] [--public DIR] [--private DIR]

``docs/PS1_ENGINE_PROBE.md`` (results, post-hoc section) reports what this computes:

1. P1, the stop's observable footprint on each stopped unit: ``flag_force_stop``, the listed actions, the remaining
   path, ``move_to_stop_remain_time`` and ``stop`` before and after the stop, to the end of the game; and how often
   ``flag_force_stop`` is set anywhere else in P1 and P2;
2. P2, the anatomy of F1's late entries: per unit, whether its first late entry follows a move order issued while the
   order's first hex held four own ground units (and the unit then stood at speed 0 until room appeared);
3. a post-hoc candidate M1d = M1c plus "a unit ordered while its first hex is full waits at once" (the order-time twin
   of M1c's wait at entry), replayed on P2 and, for non-regression, on both Sprint 2 games. M1d is derived from P2
   and is evidence for nothing; it would need its own prospective test;
4. an order-aware re-reading of the T-c and T-d events: the registered rules compared contenders by end-of-step
   occupancy and lowest index; here every unit that entered or left the contested hex in the step, contenders
   included, is processed in ascending index with the occupancy updated after each move, as M1c itself does;
5. why F2 diverges: shots, aircraft orders and occupations the surrogate does not model, and its first divergences.

Inputs are the registered probe captures (``local/evaluation/ps1-engine-probe-1``) and, for item 3, the Sprint 2
captures. The public output holds counts and step indices only.
"""

from __future__ import annotations

import argparse
import collections
import copy
import importlib.util
import json
import pickle
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation import ps1_model as pm  # noqa: E402
from miaosuan_agent.evaluation import ps1_probe as pp  # noqa: E402


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


an = _load("ps1_probe_analysis")
dry = _load("ps1_probe_dryrun")
K = pp.K
FIELDS = ("flag_force_stop", "stop", "move_to_stop_remain_time")


# ----------------------------------------------------------------------------------------------
# 1. the stop's footprint


def stop_footprint(game: Any, group: Sequence[int], k0: int) -> Dict[str, Any]:
    rows: Dict[str, collections.Counter] = {"before": collections.Counter(), "after": collections.Counter()}
    path_kept, first_flag = 0, []
    for uid in group:
        before = game.observation(k0)
        start = next(r for r in before["operators"] if r["obj_id"] == uid)
        path0 = tuple(start.get("move_path") or ())
        kept, flagged = True, None
        for k in sorted(game.samples):
            obs = game.observation(k)
            r = next((x for x in obs["operators"] if x["obj_id"] == uid), None)
            if r is None:
                continue
            listed = tuple(sorted((obs.get("valid_actions") or {}).get(uid) or {}))
            phase = "before" if k <= k0 else "after"
            rows[phase][(tuple(r.get(f) for f in FIELDS), listed)] += 1
            if k > k0:
                kept = kept and tuple(r.get("move_path") or ()) == path0
                if flagged is None and r.get("flag_force_stop"):
                    flagged = k - k0
        path_kept += kept
        first_flag.append(flagged)
    return {"units": len(group), "path_kept_to_the_end": path_kept,
            "steps_from_stop_to_flag_force_stop": sorted(set(first_flag), key=str),
            "states": {phase: {f"flag_force_stop={s[0][0]} stop={s[0][1]} move_to_stop_remain_time={s[0][2]} "
                               f"listed={list(s[1])}": n for s, n in sorted(c.items(), key=str)}
                       for phase, c in rows.items()}}


def flag_elsewhere(game: Any, exclude: Sequence[int]) -> Dict[str, int]:
    steps, units = 0, set()
    for k in sorted(game.samples):
        for r in game.global_state(k)["operators"]:
            if r.get("flag_force_stop") and r["obj_id"] not in exclude:
                steps += 1
                units.add(r["obj_id"])
    return {"unit_steps": steps, "units": len(units)}


# ----------------------------------------------------------------------------------------------
# 2./3. lateness anatomy and the post-hoc M1d


def orders_of(game: Any, t: Any, k0: int) -> Dict[int, List[Tuple[str, int, Tuple[int, ...]]]]:
    actions = an.seat_actions(game, an.fresh_feedback(game.steps))
    eligible = set().union(*(set(t.b[k]) for k in t.ks if k >= k0))
    orders: Dict[int, List[Tuple[str, int, Tuple[int, ...]]]] = collections.defaultdict(list)
    for a in actions:
        if a.k >= k0 and a.submitted.get("obj_id") in eligible and an.accepted(a):
            kind = {1: "move", 5: "occupy", 10: "stop"}.get(a.submitted.get("type"))
            if kind:
                orders[a.k].append((kind, a.submitted["obj_id"], tuple(a.submitted.get("move_path") or ())))
    return orders


def replay_m1d(t: Any, k0: int, edges: Mapping[int, pm.Edges], faction: int,
               orders: Mapping[int, Sequence[Tuple[str, int, Tuple[int, ...]]]]) -> List[Tuple[int, int, int]]:
    """The registered replay with one change: a move ordered while its first hex holds K own ground units (in the
    model, at the decision) leaves the unit waiting at once instead of starting its traversal."""
    start_rows = t.b[k0]
    units = [an.model_unit(uid, r) for uid, r in sorted(start_rows.items())]
    blocked = {int(m): t.roadblocks for m in an.ROADBLOCKED_MODES}
    sim = pm.Simulation(units=units, edges_by_mode=edges, step=k0, faction=faction, end_step=t.ks[-1],
                        objectives={h: f for h, (_, f) in t.cities[k0].items()}, blocked_by_mode=blocked,
                        restart_after_wait=True, wait_at_entry=True)
    gone, new = an.removals(t.b, t.ks, k0), an.appearances(t.b, t.ks, k0)

    def policy(s: pm.Simulation) -> None:
        for uid in gone.get(s.step, ()):
            s.units = [u for u in s.units if u.uid != uid]
        for uid in new.get(s.step, ()):
            s.units = s.units + [an.model_unit(uid, t.b[s.step][uid])]
        for kind, uid, path in orders.get(s.step, ()):
            if uid not in {u.uid for u in s.units}:
                continue
            try:
                if kind == "move":
                    occ = pm.occupancy(s.units)
                    s.order_move(uid, path)
                    if occ.get(path[0], 0) >= K:
                        s._put(replace(s.unit(uid), waiting=True, ready_at=None))
                elif kind == "stop":
                    s.order_stop(uid)
                elif kind == "occupy":
                    s.occupy(uid)
            except pm.ModelError:
                pass

    sim.run(policy)
    return [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"]


def fidelity_summary(simulated: Sequence[Tuple[int, int, int]], observed: Sequence[Tuple[int, int, int]], k0: int) -> Dict[str, Any]:
    cmp = an.study.compare_entries(simulated, observed, k0)
    off = an.offsets(simulated, observed)
    return {"hex_sequences_differ": cmp["hex_sequences_differ"], "worst_step_offset": cmp["worst_step_offset"],
            "observed_entries": cmp["observed_entries"], "offset_histogram": {str(k): v for k, v in sorted(off.items())}}


def lateness(t: Any, k0: int, orders: Mapping[int, Sequence[Tuple[str, int, Tuple[int, ...]]]],
             simulated: Sequence[Tuple[int, int, int]]) -> Dict[str, Any]:
    observed = an.observed_entries(t.b, t.ks, k0)
    by_o, by_s = collections.defaultdict(list), collections.defaultdict(list)
    for k, u, h in observed:
        by_o[u].append((k, h))
    for k, u, h in simulated:
        by_s[u].append((k, h))
    late_units: Dict[int, Tuple[int, int]] = {}
    late_entries = 0
    for u in by_o:
        for i, ((ko, _), (ks, _)) in enumerate(zip(by_o[u], by_s[u])):
            if ks != ko:
                late_entries += 1
                late_units.setdefault(u, (i, ko))
    classes: collections.Counter = collections.Counter()
    for u, (i, ko) in late_units.items():
        prev = by_o[u][i - 1][0] if i else k0
        order = next(((k, path) for k in sorted(orders) if prev <= k < ko for kind, v, path in orders[k]
                      if kind == "move" and v == u), None)
        if order is not None:
            k, path = order
            full = collections.Counter(r.hex for r in t.b[k].values())[path[0]] >= K
            waited = t.b.get(k + 1, {}).get(u) is not None and (t.b[k + 1][u].speed or 0) == 0
            classes["ordered while its first hex was full, then stood at speed 0" if full and waited else
                    "ordered with room in its first hex"] += 1
        else:
            classes["no order since its previous entry"] += 1
    return {"late_entries": late_entries, "units_with_late_entries": len(late_units),
            "first_late_entry_by_class": dict(sorted(classes.items()))}


# ----------------------------------------------------------------------------------------------
# 4. order-aware arbitration and re-waits


def order_aware(channel: Mapping[int, Mapping[int, Any]], ks: Sequence[int]) -> Dict[str, Any]:
    """For every step and hex where traversing units finish (enter or re-wait): process every unit whose position
    changed into or out of the hex in the step, and the finishers, in ascending index; a finisher enters when the hex
    holds fewer than K at its turn. Agreement with the observed entrants and re-waiters."""
    agree, disagree, events = 0, 0, 0
    for prev_k, k in zip(ks, ks[1:]):
        prev, cur = channel[prev_k], channel[k]
        finishers = collections.defaultdict(list)
        for uid, r in prev.items():
            if r.path and (r.speed or 0) != 0 and uid in cur:
                h = r.path[0]
                if cur[uid].hex == h or ((cur[uid].speed or 0) == 0 and cur[uid].path and cur[uid].path[0] == h):
                    finishers[h].append(uid)
        for h, members in finishers.items():
            entered = {u for u in members if cur[u].hex == h}
            rewaited = set(members) - entered
            if not rewaited:
                continue
            events += 1
            occ = sum(1 for r in prev.values() if r.hex == h)
            movers = {u for u in cur if u in prev and (prev[u].hex == h) != (cur[u].hex == h)} | set(members)
            predicted = set()
            for u in sorted(movers):
                if u in members:
                    if occ < K:
                        predicted.add(u)
                        occ += 1
                elif prev[u].hex == h:
                    occ -= 1
                else:
                    occ += 1
            if predicted == entered:
                agree += 1
            else:
                disagree += 1
    return {"steps_with_a_re_wait": events, "order_aware_agrees": agree, "order_aware_disagrees": disagree}


# ----------------------------------------------------------------------------------------------
# 5. F2 divergence


def f2_anatomy(game: Any, t: Any, k0: int) -> Dict[str, Any]:
    actions = an.seat_actions(game, an.fresh_feedback(game.steps))
    eligible = set(t.b[k0])
    out: collections.Counter = collections.Counter()
    for a in actions:
        if a.k < k0:
            continue
        kind, uid = a.submitted.get("type"), a.submitted.get("obj_id")
        if kind == 2:
            out["shots (the surrogate never shoots)"] += 1
        elif kind == 1 and uid not in eligible:
            out["moves of units outside the model (aircraft)"] += 1
        elif kind == 5:
            out["occupations"] += 1
    return dict(sorted(out.items()))


# ----------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / pp.PROBE_ID)
    parser.add_argument("--t1r", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--public", type=Path, default=REPO_ROOT / "evaluation" / pp.PROBE_ID)
    parser.add_argument("--private", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1-probe")
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "evaluation" / pp.PROBE_ID / "manifest.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    out: Dict[str, Any] = {"schema": "miaosuan-ps1-probe-posthoc/1", "status": "POST HOC (changes no registered verdict)"}

    p1 = an.Game.read(args.work, pp.P1_GAME)
    hooks = an.hook_events(p1)
    k0 = hooks["trigger_k"]
    group = sorted(a["action"]["obj_id"] for a in p1.steps[k0]["submitted"] if a["action"]["type"] == 10)
    out["p1_stop_footprint"] = stop_footprint(p1, group, k0)
    out["flag_force_stop_elsewhere"] = {"P1 other units": flag_elsewhere(p1, group)}

    p2 = an.Game.read(args.work, pp.P2_GAME)
    out["flag_force_stop_elsewhere"]["P2 every unit"] = flag_elsewhere(p2, ())
    costs = an.load_costs(args.work, manifest, "1930331196")
    edges = an.edges_of(costs)
    t = p2.tables()
    kp = p2.first_play_k()
    orders = orders_of(p2, t, kp)
    m1c = an.replay(t, kp, edges, p2.faction, orders=orders).entries
    observed = an.observed_entries(t.b, t.ks, kp)
    out["p2_lateness_under_m1c"] = lateness(t, kp, orders, m1c)
    m1d = replay_m1d(t, kp, edges, p2.faction, orders)
    out["m1d"] = {"definition": "M1c plus: a unit ordered while its first hex holds four own ground units waits at "
                                "once (then restarts under M1b); derived from P2 after its registered verdicts",
                  "P2": fidelity_summary(m1d, observed, kp)}
    s2_costs = an.load_costs(args.t1r, manifest, "1910631192")
    s2_edges = an.edges_of(s2_costs)
    for game_id in ("1910631192.C3.c.x01", "1910631192.C3.b.x01"):
        g, _ = dry.game(args.t1r, game_id)
        gt = g.tables()
        gk = g.first_play_k()
        go = orders_of(g, gt, gk)
        out["m1d"][f"Sprint 2 {game_id} (non-regression)"] = fidelity_summary(
            replay_m1d(gt, gk, s2_edges, g.faction, go), an.observed_entries(gt.b, gt.ks, gk), gk)
    play = [k for k in t.ks if k >= kp]
    out["order_aware_re_reading_p2"] = order_aware(t.b, play)
    out["f2_scope"] = f2_anatomy(p2, t, kp)
    text = json.dumps(out, indent=1, sort_keys=True, default=list) + "\n"
    for word in an.FORBIDDEN:
        if word in text:
            raise SystemExit(f"REFUSED: the public post-hoc output contains {word}")
    args.public.mkdir(parents=True, exist_ok=True)
    (args.public / "posthoc.json").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
