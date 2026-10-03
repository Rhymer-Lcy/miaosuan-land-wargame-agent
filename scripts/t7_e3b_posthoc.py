"""POST HOC descriptions of the E3b configuration search (``t7-e3b-search-1``, ``docs/T7_E3B_SEARCH.md``).

    python scripts/t7_e3b_posthoc.py [--check]

Written after the registered outputs (validation, search, cross-check, decision); it changes none of them, no rule and
no disposition. Two descriptions:

1. instrument control: in every full capture, every ``baseline-v2`` move or shot to an own ground unit the search's
   rows contain, with the length of the undisturbed idle run immediately before it (the D2 measure without its 75-step
   threshold), so that D2 = 0 is shown to be a measured absence rather than a blind instrument;
2. the strongest configuration (the C-h0 witnesses): in their game, per seat, the play decisions at which the
   reconstructed ``baseline-v2`` differs from the recorded ``baseline-v0`` before the witness's later command, the
   ``cur_step`` of the game's first judge record, the other unit first ordered before the witness and whether the
   opposing seat listed it between its order and the witness's ``s0`` (the facts F2 would read).

Public output ``evaluation/t7-e3b-search-1/posthoc.json`` (aggregates, no identifiers).
"""

from __future__ import annotations

import argparse
import collections
import gzip
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

_spec = importlib.util.spec_from_file_location("t7_e3b_search", REPO_ROOT / "scripts" / "t7_e3b_search.py")
search = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(search)
te = search.te

OUT = search.OUT / "posthoc.json"
PRIVATE = search.PRIVATE / "search-private.json"


def instrument() -> Dict[str, Any]:
    out = {}
    for spec in search.FULL:
        seat = search.Seat(spec["folder"], spec["game"], spec["seat"])
        decisions = seat.play_decisions
        idle, types, stationary = [], collections.Counter(), 0
        for i1, d in enumerate(decisions):
            for unit, action in d.actions.items():
                here = d.units.get(unit)
                if action.get("type") not in (te.MOVE, te.SHOOT) or here is None or here.type not in te.GROUND:
                    continue
                j = i1
                while j > 0:
                    before = decisions[j - 1]
                    if decisions[j].cur_step != before.cur_step + 1 or unit in before.actions:
                        break
                    if te.state_violation(here, before.units.get(unit), before) is not None:
                        break
                    j -= 1
                idle.append(d.cur_step - decisions[j].cur_step)
                types[str(action.get("type"))] += 1
                stationary += te.state_violation(here, here, d) is None
        out[spec["id"]] = {"commands_to_ground_units": len(idle), "by_type": dict(sorted(types.items())),
                           "stationary_at_the_command": stationary, "longest_idle_run_before_a_command": max(idle, default=None),
                           "commands_after_an_idle_run_of_at_least_75": sum(1 for v in idle if v >= te.TRANSITION)}
    return out


def strongest() -> Dict[str, Any]:
    private = json.loads(PRIVATE.read_text(encoding="utf-8"))
    rows = [r for r in private["datasets"]["C-h0"]["episodes"] if r["class"] == te.W]
    games = sorted({r["game"] for r in rows})
    frozen = json.loads(search.INPUTS.read_text(encoding="utf-8"))
    corpus = next(ds for ds in frozen["datasets"] if ds["id"] == "C-h0")
    out: Dict[str, Any] = {"witness_games": len(games), "witness_units": len({(r["game"], r["seat"], r["unit"]) for r in rows})}
    for game in games:
        entry = next(e for e in corpus["files"] if Path(e["path"]).name.startswith(game))
        with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            lines = [json.loads(x) for x in handle]
        costs = search.costs_for(header["scenario_id"], header["map_id"])
        witness = [r for r in rows if r["game"] == game]
        first = min(witness, key=lambda r: r["k0"])
        by_seat = collections.defaultdict(list)
        for row in lines:
            by_seat[row["seat"]].append(row)
        differ: Dict[str, Any] = {}
        first_judge = None
        listed_other: Dict[int, set] = collections.defaultdict(set)
        for seat_no, seat_rows in sorted(by_seat.items()):
            faction = seat_rows[0]["faction"]
            v0, v2 = search.BaselinePolicy(costs), search.ShootReservationPolicy(costs)
            m0, m2 = search.Memory(), search.Memory()
            ks = []
            for row in sorted(seat_rows, key=lambda r: r["step"]):
                raw = search.typed_json.decode(row["observation"])
                obs = search.Observation.from_raw(raw, search.Origin.ENGINE)
                d0 = v0.decide(obs, seat_no, faction, m0)
                m0 = d0.memory
                d2 = v2.decide(search.Observation.from_raw(raw, search.Origin.ENGINE), seat_no, faction, m2)
                m2 = d2.memory
                time = raw.get("time") or {}
                if time.get("stage") == search.PLAY and search.plain(d2.actions) != search.plain(d0.actions):
                    ks.append(row["step"])
                if raw.get("judge_info") and (first_judge is None or time.get("cur_step", 0) < first_judge):
                    first_judge = time.get("cur_step")
                listed_other[seat_no].update((row["step"], u.get("obj_id")) for u in raw.get("operators") or ()
                                             if u.get("color") != faction)
            mine = seat_no == first["seat"]
            differ["witness seat" if mine else "opposing seat"] = {
                "play_decisions_where_baseline_v2_differs": len(ks),
                "before_the_first_witness_order": sum(1 for k in ks if k < first["k0"]),
                "between_the_first_witness_order_and_its_command": sum(1 for k in ks if first["k0"] <= k < first["k1"]),
                "first_difference_decision": min(ks) if ks else None}
        seat_eps = [r for r in private["datasets"]["C-h0"]["episodes"] if r["game"] == game and r["seat"] == first["seat"]]
        first_orders = {}
        for r in seat_eps:
            if not r["previous"]:
                first_orders[r["unit"]] = r["k0"]
        opponent = next(s for s in by_seat if s != first["seat"])
        earlier = {u: k for u, k in first_orders.items() if u != first["unit"] and k < first["k0"]}
        seen = sum(1 for u, k in earlier.items() if any((j, u) in listed_other[opponent] for j in range(k + 1, first["k0"] + 1)))
        out[game.split(".")[0]] = {
            "reconstruction_against_recorded_baseline_v0": differ, "first_judge_record_cur_step": first_judge,
            "first_witness": {"k0": first["k0"], "s0": first["s0"], "k1": first["k1"], "s1": first["s1"], "d": first["d"],
                              "later_type": first["later_action"]["type"]},
            "other_units_first_ordered_before_k0": len(earlier),
            "of_which_listed_by_the_opposing_seat_before_s0": seen,
            "F2_facts": {"first_judge_before_s0": first_judge is not None and first_judge < first["s0"],
                         "earlier_unit_seen_by_opponent": seen > 0, "opponent": "baseline-v0 (active)"}}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    search.verified_inputs()
    payload = {"schema": "miaosuan-t7-e3b-posthoc/1", "study_id": search.STUDY,
               "status": "POST HOC: written after the registered outputs; changes none of them, no rule and no disposition",
               "instrument_control": instrument(), "strongest_configuration": strongest()}
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if args.check:
        same = OUT.read_text(encoding="utf-8") == text
        print("posthoc identical" if same else "MISMATCH")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
