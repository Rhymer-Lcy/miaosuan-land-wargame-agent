"""Diagnostic-only PS-1 engine-probe hook ``ps1-probe-hook-1`` (probe P1 of ``docs/PS1_ENGINE_PROBE.md``).

NOT A CANDIDATE. It exists to observe what the engine does with a stop order (action 10) issued to units blocked by
the stacking limit. It is never eligible for a screen, a promotion or the platform.

It composes the frozen deployment-split candidate ``tactic-deployment-split-1`` (reused by import, unchanged) with
one hook that runs after the candidate's own decision in every step:

1. Bookkeeping, every decision: for each own ground unit, the step of its last hex change or order, kept in the
   memory (the stall history of ``docs/PS1_DESIGN.md`` section 4). Time is the observation's ``cur_step``; a hex
   change counts when the unit's hex differs from the previous decision's observation; an order counts at the
   step the seat emits it. A unit seen for the first time has no progress yet (step 0).
2. Trigger, until it first holds: the frozen PS-1B trigger, a non-empty deadlocked set all of whose units are
   stalled (``evaluation/ps1_model.py``: ``deadlocked`` and ``stalled``, ``K`` = 4, threshold 2 hex times + 10).
3. At the first step it holds, and only then:

   * verification from the seat observation, coded separately from the model: every deadlocked unit shows
     ``speed`` 0, lists action 10 and has a next hex holding at least four own ground units;
   * the frozen PS-1B selection with the back-off option (``ps1_model.ps1b`` with ``Recovery(option="back-off")``,
     run on a throwaway model copy of the observed state): the stopped units and their planned back-off paths;
   * one stop ``{"actor", "obj_id", "type": 10}`` per selected unit, each passing :func:`stop_problem`.

   A failed verification, an empty selection (no escape) or a model error ends the probe for the rest of the game
   without any action; the trace records why.
4. After the stops the hook never repeats a stop and never acts on another unit. A stopped unit gets its planned
   back-off move in the first step at which its observation lists action 1 and shows no move path, if that is
   within ``WATCH_STEPS`` steps of the stops and every safety check holds (:func:`backoff_problem`); otherwise it
   is released. Until it is released or its move is emitted, the candidate's own actions for that unit are
   dropped (and recorded). After that every unit is the candidate's.

Only the seat's own observation and the hook's own history enter a decision. Before the trigger the hook emits
nothing and returns the candidate's actions and trace object unchanged, so the decisions and their trace digests are
the candidate's. Afterwards the trace carries the hook's notes (prefix ``ps1-probe:``) in its diagnostics, among
them the canonical JSON of every action the hook emits, written before the engine sees the action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import ContractError, Observation, Origin
from ..boundary.observation import Stage
from ..decision import Memory, StepTrace
from ..decision import gate
from ..decision.context import TacticalContext, build_context
from ..decision.policy import Decision
from ..decision.routing import ROADBLOCKED_MODES, move_mode
from ..decision.trace import failed
from ..evaluation import ps1_model as pm
from .deployment_split import DeploymentSplitAgent, DeploymentSplitPolicy, SplitMemory

PROBE_ID = "ps1-probe-hook-1"
STOP = 10
MOVE = 1
GROUND_TYPES = (1, 2)
#: A stopped unit's planned back-off is emitted only within this many steps of the stops (four documented
#: 75-second transitions); afterwards the unit is released without it.
WATCH_STEPS = 300
NOTE = "ps1-probe: "
RECOVERY_OPTION = "back-off"


@dataclass(frozen=True)
class ProbeState:
    """The hook's own history beyond the stall bookkeeping.

    ``phase``: ``watching`` (trigger not yet seen), ``stopped`` (stops emitted, some unit not yet resolved),
    ``done`` (every stopped unit resolved) or ``ended: <reason>`` (the probe ended without acting).
    ``group``: (unit, hex at the trigger, planned path) for every stopped unit, ascending unit.
    ``status``: (unit, ``stop-emitted`` | ``move-emitted`` | ``released: <reason>``), ascending unit.
    """

    phase: str = "watching"
    trigger_step: Optional[int] = None
    group: Tuple[Tuple[int, int, Tuple[int, ...]], ...] = ()
    status: Tuple[Tuple[int, str], ...] = ()


@dataclass(frozen=True)
class ProbeMemory:
    """The candidate's memory, untouched, plus the hook's history (all immutable)."""

    inner: Memory = field(default_factory=SplitMemory)
    hexes: Tuple[Tuple[int, int], ...] = ()  # unit -> its hex at the previous decision
    last: Tuple[Tuple[int, int], ...] = ()  # unit -> step of its last hex change or order
    probe: ProbeState = field(default_factory=ProbeState)

    @property
    def deployment_sent(self) -> bool:
        return self.inner.deployment_sent


def canonical(action: Mapping[str, Any]) -> str:
    return json.dumps(dict(action), sort_keys=True, separators=(",", ":"))


def own_ground(observation: Observation, seat: int) -> Dict[int, Any]:
    """The seat's own ground units on the map: listed for the seat, type 1 or 2, not on board."""
    listed = set(observation.seat(seat).operators)
    return {op.obj_id: op for op in observation.operators()
            if op.obj_id in listed and op.fields.get("type") in GROUND_TYPES and op.fields.get("on_board") in (0, None, False)}


def model_units(units: Mapping[int, Any], last: Mapping[int, int]) -> List[pm.Unit]:
    out = []
    for uid, op in sorted(units.items()):
        mode = move_mode(op.unit_type, op.move_state)
        if mode is None:
            continue
        out.append(pm.Unit(uid=uid, hex=op.cur_hex, speed=float(op.fields["basic_speed"]), mode=int(mode),
                           path=tuple(op.move_path or ()), last_progress=last.get(uid, 0)))
    return out


def trigger_holds(units: Sequence[pm.Unit], now: int, edges: Mapping[int, pm.Edges]) -> Tuple[bool, frozenset]:
    """The frozen PS-1B trigger: a non-empty deadlocked set, every unit of it stalled."""
    dead = pm.deadlocked(units)
    return bool(dead) and all(pm.stalled(u, now, edges) for u in units if u.uid in dead), dead


def verification_problem(units: Mapping[int, Any], dead: frozenset, listed: Mapping[int, Mapping[int, Any]]) -> Optional[str]:
    """Independent check of the trigger from the observation (no model function): every deadlocked unit at speed 0,
    listing action 10, with a next hex holding at least four own ground units."""
    counts: Dict[int, int] = {}
    for op in units.values():
        counts[op.cur_hex] = counts.get(op.cur_hex, 0) + 1
    for uid in sorted(dead):
        op = units.get(uid)
        if op is None:
            return f"deadlocked unit {uid} is not an own ground unit in the observation"
        if op.fields.get("speed") != 0:
            return f"deadlocked unit {uid} shows speed {op.fields.get('speed')!r}, not 0"
        if STOP not in (listed.get(uid) or {}):
            return f"deadlocked unit {uid} does not list action {STOP}"
        path = op.move_path or ()
        if not path or counts.get(path[0], 0) < pm.K:
            return f"deadlocked unit {uid} does not face a hex holding {pm.K} own ground units"
    return None


def stop_problem(action: Mapping[str, Any], context: TacticalContext, seen: Sequence[int]) -> Optional[str]:
    """Why a stop must not be emitted, or None (the hook's own check: the project gate does not catalogue 10)."""
    if set(action) != {"actor", "obj_id", "type"} or action.get("type") != STOP:
        return "not a stop action"
    if not all(isinstance(action[k], int) and not isinstance(action[k], bool) for k in ("actor", "obj_id")):
        return "fields must be ints"
    if action["actor"] != context.seat:
        return "actor is not this seat"
    if context.stage != Stage.PLAY:
        return "not the play stage"
    unit = context.unit(action["obj_id"])
    if unit is None:
        return "obj_id is not a controllable unit"
    if STOP not in unit.actions:
        return "action 10 not listed for the unit"
    if not unit.move_path:
        return "the unit has no move to stop"
    if action["obj_id"] in seen:
        return "second action for the same unit in one step"
    return None


def backoff_problem(uid: int, start: int, path: Tuple[int, ...], units: Mapping[int, Any],
                    context: TacticalContext, router: Any, pending: Mapping[int, int]) -> Optional[str]:
    """Why a planned back-off must not be emitted now, or None.

    s1 the unit stands in the hex it stood in at the trigger; s2 no hex of the path holds four own ground units;
    s3 the destination's own ground units plus the stopped units already sent there and not yet arrived stay below
    four; s4 the project gate accepts the move (listed, not moving, traversable neighbours, no roadblock for
    vehicles).
    """
    op = units.get(uid)
    if op is None or op.cur_hex != start:
        return "s1: the unit is not in its hex of the trigger"
    counts: Dict[int, int] = {}
    for other in units.values():
        counts[other.cur_hex] = counts.get(other.cur_hex, 0) + 1
    if any(counts.get(h, 0) >= pm.K for h in path):
        return "s2: a hex of the planned path holds four own ground units"
    if counts.get(path[-1], 0) + pending.get(path[-1], 0) >= pm.K:
        return "s3: the destination would hold four own ground units"
    action = {"actor": context.seat, "obj_id": uid, "type": MOVE, "move_path": list(path)}
    result = gate.check([action], context, router)
    if not result.accepted:
        return "s4: the project gate rejects the move: " + result.rejected[0].reason
    return None


class ProbePolicy:
    """The frozen split candidate's decision, then the hook."""

    identity = PROBE_ID

    def __init__(self, costs: Any) -> None:
        self.inner = DeploymentSplitPolicy(costs)
        self.edges = {int(m): costs.edges[m] for m in range(len(costs.edges))} if costs is not None else None

    def decide(self, observation: Observation, seat: int, faction: int, memory: ProbeMemory) -> Decision:
        inner = self.inner.decide(observation, seat, faction, memory.inner)
        now = observation.time().cur_step
        units = own_ground(observation, seat)
        hexes, last = dict(memory.hexes), dict(memory.last)
        for uid, op in units.items():
            if uid in hexes and hexes[uid] != op.cur_hex:
                last[uid] = now
        state = memory.probe
        actions = list(inner.actions)
        notes: List[str] = []
        if observation.time().stage == Stage.PLAY and self.edges is not None:
            if state.phase == "watching":
                state, actions, notes = self._watch(observation, seat, faction, units, last, now, actions)
            elif state.phase == "stopped":
                state, actions, notes = self._follow(observation, seat, faction, units, now, actions, state)
        for action in actions:
            if action.get("type") == MOVE:
                last[action["obj_id"]] = now
        successor = ProbeMemory(inner=inner.memory, hexes=tuple(sorted((u, op.cur_hex) for u, op in units.items())),
                                last=tuple(sorted(last.items())), probe=state)
        trace = inner.trace
        if notes:
            trace = replace(trace, diagnostics=tuple(trace.diagnostics) + tuple(NOTE + n for n in notes),
                            emitted=tuple((int(a["type"]), a.get("obj_id")) for a in actions))
        return Decision(tuple(actions), trace, successor)

    def _watch(self, observation: Observation, seat: int, faction: int, units: Mapping[int, Any],
               last: Mapping[int, int], now: int, actions: List[Mapping[str, Any]]):
        model = model_units(units, last)
        holds, dead = trigger_holds(model, now, self.edges)
        if not holds:
            return ProbeState(), actions, []
        notes = [f"trigger at step {now}: {len(dead)} deadlocked units, cycles {pm.cycles(model)}"]
        listed = observation.valid_actions()
        problem = verification_problem(units, dead, listed)
        if problem is not None:
            notes.append(f"ended: trigger not verified: {problem}")
            return ProbeState(phase="ended: trigger not verified", trigger_step=now), actions, notes
        roadblocks = frozenset(observation.roadblocks() or ())
        sim = pm.Simulation(units=list(model), edges_by_mode=self.edges, step=now,
                            objectives={c.coord: c.flag for c in (observation.cities() or ())}, faction=faction,
                            blocked_by_mode={int(m): roadblocks for m in ROADBLOCKED_MODES})
        recovery = pm.Recovery(option=RECOVERY_OPTION)
        try:
            pm.ps1b(recovery)(sim)
        except pm.ModelError as exc:
            notes.append(f"ended: model error in the selection: {exc}")
            return ProbeState(phase="ended: model error", trigger_step=now), actions, notes
        stopped = [e.uid for e in sim.events if e.kind == "stop"]
        if not stopped or sorted(stopped) != sorted(recovery.pending):
            notes.append(f"ended: no escape plan (witnesses {len(recovery.witnesses)})")
            return ProbeState(phase="ended: no escape plan", trigger_step=now), actions, notes
        context = build_context(observation, seat, faction)
        group = tuple((uid, units[uid].cur_hex, tuple(recovery.pending[uid])) for uid in sorted(stopped))
        kept, dropped = self._drop(actions, {uid for uid, _, _ in group})
        notes += [f"dropped the candidate's action {canonical(a)}" for a in dropped]
        stops, seen = [], [a.get("obj_id") for a in kept]
        for uid, start, path in group:
            stop = {"actor": seat, "obj_id": uid, "type": STOP}
            problem = stop_problem(stop, context, seen)
            if problem is not None:
                notes.append(f"ended: stop for unit {uid} fails its check: {problem}")
                return ProbeState(phase="ended: stop check failed", trigger_step=now), actions, notes
            stops.append(stop)
            seen.append(uid)
            notes.append(f"selected unit {uid} at hex {start}, planned back-off {list(path)}")
        notes += [f"emit {canonical(s)}" for s in stops]
        status = tuple((uid, "stop-emitted") for uid, _, _ in group)
        return ProbeState(phase="stopped", trigger_step=now, group=group, status=status), kept + stops, notes

    def _follow(self, observation: Observation, seat: int, faction: int, units: Mapping[int, Any], now: int,
                actions: List[Mapping[str, Any]], state: ProbeState):
        status = dict(state.status)
        open_units = {uid for uid, s in status.items() if s == "stop-emitted"}
        listed = observation.valid_actions()
        context = build_context(observation, seat, faction)
        notes: List[str] = []
        moves: List[Mapping[str, Any]] = []
        pending: Dict[int, int] = {}
        for uid, _, path in state.group:
            if status[uid] == "move-emitted" and uid in units and units[uid].cur_hex != path[-1]:
                pending[path[-1]] = pending.get(path[-1], 0) + 1
        for uid, start, path in state.group:
            if uid not in open_units:
                continue
            op = units.get(uid)
            eligible = op is not None and MOVE in (listed.get(uid) or {}) and not (op.move_path or ())
            if op is None:
                status[uid] = "released: the unit is not an own ground unit in the observation"
            elif now - state.trigger_step > WATCH_STEPS:
                status[uid] = f"released: not eligible within {WATCH_STEPS} steps of the stop"
            elif eligible:
                problem = backoff_problem(uid, start, path, units, context, self.inner.router, pending)
                if problem is None:
                    move = {"actor": seat, "obj_id": uid, "type": MOVE, "move_path": list(path)}
                    moves.append(move)
                    pending[path[-1]] = pending.get(path[-1], 0) + 1
                    status[uid] = "move-emitted"
                    notes.append(f"emit {canonical(move)}")
                else:
                    status[uid] = f"released: {problem}"
            if status[uid] != "stop-emitted":
                notes.append(f"unit {uid}: {status[uid]}")
        still = {uid for uid, s in status.items() if s == "stop-emitted"}
        kept, dropped = self._drop(actions, still | {m["obj_id"] for m in moves})
        notes += [f"dropped the candidate's action {canonical(a)}" for a in dropped]
        phase = "stopped" if still else "done"
        if phase == "done":
            notes.append("done: every stopped unit is resolved")
        new_state = replace(state, phase=phase, status=tuple(sorted(status.items())))
        return new_state, kept + moves, notes

    @staticmethod
    def _drop(actions: Sequence[Mapping[str, Any]], units: set) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
        kept = [a for a in actions if a.get("obj_id") not in units]
        return kept, [a for a in actions if a.get("obj_id") in units]


class ProbeAgent(DeploymentSplitAgent):
    """The platform agent interface around :class:`ProbePolicy` (diagnostic only)."""

    def __init__(self, origin: Origin = Origin.ENGINE, strict: bool = False) -> None:
        super().__init__(origin, strict)
        self.policy_id = PROBE_ID

    def setup(self, setup_info: Mapping[str, Any]) -> None:
        super().setup(setup_info)
        self.policy = ProbePolicy(self.costs)
        self.memory = ProbeMemory()

    def replay(self, observation: Any, memory: ProbeMemory) -> StepTrace:
        if self.policy is None or self.seat is None or self.faction is None:
            raise RuntimeError("replay() called before setup()")
        fresh = ProbePolicy(self.costs)
        try:
            return fresh.decide(Observation.from_raw(observation, self.origin), self.seat, self.faction, memory).trace
        except ContractError as exc:
            if self.strict:
                raise
            return failed(fresh.identity, self.seat, self.faction, exc)

    def reset(self) -> None:
        super().reset()
        self.memory = ProbeMemory()
