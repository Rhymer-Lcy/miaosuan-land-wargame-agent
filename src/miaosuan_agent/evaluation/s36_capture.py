"""Sprint 36 full-step observer: Sprint 35's (``evaluation.s35_capture``) for the Sprint 36 policies, plus wait causes.

A Stage A game has one policy under test (the Sprint 36 candidate, the Sprint 34 control or the Sprint 35 control)
against ``baseline-v2``; a Stage B game the candidate against the inert control. The observer reconstructs every
decision of the policy under test with a fresh instance of that policy from the recorded memory (structural stop
otherwise), attributes differences from a shadow ``baseline-v2``, records the largest canonical JSON size of the
policy's memory, and - new in Sprint 36 - the cause of every step in which an own ground unit of the policy under test
stands still with a move path (``wait_cause``): Sprint 35 counted every such step as a wait in front of a full hex,
but its 107-step run was a suppressed squad whose next hex held one enemy aircraft and no own unit (section 8).
Read-only: nothing it computes reaches the agents or the engine.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ..boundary import MoveCosts
from ..coalition.config import CoalitionConfig
from ..coalition.policy import CoalitionPolicy
from ..integrated.config import Config
from ..tactical.config import TacticalConfig
from ..tactical.policy import TacticalPolicy
from .s34_capture import S34Timeline
from .s35_capture import S35Timeline, plain

TIMELINE_SCHEMA = "miaosuan-s36-timeline/1"
GROUND = (1, 2)
FULL, SUPPRESSED, STOPPED, ENEMY, UNEXPLAINED = ("full next hex", "suppressed", "stop", "enemy on next hex",
                                                 "unexplained")


def wait_cause(next_own: int, keep: int, stop: int, next_enemy: int) -> str:
    """Why a ground unit with a path stands still: a full next hex (four own ground units), suppression (``keep``), a
    deferred stop order (``flag_force_stop``), an enemy ground unit on the next hex, or none of these readable."""
    if next_own >= 4:
        return FULL
    if keep:
        return SUPPRESSED
    if stop:
        return STOPPED
    if next_enemy:
        return ENEMY
    return UNEXPLAINED


def halted_units(raw: Mapping[str, Any], colour: int, everyone: Sequence[Mapping[str, Any]]) -> list:
    """(unit, cause) for every own ground unit of ``raw`` (the seat's observation) with a path and zero speed; hex
    counts from ``everyone`` (the all-seeing operators at the start of the step)."""
    out = []
    for u in raw.get("operators") or ():
        if u.get("color") != colour or u.get("type") not in GROUND or not u.get("move_path") or u.get("speed"):
            continue
        nxt = u["move_path"][0]
        own = sum(1 for o in everyone if o.get("color") == colour and o.get("type") in GROUND
                  and o.get("cur_hex") == nxt and not o.get("on_board"))
        enemy = sum(1 for o in everyone if o.get("color") != colour and o.get("type") in GROUND
                    and o.get("cur_hex") == nxt)
        out.append([u.get("obj_id"), wait_cause(own, int(bool(u.get("keep"))), int(bool(u.get("flag_force_stop"))),
                                                enemy)])
    return sorted(out)


class S36Timeline(S35Timeline):
    def __init__(self, policy_id: str, config: Any, costs: MoveCosts, **kwargs: Any) -> None:
        if isinstance(config, TacticalConfig):
            S34Timeline.__init__(self, policy_id, config.coalition.base, costs, **kwargs)
            self.shadow = TacticalPolicy(costs, config)
            self.checks["memory_bytes_max"] = 0
        elif isinstance(config, (CoalitionConfig, Config)):
            super().__init__(policy_id, config, costs, **kwargs)
        else:
            raise TypeError("the policy under test must be a Sprint 34, 35 or 36 configuration")
        self.halts: list = []

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        everyone = [dict(o) for o in (before.global_observation.fields.get("operators") or ())]
        for d in decisions:
            if d.get("policy") != self.candidate_policy:
                continue
            raw = d["observation"]
            colour = d["faction"]
            for unit, cause in halted_units(raw if isinstance(raw, Mapping) else plain(raw), colour, everyone):
                self.halts.append([index, unit, cause])

    def compact(self):
        payload = super().compact()
        payload["schema"] = TIMELINE_SCHEMA
        payload["halts"] = self.halts
        return payload


__all__ = ["S36Timeline", "wait_cause", "halted_units", "TIMELINE_SCHEMA", "FULL"]
