"""Counterfactual comparison of baseline-v1 on runtime r1 and the shoot-target-reservation candidate on one input.

Both policies decide on the same canonical start-of-step observation. The registered change predicts the
candidate's output exactly, through an oracle that does not use the candidate's code:

* ``R(u)``, for each unit ``u`` in processing order, is the set of targets of the shoot actions the candidate
  emitted for units processed before ``u`` (read off the candidate's output);
* the oracle is baseline-v1 on runtime r1 deciding on a copy of the observation in which every unit ``u``
  no longer offers the shoot options whose target is in ``R(u)`` (only options that are shoot candidates:
  well-formed and at or above the minimum attack level; anything else is left, so diagnostics are equal;
  the shoot type stays listed, possibly with no option, as it is for the candidate);
* the candidate's actions must equal the oracle's; its memory must equal the baseline's; its record of
  excluded options must list exactly the withdrawn options; and its trace must equal the oracle's apart from
  the policy name, the trace schema, the shoot-reservation record, the two reservation markers of a displaced
  unit, the engage count (the candidate counts the offered options, the oracle what remains, so they must
  differ by exactly the excluded options) and the no-op reason of a unit left without action (the candidate
  names the reservation where the oracle says "no candidate").

Every unit whose action differs from the baseline's is classified:

* ``A`` its baseline selection shoots a target in ``R(u)``, and the candidate shoots another target;
* ``B`` / ``C`` / ``D`` the same baseline selection, and the candidate occupies / moves / does nothing;
* ``I`` induced: its baseline selection is not a shoot at a target in ``R(u)``, and the difference is the
  inherited same-step occupation reservation reacting to an earlier unit that fell back to occupation;
* ``E`` anything else: unexplained.

A state with an ``E`` unit, or failing any oracle check, is unexplained. Nothing here imports the candidate.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import Observation, Origin
from ..decision import Decision, Memory
from ..decision.semantics import MIN_ATTACK_LEVEL

SHOOT, OCCUPY, MOVE = 2, 5, 1
RESERVED_REASON = "same-step-shoot-target-reserved"
CLASSES = ("A", "B", "C", "D", "I", "E")
EFFECT_OF_CLASS = {"A": "alternate-target", "B": "fallback-occupy", "C": "fallback-move", "D": "fallback-none"}
CLASS_OF_RULE = {"engage": "A", "occupy": "B", "move": "C", "none": "D"}
MARKERS = ("shoot_target_reserved", "shoot_reservation")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_candidate_option(option: Any) -> bool:
    """Whether a listed shoot option becomes a shoot candidate (the rule of ``engage_candidates``)."""
    if not isinstance(option, Mapping):
        return False
    values = [option.get(name) for name in ("target_obj_id", "weapon_id", "attack_level")]
    return all(_is_int(v) for v in values) and values[2] >= MIN_ATTACK_LEVEL


def reserved_before(decision: Decision) -> Dict[int, Set[int]]:
    """``R(u)`` for every unit of the step, from the candidate's emitted actions and processing order."""
    order = [unit.obj_id for unit in decision.trace.units]
    shots = {a["obj_id"]: a["target_obj_id"] for a in decision.actions if int(a["type"]) == SHOOT}
    result, seen = {}, set()
    for obj_id in order:
        result[obj_id] = set(seen)
        if obj_id in shots:
            seen.add(shots[obj_id])
    return result


def withdraw(raw: Mapping[str, Any], reserved: Mapping[int, Set[int]]) -> Tuple[Dict[str, Any], Dict[int, List[Tuple[int, int, int]]]]:
    """A copy of ``raw`` without each unit's shoot options on its reserved targets, and the withdrawn options."""
    result = copy.deepcopy(dict(raw))
    withdrawn: Dict[int, List[Tuple[int, int, int]]] = {}
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
                if is_candidate_option(option) and option["target_obj_id"] in targets:
                    withdrawn.setdefault(int(key), []).append(
                        (option["target_obj_id"], option["weapon_id"], option["attack_level"]))
                else:
                    kept.append(option)
            per_unit[action_key] = kept  # the type stays listed, as it is for the candidate
    return result, withdrawn


def _by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    return {action.get("obj_id", "seat"): dict(action) for action in actions}


def _normalized_candidate(payload: Dict[str, Any], excluded_counts: Mapping[int, int]) -> Dict[str, Any]:
    payload = copy.deepcopy(payload)
    for key in ("policy", "schema", "shoot_reserved"):
        payload.pop(key, None)
    for unit in payload["units"]:
        for marker in MARKERS:
            unit["detail"].pop(marker, None)
        if unit["obj_id"] in excluded_counts:
            unit["candidates"]["engage"] -= excluded_counts[unit["obj_id"]]
    return payload


def _normalized_oracle(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = copy.deepcopy(payload)
    for key in ("policy", "schema"):
        payload.pop(key, None)
    return payload


def expected_no_op_reason(oracle_reason: Optional[str]) -> Optional[str]:
    """The candidate's reason for a displaced unit left without action, given the oracle's reason."""
    if oracle_reason is None:
        return None
    prefix = f"shoot targets reserved: {RESERVED_REASON}; "
    if oracle_reason.startswith("no candidate; "):
        return prefix + oracle_reason[len("no candidate; "):]
    if oracle_reason.startswith("occupation suppressed: "):
        return prefix + oracle_reason
    return None


@dataclass
class ShootComparison:
    identical: bool
    explained: bool
    classes: Dict[str, int] = field(default_factory=dict)
    baseline_shots: int = 0
    baseline_duplicate_shots: int = 0
    candidate_shots: int = 0
    candidate_duplicate_shots: int = 0
    displaced_units: int = 0
    unchanged_units_with_exclusions: int = 0
    excluded_options: int = 0
    first_shot_changed: bool = False
    non_shoot_differences: int = 0
    changed_types: Tuple[int, ...] = ()
    problem: Optional[str] = None


def duplicates(actions: Sequence[Mapping[str, Any]]) -> Tuple[int, int]:
    """(shoot actions, shoot actions whose target an earlier shoot action of the step already has)."""
    targets = [a.get("target_obj_id") for a in actions if int(a["type"]) == SHOOT]
    return len(targets), len(targets) - len(set(targets))


def compare(raw: Mapping[str, Any], seat: int, faction: int, baseline: Any, candidate: Any, oracle_factory: Any,
            baseline_memory: Memory, candidate_memory: Memory,
            origin: Origin = Origin.ENGINE) -> Tuple[ShootComparison, Decision, Decision]:
    """Compare one decision. ``oracle_factory()`` builds a fresh baseline-v1 policy on runtime r1."""
    first = baseline.decide(Observation.from_raw(raw, origin), seat, faction, baseline_memory)
    second = candidate.decide(Observation.from_raw(raw, origin), seat, faction, candidate_memory)
    old, new = _by_unit(first.actions), _by_unit(second.actions)
    shots_old, dup_old = duplicates(first.actions)
    shots_new, dup_new = duplicates(second.actions)
    record = {entry["obj_id"]: entry for entry in second.trace.to_dict().get("shoot_reserved", [])}
    result = ShootComparison(identical=tuple(first.actions) == tuple(second.actions), explained=True,
                             classes={c: 0 for c in CLASSES}, baseline_shots=shots_old, baseline_duplicate_shots=dup_old,
                             candidate_shots=shots_new, candidate_duplicate_shots=dup_new,
                             displaced_units=sum(1 for e in record.values() if e["effect"] != "unchanged"),
                             unchanged_units_with_exclusions=sum(1 for e in record.values() if e["effect"] == "unchanged"),
                             excluded_options=sum(len(e["excluded"]) for e in record.values()),
                             changed_types=tuple(sorted({int(a["type"]) for k, a in old.items() if new.get(k) != a})))

    def fail(problem: str) -> Tuple[ShootComparison, Decision, Decision]:
        result.explained = False
        result.problem = problem
        return result, first, second

    first_old = next((a for a in first.actions if int(a["type"]) == SHOOT), None)
    first_new = next((a for a in second.actions if int(a["type"]) == SHOOT), None)
    result.first_shot_changed = first_old != first_new and first_old is not None
    if first.memory != second.memory:
        return fail("memory differs")
    if dup_new:
        return fail("the candidate emitted two shoot actions at one target")
    if first.trace.stage != 2:
        if not result.identical or record:
            return fail("the candidate differs outside the play stage")
        return result, first, second
    reserved = reserved_before(second)
    filtered, withdrawn = withdraw(raw, reserved)
    oracle = oracle_factory().decide(Observation.from_raw(filtered, origin), seat, faction, baseline_memory)
    if tuple(oracle.actions) != tuple(second.actions):
        return fail("actions differ from the oracle")
    listed = {unit: sorted((e["target_obj_id"], e["weapon_id"], e["attack_level"]) for e in entry["excluded"])
              for unit, entry in record.items()}
    if listed != {unit: sorted(options) for unit, options in withdrawn.items()}:
        return fail("the recorded exclusions differ from the withdrawn options")
    candidate_payload = second.trace.to_dict()
    expected = _normalized_candidate(candidate_payload, {u: len(o) for u, o in withdrawn.items()})
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
    fell_back_to_occupy = {u for u, e in record.items() if e["effect"] == "fallback-occupy"}
    for key in sorted(set(old) | set(new), key=str):
        if old.get(key) == new.get(key):
            continue
        before = old.get(key)
        if key == "seat":
            return fail("a deployment action differs")
        reserved_shot = (before is not None and int(before["type"]) == SHOOT
                         and before["target_obj_id"] in reserved.get(key, set()))
        if reserved_shot:
            label = CLASS_OF_RULE[units[key].rule]
            entry = record.get(key)
            if entry is None or entry["effect"] != EFFECT_OF_CLASS[label]:
                return fail(f"unit {key}: displaced but recorded as {None if entry is None else entry['effect']}")
            result.classes[label] += 1
            continue
        detail = dict(units[key].detail) if key in units else {}
        suppression = [s for s in candidate_payload["suppressed"] if s["obj_id"] == key]
        if (before is not None and int(before["type"]) == OCCUPY and suppression
                and suppression[0]["reserved_by"] in fell_back_to_occupy
                and (units[key].rule != "occupy") and (detail.get("suppressed") or units[key].no_op_reason)):
            result.classes["I"] += 1
            result.non_shoot_differences += 1
            continue
        result.classes["E"] += 1
        result.non_shoot_differences += 1
        return fail(f"unit {key}: unexplained difference")
    return result, first, second
