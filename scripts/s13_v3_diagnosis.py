"""Sprint 13 offline diagnosis of the T9-v3 primary-scenario failure (``docs/SPRINT13_V3_DIAGNOSIS.md``), server only.

    python scripts/s13_v3_diagnosis.py freeze [--check]     # evaluation/s13-v3-diagnosis/inputs.json
    python scripts/s13_v3_diagnosis.py run [--check]        # the public result files and the private rows

``freeze`` pins, by SHA-256, every private input the diagnosis reads: the four Sprint 12 P1 records with their five
capture files each, the scenario's setup cost data, and the 30 Sprint 9 phase-A primary T9-v1 records with their
``T9Capture`` and exploratory capture files. It also recomputes the four frozen policy identities from the checkout and
refuses to write if any differs from the frozen value. ``run`` first requires every pinned digest to hold, then
reconstructs every decision of the v3 seat (section 3 of the protocol; any disagreement stops the run), and writes the
public files of ``evaluation/s13-v3-diagnosis/`` and the private rows under ``local/diagnostics/s13/``. ``--check``
regenerates everything in memory and compares the public files byte for byte. No engine is opened; the ledger is
not read by ``run``.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import os
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(os.environ.get("MIAOSUAN_REPO", Path(__file__).resolve().parents[1])).resolve()
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Origin  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s13_diagnosis as sd  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

SCHEMA_INPUTS = "miaosuan-s13-inputs/1"
SCHEMA = "miaosuan-s13-diagnosis/1"
OUT_DIR = REPO_ROOT / "evaluation" / "s13-v3-diagnosis"
INPUTS = OUT_DIR / "inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s13"
S12_CARD = "s12-v3-primary-1"
S12_CAPTURES = ("t9.json", "v3.json", "v3series.json.gz", "timeline.json", "timeline.pkl")
S9_STUDY = "t9-confirmation-1"
S9_CAPTURES = ("t9.json", "explore.json")
SCENARIO = "2130511121"
PUBLIC_FILES = ("reconstruction", "redistribution", "reservations", "features", "oracles", "sequence", "disposition")
NOTE = ("offline diagnosis on recorded states: T9-v1, T9-v2 and the oracles are off-policy action counterfactuals, "
        "never engine outcomes; Sprint 9 games are other stochastic games; nothing is promoted")

#: The frozen policy-source identities (docs/SPRINT13_V3_DIAGNOSIS.md, section 1).
FROZEN = {
    "baseline-v2": "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae",
    "t9-v1": "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa",
    "t9-v2": "66a451d513d7ff5df2292238dbc4dd526d6b39c050991a25043546a0bce2bece",
    "t9-v3": "9b2003a78ace45c968e2340f06e6fe5aa1938667ab1610c448725a319a48b2b8",
}
ADDON_MODULES = {"baseline-v2": (), "t9-v1": ("experiments/exploratory_addon.py", "experiments/t9_allocation.py"),
                 "t9-v2": ("experiments/exploratory_addon.py", "experiments/t9_staging.py"),
                 "t9-v3": ("experiments/exploratory_addon.py", "experiments/t9_batch.py")}
POLICIES = ("baseline-v2", "t9-v1", "t9-v2", "t9-v3", "O1", "O2", "O3")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def policy_digests() -> Dict[str, str]:
    """Each policy's source digest recomputed from the checkout (the exploratory run cards' construction)."""
    base = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
    return {name: digest_of_files(policy_source_files(sources=base + extra)) for name, extra in ADDON_MODULES.items()}


def tree_digest(root: Path) -> Dict[str, Any]:
    """One digest over every file under ``root`` (sorted relative path and file digest); names are not published."""
    rows = sorted((p.relative_to(root).as_posix(), sha256(p)) for p in root.rglob("*") if p.is_file())
    digest = hashlib.sha256("".join(f"{name}\0{value}\n" for name, value in rows).encode("utf-8")).hexdigest()
    return {"files": len(rows), "sha256": digest}


def s12_card(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    return json.loads((repo / "evaluation" / S12_CARD / "manifest.json").read_text(encoding="utf-8"))


def s12_games(repo: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    return [dict(g) for g in s12_card(repo)["games"]]


def s9_games(repo: Path = REPO_ROOT) -> List[Dict[str, Any]]:
    phase = json.loads((repo / "evaluation" / S9_STUDY / "phase-A.json").read_text(encoding="utf-8"))
    return [{"game_id": g["game_id"], "cell": g["cell"], "session": g["session"]} for g in phase["games"]
            if g["scenario_id"] == SCENARIO and g["cell"] in ("H1", "H2")]


def build_inputs(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    digests = policy_digests()
    wrong = {k: v for k, v in digests.items() if v != FROZEN[k]}
    if wrong:
        raise SystemExit(f"refused: policy identities differ from the frozen values: {sorted(wrong)}")
    ev = repo / "local" / "evaluation"
    s12 = []
    for game in s12_games(repo):
        gid = game["game_id"]
        record = ev / S12_CARD / "games" / f"{gid}.json"
        session = json.loads(record.read_text(encoding="utf-8")).get("session")
        s12.append({"game_id": gid, "screen_position": game["screen_position"], "session": session,
                    "record_sha256": sha256(record),
                    "captures": {suffix: sha256(ev / S12_CARD / "capture" / f"{gid}.{suffix}") for suffix in S12_CAPTURES}})
    s9 = []
    for game in s9_games(repo):
        gid = game["game_id"]
        s9.append({**game, "record_sha256": sha256(ev / S9_STUDY / "games" / f"{gid}.json"),
                   "captures": {suffix: sha256(ev / S9_STUDY / "capture" / f"{gid}.{suffix}") for suffix in S9_CAPTURES}})
    if len(s12) != 4 or len(s9) != 30:
        raise SystemExit(f"refused: expected 4 Sprint 12 and 30 Sprint 9 games, found {len(s12)} and {len(s9)}")
    return {"schema": SCHEMA_INPUTS, "policies": dict(sorted(digests.items())),
            "s12": {"card": S12_CARD, "card_manifest_sha256": sha256(repo / "evaluation" / S12_CARD / "manifest.json"),
                    "report_sha256": sha256(repo / "evaluation" / S12_CARD / "report.json"),
                    "cost_data": tree_digest(ev / S12_CARD / "data" / SCENARIO), "games": s12},
            "s9": {"study": S9_STUDY, "phase_file_sha256": sha256(repo / "evaluation" / S9_STUDY / "phase-A.json"),
                   "games": s9},
            "note": "private inputs pinned before the Sprint 13 analysis; files stay under the ignored local/ tree"}


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


def require_inputs(repo: Path = REPO_ROOT) -> Mapping[str, Any]:
    """The committed inputs file, after verifying that every pinned input still has its digest."""
    committed = INPUTS.read_text(encoding="utf-8")
    if dump(build_inputs(repo)) != committed:
        raise SystemExit("refused: a private input or a policy identity differs from evaluation/s13-v3-diagnosis/inputs.json")
    return json.loads(committed)


def costs_for(repo: Path = REPO_ROOT) -> MoveCosts:
    the_card = s12_card(repo)
    map_id = next(s["map_id"] for s in the_card["scenarios"] if s["scenario_id"] == SCENARIO)
    inputs = sdk_data.load_inputs(repo / "local" / "evaluation" / S12_CARD / "data" / SCENARIO / "Data", SCENARIO, map_id)
    return MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


# ------------------------------------------------------------------------------------------------
# One Sprint 12 game


def flag_state(flag: Any, faction: int) -> str:
    return "own" if flag == faction else "enemy" if flag == 1 - faction else "neutral"


def analyze_game(entry: Mapping[str, Any], costs: MoveCosts, repo: Path = REPO_ROOT) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """(public facts, private rows) of one Sprint 12 game."""
    ev = repo / "local" / "evaluation" / S12_CARD
    gid = entry["game_id"]
    record = json.loads((ev / "games" / f"{gid}.json").read_text(encoding="utf-8"))
    t9cap = json.loads((ev / "capture" / f"{gid}.t9.json").read_text(encoding="utf-8"))
    v3cap = json.loads((ev / "capture" / f"{gid}.v3.json").read_text(encoding="utf-8"))
    timeline = json.loads((ev / "capture" / f"{gid}.timeline.json").read_text(encoding="utf-8"))
    with (ev / "capture" / f"{gid}.timeline.pkl").open("rb") as handle:
        windows = pickle.load(handle)
    facts = tl.analyze(entry, S12_CARD, record, t9cap, v3cap, timeline, windows, costs)
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == "t9-batch-capacity-v3")
    faction = next(s["faction"] for s in record["seats"] if s["policy"] == "t9-batch-capacity-v3")
    cell = entry["condition"]
    states, raws = tl.load_states(windows, seat, faction)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    memories = [pickle.loads((s["seats"].get(seat) or s["seats"].get(str(seat)))["memory"]) for s in samples]
    del windows, samples
    steps = timeline["steps"]
    values = {c["coord"]: c.get("value") for c in (raws[0].get("cities") or ())}
    names = tl.labels(values)
    n = len(steps)

    # labels from the timeline (analysis only)
    lost_at: Dict[int, int] = {}
    seen: set = set()
    for j, state in enumerate(states):
        for u in seen - state.present:
            lost_at.setdefault(u, j)
        seen |= state.present
    stood_cache: Dict[Tuple[int, Any, int], Optional[int]] = {}

    def stood(u: int, coord: Any, start: int) -> Optional[int]:
        key = (u, coord, start)
        if key not in stood_cache:
            stood_cache[key] = tl.stood_on(states, u, coord, start)
        return stood_cache[key]

    def fate(u: int, coord: Any, start: int) -> Tuple[str, Optional[int]]:
        return sd.holder_fate(u, coord, start, stood, lost_at)

    router = ShootReservationPolicy(costs).router
    problems: List[str] = []
    orders: List[Dict[str, Any]] = []
    counted: List[Dict[int, Dict[int, Optional[int]]]] = []
    selections: Dict[Tuple[int, Any], List[int]] = collections.defaultdict(list)
    held_selectable = 0
    b_rows: List[Dict[str, Any]] = []
    slot_diffs = {name: {"vs_t9-v1": 0, "vs_t9-v3": 0} for name in POLICIES}
    action_diffs = {name: {"vs_t9-v1": set(), "vs_t9-v3": set()} for name in POLICIES}
    action_diff_decisions = {name: {"vs_t9-v1": 0, "vs_t9-v3": 0} for name in POLICIES}
    redirect_infeasible = {"O2": 0, "O3": 0}
    unrelated = {"actions_compared": 0, "differences": 0}
    first = {"any_action": None, "redistribution": None}
    active = 0
    for k in range(n):
        row = (steps[k].get("s12") or {}).get(str(seat))
        submitted = [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]

        def doomed(rows: Mapping[int, Mapping[str, Any]], k=k) -> frozenset:
            out = set()
            for coord, info in rows.items():
                for u in info["mover_bounds"]:
                    if fate(u, coord, k + 1)[0] == "DESTROYED":
                        out.add(u)
            return frozenset(out)

        decided = sd.decide_policies(raws[k], seat, faction, memories[k], costs, doomed)
        found = sd.verify(decided, row, submitted)
        if found:
            problems.extend(f"decision {k}: {p}" for p in found)
            continue
        observation = decided["observation"]
        if decided["play"]:
            rows_k, _ = sd.counted_incumbents(observation, faction, router)
            counted.append({coord: dict(info["mover_bounds"]) for coord, info in rows_k.items() if info["mover_bounds"]})
        else:
            counted.append({})
        if rd.plain(decided["t9-v1"]) != rd.plain(decided["t9-v3"]) and first["any_action"] is None:
            first["any_action"] = k
        if not decided["active"]:
            continue
        active += 1
        allocation = decided["allocation"]
        captured = row["allocation"]
        for coord_text, info in captured["objectives"].items():
            mine = counted[k].get(int(coord_text), {})
            if {str(u): b for u, b in sorted(mine.items())} != info["mover_bounds"]:
                problems.append(f"decision {k}: counted movers differ from the captured allocation")
        for u, coord in allocation.selected.items():
            selections[(u, coord)].append(k)
        cur_step = observation.time().cur_step
        unit_kinds = {u.obj_id: u.unit_type for u in observation.operators()}
        for order in sd.unit_forms(decided, faction):
            order.update(k=k, cur_step=cur_step, interval=sd.interval(k),
                         kind=sd.KIND.get(unit_kinds.get(order["unit"]), "other"))
            orders.append(order)
            if order["v1"] == sd.REDIRECT and first["redistribution"] is None:
                first["redistribution"] = k
        held_selectable += sum(1 for c in allocation.claimants.values()
                               if c.feasible and c.obj_id not in allocation.selected)
        o1 = decided["O1_allocation"]
        for u in sorted(set(o1.selected) - set(allocation.selected)):
            b_rows.append({"k": k, "cur_step": cur_step, "unit": u, "objective": o1.selected[u],
                           "free_flow": allocation.claimants[u].free_flow, "excluded": sorted(decided["doomed"])})
        for name in ("O2", "O3"):
            redirect_infeasible[name] += decided[f"{name}_allocation"].redirect_infeasible
        ground = sd.own_ground(observation, faction)
        cities = {c.coord for c in (observation.cities() or ())}

        def other_actions(actions):
            return [rd.plain(a) for a in actions if not (a.get("type") == sd.MOVE and a.get("obj_id") in ground)]
        reference = other_actions(decided["baseline"])
        for name in POLICIES[1:] + ("identity",):
            unrelated["actions_compared"] += len(reference)
            if other_actions(decided[name]) != reference:
                unrelated["differences"] += 1
                problems.append(f"decision {k}: {name} changed an action other than an own ground move")
        emitted = {name: sd.ground_moves(decided["baseline" if name == "baseline-v2" else name], ground)
                   for name in POLICIES}
        slots = {name: collections.defaultdict(set) for name in POLICIES}
        for name, moves in emitted.items():
            for u, action in moves.items():
                end = list(action["move_path"])[-1]
                if end in cities:
                    slots[name][end].add(u)
        for name in POLICIES:
            for ref in ("t9-v1", "t9-v3"):
                coords = set(slots[name]) | set(slots[ref])
                slot_diffs[name][f"vs_{ref}"] += sum(1 for c in coords if slots[name][c] != slots[ref][c])
                units = set(emitted[name]) | set(emitted[ref])
                changed = {u for u in units if dict(emitted[name].get(u) or {}) != dict(emitted[ref].get(u) or {})}
                action_diffs[name][f"vs_{ref}"] |= changed
                action_diff_decisions[name][f"vs_{ref}"] += len(changed)
    if held_selectable != len(facts["holds_private"]):
        problems.append(f"held selectable claimant-decisions {held_selectable} differ from Sprint 12's holds")
    if problems:
        raise SystemExit(f"refused: {gid}: {len(problems)} reconstruction problems, e.g. {problems[:3]}")

    # -------- reservation episodes (section 6)
    holds = facts["holds_private"]
    places = facts["places_private"]
    selected_at: Dict[Any, List[int]] = collections.defaultdict(list)
    for (u, coord), ks in selections.items():
        for k in ks:
            selected_at[coord].append(k)
    eps = sd.episodes(counted, selections)
    holds_by_objective: Dict[Any, List[Mapping[str, Any]]] = collections.defaultdict(list)
    for hold in holds:
        holds_by_objective[hold["objective"]].append(hold)
    episode_rows = []
    for ep in eps:
        start_state = ep["first_counted"]
        verdict, lost = fate(ep["unit"], ep["objective"], start_state)
        path = list(states[ep["first_counted"]].units.get(ep["unit"], (None, ()))[1])
        last_position = states[ep["last_counted"]].units.get(ep["unit"], (None,))[0]
        progress = path.index(last_position) + 1 if last_position in path else 0
        # the episode runs from the selection (Sprint 12 counts a unit selected at a decision among that decision's
        # holders) to the last decision in which it was counted
        selection_ff = next((p["free_flow"] for p in places if p["unit"] == ep["unit"]
                             and p["objective"] == ep["objective"] and p["k"] == ep["selection"]), None)
        bounds = dict(ep["bounds"])
        if ep["selection"] is not None:
            bounds[ep["selection"]] = selection_ff
        blocked = [h for h in holds_by_objective[ep["objective"]]
                   if ep["start"] <= h["k"] <= ep["last_counted"] and ep["unit"] in h["holders"]]
        faster = [h for h in blocked if h["free_flow"] is not None and bounds.get(h["k"]) is not None
                  and h["free_flow"] < bounds[h["k"]]]
        row = {"unit": ep["unit"], "objective": ep["objective"], "label": names[ep["objective"]],
               "selection": ep["selection"], "first_counted": ep["first_counted"], "last_counted": ep["last_counted"],
               "counted_decisions": ep["last_counted"] - ep["first_counted"] + 1, "fate": verdict,
               "selection_free_flow": selection_ff, "decisions_to_release": ep["last_counted"] - ep["start"] + 1,
               "path_hexes": len(path), "hexes_reached": progress,
               "blocked_claimant_decisions": len(blocked), "blocked_claimants": len({h["unit"] for h in blocked}),
               "blocked_free_flow": sorted(h["free_flow"] for h in blocked if h["free_flow"] is not None),
               "faster_blocked_decisions": len(faster), "faster_blocked_claimants": len({h["unit"] for h in faster}),
               "kind": sd.KIND.get(states[ep["first_counted"]].kinds.get(ep["unit"]), "other")}
        if verdict == "DESTROYED":
            row["destroyed_step"] = states[lost].cur_step
            row["released_next_decision"] = lost == ep["last_counted"] + 1
            replacement = next((k for k in sorted(selected_at[ep["objective"]]) if k >= lost), None)
            row["replacement_decision"] = replacement
            if replacement is not None:
                row["release_to_replacement_steps"] = states[replacement].cur_step - states[lost].cur_step
                reps = [p for p in places if p["objective"] == ep["objective"] and p["k"] == replacement]
                row["replacement_outcomes"] = sorted(p["outcome"] for p in reps)
                arrivals = [p["arrival_step"] - p["cur_step"] for p in reps if p.get("arrival_step") is not None]
                row["replacement_to_arrival_steps"] = min(arrivals) if arrivals else None
        episode_rows.append(row)

    # the 27 holders of Sprint 12
    unproductive_pairs = sorted({(u, h["objective"]) for h in holds for u in h["unproductive_holders"]})
    pair_fates = collections.Counter(fate(u, coord, min(h["k"] for h in holds if u in h["unproductive_holders"]
                                                        and h["objective"] == coord) + 1)[0]
                                     for u, coord in unproductive_pairs)
    first_blocking = next((h["k"] for h in sorted(holds, key=lambda h: h["k"]) if h["unproductive_holders"]), None)

    # -------- features at selection (section 7)
    feature_rows = []
    for p in places:
        allocation_k = (steps[p["k"]].get("s12") or {}).get(str(seat))["allocation"]
        claimant = allocation_k["claimants"][str(p["unit"])]
        info = allocation_k["objectives"][str(p["objective"])]
        incumbents = info["physical"] + info["movers"]
        f = sd.features(raws[p["k"]], faction, p["unit"], p["objective"], claimant["path"], p["free_flow"], incumbents)
        feature_rows.append({"game": gid, "lost": p["outcome"] == "LOST", "outcome": p["outcome"], "k": p["k"],
                             "unit": p["unit"], **f})
    holder_rows = []
    for ep in episode_rows:
        if ep["fate"] not in ("DESTROYED", "HONOURED"):
            continue
        near, weakened, n_k = 0, 0, 0
        for k in range(ep["first_counted"], ep["last_counted"] + 1):
            raw = raws[k]
            units = {u["obj_id"]: u for u in raw.get("operators") or ()}
            me = units.get(ep["unit"])
            if me is None:
                continue
            n_k += 1
            enemy_hexes = [u["cur_hex"] for u in units.values() if u.get("color") == 1 - faction]
            near += int(any(sd.hex_distance(me["cur_hex"], h) <= 3 for h in enemy_hexes))
            weakened += int((me.get("blood") or 0) < (me.get("max_blood") or 0))
        holder_rows.append({"fate": ep["fate"], "decisions": n_k, "near_share": near / n_k if n_k else None,
                            "weakened_share": weakened / n_k if n_k else None})

    # -------- later facts under v3 (section 5)
    by_interval = {sd.interval(k): {"decisions_with_shot_listed": 0, "shot_orders": 0, "own_units_lost": 0}
                   for k in (0, 100, 500, 1500)}
    for k in range(n):
        state = states[k]
        bucket = by_interval[sd.interval(k)]
        if state.stage == 2:
            bucket["decisions_with_shot_listed"] += int(any(sd.SHOOT in v for v in state.valid.values()))
        bucket["shot_orders"] += sum(1 for a in steps[k].get("submitted") or ()
                                     if a["seat"] == seat and a["action"].get("type") == sd.SHOOT)
    for u, j in lost_at.items():
        by_interval[sd.interval(min(j, n - 1))]["own_units_lost"] += 1
    history = facts["objectives"]
    later = {"capture_order": facts["capture_order"],
             "never_own": sorted(label for label, h in history.items() if h["first_own_step"] is None),
             "own_then_lost": sorted(label for label, h in history.items()
                                     if h["first_own_step"] is not None and not h["own_at_end"]),
             "objectives_at_end": facts["objectives_at_end"], "coverage": facts["coverage"],
             "by_interval": by_interval}

    # -------- redirects in detail (section 5)
    redirects = [o for o in orders if o["v1"] == sd.REDIRECT]
    redirect_public = collections.Counter()
    for o in redirects:
        k = o["k"]
        flags = states[k].flags
        redirect_public[(names[o["destination"]], names[o["v1_to"]], o["kind"], o["v3"], o["cause"],
                         flag_state(flags.get(o["destination"]), faction),
                         flag_state(flags.get(o["v1_to"]), faction))] += 1

    # LOST places against DESTROYED episodes: a place whose unit never became a counted mover forms no episode
    episode_starts = {(e["unit"], e["objective"], e["selection"]) for e in episode_rows}
    lost_places = [p for p in places if p["outcome"] == "LOST"]
    orphan = [p for p in lost_places if (p["unit"], p["objective"], p["k"]) not in episode_starts]
    reconciliation = {"lost_places": len(lost_places),
                      "destroyed_episodes": sum(1 for e in episode_rows if e["fate"] == "DESTROYED"),
                      "lost_places_without_episode": len(orphan),
                      "decisions_from_selection_to_loss": distribution(
                          [lost_at[p["unit"]] - p["k"] for p in orphan if p["unit"] in lost_at]),
                      "destroyed_pairs_without_episode": sum(1 for pair in unproductive_pairs
                                                             if not any((e["unit"], e["objective"]) == pair
                                                                        for e in episode_rows))}
    by_pair_interval = collections.Counter((names[o["destination"]], names[o["v1_to"]], o["interval"]) for o in redirects)
    first_pair = {}
    for o in redirects:
        first_pair.setdefault((names[o["destination"]], names[o["v1_to"]]), o["k"])
    redirect_timing = [{"from": a, "to": b, "interval": iv, "count": m, "first_decision": first_pair[(a, b)]}
                       for (a, b, iv), m in sorted(by_pair_interval.items())]
    class_reasons = collections.Counter((o["class"], o["v3_reason"] or "-") for o in orders if o["class"])
    decision_one = {"redirects": sum(1 for o in redirects if o["k"] == 1),
                    "distinct_redirected": len({o["unit"] for o in redirects if o["k"] == 1}),
                    "observation_sha256": hashlib.sha256(json.dumps(raws[1], sort_keys=True, default=str)
                                                         .encode("utf-8")).hexdigest()}

    # -------- assemble
    classes = collections.Counter(o["class"] for o in orders if o["class"])
    a_units = {o["unit"] for o in redirects}
    b_units = {r["unit"] for r in b_rows}
    v1_emitted_ground = sum(1 for o in orders if o["v1"] in (sd.KEEP, sd.REDIRECT))

    def step_of(k: Optional[int]) -> Optional[int]:
        return None if k is None else states[k].cur_step

    public = {
        "game_id": gid, "cell": cell, "candidate_side": ("red", "blue")[faction], "decisions": n,
        "active_decisions": active, "orders": len(orders), "unrelated_actions": unrelated,
        "classes": {c: classes.get(c, 0) for c in sd.CLASSES},
        "unchanged_orders": sum(1 for o in orders if not o["class"]),
        "classes_by_interval": {iv: {c: sum(1 for o in orders if o["class"] == c and o["interval"] == iv)
                                     for c in sd.CLASSES} for iv in sorted({o["interval"] for o in orders})},
        "classes_by_objective": {label: {c: sum(1 for o in orders if o["class"] == c and o["objective"]
                                             and names.get(o["destination"]) == label) for c in sd.CLASSES}
                                 for label in sorted(names.values())},
        "redirect_causes": dict(sorted(collections.Counter(o["cause"] for o in redirects).items())),
        "classes_by_v3_reason": [{"class": c, "v3_reason": r, "count": m} for (c, r), m in sorted(class_reasons.items())],
        "redirect_timing": redirect_timing, "decision_one": decision_one, "reconciliation": reconciliation,
        "first": {"any_action_difference": {"decision": first["any_action"], "step": step_of(first["any_action"])},
                  "redistribution": {"decision": first["redistribution"], "step": step_of(first["redistribution"])},
                  "blocking_unproductive_reservation": {"decision": first_blocking, "step": step_of(first_blocking)},
                  "o1_admission": {"decision": b_rows[0]["k"] if b_rows else None,
                                   "step": b_rows[0]["cur_step"] if b_rows else None}},
        "a": {"distinct_redirected": len(a_units), "redirects": len(redirects), "v1_emitted_ground": v1_emitted_ground,
              "first_step": step_of(first["redistribution"])},
        "b": {"distinct_admitted": len(b_units), "admitted_decisions": len(b_rows), "held_selectable": held_selectable,
              "first_step": b_rows[0]["cur_step"] if b_rows else None},
        "redirects": [{"from": a, "to": b, "kind": c, "v3_form": d, "cause": e, "from_flag": f, "to_flag": g, "count": m}
                      for (a, b, c, d, e, f, g), m in sorted(redirect_public.items())],
        "later_facts": later,
        "oracles": {name: {"cross_objective": sum(1 for o in orders if _form(o, name) == sd.REDIRECT),
                           "staged": sum(1 for o in orders if _form(o, name) == sd.STAGE),
                           "withheld": sum(1 for o in orders if _form(o, name) == sd.WITHHOLD),
                           "kept": sum(1 for o in orders if _form(o, name) == sd.KEEP),
                           "admitted_vs_v3": sum(1 for o in orders if _form(o, name) in (sd.KEEP, sd.REDIRECT)
                                                 and o["v3"] in (sd.STAGE, sd.WITHHOLD)),
                           "slot_differences": dict(slot_diffs[name]),
                           "action_differences": dict(action_diff_decisions[name]),
                           "distinct_differing": {ref: len(s) for ref, s in action_diffs[name].items()}}
                    for name in POLICIES},
        "redirect_alternatives_dropped_by_end_test": redirect_infeasible,
        "sprint12_cross_check": {"unproductive": facts["unproductive"], "places_outcomes": facts["places"]["outcomes"],
                                 "unproductive_pairs": len(unproductive_pairs),
                                 "unproductive_pair_fates": dict(sorted(pair_fates.items()))},
        "names": sorted(names.values()),
    }
    private = {"game_id": gid, "seat": seat, "faction": faction, "names": {str(c): v for c, v in names.items()},
               "orders": orders, "b_rows": b_rows, "episodes": episode_rows, "features": feature_rows,
               "holder_rows": holder_rows, "unproductive_pairs": unproductive_pairs,
               "a_set": sorted({(o["k"], o["unit"]) for o in redirects}), "b_set": sorted({(r["k"], r["unit"]) for r in b_rows}),
               "private_values": sorted(_private_values(states, raws))}
    public["episodes"] = episode_summary(episode_rows)
    public["holder_descriptives"] = holder_summary(holder_rows)
    return public, private


def _form(order: Mapping[str, Any], name: str) -> str:
    if name == "baseline-v2":
        return sd.KEEP
    if name == "t9-v1":
        return order["v1"]
    if name == "t9-v3":
        return order["v3"]
    return order[f"form_{name}"]


def _private_values(states: Sequence[Any], raws: Sequence[Mapping[str, Any]]) -> set:
    """The hexes of the game (every position, path hex and objective seen by the seat), which must never appear as a
    value in a public file; a public count that coincides with one refuses the run. Unit ids of these games include
    round numbers (100, 200, ... 1,300) that coincide with steps and counts, so ids are excluded structurally instead:
    forbidden keys, aggregation only, and the planted-id tests of ``tests/test_s13_diagnosis.py``."""
    out = set()
    for raw in raws:
        for u in list(raw.get("operators") or ()) + list(raw.get("passengers") or ()):
            if isinstance(u.get("cur_hex"), int):
                out.add(u["cur_hex"])
            for h in u.get("move_path") or ():
                out.add(h)
        for c in raw.get("cities") or ():
            out.add(c["coord"])
    return out


def distribution(values: Sequence[Any]) -> Dict[str, Any]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0}
    mid = len(values) // 2
    median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
    return {"n": len(values), "min": values[0], "median": median, "max": values[-1]}


def episode_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"episodes": len(rows), "by_fate": dict(sorted(collections.Counter(r["fate"] for r in rows).items()))}
    for fate in ("HONOURED", "DESTROYED", "ALIVE_NOT_ARRIVED"):
        sub = [r for r in rows if r["fate"] == fate]
        out[fate] = {"episodes": len(sub), "counted_decisions": distribution([r["counted_decisions"] for r in sub]),
                     "blocked_claimant_decisions": sum(r["blocked_claimant_decisions"] for r in sub),
                     "blocking_episodes": sum(1 for r in sub if r["blocked_claimant_decisions"]),
                     "faster_blocked_decisions": sum(r["faster_blocked_decisions"] for r in sub),
                     "selection_free_flow": distribution([r["selection_free_flow"] for r in sub]),
                     "hexes_reached_share": distribution([round(r["hexes_reached"] / r["path_hexes"], 4)
                                                          for r in sub if r["path_hexes"]]),
                     "by_kind": dict(sorted(collections.Counter(r["kind"] for r in sub).items()))}
    destroyed = [r for r in rows if r["fate"] == "DESTROYED"]
    blocking = [r for r in destroyed if r["blocked_claimant_decisions"]]
    out["destroyed_blocking"] = {
        "holders": len(blocking),
        "blocked_claimant_decisions": sum(r["blocked_claimant_decisions"] for r in blocking),
        "blocked_claimants": sum(r["blocked_claimants"] for r in blocking),
        "faster_blocked_decisions": sum(r["faster_blocked_decisions"] for r in blocking),
        "faster_blocked_claimants": sum(r["faster_blocked_claimants"] for r in blocking),
        "blocked_free_flow": distribution([v for r in blocking for v in r["blocked_free_flow"]]),
        "lifetime_decisions": distribution([r["counted_decisions"] for r in blocking]),
        "selection_to_release_decisions": distribution([r.get("decisions_to_release") for r in blocking]),
        "released_next_decision": sum(1 for r in blocking if r.get("released_next_decision")),
        "release_to_replacement_steps": distribution([r.get("release_to_replacement_steps") for r in blocking]),
        "no_replacement": sum(1 for r in blocking if r.get("replacement_decision") is None),
        "replacement_to_arrival_steps": distribution([r.get("replacement_to_arrival_steps") for r in blocking]),
        "replacement_occupied_or_held": sum(1 for r in blocking if set(r.get("replacement_outcomes") or ())
                                            & {"OCCUPIED", "HELD"}),
    }
    return out


def holder_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out = {}
    for fate in ("HONOURED", "DESTROYED"):
        sub = [r for r in rows if r["fate"] == fate and r["decisions"]]
        out[fate] = {"holders": len(sub),
                     "mean_share_with_enemy_within_3": round(sum(r["near_share"] for r in sub) / len(sub), 4) if sub else None,
                     "mean_share_weakened": round(sum(r["weakened_share"] for r in sub) / len(sub), 4) if sub else None}
    return out


# ------------------------------------------------------------------------------------------------
# Sprint 9 and the snapshot comparison (section 8)


def seat_facts(t9cap: Mapping[str, Any], faction: int) -> Mapping[str, Any]:
    return (t9cap.get("seats") or {}).get(str(faction)) or {}


def snapshot_view(snapshots: Sequence[Mapping[str, Any]], faction: int, names: Mapping[Any, str]) -> Dict[str, Any]:
    series = sd.snapshot_series(snapshots, faction, names)
    coverage = sd.coverage_series(series)
    return {"series": series, "coverage": coverage}


def comparison(s12_public: Sequence[Mapping[str, Any]], names: Mapping[Any, str], repo: Path = REPO_ROOT
               ) -> Dict[str, Any]:
    ev = repo / "local" / "evaluation"
    population: Dict[str, List[Dict[str, Any]]] = {"H1": [], "H2": []}
    for game in s9_games(repo):
        gid, cell = game["game_id"], game["cell"]
        faction = 0 if cell == "H1" else 1
        side = ("red", "blue")[faction]
        record = json.loads((ev / S9_STUDY / "games" / f"{gid}.json").read_text(encoding="utf-8"))
        t9cap = json.loads((ev / S9_STUDY / "capture" / f"{gid}.t9.json").read_text(encoding="utf-8"))
        explore = json.loads((ev / S9_STUDY / "capture" / f"{gid}.explore.json").read_text(encoding="utf-8"))
        policy = next(s["policy"] for s in record["seats"] if s["faction"] == faction)
        if policy != "t9-capacity-allocation-v1":
            raise SystemExit(f"refused: {gid} seat {side} is {policy}")
        population[cell].append(_game_fields(record, t9cap, explore["snapshots"], faction, names))
    v3 = {"H1": [], "H2": []}
    for public in s12_public:
        gid = public["game_id"]
        faction = 0 if public["cell"] == "H1" else 1
        evs = ev / S12_CARD
        record = json.loads((evs / "games" / f"{gid}.json").read_text(encoding="utf-8"))
        t9cap = json.loads((evs / "capture" / f"{gid}.t9.json").read_text(encoding="utf-8"))
        v3cap = json.loads((evs / "capture" / f"{gid}.v3.json").read_text(encoding="utf-8"))
        fields = _game_fields(record, t9cap, v3cap["snapshots"], faction, names)
        fields["game_id"] = gid
        fields["v3_changes"] = (v3cap.get("v3") or {}).get("changes") or {}
        v3[public["cell"]].append(fields)
    out: Dict[str, Any] = {"population": {cell: len(rows) for cell, rows in population.items()}}
    grid = [row["k"] for row in population["H1"][0]["series"]]
    for cell in ("H1", "H2"):
        rows = population[cell]
        if any([r["k"] for r in g["series"]] != grid for g in rows + v3[cell]):
            raise SystemExit("refused: the snapshot grids differ")
        metric = "coverage" if cell == "H1" else "margin_series"
        floors = {key: [min(g[key][i] for g in rows) if all(g[key][i] is not None for g in rows) else None
                        for i in range(len(grid))] for key in ("coverage", "margin_series", "attack_series",
                                                               "strength_series")}
        pattern = sd.characteristic([g["series"] for g in rows], sorted(names.values()))
        defined = sum(len(p) for p in pattern)
        games = []
        for g in v3[cell]:
            d = sd.stays_below(g[metric], floors[metric])
            attack = sd.stays_below(g["attack_series"], floors["attack_series"])
            strength = sd.stays_below(g["strength_series"], floors["strength_series"])
            contradiction = sd.first_contradiction(g["series"], pattern) if defined else None
            placed = {key: sd.placement(g[key], [r[key] for r in rows]) for key in SCALARS}
            games.append({"game_id": g["game_id"], "divergence_snapshot": None if d is None else grid[d],
                          "attack_divergence_snapshot": None if attack is None else grid[attack],
                          "strength_divergence_snapshot": None if strength is None else grid[strength],
                          "first_ownership_divergence": contradiction,
                          "capture_order_50": [label for _, label in g["capture_order"]],
                          "placement": placed, "v3_changes": g["v3_changes"]})
        first_own = {}
        for label in sorted(names.values()):
            ks = [next((k for k, l in g["capture_order"] if l == label), None) for g in rows]
            first_own[label] = {"games_owning": sum(1 for k in ks if k is not None), "first_own_k": distribution(ks)}
        out[cell] = {"games": games, "characteristic_entries": defined,
                     "t9v1_withheld_unit_decisions": distribution([r["withheld_v1"] for r in rows]),
                     "characteristic_by_snapshot": {str(grid[i]): p for i, p in enumerate(pattern) if p},
                     "t9v1_first_own": first_own,
                     "t9v1_capture_orders": sorted(collections.Counter(
                         " > ".join(label for _, label in g["capture_order"]) for g in rows).items(),
                         key=lambda item: (-item[1], item[0]))[:5],
                     "unavailable_in_sprint9": ["per-decision redirect timing", "full-step states", "shot listings",
                                                "per-objective flags at the final state (snapshots end at k 2850)"]}
    return out


SCALARS = ("emitted_ground", "redirected", "largest_commitment", "waiting_unit_steps", "coverage_mean",
           "ever_own", "own_at_end", "own_then_lost_50", "attack", "units_lost", "margin")


def _game_fields(record: Mapping[str, Any], t9cap: Mapping[str, Any], snapshots: Sequence[Mapping[str, Any]],
                 faction: int, names: Mapping[Any, str]) -> Dict[str, Any]:
    side = ("red", "blue")[faction]
    f = seat_facts(t9cap, faction)
    scores = record.get("final_scores") or {}
    view = snapshot_view(snapshots, faction, names)
    series = view["series"]
    ever = {label for row in series for label in row["own"]}
    return {"series": series, "coverage": view["coverage"],
            "margin_series": [row["margin"] for row in series], "attack_series": [row["attack"] for row in series],
            "strength_series": [row["strength"] for row in series],
            "capture_order": sd.capture_order(series),
            "emitted_ground": (f.get("moves") or {}).get("emitted_ground"),
            "redirected": (f.get("moves") or {}).get("redirected"),
            "withheld_v1": (f.get("withholding") or {}).get("unit_decisions"),
            "largest_commitment": (f.get("max_objective_commitment") or {}).get("max"),
            "waiting_unit_steps": (f.get("waiting_in_front_of_full_hex") or {}).get("sum"),
            "coverage_mean": round((f.get("objectives") or {}).get("mean_held"), 4),
            "ever_own": (f.get("objectives") or {}).get("ever_held"),
            "own_at_end": (f.get("objectives") or {}).get("held_at_end"),
            "own_then_lost_50": len(ever - set(series[-1]["own"])),
            "attack": scores.get(f"{side}_attack"), "units_lost": (f.get("losses") or {}).get("lost"),
            "margin": scores.get(f"{side}_win")}


# ------------------------------------------------------------------------------------------------
# Assembly


def build(repo: Path = REPO_ROOT) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    require_inputs(repo)
    costs = costs_for(repo)
    games, private = [], {}
    for entry in s12_games(repo):
        public, rows = analyze_game(entry, costs, repo)
        games.append(public)
        private[entry["game_id"]] = rows
    names_by_coord = {int(c): v for c, v in next(iter(private.values()))["names"].items()}
    compare = comparison(games, names_by_coord, repo)
    hidden = set().union(*(set(p["private_values"]) for p in private.values()))

    # pooled features and their separation (section 7)
    feature_rows = [r for p in private.values() for r in p["features"]]
    separations = {f: sd.separation(feature_rows, f) for f in sd.FEATURES}
    quartiles = {f: sd.quartile_table(feature_rows, f) for f in sd.FEATURES}
    prospective = any(s["separating"] for s in separations.values())

    # disposition (section 9)
    a_all = {(g, k, u) for g, p in private.items() for k, u in p["a_set"]}
    b_all = {(g, k, u) for g, p in private.items() for k, u in p["b_set"]}
    union = a_all | b_all
    overlap = len(a_all & b_all) / len(union) if union else 0.0
    divergence = {}
    for cell in ("H1", "H2"):
        for g in compare[cell]["games"]:
            divergence[g["game_id"]] = g["divergence_snapshot"]
    per_game = {g["game_id"]: sd.game_materiality(g["a"], g["b"], divergence[g["game_id"]]) for g in games}
    seats = {g["game_id"]: g["cell"] for g in games}
    sa = sum(g["a"]["distinct_redirected"] for g in games)
    sb = sum(g["b"]["distinct_admitted"] for g in games)
    result = sd.disposition(per_game, seats, overlap, sa, sb, prospective)

    head = {"schema": SCHEMA, "note": NOTE, "inputs_sha256": sha256(INPUTS) if repo == REPO_ROOT else None}
    out = {
        "reconstruction": {**head, "games": [{key: g[key] for key in ("game_id", "cell", "candidate_side", "decisions",
                                                                      "active_decisions", "orders", "unchanged_orders",
                                                                      "classes", "classes_by_interval",
                                                                      "classes_by_objective", "redirect_causes",
                                                                      "classes_by_v3_reason", "unrelated_actions")}
                                             for g in games],
                           "pooled_classes": {c: sum(g["classes"][c] for g in games) for c in sd.CLASSES},
                           "verification": "every decision of the v3 seat reconstructed; baseline-v2 actions and trace "
                                           "digest, v3 actions and allocation sets, the oracle allocator without "
                                           "modifications and the Sprint 10 audit of T9-v1 all agreed"},
        "redistribution": {**head, "games": [{"game_id": g["game_id"], "cell": g["cell"], "first": g["first"],
                                              "a": g["a"], "redirects": g["redirects"], "later_facts": g["later_facts"],
                                              "redirect_timing": g["redirect_timing"],
                                              "decision_one": {k: v for k, v in g["decision_one"].items()
                                                               if k != "observation_sha256"}}
                                             for g in games],
                           "decision_one_state_identical_within_seat": {
                               cell: len({g["decision_one"]["observation_sha256"] for g in games if g["cell"] == cell}) == 1
                               for cell in ("H1", "H2")}},
        "reservations": {**head, "games": [{"game_id": g["game_id"], "cell": g["cell"], "episodes": g["episodes"],
                                            "sprint12_cross_check": g["sprint12_cross_check"], "b": g["b"],
                                            "reconciliation": g["reconciliation"]}
                                           for g in games],
                         "pooled": episode_summary([r for p in private.values() for r in p["episodes"]])},
        "features": {**head, "places": len(feature_rows), "lost": sum(1 for r in feature_rows if r["lost"]),
                     "separation": separations, "quartiles": quartiles, "prospectively_separating": prospective,
                     "holder_descriptives": {g["game_id"]: g["holder_descriptives"] for g in games}},
        "oracles": {**head, "games": [{"game_id": g["game_id"], "cell": g["cell"], "policies": g["oracles"],
                                       "redirect_alternatives_dropped_by_end_test":
                                           g["redirect_alternatives_dropped_by_end_test"]} for g in games],
                    "overlap": {"a_unit_decisions": len(a_all), "b_unit_decisions": len(b_all),
                                "both": len(a_all & b_all), "jaccard": round(overlap, 4)}},
        "sequence": {**head, "comparison": compare,
                     "certificates": [{"game_id": g["game_id"], "cell": g["cell"], "first": g["first"],
                                       "divergence_snapshot": divergence[g["game_id"]],
                                       "statement": "the compared T9-v1 games are other stochastic games; no causal "
                                                    "chain between them and this game is claimed"} for g in games]},
        "disposition": {**head, "thresholds": dict(sd.RULE), "per_game": per_game, "seats": seats, **result},
    }
    for name, data in out.items():
        found = sd.public_check(data, hidden)
        if found:
            raise SystemExit(f"refused: public {name} carries private content: {found[:5]}")
    return out, private


def cmd_run(args: argparse.Namespace) -> int:
    out, private = build()
    texts = {name: dump(data) for name, data in out.items()}
    for name, text in texts.items():
        if len(text.encode("utf-8")) >= 100_000:
            raise SystemExit(f"refused: public {name}.json is {len(text)} bytes (limit 100,000)")
    if args.check:
        ok = True
        for name, text in texts.items():
            path = OUT_DIR / f"{name}.json"
            same = path.exists() and path.read_text(encoding="utf-8") == text
            ok &= same
            print(f"{'OK' if same else 'MISMATCH'} evaluation/s13-v3-diagnosis/{name}.json")
        return 0 if ok else 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        (OUT_DIR / f"{name}.json").write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(private, sort_keys=True, default=list).encode("utf-8")
    (PRIVATE / "diagnosis-private.json.gz").write_bytes(gzip.compress(blob, mtime=0))
    print(f"wrote {len(texts)} public files; disposition {out['disposition']['label']}")
    return 0


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    freeze = sub.add_parser("freeze", help="pin every private input by SHA-256")
    freeze.add_argument("--check", action="store_true")
    run = sub.add_parser("run", help="the diagnosis (requires the pinned inputs)")
    run.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "freeze":
        text = dump(build_inputs())
        if args.check:
            same = INPUTS.exists() and INPUTS.read_text(encoding="utf-8") == text
            print("inputs: identical" if same else "inputs: MISMATCH")
            return 0 if same else 1
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()}")
        return 0
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
