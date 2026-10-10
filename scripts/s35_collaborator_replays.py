"""Sprint 35 audit of the collaborator comparison replays (private inputs, sanitized aggregate output).

    python scripts/s35_collaborator_replays.py

Reads the three archived replays of scenario 2020331196 (all-seeing GREEN frames 0..2882 written by the SDK offline
runner) and reconstructs, separately per seat, what was emitted, accepted, and observed to take effect. Writes

    local/diagnostics/s35/replay_audit_private.json   full detail (may contain unit ids; never published)
    evaluation/s35-coalition-agent/collaborator-replays.json   aggregates only: no coordinates, unit ids or hexes

Categories kept apart: EMISSION (an echoed action record; the runner echoes every submitted action), ACCEPTANCE (an
echo without an error), EFFECT (a state change or a judge record observed in the frames). Tactical causal value is not
computed here: a single game cannot establish it.
"""

from __future__ import annotations

import collections
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "local" / "references" / "teammate" / "20261010"
OUT = ROOT / "local" / "diagnostics" / "s35"
PUBLIC = ROOT / "evaluation" / "s35-coalition-agent" / "collaborator-replays.json"
REPLAYS = {
    "8567": ("comparison-replays/replay-8567_sc2020331196-t123_collab-blue-vs-owner-red_blue-win-780.zip",
             {"collaborator": "blue", "owner": "red"}, "OWNER_DESIGNATED"),
    "8700": ("comparison-replays/replay-8700_sc2020331196-t123_collab-red-vs-owner-blue_red-win-minus-360.zip",
             {"collaborator": "red", "owner": "blue"}, "OWNER_DESIGNATED"),
    "0047": ("supplementary-replays/replay-0047_sc2020331196-t123_unattributed_red-win-122.zip",
             None, "UNATTRIBUTED"),
}
SEATS = {1: "red", 11: "blue"}
COLOR = {0: "red", 1: "blue"}
SUB = {0: "tank", 1: "ifv", 2: "squad", 3: "artillery", 4: "ugv", 5: "uav", 6: "helicopter", 7: "loitering_munition",
       8: "transport_helicopter", 9: "other9"}
ACT = {1: "move", 2: "shoot", 3: "get_on", 4: "get_off", 5: "occupy", 6: "change_state", 7: "remove_keep",
       8: "indirect_fire_plan", 9: "guided_shoot", 10: "stop", 11: "weapon_lock", 12: "weapon_unfold",
       13: "cancel_indirect_fire", 14: "fork", 15: "union", 16: "change_altitude", 17: "activate_radar",
       18: "enter_fort", 19: "exit_fort", 20: "lay_mine", 204: "chat", 205: "graphic_marker", 303: "deploy_get_on",
       333: "end_deployment"}


def frames(path: Path):
    with zipfile.ZipFile(path) as zf:
        prefix = zf.infolist()[0].filename.split("/")[0]
        n = sum(1 for i in zf.infolist() if i.filename.split("/")[-1].isdigit())
        for k in range(n):
            yield k, json.loads(zf.read(f"{prefix}/{k}"))


def audit(tag: str) -> dict:
    rel, attribution, status = REPLAYS[tag]
    path = REF / rel
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    emitted = collections.Counter()          # (seat, stage, type)
    refused = collections.Counter()          # (seat, type, code)
    refused_msg = {}
    actor_sub = collections.Counter()        # (seat, type, actor sub_type) for unit actions
    markers = collections.Counter()          # seat -> graphic markers
    judge = collections.Counter()            # (attacker color, judge type, attacker sub, target color, target sub, hit)
    damage = collections.Counter()           # same key without hit -> summed damage
    seen_judge = set()
    moves = collections.Counter()            # (color, sub) hex transitions
    embark_eff = collections.Counter()       # (color, passenger sub) operator->passenger transitions in play stage
    disembark_eff = collections.Counter()
    stage1_eff = collections.Counter()       # (color, kind)
    first_owner = {}                         # city index -> (color, step)
    flips = collections.Counter()
    owner_steps = collections.Counter()      # (city index, color) -> steps owned
    city_values = None
    prev_pos = {}
    prev_where = {}                          # obj_id -> "op" | "pass"
    sub_of = {}
    color_of = {}
    initial = collections.Counter()
    first_frame = None
    last = None
    prev_flags = None
    for k, fr in frames(path):
        stage = fr["time"]["stage"]
        step = fr["time"]["cur_step"]
        if first_frame is None:
            first_frame = fr
            for o in fr["operators"] + fr["passengers"]:
                initial[(COLOR[o["color"]], SUB.get(o["sub_type"], o["sub_type"]))] += 1
        for o in fr["operators"] + fr["passengers"]:
            sub_of[o["obj_id"]] = o["sub_type"]
            color_of[o["obj_id"]] = o["color"]
        for rec in fr["actions"]:
            msg = rec.get("message") if "message" in rec else rec
            if not isinstance(msg, dict):
                continue
            seat = SEATS.get(msg.get("actor"), str(msg.get("actor")))
            t = msg.get("type")
            emitted[(seat, stage, ACT.get(t, t))] += 1
            if "obj_id" in msg and msg["obj_id"] in sub_of:
                actor_sub[(seat, ACT.get(t, t), SUB.get(sub_of[msg["obj_id"]]))] += 1
            if t == 205:
                markers[seat] += 1
            if "error" in rec:
                code = rec["error"].get("code")
                refused[(seat, ACT.get(t, t), code)] += 1
                refused_msg[code] = rec["error"].get("message")
        for j in fr["judge_info"]:
            key = json.dumps(j, sort_keys=True)
            if key in seen_judge:
                continue
            seen_judge.add(key)
            att_c = COLOR.get(j.get("attack_color"))
            tgt_c = COLOR.get(j.get("target_color"))
            hit = (j.get("damage") or 0) > 0
            base = (att_c, j.get("type"), SUB.get(j.get("attack_sub_type")), tgt_c, SUB.get(j.get("target_sub_type")))
            judge[base + (hit,)] += 1
            damage[base] += max(j.get("damage") or 0, 0)
        where = {}
        for o in fr["operators"]:
            where[o["obj_id"]] = "op"
            if o["obj_id"] in prev_pos and prev_pos[o["obj_id"]] != o["cur_hex"]:
                moves[(COLOR[o["color"]], SUB.get(o["sub_type"]))] += 1
            prev_pos[o["obj_id"]] = o["cur_hex"]
        for o in fr["passengers"]:
            where[o["obj_id"]] = "pass"
        for oid, w in where.items():
            pw = prev_where.get(oid)
            if pw and pw != w:
                key = (COLOR[color_of[oid]], SUB.get(sub_of[oid]))
                target = stage1_eff if stage == 1 else None
                if pw == "op" and w == "pass":
                    (target if target is not None else embark_eff)[key if target is None else key + ("embark",)] += 1
                elif pw == "pass" and w == "op":
                    (target if target is not None else disembark_eff)[key if target is None else key + ("disembark",)] += 1
        prev_where = where
        cities = fr["cities"]
        if city_values is None:
            city_values = [c["value"] for c in cities]
        flags = [c["flag"] for c in cities]
        if stage == 2:
            for i, f in enumerate(flags):
                if f in (0, 1):
                    owner_steps[(i, COLOR[f])] += 1
                    if i not in first_owner:
                        first_owner[i] = (COLOR[f], step)
                if prev_flags is not None and prev_flags[i] != f:
                    flips[i] += 1
            prev_flags = flags
        last = fr
    alive_end = collections.Counter()
    for o in last["operators"] + last["passengers"]:
        if o.get("blood", 0) > 0:
            alive_end[(COLOR[o["color"]], SUB.get(o["sub_type"]))] += 1
    s = last["scores"]
    fratricide = {f"{a}->{a}": sum(v for (ac, jt, asub, tc, tsub, hit), v in judge.items() if ac == tc == a)
                  for a in ("red", "blue")}

    def tab(counter):
        return [{"key": list(k), "n": v} for k, v in sorted(counter.items(), key=lambda kv: str(kv[0]))]

    return {
        "replay": tag, "sha256": digest, "scenario_id": first_frame["scenario_id"],
        "terrain_id": first_frame["terrain_id"], "frames": k + 1, "final_step": last["time"]["cur_step"],
        "seat_user_names": sorted({r.get("user_name") for r in first_frame["role_and_grouping_info"].values()}),
        "attribution": attribution, "attribution_status": status,
        "graphic_markers_by_seat": dict(markers),
        "initial_units": tab(initial), "alive_at_end": tab(alive_end),
        "emitted": tab(emitted), "refused": tab(refused), "refusal_codes": refused_msg,
        "unit_actions_by_actor_class": tab(actor_sub),
        "judge_records": tab(judge), "judge_damage": tab(damage), "same_colour_judge_records": fratricide,
        "hex_transitions": tab(moves), "embark_effects_play": tab(embark_eff),
        "disembark_effects_play": tab(disembark_eff), "stage1_effects": tab(stage1_eff),
        "objectives": [{"index": i, "value": v, "first_owner": first_owner.get(i, (None, None))[0],
                        "first_owned_step": first_owner.get(i, (None, None))[1], "flips": flips[i],
                        "red_steps_owned": owner_steps[(i, "red")], "blue_steps_owned": owner_steps[(i, "blue")],
                        "final_flag": COLOR.get(last["cities"][i]["flag"])} for i, v in enumerate(city_values)],
        "final_scores": {k2: s[k2] for k2 in ("red_occupy", "red_remain", "red_attack", "red_total", "red_win",
                                              "blue_occupy", "blue_remain", "blue_attack", "blue_total", "blue_win")},
    }


def first_divergence(a: str, b: str) -> dict:
    """First frame at which two replays' GREEN states differ (sizes of serialised frames, then content)."""
    pa, pb = REF / REPLAYS[a][0], REF / REPLAYS[b][0]
    for (ka, fa), (kb, fb) in zip(frames(pa), frames(pb)):
        if json.dumps(fa, sort_keys=True) != json.dumps(fb, sort_keys=True):
            diff_keys = [key for key in fa if json.dumps(fa.get(key), sort_keys=True) != json.dumps(fb.get(key), sort_keys=True)]
            return {"pair": [a, b], "first_differing_frame": ka, "step": fa["time"]["cur_step"], "differing_keys": diff_keys}
    return {"pair": [a, b], "first_differing_frame": None}


JUDGE_TYPE = {"直瞄射击": "direct", "间瞄伤害": "indirect", "引导射击": "guided"}


def public(results: dict) -> dict:
    """Aggregates only: objectives by value rank, judge types in English, no ids, hexes or marker contents."""
    out = {"schema": "miaosuan-s35-collaborator-replays/1",
           "note": "sanitized aggregates of three third-party replays; seat attribution is the owner's designation "
                   "(both seats are named alike in the replays); EMISSION = echoed action, ACCEPTANCE = echo without "
                   "an error, EFFECT = observed state change or judge record", "replays": {}}
    for tag in REPLAYS:
        r = results[tag]
        rank = sorted(range(len(r["objectives"])), key=lambda i: (-r["objectives"][i]["value"], i))
        objectives = []
        for n, i in enumerate(rank):
            o = r["objectives"][i]
            objectives.append({"label": f"objective {n + 1} ({o['value']})", "first_owner": o["first_owner"],
                               "first_owned_step": o["first_owned_step"], "flips": o["flips"],
                               "red_steps_owned": o["red_steps_owned"], "blue_steps_owned": o["blue_steps_owned"],
                               "final_owner": o["final_flag"]})
        judge = [{"key": [x["key"][0], JUDGE_TYPE.get(x["key"][1], "other"), *x["key"][2:]], "n": x["n"]}
                 for x in r["judge_records"]]
        damage = [{"key": [x["key"][0], JUDGE_TYPE.get(x["key"][1], "other"), *x["key"][2:]], "n": x["n"]}
                  for x in r["judge_damage"]]
        out["replays"][tag] = {
            "sha256": r["sha256"], "scenario_id": r["scenario_id"], "terrain_id": r["terrain_id"], "frames": r["frames"],
            "attribution": r["attribution"], "attribution_status": r["attribution_status"],
            "graphic_markers_by_seat": r["graphic_markers_by_seat"], "initial_units": r["initial_units"],
            "alive_at_end": r["alive_at_end"], "emitted": r["emitted"], "refused": r["refused"],
            "refusal_codes": r["refusal_codes"], "unit_actions_by_actor_class": r["unit_actions_by_actor_class"],
            "judge_records": judge, "judge_damage": damage, "same_colour_judge_records": r["same_colour_judge_records"],
            "hex_transitions": r["hex_transitions"], "embark_effects_play": r["embark_effects_play"],
            "disembark_effects_play": r["disembark_effects_play"], "stage1_effects": r["stage1_effects"],
            "objectives": objectives,
            # the attack score is total - occupy - remain; it is not printed (one value would match a pattern of the
            # project's pre-push privacy scan, whose accepted baseline is not changed for a derivable number)
            "final_scores": {k: v for k, v in r["final_scores"].items() if not k.endswith("_attack")}}
    out["divergence"] = results["divergence"]
    return out


def main() -> None:
    global REF, OUT
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--local", type=Path, default=ROOT / "local",
                        help="the ignored private tree holding references/teammate (a worktree passes the main one)")
    args = parser.parse_args()
    REF = args.local / "references" / "teammate" / "20261010"
    OUT = args.local / "diagnostics" / "s35"
    results = {tag: audit(tag) for tag in REPLAYS}
    results["divergence"] = [first_divergence("8700", "0047"), first_divergence("8567", "8700")]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "replay_audit_private.json").write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    PUBLIC.write_text(json.dumps(public(results), indent=1, sort_keys=True, ensure_ascii=False) + "\n",
                      encoding="utf-8", newline="\n")
    print(json.dumps(results["divergence"], ensure_ascii=False))
    for tag in REPLAYS:
        r = results[tag]
        print("==", tag, r["attribution"], "markers", r["graphic_markers_by_seat"], "final", r["final_scores"])


if __name__ == "__main__":
    main()
