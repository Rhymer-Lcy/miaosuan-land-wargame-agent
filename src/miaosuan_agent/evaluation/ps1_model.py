"""PS-1 design study: a capacity-constrained movement model for offline counterfactuals.

DESIGN STUDY (``docs/PS1_DESIGN.md``): no production policy lives here and nothing here observes the engine; every
output is model-derived. The module models one seat's own ground units on the setup cost graph under the platform's
stacking rule (at most ``K`` own ground units in a hex; a full hex cannot be entered or passed through), with the
per-hex time model ``tau = 720 / basic_speed * cost`` seconds (cost = the mode's maximum speed / current speed, as
documented; 200 m hexes, inferred). It provides:

* static analysis of one state: occupancy, full hexes, blocked units, the wait-for graph, the maximal deadlocked set
  and its hex cycles (protocol section 4);
* a step simulator: orders are applied at decision steps; a unit enters its next hex when its hex time has elapsed and
  the hex is not full, in ascending unit order within a step (assumption M2); a stop drops the rest of the move and
  starts a 75-step transition, after the unit completes a hex it is moving into (rule C2), or at once when it is
  waiting in front of a full hex (assumption M3, behaviours E1 to E4 unverified);
* a surrogate of ``baseline-v2``'s movement and occupation rules for continuations (assumption M7);
* the research alternatives PS-1A (capacity-aware dispatch) and PS-1B (stalled-movement recovery) as policies inside
  the simulator, each returning a witness when it finds no capacity-consistent escape;
* an independent validator that re-checks a trajectory against the stacking limit and the graph's adjacency.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

K = 4
STOP_PENALTY = 75
STALL_FACTOR = 2
STALL_MARGIN = 10
SECONDS_PER_HEX_AT_1KMH = 720.0  # a 200 m hex: 0.2 km / (1 km/h) * 3600 s/h
TRANSIT_WINDOW = 2  # PS-1A: transit hexes checked at the start of a new path (declared before any run)

Edges = Mapping[int, Mapping[int, float]]  # hex -> {neighbour: entry cost}


def hex_time(basic_speed: float, cost: float) -> int:
    """Whole steps to enter a neighbouring hex of the given entry cost at the given basic speed (km/h)."""
    if not (basic_speed > 0 and cost > 0):
        raise ValueError("speed and cost must be positive")
    return int(SECONDS_PER_HEX_AT_1KMH / basic_speed * cost + 0.5)


@dataclass(frozen=True)
class Unit:
    """One own unit as the model sees it. ``path`` is the remaining move path, next hex first."""

    uid: int
    hex: int
    speed: float
    mode: int
    path: Tuple[int, ...] = ()
    ready_at: Optional[int] = None  # step at which it may enter path[0]
    stopped_until: int = -1  # end of a move-to-stop transition: no order, no movement before it
    stop_after_entry: bool = False  # a stop was ordered while it was moving into path[0] (rule C2)
    last_progress: int = 0  # step of the last hex change or order
    ground: bool = True
    waiting: bool = False  # M1b: its traversal ended in front of a full hex; it stands at its hex centre (speed 0)

    @property
    def moving(self) -> bool:
        return bool(self.path)

    @property
    def next_hex(self) -> Optional[int]:
        return self.path[0] if self.path else None

    @property
    def destination(self) -> Optional[int]:
        return self.path[-1] if self.path else None


# ----------------------------------------------------------------------------------------------
# static analysis of one state


def occupancy(units: Iterable[Unit]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for u in units:
        if u.ground:
            out[u.hex] = out.get(u.hex, 0) + 1
    return out


def full_hexes(units: Iterable[Unit], k: int = K) -> FrozenSet[int]:
    return frozenset(h for h, n in occupancy(units).items() if n >= k)


def blocked_units(units: Sequence[Unit], k: int = K) -> FrozenSet[int]:
    """Ground units with an outstanding order whose next hex is full."""
    full = full_hexes(units, k)
    return frozenset(u.uid for u in units if u.ground and u.moving and u.next_hex in full)


def wait_for(units: Sequence[Unit], k: int = K) -> Dict[int, Tuple[int, ...]]:
    """u -> the ground units standing in u's next hex, for every blocked unit u."""
    blocked = blocked_units(units, k)
    by_hex: Dict[int, List[int]] = {}
    for u in units:
        if u.ground:
            by_hex.setdefault(u.hex, []).append(u.uid)
    return {u.uid: tuple(sorted(v for v in by_hex.get(u.next_hex, ()) if v != u.uid))
            for u in units if u.uid in blocked}


def deadlocked(units: Sequence[Unit], k: int = K, leaving: FrozenSet[int] = frozenset()) -> FrozenSet[int]:
    """The maximal set D of blocked units such that every unit in the next hex of a unit of D is in D or a holder.

    A holder is a ground unit without an outstanding order and not in ``leaving`` (units already scheduled to move,
    such as those in a recovery transition). Greatest fixed point: start from every blocked unit and remove any unit
    whose next hex holds a unit that has an order, or is leaving, and is not in D (that unit might leave).
    """
    graph = wait_for(units, k)
    moving = {u.uid for u in units if u.moving} | set(leaving)
    d: Set[int] = set(graph)
    changed = True
    while changed:
        changed = False
        for uid in sorted(d):
            if any(v in moving and v not in d for v in graph[uid]):
                d.discard(uid)
                changed = True
    return frozenset(d)


def cycles(units: Sequence[Unit], k: int = K, leaving: FrozenSet[int] = frozenset()) -> List[Tuple[int, ...]]:
    """Elementary cycles (as hex tuples starting at their smallest hex) of the hex graph of deadlocked units."""
    dead = deadlocked(units, k, leaving)
    edges: Dict[int, Set[int]] = {}
    for u in units:
        if u.uid in dead:
            edges.setdefault(u.hex, set()).add(u.next_hex)
    found: Set[Tuple[int, ...]] = set()

    def walk(start: int, node: int, stack: List[int]) -> None:
        for nxt in sorted(edges.get(node, ())):
            if nxt == start:
                found.add(tuple(stack))
            elif nxt not in stack and nxt > start:
                walk(start, nxt, stack + [nxt])

    for start in sorted(edges):
        walk(start, start, [start])
    return sorted(found)


def expected_hex_time(unit: Unit, edges_by_mode: Mapping[int, Edges]) -> Optional[int]:
    if not unit.moving:
        return None
    cost = edges_by_mode[unit.mode].get(unit.hex, {}).get(unit.next_hex)
    return None if cost is None else hex_time(unit.speed, cost)


def stalled(unit: Unit, now: int, edges_by_mode: Mapping[int, Edges]) -> bool:
    """Outstanding order and no progress for longer than STALL_FACTOR expected hex times plus STALL_MARGIN."""
    tau = expected_hex_time(unit, edges_by_mode)
    return tau is not None and now - unit.last_progress > STALL_FACTOR * tau + STALL_MARGIN


# ----------------------------------------------------------------------------------------------
# shortest paths (Dijkstra with the project router's tie-breaking: heap of (cost, hex), strict improvement only)


def shortest_paths(edges: Edges, start: int, blocked: FrozenSet[int] = frozenset()) -> Tuple[Dict[int, float], Dict[int, int]]:
    import heapq
    cost: Dict[int, float] = {start: 0.0}
    previous: Dict[int, int] = {}
    done: Set[int] = set()
    frontier = [(0.0, start)]
    while frontier:
        distance, node = heapq.heappop(frontier)
        if node in done:
            continue
        done.add(node)
        for neighbour, c in edges.get(node, {}).items():
            if neighbour in blocked or neighbour in done:
                continue
            candidate = distance + c
            if neighbour not in cost or candidate < cost[neighbour]:
                cost[neighbour] = candidate
                previous[neighbour] = node
                heapq.heappush(frontier, (candidate, neighbour))
    return cost, previous


def path_to(previous: Mapping[int, int], start: int, destination: int, cost: Mapping[int, float]) -> Optional[Tuple[int, ...]]:
    if destination not in cost:
        return None
    hexes = []
    node = destination
    while node != start:
        hexes.append(node)
        node = previous[node]
    return tuple(reversed(hexes))


# ----------------------------------------------------------------------------------------------
# simulation


@dataclass(frozen=True)
class Event:
    step: int
    kind: str  # "enter", "order", "stop", "occupy", "flag", "hold", "recover", "no-escape"
    uid: Optional[int]
    detail: Tuple = ()


class ModelError(Exception):
    """An order the documented contract forbids (a move to a unit with an outstanding move), or an inconsistency."""


@dataclass
class Simulation:
    """Own units and objectives; ``step`` is the decision step whose state ``units`` describes."""

    units: List[Unit]
    edges_by_mode: Mapping[int, Edges]
    step: int
    objectives: Dict[int, int] = field(default_factory=dict)  # objective hex -> flag (faction holding it, -1 none)
    faction: int = 0
    end_step: int = 1800
    k: int = K
    blocked_by_mode: Mapping[int, FrozenSet[int]] = field(default_factory=dict)  # roadblocks per mode
    restart_after_wait: bool = False  # M1b (protocol amendment 1) instead of M1
    events: List[Event] = field(default_factory=list)
    _flips: Dict[int, int] = field(default_factory=dict)

    # ---- queries
    def unit(self, uid: int) -> Unit:
        for u in self.units:
            if u.uid == uid:
                return u
        raise KeyError(uid)

    def _put(self, unit: Unit) -> None:
        self.units = [unit if u.uid == unit.uid else u for u in self.units]

    def unheld(self) -> List[int]:
        return sorted(h for h, flag in self.objectives.items() if flag != self.faction)

    def can_order(self, uid: int) -> bool:
        u = self.unit(uid)
        return not u.moving and self.step >= u.stopped_until

    # ---- orders
    def order_move(self, uid: int, path: Sequence[int]) -> None:
        u = self.unit(uid)
        if u.moving:
            raise ModelError(f"unit {uid} has an outstanding move; an issued move cannot be changed (C1)")
        if self.step < u.stopped_until:
            raise ModelError(f"unit {uid} is in its move-to-stop transition until step {u.stopped_until}")
        if not path:
            raise ModelError("empty path")
        hexes = (u.hex,) + tuple(path)
        edges = self.edges_by_mode[u.mode]
        for a, b in zip(hexes, hexes[1:]):
            if b not in edges.get(a, {}) or b in self.blocked_by_mode.get(u.mode, frozenset()):
                raise ModelError(f"path step {a}->{b} is not traversable in mode {u.mode}")
        self._put(replace(u, path=tuple(path), ready_at=self.step + hex_time(u.speed, edges[u.hex][path[0]]),
                          last_progress=self.step))
        self.events.append(Event(self.step, "order", uid, (path[-1], len(path))))

    def order_stop(self, uid: int) -> None:
        """A stop: completes a hex it is moving into (C2), or takes effect at once if it waits in front of a full hex
        (M3, unverified behaviours E1, E2, E4); a 75-step transition follows either way."""
        u = self.unit(uid)
        if not u.moving:
            raise ModelError(f"unit {uid} has no move to stop")
        waiting = u.waiting or (u.ready_at is not None and u.ready_at <= self.step)  # in front of a full hex
        if waiting or not u.ground:
            self._put(replace(u, path=(), ready_at=None, waiting=False, stopped_until=self.step + STOP_PENALTY,
                              last_progress=self.step))
        else:
            self._put(replace(u, path=u.path[:1], stop_after_entry=True))
        self.events.append(Event(self.step, "stop", uid, ("at once" if waiting else "after entry",)))

    def occupy(self, uid: int) -> None:
        u = self.unit(uid)
        if self.objectives.get(u.hex, self.faction) == self.faction:
            raise ModelError(f"unit {uid} does not stand on an unheld objective")
        self._flips[u.hex] = self.faction
        self.events.append(Event(self.step, "occupy", uid, ()))

    # ---- time
    def advance(self) -> None:
        """One engine second: flags flip; units whose hex time elapsed enter their next hex if it is not full.

        M1 (as registered): a unit that finds its next hex full keeps retrying and enters in the first step it has room.
        M1b (amendment 1, ``restart_after_wait``): it stands at its hex centre instead (``waiting``); in the first step
        its next hex has room it starts the traversal again and arrives a hex time later (counting that step).
        """
        nxt = self.step + 1
        for hex_, flag in sorted(self._flips.items()):
            self.objectives[hex_] = flag
            self.events.append(Event(nxt, "flag", None, (hex_, flag)))
        self._flips = {}
        occ = occupancy(self.units)
        for u in sorted(self.units, key=lambda x: x.uid):
            if not u.moving:
                continue
            target = u.path[0]
            if u.waiting:
                if not (u.ground and occ.get(target, 0) >= self.k):
                    tau = hex_time(u.speed, self.edges_by_mode[u.mode][u.hex][target])
                    self._put(replace(u, waiting=False, ready_at=nxt + tau - 1))
                continue
            if not (u.ready_at is not None and u.ready_at <= nxt):
                continue
            if u.ground and occ.get(target, 0) >= self.k:
                if self.restart_after_wait:
                    self._put(replace(u, waiting=True, ready_at=None))
                continue  # M1: waits at its hex, retries every step
            if u.ground:
                occ[u.hex] -= 1
                occ[target] = occ.get(target, 0) + 1
            rest = u.path[1:]
            if u.stop_after_entry:
                moved = replace(u, hex=target, path=(), ready_at=None, stop_after_entry=False,
                                stopped_until=nxt + STOP_PENALTY, last_progress=nxt)
            else:
                ready = nxt + hex_time(u.speed, self.edges_by_mode[u.mode][target][rest[0]]) if rest else None
                moved = replace(u, hex=target, path=rest, ready_at=ready, last_progress=nxt)
            self._put(moved)
            self.events.append(Event(nxt, "enter", u.uid, (target,)))
        self.step = nxt

    def run(self, policy: Optional[Callable[["Simulation"], None]] = None) -> None:
        while self.step < self.end_step:
            if policy is not None:
                policy(self)
            self.advance()


# ----------------------------------------------------------------------------------------------
# policies used inside the simulator


def recorded_orders(orders: Mapping[int, Sequence[Tuple[str, int, Tuple[int, ...]]]]) -> Callable[[Simulation], None]:
    """Replay recorded orders: step -> [(kind, uid, path)], kind in move/stop/occupy (fidelity F1)."""
    def policy(sim: Simulation) -> None:
        for kind, uid, path in orders.get(sim.step, ()):
            if kind == "move":
                sim.order_move(uid, path)
            elif kind == "stop":
                sim.order_stop(uid)
            elif kind == "occupy":
                sim.occupy(uid)
    return policy


def surrogate_choice(sim: Simulation, u: Unit, exclude: FrozenSet[int] = frozenset()) -> Optional[Tuple[int, ...]]:
    """M7: the cheapest path to the cheapest unheld objective (ties: lower hex), roadblocks excluded for the mode."""
    targets = [h for h in sim.unheld() if h not in exclude]
    if not targets or u.hex in sim.unheld():
        return None
    cost, previous = shortest_paths(sim.edges_by_mode[u.mode], u.hex, sim.blocked_by_mode.get(u.mode, frozenset()))
    options = sorted((cost[h], h) for h in targets if h in cost)
    for _, h in options:
        path = path_to(previous, u.hex, h, cost)
        if path:
            return path
    return None


def surrogate(sim: Simulation, admit: Optional[Callable[[Simulation, Unit, Tuple[int, ...]], Optional[Tuple[int, ...]]]] = None) -> None:
    """M7: per unit in ascending uid: occupy an unheld objective it stands on (one per objective per step), else move
    to the cheapest unheld objective; never re-order a unit with an outstanding move or in a stop transition."""
    reserved: Set[int] = set()
    for u in sorted(sim.units, key=lambda x: x.uid):
        if not u.ground or not sim.can_order(u.uid):
            continue
        if u.hex in sim.unheld():
            if u.hex not in reserved:
                sim.occupy(u.uid)
                reserved.add(u.hex)
            continue
        path = surrogate_choice(sim, u)
        if path is None:
            continue
        if admit is not None:
            path = admit(sim, u, path)
            if path is None:
                sim.events.append(Event(sim.step, "hold", u.uid, ()))
                continue
        sim.order_move(u.uid, path)


def committed(sim: Simulation, hex_: int, window: Optional[int] = None) -> int:
    """Units standing in ``hex_`` plus units whose remaining path contains it (within its first ``window`` hexes)."""
    n = 0
    for u in sim.units:
        if not u.ground:
            continue
        if u.hex == hex_:
            n += 1
        elif u.moving and hex_ in (u.path if window is None else u.path[:window]):
            n += 1
    return n


def ps1a_admit(sim: Simulation, u: Unit, path: Tuple[int, ...]) -> Optional[Tuple[int, ...]]:
    """PS-1A: admit a new path only if its destination and its first TRANSIT_WINDOW hexes are not saturated
    (fewer than K units standing there or ordered through them); otherwise try the next objective, else hold."""
    def admissible(p: Tuple[int, ...]) -> bool:
        if committed(sim, p[-1]) >= sim.k:
            return False
        return all(committed(sim, h, TRANSIT_WINDOW) < sim.k for h in p[:TRANSIT_WINDOW] if h != p[-1])
    if admissible(path):
        return path
    tried = {path[-1]}
    while True:
        alt = surrogate_choice(sim, u, frozenset(tried))
        if alt is None:
            return None
        if admissible(alt):
            return alt
        tried.add(alt[-1])


def ps1a(sim: Simulation) -> None:
    surrogate(sim, admit=ps1a_admit)


@dataclass
class Recovery:
    """PS-1B state: per-unit last recovery step (at most one recovery per unit per window) and pending re-orders."""

    option: str = "auto"  # "auto", "back-off" (move the waiting group aside) or "bypass" (re-route the other group)
    window: int = 600
    last: Dict[int, int] = field(default_factory=dict)
    pending: Dict[int, Tuple[int, ...]] = field(default_factory=dict)  # uid -> planned path after the transition
    witnesses: List[Dict] = field(default_factory=list)


def escape_plan(sim: Simulation, group: Sequence[Unit], mode: str, avoid: FrozenSet[int]) -> Optional[Dict[int, Tuple[int, ...]]]:
    """Paths that take every unit of ``group`` out of the dependency without entering a full hex or ``avoid``.

    back-off: to the nearest hexes (by path cost) that are not full, not on a remaining path of a blocked unit, with
    spare capacity counted as units are placed. bypass: to each unit's destination by a path avoiding full hexes.
    Returns None when some unit has no such path.
    """
    full = full_hexes(sim.units, sim.k)
    occ = occupancy(sim.units)
    plan: Dict[int, Tuple[int, ...]] = {}
    placed: Dict[int, int] = {}
    for u in sorted(group, key=lambda x: x.uid):
        barred = frozenset(full | avoid | sim.blocked_by_mode.get(u.mode, frozenset())) - {u.hex}
        cost, previous = shortest_paths(sim.edges_by_mode[u.mode], u.hex, barred)
        if mode == "bypass":
            dest = u.path[-1] if u.path else None
            p = path_to(previous, u.hex, dest, cost) if dest is not None else None
            if not p:
                return None
            plan[u.uid] = p
            continue
        options = sorted((c, h) for h, c in cost.items() if h != u.hex)
        chosen = None
        for _, h in options:
            if occ.get(h, 0) + placed.get(h, 0) < sim.k:
                chosen = h
                break
        if chosen is None:
            return None
        placed[chosen] = placed.get(chosen, 0) + 1
        plan[u.uid] = path_to(previous, u.hex, chosen, cost)
    return plan


def ps1b(state: Recovery) -> Callable[[Simulation], None]:
    """PS-1B: when a deadlocked set exists and all its units are stalled, stop the group that breaks the cycle at the
    least cost and, after the transition, re-order it by its escape plan; the surrogate orders everyone else."""
    def policy(sim: Simulation) -> None:
        for uid, path in sorted(state.pending.items()):
            if sim.can_order(uid):
                sim.order_move(uid, path)
                del state.pending[uid]
        leaving = frozenset(state.pending)
        dead = deadlocked(sim.units, sim.k, leaving)
        if dead and all(stalled(sim.unit(uid), sim.step, sim.edges_by_mode) for uid in dead) \
                and all(sim.step - state.last.get(uid, -10 ** 9) >= state.window for uid in dead):
            groups: Dict[int, List[Unit]] = {}
            for uid in sorted(dead):
                u = sim.unit(uid)
                groups.setdefault(u.hex, []).append(u)
            on_cycles = {h for cyc in cycles(sim.units, sim.k, leaving) for h in cyc}
            if on_cycles:  # only a group standing on a cycle can break it
                groups = {h: g for h, g in groups.items() if h in on_cycles}
            remaining_paths = frozenset(h for uid in dead for h in sim.unit(uid).path)
            candidates = []
            for hex_, group in sorted(groups.items()):
                for mode in (("back-off", "bypass") if state.option == "auto" else (state.option,)):
                    avoid = remaining_paths if mode == "back-off" else frozenset()
                    plan = escape_plan(sim, group, mode, avoid)
                    on_objective = hex_ in sim.objectives
                    if plan is not None:
                        candidates.append((len(group), on_objective, mode != "back-off", hex_, mode, plan))
                    else:
                        state.witnesses.append({"step": sim.step, "hex": hex_, "mode": mode, "units": len(group),
                                                "reason": "no path avoiding full hexes to a free hex or the destination"})
            if not candidates:
                sim.events.append(Event(sim.step, "no-escape", None, (len(dead),)))
                for uid in dead:
                    state.last[uid] = sim.step
            else:
                _, _, _, hex_, mode, plan = min(candidates, key=lambda c: c[:4])
                for uid, path in sorted(plan.items()):
                    sim.order_stop(uid)
                    state.pending[uid] = path
                    state.last[uid] = sim.step
                sim.events.append(Event(sim.step, "recover", None, (mode, len(plan))))
        surrogate(sim)
    return policy


# ----------------------------------------------------------------------------------------------
# independent trajectory validator (does not use the simulator)


def validate_trajectory(start: Mapping[int, int], entries: Sequence[Tuple[int, int, int]],
                        adjacent: Callable[[int, int, int], bool], ground: Mapping[int, bool], k: int = K) -> List[str]:
    """Replay (step, uid, hex) entries from start positions; report capacity violations and non-adjacent moves."""
    pos = dict(start)
    occ: Dict[int, int] = {}
    for uid, h in pos.items():
        if ground.get(uid, True):
            occ[h] = occ.get(h, 0) + 1
    problems = [f"start: a hex holds {n} ground units" for h, n in sorted(occ.items()) if n > k]
    last = None
    for step, uid, h in entries:
        if last is not None and step < last:
            problems.append(f"step {step}: entries out of order")
        last = step
        if not adjacent(uid, pos[uid], h):
            problems.append(f"step {step}: unit {uid} moved to a non-adjacent hex")
        if ground.get(uid, True):
            if occ.get(h, 0) >= k:
                problems.append(f"step {step}: unit {uid} entered a hex already holding {occ.get(h, 0)}")
            occ[pos[uid]] -= 1
            occ[h] = occ.get(h, 0) + 1
        pos[uid] = h
    return problems
