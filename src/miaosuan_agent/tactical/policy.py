"""The Sprint 36 tactical agent's decision cycle (``docs/SPRINT36_TACTICAL_RECOVERY.md`` sections 6 to 10).

Two architectures share the memory upkeep and the assessment (``tactical.assess``):

* ``stances`` (TA, TB): Sprint 35's coalition cycle (``coalition.policy.CoalitionPolicy._play``) with the Sprint 36
  assessment in place of Sprint 35's, the tactical allocator (``tactical.allocator``), and withdrawal to a safe hex as
  well as to a held objective. Steps: world view and memory upkeep (Sprint 35's, plus enemy posts and objective
  losses); lifts; traffic ledger, hazards, threat route costs; threats, pictures, assessment (kept defenders and
  withdrawing units leave the free pool); allocation; recovery and dispersal; arbitration (occupy > lift order >
  direct fire > guided fire > move > stay); indirect fire; validation; memory.
* ``guard`` (TC): Sprint 34's cycle (``integrated.policy.CommanderPolicy._play``) decides; then the survival guard reads
  the same assessment and (a) drops a move that takes a unit the assessment keeps in a held objective's zone out of
  that zone (retention: Sprint 34 lost 18 of 57 objectives after ordering the last defender away), (b) drops a move of a
  unit that is not cheap into the zone of an objective assessed ``delay`` or ``skip`` (untenable or not capturable)
  unless the unit is already in that zone, and (c) adds the assessment's withdrawal moves for units that have no action
  this step, each routed through a traffic ledger in which Sprint 34's own moves of the step are registered first.
  Every action is validated again. With the guard off the decision is Sprint 34's own.

Every unit keeps a recorded module and reason. Any exception other than a contract violation makes the decision
``baseline-v2``'s, recorded as a fallback (Sprint 34's rule).
"""

from __future__ import annotations

from dataclasses import fields, replace
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

from ..boundary import Observation
from ..coalition import capability as C
from ..coalition import coalition as K
from ..coalition.memory import updated_seen
from ..coalition.policy import WITHDRAW, CoalitionPolicy, _stance_rows
from ..coalition.support import guided_shots, support_fire
from ..coalition.validate import validate as coalition_validate
from ..decision import UnitDecision
from ..integrated import facts as F
from ..integrated import memory as M
from ..integrated import transport as T
from ..integrated.allocation import OWN, Assignment, known_enemies, support_targets
from ..integrated.fire import direct_fire, hazard_hexes, indirect_fire, threat_penalty
from ..integrated.policy import HOLD_FOR_BOARDING, CommanderPolicy, Intent
from ..integrated.traffic import Traffic
from ..integrated.validate import validate as base_validate
from ..integrated.world import State, Unit, World
from . import assess as A
from .allocator import TacticalAllocator
from .config import TacticalConfig
from .memory import TacticalMemory, canonical, updated_losses, updated_posts

CANDIDATE_PREFIX = "s36-tactical"
ENABLED = frozenset({F.MOVE, F.SHOOT, F.GET_ON, F.GET_OFF, F.OCCUPY, F.INDIRECT, F.END_DEPLOYMENT})
GUARD = "guard"


def candidate_id(config: TacticalConfig) -> str:
    return f"{CANDIDATE_PREFIX}-{config.name}-{config.revision}"


class TacticalPolicy(CoalitionPolicy):
    """``decide`` is a pure function of (observation, seat, faction, memory)."""

    def __init__(self, costs, config: TacticalConfig) -> None:
        super().__init__(costs, config.coalition)
        self.tactical = config
        self.identity = candidate_id(config)
        self.allocator = TacticalAllocator(config, self.terrain) if self.terrain is not None else None

    def decide(self, observation: Observation, seat: int, faction: int, memory: M.CommanderMemory):
        if not isinstance(memory, TacticalMemory):
            memory = TacticalMemory(**{f.name: getattr(memory, f.name) for f in fields(type(memory))
                                       if f.name in {g.name for g in fields(TacticalMemory)}})
        return super().decide(observation, seat, faction, memory)

    def _trace(self, world: World, deployment, units, accepted, rejected, diagnostics):
        trace = super()._trace(world, deployment, units, accepted, rejected, diagnostics)
        return replace(trace, policy=self.identity, config=self.tactical.name)

    def _fallback(self, observation, seat, faction, memory, reason):
        actions, trace, new_memory = super()._fallback(observation, seat, faction, memory, reason)
        return actions, replace(trace, policy=self.identity), new_memory

    # -- shared upkeep -----------------------------------------------------------------------------------------------
    def _upkeep(self, world: World, memory: TacticalMemory) -> TacticalMemory:
        co = self.coalition
        max_blood = C.enemy_max_blood(self._observation.operators() if self._observation is not None else (),
                                      world.faction)
        standing = [(e.obj_id, e.hex) for e in world.enemies if e.ground and not e.path]
        moving = [e.obj_id for e in world.enemies if e.ground and e.path]
        held_now = tuple(sorted(o.hex for o in world.objectives if o.flag == world.faction))
        return replace(memory,
                       seen=updated_seen(memory.seen, C.observed_rows(world, max_blood), world.step, co.sighting_ttl),
                       posts=updated_posts(memory.posts, standing, moving, world.step, co.sighting_ttl),
                       lost=updated_losses(memory.lost, memory.held, held_now, world.step), held=held_now)

    def _max_blood(self, world: World) -> Mapping[int, float]:
        return C.enemy_max_blood(self._observation.operators() if self._observation is not None else (), world.faction)

    def _play(self, world: World, memory: TacticalMemory):
        memory = self._upkeep(world, memory)
        if self.tactical.architecture == GUARD:
            return self._play_guarded(world, memory)
        return self._play_stances(world, memory)

    # -- TC: Sprint 34's decision under the survival guard --------------------------------------------------------
    def _play_guarded(self, world: World, memory: TacticalMemory):
        accepted, trace, new_memory = CommanderPolicy._play(self, world, memory)
        new_memory = canonical(replace(new_memory, seen=memory.seen, posts=memory.posts, lost=memory.lost,
                                       held=memory.held))
        trace = replace(trace, policy=self.identity, config=self.tactical.name)
        if not self.tactical.guard:
            return accepted, trace, new_memory
        tcfg = self.tactical
        cfg = self.config
        lift_step = T.step_lifts(world, memory.lifts, world.max_step - 3 * F.TRANSITION - 30)
        busy: Set[int] = set(lift_step.hold_still)
        free = [u for u in world.units
                if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)
                and u.obj_id not in busy]
        traffic = Traffic(world)
        pictures = self.allocator.pictures(world, known_enemies(world, memory), frozenset(u.obj_id for u in free))
        threat_list = C.threats(world, memory.seen, self._max_blood(world), self.coalition)
        assessments = A.assess(world, memory, self.allocator, tcfg, pictures, threat_list, free, traffic, self.terrain)
        untenable = {a.hex for a in assessments if a.stance in (K.DELAY, K.SKIP)}
        zone_of = {o.hex: o.zone for o in world.objectives}
        stance_of = {a.hex: a.stance for a in assessments}
        retained = {u: a.hex for a in assessments if a.stance in K.HELD_STANCES for u in a.keep}             if tcfg.retention else {}
        limit = A.cheap_limit(world, tcfg.cheap_share)
        kept: List[Dict[str, Any]] = []
        dropped: Dict[int, str] = {}
        for action in accepted:
            unit = world.unit(action.get("obj_id")) if action.get("type") == F.MOVE else None
            if unit is None or not unit.ground:
                kept.append(action)
                continue
            end = action["move_path"][-1]
            home = retained.get(unit.obj_id)
            if home is not None and end not in zone_of[home]:
                dropped[unit.obj_id] = f"guard: kept in the zone of {home} ({stance_of[home]})"
                continue
            if A.is_cheap(unit, limit):
                kept.append(action)
                continue
            target = next((h for h in untenable if end in zone_of[h] and unit.hex not in zone_of[h]), None)
            if target is not None:
                dropped[unit.obj_id] = f"guard: zone of {target} judged {stance_of[target]}"
                continue
            kept.append(action)
        for action in kept:
            if action.get("type") == F.MOVE:
                unit = world.unit(action["obj_id"])
                if unit is not None:
                    traffic.order(unit, tuple(action["move_path"]))
        acting = {a.get("obj_id") for a in kept}
        hazards = hazard_hexes(world, memory.fire_orders, world.rows, world.cols)
        threat_cost = threat_penalty(world, cfg, world.rows, world.cols)
        withdrawals: Dict[int, Tuple[int, str]] = {}
        added: List[Dict[str, Any]] = []
        if tcfg.withdrawal:
            for a in assessments:
                for unit_id, dest in a.withdraw:
                    unit = world.unit(unit_id)
                    if unit is None or unit_id in acting or unit_id in busy or unit.path or F.MOVE not in unit.actions:
                        continue
                    target = self._withdraw_target(world, traffic, dest, unit)
                    if target is None:
                        continue
                    path, why = self._route(world, unit, Intent(GUARD, WITHDRAW, target, ""), traffic, hazards,
                                            threat_cost)
                    if not path:
                        continue
                    traffic.order(unit, path)
                    added.append({"actor": world.seat, "type": F.MOVE, "obj_id": unit_id, "move_path": list(path)})
                    withdrawals[unit_id] = (target, f"guard: withdraw from {a.hex} toward {dest}")
                    acting.add(unit_id)
        if not dropped and not added:
            return accepted, replace(trace, stats=trace.stats + (("guard_dropped", 0), ("guard_withdrawals", 0)),
                                     diagnostics=tuple(trace.diagnostics) + _stance_rows(assessments)), new_memory
        verdict = base_validate(kept + added, world, self.terrain, ENABLED, False)
        final_ids = {a.get("obj_id") for a in verdict.accepted}
        plans = []
        for p in trace.plans:
            if p[0] in dropped:
                plans.append((p[0], GUARD, p[2], p[3], 0, dropped[p[0]]))
            elif p[0] in withdrawals and p[0] in final_ids:
                target, why = withdrawals[p[0]]
                plans.append((p[0], GUARD, WITHDRAW, target, F.MOVE, why))
            else:
                plans.append(p)
        decisions = []
        for d in trace.units:
            if d.obj_id in dropped:
                decisions.append(replace(d, rule=GUARD, action_type=None, no_op_reason=dropped[d.obj_id],
                                         validation="not applicable"))
            elif d.obj_id in withdrawals and d.obj_id in final_ids:
                decisions.append(replace(d, rule=GUARD, action_type=F.MOVE, no_op_reason=None, validation="accepted"))
            else:
                decisions.append(d)
        stats = trace.stats + (("guard_dropped", len(dropped)), ("guard_withdrawals",
                                                                  sum(1 for u in withdrawals if u in final_ids)))
        trace = replace(trace, units=tuple(decisions), plans=tuple(plans), stats=stats,
                        emitted=tuple((int(a["type"]), a.get("obj_id")) for a in verdict.accepted),
                        rejected=tuple(trace.rejected) + tuple(verdict.rejected),
                        diagnostics=tuple(trace.diagnostics) + _stance_rows(assessments))
        return verdict.accepted, trace, new_memory

    def _withdraw_target(self, world: World, traffic: Traffic, dest: int, unit: Unit) -> Optional[int]:
        if world.objective(dest) is not None:
            return self._stand_hex(world, traffic, dest, unit)
        return dest if traffic.stand(dest) < 2 else None

    # -- TA, TB: the stance cycle -----------------------------------------------------------------------------------
    def _play_stances(self, world: World, memory: TacticalMemory):
        cfg = self.config
        co = self.coalition
        terrain = self.terrain
        allocator: TacticalAllocator = self.allocator
        allocator.lost = {h: s for h, s in memory.lost}
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
        threat_cost = threat_penalty(world, cfg, world.rows, world.cols)

        # 4. threats, pictures, assessment
        free = [u for u in world.units
                if u.mobile_ground and u.can_move and u.state in (State.SETTLED, State.TRANSITION)
                and u.obj_id not in busy]
        free_ids = frozenset(u.obj_id for u in free)
        known = known_enemies(world, memory)
        pictures = allocator.pictures(world, known, free_ids)
        threat_list = C.threats(world, memory.seen, self._max_blood(world), co)
        assessments = A.assess(world, memory, allocator, self.tactical, pictures, threat_list, free, traffic, terrain)
        threats_kept = A.filtered_threats(world, memory, threat_list, self.tactical)
        enemy_held = frozenset(o.hex for o in world.objectives if o.flag == 1 - world.faction)
        assigned = C.attribute(threats_kept, [(o.hex, o.zone) for o in world.objectives], co, enemy_held)
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
        for unit_id, hex_ in kept.items():
            unit = world.unit(unit_id)
            if unit is not None:
                intents[unit_id] = Intent("coalition", M.HOLD, unit.hex, f"kept in the zone of {hex_}")
        for unit_id, dest in withdrawing.items():
            unit = world.unit(unit_id)
            if unit is None:
                continue
            stand = self._withdraw_target(world, traffic, dest, unit)
            if stand is not None:
                where = f"objective {dest}" if world.objective(dest) is not None else "a safe hex"
                intents[unit_id] = Intent("coalition", WITHDRAW, stand, f"withdraw toward {where}")
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
                target, reason = (intent.target if intent else -1), ("embark" if action["type"] == F.GET_ON
                                                                     else "disembark")
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
                    module, kind, target, reason = intent.module, intent.kind, intent.target, \
                        f"{intent.reason}; held: {why}"
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
            stands = set(h for h, n in traffic.inbound.items() if n > 0) | set(h for h, n in traffic.staying.items()
                                                                                if n > 0)
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
        verdict = coalition_validate(proposals, world, terrain, ENABLED, False, co.guided_fire)
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
                 ("threats_after_filter", len(threats_kept)),
                 *(("stance_" + k, v) for k, v in sorted(stance_counts.items())))
        trace = self._trace(world, None, tuple(decisions), accepted, verdict.rejected, _stance_rows(assessments))
        trace = replace(trace, plans=tuple(plans), stats=stats, lift_notes=lift_step.notes)
        return accepted, trace, new_memory


__all__ = ["TacticalPolicy", "candidate_id", "CANDIDATE_PREFIX"]
