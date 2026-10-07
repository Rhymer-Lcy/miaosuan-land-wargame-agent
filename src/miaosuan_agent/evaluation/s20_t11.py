"""Sprint 20 T11-O1 offline replay (``docs/SPRINT20_T11_REPLAY.md``): pure comparison and decision logic.

One seat-decision is decided twice on the same recorded observation by
:class:`miaosuan_agent.experiments.t11_kill_first.RankedReservationPolicy`: once with ``baseline-v2``'s ranking (which
must reproduce the recorded or reconstructed ``baseline-v2`` actions exactly) and once with the kill-first ranking.
:func:`compare_decision` classifies every unit whose emitted action differs (section 7 of the registration);
:class:`SideAnalysis` accumulates a side-game; :func:`disposition` applies the frozen first-match rule.

Nothing here reads an engine, a later observation or a recorded outcome: the replay is action-level only.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..experiments.t11_kill_first import UnitRecord, UnitView, blood_value

SHOOT, MOVE, OCCUPY = 2, 1, 5
#: Classes of a unit whose emitted action differs (section 7).
ROOT = "ROOT_TARGET_SWITCH"
INDUCED_SHOOT = "RESERVATION_INDUCED_SHOOT_CHANGE"
INDUCED_NONSHOOT = "RESERVATION_INDUCED_NONSHOOT_CHANGE"
UNEXPLAINED = "UNEXPLAINED"
CLASSES = (ROOT, INDUCED_SHOOT, INDUCED_NONSHOOT, UNEXPLAINED)
#: Kinds of a difference, by what baseline-v2 and T11 emit for the unit.
CHANGED_SHOT = "changed_shot"          # both emit a shot, (target, weapon) differs
LOST_SHOT = "lost_shot"                # baseline-v2 shoots, T11 emits no shot
GAINED_SHOT = "gained_shot"            # T11 shoots, baseline-v2 emits no shot
OTHER = "other_nonshoot"               # neither shoots, the actions differ
KINDS = (CHANGED_SHOT, LOST_SHOT, GAINED_SHOT, OTHER)
OPPORTUNITY_MIN = 10
HH_SIDE_GAMES = 4
H0_SIDE_GAMES = 16
DISPOSITIONS = ("REPLAY_INVALID", "T11_OFFLINE_MODEL_UNAVAILABLE", "T11_OFFLINE_COUPLED_BEHAVIOR",
                "T11_OFFLINE_INADEQUATE_OPPORTUNITY", "T11_OFFLINE_NO_KILL_EDGE", "T11_OFFLINE_PASS")

# ------------------------------------------------------------------------------------------------
# The documented immediate-kill model: the documentary assessment made before the replay (section 11)

DOCUMENTED = "documented"
INFERRED = "inferred_not_stated"
UNDOCUMENTED = "undocumented"
STATUSES = (DOCUMENTED, INFERRED, UNDOCUMENTED)
SNAPSHOT = "local/source-archives/docs-live-snapshot-20260929"
#: Each requirement of P(immediate destruction | target state, listed shoot option), its status in the public platform
#: documentation snapshot of 2026-09-29, and verbatim quotations (file in the snapshot, text) supporting the status.
KILL_MODEL_ITEMS: Tuple[Dict[str, Any], ...] = (
    {"id": "K1", "requirement": "a published table maps the attack level of a direct-fire shot to its possible results",
     "status": DOCUMENTED,
     "finding": "result tables exist for vehicle targets (indexed by the shooter's vehicle or squad count and the "
                "attack level), for personnel targets and infantry light weapons against vehicles (indexed by the attack "
                "level), and for air targets; each is read with a random number from 2 to 12",
     "quotes": (("rules_tables.txt", "### 对车辆单位战斗结果"),
                ("rules_tables.txt", "### 直瞄武器对人员/步兵轻武器对车辆战斗结果表"),
                ("rules_tables.txt", "### 空战斗结果表"))},
    {"id": "K2", "requirement": "the listed option's attack_level is the index those tables are read with",
     "status": UNDOCUMENTED,
     "finding": "valid_actions documents attack_level only as an attack level; the rules derive a shot's attack level "
                "from the weapon and distance tables, the shooter's vehicle or squad count (against personnel) and a "
                "separate elevation-difference correction. Whether the listed value already includes the elevation "
                "correction and the count row is not stated, so the listed value cannot be taken as the table index "
                "without an assumption",
     "quotes": (("reference_observations.txt", "\"attack_level\": \"攻击等级 int\""),
                ("rules_tables.txt", "### 攻击等级高度差修正"))},
    {"id": "K3", "requirement": "the possible results of one shot",
     "status": DOCUMENTED,
     "finding": "a number eliminates that many squads or vehicles (and suppresses a vehicle target); no effect; "
                "suppression only",
     "quotes": (("rules_rules.txt", "战果为数字表示消灭了对方几个班（或几辆车），同时对车辆单位造成压制。"),
                ("rules_rules.txt", "无效，表示未对对方造成损失。"),
                ("rules_rules.txt", "压制，表示未消灭对方有生力量，但造成了对目标的压制。"))},
    {"id": "K4", "requirement": "the probability of each result: the distribution of the random number the result "
                                "tables are read with",
     "status": INFERRED,
     "finding": "the result tables are indexed by a random number from 2 to 12; the dice are stated only for the "
                "corrections (two dice for vehicles, one die for personnel), not for the result tables themselves, so "
                "two fair dice is an inference from the range",
     "quotes": (("rules_tables.txt", "对车辆战斗结果修正时，修正方法是2颗骰子生成随机数"),
                ("rules_tables.txt", "对人员战斗结果修正时，修正方法是1颗骰子生成随机数"))},
    {"id": "K5", "requirement": "how the result and its correction combine into the final loss",
     "status": UNDOCUMENTED,
     "finding": "the correction is read from the armour column (vehicles) or as -1, 0 or +1 (personnel) after a "
                "modified second random number; whether it applies to a no-effect or a suppression result, how it is "
                "added to a number, and how a total below zero or above the target's strength is treated are not "
                "stated (the judge record names an original loss, a loss correction and a final loss, without a rule)",
     "quotes": (("rules_tables.txt", "尔后对照车辆的装甲级别查表确定最终修正结果"),
                ("reference_observations.txt", "\"ori_damage\": \"int, 原始战损\""),
                ("reference_observations.txt", "\"rect_damage\": \"int, 战损修正值\""),
                ("reference_observations.txt", "\"damage\": \"int, 最终战损\""))},
    {"id": "K6", "requirement": "how the observed blood maps to destruction",
     "status": INFERRED,
     "finding": "blood is the unit's squad (or vehicle) count and a numeric result eliminates that many, and a "
                "suppressed infantry unit suppressed again loses one squad; that a unit whose count reaches zero is "
                "removed is not stated as a rule",
     "quotes": (("rules_elements.txt", "血量（班组数）"),
                ("rules_rules.txt", "被压制的步兵棋子再次被裁决压制，损失1个班，剩余的班仍保持被压制状态。"))},
    {"id": "K7", "requirement": "whether the target class changes the table",
     "status": DOCUMENTED,
     "finding": "yes: separate tables against personnel, vehicles (with the target's armour class, an observed field) "
                "and aircraft",
     "quotes": (("reference_observations.txt", "装甲类型 0-无 1-轻型 2-中型 3-重型 4-复合装甲"),
                ("rules_tables.txt", "### 对人员攻击等级表"),
                ("rules_tables.txt", "### 对车辆攻击等级表"))},
    {"id": "K8", "requirement": "whether the weapon or shooter class changes the table",
     "status": DOCUMENTED,
     "finding": "the weapon enters through the attack-level tables; the shooter's vehicle or squad count enters the "
                "vehicle result table and the personnel attack-level table; shooter state (suppressed, moving) enters "
                "the corrections",
     "quotes": (("rules_rules.txt", "射击单位处于机动中、被压制状态，战果作不利修正。"),)},
    {"id": "K9", "requirement": "the inputs of the corrections are observable",
     "status": DOCUMENTED,
     "finding": "target terrain (map), target state (concealed, moving, stacked, marching) and shooter state are "
                "named, with observation fields for the state",
     "quotes": (("rules_rules.txt", "目标单位处于掩蔽地形、机动中，战果作不利修正。"),
                ("rules_rules.txt", "目标单位处于堆叠状态、行军状态，战果作有利修正。"))},
    {"id": "K10", "requirement": "the conditions under which the model is undefined",
     "status": DOCUMENTED,
     "finding": "the vehicle result table covers counts 1 to 5 and attack levels 1 to 10; outside them the table "
                "gives no result",
     "quotes": (("rules_tables.txt", "### 对车辆单位战斗结果"),)},
)
REQUIRED_FOR_MODEL = DOCUMENTED


def kill_model_available(items: Sequence[Mapping[str, Any]] = KILL_MODEL_ITEMS) -> bool:
    """The model is available only if every requirement is documented; an inference or a gap means an unsupported
    assumption (section 12)."""
    return bool(items) and all(item["status"] == REQUIRED_FOR_MODEL for item in items)


def kill_model_gaps(items: Sequence[Mapping[str, Any]] = KILL_MODEL_ITEMS) -> List[str]:
    return [item["id"] for item in items if item["status"] != REQUIRED_FOR_MODEL]


def normalise_space(text: str) -> str:
    return " ".join(text.split())


def quote_problems(items: Sequence[Mapping[str, Any]], read: Any) -> List[str]:
    """Every quotation must occur verbatim (whitespace normalised on both sides) in its snapshot file;
    ``read(name)`` returns a file's text."""
    problems = []
    cache: Dict[str, str] = {}
    for item in items:
        if item["status"] not in STATUSES:
            problems.append(f"{item['id']}: unknown status")
        for name, text in item["quotes"]:
            if name not in cache:
                cache[name] = normalise_space(read(name))
            if normalise_space(text) not in cache[name]:
                problems.append(f"{item['id']}: not found in {name}: {text}")
    return problems


# ------------------------------------------------------------------------------------------------
# one seat-decision

def emitted_by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[Any, Mapping[str, Any]]:
    return {a.get("obj_id"): a for a in actions if a.get("obj_id") is not None}


def is_shot(action: Optional[Mapping[str, Any]]) -> bool:
    return action is not None and action.get("type") == SHOOT


def shot_key(action: Mapping[str, Any]) -> Tuple[Any, Any]:
    return action.get("target_obj_id"), action.get("weapon_id")


def duplicate_targets(actions: Sequence[Mapping[str, Any]]) -> int:
    targets = [a.get("target_obj_id") for a in actions if is_shot(a)]
    return len(targets) - len(set(targets))


@dataclass
class UnitDiff:
    obj_id: int
    cls: str
    kind: str
    baseline: Optional[Mapping[str, Any]]
    candidate: Optional[Mapping[str, Any]]
    root_choice: Optional[Tuple[int, int, int]] = None      # T11's ranking at that point (root switches)
    root_baseline: Optional[Tuple[int, int, int]] = None    # baseline-v2's ranking at that point (root switches)
    targets_available: int = 0                              # distinct remaining targets at that point (T11 state)
    chain: int = 1
    unit_type: Any = None


@dataclass
class DecisionComparison:
    diffs: List[UnitDiff] = field(default_factory=list)
    silent_roots: int = 0              # root switches whose emitted action equals baseline-v2's
    problems: List[str] = field(default_factory=list)
    duplicates_baseline: int = 0
    duplicates_candidate: int = 0
    newly_reserved: int = 0
    no_longer_reserved: int = 0
    excluded_only_candidate: int = 0   # units with an option excluded under T11 and not under baseline-v2
    excluded_only_baseline: int = 0
    max_chain: int = 0
    fallbacks: Dict[str, int] = field(default_factory=dict)
    fallbacks_multi: Dict[str, int] = field(default_factory=dict)
    shots_baseline: int = 0
    shots_candidate: int = 0


def compare_decision(stage: Any, base_actions: Sequence[Mapping[str, Any]], base_records: Sequence[UnitRecord],
                     cand_actions: Sequence[Mapping[str, Any]], cand_records: Sequence[UnitRecord],
                     base_memory: Any, cand_memory: Any) -> DecisionComparison:
    """Classifies every unit whose emitted action differs between baseline-v2 (``base``) and T11 (``cand``)."""
    out = DecisionComparison()
    base_actions = [dict(a) for a in base_actions]
    cand_actions = [dict(a) for a in cand_actions]
    out.shots_baseline = sum(is_shot(a) for a in base_actions)
    out.shots_candidate = sum(is_shot(a) for a in cand_actions)
    out.duplicates_baseline = duplicate_targets(base_actions)
    out.duplicates_candidate = duplicate_targets(cand_actions)
    if base_memory != cand_memory:
        out.problems.append("memory differs")
    if stage != 2:
        if base_actions != cand_actions:
            out.problems.append("a non-play decision differs")
        return out
    if [r.obj_id for r in base_records] != [r.obj_id for r in cand_records]:
        out.problems.append("the unit lists differ")
        return out
    base_by, cand_by = emitted_by_unit(base_actions), emitted_by_unit(cand_actions)
    if len(base_by) != len(base_actions) or len(cand_by) != len(cand_actions):
        out.problems.append("an action without a unit or two actions for one unit")
    order = [r.obj_id for r in cand_records]
    for actions, name in ((base_actions, "baseline"), (cand_actions, "candidate")):
        if [a.get("obj_id") for a in actions] != [o for o in order if o in emitted_by_unit(actions)]:
            out.problems.append(f"{name} actions are not in unit order")
    base_final = {r.reserved_by_unit for r in base_records if r.reserved_by_unit is not None}
    cand_final = {r.reserved_by_unit for r in cand_records if r.reserved_by_unit is not None}
    out.newly_reserved = len(cand_final - base_final)
    out.no_longer_reserved = len(base_final - cand_final)
    fallbacks: collections.Counter = collections.Counter()
    fallbacks_multi: collections.Counter = collections.Counter()
    changed_index: Dict[int, UnitDiff] = {}
    for i, (b, c) in enumerate(zip(base_records, cand_records)):
        if b.engage != c.engage:
            out.problems.append("a unit's listed engage candidates differ between the two runs")
        if c.fallback is not None:
            fallbacks[c.fallback] += 1
            if len({t for t, _, _ in c.remaining}) >= 2:
                fallbacks_multi[c.fallback] += 1
        if set(c.excluded) - set(b.excluded):
            out.excluded_only_candidate += 1
        if set(b.excluded) - set(c.excluded):
            out.excluded_only_baseline += 1
        ba, ca = base_by.get(b.obj_id), cand_by.get(c.obj_id)
        if ca is not None and is_shot(ca):
            listed = {(t, w) for t, w, _ in c.engage}
            if shot_key(ca) not in listed:
                out.problems.append("a T11 shot is not a listed option")
            if ca.get("target_obj_id") in c.reserved_before:
                out.problems.append("a T11 shot targets a target reserved earlier in the step")
        root = c.ranked_choice != c.baseline_choice
        if ba == ca:
            out.silent_roots += int(root)
            continue
        b_shot, c_shot = is_shot(ba), is_shot(ca)
        kind = (CHANGED_SHOT if b_shot and c_shot else LOST_SHOT if b_shot else GAINED_SHOT if c_shot else OTHER)
        if root:
            cls = ROOT
        elif set(b.excluded) != set(c.excluded) or b.occupy_blocked != c.occupy_blocked:
            cls = INDUCED_SHOOT if kind == CHANGED_SHOT else INDUCED_NONSHOOT
        else:
            cls = UNEXPLAINED
            out.problems.append("an action difference with the same ranking and the same reservation state")
        diff = UnitDiff(c.obj_id, cls, kind, ba, ca, unit_type=c.unit_type,
                        targets_available=len({t for t, _, _ in c.remaining}))
        if root:
            diff.root_choice, diff.root_baseline = c.ranked_choice, c.baseline_choice
        # reservation chain: earlier changed units whose reserved target is in this unit's differing exclusion state
        differing = (b.reserved_before ^ c.reserved_before) & {t for t, _, _ in c.engage}
        causes = [d for j, d in changed_index.items() if j < i and
                  (base_records[j].reserved_by_unit in differing or cand_records[j].reserved_by_unit in differing)]
        diff.chain = 1 + max((d.chain for d in causes), default=0)
        changed_index[i] = diff
        out.diffs.append(diff)
    out.max_chain = max((d.chain for d in out.diffs), default=0)
    out.fallbacks = dict(fallbacks)
    out.fallbacks_multi = dict(fallbacks_multi)
    if out.duplicates_baseline or out.duplicates_candidate:
        out.problems.append("a duplicate shoot target")
    return out


# ------------------------------------------------------------------------------------------------
# one side-game

def class_label(unit_type: Any, sub_type: Any) -> str:
    return f"type {unit_type} sub {sub_type}"


@dataclass
class SideAnalysis:
    population: str
    label: str
    decisions: int = 0
    play_decisions: int = 0
    reference_equal: int = 0
    reference_compared: int = 0
    changed_decisions: int = 0
    first_change_k: Optional[int] = None
    first_change_step: Optional[int] = None
    counts: Dict[str, int] = field(default_factory=dict)
    kinds: Dict[str, Dict[str, int]] = field(default_factory=dict)
    problems: List[str] = field(default_factory=list)
    changed_shooters: Set[Any] = field(default_factory=set)
    root_rows: List[Dict[str, Any]] = field(default_factory=list)
    induced_rows: List[Dict[str, Any]] = field(default_factory=list)
    reservation: Dict[str, Any] = field(default_factory=dict)
    fallbacks: Dict[str, int] = field(default_factory=dict)
    fallbacks_multi: Dict[str, int] = field(default_factory=dict)
    private_rows: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.counts = {k: 0 for k in ("silent_root_switches", "baseline_shots", "candidate_shots",
                                      "duplicate_targets_baseline", "duplicate_targets_candidate",
                                      "changed_emitted_shots", "root_changed_shots", "induced_changed_shots")}
        self.kinds = {c: {k: 0 for k in KINDS} for c in CLASSES}
        self.reservation = {"decisions_with_a_chain": 0, "max_chain": 0, "newly_reserved_targets": 0,
                            "no_longer_reserved_targets": 0, "units_with_an_option_excluded_only_under_t11": 0,
                            "units_with_an_option_excluded_only_under_baseline": 0,
                            "baseline_shoot_targets_in_changed_decisions": 0,
                            "t11_shoot_targets_in_changed_decisions": 0}

    def add(self, k: int, step: Any, stage: Any, reference_equal: Optional[bool], comparison: DecisionComparison,
            views: Mapping[int, UnitView]) -> None:
        self.decisions += 1
        self.play_decisions += stage == 2
        if reference_equal is not None:
            self.reference_compared += 1
            self.reference_equal += bool(reference_equal)
            if not reference_equal:
                self.problems.append(f"k{k}: the baseline ranking does not reproduce baseline-v2")
        self.problems.extend(f"k{k}: {p}" for p in comparison.problems)
        c = self.counts
        c["silent_root_switches"] += comparison.silent_roots
        c["baseline_shots"] += comparison.shots_baseline
        c["candidate_shots"] += comparison.shots_candidate
        c["duplicate_targets_baseline"] += comparison.duplicates_baseline
        c["duplicate_targets_candidate"] += comparison.duplicates_candidate
        for name, n in comparison.fallbacks.items():
            self.fallbacks[name] = self.fallbacks.get(name, 0) + n
        for name, n in comparison.fallbacks_multi.items():
            self.fallbacks_multi[name] = self.fallbacks_multi.get(name, 0) + n
        if not comparison.diffs:
            return
        self.changed_decisions += 1
        if self.first_change_k is None:
            self.first_change_k, self.first_change_step = k, step
        r = self.reservation
        r["decisions_with_a_chain"] += comparison.max_chain >= 2
        r["max_chain"] = max(r["max_chain"], comparison.max_chain)
        r["newly_reserved_targets"] += comparison.newly_reserved
        r["no_longer_reserved_targets"] += comparison.no_longer_reserved
        r["units_with_an_option_excluded_only_under_t11"] += comparison.excluded_only_candidate
        r["units_with_an_option_excluded_only_under_baseline"] += comparison.excluded_only_baseline
        r["baseline_shoot_targets_in_changed_decisions"] += comparison.shots_baseline
        r["t11_shoot_targets_in_changed_decisions"] += comparison.shots_candidate
        for d in comparison.diffs:
            self.kinds[d.cls][d.kind] += 1
            self.changed_shooters.add(d.obj_id)
            shooter = views.get(d.obj_id)
            shooter_class = class_label(shooter.unit_type, shooter.sub_type) if shooter else "unknown"
            if d.kind == CHANGED_SHOT:
                c["changed_emitted_shots"] += 1
                c["root_changed_shots" if d.cls == ROOT else "induced_changed_shots"] += 1
                row = pair_row(d.baseline, d.candidate, views, shooter_class, d.targets_available)
                (self.root_rows if d.cls == ROOT else self.induced_rows).append(row)
                if d.cls == ROOT:
                    row["root"] = choice_row(d.root_baseline, d.root_choice, views)
            self.private_rows.append({"k": k, "step": step, "obj_id": d.obj_id, "class": d.cls, "kind": d.kind,
                                      "baseline": d.baseline, "candidate": d.candidate, "chain": d.chain,
                                      "root_choice": d.root_choice, "root_baseline": d.root_baseline})

    @property
    def integrity_ok(self) -> bool:
        return not self.problems and self.reference_compared == self.decisions and self.reference_equal == self.decisions


def target_facts(target: Any, views: Mapping[int, UnitView]) -> Dict[str, Any]:
    view = views.get(target)
    if view is None:
        return {"blood": None, "class": "not visible"}
    return {"blood": blood_value(view.blood), "class": class_label(view.unit_type, view.sub_type)}


def level_of(action: Mapping[str, Any], engage: Iterable[Tuple[int, int, int]]) -> Optional[int]:
    for t, w, level in engage:
        if (t, w) == shot_key(action):
            return level
    return None


def pair_row(baseline: Mapping[str, Any], candidate: Mapping[str, Any], views: Mapping[int, UnitView],
             shooter_class: str, targets_available: int) -> Dict[str, Any]:
    """One changed emitted shot, paired with baseline-v2's emitted shot of the same shooter (private until summarised)."""
    b, c = target_facts(baseline.get("target_obj_id"), views), target_facts(candidate.get("target_obj_id"), views)
    return {"shooter_class": shooter_class, "baseline_blood": b["blood"], "t11_blood": c["blood"],
            "baseline_target_class": b["class"], "t11_target_class": c["class"],
            "same_target": baseline.get("target_obj_id") == candidate.get("target_obj_id"),
            "targets_available": targets_available}


def choice_row(baseline: Optional[Tuple[int, int, int]], ranked: Optional[Tuple[int, int, int]],
               views: Mapping[int, UnitView]) -> Dict[str, Any]:
    """Baseline-v2's ranking against T11's at the same point (same remaining candidates)."""
    if baseline is None or ranked is None:
        return {}
    b, c = target_facts(baseline[0], views), target_facts(ranked[0], views)
    return {"baseline_level": baseline[2], "t11_level": ranked[2], "baseline_blood": b["blood"],
            "t11_blood": c["blood"], "same_target": baseline[0] == ranked[0],
            "baseline_target_class": b["class"], "t11_target_class": c["class"]}


# ------------------------------------------------------------------------------------------------
# summaries (public, aggregates only)

def counter(values: Iterable[Any]) -> Dict[str, int]:
    out = collections.Counter(str(v) for v in values)
    return dict(sorted(out.items()))


def summarise_root_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    root = [r["root"] for r in rows if r.get("root")]
    reductions = [r["baseline_blood"] - r["t11_blood"] for r in root
                  if r["baseline_blood"] is not None and r["t11_blood"] is not None]
    levels = [(r["baseline_level"], r["t11_level"]) for r in root]
    return {
        "n": len(rows),
        "baseline_target_blood": counter(r["baseline_blood"] for r in root),
        "t11_target_blood": counter(r["t11_blood"] for r in root),
        "blood_reduction": counter(reductions),
        "attack_level_pairs": counter(f"L{b}_L{t}" for b, t in levels),
        "attack_level_change": counter(t - b for b, t in levels),
        "t11_level_lower": sum(1 for b, t in levels if t < b),
        "t11_level_equal": sum(1 for b, t in levels if t == b),
        "t11_level_higher": sum(1 for b, t in levels if t > b),
        "shooter_class": counter(r["shooter_class"] for r in rows),
        "target_class_pairs": counter(f"{r['baseline_target_class']} -> {r['t11_target_class']}" for r in root),
        "targets_available": counter(r["targets_available"] for r in rows),
        "same_target_as_baseline_ranking": sum(1 for r in root if r["same_target"]),
        "emitted_pair_same_target": sum(1 for r in rows if r["same_target"]),
    }


def summarise_induced_rows(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    pairs = [(r["baseline_blood"], r["t11_blood"]) for r in rows]
    return {"n": len(rows), "blood_pairs": counter(f"b{b}_t{t}" for b, t in pairs),
            "shooter_class": counter(r["shooter_class"] for r in rows),
            "target_class_pairs": counter(f"{r['baseline_target_class']} -> {r['t11_target_class']}" for r in rows)}


def nonshoot(side: SideAnalysis) -> int:
    """Differences that are not a changed shot: lost, gained and other, in any class."""
    return sum(n for cls in CLASSES for kind, n in side.kinds[cls].items() if kind != CHANGED_SHOT)


def public_side(side: SideAnalysis) -> Dict[str, Any]:
    return {"side_game": side.label, "decisions": side.decisions, "play_decisions": side.play_decisions,
            "baseline_ranking_reproduces_baseline_v2": [side.reference_equal, side.reference_compared],
            "integrity_ok": side.integrity_ok, "problems": len(side.problems),
            "decisions_with_a_change": side.changed_decisions, "first_change_decision": side.first_change_k,
            "first_change_step": side.first_change_step,
            "decisions_after_first_change": (side.decisions - side.first_change_k - 1
                                             if side.first_change_k is not None else 0),
            "counts": dict(side.counts), "differences_by_class_and_kind": side.kinds,
            "non_shoot_differences": nonshoot(side), "distinct_changed_shooters": len(side.changed_shooters),
            "reservation": dict(side.reservation), "fallbacks": dict(sorted(side.fallbacks.items())),
            "fallbacks_with_two_or_more_targets": dict(sorted(side.fallbacks_multi.items())),
            "root_switches": summarise_root_rows(side.root_rows),
            "induced_changed_shots": summarise_induced_rows(side.induced_rows)}


def pooled(sides: Sequence[SideAnalysis]) -> Dict[str, Any]:
    kinds = {c: {k: sum(s.kinds[c][k] for s in sides) for k in KINDS} for c in CLASSES}
    counts = {k: sum(s.counts[k] for s in sides) for k in sides[0].counts} if sides else {}
    reservation: Dict[str, Any] = {}
    for s in sides:
        for k, v in s.reservation.items():
            reservation[k] = max(reservation.get(k, 0), v) if k == "max_chain" else reservation.get(k, 0) + v
    return {"side_games": len(sides), "decisions": sum(s.decisions for s in sides),
            "decisions_with_a_change": sum(s.changed_decisions for s in sides), "counts": counts,
            "differences_by_class_and_kind": kinds, "non_shoot_differences": sum(nonshoot(s) for s in sides),
            "distinct_changed_shooters_summed_over_side_games": sum(len(s.changed_shooters) for s in sides),
            "reservation": reservation,
            "root_switches": summarise_root_rows([r for s in sides for r in s.root_rows]),
            "induced_changed_shots": summarise_induced_rows([r for s in sides for r in s.induced_rows])}


# ------------------------------------------------------------------------------------------------
# decision items and the frozen first-match disposition

def changed_shot_counts(sides: Sequence[SideAnalysis]) -> List[int]:
    return [s.counts["changed_emitted_shots"] for s in sides]


def coupled(sides: Iterable[SideAnalysis]) -> bool:
    """Any difference that is not a changed shot, in any analysed side-game (HH and H0)."""
    return any(nonshoot(s) > 0 for s in sides)


def opportunity_ok(hh_changed_shots: Sequence[int]) -> bool:
    return len(hh_changed_shots) == HH_SIDE_GAMES and all(n >= OPPORTUNITY_MIN for n in hh_changed_shots)


def kill_edge(delta_pkill: Optional[float]) -> bool:
    """Strictly positive pooled paired delta; exactly zero, or no value, fails."""
    return delta_pkill is not None and delta_pkill > 0


def disposition(fidelity_ok: bool, model_available: bool, is_coupled: Optional[bool],
                hh_changed_shots: Sequence[int], delta_pkill: Optional[float]) -> Dict[str, Any]:
    items = {"fidelity": fidelity_ok, "kill_model_available": model_available,
             "pure_target_priority": None if is_coupled is None else not is_coupled,
             "opportunity": opportunity_ok(hh_changed_shots), "kill_edge": kill_edge(delta_pkill)}
    if not items["fidelity"]:
        outcome = DISPOSITIONS[0]
    elif not items["kill_model_available"]:
        outcome = DISPOSITIONS[1]
    elif not items["pure_target_priority"]:
        outcome = DISPOSITIONS[2]
    elif not items["opportunity"]:
        outcome = DISPOSITIONS[3]
    elif not items["kill_edge"]:
        outcome = DISPOSITIONS[4]
    else:
        outcome = DISPOSITIONS[5]
    reached = DISPOSITIONS.index(outcome)
    return {"disposition": outcome, "items": items, "hh_changed_emitted_shots": list(hh_changed_shots),
            "delta_pkill": delta_pkill, "items_below_the_first_match_are_descriptive": reached < len(DISPOSITIONS) - 1,
            "rule": "first match in the order " + ", ".join(DISPOSITIONS)}


# ------------------------------------------------------------------------------------------------
# privacy (Sprint 18's reading of the project sanitizer)

def mask_numbers(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {k: mask_numbers(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [mask_numbers(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return None
    return node


def public_problems(data: Any, private_values: Iterable[Any]) -> List[str]:
    from .s12_screen import privacy_problems
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted({str(v) for v in private_values}))
