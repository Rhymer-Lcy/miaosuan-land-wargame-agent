"""Sprint 33 registered mechanism classification of ``t7-b1-stop-engage-1`` (``docs/SPRINT33_T7_B1_LIVE.md``).

Sprint 32's prepared rules (:mod:`.s32_mechanism`) are kept unchanged and are computed for every stop and game as the
preserved Sprint 32 classification. This module registers, before any engine session, exactly two things on top of
them:

1. **One correction, under its own identity** (:data:`RULES_ID`). Sprint 32's code marks a stop ``deferred`` (adverse)
   when ``flag_force_stop`` is 1 at ANY later frame, while its documentation (section 3.5 of
   ``docs/SPRINT32_T7_B1_PREFLIGHT.md``) names *indefinite* deferral as the adverse outcome. The documented contract
   makes a moving unit finish its current hex before the stop takes effect, and the only recorded engine behaviour of
   the flag (``docs/PS1_ENGINE_PROBE.md``, B-4) is a stop that is pending because it cannot yet take effect. A flag
   raised while the unit completes its hex and gone once the path clears is therefore the documented sequence, and
   Sprint 32's code would classify it as adverse. Sprint 33 replaces ``deferred`` by ``deferred_indefinite``: the flag
   1 together with a non-empty path at a frame at or after the clearing deadline ``s0 + h0 + TOLERANCE`` (B-4's
   signature persisting beyond the documented completion). Every other adverse outcome, window, tolerance, deadline,
   censoring rule, verdict and the disposition order are Sprint 32's, called unchanged.
2. **Supplementary endpoints and an evidence level**, reported beside the verdicts and never changing them: stop
   listed, emitted in the exact documented form, echoed, refused; the flag's frames; the expected and the observed
   entry into the next hex; path clearance; transition start and completion; movement relisted; shooting listed;
   shot emitted, refused or accepted; judge records naming the unit as attacker; resumption of route movement; other
   own units blocked at the stop hex; ``baseline-v2`` actions for the unit before the stop took effect.

**What each label establishes.** Sprint 32's game verdict ``OBSERVED`` (disposition ``T7B1_MECH_SUPPORTED``) needs a
completed stop whose firing opportunity was met, i.e. a shot LISTED; it does not need a shot to be fired or accepted.
Sprint 33 therefore attaches an evidence level to the two positive dispositions:

* ``T7B1_MECH_SUPPORTED`` with ``STOP_AND_SHOT_ACCEPTED`` (a completed stop, an in-range target at completion, a shot
  emitted within the window, echoed without error and named as attacker by a judge record) or
  ``STOP_AND_SHOOTING_LISTED`` (the shot was listed; no accepted shot);
* ``T7B1_MECH_STOP_ONLY`` with ``STOP_AND_MOVEMENT_RESUMPTION`` (a completed stop after which the unit was ordered to
  move and traversed again) or ``STOP_EXECUTION`` (stop semantics only: accepted, the next hex completed, the path
  cleared, the 75-step transition completed in time, movement relisted).

A completed stop with no in-range target at completion is evidence for stop semantics only, never for engagement. A
completed stop with such a target but no listed shot is ``NOT_ENGAGING`` (Sprint 32's rule) and is reported apart.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import s32_mechanism as m32

RULES_ID = "s33-t7-b1-mechanism-1"
SCHEMA = "miaosuan-s33-mechanism/1"
TOLERANCE = m32.TOLERANCE
FEEDBACK_STEPS = m32.FEEDBACK_STEPS
STOP, MOVE, SHOOT = m32.STOP, m32.MOVE, m32.SHOOT
#: Sprint 33's adverse outcomes: Sprint 32's with ``deferred`` replaced by ``deferred_indefinite``.
ADVERSE = ("rejected", "deferred_indefinite", "path_not_cleared", "overrun", "no_transition", "transition_timing",
           "unable_to_resume")
GAME_VERDICTS = m32.GAME_VERDICTS
DISPOSITIONS = m32.DISPOSITIONS
#: Evidence levels, from the weakest to the strongest of each positive disposition.
STOP_ONLY_LEVELS = ("STOP_EXECUTION", "STOP_AND_MOVEMENT_RESUMPTION")
SUPPORTED_LEVELS = ("STOP_AND_SHOOTING_LISTED", "STOP_AND_SHOT_ACCEPTED")
ENDPOINTS = ("STOP_EXECUTION", "MOVEMENT_RESUMED", "SHOOTING_LISTED", "SHOT_ACCEPTED")


def flag_frames(order: m32.Order, frames: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """The later frames in which the stopped unit is present with ``flag_force_stop`` 1: step and path length."""
    return [{"step": f["step"], "path": len(f["units"][order.unit].path)} for f in frames[order.k + 1:]
            if order.unit in f["units"] and f["units"][order.unit].force == 1]


def deferred_indefinite(order: m32.Order, frames: Sequence[Mapping[str, Any]]) -> bool:
    """``flag_force_stop`` 1 with a non-empty path at a frame at or after the clearing deadline."""
    deadline = order.step + order.h0 + TOLERANCE
    return any(row["step"] >= deadline and row["path"] > 0 for row in flag_frames(order, frames))


def corrected(result: Mapping[str, Any], order: m32.Order, frames: Sequence[Mapping[str, Any]]) -> List[str]:
    """Sprint 33's adverse list for one stop: Sprint 32's without ``deferred``, plus ``deferred_indefinite``."""
    out = [a for a in result["adverse"] if a != "deferred"]
    if deferred_indefinite(order, frames):
        out.insert(0, "deferred_indefinite")
    return out


def exact_stop(action: Mapping[str, Any], unit: int) -> bool:
    return set(action) == {"actor", "obj_id", "type"} and action.get("obj_id") == unit and action.get("type") == STOP


def index_of_step(frames: Sequence[Mapping[str, Any]], step: Any) -> Optional[int]:
    return next((i for i, f in enumerate(frames) if f["step"] == step), None)


def endpoints(order: m32.Order, frames: Sequence[Mapping[str, Any]], result: Mapping[str, Any]) -> Dict[str, Any]:
    """The supplementary endpoints of one stop (descriptive; they never change a verdict)."""
    here = frames[order.k]
    me = here["units"].get(order.unit)
    out: Dict[str, Any] = {
        "stop_listed": me is not None and STOP in me.listed,
        "stop_emitted_exact": sum(1 for a in here.get("emitted") or () if exact_stop(a, order.unit)) == 1,
        "stop_echoed_clean": False, "stop_refused": False,
        "expected_entry_step": order.step + order.h0, "entry_step": None,
        "flag_frames": 0, "flag_first_offset": None, "flag_last_offset": None, "flag_after_clear": False,
        "deferred_indefinite": deferred_indefinite(order, frames),
        "transition_started": None, "completion_offset": None,
        "shot_emitted": False, "shot_refused": False, "judge_records_in_window": 0, "damage_in_window": 0,
        "judge_records_after_completion": 0, "resume_order_step": None, "resume_order_refused": None,
        "resumed": None, "baseline_actions_before_effect": 0, "blocked_frames": 0}
    for f in frames[order.k:]:
        if f["step"] - order.step > FEEDBACK_STEPS:
            break
        for e in f.get("feedback") or ():
            if m32.echoes(e, order.unit, STOP):
                if m32.error_code(e) is None:
                    out["stop_echoed_clean"] = True
                else:
                    out["stop_refused"] = True
    flags = flag_frames(order, frames)
    if flags:
        out["flag_frames"] = len(flags)
        out["flag_first_offset"] = flags[0]["step"] - order.step
        out["flag_last_offset"] = flags[-1]["step"] - order.step
        if result["cleared_step"] is not None:
            out["flag_after_clear"] = any(row["step"] >= result["cleared_step"] for row in flags)
    for f in frames[order.k + 1:]:
        s = f["units"].get(order.unit)
        if s is None:
            break
        if s.hex == order.next_hex:
            out["entry_step"] = f["step"]
            break
    effect = result["cleared_step"]
    for f in frames[order.k + 1:]:
        if effect is not None and f["step"] >= effect:
            break
        out["baseline_actions_before_effect"] += sum(1 for a in f.get("emitted") or () if a.get("obj_id") == order.unit)
    if effect is not None:
        start = index_of_step(frames, effect)
        snap = frames[start]["units"][order.unit]
        out["transition_started"] = m32.positive(snap.timer) and snap.stop == 0
        for f in frames[start:]:
            me = f["units"].get(order.unit)
            if me is None or me.hex != snap.hex:
                break
            out["blocked_frames"] += any(s.path and s.path[0] == snap.hex and not m32.positive(s.speed)
                                         for uid, s in f["units"].items() if uid != order.unit)
    done = result["completed_step"]
    if done is None:
        return out
    out["completion_offset"] = done - effect if effect is not None else None
    start = index_of_step(frames, done)
    window = [f for f in frames[start:] if f["step"] <= done + TOLERANCE]
    judged = [f for f in frames[start:] if f["step"] <= done + TOLERANCE + 1]
    out["shot_emitted"] = any(a.get("obj_id") == order.unit and a.get("type") == SHOOT for f in window
                              for a in f.get("emitted") or ())
    out["shot_refused"] = any(m32.echoes(e, order.unit, SHOOT) and m32.error_code(e) is not None for f in judged
                              for e in f.get("feedback") or ())
    mine = [(f, r) for f in judged for r in f.get("judge") or () if isinstance(r, Mapping)
            and r.get("att_obj_id") == order.unit]
    out["judge_records_in_window"] = len(mine)
    out["damage_in_window"] = sum(1 for _, r in mine if m32.positive(r.get("damage")))
    out["judge_records_after_completion"] = sum(1 for f in frames[start:] for r in f.get("judge") or ()
                                                if isinstance(r, Mapping) and r.get("att_obj_id") == order.unit)
    stop_hex = frames[start]["units"][order.unit].hex
    for i in range(start, len(frames)):
        f = frames[i]
        if order.unit not in f["units"]:
            break
        if not any(a.get("obj_id") == order.unit and a.get("type") == MOVE for a in f.get("emitted") or ()):
            continue
        out["resume_order_step"] = f["step"]
        out["resume_order_refused"] = any(m32.echoes(e, order.unit, MOVE) and m32.error_code(e) is not None
                                          for g in frames[i:i + 2] for e in g.get("feedback") or ())
        out["resumed"] = any(order.unit in g["units"] and ((g["units"][order.unit].path
                                                            and m32.positive(g["units"][order.unit].speed))
                                                           or g["units"][order.unit].hex != stop_hex)
                             for g in frames[i + 1:])
        break
    return out


def classify(order: m32.Order, frames: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """One stop: Sprint 32's classification (preserved, ``s32``), Sprint 33's adverse list (``adverse``) and the
    supplementary endpoints. The remaining keys are Sprint 32's, so that :func:`.s32_mechanism.game_verdict` reads
    this result under Sprint 33's correction."""
    original = m32.classify(order, frames)
    out = dict(original)
    out["adverse"] = corrected(original, order, frames)
    out["s32_adverse"] = list(original["adverse"])
    out["endpoints"] = endpoints(order, frames, original)
    return out


def qualifying(results: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """Completed, uncensored stops with no Sprint 33 adverse outcome."""
    return [r for r in results if r["completed_step"] is not None and not r["adverse"] and not r["censored"]]


def demonstrated(results: Sequence[Mapping[str, Any]]) -> List[str]:
    """The endpoints that at least one qualifying stop demonstrates, in :data:`ENDPOINTS` order. Shooting listed and
    shot accepted are read from the listing, the emission, the echo and the judge records, whether or not the
    registered firing-opportunity reading found a target in range at completion (that reading decides the verdict)."""
    q = qualifying(results)
    found = {"STOP_EXECUTION": bool(q),
             "MOVEMENT_RESUMED": any(r["endpoints"]["resumed"] for r in q),
             "SHOOTING_LISTED": any(r["fire_listed"] for r in q),
             "SHOT_ACCEPTED": any(r["shot_accepted"] for r in q)}
    return [name for name in ENDPOINTS if found[name]]


def game_verdict(structural: Sequence[str], results: Sequence[Mapping[str, Any]], runs: Sequence[int], occupy: int,
                 margin: int, control: Mapping[str, int]) -> Dict[str, Any]:
    """Sprint 33's game verdict (Sprint 32's function on the corrected adverse lists), the preserved Sprint 32 verdict
    and the endpoints demonstrated in the game."""
    out = m32.game_verdict(structural, results, runs, occupy, margin, control)
    preserved = [dict(r, adverse=r["s32_adverse"]) for r in results]
    out["s32_verdict"] = m32.game_verdict(structural, preserved, runs, occupy, margin, control)["verdict"]
    out["demonstrated"] = demonstrated(results)
    out["shots_emitted"] = sum(1 for r in qualifying(results) if r["endpoints"]["shot_emitted"])
    out["flags_observed"] = sum(1 for r in results if r["endpoints"]["flag_frames"])
    return out


def evidence_level(verdict: str, demonstrated_endpoints: Sequence[str]) -> Optional[str]:
    """The evidence level of a positive disposition, ``None`` for every other."""
    found = set(demonstrated_endpoints)
    if verdict == DISPOSITIONS[5]:
        return SUPPORTED_LEVELS[1] if "SHOT_ACCEPTED" in found else SUPPORTED_LEVELS[0]
    if verdict == DISPOSITIONS[4]:
        return STOP_ONLY_LEVELS[1] if "MOVEMENT_RESUMED" in found else STOP_ONLY_LEVELS[0]
    return None


def disposition(games: Sequence[Mapping[str, Any]], planned: int = 2) -> Dict[str, Any]:
    """Sprint 32's disposition over Sprint 33's game verdicts, the preserved Sprint 32 disposition over the preserved
    verdicts, and the evidence level with the endpoints demonstrated over the opened games."""
    out = m32.disposition(games, planned)
    preserved = [dict(g, verdict=g["s32_verdict"], gate_open=g["s32_verdict"] in GAME_VERDICTS[4:]) for g in games]
    out["s32_disposition"] = m32.disposition(preserved, planned)["disposition"]
    endpoints_seen = [name for name in ENDPOINTS if any(name in g.get("demonstrated", ()) for g in games)]
    out["demonstrated"] = endpoints_seen
    out["evidence_level"] = evidence_level(out["disposition"], endpoints_seen)
    return out
