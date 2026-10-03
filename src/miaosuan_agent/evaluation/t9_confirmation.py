"""The registered, staged confirmatory study of ``t9-capacity-allocation-v1`` (``docs/T9_CONFIRMATION.md``).

CONFIRMATORY track (``docs/EXPLORATORY_TRACK.md``): a frozen manifest, a fixed schedule, a statistical analysis plan,
phase gates and a public registration, all pushed before the first engine session. The study tests the unchanged
Sprint 8 candidate against ``baseline-v2`` and the inert control in four phases, each conditional on the registered
gate of the previous one:

* A, primary: scenario 2130511121 head to head, 15 games each of H1 (candidate red against ``baseline-v2`` blue), H2
  (``baseline-v2`` red against candidate blue) and C1 (``baseline-v2`` mirror).
* D, safety screen: the five small frozen scenarios against the inert control, C2 and C3, both arms, 3 games each.
* B, secondary: the three large scenarios against the inert control, C2 and C3, both arms, 15 games each.
* C, secondary: scenarios 2120531121 and 1930331196 head to head as in A.

Everything that decides a result lives here and is pinned by digest in the manifest: the schedule, the margin
convention, the estimands and their interval procedure, the mechanism capture, the integrity checks, the gates and
the disposition. The scripts only read records and call these functions.

Margin convention (frozen): a seat's terminal margin is its side's ``<side>_total`` minus the opponent's, the
engine's own ``<side>_win``. It is zero-sum, so in a C1 game the blue margin is minus the red margin. The primary
estimand is the equally weighted mean of the two seat-specific contrasts (H1 red margin minus the C1 red margin, H2
blue margin minus the C1 blue margin). Resampled as pairs, a C1 game contributes ``(r + b) / 2`` to it, which the
convention makes exactly 0 for every game: the C1 games cancel from the seat-averaged contrast and from every
resample, and the interval is driven by the H1 and H2 games. The code keeps the general paired form, so the identity
is a property of the data, checked per game, not an assumption of the estimator.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import Stage
from ..decision import INERT_ID
from . import manifest as mf
from . import stats
from .execution import RUNTIMES

STUDY_ID = "t9-confirmation-1"
SCHEMA = "miaosuan-t9-confirmation/1"
CAPTURE_SCHEMA = "miaosuan-t9-confirmation-capture/1"
PHASE_SCHEMA = "miaosuan-t9-confirmation-phase/1"
TRACK = "CONFIRMATORY"

CANDIDATE_ID = "t9-capacity-allocation-v1"
V2_ID = "baseline-v2-candidate-shoot-target-reservation"
CANDIDATE_DIGEST = "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa"
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
CANDIDATE_CAPACITY = 4
CANDIDATE_DETOUR = 2.0

RUNTIME = "baseline-v1-runtime-r2"
WORKERS = 32
LEDGER_BASE_SESSION = 2487
SESSION_CAP = 375
STOP_AFTER_CONSECUTIVE_FAILURES = 3

PRIMARY_SCENARIO = "2130511121"
SMALL = ("2010211129", "2010431153", "1910631192", "2010131194", "201033019601")
LARGE = ("2120531121", "1930331196", "2130511121")
H2H_CELLS = ("H1", "H2", "C1")
INERT_CELLS = ("C2-T9", "C2-V2", "C3-T9", "C3-V2")
ARMS = {"T9": CANDIDATE_ID, "V2": V2_ID}

PHASE_ORDER = ("A", "D", "B", "C")
PHASES: Dict[str, Dict[str, Any]] = {
    "A": {"kind": "h2h", "scenarios": (PRIMARY_SCENARIO,), "repetitions": 15, "role": "primary"},
    "D": {"kind": "inert", "scenarios": SMALL, "repetitions": 3, "role": "safety screen"},
    "B": {"kind": "inert", "scenarios": LARGE, "repetitions": 15, "role": "secondary (robustness against the inert control)"},
    "C": {"kind": "h2h", "scenarios": ("2120531121", "1930331196"), "repetitions": 15,
          "role": "secondary (robustness head to head)"},
}

LEVEL = 0.95
BOOTSTRAP = {"method": "studentized bootstrap (bootstrap-t)", "resamples": 20000, "seed": 20261003,
             "draw": "stats.draw over random.Random(seed derived per estimand)",
             "quantiles": "nearest rank, computed exactly (stats.exact_rank_value)"}
#: The project's established tactical margin (shoot-reservation experiment P7, variance-study planning grid).
MATERIAL_MARGIN = 10.0
#: Known factual refusal classes of baseline-v2 (shoot-reservation experiment groups B and C, 720 games).
KNOWN_REFUSAL_CLASSES = (
    (1, 404, "CantMoveKeptPeople"),
    (2, 203, "CantControlDiedOperator"),
    (2, 516, "CantShootToDiedBop"),
    (5, 203, "CantControlDiedOperator"),
)
#: Descriptive flags (never a stop on their own; see ``FLAGS``).
LATENCY_FLAG_P99_MS = 10.0
LATENCY_FLAG_MAX_MS = 5000.0
IDLE_FLAG_UNITS = 1.0
OBJECTIVE_FLAG = 0.5

GROUND = (1, 2)
MOVE = 1
SIDES = {0: "red", 1: "blue"}


# ------------------------------------------------------------------------------------------------
# Design and schedule


def cell_players(cell: str) -> Tuple[str, str]:
    """(red, blue) policies of a cell."""
    if cell == "H1":
        return CANDIDATE_ID, V2_ID
    if cell == "H2":
        return V2_ID, CANDIDATE_ID
    if cell == "C1":
        return V2_ID, V2_ID
    condition, arm = cell.split("-")
    policy = ARMS[arm]
    return (policy, INERT_ID) if condition == "C2" else (INERT_ID, policy)


def cells(phase: str) -> List[Tuple[str, str]]:
    spec = PHASES[phase]
    kinds = H2H_CELLS if spec["kind"] == "h2h" else INERT_CELLS
    return [(scenario, cell) for scenario in spec["scenarios"] for cell in kinds]


def game_id(scenario: str, cell: str, phase: str, repetition: int) -> str:
    return f"{scenario}.{cell}.{phase}.r{repetition:02d}"


def base_order(design_sha256: str, phase: str) -> List[Tuple[str, str]]:
    key = lambda c: hashlib.sha256(f"{design_sha256}:{phase}:{c[0]}:{c[1]}".encode("utf-8")).hexdigest()
    return sorted(cells(phase), key=key)


def schedule(design_sha256: str) -> List[Dict[str, Any]]:
    """Every registered game in dispatch order.

    Within a phase, round r plays repetition r of every cell once; the order within a round is a fixed hash-derived
    base order rotated by one position per round, so every cell plays every round and, in phase A, every position
    of a round exactly five times. Positions are global (1 to 375) and phase positions restart at 1."""
    games: List[Dict[str, Any]] = []
    for phase in PHASE_ORDER:
        base = base_order(design_sha256, phase)
        phase_position = 0
        for repetition in range(1, PHASES[phase]["repetitions"] + 1):
            shift = (repetition - 1) % len(base)
            for scenario, cell in base[shift:] + base[:shift]:
                phase_position += 1
                red, blue = cell_players(cell)
                games.append({"game_id": game_id(scenario, cell, phase, repetition), "phase": phase,
                              "phase_position": phase_position, "position": len(games) + 1, "scenario_id": scenario,
                              "cell": cell, "condition": cell.split("-")[0], "repetition": repetition,
                              "red": red, "blue": blue})
    return games


def phase_sessions(phase: str) -> int:
    return len(cells(phase)) * PHASES[phase]["repetitions"]


def is_study(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any], phase: Optional[str] = None) -> List[mf.GameSpec]:
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    return [mf.GameSpec(game_id=g["game_id"], scenario_id=g["scenario_id"], map_id=scenarios[g["scenario_id"]]["map_id"],
                        condition=g["condition"], red=g["red"], blue=g["blue"], repetition=g["repetition"],
                        max_time=int(scenarios[g["scenario_id"]]["max_time"]))
            for g in manifest["games"] if phase is None or g["phase"] == phase]


def game_policies(spec: mf.GameSpec) -> List[str]:
    return sorted({spec.red, spec.blue} - {INERT_ID})


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def design_digest(design: Mapping[str, Any]) -> str:
    return mf.digest(design)


def build(texts: Mapping[str, Any], shoot_manifest: Mapping[str, Any], shoot_sha256: str,
          policies: Mapping[str, Mapping[str, Any]], scheduler: str, files: Mapping[str, str],
          tests: Mapping[str, str], inputs: Mapping[str, str]) -> Dict[str, Any]:
    """The registered manifest. ``policies``: {policy id: {label, policy_source {sha256, files, sources}}}."""
    if policies[V2_ID]["policy_source"]["sha256"] != V2_DIGEST:
        raise ValueError("baseline-v2's policy source is not the frozen digest")
    if policies[CANDIDATE_ID]["policy_source"]["sha256"] != CANDIDATE_DIGEST:
        raise ValueError("the candidate's policy source is not the frozen Sprint 8 digest")
    used = sorted({scenario for phase in PHASE_ORDER for scenario in PHASES[phase]["scenarios"]})
    scenarios = [dict(s) for s in shoot_manifest["scenarios"] if s["scenario_id"] in used]
    if len(scenarios) != len(used):
        raise ValueError("a phase names a scenario outside the frozen set")
    design = {
        "schema": SCHEMA, "study_id": STUDY_ID, "evaluation_id": STUDY_ID, "track": TRACK,
        "eligible_for_promotion": False, **dict(texts),
        "candidate": {"id": CANDIDATE_ID, "capacity": CANDIDATE_CAPACITY, "detour_factor": CANDIDATE_DETOUR,
                      "policy_source_sha256": CANDIDATE_DIGEST},
        "baseline": {"id": V2_ID, "policy_source_sha256": V2_DIGEST},
        "policies": {k: {"label": v["label"], "policy_source": dict(v["policy_source"])} for k, v in sorted(policies.items())},
        "execution": {"workers": WORKERS, "runtime": RUNTIME, "scheduler": scheduler,
                      "stop_after_consecutive_failures": STOP_AFTER_CONSECUTIVE_FAILURES},
        "runtime_environment": dict(RUNTIMES[RUNTIME]),
        "scenarios": scenarios, "players": [dict(p) for p in shoot_manifest["players"]],
        "randomness": dict(shoot_manifest["randomness"]), "caps": dict(shoot_manifest["caps"]),
        "inputs": {"shoot_manifest_sha256": shoot_sha256, **dict(sorted(inputs.items()))},
        "budget": {"ledger_base_session": LEDGER_BASE_SESSION, "session_cap": SESSION_CAP,
                   "phases": {p: phase_sessions(p) for p in PHASE_ORDER}},
        "phases": {p: {"order": i + 1, "kind": PHASES[p]["kind"], "scenarios": list(PHASES[p]["scenarios"]),
                       "cells": list(H2H_CELLS if PHASES[p]["kind"] == "h2h" else INERT_CELLS),
                       "repetitions": PHASES[p]["repetitions"], "sessions": phase_sessions(p), "role": PHASES[p]["role"],
                       "requires": None if i == 0 else f"gate {PHASE_ORDER[i - 1]}: CONTINUE"}
                   for i, p in enumerate(PHASE_ORDER)},
        "analysis_parameters": {"level": LEVEL, "bootstrap": dict(BOOTSTRAP), "material_margin": MATERIAL_MARGIN,
                                "known_refusal_classes": [list(c) for c in KNOWN_REFUSAL_CLASSES],
                                "flags": {"latency_p99_ms": LATENCY_FLAG_P99_MS, "latency_max_ms": LATENCY_FLAG_MAX_MS,
                                          "idle_units": IDLE_FLAG_UNITS, "objectives": OBJECTIVE_FLAG}},
        "files": dict(sorted(files.items())), "tests": dict(sorted(tests.items())),
    }
    design_sha = design_digest(design)
    total = sum(phase_sessions(p) for p in PHASE_ORDER)
    if total != SESSION_CAP:
        raise ValueError(f"the phases plan {total} sessions, not the cap {SESSION_CAP}")
    return {**design, "design_sha256": design_sha, "games": schedule(design_sha)}


# ------------------------------------------------------------------------------------------------
# Capture


class Tee:
    """Run several read-only observers; one observer's exception never stops the others, and is re-raised after all
    of them ran (``evaluation.game.play`` records it in ``observer_errors``)."""

    def __init__(self, *observers: Any) -> None:
        self.observers = observers

    def _call(self, event: str, *args: Any) -> None:
        errors = []
        for observer in self.observers:
            try:
                getattr(observer, event)(*args)
            except Exception as exc:  # noqa: BLE001 - observers never change the game
                errors.append(f"{type(observer).__name__}.{event}: {type(exc).__name__}: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors)[:300])

    def setup(self, *args: Any) -> None:
        self._call("setup", *args)

    def step(self, *args: Any) -> None:
        self._call("step", *args)


def _summary(values: Sequence[int]) -> Dict[str, int]:
    return {"max": max(values, default=0), "sum": sum(values), "steps_positive": sum(1 for v in values if v > 0)}


def _feedback_parts(entry: Mapping[str, Any]) -> Tuple[Any, Any, Any, Any]:
    message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
    error = entry.get("error")
    code = error.get("code") if isinstance(error, Mapping) else (None if not error else "unspecified")
    return message.get("actor"), message.get("obj_id"), message.get("type"), code


class T9Capture:
    """Read-only mechanism facts of every policy seat (the candidate's and ``baseline-v2``'s), per game.

    Definitions (registered; ``docs/T9_CONFIRMATION.md``, "Mechanism"):

    * move orders: the seat's emitted orders of type 1, and those of ground units (types 1 and 2); from the
      candidate's ``t9`` trace block: kept (the skip reason ``kept: destination under capacity``), re-assigned
      (``replace`` changes not reverted), reverted and withheld (``withhold`` changes, per unit and per decision,
      with each unit's longest run of consecutive withheld decisions), and add-on errors;
    * a re-assigned move refused: an engine feedback entry of the same seat, unit and type 1 with an error code in
      the step the re-assigned move was emitted;
    * start positions: the seat's ground units listed at its first play-stage state; a unit is idle at its start
      for every post-step state in which it still stands on that hex, until it first stands elsewhere (departed),
      leaves the operator list as a passenger (embarked) or disappears (removed); never departed = still on the
      start hex in the final state;
    * waiting in front of a full hex: ground units with a non-empty move path and speed 0 in a post-step state
      (every step, deployment included, as in ``evaluation.exploratory``); objective commitments: per objective the
      ground units standing on it without a path or whose path ends on it, and the largest per step;
    * objectives held: per post-step state of the play stage, the objectives whose flag is the seat's side, counted
      and weighted by their value; holding steps per objective; held in the final state;
    * losses: units (operators or passengers) of the side at its first play-stage state that are listed in neither
      list in the final state.
    """

    def __init__(self) -> None:
        self.policies: Dict[int, str] = {}
        self.factions: List[int] = []
        self.steps = 0
        self.play_steps = 0
        self.first_play_index: Optional[int] = None
        self.first_play_step: Optional[int] = None
        self.moves: Dict[int, collections.Counter] = {}
        self.changes: Dict[int, collections.Counter] = {}
        self.skips: Dict[int, collections.Counter] = {}
        self.addon_errors: Dict[int, int] = {}
        self.withheld_runs: Dict[int, Dict[int, List[int]]] = {}  # faction -> unit -> [last index, run, longest, total]
        self.replaced_refused: Dict[int, collections.Counter] = {}
        self.start_hex: Dict[int, Dict[int, int]] = {}
        self.start_units: Dict[int, set] = {}
        self.at_start: Dict[int, Dict[int, int]] = {}  # faction -> unit -> idle post-step states
        self.left: Dict[int, Dict[int, str]] = {}  # faction -> unit -> departed | embarked | removed
        self.waiting: Dict[int, List[int]] = {0: [], 1: []}
        self.commitment_max: Dict[int, List[int]] = {0: [], 1: []}
        self.held: Dict[int, List[int]] = {0: [], 1: []}
        self.held_value: Dict[int, List[int]] = {0: [], 1: []}
        self.held_steps: Dict[int, collections.Counter] = {0: collections.Counter(), 1: collections.Counter()}
        self.first_hold: Dict[int, Dict[int, int]] = {0: {}, 1: {}}
        self.objective_values: Dict[int, int] = {}
        self._final: Any = None

    def setup(self, view: Any, players: Sequence[Mapping[str, Any]], policies: Mapping[int, str]) -> None:
        self.policies = {int(f): p for f, p in policies.items()}
        self.factions = sorted(f for f, p in self.policies.items() if p != INERT_ID)
        for f in self.factions:
            self.moves[f] = collections.Counter()
            self.changes[f] = collections.Counter()
            self.skips[f] = collections.Counter()
            self.addon_errors[f] = 0
            self.withheld_runs[f] = {}
            self.replaced_refused[f] = collections.Counter()

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        g0, g1 = before.global_observation, after.global_observation
        self.steps += 1
        kinds = {u.obj_id: u.fields.get("type") for u in g0.operators()}
        replaced: Dict[Tuple[int, int], int] = {}
        for decision in decisions:
            f = decision["faction"]
            if f not in self.factions:
                continue
            for action in decision["submitted"]:
                if action.get("type") == MOVE:
                    self.moves[f]["all"] += 1
                    if kinds.get(action.get("obj_id")) in GROUND:
                        self.moves[f]["ground"] += 1
            trace = decision["trace"]
            if getattr(trace, "addon_name", "") != "t9":
                continue
            reverted = set()
            for raw in getattr(trace, "changes", ()):
                change = json.loads(raw)
                kind = change["kind"]
                self.changes[f][kind] += 1
                if kind == "withhold":
                    runs = self.withheld_runs[f].setdefault(int(change["obj_id"]), [-2, 0, 0, 0])
                    runs[1] = runs[1] + 1 if runs[0] == index - 1 else 1
                    runs[0], runs[2], runs[3] = index, max(runs[2], runs[1]), runs[3] + 1
                elif kind == "replace":
                    replaced[(decision["seat"], int(change["obj_id"]))] = f
                elif kind == "revert":
                    reverted.add((decision["seat"], int(change["obj_id"])))
            for key in reverted:
                replaced.pop(key, None)
            for reason, count in getattr(trace, "skipped", ()):
                self.skips[f][reason] += count
            if getattr(trace, "addon_error", None):
                self.addon_errors[f] += 1
        for entry in g1.action_feedback() or ():
            actor, obj_id, kind, code = _feedback_parts(entry)
            if kind == MOVE and code is not None and (actor, obj_id) in replaced:
                self.replaced_refused[replaced[(actor, obj_id)]][str(code)] += 1
        cities = {c.coord: c for c in (g1.cities() or ())}
        commitments = {0: collections.Counter(), 1: collections.Counter()}
        waiting = {0: 0, 1: 0}
        for unit in g1.operators():
            color = unit.color
            if color not in (0, 1) or unit.fields.get("type") not in GROUND:
                continue
            path = unit.move_path or ()
            if path and unit.fields.get("speed") == 0:
                waiting[color] += 1
            end = path[-1] if path else unit.cur_hex
            if end in cities:
                commitments[color][end] += 1
        for color in (0, 1):
            self.waiting[color].append(waiting[color])
            self.commitment_max[color].append(max(commitments[color].values(), default=0))
        if g0.time().stage != Stage.PLAY:
            return
        if self.first_play_index is None:
            self.first_play_index, self.first_play_step = index, g0.time().cur_step
            for f in self.factions:
                self.start_hex[f] = {u.obj_id: u.cur_hex for u in g0.operators()
                                     if u.color == f and u.fields.get("type") in GROUND}
                self.start_units[f] = {u.obj_id for u in tuple(g0.operators()) + tuple(g0.passengers()) if u.color == f}
                self.at_start[f] = {u: 0 for u in self.start_hex[f]}
                self.left[f] = {}
            self.objective_values = {c.coord: (c.value if isinstance(c.value, int) else 0)
                                     for c in (g0.cities() or ())}
        self.play_steps += 1
        listed = {u.obj_id: u for u in g1.operators()}
        passengers = {u.obj_id for u in g1.passengers()}
        for f in self.factions:
            for obj_id, start in self.start_hex[f].items():
                if obj_id in self.left[f]:
                    continue
                unit = listed.get(obj_id)
                if unit is None:
                    self.left[f][obj_id] = "embarked" if obj_id in passengers else "removed"
                elif unit.cur_hex != start:
                    self.left[f][obj_id] = "departed"
                else:
                    self.at_start[f][obj_id] += 1
        for color in (0, 1):
            held = [c for c in cities.values() if c.flag == color]
            self.held[color].append(len(held))
            self.held_value[color].append(sum(self.objective_values.get(c.coord, 0) for c in held))
            for city in held:
                self.held_steps[color][city.coord] += 1
                self.first_hold[color].setdefault(city.coord, g1.time().cur_step)
        self._final = g1

    def seat_facts(self, f: int) -> Dict[str, Any]:
        moves, changes, skips = self.moves[f], self.changes[f], self.skips[f]
        runs = self.withheld_runs[f]
        longest = sorted(r[2] for r in runs.values())
        idle = self.at_start.get(f, {})
        left = self.left.get(f, {})
        never = sorted(u for u in idle if u not in left)
        durations = sorted(idle.values())
        final_units = set()
        if self._final is not None:
            final_units = {u.obj_id for u in tuple(self._final.operators()) + tuple(self._final.passengers())
                           if u.color == f}
        start_units = self.start_units.get(f, set())
        play = max(self.play_steps, 1)
        final_cities = [c for c in (self._final.cities() or ())] if self._final is not None else []
        return {
            "policy": self.policies[f],
            "moves": {"emitted": moves["all"], "emitted_ground": moves["ground"],
                      "kept": skips.get("kept: destination under capacity", 0),
                      "replaced": changes["replace"], "reverted": changes["revert"],
                      "redirected": changes["replace"] - changes["revert"], "withheld": changes["withhold"],
                      "unreadable_destination": skips.get("move without a readable destination", 0),
                      "replaced_refused": dict(sorted(self.replaced_refused[f].items())),
                      "addon_errors": self.addon_errors[f]},
            "withholding": {"units": len(runs), "unit_decisions": sum(r[3] for r in runs.values()),
                            "longest_run_max": longest[-1] if longest else 0,
                            "longest_run_median": stats.nearest_rank(longest, 50) if longest else 0},
            "start_positions": {"ground_units": len(idle), "never_departed": len(never),
                                "departed": sum(1 for v in left.values() if v == "departed"),
                                "embarked": sum(1 for v in left.values() if v == "embarked"),
                                "removed_before_leaving": sum(1 for v in left.values() if v == "removed"),
                                "idle_unit_steps": sum(durations),
                                "idle_steps_median": stats.nearest_rank(durations, 50) if durations else 0,
                                "idle_steps_max": durations[-1] if durations else 0,
                                "units_idle_half_play": sum(1 for d in durations if 2 * d >= play)},
            "waiting_in_front_of_full_hex": _summary(self.waiting[f]),
            "max_objective_commitment": _summary(self.commitment_max[f]),
            "objectives": {"count": len(self.objective_values),
                           "held_steps": sum(self.held[f]), "held_value_steps": sum(self.held_value[f]),
                           "mean_held": sum(self.held[f]) / play, "max_held": max(self.held[f], default=0),
                           "held_at_end": sum(1 for c in final_cities if c.flag == f),
                           "held_value_at_end": sum(self.objective_values.get(c.coord, 0) for c in final_cities
                                                    if c.flag == f),
                           "ever_held": len(self.held_steps[f]),
                           "first_hold_step_min": min(self.first_hold[f].values(), default=None)},
            "losses": {"start_units": len(start_units), "lost": len(start_units - final_units)},
        }

    def compact(self) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "steps": self.steps, "play_steps": self.play_steps,
                "first_play_step": self.first_play_step,
                "seats": {str(f): self.seat_facts(f) for f in self.factions},
                "series_checks": {str(c): {"waiting": _summary(self.waiting[c]),
                                           "commitment_max": _summary(self.commitment_max[c])} for c in (0, 1)},
                "addon_changes": {f"{f}:{k}": v for f in self.factions for k, v in sorted(self.changes[f].items())},
                "addon_skips": {str(f): dict(sorted(self.skips[f].items())) for f in self.factions if self.skips[f]}}

    def file(self) -> bytes:
        return json.dumps(self.compact(), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"


# ------------------------------------------------------------------------------------------------
# Per-game facts


def seat_margin(scores: Mapping[str, Any], faction: int) -> int:
    own, other = SIDES[faction], SIDES[1 - faction]
    return int(scores[f"{own}_total"]) - int(scores[f"{other}_total"])


def margin_identity(scores: Mapping[str, Any]) -> bool:
    """The engine's own ``<side>_win`` equals the frozen margin for both sides."""
    return all(scores.get(f"{SIDES[f]}_win") == seat_margin(scores, f) for f in (0, 1))


def refusal_classes(seat: Mapping[str, Any]) -> Dict[Tuple[int, int, str], int]:
    out: Dict[Tuple[int, int, str], int] = {}
    for fact in seat.get("refusal_facts") or ():
        key = (fact.get("action_type"), fact.get("code"), str(fact.get("message_class")))
        out[key] = out.get(key, 0) + int(fact.get("count", 1))
    return out


def latency_ms(values_us: Sequence[int]) -> Dict[str, Any]:
    ordered = sorted(values_us)
    if not ordered:
        return {"decisions": 0}
    pick = lambda p: stats.exact_rank_value(ordered, p) / 1e3
    return {"decisions": len(ordered), "p50_ms": pick(50), "p99_ms": pick(99), "max_ms": ordered[-1] / 1e3,
            "over_100ms": sum(1 for v in ordered if v > 100_000), "over_1s": sum(1 for v in ordered if v > 1_000_000)}


def game_facts(entry: Mapping[str, Any], record: Optional[Mapping[str, Any]], capture: Optional[Mapping[str, Any]],
               explore: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """One scheduled game: completion, margins, per-seat safety facts and mechanism facts.

    ``entry`` is the manifest's game; ``record`` its private record (None if absent); ``capture`` and ``explore``
    the decoded T9 and exploratory capture files (None if absent)."""
    facts: Dict[str, Any] = {k: entry[k] for k in ("game_id", "phase", "phase_position", "scenario_id", "cell",
                                                   "repetition", "red", "blue")}
    if record is None:
        facts.update(status="MISSING", completed=False)
        return facts
    scores = record.get("final_scores") or {}
    facts.update(status=record.get("status"), completed=record.get("status") == "COMPLETED",
                 completion=record.get("completion"), steps=record.get("steps"), session=record.get("session"),
                 wall_seconds=(record.get("timings_seconds") or {}).get("wall"),
                 observer_errors=len(record.get("observer_errors") or ()))
    if scores and all(f"{s}_total" in scores for s in ("red", "blue")):
        facts["margins"] = {"red": seat_margin(scores, 0), "blue": seat_margin(scores, 1)}
        facts["margin_identity"] = margin_identity(scores)
        facts["scores"] = {k: scores[k] for k in sorted(scores)}
    seats: Dict[str, Any] = {}
    for seat in record.get("seats") or ():
        if seat["policy"] == INERT_ID:
            continue
        f = seat["faction"]
        seats[SIDES[f]] = {
            "policy": seat["policy"],
            "actions_by_type": {str(k): v for k, v in sorted(seat.get("actions_by_type", {}).items())},
            "contract_errors": seat.get("contract_errors", 0),
            "gate_rejections": sum((seat.get("gate_rejections") or {}).values()),
            "replay_checks": seat.get("replay_checks", 0), "replay_mismatches": seat.get("replay_mismatches", 0),
            "refusal_classes": [[*k, v] for k, v in sorted(refusal_classes(seat).items(), key=lambda kv: str(kv[0]))],
            "latency": latency_ms(seat.get("latency_us") or ()),
        }
        if capture is not None and str(f) in capture.get("seats", {}):
            seats[SIDES[f]]["mechanism"] = capture["seats"][str(f)]
    facts["seats"] = seats
    facts["capture_checks"] = capture_checks(record, capture, explore)
    return facts


def capture_checks(record: Mapping[str, Any], capture: Optional[Mapping[str, Any]],
                   explore: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Two independently produced counts must agree: the T9 capture against the exploratory capture (waiting units,
    largest commitment, add-on changes and skips) and against the record (move orders of every policy seat)."""
    problems: List[str] = []
    if capture is None or explore is None:
        return {"ok": False, "problems": ["capture file missing"]}
    if capture.get("schema") != CAPTURE_SCHEMA:
        problems.append("T9 capture schema")
    for color in ("0", "1"):
        mine, theirs = capture["series_checks"][color], explore
        if mine["waiting"] != theirs["waiting_ground_units"][color]:
            problems.append(f"waiting series of side {color}")
        if mine["commitment_max"] != theirs["max_objective_commitment"][color]:
            problems.append(f"commitment series of side {color}")
    if capture.get("addon_changes", {}) != explore.get("addon_changes", {}):
        problems.append("add-on changes")
    if capture.get("addon_skips", {}) != explore.get("addon_skips", {}):
        problems.append("add-on skips")
    for seat in record.get("seats") or ():
        if seat["policy"] == INERT_ID:
            continue
        mine = capture.get("seats", {}).get(str(seat["faction"]))
        recorded = int((seat.get("actions_by_type") or {}).get("1", (seat.get("actions_by_type") or {}).get(1, 0)))
        if mine is None or mine["moves"]["emitted"] != recorded:
            problems.append(f"move orders of side {seat['faction']}")
    if capture.get("steps") != record.get("steps"):
        problems.append("step count")
    return {"ok": not problems, "problems": problems}


# ------------------------------------------------------------------------------------------------
# Estimands and intervals


@dataclass(frozen=True)
class Stratum:
    """Independent experimental units (games) of one stratum, their per-unit values and the stratum's weight."""

    name: str
    weight: float
    values: Tuple[float, ...]


def _variance(values: Sequence[float]) -> float:
    v = stats.variance(values)
    return 0.0 if v is None else v


def estimate(strata: Sequence[Stratum]) -> float:
    return sum(s.weight * sum(s.values) / len(s.values) for s in strata)


def standard_error(strata: Sequence[Stratum]) -> float:
    return math.sqrt(sum(s.weight ** 2 * _variance(s.values) / len(s.values) for s in strata))


def welch_df(strata: Sequence[Stratum]) -> Optional[float]:
    terms = [(s.weight ** 2 * _variance(s.values) / len(s.values), len(s.values)) for s in strata]
    terms = [(a, n) for a, n in terms if a > 0 and n > 1]
    if not terms:
        return None
    return sum(a for a, _ in terms) ** 2 / sum(a * a / (n - 1) for a, n in terms)


def seed_for(name: str) -> int:
    return int(hashlib.sha256(f"{BOOTSTRAP['seed']}:{name}".encode("utf-8")).hexdigest()[:12], 16)


def contrast(strata: Sequence[Stratum], name: str, resamples: int = BOOTSTRAP["resamples"],
             level: float = LEVEL) -> Dict[str, Any]:
    """The weighted sum of stratum means with its registered studentized-bootstrap interval, and, as non-decisive
    sensitivity, the percentile-bootstrap interval of the same resamples and the Welch interval.

    Each stratum is resampled independently with replacement at the level of its experimental units (a C1 game is
    one unit carrying both seat outcomes). With SE* the plug-in standard error of a resample, t* = (estimate* -
    estimate) / SE*; the interval is [estimate - q(1 - a/2) SE, estimate - q(a/2) SE] with nearest-rank quantiles
    q of t*. A resample with SE* = 0 gives t* = 0 when its estimate equals the observed one and an infinite t*
    of the deviation's sign otherwise."""
    if any(not s.values for s in strata):
        return {"estimable": False, "reason": "a stratum has no observation",
                "n": {s.name: len(s.values) for s in strata}}
    point, se = estimate(strata), standard_error(strata)
    rng = random.Random(seed_for(name))
    t_values: List[float] = []
    means: List[float] = []
    for _ in range(resamples):
        resampled = []
        for s in strata:
            n = len(s.values)
            resampled.append(Stratum(s.name, s.weight, tuple(s.values[stats.draw(rng, n)] for _ in range(n))))
        value, err = estimate(resampled), standard_error(resampled)
        means.append(value)
        if err > 0:
            t_values.append((value - point) / err)
        else:
            t_values.append(0.0 if value == point else math.copysign(math.inf, value - point))
    tail = (1.0 - level) / 2.0 * 100.0
    q_low, q_high = stats.exact_rank_value(t_values, tail), stats.exact_rank_value(t_values, 100.0 - tail)
    low = point - q_high * se if se > 0 else point
    high = point - q_low * se if se > 0 else point
    p_low, p_high = stats.percentile_interval(means, level)
    df = welch_df(strata)
    if df is not None:
        t = stats.t_quantile(0.5 + level / 2.0, df)
        welch = (point - t * se, point + t * se)
    else:
        welch = (point, point) if se == 0 else (None, None)
    return {"estimable": True, "estimate": point, "se": se, "ci_low": low, "ci_high": high, "level": level,
            "method": BOOTSTRAP["method"], "resamples": resamples, "seed": seed_for(name),
            "percentile_ci": [p_low, p_high], "welch_ci": list(welch), "welch_df": df,
            "strata": {s.name: {"n": len(s.values), "weight": s.weight, "mean": sum(s.values) / len(s.values),
                                "sd": stats.sd(s.values)} for s in strata}}


def h2h_strata(games: Sequence[Mapping[str, Any]], scenario: str) -> Dict[str, List[Stratum]]:
    """The strata of one head-to-head scenario's completed games: the primary-form contrast and the two seat
    contrasts. C1 games enter as units: their per-game value is (red + blue) / 2 for the seat average."""
    def margins(cell: str) -> List[Mapping[str, int]]:
        return [g["margins"] for g in games if g["scenario_id"] == scenario and g["cell"] == cell
                and g.get("completed") and "margins" in g]

    h1 = tuple(float(m["red"]) for m in margins("H1"))
    h2 = tuple(float(m["blue"]) for m in margins("H2"))
    c1 = margins("C1")
    return {
        "seat_average": [Stratum("H1 red", 0.5, h1), Stratum("H2 blue", 0.5, h2),
                         Stratum("C1 seat average", -1.0, tuple((m["red"] + m["blue"]) / 2.0 for m in c1))],
        "red": [Stratum("H1 red", 1.0, h1), Stratum("C1 red", -1.0, tuple(float(m["red"]) for m in c1))],
        "blue": [Stratum("H2 blue", 1.0, h2), Stratum("C1 blue", -1.0, tuple(float(m["blue"]) for m in c1))],
    }


def inert_strata(games: Sequence[Mapping[str, Any]], scenario: str, condition: str) -> List[Stratum]:
    side = "red" if condition == "C2" else "blue"

    def margins(arm: str) -> Tuple[float, ...]:
        return tuple(float(g["margins"][side]) for g in games if g["scenario_id"] == scenario
                     and g["cell"] == f"{condition}-{arm}" and g.get("completed") and "margins" in g)

    return [Stratum("T9", 1.0, margins("T9")), Stratum("V2", -1.0, margins("V2"))]


def mean_or_none(values: Sequence[float]) -> Optional[float]:
    return sum(values) / len(values) if values else None


# ------------------------------------------------------------------------------------------------
# Integrity, safety and gates


def ledger_audit(ledger: Sequence[Mapping[str, Any]], manifest_sha256: str, schedule_ids: Iterable[str],
                 base: int = LEDGER_BASE_SESSION, cap: int = SESSION_CAP) -> Dict[str, Any]:
    """The study's sessions in the append-only ledger: every session opened after ``base`` must be one of this
    study's scheduled games under the registered manifest, opened once, closed (or recovered) with integrity ok,
    and each record's state must continue the previous record's (the chain of state hashes is read from the ledger;
    the state file itself is never read here)."""
    ids = set(schedule_ids)
    problems: List[str] = []
    opened: Dict[str, Mapping[str, Any]] = {}
    games: Dict[str, str] = {}
    ended: Dict[str, Mapping[str, Any]] = {}
    previous = None
    for record in ledger:
        session = record.get("session")
        if session is not None and int(session) > base:
            event = record.get("event")
            if event == "session-open":
                harness = record.get("harness") or {}
                if harness.get("manifest_sha256") != manifest_sha256:
                    problems.append(f"session {session} is not under the registered manifest")
                game = harness.get("game_id")
                if game not in ids:
                    problems.append(f"session {session} plays an unscheduled game {game}")
                elif game in games:
                    problems.append(f"game {game} opened twice (sessions {games[game]} and {session})")
                else:
                    games[game] = session
                opened[session] = record
            elif event in ("session-close", "session-recovered"):
                if session in ended:
                    problems.append(f"session {session} ended twice")
                ended[session] = record
                if event == "session-recovered":
                    problems.append(f"session {session} was recovered (never closed by its game)")
                elif not (record.get("integrity") or {}).get("ok"):
                    problems.append(f"session {session} closed with an integrity failure")
        if previous is not None and record.get("event") == "session-open" and int(record["session"]) > base:
            if record.get("state") != previous.get("state"):
                problems.append(f"session {record['session']} opened with a state other than the previous record's")
        previous = record
    unclosed = sorted(set(opened) - set(ended))
    if unclosed:
        problems.append(f"unclosed sessions {unclosed}")
    used = len(opened)
    if used > cap:
        problems.append(f"{used} sessions exceed the cap of {cap}")
    return {"sessions": used, "games": dict(sorted(games.items())), "closed": len(ended), "unclosed": unclosed,
            "ok": not problems, "problems": problems}


def record_identity_problems(record: Mapping[str, Any], manifest: Mapping[str, Any], manifest_sha256: str) -> List[str]:
    problems = []
    harness = record.get("harness") or {}
    if harness.get("manifest_sha256") != manifest_sha256:
        problems.append("manifest digest")
    if harness.get("dirty") is not False:
        problems.append("dirty or unknown harness tree")
    if harness.get("study") != STUDY_ID:
        problems.append("study id")
    expected = {p: manifest["policies"][p]["policy_source"]["sha256"]
                for p in {record["policies"]["red"], record["policies"]["blue"]} - {INERT_ID}}
    if harness.get("policy_sources") != dict(sorted(expected.items())):
        problems.append("policy sources")
    if harness.get("runtime") != RUNTIME or harness.get("thread_env") != RUNTIMES[RUNTIME]:
        problems.append("runtime")
    execution = harness.get("execution") or {}
    if (execution.get("mode") != "shared" or execution.get("workers") != WORKERS
            or execution.get("scheduler") != manifest["execution"]["scheduler"]):
        problems.append("execution (mode, workers or scheduler)")
    if record.get("engine_version") != "4.1.0":
        problems.append("engine version")
    if not str(record.get("python", "")).startswith("3.10."):
        problems.append("python version")
    close = record.get("session_close") or {}
    if not (close.get("integrity") or {}).get("ok", False):
        problems.append("session close integrity")
    return problems


def candidate_seats(game: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [s for s in (game.get("seats") or {}).values() if s["policy"] == CANDIDATE_ID]


def baseline_seats(game: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [s for s in (game.get("seats") or {}).values() if s["policy"] == V2_ID]


def systemic_checks(games: Sequence[Mapping[str, Any]], known_extra: Iterable[Tuple[int, int, str]] = ()) -> Dict[str, Any]:
    """Systemic failures of a phase (each one fails its gate): contract errors, project-gate rejections, replay
    mismatches, add-on errors, observer errors, refused re-assigned moves without a known class, and factual
    refusal classes of a candidate seat that are neither known ``baseline-v2`` classes nor seen in a
    ``baseline-v2`` seat of this study."""
    totals = collections.Counter()
    known = {tuple(c) for c in KNOWN_REFUSAL_CLASSES} | {tuple(c) for c in known_extra}
    for game in games:
        for seat in (game.get("seats") or {}).values():
            if seat["policy"] == V2_ID:
                known |= {tuple(c[:3]) for c in seat["refusal_classes"]}
    new_classes = collections.Counter()
    for game in games:
        totals["observer_errors"] += game.get("observer_errors", 0)
        for seat in (game.get("seats") or {}).values():
            totals["contract_errors"] += seat["contract_errors"]
            totals["gate_rejections"] += seat["gate_rejections"]
            totals["replay_mismatches"] += seat["replay_mismatches"]
            mechanism = seat.get("mechanism") or {}
            totals["addon_errors"] += (mechanism.get("moves") or {}).get("addon_errors", 0)
            if seat["policy"] == CANDIDATE_ID:
                for c in seat["refusal_classes"]:
                    if tuple(c[:3]) not in known:
                        new_classes[f"{c[0]}/{c[1]}/{c[2]}"] += c[3]
    failures = [k for k in ("contract_errors", "gate_rejections", "replay_mismatches", "addon_errors",
                            "observer_errors") if totals[k]]
    if new_classes:
        failures.append("new refusal class in a candidate seat")
    return {"totals": dict(sorted(totals.items())), "new_refusal_classes": dict(sorted(new_classes.items())),
            "known_classes": sorted("/".join(map(str, c)) for c in known), "failures": failures, "ok": not failures}


def latency_flags(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Descriptive: candidate decisions pooled per configuration against the registered absolute thresholds."""
    flags = []
    pooled: Dict[str, Dict[str, Any]] = {}
    by_config: Dict[str, Dict[str, List[float]]] = collections.defaultdict(lambda: {"p99": [], "max": []})
    for game in games:
        for seat in candidate_seats(game):
            lat = seat["latency"]
            if lat.get("decisions"):
                key = f"{game['scenario_id']} {game['cell']}"
                by_config[key]["p99"].append(lat["p99_ms"])
                by_config[key]["max"].append(lat["max_ms"])
    for key, values in sorted(by_config.items()):
        pooled[key] = {"p99_ms_max_game": max(values["p99"]), "max_ms": max(values["max"])}
        if max(values["p99"]) > LATENCY_FLAG_P99_MS or max(values["max"]) > LATENCY_FLAG_MAX_MS:
            flags.append(key)
    return {"by_configuration": pooled, "flagged": flags}


def phase_games(manifest: Mapping[str, Any], phase: str) -> List[Mapping[str, Any]]:
    return [g for g in manifest["games"] if g["phase"] == phase]


def completion_checks(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    status = collections.Counter(g["status"] for g in games)
    not_completed = [g["game_id"] for g in games if not g.get("completed")]
    identity = [g["game_id"] for g in games if g.get("completed") and not g.get("margin_identity", False)]
    return {"scheduled": len(games), "status": dict(sorted(status.items())), "not_completed": not_completed,
            "margin_identity_failures": identity, "ok": not not_completed and not identity and bool(games)}


def h2h_analysis(games: Sequence[Mapping[str, Any]], scenario: str, phase: str,
                 resamples: int = BOOTSTRAP["resamples"]) -> Dict[str, Any]:
    strata = h2h_strata(games, scenario)
    out = {name: contrast(s, f"{phase}:{scenario}:{name}", resamples) for name, s in strata.items()}
    c1 = [g for g in games if g["scenario_id"] == scenario and g["cell"] == "C1" and g.get("completed")]
    out["c1_seat_average_values"] = sorted({(g["margins"]["red"] + g["margins"]["blue"]) / 2.0 for g in c1})
    return out


def inert_analysis(games: Sequence[Mapping[str, Any]], scenario: str, condition: str, phase: str,
                   resamples: int = BOOTSTRAP["resamples"]) -> Dict[str, Any]:
    strata = inert_strata(games, scenario, condition)
    result = contrast(strata, f"{phase}:{scenario}:{condition}", resamples)
    t9, v2 = strata[0].values, strata[1].values
    result["pairwise_range"] = ([min(t9) - max(v2), max(t9) - min(v2)] if t9 and v2 else None)
    result["values"] = {"T9": list(t9), "V2": list(v2)}
    return result


def mechanism_summary(games: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Per configuration and policy: means over completed games of the registered mechanism counts."""
    keys = (("moves", "emitted_ground"), ("moves", "kept"), ("moves", "redirected"), ("moves", "withheld"),
            ("moves", "reverted"), ("withholding", "units"), ("withholding", "longest_run_max"),
            ("start_positions", "ground_units"), ("start_positions", "never_departed"),
            ("start_positions", "idle_unit_steps"), ("start_positions", "idle_steps_max"),
            ("start_positions", "units_idle_half_play"), ("waiting_in_front_of_full_hex", "max"),
            ("waiting_in_front_of_full_hex", "sum"), ("max_objective_commitment", "max"),
            ("objectives", "mean_held"), ("objectives", "held_at_end"), ("objectives", "held_value_at_end"),
            ("objectives", "held_value_steps"), ("losses", "lost"))
    groups: Dict[str, List[Mapping[str, Any]]] = collections.defaultdict(list)
    refused: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for game in games:
        if not game.get("completed"):
            continue
        for side, seat in sorted((game.get("seats") or {}).items()):
            if "mechanism" not in seat:
                continue
            label = f"{game['scenario_id']} {game['cell']} {side} {'T9' if seat['policy'] == CANDIDATE_ID else 'V2'}"
            groups[label].append(seat["mechanism"])
            refused[label].update(seat["mechanism"]["moves"]["replaced_refused"])
    out = {}
    for label, items in sorted(groups.items()):
        out[label] = {"games": len(items), **{f"{a}.{b}": sum(i[a][b] for i in items) / len(items) for a, b in keys},
                      "replaced_refused": dict(sorted(refused[label].items()))}
    return out


def flags(games: Sequence[Mapping[str, Any]], phase: str) -> Dict[str, Any]:
    """Descriptive flags of inert-control phases, per configuration (candidate arm minus baseline arm):
    idle (mean ground units never leaving their start, difference at least ``IDLE_FLAG_UNITS``), objectives (mean
    objectives held at the end, difference at most minus ``OBJECTIVE_FLAG``) and latency. Never a stop alone."""
    out: Dict[str, Any] = {"idle": [], "objectives": [], "latency": latency_flags(games)["flagged"]}
    if PHASES[phase]["kind"] != "inert":
        return out
    for scenario in PHASES[phase]["scenarios"]:
        for condition in ("C2", "C3"):
            side = "red" if condition == "C2" else "blue"

            def values(arm: str, a: str, b: str) -> List[float]:
                return [g["seats"][side]["mechanism"][a][b] for g in games
                        if g["scenario_id"] == scenario and g["cell"] == f"{condition}-{arm}" and g.get("completed")
                        and "mechanism" in g.get("seats", {}).get(side, {})]

            idle_t9, idle_v2 = values("T9", "start_positions", "never_departed"), values("V2", "start_positions", "never_departed")
            if idle_t9 and idle_v2 and mean_or_none(idle_t9) - mean_or_none(idle_v2) >= IDLE_FLAG_UNITS:
                out["idle"].append(f"{scenario} {condition}")
            held_t9, held_v2 = values("T9", "objectives", "held_at_end"), values("V2", "objectives", "held_at_end")
            if held_t9 and held_v2 and mean_or_none(held_t9) - mean_or_none(held_v2) <= -OBJECTIVE_FLAG:
                out["objectives"].append(f"{scenario} {condition}")
    return out


def analyse_phase(manifest: Mapping[str, Any], phase: str, games: Sequence[Mapping[str, Any]],
                  ledger: Mapping[str, Any], identity_problems: Mapping[str, Sequence[str]],
                  prior_games: Sequence[Mapping[str, Any]] = (), resamples: int = BOOTSTRAP["resamples"]) -> Dict[str, Any]:
    """The registered analysis and gate of one phase. ``games``: :func:`game_facts` of every scheduled game of the
    phase; ``ledger``: :func:`ledger_audit`; ``identity_problems``: per game id, :func:`record_identity_problems`;
    ``prior_games``: facts of the earlier phases (their ``baseline-v2`` refusal classes count as known)."""
    expected = [g["game_id"] for g in phase_games(manifest, phase)]
    if [g["game_id"] for g in games] != expected:
        raise ValueError("the facts do not cover exactly the phase's scheduled games in order")
    completion = completion_checks(games)
    captures_bad = sorted(g["game_id"] for g in games if g.get("completed") and not g["capture_checks"]["ok"])
    identity_bad = {k: list(v) for k, v in sorted(identity_problems.items()) if v}
    integrity = {"ledger": ledger, "records_identity": identity_bad, "captures": captures_bad,
                 "ok": bool(ledger["ok"] and not identity_bad and not captures_bad)}
    prior_known = set()
    for game in prior_games:
        for seat in baseline_seats(game):
            prior_known |= {tuple(c[:3]) for c in seat["refusal_classes"]}
    systemic = systemic_checks(games, prior_known)
    result: Dict[str, Any] = {"schema": PHASE_SCHEMA, "study_id": STUDY_ID, "phase": phase,
                              "role": PHASES[phase]["role"], "completion": completion, "integrity": integrity,
                              "systemic": systemic, "flags": flags(games, phase),
                              "mechanism": mechanism_summary(games)}
    adverse: List[str] = []
    testable = completion["ok"] and integrity["ok"]
    if PHASES[phase]["kind"] == "h2h":
        analyses = {}
        for scenario in PHASES[phase]["scenarios"]:
            analyses[scenario] = h2h_analysis(games, scenario, phase, resamples)
        result["head_to_head"] = analyses
        if phase == "A":
            primary = analyses[PRIMARY_SCENARIO]["seat_average"]
            result["primary"] = {
                "tested": testable, "estimate": primary.get("estimate"), "ci_low": primary.get("ci_low"),
                "ci_high": primary.get("ci_high"),
                "supported": bool(testable and primary.get("estimable") and primary["ci_low"] > 0),
                "label": ("registered primary test" if testable else
                          "NOT TESTED: the phase is incomplete or failed integrity; the figures are descriptive")}
    else:
        analyses = {}
        for scenario in PHASES[phase]["scenarios"]:
            for condition in ("C2", "C3"):
                key = f"{scenario} {condition}"
                analyses[key] = inert_analysis(games, scenario, condition, phase, resamples)
                a = analyses[key]
                if phase == "D" and a.get("estimable") and a["estimate"] < -MATERIAL_MARGIN:
                    adverse.append(f"{key}: mean margin difference {a['estimate']:+.2f} below -{MATERIAL_MARGIN:g}")
                if phase == "B" and a.get("estimable") and a["ci_high"] < -MATERIAL_MARGIN:
                    adverse.append(f"{key}: interval upper limit {a['ci_high']:+.2f} below -{MATERIAL_MARGIN:g}")
        result["against_inert"] = analyses
    result["adverse_signals"] = adverse
    reasons = []
    if not completion["ok"]:
        reasons.append("not every scheduled game completed with a consistent margin")
    if not integrity["ok"]:
        reasons.append("integrity failure")
    if not systemic["ok"]:
        reasons.append("systemic failure: " + ", ".join(systemic["failures"]))
    if adverse:
        reasons.append("adverse safety signal beyond the registered threshold")
    if phase == "A" and not result["primary"]["supported"]:
        reasons.append("the primary interval's lower limit is not above 0" if testable else "primary not tested")
    following = PHASE_ORDER[PHASE_ORDER.index(phase) + 1] if phase != PHASE_ORDER[-1] else None
    decision = "STOP" if reasons else ("CONTINUE" if following else "COMPLETE")
    result["gate"] = {"decision": decision, "reasons": reasons, "permits": following if decision == "CONTINUE" else None}
    return result


def secondary_consistency(phase_results: Mapping[str, Mapping[str, Any]]) -> Optional[Dict[str, Any]]:
    """Descriptive count over the secondary configurations reached (B: 6 against the inert control, C: 2 head to
    head seat averages): point estimate above 0, interval above 0, interval below 0. No formal claim."""
    rows = []
    for key, a in (phase_results.get("B", {}).get("against_inert") or {}).items():
        rows.append((f"B {key}", a))
    for scenario, a in (phase_results.get("C", {}).get("head_to_head") or {}).items():
        rows.append((f"C {scenario} seat average", a["seat_average"]))
    rows = [(k, a) for k, a in rows if a.get("estimable")]
    if not rows:
        return None
    return {"configurations": len(rows), "estimate_above_0": sum(1 for _, a in rows if a["estimate"] > 0),
            "interval_above_0": sum(1 for _, a in rows if a["ci_low"] > 0),
            "interval_below_0": sum(1 for _, a in rows if a["ci_high"] < 0),
            "rows": {k: [a["estimate"], a["ci_low"], a["ci_high"]] for k, a in rows}}


def disposition(phase_results: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """The registered research disposition from the phases that ran (``phase_results`` in phase order)."""
    a = phase_results.get("A")
    if a is None:
        raise ValueError("phase A has not been analysed")
    primary = a["primary"]
    primary_state = ("SUPPORTED" if primary["supported"] else "NOT_SUPPORTED" if primary["tested"]
                     else "NOT_TESTED")
    safety = {}
    for phase in PHASE_ORDER:
        r = phase_results.get(phase)
        if r is None:
            safety[phase] = "NOT_REACHED"
        elif not (r["completion"]["ok"] and r["integrity"]["ok"] and r["systemic"]["ok"]):
            safety[phase] = "SYSTEMIC_FAILURE"
        elif r["adverse_signals"]:
            safety[phase] = "ADVERSE_SIGNAL"
        else:
            safety[phase] = "CLEAN"
    flagged = {p: r["flags"] for p, r in phase_results.items() if any(r["flags"].values())}
    reached = [p for p in PHASE_ORDER if p in phase_results]
    if primary_state == "NOT_TESTED":
        label = "INCONCLUSIVE_PROTOCOL_INCOMPLETE"
    elif primary_state == "NOT_SUPPORTED":
        label = "PRIMARY_NOT_SUPPORTED"
    elif any(safety[p] in ("SYSTEMIC_FAILURE", "ADVERSE_SIGNAL") for p in reached):
        label = "PRIMARY_SUPPORTED_NEEDS_REVISION"
    else:
        label = "PRIMARY_SUPPORTED"
    return {"label": label, "primary": primary_state, "safety": safety, "flags": flagged,
            "generality": secondary_consistency(phase_results) or "NOT_REACHED",
            "phases_reached": reached, "eligible_for_promotion": False,
            "note": ("a supported primary result holds for scenario 2130511121 head to head against baseline-v2 only; "
                     "generality, mechanism and safety beyond the registered gates are descriptive; no baseline is "
                     "promoted by this study")}
