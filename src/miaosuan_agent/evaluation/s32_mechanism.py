"""Sprint 32 proposed mechanism check of ``t7-b1-stop-engage-1``: the per-stop event classification, the per-game
gate and the disposition (``docs/SPRINT32_T7_B1_PREFLIGHT.md``, section 8). PROPOSED, NOT AUTHORIZED: nothing here
opens an engine session; the rules are fixed now so that the owner can approve them before any result exists.

Inputs are built by a future full-step observer from the candidate seat's own observations, the engine's feedback and
the judge records of each step. Every event is read per stop order from the frames that follow it:

* a **frame** is one decision of the candidate seat: ``step`` (``cur_step``), ``units`` (own ground units:
  :class:`Snap`), ``enemies`` (enemy ground units in the seat's view: id to (hex, type)), ``feedback`` (the fresh
  feedback entries of the step: ``message`` echoing an action, ``error`` with a ``code`` when refused), ``judge`` (the
  judge records of the step: ``att_obj_id``) and ``emitted`` (the composite policy's actions at the decision);
* an **order** is a stop the candidate emitted: its decision index ``k``, step ``s0``, unit, the steps ``h0`` its
  current hex needed at ``s0``, the unit's hex and the path's first hex at ``s0``, and its weapons.

Per stop, with ``TOLERANCE`` = 2 steps (as for the transition timing of Sprint 4: the order may take effect in the
submission step or the next, and whether the engine lists actions before or after updating its timers within a step is
unknown):

* **A rejected**: an echo of the order with an error code within :data:`FEEDBACK_STEPS` steps of ``s0``. Adverse.
* **B deferred**: ``flag_force_stop`` 1 at any later frame while the unit is present. Adverse.
* **D path cleared**: the first later frame whose ``move_path`` is empty; the deadline is ``s0 + h0 + TOLERANCE``.
  A path still non-empty at the deadline (unit present) is ``path_not_cleared``. Adverse.
* **C / C' / overrun**: the hex at the clearing frame equals the path's first hex at ``s0`` (C, the documented form),
  the hex at ``s0`` (C', in place: a documented-semantics contradiction, reported, not adverse) or another hex
  (``overrun``: the stop did not take effect where either reading puts it). Adverse when overrun.
* **E transition begins**: at the clearing frame ``move_to_stop_remain_time`` is positive and ``stop`` is 0; otherwise
  ``no_transition``. Adverse.
* **F transition completes**: the first later frame with ``stop`` 1, within ``[P + 75 - TOLERANCE,
  P + 75 + TOLERANCE]`` of the clearing step ``P``; ``stop`` 1 earlier or later is ``transition_timing``. Adverse.
* **I unable to resume**: at completion nothing is listed for the unit within ``TOLERANCE`` steps, or movement
  (action 1) is never listed again within ``TOLERANCE`` steps of completion. Adverse.
* **G firing opportunity**: evaluable when at completion an enemy ground unit in the unit's own visibility list lies
  within the published range of one of its weapons from its hex; met when action 2 is listed within ``TOLERANCE``
  steps of completion.
* **H shot emitted and accepted**: the composite emits action 2 for the unit within ``TOLERANCE`` steps of completion,
  its echo carries no error code and a judge record names the unit as attacker in that step or the next.
* **Censored**: the unit absent (destroyed) or the game over before the event's deadline, or the unit suppressed at
  completion (a suppressed unit's listings are not the stop's doing); never adverse.

Per game, first match (:func:`game_verdict`): ``STRUCTURAL``; ``ADVERSE`` (any adverse event of any stop, or a
deadlock); ``HARM``; ``NOT_ENGAGING`` (completed stops with a firing opportunity, none of which listed a shot);
``UNTESTED`` (no completed, uncensored stop); ``STOP_ONLY`` (completed stops, none with a firing opportunity);
``OBSERVED``. The gate to the next game stays open only after ``UNTESTED``, ``STOP_ONLY`` or ``OBSERVED``. The
disposition over the opened games, first match (:func:`disposition`): ``T7B1_MECH_INVALID`` (a structural stop, a game
opened behind a closed gate, more games than planned, or fewer with the gate still open); ``T7B1_MECH_REJECT`` (an
adverse or harm verdict); ``T7B1_MECH_NOT_ENGAGING``; ``T7B1_MECH_SUPPORTED`` (a game ``OBSERVED``);
``T7B1_MECH_STOP_ONLY`` (a game ``STOP_ONLY``); ``T7B1_MECH_UNTESTED``.

Per game: **deadlock** when, while a stopped unit stands on its stop hex, some own ground unit waits (a path, ``speed``
not positive) with that hex first on its path and the hex holds at least four own ground units, for
:data:`DEADLOCK_RUN` consecutive frames (Sprint 31's M3 bound); **harm** when occupy falls below the configuration's
constant control value or the margin falls more than :data:`HARM_MARGIN` below the control minimum.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..experiments import t7_b1_stop_engage as cand

SCHEMA = "miaosuan-s32-mechanism/1"
TOLERANCE = 2
FEEDBACK_STEPS = 2
DEADLOCK_RUN = 300
HARM_MARGIN = 50
STOP, MOVE, SHOOT = 10, 1, 2
ADVERSE = ("rejected", "deferred", "path_not_cleared", "overrun", "no_transition", "transition_timing",
           "unable_to_resume")
GAME_VERDICTS = ("STRUCTURAL", "ADVERSE", "HARM", "NOT_ENGAGING", "UNTESTED", "STOP_ONLY", "OBSERVED")
DISPOSITIONS = ("T7B1_MECH_INVALID", "T7B1_MECH_REJECT", "T7B1_MECH_NOT_ENGAGING", "T7B1_MECH_UNTESTED",
                "T7B1_MECH_STOP_ONLY", "T7B1_MECH_SUPPORTED")


@dataclass(frozen=True)
class Snap:
    hex: Any
    path: Tuple[Any, ...]
    speed: Any
    stop: Any
    timer: Any
    force: Any
    listed: Tuple[int, ...]
    see: Tuple[Any, ...]
    keep: Any = 0


@dataclass(frozen=True)
class Order:
    k: int
    step: int
    unit: int
    h0: int
    start_hex: int
    next_hex: int
    weapons: Tuple[int, ...]


def positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def echoes(entry: Mapping[str, Any], unit: int, kind: int) -> bool:
    message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
    return message.get("obj_id") == unit and message.get("type") == kind


def error_code(entry: Mapping[str, Any]) -> Any:
    error = entry.get("error")
    if not error:
        return None
    return error.get("code", "unspecified") if isinstance(error, Mapping) else error


def in_range(snap: Snap, weapons: Sequence[int], enemies: Mapping[Any, Tuple[Any, Any]]) -> bool:
    for eid in snap.see:
        if eid not in enemies:
            continue
        there, kind = enemies[eid]
        reach = cand.weapon_range(weapons, kind)
        if reach is not None and isinstance(there, int) and isinstance(snap.hex, int) \
                and cand.hex_distance(snap.hex, there) <= reach:
            return True
    return False


def classify(order: Order, frames: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The events of one stop order, read from the frames after its decision (``frames[order.k]`` is that decision)."""
    out: Dict[str, Any] = {"unit": order.unit, "step": order.step, "h0": order.h0, "adverse": [], "censored": None,
                           "cleared_step": None, "where": None, "completed_step": None, "fire_evaluable": None,
                           "fire_listed": None, "shot_accepted": None, "move_relisted": None}
    later = list(frames[order.k + 1:])
    for f in frames[order.k:]:
        if f["step"] - order.step > FEEDBACK_STEPS:
            break
        if any(echoes(e, order.unit, STOP) and error_code(e) is not None for e in f.get("feedback") or ()):
            out["adverse"].append("rejected")
            return out
    if any(order.unit in f["units"] and f["units"][order.unit].force == 1 for f in later):
        out["adverse"].append("deferred")
    deadline = order.step + order.h0 + TOLERANCE
    clear = None
    for i, f in enumerate(later):
        if order.unit not in f["units"]:
            out["censored"] = "lost before the path cleared"
            return out
        if not f["units"][order.unit].path:
            clear = i
            break
        if f["step"] >= deadline:
            out["adverse"].append("path_not_cleared")
            return out
    if clear is None:
        out["censored"] = "game over before the path cleared"
        return out
    fc = later[clear]
    snap = fc["units"][order.unit]
    out["cleared_step"] = fc["step"]
    if fc["step"] > deadline:
        out["adverse"].append("path_not_cleared")
    out["where"] = "next_hex" if snap.hex == order.next_hex else "in_place" if snap.hex == order.start_hex \
        else "elsewhere"
    if out["where"] == "elsewhere":
        out["adverse"].append("overrun")
    if not (positive(snap.timer) and snap.stop == 0):
        out["adverse"].append("no_transition")
    low, high = fc["step"] + cand.TRANSITION - TOLERANCE, fc["step"] + cand.TRANSITION + TOLERANCE
    done = None
    for j in range(clear, len(later)):
        f = later[j]
        if order.unit not in f["units"]:
            out["censored"] = out["censored"] or "lost during the transition"
            return out
        if f["units"][order.unit].stop == 1:
            done = j
            break
        if f["step"] > high:
            break
    if done is None:
        if later and later[-1]["step"] < high and order.unit in later[-1]["units"]:
            out["censored"] = "game over during the transition"
        else:
            out["adverse"].append("transition_timing")
        return out
    fd = later[done]
    out["completed_step"] = fd["step"]
    if not low <= fd["step"] <= high:
        out["adverse"].append("transition_timing")
    if positive(fd["units"][order.unit].keep):
        out["censored"] = "suppressed at completion"
        return out
    window = [f for f in later[done:] if f["step"] <= fd["step"] + TOLERANCE and order.unit in f["units"]]
    listed = [t for f in window for t in f["units"][order.unit].listed]
    out["move_relisted"] = MOVE in listed
    if not listed or MOVE not in listed:
        out["adverse"].append("unable_to_resume")
    out["fire_evaluable"] = in_range(fd["units"][order.unit], order.weapons, fd.get("enemies") or {})
    out["fire_listed"] = SHOOT in listed
    shots = [(f, a) for f in window for a in f.get("emitted") or () if a.get("obj_id") == order.unit
             and a.get("type") == SHOOT]
    if shots:
        accepted = False
        for f, _ in shots:
            index = frames.index(f)
            near = frames[index:index + 2]
            clean = all(error_code(e) is None for g in near for e in g.get("feedback") or ()
                        if echoes(e, order.unit, SHOOT))
            judged = any(isinstance(r, Mapping) and r.get("att_obj_id") == order.unit for g in near
                         for r in g.get("judge") or ())
            accepted = accepted or (clean and judged)
        out["shot_accepted"] = accepted
    return out


def deadlock_runs(orders: Sequence[Order], results: Sequence[Mapping[str, Any]],
                  frames: Sequence[Mapping[str, Any]]) -> List[int]:
    """The longest run of consecutive frames of the blocking condition at each completed or cleared stop's hex."""
    out = []
    for order, result in zip(orders, results):
        if result["cleared_step"] is None:
            continue
        start = next(i for i, f in enumerate(frames) if f["step"] == result["cleared_step"])
        stop_hex = frames[start]["units"][order.unit].hex
        run = best = 0
        for f in frames[start:]:
            me = f["units"].get(order.unit)
            if me is None or me.hex != stop_hex:
                break
            crowd = sum(1 for s in f["units"].values() if s.hex == stop_hex)
            blocked = any(s.path and s.path[0] == stop_hex and not positive(s.speed) for uid, s in f["units"].items()
                          if uid != order.unit)
            run = run + 1 if (blocked and crowd >= cand.STACK_LIMIT) else 0
            best = max(best, run)
        out.append(best)
    return out


def game_verdict(structural: Sequence[str], results: Sequence[Mapping[str, Any]], runs: Sequence[int],
                 occupy: int, margin: int, control: Mapping[str, int]) -> Dict[str, Any]:
    """One game's verdict, first match, and whether the gate to the next game stays open."""
    adverse = sorted({a for r in results for a in r["adverse"]})
    harm = []
    if occupy < control["occupy"]:
        harm.append("occupy below the constant control value")
    if margin < control["margin_min"] - HARM_MARGIN:
        harm.append("margin more than the harm margin below the control minimum")
    completed = [r for r in results if r["completed_step"] is not None and not r["adverse"] and not r["censored"]]
    evaluable = [r for r in completed if r["fire_evaluable"]]
    if structural:
        verdict = GAME_VERDICTS[0]
    elif adverse or any(run >= DEADLOCK_RUN for run in runs):
        verdict = GAME_VERDICTS[1]
    elif harm:
        verdict = GAME_VERDICTS[2]
    elif evaluable and not any(r["fire_listed"] for r in evaluable):
        verdict = GAME_VERDICTS[3]
    elif not completed:
        verdict = GAME_VERDICTS[4]
    elif not evaluable:
        verdict = GAME_VERDICTS[5]
    else:
        verdict = GAME_VERDICTS[6]
    return {"verdict": verdict, "gate_open": verdict in GAME_VERDICTS[4:], "adverse": adverse, "harm": harm,
            "stops": len(results), "completed": len(completed), "fire_evaluable": len(evaluable),
            "fire_listed": sum(1 for r in evaluable if r["fire_listed"]),
            "shots_accepted": sum(1 for r in completed if r["shot_accepted"]),
            "in_place": sum(1 for r in results if r["where"] == "in_place"),
            "next_hex": sum(1 for r in results if r["where"] == "next_hex"),
            "censored": sum(1 for r in results if r["censored"]), "longest_deadlock_run": max(runs, default=0)}


def disposition(games: Sequence[Mapping[str, Any]], planned: int = 2) -> Dict[str, Any]:
    """The check's disposition, first match, over the games opened in order (a game opens only after an open gate)."""
    verdicts = [g["verdict"] for g in games]
    if not games or verdicts[0] == GAME_VERDICTS[0] or GAME_VERDICTS[0] in verdicts \
            or any(not g["gate_open"] for g in games[:-1]) or len(games) > planned:
        return {"disposition": DISPOSITIONS[0], "games": len(games)}
    if any(v in GAME_VERDICTS[1:3] for v in verdicts):
        return {"disposition": DISPOSITIONS[1], "games": len(games)}
    if GAME_VERDICTS[3] in verdicts:
        return {"disposition": DISPOSITIONS[2], "games": len(games)}
    if len(games) < planned:
        return {"disposition": DISPOSITIONS[0], "games": len(games)}
    if GAME_VERDICTS[6] in verdicts:
        return {"disposition": DISPOSITIONS[5], "games": len(games)}
    if GAME_VERDICTS[5] in verdicts:
        return {"disposition": DISPOSITIONS[4], "games": len(games)}
    return {"disposition": DISPOSITIONS[3], "games": len(games)}
