"""Analysis library of the T7 mechanism probe ``t7-mechanism-probe-1`` (rules: ``evaluation/t7_probe.py``).

Read-only: it reads a game record, its T7 capture and setup data, and returns verdicts with their evidence. Every rule
it applies is the registered one; the command-line driver is ``scripts/t7_probe_analysis.py``.

Data model. A capture holds, per decision index ``k``, a pickled snapshot of the all-seeing state and of each seat's
observation (``samples``), and a compact per-step log (``steps``: the batch serialised after the step, the
pre-execution copies, the engine's feedback, judge_info records new in the step, trace digests and the candidate's t7
block). :func:`series` reads every snapshot once and keeps, per ``k``, compact unit rows from both channels (the
all-seeing state, and each seat's own observation), the listed enemy ids of each seat and the objectives and scores.
Everything else is computed from those rows and the compact log.
"""

from __future__ import annotations

import collections
import json
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Tuple

from . import effects
from . import t7_probe as tp
from . import t7_visibility as tv
from .canonical import value_digest

CHANGE_STATE, CONCEAL = 6, 4
MOVE, SHOOT, GUIDED = 1, 2, 9
GROUND = (1, 2)
TIMERS = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time", "get_on_remain_time",
          "get_off_remain_time")
SUPPORTED, REFUTED, INCONCLUSIVE, NOT_TESTED = "SUPPORTED", "REFUTED", "INCONCLUSIVE", "NOT TESTED"
PASS, FAIL = "PASS", "FAIL"


class AnalysisRefused(Exception):
    """An integrity condition the protocol makes a refusal: no verdict may be computed."""


def _num(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class U(NamedTuple):
    """One unit at one snapshot, as one channel shows it."""

    obj_id: int
    color: Any
    type: Any
    sub_type: Any
    hex: Any
    move_state: Any
    timers: Tuple[Any, ...]
    stop: Any
    keep: Any
    flag_force_stop: Any
    speed: Any
    blood: Any
    on_board: Any
    launcher: Any
    path: Optional[Tuple[Any, ...]]
    types: Optional[Tuple[int, ...]]  # listed action types (None: no valid_actions entry)
    states: Optional[Tuple[int, ...]]  # listed change-state target states (None: action 6 not listed)
    a1: Any

    @property
    def in_transition(self) -> bool:
        return any((_num(t) or 0) > 0 for t in self.timers)

    @property
    def concealed(self) -> bool:
        return self.move_state == CONCEAL and _num(self.timers[0]) == 0

    @property
    def on_map(self) -> bool:
        return self.on_board in (0, None, False)

    @property
    def launched(self) -> bool:
        return _int(self.launcher) is not None and self.launcher not in (0, -1, self.obj_id)


#: Fields compared between the two channels for an affected unit (I4).
CHANNEL_FIELDS = ("color", "type", "sub_type", "hex", "move_state", "timers", "stop", "keep", "flag_force_stop",
                  "speed", "blood", "on_board", "path", "types", "states")


def _listing(raw: Mapping[str, Any]) -> Dict[int, Mapping[Any, Any]]:
    out: Dict[int, Mapping[Any, Any]] = {}
    for unit_id, actions in (raw.get("valid_actions") or {}).items():
        uid = _int(unit_id)
        if uid is None and isinstance(unit_id, str) and unit_id.lstrip("-").isdigit():
            uid = int(unit_id)
        if uid is not None and isinstance(actions, Mapping):
            out[uid] = actions
    return out


def _types(actions: Optional[Mapping[Any, Any]]) -> Tuple[Optional[Tuple[int, ...]], Optional[Tuple[int, ...]]]:
    if actions is None:
        return None, None
    types, states = [], None
    for key, options in actions.items():
        t = _int(key) if not isinstance(key, str) else (int(key) if key.lstrip("-").isdigit() else None)
        if t is None:
            continue
        types.append(t)
        if t == CHANGE_STATE:
            values = sorted({o.get("target_state") for o in options or () if isinstance(o, Mapping)
                             and _int(o.get("target_state")) is not None})
            states = tuple(values)
    return tuple(sorted(types)), states


def unit_rows(raw: Mapping[str, Any], faction: Optional[int] = None) -> Dict[int, U]:
    """Rows of the units in ``operators`` (of ``faction`` only when given), with their listings in this view."""
    listing = _listing(raw)
    out: Dict[int, U] = {}
    for unit in raw.get("operators") or ():
        if not isinstance(unit, Mapping) or _int(unit.get("obj_id")) is None:
            continue
        if faction is not None and unit.get("color") != faction:
            continue
        uid = unit["obj_id"]
        path = unit.get("move_path")
        types, states = _types(listing.get(uid))
        out[uid] = U(uid, unit.get("color"), unit.get("type"), unit.get("sub_type"), unit.get("cur_hex"),
                     unit.get("move_state"), tuple(unit.get(t) for t in TIMERS), unit.get("stop"), unit.get("keep"),
                     unit.get("flag_force_stop"), unit.get("speed"), unit.get("blood"), unit.get("on_board"),
                     unit.get("launcher"), tuple(path) if isinstance(path, (list, tuple)) else None, types, states,
                     unit.get("A1"))
    return out


@dataclass
class SeatView:
    faction: int
    policy: str
    own: Dict[int, U]
    enemies: FrozenSet[int]
    digest: Optional[str] = None


@dataclass
class Snap:
    k: int
    cur_step: int
    stage: Any
    units: Dict[int, U]
    seats: Dict[int, SeatView]
    flags: Tuple[Tuple[Any, Any], ...]
    scores: Tuple[Tuple[str, Any], ...]
    state_digest: Optional[str] = None


@dataclass
class Game:
    """One recorded game: its record, the compact log and the snapshot windows (unpickled outer level)."""

    game_id: str
    record: Mapping[str, Any]
    compact: Mapping[str, Any]
    windows: Mapping[str, Any]
    seats: Dict[int, Tuple[int, str]] = field(default_factory=dict)  # seat -> (faction, policy)

    def __post_init__(self) -> None:
        if not self.seats:
            for p in self.compact.get("setup", {}).get("players", ()):
                self.seats[p["seat"]] = (p["faction"], p["policy"])
        self.steps = {s["k"]: s for s in self.compact.get("steps", ())}
        self.samples = {s["k"]: s for s in self.windows.get("samples", ())}

    def seats_of(self, policy: str) -> List[int]:
        return sorted(s for s, (_, p) in self.seats.items() if p == policy)

    @property
    def last_k(self) -> int:
        return max(self.steps) if self.steps else -1


def load(work: Path, game_id: str) -> Game:
    record = json.loads((work / "games" / f"{game_id}.json").read_text(encoding="utf-8"))
    compact = json.loads((work / "capture" / f"{game_id}.capture.json").read_text(encoding="utf-8"))
    with (work / "capture" / f"{game_id}.windows.pkl").open("rb") as handle:
        windows = pickle.load(handle)
    return Game(game_id, record, compact, windows)


def snap_of(k: int, cur_step: int, glob: Mapping[str, Any], observations: Mapping[int, Mapping[str, Any]],
            seats: Mapping[int, Tuple[int, str]], digests: bool = False) -> Snap:
    time = glob.get("time") or {}
    views = {}
    for seat, raw in observations.items():
        faction, policy = seats[seat]
        enemies = frozenset(u.get("obj_id") for u in raw.get("operators") or ()
                            if isinstance(u, Mapping) and u.get("color") != faction)
        views[seat] = SeatView(faction, policy, unit_rows(raw, faction), enemies,
                               value_digest(dict(raw)) if digests else None)
    flags = tuple(sorted((c.get("coord"), c.get("flag")) for c in glob.get("cities") or () if isinstance(c, Mapping)))
    scores = tuple(sorted((str(k2), v) for k2, v in (glob.get("scores") or {}).items()))
    return Snap(k, cur_step, time.get("stage"), unit_rows(glob), views, flags, scores,
                value_digest(dict(glob)) if digests else None)


Hook = Callable[[int, Mapping[str, Any], Mapping[int, Mapping[str, Any]], Mapping[int, Any]], None]


def series(game: Game, hook: Optional[Hook] = None, digests_until: int = -1) -> Dict[int, Snap]:
    """Every snapshot of the game as compact rows, in decision order (the final state under key ``last_k + 1``).

    ``hook(k, glob, observations, memories)`` is called with the raw dictionaries of every snapshot (not the final
    state); full canonical digests of the all-seeing state and the seat observations are kept up to ``digests_until``.
    """
    out: Dict[int, Snap] = {}
    for k in sorted(game.samples):
        sample = game.samples[k]
        glob = pickle.loads(sample["global"])
        observations, memories = {}, {}
        for seat, entry in sample["seats"].items():
            observations[int(seat)] = pickle.loads(entry["observation"])
            memories[int(seat)] = pickle.loads(entry["memory"]) if "memory" in entry else None
        seats = {s: game.seats[s] for s in observations}
        out[k] = snap_of(k, sample["cur_step"], glob, observations, seats, digests=k <= digests_until)
        if hook is not None:
            hook(k, glob, observations, memories)
    final = game.windows.get("final")
    if final:
        glob = pickle.loads(final["global"])
        observations = {int(s): pickle.loads(e["observation"]) for s, e in final["seats"].items()}
        out[final["k"]] = snap_of(final["k"], final["cur_step"], glob, observations,
                                  {s: game.seats[s] for s in observations})
    return out


# ----------------------------------------------------------------------------------------------
# Integrity


def integrity_record(game: Game, manifest: Mapping[str, Any], commit: Optional[str]) -> List[str]:
    """I1: problems with the record (empty list when none)."""
    r, problems = game.record, []
    if r.get("status") != "COMPLETED" or not r.get("done"):
        problems.append(f"record status {r.get('status')} done {r.get('done')}")
    harness = r.get("harness") or {}
    for policy, digest in (harness.get("policy_sources") or {}).items():
        if manifest["policies"].get(policy, {}).get("policy_source", {}).get("sha256") != digest:
            problems.append(f"policy source of {policy} is not the registered one")
    pinned = {p for p in (manifest["policies"]) if p in {game.record.get("policies", {}).get("red"),
                                                         game.record.get("policies", {}).get("blue")}}
    if set(harness.get("policy_sources") or {}) != pinned:
        problems.append("the record does not pin every registered policy it played")
    if harness.get("runtime") != manifest["execution"]["runtime"]:
        problems.append(f"runtime {harness.get('runtime')}")
    if (harness.get("capture") or {}) != {"sample_every": tp.SAMPLE_EVERY, "schema": tp.CAPTURE_SCHEMA}:
        problems.append(f"capture settings {harness.get('capture')}")
    if harness.get("dirty"):
        problems.append("harness dirty")
    if commit is not None and harness.get("commit") != commit:
        problems.append(f"harness commit {harness.get('commit')} is not the registration commit")
    if r.get("observer_errors"):
        problems.append(f"observer errors {r.get('observer_errors')[:3]}")
    for seat in r.get("seats") or ():
        if seat.get("replay_mismatches"):
            problems.append(f"replay mismatches for {seat.get('policy')}")
    return problems


def integrity_capture(game: Game) -> List[str]:
    """I2: a snapshot of every seat at every decision from 0 to the last, the compact log complete, the final state."""
    problems = []
    last = game.record.get("steps", 0) - 1
    if sorted(game.steps) != list(range(0, last + 1)):
        problems.append(f"compact log covers {len(game.steps)} of {last + 1} decisions")
    missing = [k for k in range(0, last + 1) if k not in game.samples]
    if missing:
        problems.append(f"no snapshot at {len(missing)} decisions (first {missing[:3]})")
    for k, sample in game.samples.items():
        if set(int(s) for s in sample["seats"]) != set(game.seats):
            problems.append(f"snapshot {k} lacks a seat")
            break
    if not game.windows.get("final"):
        problems.append("no final state")
    if game.compact.get("t7_capture_schema") != tp.CAPTURE_SCHEMA:
        problems.append("not a T7 capture")
    return problems


def fresh_feedback(steps: Mapping[int, Mapping[str, Any]]) -> Dict[int, List[Mapping[str, Any]]]:
    """Per step, the feedback entries not already reported at the previous step while the clock stood still."""
    out: Dict[int, List[Mapping[str, Any]]] = {}
    previous = None
    for k in sorted(steps):
        step = steps[k]
        entries = list(step.get("feedback") or ())
        if previous is not None and step["cur_step"] == previous["cur_step"]:
            pool = collections.Counter(json.dumps(e, sort_keys=True) for e in previous.get("feedback") or ())
            fresh = []
            for entry in entries:
                key = json.dumps(entry, sort_keys=True)
                if pool[key] > 0:
                    pool[key] -= 1
                else:
                    fresh.append(entry)
            entries = fresh
        out[k] = entries
        previous = step
    return out


def matches(entry: Mapping[str, Any], action: Mapping[str, Any]) -> bool:
    """A feedback entry's message is this action: same actor, type, obj_id and the identifying parameters."""
    message = entry.get("message") if isinstance(entry.get("message"), Mapping) else {}
    for key in ("actor", "type", "obj_id"):
        if message.get(key) != action.get(key):
            return False
    for key in ("target_state", "target_obj_id", "weapon_id"):
        if key in action and message.get(key) != action.get(key):
            return False
    if "move_path" in action and list(message.get("move_path") or []) != list(action.get("move_path") or []):
        return False
    return True


class Order(NamedTuple):
    k: int
    cur_step: int
    seat: int
    unit: int
    j: int


def submitted(game: Game, seat: int, k: int) -> List[Mapping[str, Any]]:
    return [s["action"] for s in game.steps[k].get("submitted") or () if s["seat"] == seat]


def serialised(game: Game, seat: int, k: int) -> List[Mapping[str, Any]]:
    return [b["action"] for b in game.steps[k].get("batch") or () if b["seat"] == seat]


def is_order(action: Mapping[str, Any]) -> bool:
    return action.get("type") == CHANGE_STATE and action.get("target_state") == CONCEAL


def orders(game: Game, seat: int) -> List[Order]:
    out = []
    for k in sorted(game.steps):
        for j, action in enumerate(submitted(game, seat, k)):
            if is_order(action):
                out.append(Order(k, game.steps[k]["cur_step"], seat, action["obj_id"], j))
    return out


def three_way(game: Game, seat: int) -> Dict[str, Any]:
    """I3: the candidate's orders by its trace blocks, its pre-execution copies and the record; every seat's copies by
    type against the record's counts. Raises :class:`AnalysisRefused` on any disagreement."""
    blocks, missing = 0, []
    for k in sorted(game.steps):
        block = (game.steps[k].get("t7") or {}).get(str(seat))
        if block is None:
            missing.append(k)
            continue
        blocks += len(block["added"])
    copies = len(orders(game, seat))
    record_seat = next(s for s in game.record["seats"] if s["seat"] == seat)
    recorded = int(record_seat["actions_by_type"].get(str(CHANGE_STATE), 0))
    other6 = sum(1 for k in game.steps for a in submitted(game, seat, k) if a.get("type") == CHANGE_STATE
                 and not is_order(a))
    result = {"trace_blocks": blocks, "pre_execution": copies, "record": recorded, "missing_blocks": len(missing),
              "other_change_state": other6}
    if missing:
        raise AnalysisRefused(f"I3: no t7 trace block at {len(missing)} decisions of seat {seat} (first {missing[:3]})")
    if not blocks == copies == recorded or other6:
        raise AnalysisRefused(f"I3: the candidate's orders disagree: {result}")
    for entry in game.record["seats"]:
        by_type = collections.Counter(str(a.get("type")) for k in game.steps for a in submitted(game, entry["seat"], k))
        if dict(by_type) != {t: c for t, c in entry["actions_by_type"].items() if c}:
            raise AnalysisRefused(f"I3: pre-execution copies of seat {entry['seat']} by type {dict(by_type)} differ from "
                                  f"the record's {entry['actions_by_type']}")
    rewritten = sum(game.steps[k].get("rewritten_in_place", 0) for k in game.steps)
    result["rewritten_in_place"] = rewritten
    return result


def channel_check(snaps: Mapping[int, Snap], seat: int, units: Iterable[int], since: int) -> Dict[str, Any]:
    """I4: the all-seeing state and the seat's own view agree on every field of every given unit from ``since`` on.
    Raises :class:`AnalysisRefused` on a disagreement; returns the counts compared."""
    compared = 0
    for k, snap in snaps.items():
        if k < since or seat not in snap.seats:
            continue
        own = snap.seats[seat].own
        for uid in units:
            a, b = snap.units.get(uid), own.get(uid)
            if (a is None) != (b is None):
                raise AnalysisRefused(f"I4: unit {uid} present in one channel only at decision {k}")
            if a is None:
                continue
            for name in CHANNEL_FIELDS:
                if getattr(a, name) != getattr(b, name):
                    raise AnalysisRefused(f"I4: unit {uid} field {name} differs between channels at decision {k}: "
                                          f"{getattr(a, name)!r} / {getattr(b, name)!r}")
            compared += 1
    return {"unit_snapshots_compared": compared}
