"""Independent re-count of the T7 audit's counts 1 to 3 through the canonical boundary (``docs/T7_DESIGN.md``, 7).

Written separately from :mod:`.t7_audit`: it reads observations only through :class:`~miaosuan_agent.boundary
.Observation` (``time()``, ``operators()``, ``valid_actions()``) and builds its own situation key, so a defect in the
raw-dictionary reading of the audit shows up as a disagreement. Only counts are compared, not digests.
"""

from __future__ import annotations

import collections
from typing import Any, Dict, Mapping, Set, Tuple

from ..boundary import Observation

GROUPS = {6: "A", 10: "B", 11: "C", 12: "C"}


def _flag(fields: Mapping[str, Any], name: str) -> Any:
    value = fields.get(name)
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value > 0


def _path_flag(fields: Mapping[str, Any]) -> Any:
    path = fields.get("move_path")
    return None if path is None else len(path) > 0


def _states(options: Any) -> Tuple[int, ...]:
    found = set()
    for option in options or ():
        value = option.get("target_state") if isinstance(option, Mapping) else None
        if isinstance(value, int) and not isinstance(value, bool):
            found.add(value)
    return tuple(sorted(found))


class CrossCount:
    def __init__(self) -> None:
        self.listing_decisions: collections.Counter = collections.Counter()
        self.unit_listings: collections.Counter = collections.Counter()
        self.keys: Dict[str, Set[Tuple[Any, ...]]] = collections.defaultdict(set)

    def add(self, observation: Observation, faction: int) -> None:
        stage = {1: "deployment", 2: "play"}.get(observation.time().stage, "other")
        units = {u.obj_id: u for u in observation.operators()}
        seen = any(u.color != faction for u in units.values())
        types_here = set()
        for unit_id, actions in observation.valid_actions().items():
            unit = units.get(unit_id)
            if unit is not None and unit.color != faction:
                continue
            fields = unit.fields if unit is not None else {}
            for action_type in sorted(actions):
                if action_type not in GROUPS:
                    continue
                types_here.add(action_type)
                self.unit_listings[f"{stage}:{action_type}"] += 1
            for group in sorted(set(GROUPS.values())):
                mine = [t for t in sorted(actions) if GROUPS.get(t) == group]
                if not mine:
                    continue
                listed_here = tuple((t, _states(actions[t])) if t == 6 else (t,) for t in mine)
                other_types = tuple(sorted(t for t in actions if GROUPS.get(t) != group))
                key = (group, fields.get("type"), fields.get("sub_type"), fields.get("move_state"), fields.get("stop"),
                       _path_flag(fields) if unit is not None else None,
                       _flag(fields, "change_state_remain_time") if unit is not None else None,
                       fields.get("weapon_unfold_state"), _flag(fields, "keep") if unit is not None else None,
                       fields.get("tire"), seen, listed_here, other_types)
                self.keys[f"{stage}:{group}"].add(key)
        for action_type in types_here:
            self.listing_decisions[f"{stage}:{action_type}"] += 1

    def summary(self) -> Dict[str, Any]:
        return {"decisions_listing": dict(sorted(self.listing_decisions.items())),
                "unit_listings": dict(sorted(self.unit_listings.items())),
                "distinct_situations": {k: len(v) for k, v in sorted(self.keys.items())}}


def agree(audit: Mapping[str, Any], cross: Mapping[str, Any]) -> Dict[str, Any]:
    """Field-by-field comparison of the three counts; ``agree`` is True only if every one is identical."""
    out = {}
    for name in ("decisions_listing", "unit_listings", "distinct_situations"):
        out[name] = dict(audit[name]) == dict(cross[name])
    out["agree"] = all(out.values())
    return out
