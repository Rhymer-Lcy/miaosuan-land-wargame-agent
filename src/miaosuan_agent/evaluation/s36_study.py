"""A registered study's disposition derived from its games, never from stored gate files (Sprint 36, section 4).

Sprint 35's report handed its disposition function only the batch gates stored on disk; a structural stop inside a
batch stores no gate, so the report printed ``INCONCLUSIVE`` for a study that had stopped invalid. The defect was that
two code paths decided whether the study had stopped: the runner (game by game) and the report (from files). Here one
function, :func:`derive`, walks the registered schedule over the games actually recorded and applies the study's own
versioned rules (:class:`Rules`) at exactly the points the runner applies them:

* after every recorded game, ``game_stop`` (structural failures, agent failures, game-level harm);
* after the last game of a batch, ``batch_gate`` (batch-level harm, futility, the end of the schedule).

The first stop ends the walk. Its kind decides the disposition (``Rules.stop_dispositions``). A recorded game after a
stop, a gap in the schedule (a later position recorded while an earlier one is not), or a recorded position that is not
in the schedule is a protocol violation and makes the study invalid, while the stop itself stays recorded. Without a
stop, a study whose schedule is not complete is ``in progress`` and the report says so: it never claims a complete
experiment; a complete schedule is judged by ``final``. Every position gets a status: ``played`` (before the stop or with
no stop), ``stopped here`` (the game whose facts or batch closed the study), ``not played (after the stop)``, ``not
played (pending)`` or ``played after the stop`` (protocol violation).

The runner calls :func:`derive` before each game (the next position must be the next pending one) and after it (to
decide whether the study continues), so the run-time decision and the report are the same function on the same
records. :func:`restate` is an independent second reading used by the report generator and the tests; the report is
refused when the two disagree.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

SCHEMA = "miaosuan-s36-study-derivation/1"
PLAYED, STOPPED_HERE, AFTER_STOP, PENDING, VIOLATION = (
    "played", "stopped here", "not played (after the stop)", "not played (pending)", "played after the stop")
IN_PROGRESS = "in progress"
STOP_KINDS = ("protocol", "structural", "agent", "harm", "futility", "complete")


@dataclass(frozen=True)
class Stop:
    kind: str                     # one of STOP_KINDS
    position: int                 # the position whose game (or whose batch's last game) closed the study
    at: str                       # "game" or "batch"
    batch: str
    findings: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "position": self.position, "at": self.at, "batch": self.batch,
                "findings": list(self.findings)}


GameStop = Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], Optional[Tuple[str, Sequence[str]]]]
BatchGate = Callable[[str, Sequence[Mapping[str, Any]]], Optional[Tuple[str, Sequence[str]]]]
Final = Callable[[Sequence[Mapping[str, Any]]], Mapping[str, Any]]


@dataclass(frozen=True)
class Rules:
    """A study's registered rules. ``batches`` maps each batch name, in schedule order, to its positions (ascending,
    contiguous over the whole schedule). ``game_stop(facts, history)`` and ``batch_gate(batch, history)`` return ``None``
    or ``(kind, findings)``; ``history`` holds the facts of every game so far including the current one. ``final``
    judges a complete schedule without a stop. ``stop_dispositions`` names the disposition of each stop kind."""

    rules_id: str
    batches: Tuple[Tuple[str, Tuple[int, ...]], ...]
    game_stop: GameStop
    batch_gate: BatchGate
    final: Final
    stop_dispositions: Mapping[str, str]
    not_started: str
    in_progress: str
    sources: Tuple[Callable[..., Any], ...] = field(default=())

    @property
    def positions(self) -> Tuple[int, ...]:
        return tuple(p for _, ps in self.batches for p in ps)

    def batch_of(self, position: int) -> str:
        return next(b for b, ps in self.batches if position in ps)

    def last_of_batch(self, position: int) -> bool:
        ps = dict(self.batches)[self.batch_of(position)]
        return position == ps[-1]

    def digest(self) -> str:
        """SHA-256 over the source text of the rule functions (the versioned rules the runner and report share)."""
        parts = [self.rules_id]
        for fn in (self.game_stop, self.batch_gate, self.final) + tuple(self.sources):
            try:
                parts.append(inspect.getsource(fn))
            except (OSError, TypeError):
                parts.append(getattr(fn, "__qualname__", repr(fn)))
        return hashlib.sha256("\n".join(parts).replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _check_rules(rules: Rules) -> None:
    positions = rules.positions
    if list(positions) != list(range(1, len(positions) + 1)):
        raise ValueError(f"{rules.rules_id}: positions must be 1..n in batch order, got {positions}")
    for kind in STOP_KINDS:
        if kind not in rules.stop_dispositions:
            raise ValueError(f"{rules.rules_id}: no disposition for stop kind {kind}")


def derive(rules: Rules, played: Mapping[int, Mapping[str, Any]], authorized: bool = True) -> Dict[str, Any]:
    """The study's state and disposition from the recorded games ``played`` (position -> facts)."""
    _check_rules(rules)
    schedule = rules.positions
    recorded = sorted(int(p) for p in played)
    status: Dict[int, str] = {}
    problems: List[str] = []
    unknown = [p for p in recorded if p not in schedule]
    if unknown:
        problems.append(f"recorded positions not in the schedule: {unknown}")
    history: List[Mapping[str, Any]] = []
    stop: Optional[Stop] = None
    walked = 0
    for position in schedule:
        if position not in played:
            break
        walked = position
        facts = played[position]
        history.append(facts)
        status[position] = PLAYED
        batch = rules.batch_of(position)
        found = rules.game_stop(facts, tuple(history))
        if found is not None:
            stop = Stop(found[0], position, "game", batch, tuple(found[1]))
            status[position] = STOPPED_HERE
            break
        if rules.last_of_batch(position):
            found = rules.batch_gate(batch, tuple(history))
            if found is not None:
                stop = Stop(found[0], position, "batch", batch, tuple(found[1]))
                status[position] = PLAYED if found[0] == "complete" else STOPPED_HERE
                break
    for position in schedule:
        if position in status:
            continue
        if position in played:
            status[position] = VIOLATION
            if stop is not None:
                problems.append(f"position {position} was played after the study stopped at {stop.position}")
            else:
                problems.append(f"position {position} was played while position {walked + 1} was not")
        else:
            status[position] = AFTER_STOP if stop is not None else PENDING
    complete = stop is None and walked == len(schedule)
    if stop is not None and stop.kind == "complete":
        complete = True
    if not authorized and not recorded:
        disposition = {"disposition": rules.not_started, "why": "no session budget was authorized"}
    elif problems:
        disposition = {"disposition": rules.stop_dispositions["protocol"], "why": "; ".join(problems)}
    elif stop is not None and stop.kind != "complete":
        disposition = {"disposition": rules.stop_dispositions[stop.kind],
                       "why": f"{stop.kind} stop at position {stop.position} ({stop.at} {stop.batch})"}
    elif complete:
        disposition = dict(rules.final(tuple(history)))
    elif not recorded:
        disposition = {"disposition": rules.not_started, "why": "no game recorded"}
    else:
        disposition = {"disposition": rules.in_progress,
                       "why": f"{len(history)} of {len(schedule)} games recorded, no stop; the schedule is not complete"}
    next_position = None
    if stop is None and not problems and walked < len(schedule):
        next_position = walked + 1
    return {
        "schema": SCHEMA, "rules": rules.rules_id, "rules_digest": rules.digest(),
        "registered_games": len(schedule), "recorded_games": len(recorded), "walked_games": len(history),
        "complete": complete, "stop": stop.to_dict() if stop else None, "protocol_problems": problems,
        "next_position": next_position,
        "positions": {str(p): status[p] for p in schedule},
        "disposition": disposition,
    }


def restate(rules: Rules, played: Mapping[int, Mapping[str, Any]], authorized: bool = True) -> Dict[str, Any]:
    """A second reading of the same rules, written independently of :func:`derive`: every game's verdict first, then
    the first stop, then the protocol checks. Returns the fields the report must agree on."""
    schedule = list(rules.positions)
    keys = sorted(int(p) for p in played)
    prefix = []
    for p in schedule:
        if p in played:
            prefix.append(p)
        else:
            break
    verdicts: List[Tuple[int, str, Optional[Tuple[str, Sequence[str]]]]] = []
    for i, p in enumerate(prefix):
        history = [played[q] for q in prefix[:i + 1]]
        verdicts.append((p, "game", rules.game_stop(played[p], tuple(history))))
        batch = rules.batch_of(p)
        if p == dict(rules.batches)[batch][-1]:
            verdicts.append((p, "batch", rules.batch_gate(batch, tuple(history))))
    first = next(((p, at, v) for p, at, v in verdicts if v is not None), None)
    stop_position = first[0] if first else None
    beyond = [p for p in keys if stop_position is not None and p > stop_position]
    gaps = [p for p in keys if p not in prefix]
    foreign = [p for p in keys if p not in schedule]
    violation = bool(beyond or gaps or foreign)
    if not authorized and not keys:
        name = rules.not_started
    elif violation:
        name = rules.stop_dispositions["protocol"]
    elif first is not None and first[2][0] != "complete":
        name = rules.stop_dispositions[first[2][0]]
    elif first is not None or len(prefix) == len(schedule):
        name = rules.final(tuple(played[p] for p in prefix))["disposition"]
    elif not keys:
        name = rules.not_started
    else:
        name = rules.in_progress
    return {"disposition": name, "stop_position": stop_position,
            "stop_kind": first[2][0] if first else None, "violation": violation,
            "complete": (first is None and len(prefix) == len(schedule)) or bool(first and first[2][0] == "complete")}


def agree(derived: Mapping[str, Any], restated: Mapping[str, Any]) -> List[str]:
    """Differences between the two readings (empty when they agree)."""
    out = []
    if derived["disposition"]["disposition"] != restated["disposition"]:
        out.append(f"disposition {derived['disposition']['disposition']} vs {restated['disposition']}")
    stop = derived["stop"] or {}
    if stop.get("position") != restated["stop_position"] and not derived["protocol_problems"]:
        out.append(f"stop position {stop.get('position')} vs {restated['stop_position']}")
    if stop.get("kind") != restated["stop_kind"] and not derived["protocol_problems"]:
        out.append(f"stop kind {stop.get('kind')} vs {restated['stop_kind']}")
    if bool(derived["protocol_problems"]) != restated["violation"]:
        out.append("protocol violation readings differ")
    if derived["complete"] != restated["complete"]:
        out.append(f"complete {derived['complete']} vs {restated['complete']}")
    return out


def report(rules: Rules, played: Mapping[int, Mapping[str, Any]], authorized: bool = True) -> Dict[str, Any]:
    """:func:`derive`, refused unless :func:`restate` agrees."""
    derived = derive(rules, played, authorized)
    differences = agree(derived, restate(rules, played, authorized))
    if differences:
        raise RuntimeError(f"{rules.rules_id}: the two readings of the study disagree: {differences}")
    return derived


def check_stored(derived: Mapping[str, Any], stored: Mapping[str, Any]) -> List[str]:
    """Problems of a stored report against a fresh derivation: a stored disposition, stop or completeness that the
    recorded games do not reproduce (for example a stopped batch reported as inconclusive)."""
    out = []
    for key in ("disposition", "stop", "complete", "positions", "rules_digest"):
        if stored.get(key) != derived.get(key):
            out.append(f"stored {key} does not match the derivation")
    return out


__all__ = ["Rules", "Stop", "derive", "restate", "agree", "report", "check_stored", "SCHEMA"]
