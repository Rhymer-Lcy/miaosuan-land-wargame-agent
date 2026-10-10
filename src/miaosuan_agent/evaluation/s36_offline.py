"""Sprint 36 offline comparison rules: episode reading, summaries, gates and the selection rule (section 15).

Registered before the comparison runs; the driver is ``scripts/s36_offline.py``. Evidence levels are kept apart in
every summary: ``model`` (engine-free MODEL WORLD, no combat: legality, determinism, latency, traffic, the movement
race), ``genuine`` (decision-level on genuine engine observations), ``episodes`` (historical descriptive: what each agent
would decide at recorded states before recorded losses; open loop, never an outcome).

Gates, each required of a candidate (``TA``, ``TB``, ``TC``):

* G1 legality: no action rejected by the agent's validator or found illegal by the independent check (genuine), no
  rejection and no model refusal (model);
* G2 no fallback and no contract error (genuine and model);
* G3 every model replay check identical; no model game crashed;
* G4 traffic: no model wait of 300 steps or more in front of a full hex;
* G5 latency: genuine p99 at most 100 ms and maximum at most 1,000 ms; model maximum at most 1,000 ms;
* G6 memory: at most 200,000 bytes of canonical JSON at every genuine decision;
* G7 coverage: against the inert control, in every scenario-side, model objective value at least ``S34-MO``'s (the
  Sprint 35 shortfall in 20 of 80 scenario-sides closed, and no new one);
* G8 movement race: against ``baseline-v2``, model objective value at least 95% of ``S34-MO``'s (no collapse; a floor,
  never a ranking: the model has no combat, so withdrawal can only cost here);
* G9 every population played (the expected numbers of model games, genuine games and episode games);
* G10 equivalence (a property of the code, required of every candidate): ``ta-as-ca`` decides as Sprint 35's ``CA``
  and ``tc-no-guard`` as ``S34-MO`` at every genuine play decision;
* G11 control fidelity: each frozen control re-decides its own recorded live games exactly (else the episode reading
  is invalid and nothing is selected);
* G12 a different policy: decisions differ from ``S34-MO``'s in at least 1% of genuine play decisions.

Rule: among the candidates passing every gate, the first in the order ``TC``, ``TA``, ``TB`` is selected: the least
change from the frozen Sprint 34 control first. Reason: the Sprint 34 control did better than the Sprint 35 candidate in
the configurations where Sprint 35 regressed; no offline population can measure a combat outcome; and a live comparison
against a fresh Sprint 34 control attributes a difference most clearly when the candidate differs from it only by named
rules. If none passes: ``S36_ENGINEERING_BLOCKED`` and no live proposal. The episode figures are reported, never
selected on; ablations are reported, never selected.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..integrated import facts as F

V2 = "baseline-v2-candidate-shoot-target-reservation"
INERT = "inert-v0"
AGENTS = ("S34-MO", "CM", "TA", "TB", "TC")
CANDIDATES = ("TC", "TA", "TB")
CONTROLS = ("S34-MO", "CM")
ABLATIONS = ("ta-no-delay-holder", "ta-no-withdrawal", "ta-no-static-filter", "ta-r1-attribution",
             "ta-no-opportunity-capture", "ta-no-coalition-capture", "ta-no-end-window", "ta-no-traffic-repair",
             "tb-no-reserve", "tb-no-artillery", "tb-no-transport", "tb-no-guided-fire", "tb-no-counterattack",
             "tc-no-withdrawal", "tc-no-retention")
EQUIVALENCE = (("CA", "ta-as-ca"), ("S34-MO", "tc-no-guard"))
THREATENED = ("secure", "defend", "delay")
WINDOW = 300
LATENCY_P99_MS, LATENCY_MAX_MS = 100.0, 1000.0
MEMORY_BYTES = 200_000
MODEL_WAIT = 300
MOVEMENT_FLOOR = 0.95
DIFFER_SHARE = 0.01
GROUND = (1, 2)


# ------------------------------------------------------------------------------------------------ episodes
def episodes_from_timeline(steps: Sequence[Mapping[str, Any]], colour: int) -> Dict[str, List[Dict[str, Any]]]:
    """Recorded episodes of the side ``colour`` from the all-seeing compact steps (unit rows: id, colour, type,
    sub_type, hex, path length, speed, blood, value, aboard): held-objective losses (with the last standing
    defenders that left alive) and own ground units destroyed standing in the zone of an objective the side held."""
    losses: List[Dict[str, Any]] = []
    destroyed: List[Dict[str, Any]] = []
    prev: Dict[int, Any] = {}
    for i, s in enumerate(steps):
        for coord, flag, value in s["cities"]:
            if prev.get(coord) == colour and flag != colour:
                zone = F.zone(coord)
                departures = []
                for j in range(i - 1, max(-1, i - 1800), -1):
                    standers = [r for r in steps[j]["units"] if r[1] == colour and r[2] in GROUND and not r[9]
                                and r[4] in zone and r[5] == 0]
                    if not standers:
                        continue
                    nxt = {r[0] for r in steps[j + 1]["units"]}
                    departures = [(r[0], steps[j]["cur_step"]) for r in standers if r[0] in nxt]
                    break
                losses.append({"objective": coord, "value": value, "step": s["cur_step"], "departures": departures})
            prev[coord] = flag
    held: Dict[int, Any] = {}
    for i in range(len(steps) - 1):
        for coord, flag, _ in steps[i]["cities"]:
            held[coord] = flag
        nxt = {r[0] for r in steps[i + 1]["units"]}
        for r in steps[i]["units"]:
            if r[1] != colour or r[2] not in GROUND or r[9] or r[5] != 0 or r[0] in nxt:
                continue
            home = next((c for c, f in held.items() if f == colour and r[4] in F.zone(c)), None)
            if home is not None:
                destroyed.append({"unit": r[0], "sub_type": r[3], "value": r[8], "objective": home,
                                  "step": steps[i + 1]["cur_step"]})
    return {"losses": losses, "destroyed": destroyed}


def episode_counts(episodes: Mapping[str, Sequence[Any]]) -> Dict[str, int]:
    return {"losses": len(episodes["losses"]), "destroyed_in_held_zone": len(episodes["destroyed"]),
            "departures": sum(len(e["departures"]) for e in episodes["losses"])}


def _nearest(per: Mapping[int, Any], step: int) -> Optional[int]:
    best = None
    for s in per:
        if s <= step and (best is None or s > best):
            best = s
    return best


def _moves(actions: Iterable[Mapping[str, Any]]) -> Dict[int, int]:
    return {a["obj_id"]: a["move_path"][-1] for a in actions if a.get("type") == 1 and a.get("move_path")}


def read_episodes(episodes: Mapping[str, Sequence[Mapping[str, Any]]], per: Mapping[int, Mapping[str, Any]],
                  steps: Sequence[Mapping[str, Any]], colour: int, cheap_limit: float) -> Dict[str, Any]:
    """One agent's decisions (``per``: decision step -> {"actions", "stances"}) read at the recorded episodes."""
    by_step = {s["cur_step"]: s for s in steps}
    out = collections.Counter()
    for loss in episodes["losses"]:
        zone = F.zone(loss["objective"])
        t = loss["step"]
        at = _nearest(per, t - 150)
        stance = per[at]["stances"].get(loss["objective"], {}).get("stance") if at is not None else None
        out["losses"] += 1
        out["recognised_150_before"] += stance in THREATENED
        present = False
        for step in range(max(0, t - WINDOW), t):
            d = per.get(step)
            if d is None:
                continue
            keep = d["stances"].get(loss["objective"], {}).get("keep") or []
            moves = _moves(d["actions"])
            row = by_step.get(step)
            standing = [r[0] for r in (row["units"] if row else ()) if r[1] == colour and r[2] in GROUND
                        and not r[9] and r[4] in zone and r[5] == 0]
            if keep or any(end in zone for end in moves.values()) \
                    or any(u not in moves or moves[u] in zone for u in standing):
                present = True
                break
        out["presence_in_last_300"] += present
        for unit, step in loss["departures"]:
            out["departures"] += 1
            d = per.get(step)
            moves = _moves(d["actions"]) if d else {}
            out["departures_kept"] += not (unit in moves and moves[unit] not in zone)
    for unit in episodes["destroyed"]:
        zone = F.zone(unit["objective"])
        valuable = unit["value"] > cheap_limit
        key = "valuable" if valuable else "cheap"
        out[f"destroyed_{key}"] += 1
        ordered_out = False
        for step in range(max(0, unit["step"] - WINDOW), unit["step"]):
            d = per.get(step)
            if d is None:
                continue
            moves = _moves(d["actions"])
            if unit["unit"] in moves and moves[unit["unit"]] not in zone:
                ordered_out = True
                break
        out[f"destroyed_{key}_ordered_out_before"] += ordered_out
    return dict(out)


# ------------------------------------------------------------------------------------------------ summaries
def _seat_of(row: Mapping[str, Any], agent: str) -> Tuple[str, str]:
    c = "0" if row["red"] == agent else "1"
    return c, "red" if c == "0" else "blue"


def summarise_model(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}
    sides: Dict[str, Dict[str, Dict[str, int]]] = collections.defaultdict(dict)
    crashes = [r for r in rows if "crash" in r]
    for r in rows:
        if "crash" in r:
            continue
        agent = r["red"] if r["red"] not in ("inert", "baseline-v2") else r["blue"]
        c, side = _seat_of(r, agent)
        seat = r["seats"][c]
        key = f"{r['population']}|{agent}"
        s = out.setdefault(key, collections.Counter())
        s["games"] += 1
        s["objective_value"] += r["occupy"][f"{side}_occupy"]
        s["objective_value_max"] += r["objective_value_total"]
        s["rejections"] += sum(seat["rejected"].values())
        s["fallbacks"] += seat["fallbacks"]
        s["replay_checks"] += seat["replay_checks"]
        s["replay_mismatches"] += seat["replay_mismatches"]
        s["model_refusals"] += r["model_refusals"]
        s["wait_unit_steps"] += r["wait_unit_steps"][c]
        s["max_wait"] = max(s["max_wait"], r["max_wait"][c])
        s["latency_ms_max_x1000"] = max(s["latency_ms_max_x1000"], int(round(1000 * (seat["latency_ms_max"] or 0))))
        s["first_owned"] += sum(1 for v in r["first_owner"].values() if v and v[0] == int(c))
        if r["population"] == "M-inert":
            sides[f"{r['scenario_id']} {side}"][agent] = r["occupy"][f"{side}_occupy"]
    summary = {k: dict(v) for k, v in sorted(out.items())}
    for v in summary.values():
        v["latency_ms_max"] = v.pop("latency_ms_max_x1000") / 1000.0
    return {"evidence": "engine-free model world, no combat", "crashes": len(crashes),
            "crash_examples": [c["crash"][:200] for c in crashes[:5]], "populations": summary,
            "m_inert_sides": {k: dict(sorted(v.items())) for k, v in sorted(sides.items())}}


def summarise_genuine(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    agents: Dict[str, collections.Counter] = {}
    latency: Dict[str, List[float]] = collections.defaultdict(list)
    equivalence = collections.Counter()
    for g in games:
        for pair, n in g["equivalence_differences"].items():
            equivalence[pair] += n
        for name, r in g["agents"].items():
            s = agents.setdefault(name, collections.Counter())
            for k in ("decisions", "play_decisions", "rejections", "independent_illegal", "fallbacks",
                      "contract_errors", "differing_from_s34", "differing_from_cm"):
                s[k] += r[k]
            s["memory_bytes_max"] = max(s["memory_bytes_max"], r["memory_bytes_max"])
            for k, v in r["actions_by_type"].items():
                s[k] += v
            for k, v in r["stats"].items():
                s[f"stat_{k}"] += v
            latency[name].append(r["latency_ms_p99"])
            s["latency_ms_max_x1000"] = max(s["latency_ms_max_x1000"], int(round(1000 * r["latency_ms_max"])))
    out = {}
    for name, s in sorted(agents.items()):
        d = dict(s)
        d["latency_ms_max"] = d.pop("latency_ms_max_x1000") / 1000.0
        d["latency_ms_p99_max_over_games"] = round(max(latency[name]), 3)
        out[name] = d
    return {"evidence": "decision-level on genuine engine observations", "games": len(games),
            "kinds": dict(collections.Counter(g["kind"].split(":")[0] for g in games)), "agents": out,
            "equivalence_differences": dict(equivalence)}


def summarise_episodes(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, collections.Counter] = {a: collections.Counter() for a in AGENTS}
    by_recorded: Dict[str, Dict[str, collections.Counter]] = collections.defaultdict(
        lambda: {a: collections.Counter() for a in AGENTS})
    fidelity = collections.Counter()
    counts = collections.Counter()
    for g in games:
        fidelity[f"{g['recorded_policy']} decisions"] += g["fidelity"]["decisions"]
        fidelity[f"{g['recorded_policy']} differing"] += g["fidelity"]["differing"]
        for k, v in g["episodes"].items():
            counts[f"{g['recorded_policy']} {k}"] += v
        for a, row in g["rows"].items():
            totals[a].update(row)
            by_recorded[g["recorded_policy"]][a].update(row)
    return {"evidence": "historical descriptive, decision-level, open loop (never an outcome)", "games": len(games),
            "episodes_by_recorded_policy": dict(sorted(counts.items())), "control_fidelity": dict(fidelity),
            "agents": {a: dict(sorted(v.items())) for a, v in totals.items()},
            "by_recorded_policy": {p: {a: dict(sorted(v.items())) for a, v in rows.items()}
                                   for p, rows in sorted(by_recorded.items())}}


# ------------------------------------------------------------------------------------------------ gates
#: Sprint 34's offline corpus (8 replay-corpus games and 16 timelines) plus the 24 Sprint 34 and 19 Sprint 35 live games.
EXPECTED_GENUINE = 8 + 16 + 24 + 19
EXPECTED_EPISODE_GAMES = 16 + 19


def gates(name: str, model: Mapping[str, Any], genuine: Mapping[str, Any], episodes: Mapping[str, Any],
          expected_model: Mapping[str, int]) -> Dict[str, Dict[str, Any]]:
    pops = model["populations"]
    inert, v2 = pops.get(f"M-inert|{name}", {}), pops.get(f"M-v2|{name}", {})
    ref_v2 = pops.get("M-v2|S34-MO", {})
    g = genuine["agents"].get(name, {})
    out: Dict[str, Dict[str, Any]] = {}

    def gate(code: str, ok: bool, detail: Any) -> None:
        out[code] = {"pass": bool(ok), "detail": detail}

    gate("G1", g.get("rejections", 1) == 0 and g.get("independent_illegal", 1) == 0
         and all(p.get("rejections", 1) == 0 and p.get("model_refusals", 1) == 0 for p in (inert, v2)),
         {"genuine_rejections": g.get("rejections"), "genuine_independent_illegal": g.get("independent_illegal"),
          "model_rejections": [inert.get("rejections"), v2.get("rejections")],
          "model_refusals": [inert.get("model_refusals"), v2.get("model_refusals")]})
    gate("G2", g.get("fallbacks", 1) == 0 and g.get("contract_errors", 1) == 0
         and all(p.get("fallbacks", 1) == 0 for p in (inert, v2)),
         {"genuine_fallbacks": g.get("fallbacks"), "genuine_contract_errors": g.get("contract_errors"),
          "model_fallbacks": [inert.get("fallbacks"), v2.get("fallbacks")]})
    gate("G3", model["crashes"] == 0 and all(p.get("replay_mismatches", 1) == 0 and p.get("replay_checks", 0) > 0
                                             for p in (inert, v2)),
         {"crashes": model["crashes"], "replay_checks": [inert.get("replay_checks"), v2.get("replay_checks")],
          "replay_mismatches": [inert.get("replay_mismatches"), v2.get("replay_mismatches")]})
    gate("G4", max(inert.get("max_wait", MODEL_WAIT), v2.get("max_wait", MODEL_WAIT)) < MODEL_WAIT,
         {"max_wait": [inert.get("max_wait"), v2.get("max_wait")]})
    gate("G5", g.get("latency_ms_p99_max_over_games", 1e9) <= LATENCY_P99_MS
         and g.get("latency_ms_max", 1e9) <= LATENCY_MAX_MS
         and max(inert.get("latency_ms_max", 1e9), v2.get("latency_ms_max", 1e9)) <= LATENCY_MAX_MS,
         {"genuine_p99_max_over_games": g.get("latency_ms_p99_max_over_games"), "genuine_max": g.get("latency_ms_max"),
          "model_max": [inert.get("latency_ms_max"), v2.get("latency_ms_max")]})
    gate("G6", g.get("memory_bytes_max", MEMORY_BYTES + 1) <= MEMORY_BYTES, {"memory_bytes_max": g.get("memory_bytes_max")})
    short = [side for side, values in model["m_inert_sides"].items()
             if name not in values or values[name] < values.get("S34-MO", 0)]
    gate("G7", not short, {"scenario_sides_below_s34_mo": short})
    floor = MOVEMENT_FLOOR * ref_v2.get("objective_value", 0)
    gate("G8", v2.get("objective_value", -1) >= floor,
         {"objective_value": v2.get("objective_value"), "s34_mo": ref_v2.get("objective_value"), "floor": floor})
    gate("G9", inert.get("games") == expected_model["M-inert"] and v2.get("games") == expected_model["M-v2"]
         and genuine["games"] == EXPECTED_GENUINE and episodes["games"] == EXPECTED_EPISODE_GAMES,
         {"model": [inert.get("games"), v2.get("games")], "expected_model": dict(expected_model),
          "genuine_games": genuine["games"], "episode_games": episodes["games"]})
    eq = genuine["equivalence_differences"]
    gate("G10", all(v == 0 for v in eq.values()) and len(eq) == 2, dict(eq))
    fid = episodes["control_fidelity"]
    gate("G11", all(fid.get(f"{c} differing", 1) == 0 and fid.get(f"{c} decisions", 0) > 0 for c in CONTROLS), dict(fid))
    differ = g.get("differing_from_s34", 0)
    gate("G12", differ >= DIFFER_SHARE * max(1, g.get("play_decisions", 0)),
         {"differing": differ, "play_decisions": g.get("play_decisions")})
    return out


def select(model: Mapping[str, Any], genuine: Mapping[str, Any], episodes: Mapping[str, Any]) -> Dict[str, Any]:
    pops = model["populations"]
    expected = {"M-inert": pops.get("M-inert|S34-MO", {}).get("games", 0),
                "M-v2": pops.get("M-v2|S34-MO", {}).get("games", 0)}
    results = {name: gates(name, model, genuine, episodes, expected) for name in CANDIDATES}
    passed = [name for name in CANDIDATES if all(v["pass"] for v in results[name].values())]
    selected = passed[0] if passed else None
    return {"rule": "among candidates passing every gate, the first of TC, TA, TB (least change from S34-MO first)",
            "gates": results, "gates_passed": passed, "selected": selected,
            "disposition": "candidate frozen for a live proposal" if selected else "S36_ENGINEERING_BLOCKED"}


__all__ = ["episodes_from_timeline", "read_episodes", "episode_counts", "summarise_model", "summarise_genuine",
           "summarise_episodes", "gates", "select", "AGENTS", "CANDIDATES", "ABLATIONS", "EQUIVALENCE"]
