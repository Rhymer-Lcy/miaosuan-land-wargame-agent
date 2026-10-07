"""Sprint 21 direct-fire adjudication-semantics audit (``docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md``): pure functions.

The audit asks whether existing runtime records of engine 4.1.0 identify the immediate direct-fire adjudication well
enough to define ``P(immediate target destruction | current observed target state, listed direct-fire option)``
without fitting a model and without an unsupported rule assumption. Four questions decide it (section 3 of the
registration): K2, whether a listed ``attack_level`` is the level the engine adjudicates with; K4, the random
mechanism, split into the deterministic table mapping and the probability law; K5, how ``ori_damage``,
``rect_damage`` and ``damage`` combine; K6, how damage, blood and removal relate per target class.

Everything here is a pure function of rows the driver (``scripts/s21_semantics.py``) builds from the frozen corpus:
pairing of submitted shots with engine feedback and ``judge_info`` records, the published result tables as
transcribed from the documentation snapshot, the registered K5 relations, the K6 tests, the per-class sufficiency rule
and the first-match disposition. No function here reads an engine, fits a probability or uses a frequency as evidence
of a law.
"""

from __future__ import annotations

import collections
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

STUDY_ID = "s21-direct-fire-semantics"
SNAPSHOT = "local/source-archives/docs-live-snapshot-20260929"
#: SHA-256 of the snapshot files this audit reads (from the snapshot's own ``SHA256SUMS``); the snapshot is local and
#: not redistributed.
SNAPSHOT_FILES_SHA256 = {
    "reference_observations.txt": "04a779ac5c6717f820213c6d886ee87097b5936ee4535d62e8c9000579ab71fa",
    "rules_tables.html": "07d3fff0a7897fa2b7bb25a73965ae786cd97f82107b6d62436274e68cbe73f8",
    "rules_tables.txt": "b153352372678e72959034c3a250edcb5f7efa3c467b987dec3876446618a930",
}
SHOOT = 2
#: The ``type`` text of a direct-fire judge record (public observation reference).
DIRECT_FIRE_TYPE = "直瞄射击"

# ------------------------------------------------------------------------------------------------
# Target classes (section 12): by the observed ``type`` field (public reference: 1 personnel, 2 vehicle, 3 aircraft,
# 4 fortification, 5 strategic support)

INFANTRY, VEHICLE, AIRCRAFT, FORTIFICATION, OTHER = "infantry", "vehicle", "aircraft", "fortification", "other"
TARGET_CLASSES = (INFANTRY, VEHICLE, AIRCRAFT, FORTIFICATION, OTHER)
CLASS_BY_TYPE = {1: INFANTRY, 2: VEHICLE, 3: AIRCRAFT, 4: FORTIFICATION}


def unit_class(unit: Optional[Mapping[str, Any]]) -> str:
    if not unit:
        return OTHER
    value = unit.get("type")
    if isinstance(value, bool) or not isinstance(value, int):
        return OTHER
    return CLASS_BY_TYPE.get(value, OTHER)


def class_of_label(label: str) -> str:
    """The class of a Sprint 20 public class label ``"type N sub M"``."""
    parts = label.split()
    if len(parts) != 4 or parts[0] != "type" or parts[2] != "sub" or not parts[1].lstrip("-").isdigit():
        raise ValueError(f"not a class label: {label}")
    return CLASS_BY_TYPE.get(int(parts[1]), OTHER)


def required_classes(hh_pooled: Mapping[str, Any]) -> List[str]:
    """Every target class on either side of a Sprint 20 HH changed shot (root and induced): section 13."""
    classes = set()
    for block in ("root_switches", "induced_changed_shots"):
        for pair, n in ((hh_pooled.get(block) or {}).get("target_class_pairs") or {}).items():
            if n:
                before, after = pair.split(" -> ")
                classes.update((class_of_label(before), class_of_label(after)))
    return [c for c in TARGET_CLASSES if c in classes]


def labelled(label: str, value: Any) -> str:
    """A public key for a numeric value: ``blood_2``, ``difference_minus_1`` (never a bare number; section 21)."""
    if isinstance(value, bool) or value is None:
        return f"{label}_{value}".lower()
    if isinstance(value, int) and value < 0:
        return f"{label}_minus_{-value}"
    return f"{label}_{value}"


def label_counts(values: Iterable[Any], label: str) -> Dict[str, int]:
    counts = collections.Counter(labelled(label, v) for v in values)
    return dict(sorted(counts.items()))


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ------------------------------------------------------------------------------------------------
# The published direct-fire result tables (documentation snapshot of 2026-09-29, ``rules_tables.html``), transcribed.
# A workstation test parses the snapshot's HTML again and compares every cell (``tests/test_s21_semantics.py``).
# Cell kinds: a number of squads or vehicles eliminated, suppression, annihilation, or no effect (an empty cell).

NUMERIC, SUPPRESSION, ANNIHILATION, NO_EFFECT = "numeric", "suppression", "annihilation", "no_effect"
OUT_OF_TABLE, NO_TABLE = "out_of_table", "no_table"
S, A = "S", "A"
PERSONNEL_TABLE, VEHICLE_TABLE, AIR_TABLE = "personnel_result_table", "vehicle_result_table", "air_result_table"
#: Weapon id of the infantry light weapon (public weapon reference); against vehicles it reads the personnel table.
INFANTRY_LIGHT_WEAPON = 29

#: 直瞄武器对人员/步兵轻武器对车辆战斗结果表: random number -> cells for attack levels 1 to 10.
PERSONNEL_RESULT: Dict[int, Tuple[Any, ...]] = {
    2: (S, S, S, S, 1, 2, 2, 2, 2, 2),
    3: (None, S, S, S, S, 1, 1, 1, 1, 1),
    4: (None, None, S, S, S, S, S, 1, 1, 1),
    5: (None, None, None, None, S, S, S, S, 1, 1),
    6: (None, None, None, None, None, S, S, S, S, S),
    7: (None, None, None, None, None, None, S, S, S, S),
    8: (None, None, None, None, None, None, S, S, S, S),
    9: (None, None, None, None, None, S, S, S, S, 1),
    10: (None, None, None, S, S, S, S, S, 1, 1),
    11: (None, S, S, S, S, S, S, 1, 1, 2),
    12: (S, S, S, S, S, 1, 2, 2, 2, 2),
}
#: 对车辆单位战斗结果, upper part: shooter count (车/班数) -> the attack level in each of the 20 result columns.
VEHICLE_COLUMNS: Dict[int, Tuple[Optional[int], ...]] = {
    1: (1, None, 2, 3, 4, 5, 6, 7, 8, None, 9, 10, None, None, None, None, None, None, None, None),
    2: (None, 1, None, 2, None, 3, 4, 5, 6, 7, None, 8, 9, 10, None, None, None, None, None, None),
    3: (None, None, 1, None, 2, None, 3, 4, None, 5, None, 6, 7, 8, 9, 10, None, None, None, None),
    4: (None, None, 1, None, 2, None, 3, None, 4, None, 5, None, 6, 7, 8, None, 9, 10, None, None),
    5: (None, None, 1, None, 2, None, None, None, 3, None, 4, None, None, 5, 6, 7, None, 8, 9, 10),
}
#: 对车辆单位战斗结果, lower part: random number -> the result in each of the 20 columns.
VEHICLE_RESULT: Dict[int, Tuple[Optional[int], ...]] = {
    2: (1, None, None, None, None, None, 1, 1, 1, 1, 1, 1, 1, 1, 2, 3, 3, 2, 3, 5),
    3: (None, None, None, 1, None, None, 1, None, None, 1, 1, 1, 1, 1, 2, 3, 3, 2, 1, 1),
    4: (None, 1, None, 1, 1, None, None, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    5: (None, None, None, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    6: (None, None, None, None, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 5),
    7: (None, None, 1, None, None, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 4, 3, 4, 3),
    8: (None, None, None, None, None, None, None, 1, 1, 1, None, None, 2, 2, 2, 2, 2, 4, 4, 4),
    9: (None, None, None, None, None, None, None, None, None, 1, 2, 2, 2, 2, 2, 2, 2, 4, 3, 4),
    10: (None, None, None, None, None, None, None, None, None, None, None, 1, 2, 2, 2, 2, 2, 4, 4, 4),
    11: (None, None, None, None, None, None, None, None, None, None, 2, 2, None, None, 2, 3, 3, 2, 2, 3),
    12: (None, None, None, None, None, None, None, None, None, None, None, None, None, 1, 2, 3, 3, 3, 2, 4),
}
#: 空战斗结果表: random number -> cells for attack levels 1 to 11 (A = 歼灭, annihilation).
AIR_RESULT: Dict[int, Tuple[Any, ...]] = {
    2: (A, A, A, A, A, A, A, A, A, A, A),
    3: (None, None, A, A, A, A, A, A, A, A, A),
    4: (None, None, None, None, A, A, A, A, A, A, A),
    5: (None, None, None, None, None, None, A, A, A, A, A),
    6: (None, None, None, None, None, None, None, None, A, A, A),
    7: (None, None, None, None, None, None, None, None, None, None, A),
    8: (None, None, None, None, None, None, None, None, None, A, A),
    9: (None, None, None, None, None, None, None, A, A, A, A),
    10: (None, None, None, None, None, A, A, A, A, A, A),
    11: (None, None, None, A, A, A, A, A, A, A, A),
    12: (None, A, A, A, A, A, A, A, A, A, A),
}
#: 车辆战损结果修正, right part: modified random number bins -> correction per armour, in the observation's ``armor``
#: order (0 none, 1 light, 2 medium, 3 heavy, 4 composite); an empty cell is a correction of 0.
VEHICLE_CORRECTION_BINS: Tuple[Tuple[Optional[int], Optional[int], Tuple[int, int, int, int, int]], ...] = (
    (None, -3, (0, -1, -2, -3, -3)),
    (-2, -1, (0, 0, -1, -2, -3)),
    (0, 0, (0, 0, 0, -1, -3)),
    (1, 1, (0, 0, 0, -1, -2)),
    (2, 2, (0, 0, 0, 0, -2)),
    (3, 5, (1, 0, 0, 0, -1)),
    (6, 8, (1, 1, 0, 0, 0)),
    (9, 9, (1, 1, 1, 0, 0)),
    (10, 10, (2, 2, 1, 1, 0)),
    (11, 11, (2, 2, 2, 2, 1)),
    (12, None, (3, 3, 3, 2, 2)),
)


def personnel_correction(modified: int) -> int:
    """人员战损结果修正: modified random number <= 0 -> -1, 1 to 7 -> 0, >= 8 -> +1."""
    return -1 if modified <= 0 else (0 if modified <= 7 else 1)


def vehicle_correction(modified: int, armor: int) -> Optional[int]:
    if not is_int(armor) or not 0 <= armor <= 4:
        return None
    for low, high, row in VEHICLE_CORRECTION_BINS:
        if (low is None or modified >= low) and (high is None or modified <= high):
            return row[armor]
    return None


def _cell(value: Any) -> Tuple[str, Optional[int]]:
    if value is None:
        return NO_EFFECT, None
    if value == S:
        return SUPPRESSION, None
    if value == A:
        return ANNIHILATION, None
    return NUMERIC, value


def raw_cell(target_class: str, weapon: Any, att_level: Any, random1: Any, shooter_count: Any) -> Tuple[str, str, Optional[int]]:
    """The published raw result for one adjudication: (table, kind, number). Table choice (section 10): a personnel
    target reads the personnel table; a vehicle or fortification target reads the vehicle table with the shooter's
    count, except the infantry light weapon, which reads the personnel table; an aircraft reads the air table; any other
    class has no table. Inputs outside a table's rows or columns give ``out_of_table``."""
    if target_class == INFANTRY:
        table = PERSONNEL_TABLE
    elif target_class in (VEHICLE, FORTIFICATION):
        table = PERSONNEL_TABLE if weapon == INFANTRY_LIGHT_WEAPON else VEHICLE_TABLE
    elif target_class == AIRCRAFT:
        table = AIR_TABLE
    else:
        return NO_TABLE, NO_TABLE, None
    if not is_int(att_level) or not is_int(random1):
        return table, OUT_OF_TABLE, None
    if table == PERSONNEL_TABLE:
        row = PERSONNEL_RESULT.get(random1)
        if row is None or not 1 <= att_level <= len(row):
            return table, OUT_OF_TABLE, None
        return (table, *_cell(row[att_level - 1]))
    if table == AIR_TABLE:
        row = AIR_RESULT.get(random1)
        if row is None or not 1 <= att_level <= len(row):
            return table, OUT_OF_TABLE, None
        return (table, *_cell(row[att_level - 1]))
    columns = VEHICLE_COLUMNS.get(shooter_count) if is_int(shooter_count) else None
    row = VEHICLE_RESULT.get(random1)
    if columns is None or row is None or att_level not in columns:
        return table, OUT_OF_TABLE, None
    return (table, *_cell(row[columns.index(att_level)]))


def correction_table(target_class: str, weapon: Any) -> Optional[str]:
    """The published correction table: personnel targets the personnel correction; vehicle and fortification targets
    the vehicle correction (the infantry light weapon too: rules, same-hex section); aircraft none."""
    if target_class == INFANTRY:
        return "personnel_correction"
    if target_class in (VEHICLE, FORTIFICATION):
        return "vehicle_correction"
    return None


# ------------------------------------------------------------------------------------------------
# Pairing (section 7): submitted shots, the engine's feedback and the step's judge_info records

PAIRED, AMBIGUOUS, ACCEPTED_NO_RECORD, REFUSED, REFUSED_WITH_RECORD, ACCEPTANCE_UNKNOWN = (
    "paired", "ambiguous", "accepted_no_record", "refused", "refused_with_record", "acceptance_unknown")
#: Statuses of a submitted shot that break pairing integrity (section 8).
INTEGRITY_FAILURES = (ACCEPTED_NO_RECORD, REFUSED_WITH_RECORD, ACCEPTANCE_UNKNOWN)
CLAIMED_TWICE = "record_claimed_by_more_than_one_accepted_shot"
RECORD_PAIRED, RECORD_AMBIGUOUS, RECORD_UNMATCHED = "paired", "ambiguous_group", "unmatched"
RECORD_SAME_HEX, RECORD_UNEXPLAINED = "same_hex_engagement", "unexplained"
#: Every integrity failure kind of sections 7 and 8; any one of them makes the audit invalid.
PROBLEM_KINDS = INTEGRITY_FAILURES + (
    CLAIMED_TWICE, "paired_record_cur_step_differs", "paired_record_colours_disagree", "shooter_or_target_not_in_pre_state",
    "shooting_seat_observation_missing", "missing_snapshot_or_final_state", "removed_units_disagree_with_snapshots",
    "unpaired_record_not_same_hex", "judge_record_of_another_type")


def shot_key(action: Mapping[str, Any]) -> Tuple[Any, Any, Any]:
    return action.get("obj_id"), action.get("target_obj_id"), action.get("weapon_id")


def record_key(record: Mapping[str, Any]) -> Tuple[Any, Any, Any]:
    return record.get("att_obj_id"), record.get("target_obj_id"), record.get("wp_id")


def pair_step(submitted: Sequence[Mapping[str, Any]], feedback: Sequence[Mapping[str, Any]],
              records: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Pairs one step. ``submitted``: the pre-execution copies ``{"seat", "faction", "j", "action"}``; ``feedback``: the
    engine's echoes ``{"message", "error"?}`` of the step; ``records``: the step's new direct-fire judge records.

    A shot is accepted when exactly one echo of a shoot action has its actor (seat), unit, target and weapon and carries
    no error, refused when that echo carries an error; otherwise acceptance is unknown. An accepted shot is paired with
    the records naming its unit, target and weapon: exactly one -> ``paired``, none -> ``accepted_no_record``, more ->
    ``ambiguous`` (excluded and counted). A record is never paired twice: a record that matches more than one accepted
    shot makes all of them ambiguous. A refused shot must have no matching record."""
    echoes: Dict[Tuple[Any, ...], List[Mapping[str, Any]]] = collections.defaultdict(list)
    for entry in feedback or ():
        message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
        if message.get("type") == SHOOT:
            echoes[(message.get("actor"),) + shot_key(message)].append(entry)
    by_key: Dict[Tuple[Any, Any, Any], List[int]] = collections.defaultdict(list)
    for i, record in enumerate(records or ()):
        by_key[record_key(record)].append(i)
    shots: List[Dict[str, Any]] = []
    submitted_keys = collections.Counter((e.get("seat"),) + shot_key(e.get("action") or {}) for e in submitted or ()
                                         if (e.get("action") or {}).get("type") == SHOOT)
    for entry in submitted or ():
        action = entry.get("action") or {}
        if action.get("type") != SHOOT:
            continue
        key = (entry.get("seat"),) + shot_key(action)
        found = echoes.get(key, [])
        if len(found) != 1 or submitted_keys[key] != 1:
            status = ACCEPTANCE_UNKNOWN
        else:
            status = REFUSED if found[0].get("error") else "accepted"
        shots.append({"seat": entry.get("seat"), "faction": entry.get("faction"), "j": entry.get("j"),
                      "obj_id": action.get("obj_id"), "target": action.get("target_obj_id"),
                      "weapon": action.get("weapon_id"), "status": status, "records": list(by_key.get(shot_key(action), []))})
    claims = collections.Counter(i for s in shots if s["status"] == "accepted" for i in s["records"])
    record_status = [RECORD_UNMATCHED] * len(records or ())
    for s in shots:
        matched = s["records"]
        if s["status"] == REFUSED:
            if matched:
                s["status"] = REFUSED_WITH_RECORD
            continue
        if s["status"] != "accepted":
            continue
        if not matched:
            s["status"] = ACCEPTED_NO_RECORD
        elif len(matched) == 1 and claims[matched[0]] == 1:
            s["status"] = PAIRED
            record_status[matched[0]] = RECORD_PAIRED
        else:
            s["status"] = AMBIGUOUS
            for i in matched:
                record_status[i] = RECORD_AMBIGUOUS
    problems = [(s["status"], f"shot j{s['j']} of seat {s['seat']}") for s in shots if s["status"] in INTEGRITY_FAILURES]
    problems += [(CLAIMED_TWICE, f"record {i} claimed by {n} accepted shots") for i, n in sorted(claims.items()) if n > 1]
    return {"shots": shots, "record_status": record_status, "problems": problems}


def listed_level(valid_actions: Mapping[Any, Any], obj_id: Any, target: Any, weapon: Any) -> Tuple[str, Optional[int]]:
    """The listed ``attack_level`` of the option (target, weapon) of a unit in its seat's ``valid_actions``:
    (``listed`` | ``missing`` | ``ambiguous``, level)."""
    acts = None
    for key, value in (valid_actions or {}).items():
        if key == obj_id or str(key) == str(obj_id):
            acts = value
            break
    options = []
    for key, value in (acts or {}).items():
        if key == SHOOT or str(key) == str(SHOOT):
            options = [o for o in value or () if isinstance(o, Mapping)
                       and o.get("target_obj_id") == target and o.get("weapon_id") == weapon]
    levels = {o.get("attack_level") for o in options}
    if not options:
        return "missing", None
    if len(levels) != 1:
        return "ambiguous", None
    level = levels.pop()
    return ("listed", level) if is_int(level) else ("missing", None)


# ------------------------------------------------------------------------------------------------
# K2 (section 9): listed attack_level against the judge record's att_level

K2_SUPPORTED, K2_REFUTED, K2_UNRESOLVED = "K2_RUNTIME_SUPPORTED", "K2_REFUTED_FOR_THE_SIMPLE_MODEL", "K2_UNRESOLVED"
SUBGROUPS = ("shooter_class", "target_class", "ele_diff", "att_obj_blood", "weapon")


def k2_summary(rows: Sequence[Mapping[str, Any]], corpus_ele_diffs: Iterable[Any]) -> Dict[str, Any]:
    """``rows``: paired shots with ``listed`` and ``judged`` levels (None when missing) and the subgroup fields."""
    both = [r for r in rows if is_int(r.get("listed")) and is_int(r.get("judged"))]
    diffs = [r["judged"] - r["listed"] for r in both]
    groups: Dict[str, Dict[str, Dict[str, int]]] = {}
    for g in SUBGROUPS:
        table: Dict[str, Dict[str, int]] = {}
        for r in both:
            key = labelled(g, r.get(g)) if g != "shooter_class" and g != "target_class" else str(r.get(g))
            cell = table.setdefault(key, {"n": 0, "equal": 0})
            cell["n"] += 1
            cell["equal"] += r["judged"] == r["listed"]
        groups[g] = dict(sorted(table.items()))
    values = {r.get("ele_diff") for r in both}
    corpus = set(corpus_ele_diffs)
    coverage = len(values) >= 2 or len(corpus) <= 1
    different = sum(d != 0 for d in diffs)
    if different:
        status = K2_REFUTED
    elif not both or not coverage:
        status = K2_UNRESOLVED
    else:
        status = K2_SUPPORTED
    by_class = {}
    for cls in TARGET_CLASSES:
        part = [r for r in both if r.get("target_class") == cls]
        if not part:
            by_class[cls] = "UNTESTED"
        elif any(r["judged"] != r["listed"] for r in part):
            by_class[cls] = K2_REFUTED
        else:
            by_class[cls] = status  # equal throughout the class: the corpus-wide K2 status applies
    return {"paired_rows": len(rows), "n_both_levels": len(both), "equal": len(both) - different,
            "different": different, "missing_listed": sum(not is_int(r.get("listed")) for r in rows),
            "missing_judged": sum(not is_int(r.get("judged")) for r in rows),
            "difference_distribution": label_counts(diffs, "difference"),
            "ele_diff_values_in_paired_rows": len(values), "ele_diff_values_in_corpus": len(corpus),
            "elevation_coverage": coverage, "subgroups": groups, "status": status, "by_target_class": by_class}


# ------------------------------------------------------------------------------------------------
# K4 (section 10): the random fields, the deterministic table mapping, and the probability law

MAPPING_SUPPORTED, MAPPING_CONTRADICTED, MAPPING_UNTESTED = (
    "K4_MAPPING_SUPPORTED", "K4_MAPPING_CONTRADICTED", "K4_MAPPING_UNTESTED")
K4P_SUPPORTED, K4P_UNRESOLVED = "K4_PROBABILITY_SUPPORTED", "K4_PROBABILITY_UNRESOLVED"
STATES_LAW, DOES_NOT_STATE_LAW = "states_the_law", "does_not_state_the_law"
#: The evidence routes of section 10 for the probability law. Route A: the public platform documentation snapshot and
#: the SDK notes; route B: existing runtime or SDK evidence that exposes the generator. Each entry: what it says, its
#: status, and verbatim quotations (``SNAPSHOT``-relative file or repository path, text) checked by a test.
K4_PROBABILITY_EVIDENCE: Tuple[Dict[str, Any], ...] = (
    {"id": "A1", "route": "A", "source": "public rules, direct-fire result tables",
     "finding": "the result tables are read with a random number from 2 to 12; the tables do not say how it is drawn",
     "status": DOES_NOT_STATE_LAW,
     "quotes": (("rules_tables.txt", "### 对车辆单位战斗结果"),
                ("rules_tables.txt", "### 直瞄武器对人员/步兵轻武器对车辆战斗结果表"),
                ("rules_tables.txt", "### 空战斗结果表"))},
    {"id": "A2", "route": "A", "source": "public rules, correction notes",
     "finding": "dice are stated only for the corrections: two dice for vehicle targets, one die for personnel targets",
     "status": DOES_NOT_STATE_LAW,
     "quotes": (("rules_tables.txt", "对车辆战斗结果修正时，修正方法是2颗骰子生成随机数"),
                ("rules_tables.txt", "对人员战斗结果修正时，修正方法是1颗骰子生成随机数"))},
    {"id": "A3", "route": "A", "source": "public observation reference and SDK observation notes",
     "finding": "random1 and random2 are documented only by name and type",
     "status": DOES_NOT_STATE_LAW,
     "quotes": (("reference_observations.txt", "\"random1\": \"int, 随机数1\","),
                ("reference_observations.txt", "\"random2_rect\": \"int, 随机数2修正值\","))},
    {"id": "B1", "route": "B", "source": "the project's recorded harness evidence (docs/BASELINE.md)",
     "finding": "the engine draws from neither of the process's global generators; no seed is documented; the "
                "engine's own generator is not exposed by any record",
     "status": DOES_NOT_STATE_LAW,
     "quotes": (("docs/BASELINE.md", "the engine draws from neither of the process's global generators, and no seed "
                                     "is documented."),)},
    {"id": "B2", "route": "B", "source": "the frozen corpus's judge records",
     "finding": "records carry the drawn values only; observed values are a sample and cannot establish a law "
                "(section 10); no record names a generator or the dice behind random1",
     "status": DOES_NOT_STATE_LAW, "quotes": ()},
)


def k4_probability_status(evidence: Sequence[Mapping[str, Any]] = K4_PROBABILITY_EVIDENCE) -> str:
    """Supported only if an evidence item of route A or B states the law; observed frequencies are never an input."""
    return K4P_SUPPORTED if any(e["status"] == STATES_LAW and e["route"] in ("A", "B") for e in evidence) else K4P_UNRESOLVED


def k4_support(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per table: which random fields are populated, their supports, min and max, joint combinations of random1 and
    random2, and the difference random2_rect - random2 (descriptive; nothing here is evidence of a law)."""
    out: Dict[str, Any] = {}
    tables = sorted({r["table"] for r in rows})
    for table in tables:
        part = [r["record"] for r in rows if r["table"] == table]
        block: Dict[str, Any] = {"records": len(part)}
        for field in ("random1", "random2", "random2_rect"):
            vals = [p[field] for p in part if is_int(p.get(field))]
            block[field] = {"populated": len(vals), "support": label_counts(vals, "random_value"),
                            "min": min(vals) if vals else None, "max": max(vals) if vals else None}
        joint = [f"random1_{p['random1']}_random2_{p['random2']}" for p in part
                 if is_int(p.get("random1")) and is_int(p.get("random2"))]
        block["joint_random1_random2"] = dict(sorted(collections.Counter(joint).items()))
        block["random2_rect_minus_random2"] = label_counts(
            [p["random2_rect"] - p["random2"] for p in part if is_int(p.get("random2")) and is_int(p.get("random2_rect"))],
            "modifier")
        out[table] = block
    return out


def k4_mapping(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The raw result of each record against its published cell. The compared field is ``ori_damage`` where the record
    has it and ``damage`` otherwise. A numeric cell must equal it; each non-numeric kind must map to one single value per
    table; a row whose inputs fall outside the table, or a class with no table, is counted. Per table: supported only with
    at least one numeric row, no numeric mismatch, every non-numeric kind single-valued and no out-of-table row."""
    out: Dict[str, Any] = {}
    for table in sorted({r["table"] for r in rows}):
        part = [r for r in rows if r["table"] == table]
        numeric = [r for r in part if r["kind"] == NUMERIC]
        mismatches = [r for r in numeric if r["observed"] != r["value"]]
        kinds = {}
        for kind in (SUPPRESSION, ANNIHILATION, NO_EFFECT):
            vals = [r["observed"] for r in part if r["kind"] == kind]
            if vals:
                kinds[kind] = label_counts(vals, "value")
        out_of_table = sum(r["kind"] == OUT_OF_TABLE for r in part)
        compared_field = label_counts([r["compared_field"] for r in part], "field")
        if table == NO_TABLE:
            status = MAPPING_UNTESTED
        elif mismatches or any(len(v) > 1 for v in kinds.values()) or out_of_table:
            status = MAPPING_CONTRADICTED
        elif not numeric:
            status = MAPPING_UNTESTED
        else:
            status = MAPPING_SUPPORTED
        out[table] = {"records": len(part), "numeric_cells": len(numeric), "numeric_matches": len(numeric) - len(mismatches),
                      "numeric_mismatches": len(mismatches), "non_numeric_values": kinds, "out_of_table": out_of_table,
                      "compared_field": compared_field, "status": status}
    return out


def correction_mapping(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """``rect_damage`` against the published correction for ``random2_rect`` (and the target's armour for vehicles):
    descriptive support for reading ``rect_damage`` as a table correction."""
    out: Dict[str, Any] = {}
    for table in sorted({r["correction_table"] for r in rows if r.get("correction_table")}):
        part = [r for r in rows if r.get("correction_table") == table]
        n = match = undefined = 0
        for r in part:
            rec = r["record"]
            if not is_int(rec.get("random2_rect")) or not is_int(rec.get("rect_damage")):
                continue
            expected = (personnel_correction(rec["random2_rect"]) if table == "personnel_correction"
                        else vehicle_correction(rec["random2_rect"], r.get("target_armor")))
            if expected is None:
                undefined += 1
                continue
            n += 1
            match += expected == rec["rect_damage"]
        out[table] = {"compared": n, "matches": match, "mismatches": n - match, "undefined_armor": undefined}
    return out


# ------------------------------------------------------------------------------------------------
# K5 (section 11): registered relations between ori_damage (o), rect_damage (r) and damage (d)
# B is the target's blood before the shot; t is 1 when the documented re-suppression loss applies (a personnel target
# already suppressed, whose raw result is suppression), else 0. Every relation is defined on every integer input.

def _positive_only(o: int, r: int) -> int:
    return max(0, o + r) if o > 0 else max(0, o)


BASE_RELATIONS: Dict[str, Callable[[int, int, int, int], int]] = {
    "additive_unclamped": lambda o, r, b, t: o + r + t,
    "additive_lower_clamp": lambda o, r, b, t: max(0, o + r) + t,
    "additive_lower_and_strength_clamp": lambda o, r, b, t: min(b, max(0, o + r) + t),
    "correction_on_positive_raw_only": lambda o, r, b, t: _positive_only(o, r) + t,
    "correction_on_positive_raw_only_strength_clamp": lambda o, r, b, t: min(b, _positive_only(o, r) + t),
    "rect_damage_is_final": lambda o, r, b, t: r + t,
}
#: The twelve registered relations for records with ori_damage and rect_damage: each base relation without and with
#: the documented re-suppression loss.
RELATIONS: Dict[str, Callable[[int, int, int, int], int]] = {}
for _name, _f in BASE_RELATIONS.items():
    RELATIONS[f"{_name}__without_resuppression_loss"] = (lambda f: lambda o, r, b, t: f(o, r, b, 0))(_f)
    RELATIONS[f"{_name}__with_resuppression_loss"] = _f


def _short(annihilation_all: bool, with_loss: bool) -> Callable[[str, Optional[int], int, int], Optional[int]]:
    def relation(kind: str, value: Optional[int], b: int, t: int) -> Optional[int]:
        extra = t if with_loss else 0
        if kind == NUMERIC:
            return value + extra
        if kind in (NO_EFFECT, SUPPRESSION):
            return 0 + extra
        if kind == ANNIHILATION:
            return (b if annihilation_all else 1) + extra
        return None
    return relation


#: The four registered relations for records without correction fields: the published cell as the final loss, with
#: annihilation read as the whole unit or as one, without and with the re-suppression loss.
SHORT_RELATIONS: Dict[str, Callable[[str, Optional[int], int, int], Optional[int]]] = {
    "table_value_annihilation_whole_unit__without_resuppression_loss": _short(True, False),
    "table_value_annihilation_whole_unit__with_resuppression_loss": _short(True, True),
    "table_value_annihilation_one__without_resuppression_loss": _short(False, False),
    "table_value_annihilation_one__with_resuppression_loss": _short(False, True),
}
K5_IDENTIFIED, K5_UNDERIDENTIFIED, K5_NO_FIT, K5_UNTESTED = (
    "K5_RUNTIME_IDENTIFIED", "K5_UNDERIDENTIFIED", "K5_NO_REGISTERED_RELATION_FITS", "K5_UNTESTED")


def resuppression_term(target_class: str, kind: str, suppressed_before: Any) -> int:
    return int(target_class == INFANTRY and kind == SUPPRESSION and bool(suppressed_before))


def k5_row(row: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The K5 tuple of one record, or None when it cannot be evaluated (no pre-shot blood, or a record without
    correction fields whose raw cell is not a published cell)."""
    rec = row["record"]
    b = row.get("target_blood_before")
    if not is_int(b) or not is_int(rec.get("damage")):
        return None
    t = resuppression_term(row["target_class"], row["kind"], row.get("target_suppressed_before"))
    full = is_int(rec.get("ori_damage")) and is_int(rec.get("rect_damage"))
    if full:
        o, r = rec["ori_damage"], rec["rect_damage"]
        fits = sorted(name for name, f in RELATIONS.items() if f(o, r, b, t) == rec["damage"])
        return {"family": "full", "fits": fits, "o": o, "r": r, "d": rec["damage"], "b": b, "t": t, "kind": row["kind"]}
    if row["kind"] not in (NUMERIC, NO_EFFECT, SUPPRESSION, ANNIHILATION):
        return None
    fits = sorted(name for name, f in SHORT_RELATIONS.items() if f(row["kind"], row["value"], b, t) == rec["damage"])
    return {"family": "short", "fits": fits, "d": rec["damage"], "b": b, "t": t, "kind": row["kind"]}


def k5_class(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Section 11 for one target class: per family, the relations that fit every row; identified only if each family
    present has exactly one survivor. Boundary coverage is reported."""
    evaluated = [k for k in (k5_row(r) for r in rows) if k is not None]
    families: Dict[str, Any] = {}
    statuses = []
    for family, names in (("full", RELATIONS), ("short", SHORT_RELATIONS)):
        part = [k for k in evaluated if k["family"] == family]
        if not part:
            continue
        survivors = [n for n in names if all(n in k["fits"] for k in part)]
        status = K5_IDENTIFIED if len(survivors) == 1 else (K5_NO_FIT if not survivors else K5_UNDERIDENTIFIED)
        statuses.append(status)
        block: Dict[str, Any] = {"rows": len(part), "survivors": survivors, "status": status,
                                 "rows_fitted_by_relation": {n: sum(n in k["fits"] for k in part) for n in names},
                                 "raw_kinds": label_counts([k["kind"] for k in part], "kind"),
                                 "resuppression_term_rows": sum(k["t"] for k in part)}
        if family == "full":
            block["boundary_coverage"] = {
                "no_effect_raw": sum(k["kind"] == NO_EFFECT for k in part),
                "suppression_raw": sum(k["kind"] == SUPPRESSION for k in part),
                "positive_raw": sum(k["o"] > 0 for k in part),
                "negative_correction": sum(k["r"] < 0 for k in part),
                "positive_correction": sum(k["r"] > 0 for k in part),
                "zero_correction": sum(k["r"] == 0 for k in part),
                "lower_clamp_exercised": sum(k["o"] + k["r"] < 0 for k in part),
                "upper_clamp_exercised": sum(max(0, k["o"] + k["r"]) > k["b"] for k in part),
            }
        families[family] = block
    if not statuses:
        status = K5_UNTESTED
    elif all(s == K5_IDENTIFIED for s in statuses):
        status = K5_IDENTIFIED
    elif K5_NO_FIT in statuses:
        status = K5_NO_FIT
    else:
        status = K5_UNDERIDENTIFIED
    return {"records": len(rows), "evaluated": len(evaluated), "not_evaluable": len(rows) - len(evaluated),
            "families": families, "status": status}


# ------------------------------------------------------------------------------------------------
# K6 (section 12): damage, blood and removal per target class

K6_SUPPORTED, K6_REFUTED, K6_UNTESTED = "K6_SUPPORTED", "K6_REFUTED", "K6_UNTESTED"


def k6_class(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """``rows``: target-steps with exactly one judge record, the target present before the step, with
    ``blood_before``, ``damage``, ``present_after``, ``blood_after`` (None when absent) and ``linked_removal`` (the
    target's launcher or carrier removed in the same step by a record of its own). Linked removals are excluded from the
    lethal rule. Tests: A, a present target's blood falls by exactly the damage; B, damage below the blood leaves the
    target present; C, damage at or above the blood removes it. Supported only with no contradiction, at least one
    lethal and at least one non-lethal positive-damage row; untested when either kind of row is missing."""
    used = [r for r in rows if not r.get("linked_removal")]
    a_rows = [r for r in used if r["present_after"]]
    a_bad = [r for r in a_rows if not (is_int(r.get("blood_after")) and r["blood_before"] - r["blood_after"] == r["damage"])]
    nonlethal = [r for r in used if r["damage"] < r["blood_before"]]
    lethal = [r for r in used if r["damage"] >= r["blood_before"]]
    b_bad = [r for r in nonlethal if not r["present_after"]]
    c_bad = [r for r in lethal if r["present_after"]]
    nonlethal_positive = [r for r in nonlethal if r["damage"] > 0]
    contradictions = len(a_bad) + len(b_bad) + len(c_bad)
    if contradictions:
        status = K6_REFUTED
    elif not lethal or not nonlethal_positive:
        status = K6_UNTESTED
    else:
        status = K6_SUPPORTED
    return {"target_steps": len(rows), "linked_removals_excluded": len(rows) - len(used),
            "a_present_after": len(a_rows), "a_decrement_not_equal_to_damage": len(a_bad),
            "b_nonlethal": len(nonlethal), "b_nonlethal_positive_damage": len(nonlethal_positive),
            "b_nonlethal_removed": len(b_bad), "c_lethal": len(lethal), "c_lethal_retained": len(c_bad),
            "zero_damage": sum(r["damage"] == 0 for r in used),
            "blood_before": label_counts([r["blood_before"] for r in used], "blood"),
            "damage": label_counts([r["damage"] for r in used], "damage"),
            "status": status}


# ------------------------------------------------------------------------------------------------
# Sufficiency (section 13), dispositions (section 17) and the conditional T11 completion (section 18)

DISPOSITIONS = ("SEMANTICS_AUDIT_INVALID", "DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED", "DIRECT_FIRE_SEMANTICS_RESOLVED")
T11_COMPLETIONS = ("T11_OFFLINE_NO_KILL_EDGE", "T11_OFFLINE_PASS")
HH_CHANGED_SHOTS = 94


def class_sufficiency(k2_status: str, k4_probability: str, k5_status: str, k6_status: str) -> Dict[str, Any]:
    items = {"K2": k2_status == K2_SUPPORTED, "K4_probability": k4_probability == K4P_SUPPORTED,
             "K5": k5_status == K5_IDENTIFIED, "K6": k6_status == K6_SUPPORTED}
    return {"items": items, "sufficient": all(items.values())}


def disposition(integrity_ok: bool, sufficiency: Mapping[str, Mapping[str, Any]], required: Sequence[str]) -> Dict[str, Any]:
    """First match: invalid pairing or inputs; any required class insufficient (a class with no rows is insufficient);
    otherwise resolved."""
    missing = [c for c in required if not (sufficiency.get(c) or {}).get("sufficient")]
    if not integrity_ok:
        outcome = DISPOSITIONS[0]
    elif not required or missing:
        outcome = DISPOSITIONS[1]
    else:
        outcome = DISPOSITIONS[2]
    return {"disposition": outcome, "required_classes": list(required), "insufficient_required_classes": missing,
            "order": list(DISPOSITIONS)}


def t11_completion(baseline: Sequence[float], candidate: Sequence[float]) -> Dict[str, Any]:
    """Sprint 20's registered kill-edge condition on the 94 HH changed emitted shots: pass only if the candidate's mean
    is strictly above the baseline's (exactly zero fails)."""
    if len(baseline) != HH_CHANGED_SHOTS or len(candidate) != HH_CHANGED_SHOTS:
        raise ValueError(f"the denominator must be the {HH_CHANGED_SHOTS} HH changed emitted shots")
    b_mean = sum(baseline) / len(baseline)
    c_mean = sum(candidate) / len(candidate)
    delta = sum(c - b for b, c in zip(baseline, candidate)) / len(baseline)
    return {"shots": len(baseline), "baseline_mean_pkill": b_mean, "candidate_mean_pkill": c_mean,
            "delta_pkill": delta, "status": T11_COMPLETIONS[1] if c_mean > b_mean else T11_COMPLETIONS[0]}


# ------------------------------------------------------------------------------------------------
# Public sanitizer (section 21)

def public_problems(data: Any, private_values: Iterable[Any]) -> List[str]:
    """Forbidden keys anywhere; unit identifiers and hexes as keys or words of strings; numeric leaves masked so counts
    cannot collide with identifiers (as in Sprint 20)."""
    from .s12_screen import privacy_problems
    from .s20_t11 import mask_numbers
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted({str(v) for v in private_values}))


__all__ = [name for name in dir() if not name.startswith("_")]
