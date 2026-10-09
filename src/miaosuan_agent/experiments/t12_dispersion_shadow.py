"""NON-EXECUTABLE analysis-side shadow of the T12-O1 objective-zone dispersion rule (Sprint 28,
``docs/SPRINT28_T12_O1.md``).

OFFLINE ONLY. Not a policy: there is no agent class, it is not in ``decision.policy.POLICIES``, no run card may name
it, and nothing it returns reaches an engine. It adds to, and filters, an action list that ``baseline-v2`` has
already produced for one seat at one decision, so that the registered dispersion rule is specified exactly, tested,
and replayed on recorded states.

Definitions (registration, sections 5 to 11):

* An **objective** is a ``cities`` entry of the seat's observation with an integer hex; the side **holds** it when its
  flag equals the side's colour. Its **centre** is its hex; its **neighbours** are the hexes at
  ``evaluation.t7_visibility.hex_distance`` 1 inside the map (:func:`neighbours`; the documented order of
  ``Map.get_neighbors`` is not used, only the set).
* An **own ground unit** is a unit of the seat's own ``operators`` of type 1 or 2 (artillery included) with an integer
  hex; passengers are not operators. Own ground units are what the published stacking rule limits to four per hex.
* **Idle**, checked in the order of :data:`IDLE_LEVELS` for an own ground unit on a centre (every level must hold):
  ``A_stationary`` (``speed`` not positive: physically not moving); ``B_no_route`` (empty observed ``move_path``);
  ``C_no_transition`` (the engine's ``stop`` flag not 0, and ``move_to_stop_remain_time`` and
  ``change_state_remain_time`` not positive: no stop or state transition);
  ``D_no_transport_transition`` (``get_on_remain_time`` and ``get_off_remain_time`` not positive);
  ``E_not_suppressed`` (``keep`` false); ``F_no_baseline_move`` (``baseline-v2`` gives the unit no MOVE at this
  decision); ``G_no_baseline_action`` (``baseline-v2`` gives the unit no action of any type at this decision: the
  safety gate admits one action per unit per step, so any action is incompatible with a dispersion MOVE). A missing
  field counts as not positive / not 0 / false, the observed absence of a transition.
* **Trigger** (theoretical tier), per held objective at a play decision (stage 2): at least ``MIN_IDLE`` (2) idle own
  ground units on its centre, none of them under an active hold of this rule, and a **passable** neighbour: a
  neighbour that is a traversable cost-graph neighbour of the centre in at least one ground mode (vehicle, vehicle
  march, infantry) and holds fewer than ``STACK_LIMIT`` (4) own ground units.
* **Legal one-hex MOVE** (unit level), for an idle unit on a centre and a neighbour: action type 1 is listed for the
  unit in this decision's ``valid_actions``; the unit has a documented movement mode
  (``decision.routing.move_mode``); the one-hex path passes the project's safety-gate path check
  (``decision.gate._path_problem``: a traversable neighbour in the unit's mode, never the start hex, never a roadblock
  for vehicle modes); and the neighbour holds fewer than four own ground units.
* **Admissible destination** (the local rule): a legal neighbour that is not an objective hex, holds no visible enemy
  operator, and is not a hex of any own unit's observed ``move_path`` nor of any ``baseline-v2`` MOVE route at this
  decision (so a dispersed unit neither captures, nor enters close combat, nor stands on an own route).

**Batch** (section 10), per triggered objective in increasing hex order, sharing one occupancy count per decision:
the idle centre units are ordered by (number of admissible destinations, unit id); the first is the **holder** and is
never moved by this rule; each other unit, in that order, takes the admissible destination with the fewest own ground
units after the moves already assigned at this decision, then the lowest entry cost in its mode, then the lowest hex,
provided the count stays within four; a unit with no destination left stays (``no_destination_left``) and a unit with
no admissible destination stays (``no_admissible_destination``). The **legal tier** holds when the batch moves at
least one unit.

**Action change**: each assigned unit gets ``{"actor", "obj_id", "type": 1, "move_path": [destination]}`` appended
after ``baseline-v2``'s actions, in batch order; ``baseline-v2``'s actions are kept unchanged and in order. Each
dispersed unit then enters a **hold** ``(unit, objective, destination, start step)``: while it lasts every
``baseline-v2`` MOVE of the unit is withheld (removed; the rest keep their order). A hold is released, before any
action is examined, by the first of :data:`RELEASE_REASONS`: the objective is no longer held; the unit is absent from
the own operators. A unit under a hold is neither an idle holder nor a dispersal candidate.

Non-play decisions pass unchanged and leave the memory unchanged. A new game starts from an empty :class:`DispersionMemory`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveMode
from ..decision.gate import _path_problem
from ..decision.routing import ROADBLOCKED_MODES, move_mode
from ..evaluation.t7_visibility import hex_distance

SHADOW_ID = "t12-o1-dispersion-shadow"
STATUS = "ANALYSIS SHADOW - NON-EXECUTABLE"
EXECUTABLE = False
MOVE = 1
GROUND = (1, 2)
PLAY_STAGE = 2
MIN_IDLE = 2
STACK_LIMIT = 4
GROUND_MODES = (MoveMode.VEHICLE, MoveMode.VEHICLE_MARCH, MoveMode.INFANTRY)
#: Idle levels, nested, in evaluation order (registration, section 7).
IDLE_LEVELS = ("A_stationary", "B_no_route", "C_no_transition", "D_no_transport_transition", "E_not_suppressed",
               "F_no_baseline_move", "G_no_baseline_action")
#: Why a neighbour is not a legal one-hex destination for a unit, first match.
LEGAL_REASONS = ("legal", "move_not_listed", "no_movement_mode", "gate_path_refused", "stack_full")
#: Why a legal neighbour is not admissible under the local rule, first match.
ADMISSIBLE_REASONS = ("admissible", "objective_hex", "visible_enemy", "own_route_hex")
#: Outcome of each idle centre unit in a batch.
BATCH_OUTCOMES = ("holder", "dispersed", "no_destination_left", "no_admissible_destination")
RELEASE_REASONS = ("objective_not_held", "unit_absent")
#: Raw operator fields the idle definition reads beyond the census unit view (captured by the loader).
TRANSITION_FIELDS = ("stop", "move_to_stop_remain_time", "change_state_remain_time", "get_on_remain_time",
                     "get_off_remain_time")


def hex_int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def positive(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def is_ground(u: Optional[Mapping[str, Any]]) -> bool:
    return bool(u) and u.get("type") in GROUND and hex_int(u.get("cur_hex")) is not None


def neighbours(h: int, rows: int, cols: int) -> Tuple[int, ...]:
    """The hexes at distance 1 from ``h`` inside a ``rows`` x ``cols`` map (four-digit hexes, row * 100 + col),
    sorted."""
    r, c = divmod(h, 100)
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if not (dr or dc):
                continue
            rr, cc = r + dr, c + dc
            if 0 <= rr < rows and 0 <= cc < cols and hex_distance(h, rr * 100 + cc) == 1:
                out.append(rr * 100 + cc)
    return tuple(sorted(out))


def ground_counts(own: Mapping[Any, Mapping[str, Any]]) -> Dict[int, int]:
    """Own ground units per hex."""
    out: Dict[int, int] = {}
    for u in own.values():
        if is_ground(u):
            out[u["cur_hex"]] = out.get(u["cur_hex"], 0) + 1
    return out


def idle_level(u: Mapping[str, Any], extra: Mapping[str, Any], acted: Mapping[Any, Sequence[int]], unit_id: Any) -> str:
    """The first idle level the unit fails, or ``"idle"`` when it passes all of :data:`IDLE_LEVELS`. ``extra`` holds the
    unit's :data:`TRANSITION_FIELDS` from the raw observation; ``acted`` maps a unit to the action types
    ``baseline-v2`` gives it at this decision."""
    if positive(u.get("speed")):
        return IDLE_LEVELS[0]
    if u.get("move_path"):
        return IDLE_LEVELS[1]
    stopping = extra.get("stop") == 0 or positive(extra.get("move_to_stop_remain_time"))
    if stopping or positive(extra.get("change_state_remain_time")):
        return IDLE_LEVELS[2]
    if positive(extra.get("get_on_remain_time")) or positive(extra.get("get_off_remain_time")):
        return IDLE_LEVELS[3]
    if u.get("keep"):
        return IDLE_LEVELS[4]
    types = acted.get(unit_id) or ()
    if MOVE in types:
        return IDLE_LEVELS[5]
    if types:
        return IDLE_LEVELS[6]
    return "idle"


@dataclass(frozen=True)
class Context:
    """One decision's inputs (private): the seat's colour, step, stage, own units, visible enemies, objective flags,
    the listed actions per unit, the ``baseline-v2`` actions, the movement costs (``MoveCosts``), the roadblock hexes,
    the raw transition fields per own unit, and the seat id used for appended actions."""

    faction: int
    cur_step: int
    stage: Any
    own: Mapping[Any, Mapping[str, Any]]
    enemies: Tuple[Mapping[str, Any], ...]
    flags: Mapping[Any, Any]
    valid: Mapping[Any, Mapping[int, Any]]
    actions: Tuple[Mapping[str, Any], ...]
    costs: Any
    roadblocks: frozenset
    extras: Mapping[Any, Mapping[str, Any]]
    actor: Any = None


class _RouterView:
    """The minimum the gate's path check reads from a router: its ``costs``."""

    def __init__(self, costs: Any) -> None:
        self.costs = costs


def legal_reason(ctx: Context, unit_id: Any, centre: int, dest: int, counts: Mapping[int, int]) -> str:
    """Whether a one-hex MOVE of the unit from ``centre`` to ``dest`` is legally supported, first failing reason of
    :data:`LEGAL_REASONS`."""
    u = ctx.own[unit_id]
    if MOVE not in (ctx.valid.get(unit_id) or {}):
        return LEGAL_REASONS[1]
    mode = move_mode(u.get("type"), u.get("move_state"))
    if mode is None:
        return LEGAL_REASONS[2]
    blocked = ctx.roadblocks if mode in ROADBLOCKED_MODES else frozenset()
    if _path_problem([dest], centre, mode, blocked, _RouterView(ctx.costs)) is not None:
        return LEGAL_REASONS[3]
    if counts.get(dest, 0) >= STACK_LIMIT:
        return LEGAL_REASONS[4]
    return LEGAL_REASONS[0]


def route_hexes(ctx: Context) -> frozenset:
    """Every hex of an own unit's observed ``move_path`` or of a ``baseline-v2`` MOVE route at this decision."""
    out = set()
    for u in ctx.own.values():
        out.update(h for h in (u.get("move_path") or ()) if hex_int(h) is not None)
    for a in ctx.actions:
        if a.get("type") == MOVE:
            out.update(h for h in (a.get("move_path") or ()) if hex_int(h) is not None)
    return frozenset(out)


def admissible_reason(ctx: Context, dest: int, routes: frozenset, enemy_hexes: frozenset) -> str:
    if dest in ctx.flags:
        return ADMISSIBLE_REASONS[1]
    if dest in enemy_hexes:
        return ADMISSIBLE_REASONS[2]
    if dest in routes:
        return ADMISSIBLE_REASONS[3]
    return ADMISSIBLE_REASONS[0]


def entry_cost(ctx: Context, unit: Mapping[str, Any], centre: int, dest: int) -> float:
    mode = move_mode(unit.get("type"), unit.get("move_state"))
    return ctx.costs.neighbours(mode, centre).get(dest, float("inf")) if mode is not None else float("inf")


@dataclass(frozen=True)
class UnitCheck:
    """One idle centre unit: its unit id, the legal reason per neighbour, the admissible destinations, and its batch
    outcome and destination."""

    unit: Any
    legal: Tuple[Tuple[int, str], ...]
    admissible: Tuple[int, ...]
    outcome: str
    destination: Optional[int] = None


@dataclass(frozen=True)
class ObjectiveCheck:
    """One held objective at one decision (private): the centre's own ground units with their idle level, the idle
    units, the neighbours with their own ground counts and passability, the theoretical trigger, the batch, and the
    legal tier."""

    objective: int
    centre_units: Tuple[Tuple[Any, str], ...]
    idle: Tuple[Any, ...]
    held_out: Tuple[Any, ...]
    neighbour_counts: Tuple[Tuple[int, int, bool], ...]
    trigger: bool
    units: Tuple[UnitCheck, ...] = ()
    legal_tier: bool = False

    @property
    def dispersed(self) -> Tuple[Tuple[Any, int], ...]:
        return tuple((c.unit, c.destination) for c in self.units if c.outcome == "dispersed")

    @property
    def holder(self) -> Optional[Any]:
        return next((c.unit for c in self.units if c.outcome == "holder"), None)


def evaluate(ctx: Context, held: Iterable[Any] = ()) -> Tuple[ObjectiveCheck, ...]:
    """Every objective the side holds, with the trigger and the batch, in increasing hex order. ``held`` lists the
    units under an active hold (they are not idle holders). The batch counts are shared across objectives."""
    if ctx.stage != PLAY_STAGE:
        return ()
    held = set(held)
    counts = ground_counts(ctx.own)
    acted: Dict[Any, List[int]] = {}
    for a in ctx.actions:
        acted.setdefault(a.get("obj_id"), []).append(a.get("type"))
    routes = route_hexes(ctx)
    enemy_hexes = frozenset(e["cur_hex"] for e in ctx.enemies if hex_int(e.get("cur_hex")) is not None)
    assigned: Dict[int, int] = {}
    out: List[ObjectiveCheck] = []
    for centre in sorted(c for c, flag in ctx.flags.items() if hex_int(c) is not None and flag == ctx.faction):
        on = sorted(o for o, u in ctx.own.items() if is_ground(u) and u["cur_hex"] == centre)
        levels = tuple((o, idle_level(ctx.own[o], ctx.extras.get(o) or {}, acted, o)) for o in on)
        idle = tuple(o for o, lv in levels if lv == "idle" and o not in held)
        held_out = tuple(o for o, lv in levels if lv == "idle" and o in held)
        nbrs = neighbours(centre, ctx.costs.rows, ctx.costs.cols)
        cells = tuple((n, counts.get(n, 0), any(n in ctx.costs.neighbours(m, centre) for m in GROUND_MODES))
                      for n in nbrs)
        trigger = len(idle) >= MIN_IDLE and any(p and k < STACK_LIMIT for _, k, p in cells)
        if not trigger:
            out.append(ObjectiveCheck(centre, levels, idle, held_out, cells, False))
            continue
        per: Dict[Any, Tuple[Tuple[Tuple[int, str], ...], Tuple[int, ...]]] = {}
        for o in idle:
            legal = tuple((n, legal_reason(ctx, o, centre, n, counts)) for n in nbrs)
            admissible = tuple(n for n, r in legal if r == LEGAL_REASONS[0]
                               and admissible_reason(ctx, n, routes, enemy_hexes) == ADMISSIBLE_REASONS[0])
            per[o] = (legal, admissible)
        order = sorted(idle, key=lambda o: (len(per[o][1]), o))
        checks: List[UnitCheck] = [UnitCheck(order[0], per[order[0]][0], per[order[0]][1], "holder")]
        for o in order[1:]:
            legal, admissible = per[o]
            if not admissible:
                checks.append(UnitCheck(o, legal, admissible, "no_admissible_destination"))
                continue
            room = [n for n in admissible if counts.get(n, 0) + assigned.get(n, 0) < STACK_LIMIT]
            if not room:
                checks.append(UnitCheck(o, legal, admissible, "no_destination_left"))
                continue
            u = ctx.own[o]
            dest = min(room, key=lambda n: (counts.get(n, 0) + assigned.get(n, 0), entry_cost(ctx, u, centre, n), n))
            assigned[dest] = assigned.get(dest, 0) + 1
            checks.append(UnitCheck(o, legal, admissible, "dispersed", dest))
        tier = any(c.outcome == "dispersed" for c in checks)
        out.append(ObjectiveCheck(centre, levels, idle, held_out, cells, True, tuple(checks), tier))
    return tuple(out)


@dataclass(frozen=True)
class DispersionMemory:
    """Active holds ``(unit, objective, destination, start_step)``, sorted by unit."""

    holds: Tuple[Tuple[Any, int, int, int], ...] = ()


@dataclass(frozen=True)
class DispersionEvent:
    """``disperse`` (an appended MOVE), ``withhold`` (a ``baseline-v2`` MOVE of a held unit removed) or ``release``
    (with ``reason``)."""

    kind: str
    unit: Any
    objective: int
    step: int
    destination: Optional[int] = None
    index: Optional[int] = None
    reason: Optional[str] = None
    start: Optional[int] = None


@dataclass(frozen=True)
class DispersionResult:
    actions: Tuple[Mapping[str, Any], ...]
    added: Tuple[Mapping[str, Any], ...]
    withheld: Tuple[int, ...]
    events: Tuple[DispersionEvent, ...]
    checks: Tuple[ObjectiveCheck, ...]
    memory: DispersionMemory


def release_reason(ctx: Context, unit_id: Any, objective: int) -> Optional[str]:
    if ctx.flags.get(objective) != ctx.faction:
        return RELEASE_REASONS[0]
    if unit_id not in ctx.own:
        return RELEASE_REASONS[1]
    return None


def decide(ctx: Context, memory: DispersionMemory) -> DispersionResult:
    """One decision of the shadow: the candidate action list (``baseline-v2``'s minus the withheld MOVEs of held units,
    then the appended dispersion MOVEs), the appended actions, the withheld indices, the events, the objective checks
    and the new memory. Deterministic; inputs are not modified."""
    actions = [dict(a) for a in ctx.actions]
    if ctx.stage != PLAY_STAGE:
        return DispersionResult(tuple(actions), (), (), (), (), memory)
    events: List[DispersionEvent] = []
    holds: Dict[Any, Tuple[int, int, int]] = {}
    for unit_id, objective, dest, start in memory.holds:
        reason = release_reason(ctx, unit_id, objective)
        if reason is None:
            holds[unit_id] = (objective, dest, start)
        else:
            events.append(DispersionEvent("release", unit_id, objective, ctx.cur_step, dest, reason=reason, start=start))
    withheld: List[int] = []
    for i, a in enumerate(actions):
        if a.get("type") == MOVE and a.get("obj_id") in holds:
            objective, dest, start = holds[a["obj_id"]]
            withheld.append(i)
            events.append(DispersionEvent("withhold", a["obj_id"], objective, ctx.cur_step, dest, index=i, start=start))
    checks = evaluate(ctx, holds)
    added: List[Dict[str, Any]] = []
    for check in checks:
        if not check.legal_tier:
            continue
        for unit_id, dest in check.dispersed:
            added.append({"actor": ctx.actor, "obj_id": unit_id, "type": MOVE, "move_path": [dest]})
            holds[unit_id] = (check.objective, dest, ctx.cur_step)
            events.append(DispersionEvent("disperse", unit_id, check.objective, ctx.cur_step, dest, start=ctx.cur_step))
    kept = set(withheld)
    out = tuple(a for i, a in enumerate(actions) if i not in kept) + tuple(added)
    new = DispersionMemory(tuple(sorted((u, o, d, s) for u, (o, d, s) in holds.items())))
    return DispersionResult(out, tuple(added), tuple(withheld), tuple(events), checks, new)
