"""Registered endpoints of the T7 mechanism probe (rules: ``evaluation/t7_probe.py``; data: ``t7_probe_metrics``).

Each function applies one registered rule to the compact series of a game and returns the verdict with its full
evidence. Nothing here reads the engine; nothing here chooses an action.
"""

from __future__ import annotations

import bisect
import collections
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from . import t7_probe as tp
from . import t7_visibility as tv
from .t7_probe_metrics import (CHANGE_STATE, CONCEAL, FAIL, GROUND, INCONCLUSIVE, MOVE, NOT_TESTED, PASS, REFUTED,
                               SHOOT, SUPPORTED, AnalysisRefused, Game, Order, Snap, U, _int, _num, is_order, matches,
                               serialised, submitted)

WINDOW = tp.COMPLETION_WINDOW
TRANSIENT = tp.TRANSIENT


def by_cur_step(snaps: Mapping[int, Snap]) -> Dict[int, Snap]:
    """The play-stage snapshots indexed by cur_step (in play the clock advances one step per decision)."""
    out: Dict[int, Snap] = {}
    for k in sorted(snaps):
        snap = snaps[k]
        if snap.stage == 2:
            out[snap.cur_step] = snap
    return out


def last_cur_step(snaps: Mapping[int, Snap]) -> int:
    return max(s.cur_step for s in snaps.values())


# ----------------------------------------------------------------------------------------------
# E1 and S1


def echo_codes(game: Game, seat: int, k: int, j: int, fresh: Mapping[int, List[Mapping[str, Any]]]) -> List[Any]:
    """Error codes of the fresh feedback entries that echo the seat's j-th action of decision k: matched against the
    pre-execution copy or against the action as serialised after the step (the engine may rewrite it in place)."""
    copy_ = submitted(game, seat, k)[j]
    after = serialised(game, seat, k)
    late = after[j] if j < len(after) else copy_
    return [_code(e) for e in fresh.get(k, ()) if matches(e, copy_) or matches(e, late)]


def order_feedback(game: Game, order_list: Sequence[Order], fresh: Mapping[int, List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    out = []
    for o in order_list:
        codes = echo_codes(game, o.seat, o.k, o.j, fresh)
        out.append({"k": o.k, "cur_step": o.cur_step, "unit": o.unit, "matching": len(codes), "codes": codes})
    return out


def _code(entry: Mapping[str, Any]) -> Any:
    error = entry.get("error")
    if not error:
        return None
    code = error.get("code") if isinstance(error, Mapping) else None
    return code if code is not None else "unspecified"


def e1(feedback: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    if not feedback:
        return {"verdict": NOT_TESTED, "orders": 0}
    errors = [f for f in feedback if any(c is not None for c in f["codes"])]
    odd = [f for f in feedback if f["matching"] != 1]
    verdict = REFUTED if errors else INCONCLUSIVE if odd else SUPPORTED
    return {"verdict": verdict, "orders": len(feedback), "echoed_without_error": sum(
        1 for f in feedback if f["matching"] == 1 and f["codes"] == [None]), "with_error_code": len(errors),
        "no_or_several_echoes": len(odd), "error_codes": sorted({str(c) for f in errors for c in f["codes"] if c})}


def s1(feedback: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    errors = [f for f in feedback if any(c is not None for c in f["codes"])]
    return {"verdict": FAIL if errors else PASS, "orders": len(feedback), "orders_with_error_code": len(errors)}


# ----------------------------------------------------------------------------------------------
# E2: outcome of each order (channel A forward scan), and its independent reconstruction (channel B)


def _judged(game: Game, k: int, unit: int) -> bool:
    return any(r.get("att_obj_id") == unit for r in game.steps.get(k, {}).get("judge_new") or ())


def _accepted_other(game: Game, seat: int, k: int, unit: int, fresh: Mapping[int, List[Mapping[str, Any]]]) -> bool:
    """A non-order action of the seat for the unit at decision k, matched by a fresh feedback entry without error."""
    for j, action in enumerate(submitted(game, seat, k)):
        if action.get("obj_id") != unit or is_order(action):
            continue
        codes = echo_codes(game, seat, k, j, fresh)
        if codes and all(c is None for c in codes):
            return True
    return False


def interrupter(game: Game, snaps_k: Mapping[int, Snap], o: Order, until_k: int,
                fresh: Mapping[int, List[Mapping[str, Any]]]) -> Optional[Tuple[int, str]]:
    """The first documented interrupter of an order's transition seen at a snapshot o.k + 1 .. until_k: in the step
    that led to the snapshot (the unit fired, or a baseline-v2 action for it was accepted), or in the snapshot itself
    (the unit gone or boarded, suppressed, or sharing its hex with an enemy unit)."""
    for k in range(o.k + 1, until_k + 1):
        step = k - 1
        if _judged(game, step, o.unit):
            return k, "fired"
        if _accepted_other(game, o.seat, step, o.unit, fresh):
            return k, "accepted baseline-v2 action"
        snap = snaps_k.get(k)
        if snap is None:
            continue
        unit = snap.units.get(o.unit)
        if unit is None or not unit.on_map:
            return k, "gone or boarded"
        if (_num(unit.keep) or 0) > 0:
            return k, "suppressed"
        if any(u.hex == unit.hex and u.color != unit.color and u.on_map for u in snap.units.values()):
            return k, "same-hex engagement"
    return None


def outcomes(game: Game, snaps: Mapping[int, Snap], order_list: Sequence[Order],
             fresh: Mapping[int, List[Mapping[str, Any]]]) -> List[Dict[str, Any]]:
    """Channel A: per order, a forward scan over the all-seeing rows."""
    by_step = by_cur_step(snaps)
    end = last_cur_step(snaps)
    k_of = {s.cur_step: k for k, s in snaps.items() if s.stage == 2}
    out = []
    for o in order_list:
        s0 = o.cur_step
        trajectory, timer_start, first4, completion = [], None, None, None
        for s in range(s0 + 1, s0 + WINDOW + 1):
            snap = by_step.get(s)
            if snap is None:
                break
            unit = snap.units.get(o.unit)
            if unit is None:
                trajectory.append([s, None, None])
                continue
            timer = unit.timers[0]
            trajectory.append([s, timer, unit.move_state])
            if timer_start is None and (_num(timer) or 0) > 0:
                timer_start = s
            if first4 is None and unit.move_state == CONCEAL:
                first4 = s
            if unit.concealed:
                completion = s
                break
        timer_ok = any(s0 + d == timer_start for d in tp.TIMER_START)
        record = {"k": o.k, "cur_step": s0, "unit": o.unit, "timer_start": timer_start, "first_move_state_4": first4,
                  "completion": completion, "d": None if completion is None else completion - s0,
                  "timer_ok": timer_ok, "interrupter": None, "later_concealed": None, "trajectory": trajectory}
        if completion is not None:
            record["outcome"] = "COMPLETED" if timer_ok else "COMPLETED_TIMER_ANOMALY"
        else:
            last_k = k_of.get(min(end, s0 + WINDOW), max(snaps))
            stop = interrupter(game, snaps, o, last_k, fresh)
            if stop is not None:
                record["outcome"], record["interrupter"] = "INTERRUPTED", {"k": stop[0], "what": stop[1]}
            elif end < s0 + WINDOW:
                record["outcome"] = "CENSORED"
            else:
                later = next((s for s in range(s0 + WINDOW + 1, end + 1)
                              if by_step.get(s) is not None and o.unit in by_step[s].units
                              and by_step[s].units[o.unit].concealed), None)
                record["later_concealed"] = later
                record["outcome"] = "LATE" if later is not None else "NOT_COMPLETED"
        out.append(record)
    return out


def reconstruct(snaps: Mapping[int, Snap], seat: int, order_list: Sequence[Order]) -> List[Tuple[Any, Any]]:
    """Channel B (I6): one pass over the seat's own view for every unit, then a bisect per order: (first positive
    timer within two steps, first concealed step within the window)."""
    positive: Dict[int, List[int]] = collections.defaultdict(list)
    concealed: Dict[int, List[int]] = collections.defaultdict(list)
    for k in sorted(snaps):
        snap = snaps[k]
        if snap.stage != 2 or seat not in snap.seats:
            continue
        for uid, unit in snap.seats[seat].own.items():
            timer = unit.timers[0]
            if isinstance(timer, (int, float)) and not isinstance(timer, bool) and timer > 0:
                positive[uid].append(snap.cur_step)
            if unit.move_state == CONCEAL and timer == 0:
                concealed[uid].append(snap.cur_step)
    out = []
    for o in order_list:
        def first(values: List[int], lo: int, hi: int) -> Optional[int]:
            i = bisect.bisect_left(values, lo)
            return values[i] if i < len(values) and values[i] <= hi else None
        out.append((first(positive[o.unit], o.cur_step + 1, o.cur_step + max(tp.TIMER_START)),
                    first(concealed[o.unit], o.cur_step + 1, o.cur_step + WINDOW)))
    return out


def check_reconstruction(records: Sequence[Mapping[str, Any]], other: Sequence[Tuple[Any, Any]]) -> Dict[str, Any]:
    for record, (timer_b, completion_b) in zip(records, other):
        timer_a = record["timer_start"] if record["timer_start"] is not None and record["timer_start"] <= \
            record["cur_step"] + max(tp.TIMER_START) else None
        if (timer_a, record["completion"]) != (timer_b, completion_b):
            raise AnalysisRefused(f"I6: order at decision {record['k']} unit {record['unit']}: channel A "
                                  f"{(timer_a, record['completion'])}, channel B {(timer_b, completion_b)}")
    return {"orders_compared": len(records)}


def e2(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    counts = collections.Counter(r["outcome"] for r in records)
    if not records:
        verdict = NOT_TESTED
    elif any(counts[x] for x in ("COMPLETED_TIMER_ANOMALY", "LATE", "NOT_COMPLETED")):
        verdict = REFUTED
    elif counts["INTERRUPTED"] or counts["CENSORED"]:
        verdict = INCONCLUSIVE
    else:
        verdict = SUPPORTED
    durations = sorted(r["d"] for r in records if r["d"] is not None)
    return {"verdict": verdict, "orders": len(records), "outcomes": dict(sorted(counts.items())),
            "durations": dict(sorted(collections.Counter(durations).items())),
            "timer_start_offsets": dict(sorted(collections.Counter(
                (r["timer_start"] - r["cur_step"]) if r["timer_start"] is not None else None for r in records).items(),
                key=lambda kv: str(kv[0]))),
            "first_move_state_4_offsets": dict(sorted(collections.Counter(
                (r["first_move_state_4"] - r["cur_step"]) if r["first_move_state_4"] is not None else None
                for r in records).items(), key=lambda kv: str(kv[0])))}


def primary(records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    reached = sum(1 for r in records if r["d"] is not None and r["d"] <= WINDOW)
    counts = collections.Counter(r["outcome"] for r in records)
    return {"orders": len(records), "reached_within_76": reached,
            "share": None if not records else reached / len(records),
            "censored": counts["CENSORED"], "interrupted": counts["INTERRUPTED"],
            "failed": counts["LATE"] + counts["NOT_COMPLETED"],
            "criterion_100_percent": bool(records) and reached == len(records)}


# ----------------------------------------------------------------------------------------------
# S2 and E3a


def _runs(flags: Sequence[Tuple[int, bool]]) -> List[Tuple[int, int]]:
    """Maximal runs of consecutive True flags: (first k, length)."""
    runs, start, length = [], None, 0
    for k, flag in flags:
        if flag:
            if start is None:
                start, length = k, 0
            length += 1
        elif start is not None:
            runs.append((start, length))
            start = None
    if start is not None:
        runs.append((start, length))
    return runs


def s2(snaps: Mapping[int, Snap], order_list: Sequence[Order]) -> Dict[str, Any]:
    first: Dict[int, Order] = {}
    for o in order_list:
        first.setdefault(o.unit, o)
    if not first:
        return {"verdict": NOT_TESTED, "units": 0}
    violations, transients = [], []
    for uid, o in sorted(first.items()):
        listed_move = MOVE in (snaps[o.k].units[uid].types or ())
        ffs, empty, immobile = [], [], []
        for k in sorted(snaps):
            if k < o.k:
                continue
            unit = snaps[k].units.get(uid)
            if unit is None or not unit.on_map:
                empty.append((k, False))
                immobile.append((k, False))
                continue
            if unit.flag_force_stop == 1:
                ffs.append(k)
            free = not unit.in_transition
            empty.append((k, free and not unit.types))
            immobile.append((k, listed_move and free and (_num(unit.keep) or 0) == 0 and unit.path == ()
                             and MOVE not in (unit.types or ())))
        if ffs:
            violations.append({"unit": uid, "what": "flag_force_stop", "first_k": ffs[0], "snapshots": len(ffs)})
        for name, flags in (("empty listing outside a transition", empty), ("move not listed", immobile)):
            for start, length in _runs(flags):
                item = {"unit": uid, "what": name, "first_k": start, "snapshots": length}
                (violations if length > TRANSIENT else transients).append(item)
    return {"verdict": FAIL if violations else PASS, "units": len(first), "violations": violations,
            "transients": transients}


def concealed_periods(snaps: Mapping[int, Snap], records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """For every completed order, the decisions from its completion while the unit stays concealed."""
    k_of = {s.cur_step: k for k, s in snaps.items() if s.stage == 2}
    out = []
    for r in records:
        if r["completion"] is None:
            continue
        start = k_of[r["completion"]]
        ks = []
        for k in sorted(snaps):
            if k < start:
                continue
            unit = snaps[k].units.get(r["unit"])
            if unit is None or not unit.concealed:
                break
            ks.append(k)
        out.append({"unit": r["unit"], "order_k": r["k"], "start_k": start, "ks": ks})
    return out


def e3a(snaps: Mapping[int, Snap], records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    periods = concealed_periods(snaps, records)
    if not periods:
        return {"verdict": NOT_TESTED, "completed_orders": 0}
    losses, transients, eligible = [], [], 0
    types_seen: collections.Counter = collections.Counter()
    states_seen: collections.Counter = collections.Counter()
    for p in periods:
        before = set(snaps[p["order_k"]].units[p["unit"]].types or ()) - {CHANGE_STATE}
        flags: Dict[int, List[Tuple[int, bool]]] = {t: [] for t in sorted(before)}
        for k in p["ks"]:
            unit = snaps[k].units[p["unit"]]
            judged = unit.on_map and not unit.in_transition and (_num(unit.keep) or 0) == 0
            if judged:
                eligible += 1
                types_seen[str(list(unit.types or ()))] += 1
                states_seen[str(list(unit.states)) if unit.states is not None else "action 6 not listed"] += 1
            for t in flags:
                flags[t].append((k, judged and t not in (unit.types or ())))
        for t, series_ in flags.items():
            for start, length in _runs(series_):
                item = {"unit": p["unit"], "type": t, "first_k": start, "snapshots": length}
                (losses if length > TRANSIENT else transients).append(item)
    verdict = NOT_TESTED if eligible == 0 else REFUTED if losses else SUPPORTED
    return {"verdict": verdict, "completed_orders": len(periods), "concealed_unit_snapshots": eligible,
            "losses": losses, "transients": transients, "listed_types_while_concealed": dict(sorted(types_seen.items())),
            "change_state_options_while_concealed": dict(sorted(states_seen.items())),
            "lost_types": sorted({x["type"] for x in losses})}


# ----------------------------------------------------------------------------------------------
# E3b and E5


def _executed(game: Game, snaps: Mapping[int, Snap], k: int, action: Mapping[str, Any]) -> Optional[bool]:
    unit_id = action.get("obj_id")
    if action.get("type") in (SHOOT, tp_guided()):
        return _judged(game, k, unit_id)
    nxt = snaps.get(k + 1)
    now = snaps[k].units.get(unit_id)
    if nxt is None or now is None or unit_id not in nxt.units:
        return None
    later = nxt.units[unit_id]
    path = tuple(action.get("move_path") or ())
    if not path:
        return None
    return later.hex == path[0] or (bool(later.path) and tuple(later.path) == path[len(path) - len(later.path):])


def tp_guided() -> int:
    return 9


def _own_ground_in(snap: Snap, hex_: Any, color: Any) -> int:
    return sum(1 for u in snap.units.values() if u.hex == hex_ and u.color == color and u.type in GROUND and u.on_map)


def e3b(game: Game, snaps: Mapping[int, Snap], seats: Sequence[int],
        fresh: Mapping[int, List[Mapping[str, Any]]]) -> Dict[str, Any]:
    events, comparison, others = [], collections.Counter(), collections.Counter()
    for seat in seats:
        for k in sorted(game.steps):
            if k not in snaps or k + 1 not in snaps:
                continue
            for j, action in enumerate(submitted(game, seat, k)):
                if is_order(action):
                    continue
                unit = snaps[k].units.get(action.get("obj_id"))
                if unit is None:
                    continue
                nxt = snaps[k + 1].units.get(unit.obj_id)
                if unit.concealed and action.get("type") not in (MOVE, SHOOT):
                    others[str(action.get("type"))] += 1
                    continue
                if not unit.concealed:
                    if (action.get("type") == MOVE and unit.move_state == 0 and not unit.in_transition
                            and unit.path == () and nxt is not None):
                        started = (_num(nxt.speed) or 0) > 0 or nxt.hex != unit.hex
                        comparison["started at the next snapshot" if started else "not started at the next snapshot"] += 1
                    continue
                codes = echo_codes(game, seat, k, j, fresh)
                executed = _executed(game, snaps, k, action)
                event = {"k": k, "cur_step": snaps[k].cur_step, "seat": seat, "unit": unit.obj_id,
                         "type": action.get("type"), "listed": action.get("type") in (unit.types or ()),
                         "feedback_codes": codes, "executed": executed,
                         "move_state_next": None if nxt is None else nxt.move_state,
                         "speed_next": None if nxt is None else nxt.speed}
                accepted = bool(codes) and all(c is None for c in codes)
                exited = nxt is not None and nxt.move_state != CONCEAL
                if action.get("type") == MOVE:
                    path = tuple(action.get("move_path") or ())
                    full = nxt is not None and path and _own_ground_in(snaps[k + 1], path[0], unit.color) >= 4
                    moving = nxt is not None and ((_num(nxt.speed) or 0) > 0 or nxt.hex != unit.hex)
                    if full and not moving:
                        event["class"] = "excluded: first hex holds 4 own ground units"
                    else:
                        event["class"] = "consistent" if accepted and executed and exited and moving else "inconsistent"
                else:
                    event["class"] = "consistent" if accepted and executed and exited else "inconsistent"
                events.append(event)
    consistent = sum(1 for e in events if e["class"] == "consistent")
    inconsistent = sum(1 for e in events if e["class"] == "inconsistent")
    if not events:
        verdict = NOT_TESTED
    elif inconsistent:
        verdict = REFUTED
    elif consistent:
        verdict = SUPPORTED
    else:
        verdict = INCONCLUSIVE
    return {"verdict": verdict, "events": len(events), "consistent": consistent, "inconsistent": inconsistent,
            "excluded": len(events) - consistent - inconsistent, "by_type": dict(sorted(collections.Counter(
                str(e["type"]) for e in events).items())), "event_list": events,
            "matched_comparison_unconcealed_moves": dict(sorted(comparison.items())),
            "other_types_on_concealed_units": dict(sorted(others.items()))}


def e5(game: Game, snaps: Mapping[int, Snap], order_list: Sequence[Order], records: Sequence[Mapping[str, Any]],
       fresh: Mapping[int, List[Mapping[str, Any]]]) -> Dict[str, Any]:
    k_of = {s.cur_step: k for k, s in snaps.items() if s.stage == 2}
    last_k = max(snaps)
    events = []
    for o, r in zip(order_list, records):
        end_k = k_of[r["completion"]] if r["completion"] is not None else k_of.get(
            min(o.cur_step + WINDOW, last_cur_step(snaps)), last_k)
        completed = r["completion"] is not None
        unit0 = snaps[o.k].units.get(o.unit)
        tank = unit0 is not None and unit0.a1 == 1
        for k in range(o.k + 1, end_k):
            snap = snaps.get(k)
            if snap is None or o.unit not in snap.units:
                continue
            unit = snap.units[o.unit]
            remaining = _num(unit.timers[0]) or 0
            for j, action in enumerate(submitted(game, o.seat, k)):
                if action.get("obj_id") != o.unit or is_order(action):
                    continue
                codes = echo_codes(game, o.seat, k, j, fresh)
                executed = _executed(game, snaps, k, action)
                refused = any(c is not None for c in codes)
                if refused:
                    what = "refused"
                elif executed and remaining <= 1:
                    what = "executed as the transition ended"
                elif executed:
                    what = "executed during the transition"
                else:
                    what = "not executed during the transition"
                if tank and action.get("type") in (SHOOT, 9) and executed:
                    consistent = not completed
                else:
                    consistent = what != "executed during the transition"
                events.append({"order_k": o.k, "k": k, "unit": o.unit, "event": f"baseline-v2 action type "
                               f"{action.get('type')}", "observed": what, "codes": codes,
                               "transition_completed": completed, "consistent": consistent})
            if (_num(unit.keep) or 0) > 0:
                events.append({"order_k": o.k, "k": k, "unit": o.unit, "event": "suppressed",
                               "transition_completed": completed, "consistent": not completed})
                break
            if any(u.hex == unit.hex and u.color != unit.color and u.on_map for u in snap.units.values()):
                events.append({"order_k": o.k, "k": k, "unit": o.unit, "event": "same-hex engagement",
                               "transition_completed": completed, "consistent": not completed})
                break
            if _judged(game, k, o.unit) and not any(a.get("obj_id") == o.unit for a in submitted(game, o.seat, k)):
                events.append({"order_k": o.k, "k": k, "unit": o.unit, "event": "fired without an order",
                               "transition_completed": completed, "consistent": tank and not completed})
    if not events:
        verdict = NOT_TESTED
    elif any(not e["consistent"] for e in events):
        verdict = REFUTED
    else:
        verdict = SUPPORTED
    return {"verdict": verdict, "events": len(events), "event_list": events,
            "by_event": dict(sorted(collections.Counter(e["event"] for e in events).items()))}


# ----------------------------------------------------------------------------------------------
# S3 and E6 (P-A against the reference game)


def _without_orders(actions: Iterable[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    return [a for a in actions if not is_order(a)]


def s3(game: Game, snaps: Mapping[int, Snap], ref: Game, ref_snaps: Mapping[int, Snap], seat: int, inert: int,
       order_list: Sequence[Order], predicted_units_ok: Optional[bool], predicted_k: int = tp.PREDICTED_FIRST_K,
       predicted_count: int = tp.PREDICTED_FIRST_UNITS) -> Dict[str, Any]:
    first_k = order_list[0].k if order_list else None
    rec, rrec = game.record, ref.record
    trace = {s["seat"]: s["trace_steps"] for s in rec["seats"]}
    rtrace = {s["seat"]: s["trace_steps"] for s in rrec["seats"]}
    premise: List[str] = []
    compared = collections.Counter()
    if first_k is None:
        premise.append("no concealment order was issued")
    elif first_k != predicted_k:
        premise.append(f"the first order is at decision {first_k}, predicted {predicted_k}")
    if first_k is not None and sum(1 for o in order_list if o.k == first_k) != predicted_count:
        premise.append("the first order's unit count differs from the prediction")
    if predicted_units_ok is False:
        premise.append("the first order's units differ from the predicted units")
    horizon = first_k if first_k is not None else rec["steps"] - 1
    for k in range(0, horizon + 1):
        if k >= len(rec["state_steps"]) or k >= len(rrec["state_steps"]):
            premise.append(f"no state digest at decision {k}")
            break
        if rec["state_steps"][k] != rrec["state_steps"][k]:
            premise.append(f"all-seeing state differs at decision {k}")
            break
        compared["state digests"] += 1
        if k in ref_snaps and k in snaps:
            if snaps[k].seats[seat].digest is None or snaps[k].seats[seat].digest != ref_snaps[k].seats[seat].digest:
                premise.append(f"candidate seat observation differs at decision {k}")
                break
            compared["observation digests"] += 1
        block = game.steps[k]["t7"][str(seat)]
        if block["baseline_trace_sha256"][:len(rtrace[seat][k])] != rtrace[seat][k]:
            premise.append(f"baseline-v2 trace differs at decision {k}")
            break
        compared["baseline-v2 trace digests"] += 1
        if trace[inert][k] != rtrace[inert][k]:
            premise.append(f"inert trace differs at decision {k}")
            break
        mine = serialised(game, seat, k)
        expected = serialised(ref, seat, k)
        if (k < horizon or first_k is None) and mine != expected:
            premise.append(f"candidate seat actions differ at decision {k}")
            break
        if k == first_k and (_without_orders(mine) != expected or not all(is_order(a) for a in mine[len(expected):])):
            premise.append(f"candidate seat actions at the first order are not the reference's plus the orders")
            break
        if serialised(game, inert, k) != serialised(ref, inert, k):
            premise.append(f"inert seat actions differ at decision {k}")
            break
        compared["decisions"] += 1
    s3a = not premise
    after: List[Dict[str, Any]] = []
    if s3a:
        for k in range(first_k + 1, max(rec["steps"], rrec["steps"])):
            if k not in game.steps or k not in ref.steps:
                after.append({"k": k, "what": "decision missing in one game"})
                break
            mine, expected = _without_orders(serialised(game, seat, k)), serialised(ref, seat, k)
            if mine != expected:
                after.append({"k": k, "what": "baseline-v2 actions differ", "probe": mine, "reference": expected})
                break
            if serialised(game, inert, k) != serialised(ref, inert, k):
                after.append({"k": k, "what": "inert actions differ"})
                break
            compared["decisions after the first order"] += 1
        if rec["steps"] != rrec["steps"]:
            after.append({"what": f"steps {rec['steps']} against {rrec['steps']}"})
        if rec.get("final_scores") != rrec.get("final_scores"):
            after.append({"what": "final scores differ", "probe": rec.get("final_scores"),
                          "reference": rrec.get("final_scores")})
    completed = rec.get("status") == "COMPLETED"
    if not s3a or not completed:
        verdict = INCONCLUSIVE
    else:
        verdict = FAIL if after else PASS
    v2_trace_after = None
    if s3a:
        equal = sum(1 for k in range(first_k + 1, rec["steps"]) if k < len(rtrace[seat])
                    and game.steps[k]["t7"][str(seat)]["baseline_trace_sha256"][:len(rtrace[seat][k])] == rtrace[seat][k])
        v2_trace_after = {"equal": equal, "compared": max(0, rec["steps"] - first_k - 1)}
    return {"verdict": verdict, "s3a_premise": s3a, "premise_problems": premise, "after_first_order": after,
            "first_order_k": first_k, "compared": dict(compared),
            "baseline_v2_trace_digests_after_first_order": v2_trace_after}


def e6(snaps: Mapping[int, Snap], ref_snaps: Mapping[int, Snap], game: Game, ref: Game, s3a: bool,
       records: Sequence[Mapping[str, Any]], first_k: Optional[int]) -> Dict[str, Any]:
    if not records:
        return {"verdict": NOT_TESTED}
    if not s3a:
        return {"verdict": INCONCLUSIVE, "reason": "the reference was not reproduced before the first order"}
    differences, compared = [], 0
    for k in sorted(ref_snaps):
        if k < first_k or k not in snaps:
            continue
        a, b = snaps[k], ref_snaps[k]
        pos_a = {u: (x.hex, x.on_map, x.blood) for u, x in a.units.items()}
        pos_b = {u: (x.hex, x.on_map, x.blood) for u, x in b.units.items()}
        if pos_a != pos_b:
            units = sorted(u for u in set(pos_a) | set(pos_b) if pos_a.get(u) != pos_b.get(u))
            differences.append({"k": k, "what": "positions, presence or blood", "units": units})
        if a.flags != b.flags:
            differences.append({"k": k, "what": "objective flags"})
        if a.scores != b.scores:
            differences.append({"k": k, "what": "scores"})
        if differences:
            break
        compared += 1
    if not differences and game.record.get("final_scores") != ref.record.get("final_scores"):
        differences.append({"what": "final scores"})
    completed = any(r["completion"] is not None for r in records)
    verdict = REFUTED if differences else SUPPORTED if completed else NOT_TESTED
    return {"verdict": verdict, "snapshots_compared": compared, "first_difference": differences[:1]}


# ----------------------------------------------------------------------------------------------
# S4


def s4(game: Game, seat: int) -> Dict[str, Any]:
    allowed = {(c["action_type"], c["code"], c["message_class"]) for c in tp.REFUSAL_CLASSES}
    record = {s["seat"]: s for s in game.record["seats"]}
    problems = []
    classes = {}
    for s, entry in record.items():
        found = [(f["action_type"], f["code"], f["message_class"], f["count"]) for f in entry.get("refusal_facts") or ()]
        classes[s] = [{"action_type": a, "code": c, "message_class": m, "count": n} for a, c, m, n in found]
        if s == seat:
            new = [(a, c, m) for a, c, m, _ in found if (a, c, m) not in allowed]
            if new:
                problems.append(f"refusal classes outside baseline-v2's registered set: {new}")
            if entry.get("contract_errors"):
                problems.append(f"contract errors {entry['contract_errors']}")
            if entry.get("replay_mismatches"):
                problems.append(f"replay mismatches {entry['replay_mismatches']}")
    missing = [k for k in game.steps if str(seat) not in (game.steps[k].get("t7") or {})]
    errors = [k for k in game.steps if (game.steps[k].get("t7") or {}).get(str(seat), {}).get("error")]
    if missing:
        problems.append(f"decisions without a t7 block: {len(missing)}")
    if errors:
        problems.append(f"t7 errors at {len(errors)} decisions")
    if game.record.get("observer_errors"):
        problems.append("observer errors")
    opponent_new = {s: [c for c in v if (c["action_type"], c["code"], c["message_class"]) not in allowed]
                    for s, v in classes.items() if s != seat}
    return {"verdict": FAIL if problems else PASS, "problems": problems, "refusal_classes": {str(s): v for s, v in
            classes.items()}, "opponent_classes_outside_the_set": {str(s): v for s, v in opponent_new.items()}}


# ----------------------------------------------------------------------------------------------
# E4: visibility of concealed units to an active opponent


def _as_dict(u: U) -> Dict[str, Any]:
    return {"obj_id": u.obj_id, "type": u.type, "sub_type": u.sub_type, "cur_hex": u.hex}


def _targets(units: Mapping[int, U], faction: Any) -> Dict[int, U]:
    return {i: u for i, u in units.items() if u.color == faction and u.type in GROUND and u.on_map
            and _int(u.hex) is not None}


def _observers(units: Mapping[int, U], faction: Any) -> List[Dict[str, Any]]:
    return [_as_dict(u) for u in units.values() if u.color == faction and u.on_map and _int(u.hex) is not None]


def visibility_rows(m: tv.MapData, snap: Snap, seat_of: Mapping[Any, int], channel: str) -> List[Tuple]:
    """Every ground target-step of the snapshot: (target, faction, state, class, listed, nearest relevant observer).

    ``channel`` 'A' reads the all-seeing rows; 'B' reads each seat's own view (targets from their own seat, observers
    from the opposing seat's own view)."""
    out = []
    for faction, seat in seat_of.items():
        other = [f for f in seat_of if f != faction][0]
        opposing = seat_of[other]
        if channel == "A":
            targets = _targets(snap.units, faction)
            observers = _observers(snap.units, other)
        else:
            targets = _targets(snap.seats[seat].own, faction)
            observers = _observers(snap.seats[opposing].own, other)
        listed = snap.seats[opposing].enemies
        for uid, unit in sorted(targets.items()):
            if unit.launched:
                out.append((uid, faction, "excluded: launched unit", None, uid in listed, None, (unit.hex,)))
                continue
            target = _as_dict(unit)
            label, pairs = tv.classify(m, observers, target)
            signature = (unit.hex,) + tuple(sorted((p.observer, p.distance, p.band, p.los) for p in pairs))
            if unit.concealed:
                near = min((p for p in pairs if p.band in (tv.INSIDE, tv.BETWEEN, tv.BOUNDARY)),
                           key=lambda p: (p.distance, p.observer), default=None)
                out.append((uid, faction, "concealed", label, uid in listed,
                            None if near is None else (near.observer, near.distance, near.aerial, near.band), signature))
            elif unit.move_state == 0 and not unit.in_transition:
                seers = [o for o in observers if tv.sees_unconcealed(m, o, target)]
                out.append((uid, faction, "unconcealed", "seen" if seers else "unseen", uid in listed,
                            label == tv.DISCRIMINATING, signature))
            else:
                out.append((uid, faction, "excluded: transition or other movement state", None, uid in listed, None,
                            signature))
    return out


def control_valid(total: int, agree: int, matched: int, matched_listed: int) -> bool:
    """The registered validity of the model in one game: agreement on the control and on the matched band."""
    return (total > 0 and agree / total >= tp.CONTROL_AGREEMENT and matched >= tp.MATCHED_MINIMUM
            and matched_listed / matched >= tp.MATCHED_AGREEMENT)


def e4_game(m: tv.MapData, snaps: Mapping[int, Snap], seat_of: Mapping[Any, int]) -> Dict[str, Any]:
    """Per game: classes, outcomes and control agreement; both channels must agree (refusal otherwise)."""
    classes: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    control = collections.Counter()
    matched = collections.Counter()
    private: List[Dict[str, Any]] = []
    targets_by_class: Dict[str, Set[int]] = collections.defaultdict(set)
    pairs_by_class: Dict[str, Set[Tuple[int, int]]] = collections.defaultdict(set)
    episodes: Dict[str, int] = collections.Counter()
    previous: Dict[int, Tuple[str, int]] = {}
    for k in sorted(snaps):
        snap = snaps[k]
        if snap.stage != 2 or any(s not in snap.seats for s in seat_of.values()):
            continue
        a = visibility_rows(m, snap, seat_of, "A")
        b = visibility_rows(m, snap, seat_of, "B")
        if [r[:5] + r[6:] for r in a] != [r[:5] + r[6:] for r in b]:
            raise AnalysisRefused(f"E4 channels disagree at decision {k}")
        for uid, faction, state, label, listed, extra, _ in a:
            if state == "concealed":
                classes[label]["listed" if listed else "unlisted"] += 1
                targets_by_class[label].add(uid)
                if extra is not None:
                    pairs_by_class[label].add((uid, extra[0]))
                last = previous.get(uid)
                if last is None or last[0] != label or last[1] != k - 1:
                    episodes[label] += 1
                previous[uid] = (label, k)
                if label in (tv.DISCRIMINATING, tv.EXPECTED_VISIBLE, tv.TERRAIN, tv.EXCEPTION_VISIBLE,
                             tv.AMBIGUOUS_AIR, tv.AMBIGUOUS_BOUNDARY):
                    private.append({"k": k, "cur_step": snap.cur_step, "target": uid, "class": label,
                                    "listed": listed, "nearest": extra})
            elif state == "unconcealed":
                control[("seen" if label == "seen" else "unseen", listed)] += 1
                if extra:
                    matched["listed" if listed else "unlisted"] += 1
            else:
                classes[state]["listed" if listed else "unlisted"] += 1
    agree = control[("seen", True)] + control[("unseen", False)]
    total = sum(control.values())
    m_total = matched["listed"] + matched["unlisted"]
    valid = control_valid(total, agree, m_total, matched["listed"])
    return {"classes": {k: dict(v) for k, v in sorted(classes.items())},
            "distinct_targets": {k: len(v) for k, v in sorted(targets_by_class.items())},
            "distinct_pairs": {k: len(v) for k, v in sorted(pairs_by_class.items())},
            "episodes": dict(sorted(episodes.items())),
            "control": {"target_steps": total, "agree": agree, "agreement": None if not total else agree / total,
                        "seen_listed": control[("seen", True)], "seen_unlisted": control[("seen", False)],
                        "unseen_listed": control[("unseen", True)], "unseen_unlisted": control[("unseen", False)]},
            "matched": {"target_steps": m_total, "listed": matched["listed"],
                        "share_listed": None if not m_total else matched["listed"] / m_total},
            "control_valid": valid, "private": private}


def e4_verdicts(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """E4a and E4b over the given per-game results (one game, or P-B1 and P-B2 pooled)."""
    disc = collections.Counter()
    vis = collections.Counter()
    for g in games:
        disc.update(g["classes"].get(tv.DISCRIMINATING, {}))
        vis.update(g["classes"].get(tv.EXPECTED_VISIBLE, {}))
    valid = bool(games) and all(g["control_valid"] for g in games)
    n = disc["listed"] + disc["unlisted"]
    if n == 0:
        e4a = NOT_TESTED
    elif not valid:
        e4a = INCONCLUSIVE
    elif disc["listed"] == 0:
        e4a = SUPPORTED
    elif disc["listed"] / n >= tp.REFUTE_SHARE:
        e4a = REFUTED
    else:
        e4a = INCONCLUSIVE
    nv = vis["listed"] + vis["unlisted"]
    e4b = NOT_TESTED if nv == 0 else REFUTED if vis["unlisted"] else SUPPORTED
    return {"E4a": {"verdict": e4a, "discriminating_target_steps": n, "listed": disc["listed"],
                    "control_valid_in_every_game": valid},
            "E4b": {"verdict": e4b, "expected_listed_target_steps": nv, "unlisted": vis["unlisted"]}}


# ----------------------------------------------------------------------------------------------
# Gates and disposition


def gate_pa(pa: Mapping[str, Any], installation_ok: bool) -> Dict[str, Any]:
    checks = {"integrity": pa["integrity"]["ok"], "S1": pa["S1"]["verdict"] == PASS, "S2": pa["S2"]["verdict"] == PASS,
              "S3": pa["S3"]["verdict"] == PASS, "E2": pa["E2"]["verdict"] == SUPPORTED,
              "ledger, installation and identities": installation_ok}
    return {"continue_to_pb": all(checks.values()), "checks": checks}


def stop_after_pb1(pb1: Mapping[str, Any], installation_ok: bool) -> Dict[str, Any]:
    checks = {"integrity": pb1["integrity"]["ok"], "S1": pb1["S1"]["verdict"] == PASS,
              "S2": pb1["S2"]["verdict"] != FAIL, "S4": pb1["S4"]["verdict"] == PASS,
              "ledger, installation and identities": installation_ok}
    return {"run_pb2": all(checks.values()), "checks": checks}


def pooled(verdicts: Sequence[Optional[str]]) -> str:
    """Pool one endpoint's verdicts over games: REFUTED if any, else SUPPORTED if any and none INCONCLUSIVE."""
    present = [v for v in verdicts if v is not None]
    if REFUTED in present:
        return REFUTED
    if INCONCLUSIVE in present:
        return INCONCLUSIVE
    if SUPPORTED in present:
        return SUPPORTED
    return NOT_TESTED


def disposition(results: Mapping[str, Mapping[str, Any]], played: Sequence[str]) -> Dict[str, Any]:
    """The registered disposition from the registered results of the games played (keys 'P-A', 'P-B1', 'P-B2')."""
    games = [results[g] for g in played]
    e = {name: pooled([g.get(name, {}).get("verdict") for g in games]) for name in ("E1", "E2", "E3a", "E3b", "E5")}
    e["E6"] = results["P-A"]["E6"]["verdict"] if "P-A" in results else NOT_TESTED
    e["E4a"] = (results.get("pooled_e4") or {}).get("E4a", {}).get("verdict", NOT_TESTED)
    e["E4b"] = (results.get("pooled_e4") or {}).get("E4b", {}).get("verdict", NOT_TESTED)
    safety_fail = any(g["S1"]["verdict"] == FAIL or g["S2"]["verdict"] == FAIL for g in games)
    not_completed = any(r["outcome"] == "NOT_COMPLETED" for g in games for r in g.get("orders", ()))
    integrity_fail = any(not g["integrity"]["ok"] for g in games)
    s4_fail = any(g.get("S4", {}).get("verdict") == FAIL for g in games)
    s3_fail = "P-A" in results and results["P-A"]["S3"]["verdict"] == FAIL
    reasons = []
    if safety_fail or e["E1"] == REFUTED or e["E3b"] == REFUTED or e["E4a"] == REFUTED or (
            e["E2"] == REFUTED and not_completed):
        label = "SHELVE"
        reasons = [n for n, bad in (("S1 or S2 FAIL", safety_fail), ("E1 REFUTED", e["E1"] == REFUTED),
                                    ("E3b REFUTED", e["E3b"] == REFUTED), ("E4a REFUTED", e["E4a"] == REFUTED),
                                    ("E2 REFUTED with an order NOT_COMPLETED", e["E2"] == REFUTED and not_completed))
                   if bad]
    elif integrity_fail or s4_fail or s3_fail or e["E6"] == REFUTED or e["E3a"] == REFUTED or e["E5"] == REFUTED \
            or e["E2"] == REFUTED:
        label = "REVISE"
        reasons = [n for n, bad in (("integrity", integrity_fail), ("S4 FAIL", s4_fail), ("S3 FAIL", s3_fail),
                                    ("E6 REFUTED", e["E6"] == REFUTED), ("E3a REFUTED", e["E3a"] == REFUTED),
                                    ("E5 REFUTED", e["E5"] == REFUTED), ("E2 REFUTED (timing)", e["E2"] == REFUTED))
                   if bad]
    elif e["E2"] == SUPPORTED and len(played) == 3 and all(e[n] == SUPPORTED for n in ("E1", "E3a", "E3b", "E4a", "E6")) \
            and all(g["S1"]["verdict"] == PASS and g["S2"]["verdict"] in (PASS, NOT_TESTED) for g in games) \
            and not s4_fail and results["P-A"]["S3"]["verdict"] == PASS:
        label = "READY_FOR_TACTICAL_SCREEN"
    else:
        label = "NEEDS_TARGETED_PROBE"
        reasons = [f"{n} {e[n]}" for n in ("E1", "E2", "E3a", "E3b", "E4a", "E6") if e[n] != SUPPORTED]
        if len(played) < 3:
            reasons.append(f"games played: {', '.join(played)}")
    return {"disposition": label, "reasons": reasons, "pooled_verdicts": e, "games_played": list(played)}
