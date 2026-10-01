"""The registered read-only diagnostic ``baseline-v2-residual-516-diagnostic-1``.

Question: what removes the target of the residual single-shot code-516 refusals (``shoot / 516 /
CantShootToDiedBop``) of ``baseline-v2``, which remained after same-seat, same-step repeated fire was
eliminated? The diagnostic plays 32 new games of one configuration, scenario 1930331196 under C3
(``baseline-v2`` as blue against the inert control as red), on ``baseline-v1-runtime-r2`` with 32
workers through the qualified production scheduler. Nothing about the policy, the routing, the garbage
collector or the engine changes; a read-only observer records, privately, the complete joint action
batch of every engine step, the engine's action feedback and the ``judge_info`` records new in each
step, and keeps a short rolling window of complete pre-step observations that is written out only when
a step carries a code-516 refusal.

Each refusal gets a factual record first (:func:`event_facts`), then exactly one category of the
registered taxonomy (:func:`classify`): H1 friendly cross-seat same-step fire, H2 opposing-seat
same-step action, H3 an effect of an action issued in an earlier step, H4 an engine-resolved effect
not represented as a direct same-target shot, H5 a non-combat removal or state transition, H6 an
engine ordering or adjudication artifact, H7 unresolved. A category is assigned only when its evidence
rule matches and no other rule does.
"""

from __future__ import annotations

import collections
import hashlib
import json
import pickle
import time
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Observation, Origin
from . import manifest as mf
from . import refusals
from . import shoot_experiment as sx
from .execution import RUNTIMES
from ..decision import INERT_ID
from ..decision import digest as trace_digest

SCHEMA = "miaosuan-residual516-diagnostic/1"
DIAGNOSTIC_ID = "baseline-v2-residual-516-diagnostic-1"
CAPTURE_SCHEMA = "miaosuan-residual516-capture/1"
FACT_SCHEMA = "miaosuan-residual516-fact/1"
RESULTS_SCHEMA = "miaosuan-residual516-results/1"
PURPOSE = "diagnostic"
SCENARIO_ID = "1930331196"
CONDITION = "C3"
GAMES = 32
WORKERS = 32
RUNTIME = "baseline-v1-runtime-r2"
BASELINE_V2_SOURCE_SHA256 = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
#: Pre-step snapshots kept in the rolling window, the event step's own included.
WINDOW = 5
#: A representative decision snapshot of each policy seat is also kept every this many decisions.
SAMPLE_EVERY = 200
#: Earlier steps searched, in the compact per-step log, for shots at a refused target and their records.
PRIOR_STEPS = 30
TRIGGER_CODE = 516
SHOOT, BOARD, UNLOAD, INDIRECT, GUIDED = 2, 3, 4, 8, 9
SHOT_TYPES = (SHOOT, GUIDED)
#: Unit fields whose changes the compact per-step log records.
WATCHED_FIELDS = ("blood", "lose_control", "launcher", "car", "on_board", "alive_remain_time", "keep")
CATEGORIES = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
STOP_AFTER_CONSECUTIVE_FAILURES = 3

QUESTION = ("What removes the target of baseline-v2's residual single-shot code-516 refusals, which remained after "
            "same-seat, same-step repeated fire was eliminated?")
TAXONOMY = {
    "H1": "friendly cross-seat same-step fire: another seat of the refused seat's faction shot the same target in the "
          "same engine step, and a judge_info record of that shot shows damage to the target in that step",
    "H2": "opposing-seat same-step action: a judge_info record new in the step shows damage to the target from a unit "
          "of the other faction, or an action of the other faction accepted in the step names the target as its "
          "target, or boards or unloads it (action type 3 or 4 with the target as actor or target)",
    "H3": "delayed or prior-step effect: a judge_info record new in the step shows damage to the target from a unit "
          "that did not shoot it in the step's batch but issued an accepted shot at it in an earlier step, or an "
          "indirect-fire point at the target's hex resolved in the step",
    "H4": "indirect, area or automatic engine effect: no judge_info record shows damage to the target in the step, and "
          "an object the target is linked to at step start (its launcher or carrying vehicle, or a vehicle listing it "
          "as passenger or launched unit) was on the map at step start and absent after it",
    "H5": "non-combat removal or state transition: no damage record, no linked removal and no opposing action on "
          "the target, and the target is listed as a passenger after the step or one of its watched fields records a "
          "transition (on_board to 1, lose_control to 1, alive_remain_time to 0)",
    "H6": "engine ordering or adjudication artifact: the target is still on the map after the step although the shot "
          "was refused as fired at a destroyed unit, or a judge_info record of the refused shot itself appears (one "
          "the actor's own earlier accepted shot at the target does not explain)",
    "H7": "unresolved: no rule matches, or more than one does",
}
CLASSIFICATION_RULES = (
    "Only code-516 refusals of the policy seat count; each is classified once. A positive damage record is a "
    "judge_info record new in the refusal's step whose target_obj_id is the target and whose damage field is a "
    "number greater than 0.",
    "Each rule H1 to H6 is evaluated independently on the factual record. Exactly one matching rule gives the "
    "category; none, or two or more, give H7 with the matching rules listed.",
    "Evidence strength: H1, H2, H3 strong when the attributed damage records sum to at least the target's blood at "
    "step start and no positive damage record on the target is left unattributed, otherwise moderate; H4 strong when "
    "the linked object has a positive damage record in the step and the target has no judge_info record at all in "
    "it, otherwise moderate; H5 strong when the target is a passenger after the step, otherwise moderate; H6 strong "
    "when the target is on the map after the step, otherwise moderate; H7 none.",
    "Batch position is reported but never used as evidence of resolution order; ordering is inferred only from engine "
    "evidence (judge_info, action feedback).",
)
FACTS = (
    "action type, error code, the engine message and its normalized class, seat and faction",
    "actor, target and weapon (private identifiers)",
    "whether the target was on the map at step start, and its class and watched fields then",
    "whether the shot was listed in the seat's start-of-step valid_actions and passed the project gate",
    "every action of the complete submitted batch that names the target, with seat, faction, batch position, position "
    "in its seat's output and the engine's feedback for it",
    "shots at the target from the refused seat, from other seats of its faction, from the other faction, in total",
    "whether target and actor are present after the step, and whether the target is then a passenger",
    "judge_info records new in the step: those on the target (attacker, its faction, whether the attacker shot the "
    "target in this batch or in an earlier step), and those of the refused shot's actor",
    "objects linked to the target at step start (launcher, carrying vehicle, vehicles listing it) and whether each was "
    "present after the step, with its damage records in the step",
    "indirect-fire points at the target's hex, the target's watched-field changes, and the action feedback naming it",
    "accepted shots at the target and judge_info records on it in the preceding steps of the compact log",
)
CAPTURE = {
    "schema": CAPTURE_SCHEMA,
    "per_step": ("decision index and engine step; the complete submitted batch in engine order (seat, faction, batch "
                 "position, position in the seat's output, the action); each seat's decision-trace digest and gate "
                 "rejections; the engine's action feedback after the step; judge_info records new in the step and "
                 "whether the previous list was a prefix of the new one; indirect-fire points; units gone, appeared, "
                 "boarded or landed in the step; watched-field changes"),
    "window": (f"the {WINDOW} most recent pre-step snapshots (all-seeing observation, and each policy seat's "
               "observation, memory, actions and trace digest), written with the post-step all-seeing observation only "
               "for a step whose feedback carries code 516"),
    "samples": f"the policy seat's pre-step snapshot every {SAMPLE_EVERY} decisions, for the replay check",
    "setup": "seats of role_and_grouping_info with faction, role and operator count; players and their policies",
    "storage": "local/evaluation/<name>/capture/<game>.capture.json (compact log) and <game>.windows.pkl (snapshots), "
               "created exclusively, git-ignored",
}
CROSS_SEAT = (
    "Over every captured step: a target is shot by a seat when the batch holds a shoot or guided-shoot action of that "
    "seat at it. A cross-seat collision is a (step, target) shot by two or more seats of one faction. Collisions are "
    "counted with the steps holding them, and split by whether the step's feedback carries a code-516 refusal of a "
    "shot at that target.",
    "Same-seat repeated fire (two or more shots of one seat at one target in one step) is counted as well; under "
    "baseline-v2 it must be 0.",
    "Unit actions of the inert seat are counted; under the control they must be 0.",
)
INSTRUMENTATION = (
    "The observer is called after every seat has decided and after the engine step; it reads, serializes and never "
    "returns anything to the policy or the engine. Without an observer the game loop and its record are unchanged.",
    "Every game must pass the independence comparison with the serial reference of 1930331196 C3 under baseline-v2 "
    "(state and trace digests up to the common prefix of the 15 serial games, not equal to a serial chain).",
    "Every in-game replay check (a fresh policy instance recomputes the decision every 100 steps) must agree.",
    "Offline, in a separate process, a fresh baseline-v2 policy recomputes the decision of every captured snapshot "
    "(event windows and samples) from the captured observation and memory; actions and trace digest must equal the "
    "captured ones.",
    "Observer time is measured per game; no observer error may occur.",
    "If any of these fails, the diagnostic stops at analysis: no classification is reported as valid.",
)
STOP_RULES = (
    "Before the first game: the shared-server courtesy check of the concurrency qualification (other activity at "
    "most 16 logical CPUs over 30 s and at least 16 logical CPUs idle beside the 32 workers), rechecked every 300 s up "
    "to 6 times; if the host stays busy, the run waits and the registered worker count is not changed.",
    f"During the run: dispatch stops after {STOP_AFTER_CONSECUTIVE_FAILURES} consecutive games that did not complete "
    "and on any other exit status; no game is retried or replaced, and a failed game is preserved and reported.",
    "No policy, routing, collection, runtime or engine change is made during or because of the diagnostic.",
)
ARTIFACTS = {
    "public": ("this module, the manifest, the analysis script, the diagnostic document, and results.json with "
               "sanitized counts only (no unit, seat-internal or step identifiers, no observation content, no "
               "judge_info payload)"),
    "private": ("game records, capture logs, snapshot windows and the factual records, under the git-ignored "
                "local/evaluation/" + DIAGNOSTIC_ID + "/"),
}
CONCLUSIONS = ("RESIDUAL 516 MECHANISM EXPLAINED", "RESIDUAL 516 MECHANISM PARTIALLY EXPLAINED",
               "RESIDUAL 516 MECHANISM UNRESOLVED")
CONCLUSION_RULE = (
    "EXPLAINED when every instrumentation check passes, at least one residual code-516 refusal occurs and every one "
    "is classified in H1 to H6 with strong evidence; PARTIALLY EXPLAINED when the checks pass and at least one "
    "residual refusal is classified in H1 to H6 but not every one is, or not every one with strong evidence; "
    "UNRESOLVED otherwise, including when no residual refusal occurs or an instrumentation check fails."
)
PRIOR_EVIDENCE = (
    "Before registration, the existing private records of the shoot-reservation experiment were inspected for the "
    "unit class of each residual target: all 10 residual code-516 targets in scenario 1930331196 (8 in C3, 2 in C1) "
    "were of one unit class, an unmanned ground vehicle whose record names a launching vehicle. This informed the "
    "watched fields and the linked-object facts; the taxonomy and its rules do not depend on it.",
)
NOT_CLAIMED = (
    "No rate is estimated: 32 games are for mechanism capture, not statistical estimation, and they are not a "
    "tactical evaluation dataset.",
    "No policy is changed or promoted; any remediation needs its own registration.",
)


# ----------------------------------------------------------------------------------------------
# Registration


def game_ids() -> List[str]:
    return [f"{SCENARIO_ID}.{CONDITION}.d{k:02d}" for k in range(1, GAMES + 1)]


def build(shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str, cq_plan: Mapping[str, Any],
          cq_plan_sha256: str, rt_results: Mapping[str, Any], rt_results_sha256: str) -> Dict[str, Any]:
    """The registered manifest, from the committed shoot-experiment manifest, concurrency plan and runtime results."""
    candidate = shoot_manifest["groups"]["C"]
    if candidate["policy_source"]["sha256"] != BASELINE_V2_SOURCE_SHA256:
        raise ValueError("the shoot experiment's group C is not the frozen baseline-v2 source")
    conditions = candidate["conditions"][CONDITION]
    if conditions != {"red": INERT_ID, "blue": sx.CANDIDATE_ID}:
        raise ValueError(f"{CONDITION} is not baseline-v2 as blue against the inert control: {conditions}")
    scenario = next(s for s in shoot_manifest["scenarios"] if s["scenario_id"] == SCENARIO_ID)
    reference = next(b["reference"] for b in cq_plan["block"] if b["config"] == f"{SCENARIO_ID}.{CONDITION}")
    (scheduler,) = rt_results["production_path"]["scheduler"]
    if rt_results["disposition"]["runtime"] != RUNTIME:
        raise ValueError("the runtime qualification did not promote baseline-v1-runtime-r2")
    return {
        "schema": SCHEMA, "diagnostic_id": DIAGNOSTIC_ID, "evaluation_id": DIAGNOSTIC_ID, "purpose": PURPOSE,
        "question": QUESTION,
        "policy_under_test": sx.CANDIDATE_ID, "control_policy": INERT_ID,
        "policy_source": dict(candidate["policy_source"]), "golden_trace_chain": candidate["golden_trace_chain"],
        "identities": {"tactical": "baseline-v2", "code_identity": sx.CANDIDATE_ID,
                       "policy_source_sha256": BASELINE_V2_SOURCE_SHA256, "runtime": RUNTIME,
                       "runtime_environment": dict(RUNTIMES[RUNTIME]), "scheduler": scheduler},
        "execution": {"workers": WORKERS, "runtime": RUNTIME, "scheduler": scheduler},
        "configuration": {"scenario_id": SCENARIO_ID, "condition": CONDITION, "red": INERT_ID, "blue": sx.CANDIDATE_ID},
        "scenarios": [dict(scenario)], "players": [dict(p) for p in shoot_manifest["players"]],
        "randomness": dict(shoot_manifest["randomness"]), "caps": dict(shoot_manifest["caps"]),
        "games": [{"game_id": game, "repetition": k} for k, game in enumerate(game_ids(), start=1)],
        "reference": dict(reference),
        "inputs": {"shoot_manifest_sha256": shoot_manifest_sha256, "concurrency_plan_sha256": cq_plan_sha256,
                   "runtime_results_sha256": rt_results_sha256},
        "known_refusal_classes": [list(c) for c in sx.KNOWN_CLASSES],
        "capture": dict(CAPTURE), "taxonomy": dict(TAXONOMY), "classification_rules": list(CLASSIFICATION_RULES),
        "facts": list(FACTS), "cross_seat": list(CROSS_SEAT), "instrumentation": list(INSTRUMENTATION),
        "stop_rules": list(STOP_RULES), "artifacts": dict(ARTIFACTS), "prior_evidence": list(PRIOR_EVIDENCE),
        "not_claimed": list(NOT_CLAIMED), "conclusion_rule": CONCLUSION_RULE,
        "parameters": {"window": WINDOW, "sample_every": SAMPLE_EVERY, "prior_steps": PRIOR_STEPS,
                       "trigger_code": TRIGGER_CODE, "watched_fields": list(WATCHED_FIELDS)},
    }


def digest(manifest: Mapping[str, Any]) -> str:
    return mf.digest(manifest)


def is_diagnostic(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any]) -> List[mf.GameSpec]:
    scenario = manifest["scenarios"][0]
    config = manifest["configuration"]
    return [mf.GameSpec(game_id=g["game_id"], scenario_id=scenario["scenario_id"], map_id=scenario["map_id"],
                        condition=config["condition"], red=config["red"], blue=config["blue"],
                        repetition=g["repetition"], max_time=int(scenario["max_time"])) for g in manifest["games"]]


# ----------------------------------------------------------------------------------------------
# Capture (the observer)


def plain(value: Any) -> Any:
    """A JSON-ready copy: mappings with string keys, lists for sequences, numbers from numpy scalars."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {k if isinstance(k, str) else str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    for method in ("item", "tolist"):
        if hasattr(value, method):
            return plain(getattr(value, method)())
    return repr(value)


def _key(record: Any) -> str:
    return json.dumps(plain(record), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


#: Above this length a prefix is checked at its first, middle and last record only (reported as such).
FULL_PREFIX_CHECK = 200


def judge_delta(before: Sequence[Any], after: Sequence[Any],
                before_keys: Optional[List[str]] = None) -> Tuple[List[Any], str, List[str]]:
    """The judge_info records new after a step, how the two lists relate, and the keys of the new list.

    ``prefix``: the previous list is a non-empty prefix of the new one (accumulating), checked record by record;
    ``prefix-sampled``: the same, checked at the first, middle and last record of a list longer than
    ``FULL_PREFIX_CHECK``; ``replaced``: the previous list is not a prefix; ``first``: the previous list was empty and
    the new one is not; ``empty``: the new list is empty. ``before_keys`` may pass the keys of ``before`` computed for
    the previous step.
    """
    if not after:
        return [], "empty", []
    if not before:
        return list(after), "first", [_key(r) for r in after]
    b = before_keys if before_keys is not None and len(before_keys) == len(before) else [_key(r) for r in before]
    n = len(b)
    if len(after) >= n:
        probes = range(n) if n <= FULL_PREFIX_CHECK else sorted({0, n // 2, n - 1})
        if all(_key(after[i]) == b[i] for i in probes):
            new = list(after[n:])
            return new, "prefix" if n <= FULL_PREFIX_CHECK else "prefix-sampled", b + [_key(r) for r in new]
    a = [_key(r) for r in after]
    remaining = collections.Counter(b)
    new = []
    for record, key in zip(after, a):
        if remaining[key] > 0:
            remaining[key] -= 1
        else:
            new.append(record)
    return new, "replaced", a


def unit_table(observation: Mapping[str, Any]) -> Dict[int, Dict[str, Any]]:
    """obj_id -> where it is listed (operators or passengers), its class and its watched fields."""
    table: Dict[int, Dict[str, Any]] = {}
    for where in ("operators", "passengers"):
        for unit in observation.get(where) or ():
            if not isinstance(unit, Mapping) or "obj_id" not in unit:
                continue
            entry = {"where": where, "class": [plain(unit.get("color")), plain(unit.get("type")), plain(unit.get("sub_type"))],
                     "hex": plain(unit.get("cur_hex"))}
            entry.update({name: plain(unit.get(name)) for name in WATCHED_FIELDS})
            entry["launch_ids"] = plain(unit.get("launch_ids") or [])
            entry["passenger_ids"] = plain(unit.get("passenger_ids") or [])
            table[int(unit["obj_id"])] = entry
    return table


def unit_delta(before: Mapping[int, Mapping[str, Any]], after: Mapping[int, Mapping[str, Any]]) -> Dict[str, Any]:
    gone = sorted(set(before) - set(after))
    appeared = sorted(set(after) - set(before))
    boarded = sorted(u for u in set(before) & set(after)
                     if before[u]["where"] == "operators" and after[u]["where"] == "passengers")
    landed = sorted(u for u in set(before) & set(after)
                    if before[u]["where"] == "passengers" and after[u]["where"] == "operators")
    changed = {}
    for unit in sorted(set(before) & set(after)):
        diff = {name: [before[unit][name], after[unit][name]] for name in WATCHED_FIELDS
                if before[unit][name] != after[unit][name]}
        if diff:
            changed[str(unit)] = diff
    return {"gone": gone, "appeared": appeared, "boarded": boarded, "landed": landed, "changed": changed}


def feedback_code(entry: Mapping[str, Any]) -> Any:
    error = entry.get("error")
    if not error or not isinstance(error, Mapping):
        return None
    return refusals._code(error.get("code"))


class Capture:
    """The read-only observer of one game. ``play(..., observer=Capture(...))`` calls :meth:`setup` once and
    :meth:`step` after every engine step; nothing it does reaches the policies or the engine."""

    def __init__(self, policy_seats: Iterable[str] = (sx.CANDIDATE_ID,), window: int = WINDOW,
                 sample_every: int = SAMPLE_EVERY, clock: Callable[[], float] = time.perf_counter) -> None:
        self.policies = frozenset(policy_seats)
        self.window, self.sample_every, self.clock = window, sample_every, clock
        self.setup_info: Dict[str, Any] = {}
        self.steps: List[Dict[str, Any]] = []
        self.ring: collections.deque = collections.deque(maxlen=window)
        self.events: List[Dict[str, Any]] = []
        self.samples: List[Dict[str, Any]] = []
        self.seconds = 0.0
        self.semantics: collections.Counter = collections.Counter()
        self._judge_keys: Optional[List[str]] = None

    def setup(self, view: Any, players: Sequence[Mapping[str, Any]], policies: Mapping[int, str]) -> None:
        tick = self.clock()
        everything = view.global_observation
        seats = []
        for seat, info in sorted(everything.role_and_grouping().items()):
            seats.append({"seat": seat, "faction": info.faction, "role": info.role, "operators": len(info.operators)})
        census: collections.Counter = collections.Counter()
        table = unit_table(everything.fields)
        for unit in table.values():
            census[f"{unit['class'][0]}/{unit['where']}"] += 1
        groups = everything.role_and_grouping()
        playing = {p["seat"] for p in players}
        coverage = {}
        for faction in sorted({u["class"][0] for u in table.values()}, key=str):
            units = {u for u, e in table.items() if e["class"][0] == faction}
            listed = {u for info in groups.values() if info.faction == faction for u in info.operators}
            by_players = {u for seat, info in groups.items() if seat in playing for u in info.operators}
            coverage[str(faction)] = {"units": len(units), "listed_for_any_seat": len(units & listed),
                                      "listed_for_a_playing_seat": len(units & by_players),
                                      "seats": sorted(seat for seat, info in groups.items() if info.faction == faction),
                                      "playing_seats": sorted(seat for seat, info in groups.items()
                                                              if info.faction == faction and seat in playing)}
        self.setup_info = {"seats": seats, "players": [{"seat": p["seat"], "faction": p["faction"], "role": p["role"],
                                                         "policy": policies[p["faction"]]} for p in players],
                           "units": dict(sorted(census.items())), "coverage": coverage, "state_form": view.form.value}
        self.seconds += self.clock() - tick

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        tick = self.clock()
        g0, g1 = before.global_observation, after.global_observation
        batch, position = [], 0
        for decision in decisions:
            for j, action in enumerate(decision["actions"]):
                batch.append({"i": position, "seat": decision["seat"], "faction": decision["faction"], "j": j,
                              "action": plain(action)})
                position += 1
        traces = {str(d["seat"]): trace_digest(d["trace"]) for d in decisions}
        rejected = {str(d["seat"]): plain(list(d["trace"].rejected)) for d in decisions if d["trace"].rejected}
        feedback = [plain(entry) for entry in (g1.action_feedback() or ())]
        new_judge, relation, self._judge_keys = judge_delta(list(g0.fields.get("judge_info") or ()),
                                                            list(g1.fields.get("judge_info") or ()), self._judge_keys)
        self.semantics[relation] += 1
        table0, table1 = unit_table(g0.fields), unit_table(g1.fields)
        entry = {"k": index, "cur_step": g0.time().cur_step, "stage": g0.time().stage, "batch": batch,
                 "traces": traces, "feedback": feedback, "judge_new": plain(new_judge), "judge_relation": relation,
                 "judge_lengths": [len(g0.fields.get("judge_info") or ()), len(g1.fields.get("judge_info") or ())],
                 **unit_delta(table0, table1)}
        if rejected:
            entry["rejected"] = rejected
        jm = g1.fields.get("jm_points")
        if jm:
            entry["jm_points"] = plain(jm)
        self.steps.append(entry)
        snapshot = {"k": index, "cur_step": entry["cur_step"], "global": pickle.dumps(dict(g0.fields), protocol=4),
                    "seats": {d["seat"]: {"faction": d["faction"], "policy": d["policy"],
                                          "observation": pickle.dumps(dict(d["observation"]), protocol=4),
                                          "memory": pickle.dumps(d["memory"], protocol=4),
                                          "actions": plain(d["actions"]), "trace": traces[str(d["seat"])]}
                              for d in decisions if d["policy"] in self.policies}}
        self.ring.append(snapshot)
        if any(feedback_code(e) == TRIGGER_CODE for e in feedback):
            self.events.append({"k": index, "window": list(self.ring),
                                "after": pickle.dumps(dict(g1.fields), protocol=4)})
        elif index > 0 and index % self.sample_every == 0:
            self.samples.append(snapshot)
        self.seconds += self.clock() - tick

    def compact(self) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "setup": self.setup_info, "steps": self.steps,
                "events": [e["k"] for e in self.events], "samples": [s["k"] for s in self.samples],
                "judge_relations": dict(sorted(self.semantics.items())), "observer_seconds": self.seconds}

    def windows(self) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "events": self.events, "samples": self.samples}

    def files(self) -> Tuple[bytes, bytes]:
        compact = json.dumps(self.compact(), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        return compact, pickle.dumps(self.windows(), protocol=4)

    def summary(self, compact: bytes, windows: bytes) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "steps": len(self.steps), "events": len(self.events),
                "samples": len(self.samples), "observer_seconds": self.seconds,
                "compact_sha256": hashlib.sha256(compact).hexdigest(), "windows_sha256": hashlib.sha256(windows).hexdigest(),
                "judge_relations": dict(sorted(self.semantics.items()))}


# ----------------------------------------------------------------------------------------------
# Facts and classification


def _number(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _positive(record: Mapping[str, Any]) -> bool:
    damage = _number(record.get("damage"))
    return damage is not None and damage > 0


def _same_action(echo: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    return refusals.same_action(echo, action)


def prior_shots(steps: Sequence[Mapping[str, Any]], k: int, target: Any, depth: int = PRIOR_STEPS) -> List[Dict[str, Any]]:
    """Shots at ``target`` in the ``depth`` steps before decision ``k`` with the engine's feedback on each."""
    found = []
    for entry in steps:
        if not (k - depth <= entry["k"] < k):
            continue
        for item in entry["batch"]:
            action = item["action"]
            if action.get("type") in SHOT_TYPES and action.get("target_obj_id") == target:
                codes = [feedback_code(f) for f in entry["feedback"] if _same_action(f.get("message") or {}, action)]
                found.append({"k": entry["k"], "actor": action.get("obj_id"), "seat": item["seat"],
                              "faction": item["faction"], "type": action.get("type"),
                              "feedback": codes[0] if codes else "absent"})
    return found


def prior_judge(steps: Sequence[Mapping[str, Any]], k: int, target: Any, depth: int = PRIOR_STEPS) -> List[Dict[str, Any]]:
    return [{"k": entry["k"], "attacker": r.get("att_obj_id"), "damage": r.get("damage"), "cur_step": r.get("cur_step"),
             "type": r.get("type")}
            for entry in steps if k - depth <= entry["k"] < k for r in entry["judge_new"] if r.get("target_obj_id") == target]


def event_facts(game: str, entry: Mapping[str, Any], steps: Sequence[Mapping[str, Any]], before: Mapping[str, Any],
                after: Mapping[str, Any], seat_observation: Optional[Mapping[str, Any]], policy_seats: Iterable[int],
                factions: Mapping[int, int]) -> List[Dict[str, Any]]:
    """The factual records of the code-516 refusals of policy seats in one captured step (no interpretation).

    ``before`` and ``after`` are the raw all-seeing observations around the step, ``seat_observation`` the policy
    seat's raw start-of-step observation, ``factions`` maps every seat of ``role_and_grouping_info`` to its faction.
    """
    seats = set(policy_seats)
    start, end = unit_table(before), unit_table(after)
    on_map = {u for u, e in start.items() if e["where"] == "operators"}
    valid = Observation.from_raw(seat_observation, Origin.ENGINE).valid_actions() if seat_observation else None
    records = []
    for feedback in entry["feedback"]:
        message = feedback.get("message") or {}
        if feedback_code(feedback) != TRIGGER_CODE or message.get("actor") not in seats:
            continue
        seat, target, actor = message.get("actor"), message.get("target_obj_id"), message.get("obj_id")
        faction = factions.get(seat)
        mine = [item for item in entry["batch"] if item["seat"] == seat and _same_action(message, item["action"])]
        involved = []
        for item in entry["batch"]:
            action = item["action"]
            if action.get("target_obj_id") == target or action.get("obj_id") == target:
                codes = [feedback_code(f) for f in entry["feedback"] if _same_action(f.get("message") or {}, action)]
                involved.append({"i": item["i"], "j": item["j"], "seat": item["seat"], "faction": item["faction"],
                                 "type": action.get("type"), "actor": action.get("obj_id"),
                                 "role": "target" if action.get("target_obj_id") == target else "actor",
                                 "feedback": codes[0] if codes else "absent"})
        shots = [a for a in involved if a["role"] == "target" and a["type"] in SHOT_TYPES]
        landed = [a for a in shots if a["feedback"] is None]  # same-step shots the engine did not refuse
        earlier = prior_shots(steps, entry["k"], target)
        accepted_earlier = {}
        for shot in earlier:
            if shot["feedback"] is None:
                accepted_earlier[shot["actor"]] = max(accepted_earlier.get(shot["actor"], -1), shot["k"])
        on_target = []
        for record in entry["judge_new"]:
            if record.get("target_obj_id") != target:
                continue
            attacker = record.get("att_obj_id")
            same = [a for a in landed if a["actor"] == attacker or a["actor"] == record.get("guide_obj_id")]
            on_target.append({"attacker": attacker, "attacker_class": start.get(attacker, end.get(attacker, {})).get("class"),
                              "type": record.get("type"), "damage": record.get("damage"), "cur_step": record.get("cur_step"),
                              "same_step_seats": sorted({a["seat"] for a in same}),
                              "earlier_k": accepted_earlier.get(attacker)})
        by_actor = [r for r in entry["judge_new"] if r.get("att_obj_id") == actor and r.get("target_obj_id") == target
                    and actor not in accepted_earlier]  # not explained by the actor's own earlier accepted shot
        linked_ids: Dict[Any, str] = {}
        target_start = start.get(target, {})
        for relation in ("launcher", "car"):
            value = target_start.get(relation)
            if isinstance(value, int) and not isinstance(value, bool) and value not in (0, -1) and value != target:
                linked_ids.setdefault(value, relation)
        for unit, e in start.items():
            if target in (e.get("launch_ids") or []) or target in (e.get("passenger_ids") or []):
                linked_ids.setdefault(unit, "lists the target")
        linked = []
        for unit, relation in sorted(linked_ids.items(), key=lambda item: str(item[0])):
            damage = [r for r in entry["judge_new"] if r.get("target_obj_id") == unit]
            shots_at = []
            for item in entry["batch"]:
                action = item["action"]
                if action.get("type") in SHOT_TYPES and action.get("target_obj_id") == unit:
                    codes = [feedback_code(f) for f in entry["feedback"] if _same_action(f.get("message") or {}, action)]
                    shots_at.append({"i": item["i"], "seat": item["seat"], "faction": item["faction"],
                                     "by_refused_actor": action.get("obj_id") == actor,
                                     "feedback": codes[0] if codes else "absent"})
            linked.append({"id": unit, "relation": relation, "class": start.get(unit, {}).get("class"),
                           "present_before": unit in start, "on_map_before": unit in on_map, "present_after": unit in end,
                           "damage_records": len(damage), "positive_damage": sum(1 for r in damage if _positive(r)),
                           "damage_attackers": sorted({str(r.get("att_obj_id")) for r in damage}),
                           "same_step_shots": shots_at})
        hex_ = target_start.get("hex")
        records.append({
            "schema": FACT_SCHEMA, "game": game, "k": entry["k"], "engine_step": entry["cur_step"],
            "action_type": message.get("type"), "code": TRIGGER_CODE,
            "message": str((feedback.get("error") or {}).get("message"))[:200],
            "message_class": refusals.normalize_message((feedback.get("error") or {}).get("message")),
            "seat": seat, "faction": faction, "actor": actor, "target": target, "weapon": message.get("weapon_id"),
            "batch_size": len(entry["batch"]), "batch_position": mine[0]["i"] if mine else None,
            "seat_position": mine[0]["j"] if mine else None, "passed_project_gate": bool(mine),
            "legal_at_start": None if valid is None else refusals.listed_at_start(message, valid),
            "target_on_map_at_start": target in on_map, "target_class": target_start.get("class"),
            "target_blood_at_start": target_start.get("blood"),
            "target_start": {name: target_start.get(name) for name in WATCHED_FIELDS} if target_start else None,
            "same_target": involved,
            "own_shots": sum(1 for a in shots if a["seat"] == seat),
            "friendly_other_seat_shots": sum(1 for a in shots if a["seat"] != seat and factions.get(a["seat"]) == faction),
            "opposing_shots": sum(1 for a in shots if factions.get(a["seat"]) not in (None, faction)),
            "total_shots": len(shots),
            "opposing_actions_on_target": [a for a in involved if factions.get(a["seat"]) not in (None, faction)
                                           and a["feedback"] is None
                                           and (a["role"] == "target" or a["type"] in (BOARD, UNLOAD))],
            "opposing_unit_actions_in_step": sum(1 for item in entry["batch"]
                                                 if factions.get(item["seat"]) not in (None, faction)
                                                 and "obj_id" in item["action"]),
            "target_present_after": target in end, "target_passenger_after": end.get(target, {}).get("where") == "passengers",
            "target_on_map_after": end.get(target, {}).get("where") == "operators",
            "actor_present_after": actor in end,
            "judge_on_target": on_target, "judge_by_actor_on_target": len(by_actor),
            "judge_relation": entry["judge_relation"],
            "linked": linked,
            "jm_at_target_hex": [p for p in entry.get("jm_points") or [] if p.get("pos") == hex_],
            "target_changes": entry["changed"].get(str(target), {}),
            "feedback_on_target": [{"type": (f.get("message") or {}).get("type"), "seat": (f.get("message") or {}).get("actor"),
                                    "code": feedback_code(f)} for f in entry["feedback"]
                                   if (f.get("message") or {}).get("target_obj_id") == target
                                   or (f.get("message") or {}).get("obj_id") == target],
            "prior_shots_at_target": earlier, "prior_judge_on_target": prior_judge(steps, entry["k"], target),
        })
    return records


def classify(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """The registered category of one factual record, with the rules that matched and the evidence strength."""
    seat, faction = facts["seat"], facts["faction"]
    positive = [r for r in facts["judge_on_target"] if _positive(r)]
    blood = _number(facts.get("target_blood_at_start"))
    attributed: Dict[str, List[Mapping[str, Any]]] = {}
    attributed["H1"] = [r for r in positive if any(s != seat for s in r["same_step_seats"])
                        and r.get("attacker_class") and r["attacker_class"][0] == faction]
    attributed["H2"] = [r for r in positive if r.get("attacker_class") and r["attacker_class"][0] not in (None, faction)]
    attributed["H3"] = [r for r in positive if not r["same_step_seats"] and r.get("earlier_k") is not None]
    matches: Dict[str, str] = {}
    if attributed["H1"]:
        matches["H1"] = "damage record from another friendly seat's same-step shot"
    if attributed["H2"] or facts["opposing_actions_on_target"]:
        matches["H2"] = "opposing-faction action or damage involving the target"
    if attributed["H3"] or any(p.get("status") == 1 for p in facts["jm_at_target_hex"]):
        matches["H3"] = "damage from a shot issued in an earlier step, or an indirect-fire point resolving at its hex"
    linked_gone = [l for l in facts["linked"] if l["present_before"] and not l["present_after"]]
    if not positive and linked_gone:
        matches["H4"] = "no damage record on the target; a linked object was removed in the step"
    changes = facts.get("target_changes") or {}
    transition = (facts["target_passenger_after"] or changes.get("on_board", [None, None])[1] == 1
                  or changes.get("lose_control", [None, None])[1] == 1
                  or changes.get("alive_remain_time", [None, None])[1] == 0)
    if not positive and not linked_gone and not facts["opposing_actions_on_target"] and transition:
        matches["H5"] = "no damage and no linked removal; the target became a passenger or changed state"
    if facts["target_on_map_after"] or facts["judge_by_actor_on_target"]:
        matches["H6"] = "the target is on the map after the step, or the refused shot was adjudicated"
    if len(matches) != 1:
        return {"category": "H7", "matches": sorted(matches), "strength": "none",
                "reason": "no rule matched" if not matches else "more than one rule matched"}
    (category,) = matches
    strength = "moderate"
    if category in ("H1", "H2", "H3"):
        unattributed = [r for r in positive if r not in attributed[category]]
        total = sum(_number(r.get("damage")) or 0.0 for r in attributed[category])
        if blood is not None and attributed[category] and total >= blood and not unattributed:
            strength = "strong"
    elif category == "H4":
        if any(l["positive_damage"] for l in linked_gone) and not facts["judge_on_target"]:
            strength = "strong"
    elif category == "H5":
        strength = "strong" if facts["target_passenger_after"] else "moderate"
    elif category == "H6":
        strength = "strong" if facts["target_on_map_after"] else "moderate"
    return {"category": category, "matches": [category], "strength": strength, "reason": matches[category]}


def conclusion(classifications: Sequence[Mapping[str, Any]], instrumentation_pass: bool) -> str:
    """The registered conclusion from every residual refusal's classification and the instrumentation verdict."""
    explained = [c for c in classifications if c["category"] != "H7"]
    if not instrumentation_pass or not explained:
        return CONCLUSIONS[2]
    if len(explained) == len(classifications) and all(c["strength"] == "strong" for c in explained):
        return CONCLUSIONS[0]
    return CONCLUSIONS[1]


def collisions(game: str, steps: Sequence[Mapping[str, Any]], factions: Mapping[int, int]) -> Dict[str, Any]:
    """Cross-seat and same-seat same-target fire over every captured step of one game (private detail)."""
    cross, cross_steps, same_seat = [], set(), 0
    shots_total = 0
    for entry in steps:
        by_target: Dict[Any, collections.Counter] = collections.defaultdict(collections.Counter)
        for item in entry["batch"]:
            action = item["action"]
            if action.get("type") in SHOT_TYPES:
                by_target[action.get("target_obj_id")][item["seat"]] += 1
                shots_total += 1
        refused = {(f.get("message") or {}).get("target_obj_id") for f in entry["feedback"]
                   if feedback_code(f) == TRIGGER_CODE}
        for target, per_seat in by_target.items():
            same_seat += sum(1 for n in per_seat.values() if n > 1)
            per_faction: Dict[Any, set] = collections.defaultdict(set)
            for s in per_seat:
                per_faction[factions.get(s)].add(s)
            if any(len(group) > 1 for group in per_faction.values()):
                cross.append({"game": game, "k": entry["k"], "target": target, "produced_516": target in refused})
                cross_steps.add(entry["k"])
    return {"shots": shots_total, "cross_seat_collisions": cross, "cross_seat_steps": len(cross_steps),
            "same_seat_repeats": same_seat}


def opposing_unit_actions(steps: Sequence[Mapping[str, Any]], policy_factions: Iterable[int]) -> int:
    active = set(policy_factions)
    return sum(1 for entry in steps for item in entry["batch"]
               if item["faction"] not in active and "obj_id" in item["action"])
