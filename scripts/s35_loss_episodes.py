"""Sprint 35: the held-objective losses of Sprint 34's Stage A games, episode by episode (post hoc, read-only).

    python scripts/s35_loss_episodes.py [--work DIR] [--data DIR] [--private FILE] [--out FILE] [--workers N]

For each of the 16 Stage A games of the Sprint 34 live card (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 11), every
step at which an objective the candidate side held changes flag is a loss episode. For each episode this script reads

* the compact all-seeing timeline (what was really there): own and enemy ground units in the objective's zone at fixed
  look-backs, their classes and remaining strength, the step the last own unit left the zone and the step enemy ground
  units entered it, and what became of the own units that were in the zone 150 steps earlier (destroyed in the zone,
  destroyed elsewhere, or alive outside it);
* the candidate seat's own recorded observation (what the seat could legally know): visible enemy ground units within
  4 and 8 hexes of the objective, and their classes, at the same look-backs;
* the candidate's recorded per-unit plans: the module and task kind under which each departing unit was moved;
* the setup movement-cost graph: which own ground units, not in the zone and not aboard, could have reached the
  objective (free-flow time, a lower bound) before the loss from the step the first enemy was visible within 8 hexes.

It also samples every held objective every 25 steps (the decision states, not only the losses) and records whether it
was lost within the next 300 steps, so that a candidate predictor can be read against the states where nothing was
lost. Everything here is post hoc and descriptive; nothing is a counterfactual outcome.

Private detail (per episode, with steps; no hexes or ids) goes to ``--private``; the public file holds aggregates only.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import multiprocessing as mp
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

LOOKBACKS = (1, 75, 150, 300)
RADII = (4, 8)
SAMPLE_EVERY = 25
HORIZON = 300
GROUND_TYPES = (1, 2)
CLASS = {0: "tank", 1: "ifv", 2: "squad", 3: "artillery", 4: "ugv"}


def _cards():
    spec = importlib.util.spec_from_file_location("s35l_cards", REPO_ROOT / "scripts" / "build_s34_card.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ground(rows, colour):
    """Ground units of a side on the map (passengers excluded): row = [id, colour, type, sub, hex, plen, speed, blood,
    value, aboard]."""
    return [r for r in rows if r[1] == colour and r[2] in GROUND_TYPES and not r[9]]


def one(job) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.boundary import MoveCosts, Observation, Origin
    from miaosuan_agent.evaluation import s34_live as sl
    from miaosuan_agent.integrated import facts as F
    from miaosuan_agent.integrated.movement import Terrain, unit_mode
    from miaosuan_agent.integrated.world import build_world
    work, game, data_root, map_id = job
    colour = 0 if sl.CANDIDATE_SIDE[game["condition"]] == "red" else 1
    seat = 1 if colour == 0 else 11
    compact = json.loads((Path(work) / "capture" / f"{game['game_id']}.timeline.json").read_text(encoding="utf-8"))
    steps = [s for s in compact["steps"] if s["k"] >= 0]
    windows = pickle.load(open(Path(work) / "capture" / f"{game['game_id']}.timeline.pkl", "rb"))
    samples = {s["cur_step"]: s for s in windows["samples"]}
    inputs = sdk_data.load_inputs(Path(data_root), game["scenario_id"], map_id)
    costs = MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "cost")
    terrain = Terrain(costs)
    by_step = {s["cur_step"]: s for s in steps}
    max_step = steps[-1]["cur_step"]

    def view(step):
        sample = samples.get(step)
        if sample is None or str(seat) not in sample["seats"]:
            return None, None
        snap = sample["seats"][str(seat)]
        raw = pickle.loads(snap["observation"])
        obs = Observation.from_raw(raw, Origin.ENGINE)
        return build_world(obs, seat, colour, terrain.rows, terrain.cols), snap

    def visible_near(world, centre):
        out = {}
        for radius in RADII:
            near = [e for e in world.enemies if e.ground and F.hex_distance(e.hex, centre) <= radius]
            out[f"r{radius}"] = {"n": len(near), "blood": sum(e.blood for e in near),
                                 "classes": dict(collections.Counter(CLASS.get(e.sub_type, "other") for e in near))}
        return out

    def eta(row_unit, target, world):
        unit = world.unit(row_unit) if world is not None else None
        if unit is None or unit.aboard:
            return None
        mode = unit_mode(unit.type, unit.move_state)
        if mode is None:
            return None
        cost = terrain.cost_to(mode, unit.hex, target, world.roadblocks)
        return terrain.seconds(unit.basic_speed, cost)

    episodes: List[Dict[str, Any]] = []
    prev: Dict[int, Any] = {}
    for i, s in enumerate(steps):
        for coord, flag, value in s["cities"]:
            if prev.get(coord) == colour and flag != colour:
                zone = F.zone(coord, terrain.rows, terrain.cols)
                t = s["cur_step"]
                ep: Dict[str, Any] = {"step": t, "value": value, "new_flag": "enemy" if flag == 1 - colour else "none"}
                for back in LOOKBACKS:
                    st = by_step.get(max(0, t - back), steps[0])
                    own = [r for r in ground(st["units"], colour) if r[4] in zone]
                    enemy = [r for r in ground(st["units"], 1 - colour) if r[4] in zone]
                    ep[f"truth_b{back}"] = {
                        "own": len(own), "enemy": len(enemy), "own_blood": sum(r[7] for r in own),
                        "enemy_blood": sum(r[7] for r in enemy),
                        "own_classes": dict(collections.Counter(CLASS.get(r[3], "other") for r in own)),
                        "enemy_classes": dict(collections.Counter(CLASS.get(r[3], "other") for r in enemy)),
                        "own_alive_ground": len(ground(st["units"], colour))}
                    world, _ = view(max(0, t - back))
                    ep[f"seen_b{back}"] = visible_near(world, coord) if world is not None else None
                # timing: last own presence and first enemy entry before the loss
                last_own = first_enemy = None
                for j in range(i, -1, -1):
                    st = steps[j]
                    if last_own is None and any(r[4] in zone for r in ground(st["units"], colour)):
                        last_own = st["cur_step"]
                    if any(r[4] in zone for r in ground(st["units"], 1 - colour)):
                        first_enemy = st["cur_step"]
                    elif first_enemy is not None:
                        break
                    if t - st["cur_step"] > 900:
                        break
                ep["last_own_in_zone_step"] = last_own
                ep["first_enemy_in_zone_step"] = first_enemy
                # what happened to the units in the zone 150 steps earlier
                before = by_step.get(max(0, t - 150), steps[0])
                ids_before = [r[0] for r in ground(before["units"], colour) if r[4] in zone]
                after_rows = {r[0]: r for r in s["units"]}
                fate = collections.Counter()
                departed_tasks = collections.Counter()
                for uid in ids_before:
                    r = after_rows.get(uid)
                    if r is None or r[7] <= 0:
                        # destroyed: where was it last seen?
                        last_hex = None
                        for j in range(i, max(-1, i - 160), -1):
                            rr = next((x for x in steps[j]["units"] if x[0] == uid), None)
                            if rr is not None:
                                last_hex = rr[4]
                                break
                        fate["destroyed_in_zone" if last_hex in zone else "destroyed_after_leaving"] += 1
                    elif r[9]:
                        fate["aboard"] += 1
                    elif r[4] in zone:
                        fate["still_in_zone"] += 1
                    else:
                        fate["alive_outside_zone"] += 1
                        # the plan under which it was last moved before leaving
                        for back in range(150, 0, -1):
                            sample = samples.get(t - back)
                            snap = sample["seats"].get(str(seat)) if sample else None
                            if not snap:
                                continue
                            for p in snap.get("plans") or ():
                                if p[0] == uid and p[4] == F.MOVE:
                                    departed_tasks[f"{p[1]}/{p[2]}"] += 1
                ep["fate_of_units_in_zone_b150"] = dict(fate)
                ep["departure_orders_by_module_kind"] = dict(departed_tasks)
                # the last standing defenders (own ground units in the zone without a path) and how they ended
                last_stand = None
                for j in range(i - 1, max(-1, i - 1800), -1):
                    standers = [r for r in ground(steps[j]["units"], colour) if r[4] in zone and r[5] == 0]
                    if standers:
                        last_stand = (j, [r[0] for r in standers], {r[0]: r[3] for r in standers})
                        break
                if last_stand is None:
                    ep["last_defenders"] = {"found_within_1800_steps": False}
                else:
                    j, ids, subs = last_stand
                    ends = collections.Counter()
                    classes = collections.Counter(CLASS.get(subs[u], "other") for u in ids)
                    for uid in ids:
                        nxt = next((x for x in steps[j + 1]["units"] if x[0] == uid), None) if j + 1 < len(steps) else None
                        if nxt is None or nxt[7] <= 0:
                            ends["destroyed"] += 1
                            continue
                        if nxt[9]:
                            ends["boarded"] += 1
                            continue
                        plan_kind = "no recorded order"
                        for back in range(0, 3):
                            sample = samples.get(steps[j]["cur_step"] - back)
                            snap = sample["seats"].get(str(seat)) if sample else None
                            for p in (snap.get("plans") or ()) if snap else ():
                                if p[0] == uid and p[4] == F.MOVE:
                                    plan_kind = f"ordered away: {p[1]}/{p[2]}"
                        ends[plan_kind] += 1
                    ep["last_defenders"] = {"found_within_1800_steps": True, "steps_before_loss": t - steps[j]["cur_step"],
                                            "count": len(ids), "classes": dict(classes), "ends": dict(ends)}
                # reserve reach from the first sighting of an enemy within 8 hexes in the 600 steps before the loss
                first_seen = None
                for back in range(600, 0, -25):
                    w, _ = view(max(0, t - back))
                    if w is not None and any(e.ground and F.hex_distance(e.hex, coord) <= 8 for e in w.enemies):
                        first_seen = t - back
                        break
                ep["first_seen_within_8_step"] = first_seen
                if first_seen is not None:
                    w, snap = view(first_seen)
                    plans = {p[0]: (p[1], p[2], p[3]) for p in (snap.get("plans") or ())} if snap else {}
                    reach = collections.Counter()
                    for unit in w.units:
                        if not unit.mobile_ground or unit.hex in zone:
                            continue
                        e = eta(unit.obj_id, coord, w)
                        if e is None:
                            continue
                        in_time = first_seen + e <= t
                        task = plans.get(unit.obj_id, ("none", "", -1))
                        holding_other = task[1] == "hold" and task[2] != coord
                        reach["could_arrive" if in_time else "too_far"] += 1
                        if in_time:
                            reach["could_arrive_while_holding_another"] += int(holding_other)
                            reach["could_arrive_free_or_reserve"] += int(task[0] in ("reserve", "none") and not unit.path)
                    ep["reserve_reach"] = dict(reach)
                    ep["warning_steps"] = t - first_seen
                episodes.append(ep)
            prev[coord] = flag

    # decision-state sample of every held objective: lost within the horizon or not, with the seat-legal features
    samples_out = []
    flags_by_step = {s["cur_step"]: {c: f for c, f, _ in s["cities"]} for s in steps}
    values = {c: v for c, _, v in steps[0]["cities"]}
    lost_at = collections.defaultdict(list)
    prevf: Dict[int, Any] = {}
    for s in steps:
        for c, f, _ in s["cities"]:
            if prevf.get(c) == colour and f != colour:
                lost_at[c].append(s["cur_step"])
            prevf[c] = f
    for t in range(SAMPLE_EVERY, max_step - HORIZON + 1, SAMPLE_EVERY):
        flags = flags_by_step.get(t)
        if flags is None:
            continue
        held = [c for c, f in flags.items() if f == colour]
        if not held:
            continue
        world, _ = view(t)
        if world is None:
            continue
        for c in held:
            zone = F.zone(c, terrain.rows, terrain.cols)
            own = [u for u in world.units + world.allies if u.ground and not u.aboard and u.hex in zone]
            seen = {r: [e for e in world.enemies if e.ground and F.hex_distance(e.hex, c) <= r] for r in RADII}
            lost = any(t < x <= t + HORIZON for x in lost_at[c])
            samples_out.append({"value": values.get(c), "own_in_zone": len(own),
                                "own_blood": sum(u.blood for u in own),
                                "seen_r4": len(seen[4]), "seen_r8": len(seen[8]),
                                "seen_r8_blood": sum(e.blood for e in seen[8]),
                                "lost_within_horizon": lost})
    return {"position": game["position"], "scenario_id": game["scenario_id"], "condition": game["condition"],
            "side": sl.CANDIDATE_SIDE[game["condition"]], "episodes": episodes, "held_samples": samples_out}


def aggregate(games: List[Dict[str, Any]]) -> Dict[str, Any]:
    eps = [e for g in games for e in g["episodes"]]
    out: Dict[str, Any] = {"games": len(games), "episodes": len(eps)}
    out["episodes_by_game"] = {f"p{g['position']:02d}": len(g["episodes"]) for g in games}
    out["new_flag"] = dict(collections.Counter(e["new_flag"] for e in eps))
    for back in LOOKBACKS:
        out[f"truth_own_in_zone_b{back}"] = dict(sorted(collections.Counter(e[f"truth_b{back}"]["own"] for e in eps).items()))
        out[f"truth_enemy_in_zone_b{back}"] = dict(sorted(collections.Counter(e[f"truth_b{back}"]["enemy"] for e in eps).items()))
        seen = [e[f"seen_b{back}"] for e in eps if e[f"seen_b{back}"] is not None]
        out[f"seen_r4_b{back}"] = dict(sorted(collections.Counter(x["r4"]["n"] for x in seen).items()))
        out[f"seen_r8_b{back}"] = dict(sorted(collections.Counter(x["r8"]["n"] for x in seen).items()))
    fate = collections.Counter()
    for e in eps:
        fate.update(e["fate_of_units_in_zone_b150"])
    out["fate_of_units_in_zone_b150"] = dict(sorted(fate.items()))
    dep = collections.Counter()
    for e in eps:
        dep.update(e["departure_orders_by_module_kind"])
    out["departure_orders_by_module_kind"] = dict(sorted(dep.items()))
    kinds = collections.Counter()
    for e in eps:
        f = e["fate_of_units_in_zone_b150"]
        if not f:
            kinds["no_own_unit_in_zone_150_before"] += 1
        elif f.get("alive_outside_zone") and not (f.get("destroyed_in_zone") or f.get("destroyed_after_leaving")):
            kinds["defenders_left_alive"] += 1
        elif (f.get("destroyed_in_zone") or 0) and not f.get("alive_outside_zone"):
            kinds["defenders_destroyed_in_zone"] += 1
        else:
            kinds["mixed"] += 1
    out["episode_kind"] = dict(sorted(kinds.items()))
    last_ends = collections.Counter()
    last_kind = collections.Counter()
    last_classes = collections.Counter()
    gap = []
    for e in eps:
        ld = e.get("last_defenders", {})
        if not ld.get("found_within_1800_steps"):
            last_kind["no standing defender within 1800 steps"] += 1
            continue
        last_ends.update(ld["ends"])
        last_classes.update(ld["classes"])
        gap.append(ld["steps_before_loss"])
        ends = ld["ends"]
        if set(ends) == {"destroyed"}:
            last_kind["all last defenders destroyed"] += 1
        elif not ends.get("destroyed"):
            last_kind["all last defenders left alive"] += 1
        else:
            last_kind["some destroyed, some left"] += 1
    out["last_defenders_end"] = dict(sorted(last_ends.items()))
    out["last_defenders_episode_kind"] = dict(sorted(last_kind.items()))
    out["last_defenders_classes"] = dict(sorted(last_classes.items()))
    out["last_defenders_steps_before_loss"] = sorted(gap)
    warned = [e for e in eps if e.get("first_seen_within_8_step") is not None]
    out["episodes_with_enemy_seen_within_8_in_600_before"] = len(warned)
    out["warning_steps"] = sorted(e["warning_steps"] for e in warned)
    reach = collections.Counter()
    for e in warned:
        rr = e.get("reserve_reach", {})
        reach["episodes_with_any_unit_able_to_arrive"] += int(rr.get("could_arrive", 0) > 0)
        reach["episodes_with_free_or_reserve_unit_able_to_arrive"] += int(rr.get("could_arrive_free_or_reserve", 0) > 0)
        reach["episodes_where_only_holders_of_other_objectives_could_arrive"] += int(
            rr.get("could_arrive", 0) > 0 and rr.get("could_arrive", 0) == rr.get("could_arrive_while_holding_another", 0))
    out["reserve_reach"] = dict(reach)
    # outnumbering at the loss: enemy in zone at b1 versus own in zone at b150 (the garrison it met)
    cmp_ = collections.Counter()
    for e in eps:
        own150 = e["truth_b150"]["own"]
        en1 = e["truth_b1"]["enemy"]
        cmp_["enemy_b1_gt_own_b150" if en1 > own150 else "enemy_b1_le_own_b150"] += 1
    out["enemy_at_loss_vs_garrison_150_before"] = dict(cmp_)
    # predictor table on the held-objective decision states
    samples = [s for g in games for s in g["held_samples"]]
    table = {}
    for name, test in (
            ("seen_r8_ge_1", lambda s: s["seen_r8"] >= 1),
            ("seen_r8_gt_own_in_zone", lambda s: s["seen_r8"] > s["own_in_zone"]),
            ("seen_r8_ge_2_and_gt_own", lambda s: s["seen_r8"] >= 2 and s["seen_r8"] > s["own_in_zone"]),
            ("seen_r4_ge_1", lambda s: s["seen_r4"] >= 1),
            ("own_in_zone_le_1", lambda s: s["own_in_zone"] <= 1),
            ("own_in_zone_0", lambda s: s["own_in_zone"] == 0)):
        tp = sum(1 for s in samples if test(s) and s["lost_within_horizon"])
        fp = sum(1 for s in samples if test(s) and not s["lost_within_horizon"])
        fn = sum(1 for s in samples if not test(s) and s["lost_within_horizon"])
        tn = sum(1 for s in samples if not test(s) and not s["lost_within_horizon"])
        table[name] = {"flag_and_lost": tp, "flag_not_lost": fp, "no_flag_lost": fn, "no_flag_not_lost": tn}
    out["held_state_samples"] = len(samples)
    out["held_state_samples_lost_within_horizon"] = sum(1 for s in samples if s["lost_within_horizon"])
    out["predictor_tables"] = table
    out["note"] = ("post hoc and descriptive (Sprint 35); truth = all-seeing compact timeline, seen = the candidate "
                   "seat's own observation; reserve reach uses free-flow time, a lower bound on arrival")
    return out


def main() -> int:
    from miaosuan_agent.evaluation import s34_live as sl
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / sl.CARD_ID)
    parser.add_argument("--data", type=Path, default=REPO_ROOT / "local" / "s34-data" / "Data")
    parser.add_argument("--private", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "s35" / "loss-episodes-private.json")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "evaluation" / "s35-coalition-agent" / "loss-episodes.json")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    cards = _cards()
    card = json.loads(cards.CARD.read_text(encoding="utf-8"))
    maps = {s["scenario_id"]: s["map_id"] for s in card["scenarios"]}
    games = [g for g in sl.schedule(cards.CANDIDATE_ID) if g["stage"] == "A"]
    jobs = [(str(args.work), g, str(args.data), maps[g["scenario_id"]]) for g in games]
    with mp.Pool(args.workers) as pool:
        results = sorted(pool.map(one, jobs), key=lambda r: r["position"])
    args.private.parent.mkdir(parents=True, exist_ok=True)
    args.private.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    payload = {"schema": "miaosuan-s35-loss-episodes/1", "aggregate": aggregate(results),
               "by_scenario_side": {}}
    for sid in sorted({g["scenario_id"] for g in results}):
        for side in ("red", "blue"):
            sub = [g for g in results if g["scenario_id"] == sid and g["side"] == side]
            if sub:
                payload["by_scenario_side"][f"{sid} {side}"] = {
                    "episodes": sum(len(g["episodes"]) for g in sub),
                    "kinds": aggregate(sub)["episode_kind"]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(payload["aggregate"], indent=1)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
