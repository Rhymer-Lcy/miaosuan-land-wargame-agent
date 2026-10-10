"""Sprint 34 read-only fact probe over genuine full-step timelines (private output, aggregates printed).

Reads timeline pickles (rd.Capture windows: samples[k]['seats'][seat]['observation'] pickled raw seat view).
Counts listing conditions for occupy (5), get on (3), get off (4), shoot (2) while moving, change state (6),
and describes jm_points / passengers / enemy field masking. No engine, no writes except stdout.
"""
import collections
import json
import pickle
import sys

GROUND = (1, 2)


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def hexd(a, b):
    (r1, c1), (r2, c2) = divmod(a, 100), divmod(b, 100)
    q1, q2 = c1 - (r1 - (r1 & 1)) // 2, c2 - (r2 - (r2 & 1)) // 2
    return (abs(q1 - q2) + abs(r1 - r2) + abs((-q1 - r1) - (-q2 - r2))) // 2


def state_label(u):
    path = bool(u.get("move_path"))
    spd = num(u.get("speed")) or 0
    mts = num(u.get("move_to_stop_remain_time")) or 0
    stop = u.get("stop")
    if path:
        return "moving" if spd > 0 else "waiting"
    if mts > 0:
        return "transition"
    return f"settled_stop{stop}"


def probe(path, out):
    windows = pickle.load(open(path, "rb"))
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    occ = out["occupy"]
    for s in samples:
        for seat_key, snap in s["seats"].items():
            raw = pickle.loads(snap["observation"])
            if (raw.get("time") or {}).get("stage") != 2:
                continue
            ops = raw.get("operators") or []
            seat = int(seat_key)
            rg = raw.get("role_and_grouping_info") or {}
            faction = (rg.get(seat) or rg.get(str(seat)) or {}).get("faction")
            va = raw.get("valid_actions") or {}
            own = [u for u in ops if u.get("color") == faction]
            enemy = [u for u in ops if u.get("color") != faction]
            out["seat_decisions"] += 1
            out["enemy_visible_decisions"] += bool(enemy)
            for e in enemy:
                out["enemy_fields"][tuple(sorted(k for k, v in e.items() if v not in (None, [], {}, 0)))[:0] or "n"] += 0
                for k in ("move_path", "speed", "cur_pos", "blood", "see_enemy_bop_ids", "passenger_ids", "launcher",
                          "carry_weapon_ids", "weapon_cool_time", "stop", "move_to_stop_remain_time"):
                    v = e.get(k)
                    out["enemy_field_nonempty"][k] += v not in (None, [], {}, 0, "")
                out["enemy_units"] += 1
            jm = raw.get("jm_points") or []
            out["jm_nonempty_decisions"] += bool(jm)
            for p in jm[:3]:
                out["jm_keys"][tuple(sorted(p.keys()))] += 1
                owner = next((u for u in ops if u.get("obj_id") == p.get("obj_id")), None)
                out["jm_owner"]["own" if owner and owner.get("color") == faction else "enemy" if owner else "absent"] += 1
            cities = {c["coord"]: c for c in raw.get("cities") or []}
            enemy_ground_hexes = [e.get("cur_hex") for e in enemy if e.get("type") in GROUND]
            passengers = raw.get("passengers") or []
            out["passenger_records"] += len(passengers)
            for u in own:
                acts = va.get(u["obj_id"]) or va.get(str(u["obj_id"])) or {}
                types = {int(k) for k in acts}
                lab = state_label(u)
                ut, st = u.get("type"), u.get("sub_type")
                if ut in GROUND and u.get("cur_hex") in cities and cities[u["cur_hex"]].get("flag") != faction:
                    near = any(isinstance(h, int) and hexd(h, u["cur_hex"]) <= 1 for h in enemy_ground_hexes)
                    occ[(ut, st, lab, "enemy_adjacent" if near else "clear", 5 in types)] += 1
                if 3 in types:
                    out["get_on"][(ut, st, lab)] += 1
                    for opt in acts.get(3) or acts.get("3") or []:
                        car = next((c for c in own if c.get("obj_id") == opt.get("target_obj_id")), None)
                        if car is not None:
                            out["get_on_carrier"][(car.get("sub_type"), state_label(car),
                                                   "same_hex" if car.get("cur_hex") == u.get("cur_hex") else
                                                   f"d{hexd(car.get('cur_hex'), u.get('cur_hex'))}")] += 1
                        else:
                            out["get_on_carrier"][("carrier_not_in_operators",)] += 1
                if 4 in types:
                    out["get_off"][(ut, st, lab)] += 1
                if 2 in types and lab in ("moving", "waiting"):
                    out["shoot_while_path"][(ut, st, lab)] += 1
                if 2 in types and lab == "transition":
                    out["shoot_in_transition"][(ut, st)] += 1
                if 6 in types:
                    opts = tuple(sorted(o.get("target_state") for o in (acts.get(6) or acts.get("6") or [])))
                    out["change_state"][(ut, st, lab, opts)] += 1
                if 8 in types:
                    out["artillery"][(ut, st, lab)] += 1
                if 1 in types:
                    out["move_listed"][(ut, st, lab)] += 1
                elif ut in GROUND:
                    out["move_not_listed"][(ut, st, lab)] += 1
                if u.get("passenger_ids"):
                    out["carrier_with_passengers"][(st, lab, 4 in types)] += 1


def main():
    out = {"seat_decisions": 0, "enemy_visible_decisions": 0, "enemy_units": 0, "passenger_records": 0,
           "jm_nonempty_decisions": 0}
    for key in ("occupy", "get_on", "get_on_carrier", "get_off", "shoot_while_path", "shoot_in_transition",
                "change_state", "artillery", "move_listed", "move_not_listed", "carrier_with_passengers",
                "enemy_fields", "enemy_field_nonempty", "jm_keys", "jm_owner"):
        out[key] = collections.Counter()
    for path in sys.argv[1:]:
        probe(path, out)
        print("done", path.split("/")[-1], out["seat_decisions"], file=sys.stderr, flush=True)
    for k, v in out.items():
        if isinstance(v, collections.Counter):
            print("##", k)
            for kk, vv in sorted(v.items(), key=lambda kv: str(kv[0])):
                print("  ", kk, vv)
        else:
            print("##", k, v)


if __name__ == "__main__":
    main()
