"""Pre-session rehearsals of the Sprint 12 screen on frozen Sprint 10 captures (server only; no engine).

    python scripts/s12_rehearsal.py real [--check]   # evaluation/s12-v3-screen/rehearsal.json
    python scripts/s12_rehearsal.py timing           # evaluation/s12-v3-screen/timing.json

``real`` runs the screen's extraction (``evaluation.s12_timeline``) and seat-local reconstruction
(``evaluation.s12_capture.reconstruct``) over the six frozen full-step diagnostic captures of Sprint 10 (pinned by
SHA-256 in the output) and requires them to reproduce facts established independently:

* in the ``baseline-v2`` 2120531121 C3 game, objective A (Sprint 11's label) first own at decision 564, with two own
  units standing on it (Sprint 11's certificate);
* in the ``baseline-v2`` 1930331196 C2 game, an accepted direct-fire order at decision 611 (Sprint 10's diagnosis);
* in every game, the value of the objectives the diagnosed seat holds in the final state equals its occupy score;
* in every game, the arrival of every emitted ground move against its free-flow time (exact, late, early, never)
  equals Sprint 11's control audit (``evaluation/s11-batch-allocator/replay.json``);
* at every decision, the reconstructed ``baseline-v2`` actions equal the captured ones, and wherever Sprint 11's
  private replay holds the decision, the reconstructed v3 places and held moves equal Sprint 11's.

``timing`` replays the largest of these captures through the complete observer stack (Sprint 9's ``T9Capture``, the
compact v3 capture and the full-step timeline, with the diagnosed seat decided by v3 from its captured observation
and memory) and through the per-game analysis, measures their time, and projects it to a 2130511121 head-to-head game.
"""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.agent import PolicyAgent  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin, normalize_state  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import s12_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import t9_batch_replay as rp  # noqa: E402
from miaosuan_agent.evaluation import t9_confirmation as tc  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

EV = REPO_ROOT / "local" / "evaluation"
OUT = REPO_ROOT / "evaluation" / sc.SCREEN_ID / "rehearsal.json"
TIMING = REPO_ROOT / "evaluation" / sc.SCREEN_ID / "timing.json"
S11_PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s11" / "replay-private.json"
S11_PUBLIC = REPO_ROOT / "evaluation" / "s11-batch-allocator" / "replay.json"
GAMES = [  # (configuration, card, stem, scenario, map id, diagnosed seat, policy that played it)
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g01", "2120531121", "21", 11, "t9-v1"),
    ("2120531121 C3", "s10-t9-v1-diagnosis", "2120531121.C3.s10-t9-v1-diagnosis.g02", "2120531121", "21", 11,
     "baseline-v2"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g03", "1930331196", "96", 11, "t9-v1"),
    ("1930331196 C3", "s10-t9-v1-diagnosis", "1930331196.C3.s10-t9-v1-diagnosis.g04", "1930331196", "96", 11,
     "baseline-v2"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g01", "1930331196", "96", 1,
     "t9-v1"),
    ("1930331196 C2", "s10-t9-v1-c2-diagnosis", "1930331196.C2.s10-t9-v1-c2-diagnosis.g02", "1930331196", "96", 1,
     "baseline-v2"),
]
#: Sprint 10's head-to-head games of 2130511121 (sessions 2785, 2786): the longest wall time without the full timeline.
H2H_WALL_SECONDS = 131.8
H2H_OPERATORS, DIAGNOSED_OPERATORS = 89, 54
#: The largest in-game observer time of Sprint 10's full-step diagnostic capture (session 2775, 1930331196 C3), which
#: did the same per-step work (full snapshots and a seat-local re-decision) inside a running game.
SPRINT10_MAX_IN_GAME_OBSERVER_SECONDS = 154.7


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def costs(card: str, scenario: str, map_id: str) -> MoveCosts:
    data = EV / card / "data" / scenario / "Data"
    return MoveCosts.from_raw(sdk_data.load_inputs(data, scenario, map_id).cost, Origin.ENGINE, "setup_info.cost_data")


def files(card: str, stem: str):
    base = EV / card / "capture" / stem
    with open(f"{base}.windows.pkl", "rb") as handle:
        windows = pickle.load(handle)
    compact = json.loads(Path(f"{base}.diagnostic.json").read_text(encoding="utf-8"))
    record = json.loads((EV / card / "games" / f"{stem}.json").read_text(encoding="utf-8"))
    return windows, compact, record


def arrival_audit(states, raw_units, steps, seat, router) -> collections.Counter:
    """Every emitted ground move of the seat: arrival at its path's end (path empty there) against the decision index
    plus its free-flow time (Sprint 11's convention)."""
    out = collections.Counter()
    for k, entry in enumerate(steps):
        if states[k].stage != 2:
            continue
        for item in entry.get("submitted") or ():
            action = item["action"]
            if item["seat"] != seat or action.get("type") != 1 or action.get("obj_id") not in states[k].units:
                continue
            path = list(action["move_path"])
            hex_, _, _, _ = states[k].units[action["obj_id"]]
            raw_unit = raw_units[k][action["obj_id"]]
            times, _ = tb.path_times(router, raw_unit.get("type"), raw_unit.get("move_state"),
                                     raw_unit.get("basic_speed"), hex_, path)
            if times is None:
                out["unreadable"] += 1
                continue
            arrived = next((j for j in range(k + 1, len(states) - 1) if action["obj_id"] in states[j].units
                            and states[j].units[action["obj_id"]][0] == path[-1]
                            and not states[j].units[action["obj_id"]][1]), None)
            predicted = k + sum(times)
            out["arrival: " + ("never" if arrived is None else "early" if arrived < predicted else
                               "exact" if arrived == predicted else "late")] += 1
    return out


def rehearse(entry, s11_private, s11_public) -> Dict[str, Any]:
    config, card, stem, scenario, map_id, seat, played = entry
    windows, compact, record = files(card, stem)
    faction = 0 if seat == 1 else 1
    side = "red" if faction == 0 else "blue"
    move_costs = costs(card, scenario, map_id)
    states, raws = tl.load_states(windows, seat, faction)
    raw_units = [{u["obj_id"]: u for u in raw.get("operators") or () if u.get("color") == faction} for raw in raws]
    steps = compact["steps"]
    router = ShootReservationPolicy(move_costs).router
    values = {c["coord"]: c.get("value") for c in raws[0].get("cities") or ()}
    names = tl.labels(values)
    history = tl.objective_history(states, faction)
    checks: Dict[str, Any] = {}
    final_value = sum(values[c] for c, h in history.items() if h["own_at_end"])
    checks["final objective value equals the occupy score"] = final_value == record["final_scores"][f"{side}_occupy"]
    audit = arrival_audit(states, raw_units, steps, seat, router)
    s11 = next(g for g in s11_public["games"] if g["game"] == stem)["control_audit"]
    expected = {k: v for k, v in s11.items() if k.startswith("arrival: ")}
    checks["arrival audit equals Sprint 11's"] = dict(audit) == expected
    checks["arrival audit"] = dict(sorted(audit.items()))
    rows = {r["k"]: r for r in s11_private[stem]["decisions"]}
    baseline_equal = owners_equal = decisions = compared = 0
    totals, removed = collections.Counter(), []
    stop_checks = collections.Counter()
    stacked = 0
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    for sample in samples:
        k = sample["k"]
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        raw = pickle.loads(snap["observation"])
        memory = pickle.loads(snap["memory"])
        rebuilt = cap.reconstruct(raw, seat, faction, memory, move_costs, v3=True)
        decisions += 1
        baseline_equal += int(rebuilt["baseline_actions"] == snap["baseline_actions"])
        state = states[k]
        stacked = max(stacked, max(collections.Counter(p[0] for p in state.units.values()).values(), default=0))
        if state.stage == 2 and any(a.get("type") == 1 for a in rebuilt["baseline_actions"]):
            observation = Observation.from_raw(raw, Origin.ENGINE)
            structure = rp.structural(observation, faction, rebuilt["baseline_actions"], rebuilt["actions"], router)
            capacity = rp.capacity_check(rp.commitments(observation, faction, router), structure["owners"])
            stop_checks["S8 caused"] += int(bool(capacity.get("caused")))
            stop_checks["S9"] += len(tl.staging_excess(state.units, rebuilt["baseline_actions"], rebuilt["actions"],
                                                      sc.RULES["stage_cap"]))
            stop_checks["S10"] += structure.get("prefix_failures", 0)
            stop_checks["S11"] += structure.get("cross_objective", 0)
            stop_checks["S12"] += structure.get("unrelated_changed", 0) + structure.get("invented", 0)
            stop_checks["decisions checked"] += 1
        if k in rows:
            observation = Observation.from_raw(raw, Origin.ENGINE)
            ground = rp.own_ground(observation, faction)
            base_moves = rp.ground_moves(rebuilt["baseline_actions"], ground)
            out_moves = rp.ground_moves(rebuilt["actions"], ground)
            structure = rp.structural(observation, faction, rebuilt["baseline_actions"], rebuilt["actions"], router)
            owners = structure["owners"]
            for key in ("kept", "shortened", "withheld"):
                totals[key] += structure.get(key, 0)
            removed.extend(structure["removed"])
            held = sorted(u for u, a in base_moves.items() if dict(out_moves.get(u) or {}) != dict(a))
            mine = {"owners": {str(c): sorted(ids) for c, ids in owners.items()}, "held": held}
            theirs = rows[k]["policies"]["candidate"]
            compared += 1
            owners_equal += int(mine == {"owners": {str(c): sorted(ids) for c, ids in theirs["owners"].items()},
                                         "held": sorted(theirs["held"])})
    published = next(g for g in s11_public["games"] if g["game"] == stem)
    checks["v3 kept, shortened and withheld totals equal Sprint 11's"] = (
        {k: totals[k] for k in ("kept", "shortened", "withheld")}
        == {k: published["policies"]["candidate"].get(k, 0) for k in ("kept", "shortened", "withheld")}
        and rp.distribution(removed) == published["hexes_removed_per_shortened_move"]["candidate"])
    checks["recomputed stops on the reconstructed v3 decisions"] = dict(sorted(stop_checks.items()))
    checks["no recomputed stop fires on correct v3 decisions"] = (
        stop_checks["decisions checked"] > 0
        and all(v == 0 for key, v in stop_checks.items() if key != "decisions checked"))
    checks["at most four own ground units on one hex in every state"] = stacked <= sc.RULES["capacity"]
    checks["largest own ground stack"] = stacked
    checks["baseline-v2 reconstructed equal (decisions)"] = [baseline_equal, decisions]
    checks["v3 places and held moves equal Sprint 11's (decisions)"] = [owners_equal, compared]
    if config == "2120531121 C3" and played == "baseline-v2":
        coord = next(c for c, n in names.items() if n == "80-point objective A")
        first = next(j for j, s in enumerate(states) if s.flags.get(coord) == faction)
        standing = sum(1 for u, (h, path, _, _) in states[first].units.items() if h == coord and not path)
        checks["objective A first own at decision 564 with two units standing"] = (first, standing) == (564, 2)
    if config == "1930331196 C2" and played == "baseline-v2":
        shots = [a["action"] for a in steps[611]["submitted"] if a["seat"] == seat and a["action"].get("type") == 2]
        responses = [tl.response(steps[611], seat, a) for a in shots]
        checks["accepted direct-fire order at decision 611"] = bool(shots) and all(r == "accepted" for r in responses)
    return {"configuration": config, "played_by": played, "capture_sha256": sha256(EV / card / "capture" /
                                                                                  f"{stem}.windows.pkl"),
            "decisions": len(samples), "checks": checks,
            "objectives": {names[c]: {"first_own_step": h["first_own_step"], "own_at_end": h["own_at_end"]}
                           for c, h in sorted(history.items(), key=lambda i: names[i[0]])}}


def cmd_real(args: argparse.Namespace) -> int:
    s11_private = json.loads(S11_PRIVATE.read_text(encoding="utf-8"))
    s11_public = json.loads(S11_PUBLIC.read_text(encoding="utf-8"))
    games = [rehearse(entry, s11_private, s11_public) for entry in GAMES]
    passed = all(v is True or (isinstance(v, list) and v[0] == v[1]) for g in games
                 for name, v in g["checks"].items()
                 if name not in ("arrival audit", "recomputed stops on the reconstructed v3 decisions",
                                 "largest own ground stack"))
    payload = {"schema": "miaosuan-s12-rehearsal/1", "screen": sc.SCREEN_ID, "games": [{**g, "stem": e[2]} for g, e in
                                                                                       zip(games, GAMES)],
               "s11_private_sha256": sha256(S11_PRIVATE), "passed": passed}
    text = sc.dump(payload)
    problems = sc.privacy_problems(payload)
    if problems:
        raise SystemExit(f"rehearsal output carries private content: {problems[:3]}")
    if args.check:
        same = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print(("OK " if same else "MISMATCH ") + OUT.relative_to(REPO_ROOT).as_posix())
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"rehearsal passed: {passed}")
    for g in games:
        print(g["configuration"], g["played_by"], json.dumps(g["checks"]))
    return 0 if passed else 1


def cmd_timing(args: argparse.Namespace) -> int:
    entry = GAMES[0]
    config, card, stem, scenario, map_id, seat, played = entry
    windows, compact, record = files(card, stem)
    move_costs = costs(card, scenario, map_id)
    inputs = sdk_data.load_inputs(EV / card / "data" / scenario / "Data", scenario, map_id)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    faction = 0 if seat == 1 else 1
    other_seat, other_faction = (11, 1) if seat == 1 else (1, 0)

    def view(sample):
        mapping = {-1: pickle.loads(sample["global"])}
        for s, snap in sample["seats"].items():
            mapping[snap["faction"]] = pickle.loads(snap["observation"])
        return normalize_state(mapping, Origin.ENGINE)

    inert = PolicyAgent(INERT_ID)
    inert.setup({"seat": other_seat, "faction": other_faction, "cost_data": inputs.cost})
    policy = tb.BatchPolicy(move_costs)
    t9 = tc.T9Capture()
    v3 = cap.V3CompactCapture((sc.V3_ID,))
    timeline = cap.V3Timeline((INERT_ID, sc.V3_ID), move_costs)
    tee = tc.Tee(t9, v3, timeline)
    policies = {faction: sc.V3_ID, other_faction: INERT_ID}
    players = [{"seat": 1, "faction": 0, "role": 1}, {"seat": 11, "faction": 1, "role": 1}]
    views = [view(s) for s in samples[:1]]
    tee.setup(views[0], players, policies)
    observer = 0.0
    previous = view(samples[0])
    for i, sample in enumerate(samples):
        before = previous
        after = view(samples[i + 1]) if i + 1 < len(samples) else None
        if after is None:
            final = windows["final"]
            mapping = {-1: pickle.loads(final["global"])}
            for s, snap in final["seats"].items():
                mapping[snap["faction"]] = pickle.loads(snap["observation"])
            after = normalize_state(mapping, Origin.ENGINE)
        decisions = []
        for player in players:
            snap = sample["seats"].get(player["seat"]) or sample["seats"].get(str(player["seat"]))
            raw = pickle.loads(snap["observation"])
            if player["faction"] == faction:
                memory = pickle.loads(snap["memory"])
                memory = AddonMemory(memory.baseline if isinstance(memory, AddonMemory) else memory)
                decision = policy.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory)
                actions, trace, name = list(decision.actions), decision.trace, sc.V3_ID
            else:
                actions = inert.step(raw)
                trace, name, memory = inert.last_trace, INERT_ID, inert.memory
            decisions.append({"seat": player["seat"], "faction": player["faction"], "policy": name,
                              "observation": raw, "memory": memory, "actions": actions,
                              "submitted": copy.deepcopy(actions), "trace": trace})
        tick = time.perf_counter()
        tee.step(i, before, after, decisions)
        observer += time.perf_counter() - tick
        previous = after
    tick = time.perf_counter()
    timeline_compact, pickled = timeline.files()
    files_seconds = time.perf_counter() - tick
    fake = dict(record, seats=[dict(s, policy=sc.V3_ID if s["faction"] == faction else INERT_ID)
                               for s in record["seats"]], session_close={"integrity": {"ok": True}})
    game = {"game_id": "timing", "scenario_id": scenario, "condition": "C3", "red": INERT_ID, "blue": sc.V3_ID,
            "screen_position": 7}
    tick = time.perf_counter()
    tl.analyze(game, "timing", fake, json.loads(t9.file()), json.loads(v3.files()[0]), json.loads(timeline_compact),
               pickle.loads(pickled), move_costs)
    analysis = time.perf_counter() - tick
    per_step = observer / len(samples)
    factor = 2 * H2H_OPERATORS / DIAGNOSED_OPERATORS
    projected_observer = observer * factor
    projected_analysis = analysis * factor
    projected_game = H2H_WALL_SECONDS + projected_observer + files_seconds * factor
    conservative_game = H2H_WALL_SECONDS + max(observer, SPRINT10_MAX_IN_GAME_OBSERVER_SECONDS) * factor
    payload = {"schema": "miaosuan-s12-timing/1", "capture": stem, "decisions": len(samples),
               "observer_seconds": round(observer, 1), "observer_ms_per_step": round(1000 * per_step, 2),
               "files_seconds": round(files_seconds, 1), "analysis_seconds": round(analysis, 1),
               "windows_bytes": len(pickled), "timeline_compact_bytes": len(timeline_compact),
               "projection": {"factor": round(factor, 3),
                              "basis": "two reconstructed policy seats instead of one, and 89 operators instead of 54",
                              "h2h_wall_without_timeline_seconds": H2H_WALL_SECONDS,
                              "game_seconds": round(projected_game, 1),
                              "game_process_seconds_with_analysis": round(projected_game + projected_analysis, 1),
                              "conservative_game_seconds": round(conservative_game, 1),
                              "conservative_basis": "Sprint 10's largest in-game full-step observer time "
                                                    f"({SPRINT10_MAX_IN_GAME_OBSERVER_SECONDS} s) instead of this "
                                                    "offline measurement, with the same factor",
                              "conservative_process_seconds_with_analysis": round(conservative_game + projected_analysis, 1),
                              "safe_if": "conservative game below half the wall cap and the game process below the "
                                         "process timeout minus 900 s",
                              "wall_cap_seconds": 1800, "process_timeout_seconds": 2100}}
    TIMING.parent.mkdir(parents=True, exist_ok=True)
    TIMING.write_text(sc.dump(payload), encoding="utf-8", newline="\n")
    print(json.dumps(payload, indent=1))
    return 0 if conservative_game < 900 and conservative_game + projected_analysis < 1200 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    real = sub.add_parser("real")
    real.add_argument("--check", action="store_true")
    real.set_defaults(func=cmd_real)
    timing = sub.add_parser("timing")
    timing.set_defaults(func=cmd_timing)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
