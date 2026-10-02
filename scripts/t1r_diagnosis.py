"""T1-r diagnosis: compare two captured diagnostic games of one scenario, baseline-v2 against the split candidate.

    PYTHON scripts/t1r_diagnosis.py --work DIR --baseline GAME --candidate GAME [--expect-totals B C] [--out PATH]

DIAGNOSTIC (docs/T1R_DIAGNOSIS.md): no decision rule depends on it. Reads the two games' records and step captures
(``residual516.Capture`` with a full-state snapshot every step), checks the premise (the records reproduce the Sprint 1
scores) and lesson L4's cross-checks (batch counts equal the record's action counts; the final flags reproduce the
occupy score), then computes the pre-declared observables of hypotheses H1 to H6, the per-window attribution of the
occupy score and the first behavioural divergence by engine time. The public output holds counts, scores, step indices
and objective labels (by value) only; never a unit identifier or a hex number.
"""

from __future__ import annotations

import argparse
import collections
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402

MOVE, SHOOT, OCCUPY, GUIDED = 1, 2, 5, 9
DEPLOY_SPLIT_TYPES = (314, 14)
STACK_LIMIT = 4
WINDOW = 200
COMPLETION_HORIZON = 20  # steps a unit may still be travelling after its last snapshot before "not completed"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unpickle(value: Any) -> Any:
    return pickle.loads(value) if isinstance(value, (bytes, bytearray)) else value


class Game:
    """One captured game: record, compact capture and the per-step snapshots keyed by decision index."""

    def __init__(self, record: Mapping[str, Any], capture: Mapping[str, Any], windows: Mapping[str, Any]) -> None:
        self.record, self.capture = record, capture
        self.steps: List[Mapping[str, Any]] = list(capture["steps"])
        self.snapshots: Dict[int, Mapping[str, Any]] = {s["k"]: s for s in windows["samples"]}
        for event in windows.get("events", ()):
            for s in event["window"]:
                self.snapshots.setdefault(s["k"], s)
        seat = next(s for s in record["seats"] if s["policy"] != INERT_ID)
        self.seat, self.faction, self.policy = seat["seat"], seat["faction"], seat["policy"]
        self.colour = "red" if self.faction == 0 else "blue"
        self.other = "blue" if self.colour == "red" else "red"

    @classmethod
    def read(cls, work: Path, game_id: str) -> "Game":
        return cls(load(work / "games" / f"{game_id}.json"), load(work / "capture" / f"{game_id}.capture.json"),
                   pickle.loads((work / "capture" / f"{game_id}.windows.pkl").read_bytes()))

    def state(self, k: int) -> Optional[Mapping[str, Any]]:
        snap = self.snapshots.get(k)
        return unpickle(snap["global"]) if snap else None

    def observation(self, k: int) -> Optional[Mapping[str, Any]]:
        snap = self.snapshots.get(k)
        if not snap:
            return None
        entry = snap["seats"].get(self.seat) or snap["seats"].get(str(self.seat))
        return unpickle(entry["observation"]) if entry else None

    def own_actions(self, k: int) -> List[Mapping[str, Any]]:
        return [i["action"] for i in self.steps[k]["batch"] if i["seat"] == self.seat]


# ----------------------------------------------------------------------------------------------
# per-state quantities (pure functions over plain dicts)


def own_units(state: Mapping[str, Any], faction: int) -> List[Mapping[str, Any]]:
    return [u for u in (state.get("operators") or []) if u.get("color") == faction]


def ground(units: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [u for u in units if not u.get("on_board")]


def occupancy(units: Sequence[Mapping[str, Any]]) -> Dict[int, int]:
    """hex -> blood sum of the ground units standing in it (what splitting alone leaves unchanged)."""
    out: Dict[int, int] = collections.Counter()
    for u in ground(units):
        out[u["cur_hex"]] += int(u.get("blood") or 0)
    return dict(out)


def stack_counts(units: Sequence[Mapping[str, Any]]) -> Dict[int, int]:
    return dict(collections.Counter(u["cur_hex"] for u in ground(units)))


def objectives(state: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Objectives sorted by value, descending, labelled by value (never by hex in the public output)."""
    cities = sorted((dict(c) for c in state.get("cities") or []), key=lambda c: (-int(c["value"]), c["coord"]))
    for city in cities:
        city["label"] = f"objective_value_{city['value']}"
    return cities


def idle_reason(unit: Mapping[str, Any], valid: Mapping[Any, Any], unheld_hexes: Sequence[int]) -> str:
    """Why a unit without an action this step had none, read from its observed fields (the policy's hierarchy)."""
    listed = valid.get(unit["obj_id"]) or valid.get(str(unit["obj_id"])) or {}
    kinds = {int(k) for k in listed}
    if unit.get("on_board"):
        return "passenger"
    if unit.get("move_path"):
        return "already moving"
    if kinds & {SHOOT, GUIDED}:
        return "shoot listed, not emitted"
    if OCCUPY in kinds:
        return "occupy listed, not emitted"
    if unit["cur_hex"] in unheld_hexes:
        return "standing on an unheld objective, occupy not listed"
    if MOVE not in kinds:
        return "move not listed"
    if not unheld_hexes:
        return "no objective outside own control"
    return "move listed, none emitted"


def step_metrics(game: Game, k: int) -> Optional[Dict[str, Any]]:
    state = game.state(k)
    if state is None:
        return None
    units = own_units(state, game.faction)
    cities = objectives(state)
    unheld = [c["coord"] for c in cities if c["flag"] != game.faction]
    valid = (game.observation(k) or {}).get("valid_actions") or {}
    actions = game.own_actions(k)
    acted = {a.get("obj_id") for a in actions}
    moves = [(a["obj_id"], a["move_path"][-1]) for a in actions if a.get("type") == MOVE and a.get("move_path")]
    by_id = {u["obj_id"]: u for u in units}
    occupies = [(a["obj_id"], by_id[a["obj_id"]]["cur_hex"]) for a in actions if a.get("type") == OCCUPY and a["obj_id"] in by_id]
    idle = [idle_reason(u, valid, unheld) for u in units if u["obj_id"] not in acted]
    stacks = stack_counts(units)
    return {"k": k, "cur_step": state["time"]["cur_step"], "stage": state["time"]["stage"],
            "occupancy": occupancy(units), "hexes": sorted(stacks), "stacks": stacks, "max_stack": max(stacks.values(), default=0),
            "blood_sum": sum(int(u.get("blood") or 0) for u in units), "units": len(units),
            "passengers": sum(1 for u in units if u.get("on_board") or u.get("car") is not None),
            "flags": {c["label"]: c["flag"] for c in cities}, "unheld_hexes": unheld,
            "standing_on_unheld": sum(1 for u in ground(units) if u["cur_hex"] in unheld),
            "keeping": sum(1 for u in units if u.get("keep")),
            "moves": moves, "occupies": occupies,
            "shots": sum(1 for a in actions if a.get("type") in (SHOOT, GUIDED)),
            "idle_reasons": dict(collections.Counter(idle))}


# ----------------------------------------------------------------------------------------------
# game-level analysis


def timeline(game: Game) -> List[Dict[str, Any]]:
    out = []
    for k in range(len(game.steps)):
        m = step_metrics(game, k)
        if m is not None:
            out.append(m)
    return out


def flag_flips(tl: Sequence[Mapping[str, Any]], faction: int) -> Dict[str, Optional[int]]:
    """First snapshot step at which each objective is held by the policy's faction (None: never)."""
    flips: Dict[str, Optional[int]] = {}
    labels = sorted({label for m in tl for label in m["flags"]})
    for label in labels:
        flips[label] = next((m["k"] for m in tl if m["flags"].get(label) == faction), None)
    return flips


def move_completion(game: Game, tl: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Of the moves issued, how many units later stand on their destination (before their next move)."""
    issued: List[Tuple[int, int, int]] = [(k, a["obj_id"], a["move_path"][-1]) for k in range(len(game.steps))
                                          for a in game.own_actions(k) if a.get("type") == MOVE and a.get("move_path")]
    completed = not_completed = unknown = 0
    for k, unit, dest in issued:
        later_moves = [kk for kk, u, _ in issued if u == unit and kk > k]
        horizon = min(later_moves) if later_moves else len(game.steps)
        reached = False
        checked = False
        for kk in range(k + 1, min(horizon + COMPLETION_HORIZON, len(game.steps))):
            state = game.state(kk)
            if state is None:
                continue
            checked = True
            u = next((x for x in own_units(state, game.faction) if x["obj_id"] == unit), None)
            if u is not None and u["cur_hex"] == dest:
                reached = True
                break
        if reached:
            completed += 1
        elif checked and horizon + COMPLETION_HORIZON <= len(game.steps):
            not_completed += 1
        else:
            unknown += 1
    return {"issued": len(issued), "completed": completed, "not_completed": not_completed, "undetermined": unknown}


def fresh_feedback(steps: Sequence[Mapping[str, Any]]) -> List[List[Mapping[str, Any]]]:
    """Feedback entries new in each step (the engine re-reports earlier entries while cur_step stands still)."""
    out: List[List[Mapping[str, Any]]] = []
    previous: List[Mapping[str, Any]] = []
    clock = None
    for step in steps:
        entries = list(step["feedback"])
        repeated = step.get("cur_step") == clock and entries[:len(previous)] == previous
        out.append(entries[len(previous):] if repeated else entries)
        previous, clock = entries, step.get("cur_step")
    return out


def summarize(game: Game) -> Dict[str, Any]:
    tl = timeline(game)
    if not tl:
        raise SystemExit(f"REFUSED: {game.record['game_id']} has no state snapshots")
    play = [m for m in tl if m["stage"] == 2]
    record_seat = next(s for s in game.record["seats"] if s["seat"] == game.seat)
    counts = record_seat["actions_by_type"]
    every = [a for k in range(len(game.steps)) for a in game.own_actions(k)]
    batch_moves = sum(1 for a in every if a.get("type") == MOVE)
    batch_occupies = sum(1 for a in every if a.get("type") == OCCUPY)
    batch_splits = sum(1 for a in every if a.get("type") in DEPLOY_SPLIT_TYPES)
    for label, batch, recorded in (("moves", batch_moves, counts.get(str(MOVE), 0)),
                                   ("occupations", batch_occupies, counts.get(str(OCCUPY), 0)),
                                   ("deployment splits", batch_splits, counts.get("314", 0))):
        if batch != recorded:
            raise SystemExit(f"REFUSED: {game.record['game_id']}: {batch} {label} in the capture but the record counts "
                             f"{recorded}; the capture is not being read correctly")
    final = tl[-1]
    last_state = game.state(final["k"])
    cities = objectives(last_state)
    held_value = sum(int(c["value"]) for c in cities if c["flag"] == game.faction)
    scores = game.record["final_scores"]
    occupy_score = scores[f"{game.colour}_occupy"]
    value_blood = sum(int(u.get("value") or 0) * int(u.get("blood") or 0) for u in own_units(last_state, game.faction))
    errors = collections.Counter()
    for k, news in enumerate(fresh_feedback(game.steps)):
        for e in news:
            if isinstance(e.get("error"), Mapping) and (e.get("message") or {}).get("actor") == game.seat:
                errors[f"{e['error'].get('code')}/{(e.get('message') or {}).get('type')}"] += 1
    idle = collections.Counter()
    idle_while_unheld = collections.Counter()
    for m in play:
        for reason, n in m["idle_reasons"].items():
            idle[reason] += n
            if m["unheld_hexes"]:
                idle_while_unheld[reason] += n
    windows = {}
    for m in play:
        w = (m["cur_step"] // WINDOW) * WINDOW
        windows[str(w)] = sum(int(c["value"]) for c in cities if m["flags"].get(c["label"]) == game.faction)
    return {
        "game": game.record["game_id"], "policy": game.policy, "colour": game.colour,
        "snapshots": len(tl), "play_snapshots": len(play), "steps": len(game.steps),
        "deployment_steps": sum(1 for s in game.steps if s.get("stage") == 1),
        "first_play_k": play[0]["k"] if play else None, "final_cur_step": final["cur_step"],
        "scores": {k: v for k, v in scores.items() if k.startswith(game.colour)},
        "units_at_first_play": play[0]["units"] if play else None, "units_at_end": final["units"],
        "blood_sum_min_max": [min(m["blood_sum"] for m in tl), max(m["blood_sum"] for m in tl)],
        "shots": sum(m["shots"] for m in tl), "passenger_unit_steps": sum(m["passengers"] for m in tl),
        "boarded_or_landed_events": sum(len(s.get("boarded", [])) + len(s.get("landed", [])) for s in game.steps),
        "max_stack_over_game": max(m["max_stack"] for m in tl),
        "unit_steps_at_stack_limit": sum(n for m in play for n in m["stacks"].values() if n >= STACK_LIMIT),
        "steps_with_a_full_hex": sum(1 for m in play if m["max_stack"] >= STACK_LIMIT),
        "moves": move_completion(game, tl), "moves_issued": batch_moves, "occupations_issued": batch_occupies,
        "deployment_splits_issued": batch_splits,
        "occupation_steps": [m["k"] for m in play if m["occupies"]],
        "unit_steps_standing_on_unheld_objective": sum(m["standing_on_unheld"] for m in play),
        "unit_steps_standing_on_unheld_without_occupation": sum(
            m["standing_on_unheld"] - len(m["occupies"]) for m in play if m["standing_on_unheld"] > len(m["occupies"])),
        "keeping_unit_steps": sum(m["keeping"] for m in play),
        "idle_reasons_play": dict(sorted(idle.items())), "idle_reasons_while_an_objective_unheld": dict(sorted(idle_while_unheld.items())),
        "flag_flip_k": flag_flips(tl, game.faction), "objective_values": [int(c["value"]) for c in cities],
        "held_value_at_end": held_value, "occupy_score": occupy_score, "value_times_blood_at_end": value_blood,
        "remain_score": scores[f"{game.colour}_remain"],
        "fresh_feedback_errors_by_code_and_type": dict(sorted(errors.items())),
        "occupy_points_held_by_window": windows,
    }


def first_divergence(base: Game, cand: Game) -> Dict[str, Any]:
    """Align by engine time; the first play step whose blood-weighted occupancy or flags differ."""
    def by_time(game: Game) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        for m in timeline(game):
            if m["stage"] == 2:
                out.setdefault(m["cur_step"], m)  # the first decision at that engine time
        return out
    a, b = by_time(base), by_time(cand)
    common = sorted(set(a) & set(b))
    for t in common:
        ma, mb = a[t], b[t]
        reasons = []
        if ma["occupancy"] != mb["occupancy"]:
            moved = {h for h in set(ma["occupancy"]) | set(mb["occupancy"]) if ma["occupancy"].get(h) != mb["occupancy"].get(h)}
            reasons.append(f"blood-weighted occupancy differs in {len(moved)} hexes")
        if ma["flags"] != mb["flags"]:
            reasons.append("city flags differ")
        if reasons:
            prior = {k: (ka, kb) for k, ka, kb in [(tt, a[tt]["k"], b[tt]["k"]) for tt in common if tt < t][-3:]}
            return {"cur_step": t, "k_baseline": ma["k"], "k_candidate": mb["k"], "reasons": reasons,
                    "baseline_moves_issued_up_to_here": sum(len(a[tt]["moves"]) for tt in common if tt <= t),
                    "candidate_moves_issued_up_to_here": sum(len(b[tt]["moves"]) for tt in common if tt <= t),
                    "destinations_differ_at_first_play_step": sorted(set(d for _, d in a[common[0]]["moves"])) !=
                    sorted(set(d for _, d in b[common[0]]["moves"])),
                    "preceding_aligned_steps": {str(k): v for k, v in prior.items()}}
    return {"cur_step": None, "reasons": [], "aligned_play_steps": len(common)}


def analyse(work: Path, baseline_id: str, candidate_id: str, expect: Optional[Tuple[int, int]]) -> Dict[str, Any]:
    base, cand = Game.read(work, baseline_id), Game.read(work, candidate_id)
    premise = {"baseline_total": base.record["final_scores"][f"{base.colour}_total"],
               "candidate_total": cand.record["final_scores"][f"{cand.colour}_total"],
               "both_completed": base.record["status"] == "COMPLETED" and cand.record["status"] == "COMPLETED"}
    if expect is not None:
        premise["expected"] = list(expect)
        premise["reproduced"] = (premise["baseline_total"], premise["candidate_total"]) == expect
        if not premise["reproduced"]:
            return {"schema": "miaosuan-t1r-diagnosis/1", "premise": premise, "stopped": "the records do not reproduce the "
                    "expected totals; determinism is part of the premise"}
    sb, sc = summarize(base), summarize(cand)
    for s in (sb, sc):
        if s["held_value_at_end"] > s["occupy_score"]:
            raise SystemExit(f"REFUSED: {s['game']}: flags at the last snapshot hold {s['held_value_at_end']} but the "
                             f"occupy score is {s['occupy_score']}; the capture is not being read correctly")
        s["flags_at_last_snapshot_reproduce_occupy_score"] = s["held_value_at_end"] == s["occupy_score"]
    diff_components = {part: sc["scores"][f"{cand.colour}_{part}"] - sb["scores"][f"{base.colour}_{part}"]
                       for part in ("occupy", "attack", "remain")}
    total_diff = sc["scores"][f"{cand.colour}_total"] - sb["scores"][f"{base.colour}_total"]
    windows = {w: sc["occupy_points_held_by_window"].get(w, 0) - sb["occupy_points_held_by_window"].get(w, 0)
               for w in sorted(set(sb["occupy_points_held_by_window"]) | set(sc["occupy_points_held_by_window"]), key=int)}
    verdicts = {
        "H1": ("REFUTED" if sb["blood_sum_min_max"][0] == sb["blood_sum_min_max"][1] == sc["blood_sum_min_max"][0] ==
               sc["blood_sum_min_max"][1] and sb["shots"] == sc["shots"] == 0 and
               sc["remain_score"] == sc["value_times_blood_at_end"] else "SUPPORTED"),
        "H4": ("REFUTED" if sb["passenger_unit_steps"] == sc["passenger_unit_steps"] == 0 and
               sb["boarded_or_landed_events"] == sc["boarded_or_landed_events"] == 0 else "SUPPORTED"),
        "H6": ("REFUTED" if all(s["remain_score"] == s["value_times_blood_at_end"] and s["held_value_at_end"] == s["occupy_score"]
                                for s in (sb, sc)) else "SUPPORTED"),
    }
    return {"schema": "miaosuan-t1r-diagnosis/1", "status": "DIAGNOSTIC", "premise": premise,
            "baseline": sb, "candidate": sc,
            "difference": {"total": total_diff, "components": diff_components,
                           "components_sum_equals_total": sum(diff_components.values()) == total_diff,
                           "occupy_points_held_by_window_candidate_minus_baseline": windows},
            "first_divergence": first_divergence(base, cand),
            "mechanical_verdicts": verdicts}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--expect-totals", type=int, nargs=2, metavar=("BASELINE", "CANDIDATE"))
    parser.add_argument("--out", type=Path, help="write the public analysis here (JSON)")
    args = parser.parse_args()
    result = analyse(args.work, args.baseline, args.candidate, tuple(args.expect_totals) if args.expect_totals else None)
    text = json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
