"""Sprint 31 historical feasibility preflight of ``t13-keep-one-k2`` (``docs/SPRINT31_T13_K2_PILOT.md``, section 4).

Offline, before any engine session. Everything is Sprint 30's frozen preflight (``evaluation/s30_preflight.py``,
unchanged): the populations (HH, HI genuine; H0 off-policy), their pinned inputs and loader, the fidelity anchors, the
per-side analysis, the first-divergence definition and its validity rule, the departure episodes and the onward labels.
Two things change, and only these:

* **the rule**: the K2 candidate (``experiments/t13_keep_one_k2.py``) instead of K1. Sprint 30's
  :func:`~.s30_preflight.analyse_side` is run unchanged inside :func:`k2_rules`, which points that module's two
  rule-specific names, ``k1`` (the rule module) and ``independent_problems`` (the independent restatement), at the K2
  rule and at :func:`independent_problems` below for the duration of the call and restores them afterwards;
* **the independent restatement** of the holder test (:func:`holder_ok`): K1's restatement with K2's level C, written
  apart from the candidate's code: a unit showing a stop transition (``stop`` 0 or a positive
  ``move_to_stop_remain_time``) qualifies only with ``speed``, ``stop``, ``move_to_stop_remain_time``,
  ``flag_force_stop``, ``change_state_remain_time``, ``get_on_remain_time`` and ``get_off_remain_time`` all numbers,
  speed 0, stop 0, the timer in 1 to 75, and the four others 0; any other unit as in K1.

**Stop** (:func:`disposition`, first match): ``K2_PREFLIGHT_INVALID`` (a fidelity anchor, an integrity check or the
independent check fails); ``K2_PREFLIGHT_INADEQUATE`` (no verified first-divergence opportunity among the two HH red
side-games, or none among the two HH blue side-games, or none in either of the pilot's two fixed inert configurations,
2120531121 C3 and 1930331196 C2): no engine session is opened; otherwise ``K2_PREFLIGHT_PASS``. A verified opportunity
is Sprint 30's: a side-game with a valid first divergence and no independent-check finding.
"""

from __future__ import annotations

import collections
import contextlib
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Sequence, Tuple

from ..boundary import MoveCosts
from ..experiments import t13_keep_one_k2 as k2
from . import s30_preflight as pf

STUDY_ID = "s31-t13-k2"
SCHEMA = "miaosuan-s31-preflight/1"
#: The pilot's inert configurations, fixed by the owner's brief (scenario, condition): C3 = candidate blue, C2 = red.
PILOT_INERT = (("2120531121", "C3"), ("1930331196", "C2"))
DISPOSITIONS = ("K2_PREFLIGHT_INVALID", "K2_PREFLIGHT_INADEQUATE", "K2_PREFLIGHT_PASS")
INVALID, INADEQUATE, PASS = DISPOSITIONS
ANCHORS = pf.ANCHORS
POPULATIONS, GENUINE = pf.POPULATIONS, pf.GENUINE
MOVE = pf.MOVE
SETTLE_LIMIT = 75
#: Sprint 30's frozen independent check, bound before any swap (it reads ``holder_ok`` from its own module).
_S30_INDEPENDENT = pf.independent_problems
SETTLE_NAMES = ("speed", "stop", "move_to_stop_remain_time", "flag_force_stop", "change_state_remain_time",
                "get_on_remain_time", "get_off_remain_time")


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def holder_ok(u: Mapping[str, Any], acts: Sequence[Mapping[str, Any]], centre: int) -> bool:
    """K2's holder test restated: K1's, with a stop transition admitted only in the documented settling form."""
    if pf.positive(u.get("speed")) or u.get("move_path"):
        return False
    if u.get("stop") == 0 or pf.positive(u.get("move_to_stop_remain_time")):
        values = dict((name, u.get(name)) for name in SETTLE_NAMES)
        if not all(number(v) for v in values.values()):
            return False
        if values["speed"] != 0 or values["stop"] != 0 or values["flag_force_stop"] != 0:
            return False
        if not 0 < values["move_to_stop_remain_time"] <= SETTLE_LIMIT:
            return False
        if any(values[name] != 0 for name in ("change_state_remain_time", "get_on_remain_time",
                                               "get_off_remain_time")):
            return False
    elif pf.positive(u.get("change_state_remain_time")):
        return False
    if pf.positive(u.get("get_on_remain_time")) or pf.positive(u.get("get_off_remain_time")):
        return False
    if len(acts) != 1 or acts[0].get("type") != MOVE:
        return False
    route = acts[0].get("move_path")
    return isinstance(route, (list, tuple)) and len(route) > 0 and all(pf.is_int(h) for h in route) \
        and route[-1] != centre


def independent_problems(raw: Mapping[str, Any], faction: int, baseline: Sequence[Mapping[str, Any]],
                         live: Sequence[Mapping[str, Any]], costs: MoveCosts) -> List[str]:
    """Sprint 30's independent check (``s30_preflight.independent_problems``, bound at import) with K2's holder test."""
    with swapped(pf, holder_ok=holder_ok):
        return _S30_INDEPENDENT(raw, faction, baseline, live, costs)


@contextlib.contextmanager
def swapped(module: Any, **names: Any) -> Iterator[None]:
    """Point ``module``'s given names at new objects for the duration of the block, then restore them exactly."""
    missing = [n for n in names if not hasattr(module, n)]
    if missing:
        raise AttributeError(f"{module.__name__} has no {missing}")
    saved = {n: getattr(module, n) for n in names}
    try:
        for n, v in names.items():
            setattr(module, n, v)
        yield
    finally:
        for n, v in saved.items():
            setattr(module, n, v)


@contextlib.contextmanager
def k2_rules() -> Iterator[None]:
    """Sprint 30's analysis with the K2 rule and the K2 restatement (see the module docstring)."""
    with swapped(pf, k1=k2, independent_problems=independent_problems):
        yield


def analyse_side(meta: Mapping[str, Any], stream: Iterable[Any], costs: MoveCosts,
                 travel: Any) -> Tuple[Dict[str, Any], set]:
    with k2_rules():
        return pf.analyse_side(meta, stream, costs, travel)


def disposition(anchors_ok: bool, sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    reasons = []
    if not anchors_ok:
        reasons.append("a fidelity anchor is not reproduced")
    if any(s["independent_check_findings"] for s in sides):
        reasons.append("the independent check found an unexplained or missed withholding")
    if reasons:
        return {"disposition": INVALID, "reasons": reasons}
    for colour in ("red", "blue"):
        group = [s for s in sides if s["population"] == "HH" and s["colour"] == colour]
        if len(group) != 2:
            reasons.append(f"the HH {colour} side-games are not the two registered ones")
        elif not any(s["verified_opportunity"] for s in group):
            reasons.append(f"no verified first-divergence opportunity in the HH {colour} side-games")
    for scenario, condition in PILOT_INERT:
        group = [s for s in sides if s["population"] == "HI" and (s["scenario"], s["condition"]) == (scenario,
                                                                                                   condition)]
        if len(group) != 1:
            reasons.append(f"the HI side-game {scenario} {condition} is not the registered one")
        elif not group[0]["verified_opportunity"]:
            reasons.append(f"no verified first-divergence opportunity in HI {scenario} {condition}")
    return {"disposition": INADEQUATE if reasons else PASS, "reasons": reasons}


def pooled(sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    return pf.pooled(sides)


def public_side(s: Mapping[str, Any]) -> Dict[str, Any]:
    return pf.public_side(s)


def opportunities(sides: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per genuine side-game: the first divergence (decision, step, objective, holder class, whether the holder was
    settling is not recorded by Sprint 30's analysis), the verified flag and the post-divergence withholdings."""
    out = collections.OrderedDict()
    for s in sides:
        if s["population"] not in GENUINE:
            continue
        fd = s["first_divergence"]
        out[s["label"]] = {"verified_opportunity": s["verified_opportunity"],
                           "first_divergence_step": fd["step"] if fd else None,
                           "objective": fd["objective"] if fd else None,
                           "holder_class": fd["holder_class"] if fd else None,
                           "withholding_decisions": s["withholding_decisions"],
                           "post_divergence_withholding_decisions": s["post_divergence_withholding_decisions"]}
    return dict(out)
