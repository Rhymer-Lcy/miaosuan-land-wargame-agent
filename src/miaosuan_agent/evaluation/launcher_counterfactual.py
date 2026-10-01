"""Counterfactual comparison of baseline-v2 and the launcher-dependent shoot-reservation candidate on one input.

Both policies decide on the same canonical start-of-step observation. The registered change predicts the
candidate's output exactly, through an oracle that does not use the candidate's code:

* ``R(u)``, for each unit ``u`` in processing order, is the set of targets of the shoot actions the candidate
  emitted for units processed before ``u`` (read off the candidate's output); these are the reserved launchers;
* the relation is each operator's ``launcher`` field in the same observation (an int, bools excluded);
* the oracle is baseline-v2 deciding on a copy of the observation in which every unit ``u`` no longer offers the
  shoot options (well-formed, at or above the minimum attack level) whose target is not in ``R(u)`` and whose
  target's launcher is in ``R(u)``; the shoot type stays listed, possibly with no option;
* the candidate's actions must equal the oracle's, its memory the baseline's, its launcher record the withdrawn
  options, and its trace the oracle's apart from the policy name, the schema, the launcher record, the two
  launcher markers of a displaced unit, the engage count (it differs by exactly the withdrawn options), the no-op
  reason of a unit left without action, and the malformed-relation diagnostics the candidate appends.

Every unit whose action differs from baseline-v2's is classified: direct, when baseline-v2 selected a shoot at a
target whose launcher is in ``R(u)`` (by the candidate's outcome: alternate-target, fallback-occupy, fallback-move,
fallback-none); secondary, when baseline-v2's action was not such a shoot and the difference is the inherited
same-target or occupation reservation reacting to an earlier unit's changed choice; otherwise unexplained. Each
changed decision gets one category: C7 if anything is unexplained or an oracle check fails, else C6 if any unit is
secondary, else C5 if two or more units are direct, else C1 to C4 by the one direct unit's outcome. Nothing here
imports the candidate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import Observation, Origin
from ..decision import Decision, Memory
from .shoot_counterfactual import is_candidate_option

SHOOT, OCCUPY, MOVE = 2, 5, 1
LAUNCHER_REASON = "same-step-launcher-target-reserved"
SHOOT_REASON = "same-step-shoot-target-reserved"
OBJECTIVE_REASON = "same-step-objective-reserved"
CATEGORIES = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
CATEGORY_OF_RULE = {"engage": "C1", "occupy": "C2", "move": "C3", "none": "C4"}
EFFECT_OF_RULE = {"engage": "alternate-target", "occupy": "fallback-occupy", "move": "fallback-move",
                  "none": "fallback-none"}
MARKERS = ("launcher_target_reserved", "launcher_reservation")
MALFORMED = "malformed launcher relation skipped"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def relations(raw: Mapping[str, Any]) -> Dict[int, int]:
    """obj_id -> launcher id for the observation's operators whose ``launcher`` is an int."""
    return {u["obj_id"]: u["launcher"] for u in raw.get("operators") or ()
            if isinstance(u, Mapping) and _is_int(u.get("launcher")) and _is_int(u.get("obj_id"))}


def reserved_before(decision: Decision) -> Dict[int, Set[int]]:
    order = [unit.obj_id for unit in decision.trace.units]
    shots = {a["obj_id"]: a["target_obj_id"] for a in decision.actions if int(a["type"]) == SHOOT}
    result, seen = {}, set()
    for obj_id in order:
        result[obj_id] = set(seen)
        if obj_id in shots:
            seen.add(shots[obj_id])
    return result


def withdraw(raw: Mapping[str, Any], reserved: Mapping[int, Set[int]], launchers: Mapping[int, int]
             ) -> Tuple[Dict[str, Any], Dict[int, List[Tuple[int, int, int, int]]]]:
    """A copy without each unit's dependent-target options, and the withdrawn (target, launcher, weapon, level)."""
    result = copy.deepcopy(dict(raw))
    withdrawn: Dict[int, List[Tuple[int, int, int, int]]] = {}
    for key, per_unit in result["valid_actions"].items():
        targets = reserved.get(int(key))
        if not targets:
            continue
        for action_key in [k for k in per_unit if int(k) == SHOOT]:
            options = per_unit[action_key]
            if not isinstance(options, list):
                continue
            kept = []
            for option in options:
                if (is_candidate_option(option) and option["target_obj_id"] not in targets
                        and launchers.get(option["target_obj_id"]) in targets):
                    withdrawn.setdefault(int(key), []).append((option["target_obj_id"], launchers[option["target_obj_id"]],
                                                               option["weapon_id"], option["attack_level"]))
                else:
                    kept.append(option)
            per_unit[action_key] = kept
    return result, withdrawn


def _by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    return {action.get("obj_id", "seat"): dict(action) for action in actions}


def _normalized_candidate(payload: Dict[str, Any], withdrawn_counts: Mapping[int, int]) -> Dict[str, Any]:
    payload = copy.deepcopy(payload)
    for key in ("policy", "schema", "launcher_reserved"):
        payload.pop(key, None)
    payload["diagnostics"] = [d for d in payload["diagnostics"] if MALFORMED not in d]
    for unit in payload["units"]:
        for marker in MARKERS:
            unit["detail"].pop(marker, None)
        if unit["obj_id"] in withdrawn_counts:
            unit["candidates"]["engage"] -= withdrawn_counts[unit["obj_id"]]
    return payload


def _normalized_oracle(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(payload)
    for key in ("policy", "schema"):
        payload.pop(key, None)
    return payload


def expected_no_op_reason(oracle_reason: Optional[str]) -> Optional[str]:
    """The candidate's reason for a unit displaced by the launcher rule and left without action."""
    if oracle_reason is None:
        return None
    launcher = f"launcher targets reserved: {LAUNCHER_REASON}; "
    if oracle_reason.startswith("no candidate; "):
        return launcher + oracle_reason[len("no candidate; "):]
    if oracle_reason.startswith(f"shoot targets reserved: {SHOOT_REASON}; "):
        head = f"shoot targets reserved: {SHOOT_REASON}; "
        return head + launcher + oracle_reason[len(head):]
    if oracle_reason.startswith("occupation suppressed: "):
        return launcher + oracle_reason
    return None


@dataclass
class LauncherComparison:
    identical: bool
    explained: bool
    category: Optional[str] = None
    units: Dict[str, int] = field(default_factory=dict)
    direct: List[Dict[str, Any]] = field(default_factory=list)
    excluded_options: int = 0
    unchanged_units_with_exclusions: int = 0
    baseline_shots: int = 0
    candidate_shots: int = 0
    changed_types: Tuple[int, ...] = ()
    problem: Optional[str] = None


def compare(raw: Mapping[str, Any], seat: int, faction: int, baseline: Any, candidate: Any, oracle_factory: Any,
            memory: Memory, origin: Origin = Origin.ENGINE) -> Tuple[LauncherComparison, Decision, Decision]:
    """Compare one decision. ``oracle_factory()`` builds a fresh baseline-v2 policy."""
    first = baseline.decide(Observation.from_raw(raw, origin), seat, faction, memory)
    second = candidate.decide(Observation.from_raw(raw, origin), seat, faction, memory)
    old, new = _by_unit(first.actions), _by_unit(second.actions)
    record = {entry["obj_id"]: entry for entry in second.trace.to_dict().get("launcher_reserved", [])}
    result = LauncherComparison(
        identical=tuple(first.actions) == tuple(second.actions), explained=True,
        units={"alternate-target": 0, "fallback-occupy": 0, "fallback-move": 0, "fallback-none": 0, "secondary": 0,
               "unexplained": 0},
        excluded_options=sum(len(e["excluded"]) for e in record.values()),
        unchanged_units_with_exclusions=sum(1 for e in record.values() if e["effect"] == "unchanged"),
        baseline_shots=sum(1 for a in first.actions if int(a["type"]) == SHOOT),
        candidate_shots=sum(1 for a in second.actions if int(a["type"]) == SHOOT),
        changed_types=tuple(sorted({int(a["type"]) for k, a in old.items() if new.get(k) != a})))

    def fail(problem: str) -> Tuple[LauncherComparison, Decision, Decision]:
        result.explained = False
        result.problem = problem
        result.category = "C7" if not result.identical else None
        return result, first, second

    if first.memory != second.memory:
        return fail("memory differs")
    if first.trace.stage != 2:
        if not result.identical or record:
            return fail("the candidate differs outside the play stage")
        return result, first, second
    launchers = relations(raw)
    reserved = reserved_before(second)
    filtered, withdrawn = withdraw(raw, reserved, launchers)
    oracle = oracle_factory().decide(Observation.from_raw(filtered, origin), seat, faction, memory)
    if tuple(oracle.actions) != tuple(second.actions):
        return fail("actions differ from the oracle")
    listed = {unit: sorted((e["target_obj_id"], e["launcher"], e["weapon_id"], e["attack_level"])
                           for e in entry["excluded"]) for unit, entry in record.items()}
    if listed != {unit: sorted(options) for unit, options in withdrawn.items()}:
        return fail("the recorded exclusions differ from the withdrawn options")
    proposals = [a for a in second.actions]
    for entry in record.values():
        for e in entry["excluded"]:
            position = e["reserved_by_position"]
            if not (0 <= position < len(proposals) and proposals[position].get("obj_id") == e["reserved_by"]
                    and proposals[position].get("target_obj_id") == e["launcher"]):
                return fail("a recorded launcher shot is not the proposal at its recorded position")
    expected = _normalized_candidate(second.trace.to_dict(), {u: len(o) for u, o in withdrawn.items()})
    actual = _normalized_oracle(oracle.trace.to_dict())
    for unit in expected["units"]:
        entry = record.get(unit["obj_id"])
        if entry is not None and entry["effect"] == "fallback-none":
            oracle_unit = next((u for u in actual["units"] if u["obj_id"] == unit["obj_id"]), None)
            if oracle_unit is None or unit["no_op_reason"] != expected_no_op_reason(oracle_unit["no_op_reason"]):
                return fail(f"no-op reason of unit {unit['obj_id']} does not match the oracle")
            unit["no_op_reason"] = oracle_unit["no_op_reason"]
    if expected != actual:
        return fail("trace differs from the oracle")
    units = {unit.obj_id: unit for unit in second.trace.units}
    candidate_payload = second.trace.to_dict()
    changed_shots = {k for k, a in new.items() if int(a["type"]) == SHOOT and old.get(k) != a}
    fallback_occupy = {u for u, e in record.items() if e["effect"] == "fallback-occupy"}
    secondary = 0
    for key in sorted(set(old) | set(new), key=str):
        if old.get(key) == new.get(key):
            continue
        if key == "seat":
            return fail("a deployment action differs")
        before = old.get(key)
        if (before is not None and int(before["type"]) == SHOOT and before["target_obj_id"] not in reserved.get(key, set())
                and launchers.get(before["target_obj_id"]) in reserved.get(key, set())):
            rule = units[key].rule
            entry = record.get(key)
            if entry is None or entry["effect"] != EFFECT_OF_RULE[rule]:
                return fail(f"unit {key}: displaced but recorded as {None if entry is None else entry['effect']}")
            result.units[EFFECT_OF_RULE[rule]] += 1
            result.direct.append({"unit": key, "suppressed": before, "outcome": EFFECT_OF_RULE[rule],
                                  "launcher": launchers[before["target_obj_id"]]})
            continue
        shoot_entry = next((e for e in candidate_payload["shoot_reserved"] if e["obj_id"] == key), None)
        if (before is not None and int(before["type"]) == SHOOT and before["target_obj_id"] in reserved.get(key, set())
                and shoot_entry is not None and any(e["reserved_by"] in changed_shots for e in shoot_entry["excluded"])):
            secondary += 1  # the inherited shoot-target reservation reacting to an earlier unit's changed shot
            continue
        suppression = [s for s in candidate_payload["suppressed"] if s["obj_id"] == key]
        if (before is not None and int(before["type"]) == OCCUPY and suppression
                and suppression[0]["reserved_by"] in fallback_occupy):
            secondary += 1  # the inherited occupation reservation reacting to an earlier fallback occupation
            continue
        result.units["unexplained"] += 1
        return fail(f"unit {key}: unexplained difference")
    result.units["secondary"] = secondary
    if not result.identical:
        direct = len(result.direct)
        result.category = ("C6" if secondary else "C5" if direct >= 2
                           else CATEGORY_OF_RULE[{v: k for k, v in EFFECT_OF_RULE.items()}[result.direct[0]["outcome"]]]
                           if direct == 1 else "C7")
        if result.category == "C7":
            result.explained = False
            result.problem = "actions differ without a direct or secondary unit"
    return result, first, second
