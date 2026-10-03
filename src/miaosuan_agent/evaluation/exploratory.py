"""The EXPLORATORY track: lightweight, versioned run cards for small engine batches (``docs/EXPLORATORY_TRACK.md``).

A run card registers one batch of exploratory games before its first game: the candidate's identity (policy source
digest over ``baseline-v2``'s frozen sources plus the candidate's modules), the specific tactical mechanism, the
controls, every game's configuration, the batch's session budget and the sprint's session cap, the essential safety
checks and the intended observations. It carries no statistical analysis plan, needs no public issue and no owner
approval per game, and can never promote a baseline: ``eligible_for_promotion`` is always false, and a later claim
of improvement needs the CONFIRMATORY track's full registration.

Engine safeguards are unchanged: every game runs through ``scripts/run_evaluation.sh`` (``--plan explore``) with the
persistent installation, the session ledger and the policy-source checks before the first game, by every game and
after the last game. On top of them, a card's games are refused when the sprint's ledger-counted session cap would
be exceeded (:func:`budget_problem`).

The capture (:class:`ExploreCapture`) is a read-only observer that writes compact facts per game beside the record:
indirect-fire orders and their engine feedback, every indirect-fire point and indirect-fire judgement in the
all-seeing view, artillery state changes, own ground units waiting in front of a full hex, objective commitments, and
blood totals. It never changes the game (``evaluation.game.play``).
"""

from __future__ import annotations

import collections
import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..decision import INERT_ID
from . import manifest as mf
from .execution import RUNTIMES

SCHEMA = "miaosuan-exploratory-run-card/1"
TRACK = "EXPLORATORY"
CAPTURE_SCHEMA = "miaosuan-exploratory-capture/1"
#: Ledger accounting of the sprint that introduced the track: sessions after this closed session count toward the cap.
LEDGER_BASE_SESSION = 2464
SPRINT_SESSION_CAP = 24
INDIRECT = 8
GROUND = (1, 2)
SNAPSHOT_EVERY = 50


def build(card_id: str, texts: Mapping[str, Any], shoot_manifest: Mapping[str, Any], shoot_manifest_sha256: str,
          policies: Sequence[Mapping[str, Any]], candidate: str, games: Sequence[Mapping[str, Any]],
          runtime: str, workers: int, budget: Mapping[str, int]) -> Dict[str, Any]:
    """A run card. ``policies``: {id, label, policy_source {sha256, files, sources}}; ``games``: {game_id,
    scenario_id, condition, red, blue}; ``budget``: {batch_sessions, ledger_base_session, sprint_session_cap}."""
    used = sorted({g["scenario_id"] for g in games})
    scenarios = [dict(s) for s in shoot_manifest["scenarios"] if s["scenario_id"] in used]
    if len(scenarios) != len(used):
        raise ValueError("a game names a scenario outside the frozen set")
    known = {p["id"] for p in policies} | {INERT_ID}
    if any(g["red"] not in known or g["blue"] not in known for g in games):
        raise ValueError("a game names an unregistered policy")
    if len({g["game_id"] for g in games}) != len(games):
        raise ValueError("game ids repeat")
    if int(budget["batch_sessions"]) != len(games):
        raise ValueError("the batch budget must equal the number of games")
    return {
        "schema": SCHEMA, "card_id": card_id, "evaluation_id": card_id, "track": TRACK, "purpose": "exploratory",
        "eligible_for_promotion": False, **dict(texts), "candidate": candidate,
        "policies": {p["id"]: {"label": p["label"], "policy_source": dict(p["policy_source"])} for p in policies},
        "execution": {"workers": int(workers), "runtime": runtime},
        "runtime_environment": dict(RUNTIMES[runtime]),
        "scenarios": scenarios, "players": [dict(p) for p in shoot_manifest["players"]],
        "randomness": dict(shoot_manifest["randomness"]), "caps": dict(shoot_manifest["caps"]),
        "inputs": {"shoot_manifest_sha256": shoot_manifest_sha256},
        "budget": {k: int(v) for k, v in sorted(budget.items())},
        "games": [{"game_id": g["game_id"], "scenario_id": g["scenario_id"], "condition": g["condition"],
                   "red": g["red"], "blue": g["blue"], "position": k} for k, g in enumerate(games, start=1)],
    }


def digest(card: Mapping[str, Any]) -> str:
    return mf.digest(card)


def is_card(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(card: Mapping[str, Any]) -> List[mf.GameSpec]:
    scenarios = {s["scenario_id"]: s for s in card["scenarios"]}
    return [mf.GameSpec(game_id=g["game_id"], scenario_id=g["scenario_id"], map_id=scenarios[g["scenario_id"]]["map_id"],
                        condition=g["condition"], red=g["red"], blue=g["blue"], repetition=1,
                        max_time=int(scenarios[g["scenario_id"]]["max_time"]))
            for g in card["games"]]


def game_policies(spec: mf.GameSpec) -> List[str]:
    return sorted({spec.red, spec.blue} - {INERT_ID})


# ------------------------------------------------------------------------------------------------
# Session budget


def sessions_after(ledger: Path, base: int) -> int:
    """The number of sessions opened after ``base`` according to the append-only ledger."""
    count = 0
    with open(ledger, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("event") == "session-open" and int(record["session"]) > base:
                count += 1
    return count


def budget_problem(card: Mapping[str, Any], ledger: Path, planned: int) -> Optional[str]:
    """Why ``planned`` more sessions would break the card's sprint cap, or None."""
    budget = card["budget"]
    if not Path(ledger).is_file():
        return f"no session ledger at {ledger}"
    used = sessions_after(ledger, budget["ledger_base_session"])
    if used + planned > budget["sprint_session_cap"]:
        return (f"{used} sessions already opened after session {budget['ledger_base_session']}; {planned} more would "
                f"exceed the sprint cap of {budget['sprint_session_cap']}")
    if planned > budget["batch_sessions"]:
        return f"{planned} sessions exceed the card's batch budget of {budget['batch_sessions']}"
    return None


# ------------------------------------------------------------------------------------------------
# Capture


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (int, float, str, bool)) or value is None:
        return value
    return repr(value)


def _is_indirect_judgement(entry: Mapping[str, Any]) -> bool:
    """An indirect-fire judgement: the documented record carries ``align_status`` and the type text 间瞄射击."""
    return "align_status" in entry or "间瞄" in str(entry.get("type", ""))


class ExploreCapture:
    """Read-only per-game facts for the exploratory mechanisms (see the module docstring)."""

    def __init__(self, policies: Sequence[str], clock: Any = time.perf_counter) -> None:
        self.policies = tuple(policies)
        self.clock = clock
        self.seconds = 0.0
        self.orders: List[Dict[str, Any]] = []
        self.feedback: List[Dict[str, Any]] = []
        self.points: List[Dict[str, Any]] = []
        self.open_points: Dict[str, Dict[str, Any]] = {}
        self.judgements: List[Dict[str, Any]] = []
        self.artillery: Dict[str, Dict[str, Any]] = {}
        self.artillery_changes: List[Dict[str, Any]] = []
        self.waiting: Dict[int, List[int]] = {0: [], 1: []}
        self.commitment_max: Dict[int, List[int]] = {0: [], 1: []}
        self.snapshots: List[Dict[str, Any]] = []
        self.addon_changes: collections.Counter = collections.Counter()
        self.addon_distances: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        self.addon_skips: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        self.addon_errors: List[Dict[str, Any]] = []
        self.steps = 0

    def setup(self, view: Any, players: Sequence[Mapping[str, Any]], policies: Mapping[int, str]) -> None:
        self.factions = {int(f): p for f, p in policies.items()}

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        tick = self.clock()
        self.steps += 1
        g0, g1 = before.global_observation, after.global_observation
        step = g0.time().cur_step
        for decision in decisions:
            trace = decision["trace"]
            name = getattr(trace, "addon_name", "")
            if name:
                for change in getattr(trace, "changes", ()):
                    change = json.loads(change)
                    self.addon_changes[f"{decision['faction']}:{change['kind']}"] += 1
                    if isinstance(change.get("distance"), int):
                        self.addon_distances[str(decision["faction"])][str(change["distance"])] += 1
                for reason, count in getattr(trace, "skipped", ()):
                    self.addon_skips[str(decision["faction"])][reason] += count
                if getattr(trace, "addon_error", None):
                    self.addon_errors.append({"k": index, "faction": decision["faction"], "error": trace.addon_error})
            for action in decision["submitted"]:
                if action.get("type") == INDIRECT:
                    self.orders.append({"k": index, "cur_step": step, "faction": decision["faction"],
                                        "action": _plain(action)})
        for entry in g1.action_feedback() or ():
            message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
            if message.get("type") == INDIRECT:
                self.feedback.append({"k": index, "cur_step": step, "entry": _plain(entry)})
        after_step = g1.time().cur_step
        for point in g1.fields.get("jm_points") or ():
            if not isinstance(point, Mapping):
                continue
            key = f"{point.get('color')}:{point.get('obj_id')}:{point.get('pos')}:{point.get('weapon_id')}"
            episode = self.open_points.get(key)
            if episode is None or after_step - episode["last_step"] > 1:
                episode = {"key": key, "first_step": after_step, "first": _plain(point), "statuses": {}}
                self.points.append(episode)
                self.open_points[key] = episode
            episode["statuses"].setdefault(str(point.get("status")), after_step)
            episode["last_step"], episode["last"] = after_step, _plain(point)
        for entry in g1.fields.get("judge_info") or ():
            if isinstance(entry, Mapping) and _is_indirect_judgement(entry):
                self.judgements.append({"k": index, "cur_step": after_step, "entry": _plain(entry)})
        cities = {c.coord for c in (g1.cities() or ())}
        commitments: Dict[int, collections.Counter] = {0: collections.Counter(), 1: collections.Counter()}
        waiting = {0: 0, 1: 0}
        blood = {0: 0, 1: 0}
        for unit in g1.operators():
            color = unit.color
            if color not in (0, 1):
                continue
            fields = unit.fields
            if isinstance(fields.get("blood"), int):
                blood[color] += fields["blood"]
            if fields.get("type") in GROUND:
                path = unit.move_path or ()
                if path and fields.get("speed") == 0:
                    waiting[color] += 1
                end = path[-1] if path else unit.cur_hex
                if end in cities:
                    commitments[color][end] += 1
            if INDIRECT in (g1.valid_actions().get(unit.obj_id) or {}) or fields.get("sub_type") == 3:
                state = {name: _plain(fields.get(name)) for name in
                         ("weapon_cool_time", "remain_bullet_nums", "weapon_unfold_state", "blood", "keep")}
                state["listed_8"] = INDIRECT in (g1.valid_actions().get(unit.obj_id) or {})
                previous = self.artillery.get(str(unit.obj_id))
                if previous != state:
                    self.artillery_changes.append({"k": index, "cur_step": g1.time().cur_step, "obj_id": unit.obj_id,
                                                   "color": color, "state": state})
                    self.artillery[str(unit.obj_id)] = state
        for color in (0, 1):
            self.waiting[color].append(waiting[color])
            self.commitment_max[color].append(max(commitments[color].values(), default=0))
        if index % SNAPSHOT_EVERY == 0:
            self.snapshots.append({"k": index, "cur_step": g1.time().cur_step, "blood": blood,
                                   "scores": _plain(dict(g1.fields.get("scores") or {})),
                                   "flags": sorted((c.coord, c.flag) for c in (g1.cities() or ()))})
        self.seconds += self.clock() - tick

    def compact(self) -> Dict[str, Any]:
        def series(values: List[int]) -> Dict[str, Any]:
            return {"max": max(values, default=0), "sum": sum(values), "steps_positive": sum(1 for v in values if v > 0)}

        return {"schema": CAPTURE_SCHEMA, "policies": self.policies, "steps": self.steps,
                "addon_changes": dict(sorted(self.addon_changes.items())),
                "addon_distances": {k: dict(sorted(v.items(), key=lambda item: int(item[0])))
                                    for k, v in sorted(self.addon_distances.items())},
                "addon_skips": {k: dict(sorted(v.items())) for k, v in sorted(self.addon_skips.items())},
                "addon_errors": self.addon_errors,
                "indirect_orders": self.orders, "indirect_feedback": self.feedback,
                "indirect_points": self.points,
                "indirect_judgements": self.judgements,
                "artillery_changes": self.artillery_changes,
                "waiting_ground_units": {str(c): series(v) for c, v in self.waiting.items()},
                "max_objective_commitment": {str(c): series(v) for c, v in self.commitment_max.items()},
                "snapshots": self.snapshots}

    def files(self) -> Tuple[bytes, bytes]:
        compact = json.dumps(self.compact(), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        series = json.dumps({"waiting": self.waiting, "commitment_max": self.commitment_max},
                            sort_keys=True).encode("utf-8")
        return compact, gzip.compress(series, mtime=0)

    def summary(self, compact: bytes, series: bytes) -> Dict[str, Any]:
        return {"schema": CAPTURE_SCHEMA, "steps": self.steps, "indirect_orders": len(self.orders),
                "indirect_feedback": len(self.feedback), "indirect_points": len(self.points),
                "indirect_judgements": len(self.judgements), "addon_errors": len(self.addon_errors),
                "observer_seconds": self.seconds, "compact_sha256": hashlib.sha256(compact).hexdigest(),
                "series_sha256": hashlib.sha256(series).hexdigest()}
