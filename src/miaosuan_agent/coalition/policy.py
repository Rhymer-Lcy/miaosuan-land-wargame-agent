"""The coalition agent's decision cycle (``docs/SPRINT35_COALITION_AGENT.md`` section 7).

Sprint 34's cycle (``integrated.policy``) with the objective stances inserted before the allocation:

1. world view and memory upkeep (Sprint 34's, plus class-aware sightings with strength);
2. lift life cycle (Sprint 34's ``integrated.transport``);
3. traffic ledger, hazards and threat route costs (Sprint 34's);
4. known threats with confidence, objective pictures, **stances** (``coalition.assess``): kept defenders and withdrawing
   units leave the free pool; withdrawing units get a move to their destination objective's zone;
5. allocation over the stance places (``allocator.CoalitionAllocator``); a reinforcement or reserve unit is routed to a
   stand hex in the objective's zone (the objective hex while it has room, else the zone hex with the fewest planned
   own units), so that defenders spread over the zone instead of crowding one hex;
6. recovery and dispersal (Sprint 34's);
7. per-unit arbitration in ascending id: occupy > lift order > direct fire > guided fire (variant B) > move > stay;
8. indirect fire: Sprint 34's guarded rule, or (variant B) ``support.support_fire``;
9. independent validation (``coalition.validate``), memory (stances, sightings).

Every unit gets a recorded module and reason. Any exception other than a contract violation makes the decision
``baseline-v2``'s, recorded as a fallback, as in Sprint 34.
"""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import ContractError, MoveCosts, Observation, Stage, deployment_completion_available
from ..decision import Memory, UnitDecision
from ..decision.trace import StepTrace
from ..experiments.shoot_reservation import ShootReservationPolicy
from ..integrated import facts as F
from ..integrated import memory as M
from ..integrated import transport as T
from ..integrated.allocation import OWN, Assignment, known_enemies, support_targets
from ..integrated.fire import direct_fire, hazard_hexes, indirect_fire, threat_penalty
from ..integrated.movement import Terrain, unit_mode
from ..integrated.policy import HOLD_FOR_BOARDING, CommanderPolicy, CommanderTrace, Intent
from ..integrated.traffic import Traffic
from ..integrated.world import State, Unit, World, build_world
from . import capability as C
from . import coalition as K
from .allocator import CoalitionAllocator
from .config import CoalitionConfig
from .memory import CoalitionMemory, canonical, updated_seen
from .support import guided_shots, support_fire
from .validate import validate

CANDIDATE_PREFIX = "s35-coalition"
ENABLED = frozenset({F.MOVE, F.SHOOT, F.GET_ON, F.GET_OFF, F.OCCUPY, F.INDIRECT, F.END_DEPLOYMENT})
WITHDRAW = "withdraw"


def candidate_id(config: CoalitionConfig) -> str:
    return f"{CANDIDATE_PREFIX}-{config.name}-{config.revision}"


def _stance_rows(assessments: Sequence[K.Assessment]) -> Tuple[str, ...]:
    rows = []
    for a in assessments:
        rows.append(f"objective {a.hex}: {a.stance} threat {a.threat:.3f} (visible {a.visible_threat:.3f}) "
                    f"eta {'none' if a.enemy_eta == float('inf') else int(a.enemy_eta)} defence {a.defence:.3f} "
                    f"want {a.requirement:.3f} places {a.places} keep {list(a.keep)} withdraw {list(a.withdraw)}: "
                    f"{a.note}")
    return tuple(rows)


class CoalitionPolicy(CommanderPolicy):
    """``decide`` is a pure function of (observation, seat, faction, memory)."""

    def __init__(self, costs: Optional[MoveCosts], config: CoalitionConfig) -> None:
        super().__init__(costs, config.base)
        self.coalition = config
        self.identity = candidate_id(config)
        self.allocator = CoalitionAllocator(config, self.terrain) if self.terrain is not None else None
        self._observation: Optional[Observation] = None

    def decide(self, observation: Observation, seat: int, faction: int, memory: M.CommanderMemory):
        if not isinstance(memory, CoalitionMemory):
            memory = CoalitionMemory(**{f.name: getattr(memory, f.name) for f in fields(M.CommanderMemory)})
        self._observation = observation
        try:
            return super().decide(observation, seat, faction, memory)
        finally:
            self._observation = None

    def _fallback(self, observation, seat, faction, memory, reason):
        actions, trace, new_memory = super()._fallback(observation, seat, faction, memory, reason)
        return actions, replace(trace, policy=self.identity), new_memory

    def _trace(self, world: World, deployment, units, accepted, rejected, diagnostics) -> CommanderTrace:
        trace = super()._trace(world, deployment, units, accepted, rejected, diagnostics)
        return replace(trace, policy=self.identity, config=self.coalition.name)

    # -- play ------------------------------------------------------------------------------------
    def _play(self, world: World, memory: CoalitionMemory):
        cfg = self.config
        co = self.coalition
        terrain = self.terrain
        allocator: CoalitionAllocator = self.allocator
        present = {u.obj_id for u in world.units} | {p.obj_id for p in world.passengers}
        max_blood = C.enemy_max_blood(self._observation.operators() if self._observation is not None else (),
                                      world.faction)
        sightings = M.updated_sightings(memory.sightings,
                                        [(e.obj_id, e.hex, e.type, int(e.value)) for e in world.enemies], world.step)
        seen = updated_seen(memory.seen, C.observed_rows(world, max_blood), world.step, co.sighting_ttl)
        owned = [o.hex for o in world.objectives if o.flag == world.faction]
        memory = replace(memory, sightings=sightings, seen=seen,
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
        threat_cost = threat_penalty(world, cfg, world.rows, world.cols)

        # 4. threats, pictures, stances
        free = [u for u in world.units
                if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)
                and u.obj_id not in busy]
        free_ids = frozenset(u.obj_id for u in free)
        known = known_enemies(world, memory)
        pictures = allocator.pictures(world, known, free_ids)
        threat_list = C.threats(world, memory.seen, max_blood, co)
        assessments = K.assess(world, memory, allocator, co, pictures, threat_list, free)
        enemy_held = frozenset(o.hex for o in world.objectives if o.flag == 1 - world.faction)
        assigned = C.attribute(threat_list, [(o.hex, o.zone) for o in world.objectives], co, enemy_held)
        threat_members = {hex_: C.zone_threat(rows).members for hex_, rows in assigned.items()}
        kept: Dict[int, int] = {}
        withdrawing: Dict[int, int] = {}
        for a in assessments:
            for unit_id in a.keep:
                kept.setdefault(unit_id, a.hex)
            for unit_id, dest in a.withdraw:
                withdrawing.setdefault(unit_id, dest)
        pool = [u for u in free if u.obj_id not in kept and u.obj_id not in withdrawing]
        pool_ids = frozenset(u.obj_id for u in pool)

        anchored = set()
        for unit_id, kind, target, _ in memory.tasks:
            unit = world.unit(unit_id)
            if kind in (M.HOLD, M.CAPTURE) and unit is not None and unit.hex == target and world.objective(target):
                anchored.add(unit_id)
        for unit_id, action_type, step in memory.orders:
            if action_type == F.GET_ON and world.step - step < cfg.lift_cooldown:
                anchored.add(unit_id)
        lift_candidates = (T.candidates(world, sorted(pool_ids - anchored), sorted(busy)) if cfg.transport else [])
        delivered = dict(lift_step.delivered)
        loaded = [(p, world.unit(c), o) for p, c, o in lift_step.loaded if world.unit(c) is not None]
        assignments = allocator.allocate_places(world, memory, pool, pictures, assessments, lift_candidates, loaded)
        by_unit: Dict[int, Assignment] = {}
        for a in assignments:
            for member in (a.members or (a.unit,)):
                by_unit[member] = a
        support = support_targets(world, pictures, assignments)

        intents: Dict[int, Intent] = {}
        new_lifts: List[M.Lift] = []
        lift_orders: Dict[int, dict] = {}
        for unit_id, action in lift_step.orders:
            carrier = world.unit(unit_id)
            if carrier is not None and traffic.present.get(carrier.hex, 0) >= F.STACK_LIMIT:
                continue
            lift_orders[unit_id] = action
        for carrier_id, objective in lift_step.carry_moves:
            intents[carrier_id] = Intent("transport", M.CARRY, objective, "carry passenger to objective")
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
        # kept defenders stay; withdrawing units leave for their destination's zone
        for unit_id, hex_ in kept.items():
            unit = world.unit(unit_id)
            if unit is not None:
                intents[unit_id] = Intent("coalition", M.HOLD, unit.hex, f"kept in the zone of {hex_}")
        for unit_id, dest in withdrawing.items():
            unit = world.unit(unit_id)
            if unit is None:
                continue
            stand = self._stand_hex(world, traffic, dest, unit)
            if stand is not None:
                intents[unit_id] = Intent("coalition", WITHDRAW, stand, f"withdraw toward {dest}")
        for a in assignments:
            if a.kind == M.CARRY:
                continue
            if a.kind == M.RIDE:
                infantry_id, carrier_id = a.members
                lift_orders[infantry_id] = {"type": F.GET_ON, "obj_id": infantry_id, "target_obj_id": carrier_id}
                new_lifts.append((infantry_id, carrier_id, a.target, M.BOARDING, world.step))
                busy.update(a.members)
                intents[infantry_id] = Intent("transport", M.RIDE, a.target, a.reason)
                intents[carrier_id] = Intent("transport", HOLD_FOR_BOARDING, a.target, "hold still while the passenger boards")
                continue
            unit = world.unit(a.unit)
            if unit is None:
                continue
            target = a.target
            module = "allocation"
            if not a.reason.startswith("base"):
                module = "coalition"
                zone = world.objective(a.target).zone if world.objective(a.target) else frozenset()
                if unit.hex in zone:
                    target = unit.hex
                else:
                    stand = self._stand_hex(world, traffic, a.target, unit)
                    target = stand if stand is not None else a.target
            verb = "stay" if unit.hex == target else "move"
            intents[a.unit] = Intent(module, a.kind, target, f"{a.reason}: {verb}")
        for unit_id, target in support.items():
            intents.setdefault(unit_id, Intent("support", M.SUPPORT, target, "aircraft support"))

        # 6. recovery and dispersal
        if cfg.recovery:
            self._recovery(world, traffic, intents, by_unit, busy, pictures)
        if cfg.dispersal:
            self._disperse(world, traffic, intents, busy, hazards)

        # 7. arbitration
        fire = direct_fire(world, cfg, world.units)
        guided: Dict[int, Tuple[int, int, int, int]] = {}
        if co.guided_fire:
            shooting = frozenset(u for u in fire if u not in busy)
            reserved = {shot[0] for u, shot in fire.items() if u not in busy}
            acting = frozenset(shooting | set(lift_orders) | busy)
            guided = guided_shots(world, acting, reserved)
        guided_carriers = {shot[2] for shot in guided.values()}
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
            elif unit.obj_id in guided:
                shot = guided[unit.obj_id]
                action = {"type": F.GUIDED, "obj_id": unit.obj_id, "target_obj_id": shot[0], "weapon_id": shot[1],
                          "guided_obj_id": shot[2]}
                module, kind, target, reason = "guided", "guided shot", -1, f"attack level {shot[3]}"
            elif unit.obj_id in guided_carriers:
                module, kind, target, reason = "guided", "carrier", -1, "carrier of a guided shot this step"
            elif intent is not None and intent.kind not in (M.RIDE, HOLD_FOR_BOARDING) and unit.hex != intent.target \
                    and F.MOVE in unit.actions and not unit.path \
                    and (unit.obj_id not in busy or (intent.module == "transport" and intent.kind == M.CARRY)):
                path, why = self._route(world, unit, intent, traffic, hazards, threat_cost)
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

        # 8. indirect fire
        artillery_orders = 0
        if cfg.artillery:
            stands = set(h for h, n in traffic.inbound.items() if n > 0) | set(h for h, n in traffic.staying.items() if n > 0)
            acted = {a["obj_id"] for a in proposals} | guided_carriers
            if co.fire_support or co.arrival_fire:
                orders = support_fire(world, co, stands, memory.fire_orders, assessments, threat_members)
            else:
                orders = [(u, h, w, "indirect fire clear of own units") for u, h, w in
                          indirect_fire(world, cfg, stands, memory.fire_orders)]
            for unit_id, hex_, weapon, why in orders:
                if unit_id in acted:
                    continue
                proposals.append({"actor": world.seat, "type": F.INDIRECT, "obj_id": unit_id, "jm_pos": hex_,
                                  "weapon_id": weapon})
                artillery_orders += 1
                fired = (unit_id, "artillery", "indirect", hex_, F.INDIRECT, why)
                plans = [fired if p[0] == unit_id else p for p in plans]
                decisions = [replace(d, rule="artillery", action_type=F.INDIRECT, no_op_reason=None)
                             if d.obj_id == unit_id else d for d in decisions]

        # 9. validation and memory
        verdict = validate(proposals, world, terrain, ENABLED, False, co.guided_fire)
        rejected_units = {r[1] for r in verdict.rejected}
        decisions = [replace(d, validation=("rejected: " + next(r[2] for r in verdict.rejected if r[1] == d.obj_id))
                             if d.obj_id in rejected_units else "accepted" if d.action_type is not None
                             else "not applicable") for d in decisions]
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
        orders_mem = {o[0]: o for o in memory.orders}
        fire_orders = list(memory.fire_orders)
        for a in accepted:
            if "obj_id" in a:
                orders_mem[a["obj_id"]] = (a["obj_id"], int(a["type"]), world.step)
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
        new_memory = canonical(replace(memory, tasks=tuple(tasks.values()), lifts=tuple(lifts),
                                       orders=tuple(orders_mem.values()), fire_orders=tuple(fire_orders),
                                       stances=K.stances_for_memory(assessments, memory, world.step)))
        stance_counts: Dict[str, int] = {}
        for a in assessments:
            stance_counts[a.stance] = stance_counts.get(a.stance, 0) + 1
        stats = (("free", len(free)), ("pool", len(pool)), ("kept", len(kept)), ("withdrawing", len(withdrawing)),
                 ("assignments", len(assignments)), ("lift_candidates", len(lift_candidates)),
                 ("lifts", len(new_memory.lifts)), ("recovery_moves", recovery_moves), ("held_moves", blocked_moves),
                 ("artillery_orders", artillery_orders), ("guided_shots", len(guided)),
                 ("waiting_units", len(traffic.waiting)), ("known_enemies", len(threat_list)),
                 *(("stance_" + k, v) for k, v in sorted(stance_counts.items())))
        trace = self._trace(world, None, tuple(decisions), accepted, verdict.rejected, _stance_rows(assessments))
        trace = replace(trace, plans=tuple(plans), stats=stats, lift_notes=lift_step.notes)
        return accepted, trace, new_memory

    # -- helpers ---------------------------------------------------------------------------------
    def _stand_hex(self, world: World, traffic: Traffic, objective_hex: int, unit: Unit) -> Optional[int]:
        """Where a reinforcing or withdrawing unit should stand in ``objective_hex``'s zone: the objective hex while its
        planned stand is below the destination cap, else the zone hex (passable for the unit's mode, no roadblock, not
        another objective) with the fewest planned own units, then the lowest free-flow cost from the unit, then hex."""
        objective = world.objective(objective_hex)
        if objective is None:
            return None
        if traffic.accepts(objective_hex, self.config.destination_cap):
            return objective_hex
        mode = unit_mode(unit.type, unit.move_state)
        if mode is None:
            return None
        options = []
        for h in sorted(objective.zone - {objective_hex}):
            if world.objective(h) is not None or h in world.roadblocks:
                continue
            if traffic.stand(h) >= 2:
                continue
            cost = self.terrain.cost_to(mode, unit.hex, h, world.roadblocks)
            if cost is None and unit.hex != h:
                continue
            options.append((traffic.stand(h), cost or 0.0, h))
        return min(options)[2] if options else None
