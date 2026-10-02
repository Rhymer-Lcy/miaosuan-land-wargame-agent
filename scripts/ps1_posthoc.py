"""PS-1 design study, POST-HOC descriptions; written after every gate of the study was computed, changes no gate.

    PYTHON scripts/ps1_posthoc.py [--work DIR] [--public DIR] [--corpus-root DIR] [--smoke DIR]

``docs/PS1_DESIGN.md`` section 11 reports what this computes, as hypotheses for a live probe:

1. the first departure of the M1b replay of the split game from its capture;
2. M1c (M1b plus waiting at entry, ``evaluation/ps1_model.py``): fidelity on both Sprint 2 games and the certificate
   verdicts under it (sensitivity only; M1c was derived from the departure in item 1);
3. the restart episodes outside both amendment-1 windows, split into traversals and waits;
4. the entry rule on the replay corpus: a unit entering a hex with a path left shows speed 0 exactly when its next hex
   is full at the moment it is processed (ascending index, descending index, end of step compared);
5. every deadlock episode of the replay corpus (merged across trigger flicker) and the change that released it;
6. the Sprint 1 smoke snapshots in which the PS-1B trigger fired.

Inputs are the study's immutable inputs (SHA-256 checked before and after). The public output holds counts, step
indices, scenario ids and seats; no unit id and no hex.
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision.routing import move_mode  # noqa: E402
from miaosuan_agent.evaluation import ps1_model as pm  # noqa: E402

_spec = importlib.util.spec_from_file_location("ps1_study", Path(__file__).with_name("ps1_study.py"))
study = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(study)


def own_rows(obs: Mapping[str, Any], seat: int) -> Dict[int, Mapping[str, Any]]:
    info = obs.get("role_and_grouping_info") or {}
    listed = set((info.get(seat) or info.get(str(seat)) or {}).get("operators") or ())
    return {r["obj_id"]: r for r in obs.get("operators") or [] if r.get("obj_id") in listed
            and r.get("type") in study.GROUND and not r.get("on_board")}


# ----------------------------------------------------------------------------------------------
# 1. the first departure of the M1b replay


def departure(cap: Any, costs: Any, recon: Mapping[str, Any]) -> Dict[str, Any]:
    """Replay the recorded orders under M1b; for each unit whose hex sequence differs, its first differing entry, and the
    contention at the contested hex: the first step after the unit's previous entry with room, free places, contenders."""
    k0 = study.first_play_k(cap)
    orders: Dict[int, List] = collections.defaultdict(list)
    for k, oid, path in recon["private"]["orders"]:
        orders[k].append(("move", oid, tuple(path)))
    for k, oid in recon["private"]["occupations"]:
        orders[k].append(("occupy", oid, ()))
    sim = study.start_simulation(cap, k0, costs, recon, restart=True)
    sim.run(pm.recorded_orders(orders))
    sim_e: Dict[int, List[Tuple[int, int]]] = collections.defaultdict(list)
    obs_e: Dict[int, List[Tuple[int, int]]] = collections.defaultdict(list)
    for e in sim.events:
        if e.kind == "enter":
            sim_e[e.uid].append((e.step, e.detail[0]))
    for k, oid, h in recon["private"]["entries"]:
        if k > k0:
            obs_e[oid].append((k, h))
    rows = []
    for uid in sorted(obs_e):
        o, m = obs_e[uid], sim_e[uid]
        if [h for _, h in o] == [h for _, h in m]:
            continue
        i = next(j for j, (a, b) in enumerate(zip(o, m)) if a != b)
        contested = o[i][1]
        previous_k = o[i - 1][0] if i > 0 else k0
        speed_at_entry = study.observed_speed(cap, previous_k, uid)
        window = [k for k in cap.ks() if previous_k <= k < o[i][0]]
        wait_k = next((k for k in window if study.observed_speed(cap, k, uid) == 0), None)
        room_k = next((k for k in window if wait_k is not None and k > wait_k and
                       sum(1 for hx, _ in study.channel_a(cap.global_state(k), cap.faction).values() if hx == contested) < pm.K),
                      None)
        row = {"observed_entry_k": o[i][0], "model_entry_k": m[i][0], "previous_entry_k": previous_k,
               "speed_zero_at_previous_entry": speed_at_entry == 0, "first_wait_k": wait_k, "room_k": room_k}
        if room_k is not None:
            state = study.channel_a(cap.global_state(room_k), cap.faction)
            row["free_places_at_room"] = pm.K - sum(1 for hx, _ in state.values() if hx == contested)
            row["contenders_at_room"] = sum(1 for hx, p in state.values() if p and p[0] == contested)
        rows.append(row)
    return {"units_whose_sequence_differs": len(rows), "units": sorted(rows, key=lambda r: r["observed_entry_k"])}


# ----------------------------------------------------------------------------------------------
# 3. restart episodes outside both windows


def outside_windows(episodes: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    """Episodes with ``d`` in neither amendment-1 window, split into traversal runs (moving) and waits (re-waits)."""
    rows = [e for e in episodes if not (e["d"] in (0, 1) or abs(e["d"] - (e["tau"] - 1)) <= 1)]
    traversals = [(n, e["tau"]) for e in rows for moving, n, _ in e["runs"] if moving]
    rewaits = [occ for e in rows for i, (moving, _, occ) in enumerate(e["runs"]) if not moving and i > 0]
    return {"episodes": len(rows), "traversals": len(traversals),
            "traversals_of_tau_minus_1": sum(1 for n, tau in traversals if n == tau - 1),
            "traversals_within_1_of_tau_minus_1": sum(1 for n, tau in traversals if abs(n - (tau - 1)) <= 1),
            "rewaits": len(rewaits), "rewaits_beginning_with_the_target_full": sum(1 for o in rewaits if o >= pm.K),
            "rows": [{"tau": e["tau"], "d": e["d"], "runs": [[m, n] for m, n, _ in e["runs"]]} for e in rows]}


# ----------------------------------------------------------------------------------------------
# 4. the entry rule


def entry_rule(sequence: Sequence[Tuple[int, Mapping[str, Any]]], seat: int) -> collections.Counter:
    """For every unit that enters a hex with a path left: does its speed-0 state match its next hex being full at the
    moment it is processed? Occupancy at that moment under three orders; transitions with a step gap or a changed unit
    set are skipped."""
    table: collections.Counter = collections.Counter()

    def processing(prev, cur, order):
        occ = collections.Counter(r["cur_hex"] for r in prev.values())
        seen = {}
        for uid in order:
            if cur[uid]["cur_hex"] != prev[uid]["cur_hex"]:
                occ[prev[uid]["cur_hex"]] -= 1
                occ[cur[uid]["cur_hex"]] += 1
            seen[uid] = dict(occ)
        return seen

    prev, prev_step = None, None
    for step, obs in sequence:
        cur = own_rows(obs, seat)
        if prev is not None and step == prev_step + 1 and set(cur) == set(prev):
            asc = processing(prev, cur, sorted(cur))
            desc = processing(prev, cur, sorted(cur, reverse=True))
            end = collections.Counter(r["cur_hex"] for r in cur.values())
            for uid, r in cur.items():
                if r["cur_hex"] == prev[uid]["cur_hex"] or not r.get("move_path"):
                    continue
                nh = r["move_path"][0]
                waited = (r.get("speed") or 0) == 0
                table["entries"] += 1
                table["waited at once" if waited else "started"] += 1
                for name, occ in (("ascending", asc[uid]), ("descending", desc[uid]), ("end of step", end)):
                    agree = (occ.get(nh, 0) >= pm.K) == waited
                    table[f"{name} agrees" if agree else f"{name} disagrees"] += 1
                    if name == "ascending" and not agree:
                        table["ascending disagreements with the keep flag set" if r.get("keep") else
                              "ascending disagreements without the keep flag"] += 1
                        table["ascending disagreements with the next hex full" if asc[uid].get(nh, 0) >= pm.K else
                              "ascending disagreements with the next hex not full"] += 1
        elif prev is not None:
            table["skipped transitions"] += 1
        prev, prev_step = cur, step
    return table


# ----------------------------------------------------------------------------------------------
# 5. deadlock episodes


def deadlock_episodes(sequence: Sequence[Tuple[int, Mapping[str, Any]]], seat: int,
                      edges: Mapping[int, pm.Edges]) -> List[Dict[str, Any]]:
    """Maximal runs of steps with a non-empty deadlocked set (so a trigger that lapses inside one run does not split it),
    with the PS-1B trigger steps inside, and the visible changes at the first step without a deadlock."""
    last: Dict[int, int] = {}
    prev_hex: Dict[int, int] = {}
    prev_dest: Dict[int, Any] = {}
    episodes: List[Dict[str, Any]] = []
    cur = None
    previous_rows: Dict[int, Mapping[str, Any]] = {}
    for step, obs in sequence:
        rows = own_rows(obs, seat)
        units = []
        for oid, r in rows.items():
            path = tuple(r.get("move_path") or ())
            if prev_hex.get(oid) != r["cur_hex"] or (path and prev_dest.get(oid) != path[-1]):
                last[oid] = step
            prev_hex[oid] = r["cur_hex"]
            prev_dest[oid] = path[-1] if path else None
            mode = move_mode(r["type"], r.get("move_state"))
            if mode is None:
                continue
            units.append(pm.Unit(oid, r["cur_hex"], float(r["basic_speed"]), int(mode), path, last_progress=last.get(oid, step)))
        dead = pm.deadlocked(units)
        if dead:
            by = {u.uid: u for u in units}
            holders = {v for d in dead for v in pm.wait_for(units)[d] if not by[v].moving}
            cities = {int(c["coord"]) for c in obs.get("cities") or ()}
            if cur is None:
                cur = {"start": step, "members": set(), "holders": set(), "cycle": False, "trigger_steps": 0,
                       "first_trigger": None, "max_units": 0, "holders_on_objective": False}
            cur["end"] = step
            cur["members"] |= set(dead)
            cur["holders"] |= holders
            cur["max_units"] = max(cur["max_units"], len(dead))
            cur["cycle"] = cur["cycle"] or bool(pm.cycles(units))
            cur["holders_on_objective"] = cur["holders_on_objective"] or any(by[h].hex in cities for h in holders)
            if all(pm.stalled(by[d], step, edges) for d in dead):
                cur["trigger_steps"] += 1
                if cur["first_trigger"] is None:
                    cur["first_trigger"] = step
        elif cur is not None:
            every = {r["obj_id"]: r for r in obs.get("operators") or []}
            reasons = set()
            for uid in cur["members"] | cur["holders"]:
                if uid in previous_rows and uid not in rows:
                    r = every.get(uid)
                    reasons.add("removed from the observation" if r is None else "boarded" if r.get("on_board")
                                else "left the seat's list")
            for uid in cur["holders"]:
                if uid in rows and uid in previous_rows:
                    if not previous_rows[uid].get("move_path") and rows[uid].get("move_path"):
                        reasons.add("a holder received an order")
                    if rows[uid]["cur_hex"] != previous_rows[uid]["cur_hex"]:
                        reasons.add("a holder left its hex")
            for uid in cur["members"]:
                if uid in rows and uid in previous_rows:
                    if rows[uid]["cur_hex"] != previous_rows[uid]["cur_hex"]:
                        reasons.add("a deadlocked unit entered its next hex")
                    before = tuple(previous_rows[uid].get("move_path") or ())
                    if tuple(rows[uid].get("move_path") or ()) not in (before, before[1:]):
                        reasons.add("a deadlocked unit's path changed")
            cur["released_by"] = sorted(reasons) or ["no visible change"]
            episodes.append(cur)
            cur = None
        previous_rows = rows
    if cur is not None:
        cur["released_by"] = ["lasted to the end of the game"]
        episodes.append(cur)
    return [{"start": e["start"], "end": e["end"], "steps": e["end"] - e["start"] + 1, "max_units": e["max_units"],
             "kind": "cycle" if e["cycle"] else "chain", "holders_on_objective": e["holders_on_objective"],
             "trigger_steps": e["trigger_steps"],
             "trigger_latency": None if e["first_trigger"] is None else e["first_trigger"] - e["start"],
             "released_by": e["released_by"]} for e in episodes]


# ----------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--public", type=Path, default=REPO_ROOT / "evaluation" / "ps1-design-1")
    parser.add_argument("--corpus-root", type=Path, default=REPO_ROOT / "local" / "replay-corpus")
    parser.add_argument("--smoke", type=Path, default=REPO_ROOT / "local" / "evaluation" / f"{study.SCREEN}-smoke")
    args = parser.parse_args()
    manifest = study.load(REPO_ROOT / "evaluation" / study.SCREEN / "manifest.json")
    before = study.inputs_digest(args.work)
    costs, _ = study.load_costs(args.work, manifest, study.SCENARIO)
    edges = {int(m): costs.edges[m] for m in range(len(costs.edges))}
    caps = {g: study.Capture.read(args.work, g) for g in (study.BASELINE_GAME, study.CANDIDATE_GAME)}
    recon = {g: study.reconstruct(c, costs) for g, c in caps.items()}
    out: Dict[str, Any] = {"schema": "miaosuan-ps1-posthoc/1", "status": "POST HOC (changes no gate)"}

    out["m1b_departure"] = departure(caps[study.CANDIDATE_GAME], costs, recon[study.CANDIDATE_GAME])

    m1c: Dict[str, Any] = {"fidelity": {}, "certificates": {}}
    for g, cap in caps.items():
        f = study.fidelity(cap, costs, recon[g], restart=True, entry_wait=True)
        m1c["fidelity"][g] = {"F1_pass": f["F1_pass"], "F2_pass": f["F2_pass"],
                              "F1": {k: v for k, v in f["F1"].items() if k != "private"},
                              "F2": {k: v for k, v in f["F2"].items() if k != "private"}}
    cand, rc = caps[study.CANDIDATE_GAME], recon[study.CANDIDATE_GAME]
    k_detect, k_play = rc["first_detection_k"], study.first_play_k(cand)
    k_flip = next(k for k in cand.ks() if study.objectives_at(cand, k) != study.objectives_at(cand, k_play))
    for label, k, factory in (("A1", k_play, "ps1a"), ("A4", k_flip, "retarget"), ("A2", k_detect, "ps1b-back-off"),
                              ("A3", k_detect, "ps1b-bypass"), ("A5a", k_detect + 300, "ps1b-back-off"),
                              ("A5b", k_detect + 900, "ps1b-back-off")):
        c = study.certificate(label, "post hoc sensitivity under M1c", cand, costs, rc, k, factory, ["M1c"], [], entry_wait=True)
        m1c["certificates"][label] = {key: c["public"][key] for key in
                                      ("verdict", "cycle_broken_at_k", "deadlocked_at_end", "cycles_at_end", "capacity_violations",
                                       "commands", "flag_steps", "occupy_points_at_end")}
    out["m1c"] = m1c

    sprint2_eps: List[Dict[str, Any]] = []
    for cap in caps.values():
        sprint2_eps += study.restart_episodes([(k, cap.observation(k)) for k in cap.ks()], cap.seat, cap.faction, edges, trace=True)
    corpus_eps: List[Dict[str, Any]] = []
    entry = collections.Counter()
    episodes: List[Dict[str, Any]] = []
    corpus_costs: Dict[str, Any] = {}
    for game, seqs, factions in study.corpus_games(args.corpus_root):
        sid = game.split(".")[0]
        if sid not in corpus_costs:
            corpus_costs[sid] = study.load_costs(REPO_ROOT / "local" / "evaluation" / study.SCREEN, manifest, sid)[0]
        ce = {int(m): corpus_costs[sid].edges[m] for m in range(len(corpus_costs[sid].edges))}
        for seat, seq in sorted(seqs.items()):
            pairs = [(s, o) for s, o, _ in seq]
            corpus_eps += study.restart_episodes(pairs, seat, factions[seat], ce, trace=True)
            entry.update(entry_rule(pairs, seat))
            for e in deadlock_episodes(pairs, seat, ce):
                episodes.append({"game": game, "seat": seat, **e})
    out["restart_outside_windows"] = {"sprint2 games": outside_windows(sprint2_eps), "replay corpus": outside_windows(corpus_eps)}
    out["entry_rule_replay_corpus"] = dict(sorted(entry.items()))
    fired = [e for e in episodes if e["trigger_steps"]]
    out["corpus_deadlock_episodes"] = {
        "episodes": len(episodes), "deadlock_steps": sum(e["steps"] for e in episodes),
        "trigger_steps": sum(e["trigger_steps"] for e in episodes), "episodes_where_the_trigger_fired": len(fired),
        "by_kind_and_release": dict(sorted(collections.Counter(
            f"{e['kind']}, {'fired' if e['trigger_steps'] else 'never fired'}, {'; '.join(e['released_by'])}"
            for e in episodes).items())),
        "rows": episodes}

    smoke: Dict[str, Any] = {}
    for rec_path in sorted((args.smoke / "games").glob("*.json")):
        cap = study.Capture.read(args.smoke, rec_path.stem)
        sid = rec_path.stem.split(".")[0]
        if sid not in corpus_costs:
            corpus_costs[sid] = study.load_costs(REPO_ROOT / "local" / "evaluation" / study.SCREEN, manifest, sid)[0]
        ce = {int(m): corpus_costs[sid].edges[m] for m in range(len(corpus_costs[sid].edges))}
        seq = [(k, cap.observation(k), cap.own_actions(k)) for k in cap.ks() if cap.observation(k)["time"]["stage"] == 2]
        res = study.census_sequence(seq, cap.seat, cap.faction, ce)
        firings = res["private"]["firings"]
        smoke[rec_path.stem] = {"snapshots": len(seq), "trigger_snapshots": res["counts"].get("ps1b_trigger_steps", 0),
                                "max_deadlocked_units": max((f["deadlocked"] for f in firings), default=0),
                                "cycle_present": any(f["cycles"] for f in firings)}
    out["smoke_trigger_snapshots"] = smoke

    if study.inputs_digest(args.work) != before:
        raise SystemExit("REFUSED: an input file changed during the post-hoc run")
    text = json.dumps(out, indent=1, sort_keys=True, default=list) + "\n"
    for forbidden in ("obj_id", "cur_hex"):
        if forbidden in text:
            raise SystemExit(f"REFUSED: the public post-hoc output contains {forbidden}")
    args.public.mkdir(parents=True, exist_ok=True)
    (args.public / "posthoc.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.public / 'posthoc.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
