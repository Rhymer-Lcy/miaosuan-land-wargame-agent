"""The integrated decision cycle (``docs/SPRINT34_INTEGRATED_AGENT.md`` section 6).

One play-stage decision:

1. world view and memory upkeep (sightings, first ownership, tasks of units that are gone);
2. lift life cycle (:mod:`.transport`): records advance; boarding and unloading orders; loaded carriers to move;
3. traffic ledger (:mod:`.traffic`) and the fire picture (:mod:`.fire`);
4. objective pictures and allocation of the free mobile ground units (:mod:`.allocation`), lift pairs included in
   variant B; aircraft support targets;
5. recovery: for each full hex an own unit waits to enter, one free unit standing there with no reason to stay is moved
   out (never through a full hex);
6. per-unit arbitration in ascending id: occupy > lift order > direct fire > move > stay. A unit gets at most one action;
   each move is planned and registered in the traffic ledger before the next unit is planned;
7. indirect fire (variant B) clear of every own unit, path and planned stand;
8. independent validation (:mod:`.validate`) of every action; rejected actions are not emitted;
9. memory: tasks, lifts, orders, fire orders.

Every unit gets a recorded reason, acted or not. Any exception other than a contract violation makes the decision
``baseline-v2``'s own (a fresh instance on the same observation), recorded as a fallback; a contract violation is
handled by the agent like ``baseline-v2`` (no action).
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import ContractError, MoveCosts, Observation, Stage, deployment_completion_available
from ..decision import Memory, StepTrace, UnitDecision
from ..decision.policy import Decision
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import facts as F
from . import memory as M
from . import transport as T
from .allocation import OWN, Allocator, Assignment, known_enemies, support_targets
from .config import Config
from .fire import direct_fire, hazard_hexes, indirect_fire, threat_penalty
from .movement import Terrain, unit_mode
from .traffic import Traffic
from .validate import validate
from .world import State, Unit, World, build_world

CANDIDATE_PREFIX = "s34-integrated"
TRACE_SCHEMA = "miaosuan-decision-trace/1+s34-integrated"
ENABLED = frozenset({F.MOVE, F.SHOOT, F.GET_ON, F.GET_OFF, F.OCCUPY, F.INDIRECT, F.END_DEPLOYMENT})
#: Module labels of a unit's plan (trace and analysis).
MODULES = ("occupy", "transport", "fire", "artillery", "allocation", "recovery", "support", "reserve", "none")
HOLD_FOR_BOARDING = "boarding-hold"


def candidate_id(config: Config) -> str:
    return f"{CANDIDATE_PREFIX}-{config.name}-1"


@dataclass(frozen=True)
class CommanderTrace(StepTrace):
    config: str = ""
    fallback: Optional[str] = None
    plans: Tuple[Tuple[int, str, str, int, int, str], ...] = ()   # (unit, module, kind, target, action type, reason)
    stats: Tuple[Tuple[str, int], ...] = ()
    lift_notes: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = super().to_dict()
        payload["schema"] = TRACE_SCHEMA
        payload["integrated"] = {
            "config": self.config, "fallback": self.fallback,
            "plans": [{"obj_id": u, "module": m, "kind": k, "target": t, "action_type": a, "reason": r}
                      for u, m, k, t, a, r in self.plans],
            "stats": dict(self.stats), "lift_notes": list(self.lift_notes),
        }
        return payload


@dataclass(frozen=True)
class Intent:
    module: str
    kind: str
    target: int
    reason: str


class CommanderPolicy:
    """The integrated agent's policy. ``decide`` is a pure function of (observation, seat, faction, memory)."""

    def __init__(self, costs: Optional[MoveCosts], config: Config) -> None:
        self.config = config
        self.identity = candidate_id(config)
        self.costs = costs
        self.terrain = Terrain(costs) if costs is not None else None
        self.allocator = Allocator(config, self.terrain) if self.terrain is not None else None

    # -- entry -----------------------------------------------------------------------------------
    def decide(self, observation: Observation, seat: int, faction: int, memory: M.CommanderMemory) -> Tuple[
            Tuple[Mapping[str, Any], ...], StepTrace, M.CommanderMemory]:
        try:
            return self._decide(observation, seat, faction, memory)
        except ContractError:
            raise
        except Exception as exc:  # noqa: BLE001 - fail closed to baseline-v2, recorded
            return self._fallback(observation, seat, faction, memory, f"{type(exc).__name__}: {exc}"[:300])

    def _fallback(self, observation: Observation, seat: int, faction: int, memory: M.CommanderMemory,
                  reason: str) -> Tuple[Tuple[Mapping[str, Any], ...], StepTrace, M.CommanderMemory]:
        decision: Decision = ShootReservationPolicy(self.costs).decide(
            observation, seat, faction, Memory(deployment_sent=memory.deployment_sent))
        base = decision.trace
        trace = CommanderTrace(**{f.name: getattr(base, f.name) for f in fields(StepTrace)},
                               config=self.config.name, fallback=reason)
        trace = replace(trace, policy=self.identity)
        new_memory = replace(memory, deployment_sent=decision.memory.deployment_sent,
                             fallbacks=memory.fallbacks + 1)
        return tuple(decision.actions), trace, new_memory

    def _decide(self, observation: Observation, seat: int, faction: int, memory: M.CommanderMemory):
        rows = self.terrain.rows if self.terrain else 100
        cols = self.terrain.cols if self.terrain else 100
        world = build_world(observation, seat, faction, rows, cols)
        if world.stage == Stage.DEPLOYMENT:
            return self._deploy(observation, world, memory)
        if world.stage != Stage.PLAY:
            trace = self._trace(world, None, (), (), (), (f"stage {world.stage} is not interpreted; no action",))
            return (), trace, memory
        if self.terrain is None:
            return self._fallback(observation, seat, faction, memory, "no movement-cost data")
        return self._play(world, memory)

    def _deploy(self, observation: Observation, world: World, memory: M.CommanderMemory):
        if memory.deployment_sent:
            return (), self._trace(world, "already sent", (), (), (), ()), memory
        available = deployment_completion_available(observation, world.seat)
        if not available:
            return (), self._trace(world, "not available", (), (), (), ()), memory
        verdict = validate([{"actor": world.seat, "type": F.END_DEPLOYMENT}], world, self.terrain, ENABLED, True)
        status = "emitted" if verdict.accepted else "rejected by validation"
        trace = self._trace(world, status, (), verdict.accepted, verdict.rejected, ())
        return verdict.accepted, trace, replace(memory, deployment_sent=bool(verdict.accepted))

    # -- play ------------------------------------------------------------------------------------
    def _play(self, world: World, memory: M.CommanderMemory):
        cfg = self.config
        terrain = self.terrain
        allocator = self.allocator
        present = {u.obj_id for u in world.units} | {p.obj_id for p in world.passengers}
        sightings = M.updated_sightings(memory.sightings,
                                        [(e.obj_id, e.hex, e.type, int(e.value)) for e in world.enemies], world.step)
        owned = [o.hex for o in world.objectives if o.flag == world.faction]
        memory = replace(memory, sightings=sightings,
                         first_owned=M.first_owned_update(memory.first_owned, owned, world.step),
                         tasks=tuple(t for t in memory.tasks if t[0] in present),
                         orders=tuple(o for o in memory.orders if o[0] in present),
                         fire_orders=M.live_fire_orders(memory.fire_orders, world.step))

        # 2. lifts
        carry_deadline = world.max_step - 3 * F.TRANSITION - 30
        lift_step = T.step_lifts(world, memory.lifts, carry_deadline)
        busy: Set[int] = set(lift_step.hold_still)
        traffic = Traffic(world)
        hazards = hazard_hexes(world, memory.fire_orders, world.rows, world.cols)
        threat = threat_penalty(world, cfg, world.rows, world.cols)

        # 3-4. allocation
        free = [u for u in world.units
                if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)
                and u.obj_id not in busy]
        free_ids = frozenset(u.obj_id for u in free)
        known = known_enemies(world, memory)
        pictures = allocator.pictures(world, known, free_ids)
        # A unit holding or capturing the objective it stands on is anchored: never offered as a lift passenger, so a
        # delivered passenger is not carried off again by the carrier that dropped it.
        anchored = set()
        for unit_id, kind, target, _ in memory.tasks:
            unit = world.unit(unit_id)
            if kind in (M.HOLD, M.CAPTURE) and unit is not None and unit.hex == target and world.objective(target):
                anchored.add(unit_id)
        for unit_id, action_type, step in memory.orders:
            if action_type == F.GET_ON and world.step - step < cfg.lift_cooldown:
                anchored.add(unit_id)
        lift_candidates = (T.candidates(world, sorted(free_ids - anchored), sorted(busy)) if cfg.transport else [])
        delivered = dict(lift_step.delivered)
        loaded = [(p, world.unit(c), o) for p, c, o in lift_step.loaded if world.unit(c) is not None]
        assignments = allocator.allocate(world, memory, free, pictures, lift_candidates, loaded)
        by_unit: Dict[int, Assignment] = {}
        for a in assignments:
            for member in (a.members or (a.unit,)):
                by_unit[member] = a
        support = support_targets(world, pictures, assignments)

        intents: Dict[int, Intent] = {}
        new_lifts: List[M.Lift] = []
        # A disembark into a hex that already holds four own ground units is not ordered (its engine behaviour is not
        # established; Sprint 22 avoided it too): the carrier waits.
        lift_orders: Dict[int, dict] = {}
        for unit_id, action in lift_step.orders:
            carrier = world.unit(unit_id)
            if carrier is not None and traffic.present.get(carrier.hex, 0) >= F.STACK_LIMIT:
                continue
            lift_orders[unit_id] = action
        for carrier_id, objective in lift_step.carry_moves:
            intents[carrier_id] = Intent("transport", M.CARRY, objective, "carry passenger to objective")
        # Settled loaded carriers follow the allocation: a new target, or (no slot) unload where they stand.
        retarget: Dict[Tuple[int, int], int] = {}
        unload_here: Set[Tuple[int, int]] = set()
        carried_to = {(a.members[0], a.members[1]): a.target for a in assignments if a.kind == M.CARRY}
        for passenger_id, carrier_id, objective in lift_step.loaded:
            carrier = world.unit(carrier_id)
            if (passenger_id, carrier_id) in carried_to:
                target = carried_to[(passenger_id, carrier_id)]
                retarget[(passenger_id, carrier_id)] = target
                note = "carry passenger to objective" + ("" if target == objective else " (re-targeted)")
                intents[carrier_id] = Intent("transport", M.CARRY, target, note)
            elif (carrier is not None and passenger_id in T.options(carrier, F.GET_OFF)
                  and traffic.present.get(carrier.hex, 0) < F.STACK_LIMIT):
                lift_orders[carrier_id] = {"type": F.GET_OFF, "obj_id": carrier_id, "target_obj_id": passenger_id}
                unload_here.add((passenger_id, carrier_id))
                intents.pop(carrier_id, None)
        for a in assignments:
            if a.kind == M.CARRY:
                continue
            if a.kind == M.RIDE:
                infantry_id, carrier_id = a.members
                lift_orders[infantry_id] = {"type": F.GET_ON, "obj_id": infantry_id, "target_obj_id": carrier_id}
                new_lifts.append((infantry_id, carrier_id, a.target, M.BOARDING, world.step))
                busy.update(a.members)
                intents[infantry_id] = Intent("transport", M.RIDE, a.target, a.reason)
                intents[carrier_id] = Intent("transport", HOLD_FOR_BOARDING, a.target,
                                             "hold still while the passenger boards")
                continue
            unit = world.unit(a.unit)
            if unit is None:
                continue
            if unit.hex == a.target:
                intents[a.unit] = Intent("allocation", a.kind, a.target, f"{a.reason}: stay")
            else:
                intents[a.unit] = Intent("allocation", a.kind, a.target, f"{a.reason}: move")
        for unit_id, target in support.items():
            intents.setdefault(unit_id, Intent("support", M.SUPPORT, target, "aircraft support"))

        # 5. recovery of blocked columns, then dispersal of surplus units off full objective hexes
        if cfg.recovery:
            self._recovery(world, traffic, intents, by_unit, busy, pictures)
        if cfg.dispersal:
            self._disperse(world, traffic, intents, busy, hazards)

        # 6. arbitration
        fire = direct_fire(world, cfg, world.units)
        occupy_taken: Set[int] = set()
        proposals: List[Mapping[str, Any]] = []
        plans: List[Tuple[int, str, str, int, int, str]] = []
        decisions: List[UnitDecision] = []
        recovery_moves = 0
        blocked_moves = 0
        for unit in world.units:
            action, module, kind, target, reason = None, "none", "", -1, ""
            intent = intents.get(unit.obj_id)
            if (F.OCCUPY in unit.actions and unit.hex not in occupy_taken
                    and any(o.hex == unit.hex and o.flag != world.faction for o in world.objectives)):
                action = {"type": F.OCCUPY, "obj_id": unit.obj_id}
                occupy_taken.add(unit.hex)
                module, kind, target, reason = "occupy", "occupy", unit.hex, "occupation listed on an objective not held"
            elif unit.obj_id in lift_orders:
                action = dict(lift_orders[unit.obj_id])
                module, kind = "transport", (M.RIDE if action["type"] == F.GET_ON else M.CARRY)
                target, reason = (intent.target if intent else -1), ("embark" if action["type"] == F.GET_ON else "disembark")
            elif unit.obj_id in fire and unit.obj_id not in busy:
                shot = fire[unit.obj_id]
                action = {"type": F.SHOOT, "obj_id": unit.obj_id, "target_obj_id": shot[0], "weapon_id": shot[1]}
                module, kind, target, reason = "fire", "shoot", -1, f"attack level {shot[2]}"
            elif intent is not None and intent.kind not in (M.RIDE, HOLD_FOR_BOARDING) and unit.hex != intent.target \
                    and F.MOVE in unit.actions and not unit.path \
                    and (unit.obj_id not in busy or (intent.module == "transport" and intent.kind == M.CARRY)):
                path, why = self._route(world, unit, intent, traffic, hazards, threat)
                if path:
                    action = {"type": F.MOVE, "obj_id": unit.obj_id, "move_path": list(path)}
                    traffic.order(unit, path)
                    module, kind, target, reason = intent.module, intent.kind, intent.target, intent.reason
                    recovery_moves += intent.module == "recovery"
                else:
                    blocked_moves += 1
                    module, kind, target, reason = intent.module, intent.kind, intent.target, f"{intent.reason}; held: {why}"
            elif intent is not None:
                module, kind, target, reason = intent.module, intent.kind, intent.target, intent.reason
            else:
                module, kind, target, reason = self._idle_reason(unit, busy, world)
            if action is not None:
                action = {"actor": world.seat, **action}
                proposals.append(action)
            plans.append((unit.obj_id, module, kind, target, int(action["type"]) if action else 0, reason))
            decisions.append(UnitDecision(unit.obj_id, (), module, int(action["type"]) if action else None,
                                          None, (("kind", kind), ("target", target)),
                                          no_op_reason=None if action else reason))

        # 7. indirect fire
        artillery_orders = 0
        if cfg.artillery:
            stands = set(h for h, n in traffic.inbound.items() if n > 0) | set(h for h, n in traffic.staying.items() if n > 0)
            acted = {a["obj_id"] for a in proposals}
            for unit_id, hex_, weapon in indirect_fire(world, cfg, stands, memory.fire_orders):
                if unit_id in acted:
                    continue
                proposals.append({"actor": world.seat, "type": F.INDIRECT, "obj_id": unit_id, "jm_pos": hex_,
                                  "weapon_id": weapon})
                artillery_orders += 1
                fired = (unit_id, "artillery", "indirect", hex_, F.INDIRECT, "indirect fire clear of own units")
                plans = [fired if p[0] == unit_id else p for p in plans]
                decisions = [replace(d, rule="artillery", action_type=F.INDIRECT, no_op_reason=None)
                             if d.obj_id == unit_id else d for d in decisions]

        # 8. validation
        verdict = validate(proposals, world, terrain, ENABLED, False)
        rejected_units = {r[1] for r in verdict.rejected}
        decisions = [replace(d, validation=("rejected: " + next(r[2] for r in verdict.rejected if r[1] == d.obj_id))
                             if d.obj_id in rejected_units else "accepted" if d.action_type is not None
                             else "not applicable") for d in decisions]

        # 9. memory
        accepted = verdict.accepted
        tasks: Dict[int, M.Task] = {}
        old = {t[0]: t for t in memory.tasks}
        for unit in world.units:
            intent = intents.get(unit.obj_id)
            if unit.path and unit.obj_id in old and old[unit.obj_id][2] == unit.path[-1]:
                tasks[unit.obj_id] = old[unit.obj_id]
                continue
            if intent is None or intent.module in ("recovery",):
                continue
            prior = old.get(unit.obj_id)
            since = prior[3] if prior and prior[1] == intent.kind and prior[2] == intent.target else world.step
            tasks[unit.obj_id] = (unit.obj_id, intent.kind, intent.target, since)
        for passenger_id, objective in delivered.items():
            tasks[passenger_id] = (passenger_id, M.HOLD, objective, world.step)
        orders = {o[0]: o for o in memory.orders}
        fire_orders = list(memory.fire_orders)
        for a in accepted:
            if "obj_id" in a:
                orders[a["obj_id"]] = (a["obj_id"], int(a["type"]), world.step)
            if a["type"] == F.INDIRECT:
                fire_orders.append((a["jm_pos"], world.step, a["obj_id"]))
        accepted_ids = {(a.get("obj_id"), a["type"]) for a in accepted}
        lifts = []
        for lf in lift_step.lifts:
            pair = (lf[0], lf[1])
            if lf[3] == M.UNLOADING and lf[4] == world.step and (lf[1], F.GET_OFF) not in accepted_ids:
                lf = (lf[0], lf[1], lf[2], M.CARRYING, lf[4])
            elif pair in unload_here and (lf[1], F.GET_OFF) in accepted_ids:
                carrier = world.unit(lf[1])
                lf = (lf[0], lf[1], carrier.hex if carrier else lf[2], M.UNLOADING, world.step)
            elif pair in retarget:
                lf = (lf[0], lf[1], retarget[pair], lf[3], lf[4])
            lifts.append(lf)
        lifts += [lf for lf in new_lifts if (lf[0], F.GET_ON) in accepted_ids]
        new_memory = M.canonical(replace(memory, tasks=tuple(tasks.values()), lifts=tuple(lifts),
                                         orders=tuple(orders.values()), fire_orders=tuple(fire_orders)))
        stats = (("free", len(free)), ("assignments", len(assignments)), ("lift_candidates", len(lift_candidates)),
                 ("lifts", len(new_memory.lifts)), ("recovery_moves", recovery_moves),
                 ("held_moves", blocked_moves), ("artillery_orders", artillery_orders),
                 ("waiting_units", len(traffic.waiting)), ("known_enemies", len(known)))
        trace = self._trace(world, None, tuple(decisions), accepted, verdict.rejected, ())
        trace = replace(trace, plans=tuple(plans), stats=stats, lift_notes=lift_step.notes)
        return accepted, trace, new_memory

    # -- helpers ---------------------------------------------------------------------------------
    def _route(self, world: World, unit: Unit, intent: Intent, traffic: Traffic, hazards: FrozenSet[int],
               threat: Mapping[int, float]) -> Tuple[Optional[Tuple[int, ...]], str]:
        mode = unit_mode(unit.type, unit.move_state)
        if mode is None:
            return None, "no movement mode"
        if unit.air:
            path = self.terrain.plan(mode, unit.hex, intent.target, world.roadblocks)
            return (path, "") if path else (None, "no air route")
        is_objective = world.objective(intent.target) is not None
        cap = self.config.destination_cap if is_objective else F.STACK_LIMIT - 1
        if not traffic.accepts(intent.target, cap):
            return None, "destination stand at capacity"
        if intent.target in hazards:
            return None, "destination under indirect fire"
        blocked = traffic.blocked_for(unit.hex) | (hazards - {unit.hex})
        penalty = dict(traffic.penalty())
        for h, p in threat.items():
            penalty[h] = penalty.get(h, 0.0) + p
        path = self.terrain.plan(mode, unit.hex, intent.target, world.roadblocks, blocked, penalty)
        if not path:
            return None, "no route clear of full hexes"
        if not traffic.first_hex_open(path[0]):
            return None, "first hex full"
        return path, ""

    def _recovery(self, world: World, traffic: Traffic, intents: Dict[int, Intent], by_unit: Mapping[int, Assignment],
                  busy: Set[int], pictures) -> None:
        held = {p.hex for p in pictures if p.status == OWN}
        waiting_paths: Set[int] = set()
        for w in traffic.waiting:
            waiting_paths.update(w.path)
        for hex_, waiters in traffic.blockers().items():
            standing = [u for u in world.units if u.hex == hex_ and not u.path and u.mobile_ground and u.can_move
                        and u.state in (State.SETTLED, State.TRANSITION) and u.obj_id not in busy]
            if not standing:
                continue
            stay = [u for u in standing if (intents.get(u.obj_id) and intents[u.obj_id].target == hex_)]
            movable = [u for u in standing if u not in stay]
            if not movable and hex_ in held and len(stay) <= 1:
                continue
            pool = movable or sorted(stay, key=lambda u: (u.value, u.obj_id))[1:] or ([] if hex_ in held else stay)
            if not pool:
                continue
            mover = min(pool, key=lambda u: (u.value, u.obj_id))
            intent = intents.get(mover.obj_id)
            if intent is not None and intent.target != hex_:
                continue  # it is leaving anyway
            mode = unit_mode(mover.type, mover.move_state)
            options = []
            for n in F.neighbours(hex_, world.rows, world.cols):
                if n in waiting_paths or n not in self.terrain.costs.neighbours(mode, hex_):
                    continue
                if mode is not None and n in world.roadblocks:
                    continue
                if traffic.stand(n) >= F.STACK_LIMIT - 1 or world.objective(n) is not None:
                    continue
                options.append((traffic.stand(n), n))
            if options:
                target = min(options)[1]
                intents[mover.obj_id] = Intent("recovery", M.RESERVE, target,
                                               f"step aside from {hex_} for {len(waiters)} waiting unit(s)")

    def _disperse(self, world: World, traffic: Traffic, intents: Dict[int, Intent], busy: Set[int],
                  hazards: FrozenSet[int]) -> None:
        """One surplus unit per full objective hex steps into the objective's zone (it keeps denying the zone)."""
        cap = self.config.destination_cap
        waiting_paths: Set[int] = set()
        for w in traffic.waiting:
            waiting_paths.update(w.path)
        for o in world.objectives:
            if traffic.stand(o.hex) < cap:
                continue
            surplus = [u for u in world.units if u.hex == o.hex and not u.path and u.mobile_ground and u.can_move
                       and u.state in (State.SETTLED, State.TRANSITION) and u.obj_id not in busy
                       and u.obj_id not in intents]
            if not surplus:
                continue
            mover = min(surplus, key=lambda u: (-u.value, u.obj_id))
            mode = unit_mode(mover.type, mover.move_state)
            if mode is None:
                continue
            options = []
            for n in sorted(o.zone - {o.hex}):
                if n in waiting_paths or n in hazards or world.objective(n) is not None:
                    continue
                if n not in self.terrain.costs.neighbours(mode, o.hex) or n in world.roadblocks:
                    continue
                if traffic.stand(n) >= 2:
                    continue
                options.append((traffic.stand(n), n))
            if options:
                intents[mover.obj_id] = Intent("dispersal", M.RESERVE, min(options)[1],
                                               f"step off full objective {o.hex} into its zone")

    @staticmethod
    def _idle_reason(unit: Unit, busy: Set[int], world: World) -> Tuple[str, str, int, str]:
        if unit.obj_id in busy:
            return "transport", "lift", -1, "held for a lift in progress"
        if unit.path:
            return "none", "moving", unit.path[-1], f"executing a move ({unit.state.value})"
        if not unit.actions:
            return "none", "", -1, "no action listed"
        if unit.artillery:
            return "artillery", "", -1, "no indirect-fire target clear of own units"
        if unit.air:
            return "support", "", -1, "aircraft: no support target"
        if unit.state not in (State.SETTLED, State.TRANSITION):
            return "none", "", -1, f"in {unit.state.value}"
        return "reserve", M.RESERVE, unit.hex, "no slot worth its travel time; stays"

    def _trace(self, world: World, deployment: Optional[str], units, accepted, rejected, diagnostics) -> CommanderTrace:
        return CommanderTrace(
            policy=self.identity, step=world.step, stage=world.stage, seat=world.seat, faction=world.faction,
            deployment=deployment, units=tuple(units), excluded=world.excluded,
            emitted=tuple((int(a["type"]), a.get("obj_id")) for a in accepted),
            rejected=tuple(rejected), diagnostics=tuple(diagnostics), config=self.config.name)
