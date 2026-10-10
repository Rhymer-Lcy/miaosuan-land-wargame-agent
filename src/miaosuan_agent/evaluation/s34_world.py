"""Sprint 34 MODEL WORLD: a deterministic stand-in engine on real SDK map and scenario data (offline only).

It is a model, not the engine: nothing it produces is engine evidence, and no score it computes is a prediction of a
game's outcome. It exists to run whole policies end to end, offline, on every validated scenario: legality of every
action against the listings it generates, determinism, latency, assignment and route behaviour, stacking-limit
blocks, transport, and the movement race to the objectives. It has **no combat damage**: shots are listed and echoed
but change nothing, and indirect fire records an impact point but damages nothing.

Rules (each from an engine fact recorded in ``docs/TACTICAL_FRONTIER.md`` or measured in Sprint 34, section 3):

* time: deployment until both seats send 333 (``cur_step`` stays 0), then one step per call to ``max_step``;
* movement: a unit with a path needs ``hex_time = round(720 / basic_speed * cost)`` steps to enter its next hex;
  ``speed = 1 / hex_time``, ``cur_pos`` the fraction done; a ground unit whose next hex holds four own ground units
  waits with speed 0 and restarts with a full hex time; units are processed in ascending id with occupancy updated
  after each entry; entering the last hex empties the path and starts the 75-step transition (``stop`` 0, then 1);
* listings: move for units without a path and no embark/disembark timer (never for artillery); stop while a path is
  set; occupation for a ground non-artillery unit on an objective its side does not hold with no enemy ground unit in
  the zone (also during the transition); embark for a settled infantry or unmanned ground vehicle sharing a hex with
  a settled carrier; disembark for a settled carrier with passengers; indirect fire for artillery with its weapon
  cooled (299 steps after an order); a shot at a visible enemy within the published range for a stationary unit not
  in transition (tanks also while moving) with its weapon cooled (75 steps after a shot);
* visibility: an enemy is visible when an own unit not aboard is within 10 hexes of an infantry target or 25 of a
  vehicle (2 for unmanned aerial vehicles and loitering munitions); line of sight is not modelled; enemy relation
  fields are masked;
* embark completes 75 steps after the order (the passenger leaves the map and joins the carrier); disembark 75 steps
  after the order (the passenger on the carrier's hex, settled);
* occupation sets the objective's flag at once.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from ..boundary import MoveCosts, MoveMode
from ..decision.routing import ROADBLOCKED_MODES, move_mode
from ..integrated import facts as F

SEATS = {0: 1, 1: 11}
SHOT_COOL = 75
INDIRECT_COOL = 299
MASKED = ("launcher", "passenger_ids", "launch_ids", "see_enemy_bop_ids", "car", "get_on_partner_id",
          "get_off_partner_id")


class ModelWorld:
    def __init__(self, scenario: Mapping[str, Any], costs: MoveCosts, max_step: Optional[int] = None,
                 terrain_id: Optional[int] = None) -> None:
        self.scenario = scenario
        self.costs = costs
        self.terrain_id = terrain_id
        self.max_step = int(max_step or scenario["time"]["max_time"])
        self.stage, self.cur_step = 1, 0
        self.ended = {0: False, 1: False}
        self.units: Dict[int, Dict[str, Any]] = {}
        self.aboard: Dict[int, Dict[str, Any]] = {}
        for raw in scenario["operators"]:
            unit = copy.deepcopy(raw)
            unit.setdefault("move_path", [])
            unit["move_path"] = list(unit.get("move_path") or [])
            for key, default in (("speed", 0), ("cur_pos", 0), ("move_to_stop_remain_time", 0), ("stop", 1),
                                 ("get_on_remain_time", 0), ("get_off_remain_time", 0), ("weapon_cool_time", 0),
                                 ("change_state_remain_time", 0), ("passenger_ids", []), ("flag_force_stop", 0)):
                if unit.get(key) is None:
                    unit[key] = copy.deepcopy(default)
            unit["_progress"] = 0
            if unit.get("on_board"):
                self.aboard[unit["obj_id"]] = unit
            else:
                self.units[unit["obj_id"]] = unit
        for unit in list(self.aboard.values()):
            carrier = self.units.get(unit.get("car"))
            if carrier is not None and unit["obj_id"] not in carrier["passenger_ids"]:
                carrier["passenger_ids"].append(unit["obj_id"])
        self.cities = [dict(c) for c in scenario["cities"]]
        self.echo: List[Dict[str, Any]] = []
        self.refused: List[Dict[str, Any]] = []
        self.jm_points: List[Dict[str, Any]] = []
        self.pending: List[Tuple[int, str, int, int]] = []   # (due step, kind, unit, partner)
        self.first_owner: Dict[int, Tuple[int, int]] = {}
        self.wait_steps: Dict[int, int] = {}
        self.max_wait: Dict[int, int] = {}
        self.events: List[Tuple[int, str, int, int]] = []
        self.friendly_exposure: Dict[int, int] = {}

    # -- helpers ---------------------------------------------------------------------------------
    @staticmethod
    def ground(unit: Mapping[str, Any]) -> bool:
        return unit.get("type") in F.GROUND

    @staticmethod
    def artillery(unit: Mapping[str, Any]) -> bool:
        return unit.get("type") == F.VEHICLE and unit.get("sub_type") == F.ARTILLERY

    def occupancy(self, color: int, hex_: int) -> int:
        return sum(1 for u in self.units.values() if u["color"] == color and self.ground(u) and u["cur_hex"] == hex_)

    def zone_has_enemy(self, color: int, hex_: int) -> bool:
        zone = F.zone(hex_, self.costs.rows, self.costs.cols)
        return any(u["color"] != color and self.ground(u) and u["cur_hex"] in zone for u in self.units.values())

    def room(self, carrier: Mapping[str, Any], sub_type: Any) -> bool:
        """Whether ``carrier`` has a free place for a passenger of ``sub_type`` (``max_passenger_nums`` by sub_type)."""
        limits = carrier.get("max_passenger_nums") or {}
        limit = limits.get(str(sub_type), limits.get(sub_type, 0))
        aboard = sum(1 for p in carrier["passenger_ids"] if (self.aboard.get(p) or {}).get("sub_type") == sub_type)
        return F.is_int(limit) and aboard < limit

    def settled(self, unit: Mapping[str, Any]) -> bool:
        return (not unit["move_path"] and unit["move_to_stop_remain_time"] <= 0 and unit["get_on_remain_time"] <= 0
                and unit["get_off_remain_time"] <= 0)

    def hex_time(self, unit: Mapping[str, Any], frm: int, to: int) -> Optional[int]:
        mode = move_mode(unit["type"], unit.get("move_state"))
        if mode is None:
            return None
        return F.hex_time(unit.get("basic_speed"), self.costs.neighbours(mode, frm).get(to))

    def visible(self, color: int) -> List[Dict[str, Any]]:
        observers = [u for u in self.units.values() if u["color"] == color]
        seen = []
        for e in self.units.values():
            if e["color"] == color:
                continue
            for o in observers:
                if (o.get("type"), o.get("sub_type")) in ((F.AIRCRAFT, F.UAV), (F.AIRCRAFT, F.LOITERING)):
                    reach = 2
                elif e.get("type") == F.INFANTRY:
                    reach = 10
                else:
                    reach = 25
                if F.hex_distance(o["cur_hex"], e["cur_hex"]) <= reach:
                    seen.append(e)
                    break
        return seen

    # -- listings --------------------------------------------------------------------------------
    def listing(self, unit: Dict[str, Any], visible: Sequence[Mapping[str, Any]]) -> Dict[int, Any]:
        acts: Dict[int, Any] = {}
        color = unit["color"]
        if unit["move_path"]:
            acts[F.STOP] = None
        busy = unit["get_on_remain_time"] > 0 or unit["get_off_remain_time"] > 0
        if not unit["move_path"] and not busy and not self.artillery(unit) and (unit.get("basic_speed") or 0) > 0:
            acts[F.MOVE] = None
        if self.artillery(unit) and unit["weapon_cool_time"] <= 0:
            weapons = [w for w in unit.get("carry_weapon_ids") or [] if F.is_int(w)]
            if weapons:
                acts[F.INDIRECT] = [{"weapon_id": w} for w in sorted(weapons)[:1]]
        if (self.ground(unit) and not self.artillery(unit) and not unit["move_path"] and not busy
                and any(c["coord"] == unit["cur_hex"] and c["flag"] != color for c in self.cities)
                and not self.zone_has_enemy(color, unit["cur_hex"])):
            acts[F.OCCUPY] = None
        if unit.get("type") == F.INFANTRY or (unit.get("type") == F.VEHICLE and unit.get("sub_type") == F.UGV):
            if self.settled(unit):
                cars = [c for c in self.units.values() if c["color"] == color and c["cur_hex"] == unit["cur_hex"]
                        and c["obj_id"] != unit["obj_id"] and self.settled(c)
                        and unit.get("sub_type") in (c.get("valid_passenger_types") or [])
                        and self.room(c, unit.get("sub_type"))]
                if cars:
                    acts[F.GET_ON] = [{"target_obj_id": c["obj_id"]} for c in sorted(cars, key=lambda c: c["obj_id"])]
        if unit["passenger_ids"] and self.settled(unit):
            acts[F.GET_OFF] = [{"target_obj_id": p} for p in sorted(unit["passenger_ids"])]
        moving_tank = unit["move_path"] and unit.get("type") == F.VEHICLE and unit.get("sub_type") == F.TANK
        stationary = not unit["move_path"] and unit["move_to_stop_remain_time"] <= 0 and not busy
        if (stationary or moving_tank) and unit["weapon_cool_time"] <= 0 and not self.artillery(unit):
            options = []
            for e in visible:
                reach = F.weapon_range(unit.get("carry_weapon_ids") or [], e.get("type"))
                if reach and F.hex_distance(unit["cur_hex"], e["cur_hex"]) <= reach:
                    for w in sorted(unit.get("carry_weapon_ids") or []):
                        if F.weapon_range([w], e.get("type")):
                            options.append({"target_obj_id": e["obj_id"], "weapon_id": w, "attack_level": 5})
            if options:
                acts[F.SHOOT] = options
        return acts

    # -- observations ------------------------------------------------------------------------------
    def observation(self, color: int) -> Dict[str, Any]:
        visible = self.visible(color)
        operators = []
        for u in sorted(self.units.values(), key=lambda u: u["obj_id"]):
            if u["color"] == color:
                operators.append({k: copy.deepcopy(v) for k, v in u.items() if not k.startswith("_")})
        for e in sorted(visible, key=lambda u: u["obj_id"]):
            record = {k: copy.deepcopy(v) for k, v in e.items() if not k.startswith("_")}
            for k in MASKED:
                if k in record:
                    record[k] = [] if isinstance(record[k], list) else None
            operators.append(record)
        passengers = [{k: copy.deepcopy(v) for k, v in u.items() if not k.startswith("_")}
                      for u in sorted(self.aboard.values(), key=lambda u: u["obj_id"]) if u["color"] == color]
        valid = {}
        if self.stage == 2:
            for u in self.units.values():
                if u["color"] == color:
                    acts = self.listing(u, visible)
                    if acts:
                        valid[u["obj_id"]] = acts
        seat = SEATS[color]
        own_ids = sorted([u["obj_id"] for u in self.units.values() if u["color"] == color]
                         + [u["obj_id"] for u in self.aboard.values() if u["color"] == color])
        extra = {} if self.terrain_id is None else {"terrain_id": int(self.terrain_id)}
        return {**extra,
            "time": {"cur_step": self.cur_step, "stage": self.stage, "tick": 1.0, "max_time": self.max_step,
                     "max_step": self.max_step},
            "operators": operators, "passengers": passengers, "valid_actions": valid,
            "role_and_grouping_info": {seat: {"faction": color, "role": 1, "operators": own_ids, "user_id": 0,
                                              "user_name": "model", "end_deployment": self.ended[color]}},
            "cities": [dict(c) for c in self.cities], "communication": [], "judge_info": [],
            "jm_points": [dict(p) for p in self.jm_points], "scores": self.scores(),
            "landmarks": {"roadblocks": [], "minefields": [], "fortifications": []},
            "scenario_id": int(self.scenario.get("scenario_id")),
        }

    def scores(self) -> Dict[str, int]:
        occupy = {0: 0, 1: 0}
        for c in self.cities:
            if c["flag"] in occupy:
                occupy[c["flag"]] += int(c.get("value") or 0)
        return {"red_occupy": occupy[0], "blue_occupy": occupy[1]}

    # -- step --------------------------------------------------------------------------------------
    def refuse(self, action: Mapping[str, Any], reason: str) -> None:
        self.refused.append({"step": self.cur_step, "action": dict(action), "reason": reason})

    def apply(self, color: int, action: Mapping[str, Any], listed: Mapping[int, Dict[int, Any]]) -> None:
        kind = action.get("type")
        if kind == F.END_DEPLOYMENT:
            if self.stage == 1:
                self.ended[color] = True
            return
        if self.stage != 2:
            self.refuse(action, "not in play")
            return
        unit = self.units.get(action.get("obj_id"))
        if unit is None or unit["color"] != color:
            self.refuse(action, "unknown or foreign unit")
            return
        acts = listed.get(unit["obj_id"], {})
        if kind not in acts:
            self.refuse(action, f"type {kind} not listed")
            return
        if kind == F.MOVE:
            path = action.get("move_path") or []
            mode = move_mode(unit["type"], unit.get("move_state"))
            here = unit["cur_hex"]
            for h in path:
                if h not in self.costs.neighbours(mode, here):
                    self.refuse(action, "bad path")
                    return
                here = h
            unit["move_path"] = list(path)
            unit["_progress"] = 0
            unit["move_to_stop_remain_time"] = 0
            unit["stop"] = 0
        elif kind == F.OCCUPY:
            for c in self.cities:
                if c["coord"] == unit["cur_hex"]:
                    c["flag"] = color
                    self.first_owner.setdefault(c["coord"], (color, self.cur_step))
                    self.events.append((self.cur_step, "occupy", color, c["coord"]))
        elif kind == F.GET_ON:
            target = action.get("target_obj_id")
            if {"target_obj_id": target} not in (acts.get(F.GET_ON) or []):
                self.refuse(action, "carrier not listed")
                return
            unit["get_on_remain_time"] = F.TRANSITION
            self.pending.append((self.cur_step + F.TRANSITION, "on", unit["obj_id"], target))
        elif kind == F.GET_OFF:
            target = action.get("target_obj_id")
            if target not in unit["passenger_ids"]:
                self.refuse(action, "passenger not aboard")
                return
            unit["get_off_remain_time"] = F.TRANSITION
            self.pending.append((self.cur_step + F.TRANSITION, "off", unit["obj_id"], target))
        elif kind == F.SHOOT:
            unit["weapon_cool_time"] = SHOT_COOL
            self.events.append((self.cur_step, "shot", color, unit["obj_id"]))
        elif kind == F.INDIRECT:
            unit["weapon_cool_time"] = INDIRECT_COOL
            self.jm_points.append({"obj_id": unit["obj_id"], "weapon_id": action.get("weapon_id"),
                                   "pos": action.get("jm_pos"), "status": 0, "fly_time": 150, "boom_time": 300})
            self.events.append((self.cur_step, "indirect", color, int(action.get("jm_pos") or -1)))
        self.echo.append({"cur_step": self.cur_step, "message": dict(action)})

    def step(self, actions_by_color: Mapping[int, Sequence[Mapping[str, Any]]]) -> bool:
        listed = {}
        if self.stage == 2:
            for color in (0, 1):
                visible = self.visible(color)
                listed[color] = {u["obj_id"]: self.listing(u, visible) for u in self.units.values() if u["color"] == color}
        self.echo = []
        for color in (0, 1):
            seen = set()
            for action in actions_by_color.get(color, ()):
                if action.get("obj_id") in seen:
                    self.refuse(action, "second action for a unit")
                    continue
                if "obj_id" in action:
                    seen.add(action["obj_id"])
                self.apply(color, action, listed.get(color, {}))
        if self.stage == 1:
            if all(self.ended.values()):
                self.stage = 2
            return False
        self._advance()
        self.cur_step += 1
        return self.cur_step >= self.max_step

    def _advance(self) -> None:
        for unit in sorted(self.units.values(), key=lambda u: u["obj_id"]):
            for key in ("weapon_cool_time", "get_on_remain_time", "get_off_remain_time"):
                if unit[key] > 0:
                    unit[key] -= 1
            if unit["move_to_stop_remain_time"] > 0:
                unit["move_to_stop_remain_time"] -= 1
                if unit["move_to_stop_remain_time"] == 0:
                    unit["stop"] = 1
            if not unit["move_path"]:
                unit["speed"], unit["cur_pos"] = 0, 0
                continue
            nxt = unit["move_path"][0]
            tau = self.hex_time(unit, unit["cur_hex"], nxt) or 10 ** 6
            if self.ground(unit) and self.occupancy(unit["color"], nxt) >= F.STACK_LIMIT:
                unit["speed"], unit["_progress"], unit["cur_pos"] = 0, 0, 0
                self.wait_steps[unit["obj_id"]] = self.wait_steps.get(unit["obj_id"], 0) + 1
                unit["_waited"] = unit.get("_waited", 0) + 1
                self.max_wait[unit["obj_id"]] = max(self.max_wait.get(unit["obj_id"], 0), unit["_waited"])
                continue
            unit["_waited"] = 0
            unit["_progress"] += 1
            unit["speed"] = 1.0 / tau
            if unit["_progress"] >= tau:
                unit["cur_hex"] = nxt
                unit["move_path"].pop(0)
                unit["_progress"] = 0
                if not unit["move_path"]:
                    unit["speed"], unit["cur_pos"] = 0, 0
                    unit["move_to_stop_remain_time"] = F.TRANSITION
                    unit["stop"] = 0
                    continue
                tau = self.hex_time(unit, unit["cur_hex"], unit["move_path"][0]) or 10 ** 6
            unit["cur_pos"] = unit["_progress"] / tau
        due = sorted(p for p in self.pending if p[0] <= self.cur_step + 1)
        self.pending = [p for p in self.pending if p[0] > self.cur_step + 1]
        for _, kind, unit_id, partner in due:
            if kind == "on":
                unit, carrier = self.units.get(unit_id), self.units.get(partner)
                if unit is None or carrier is None or unit["cur_hex"] != carrier["cur_hex"]:
                    continue
                del self.units[unit_id]
                unit["on_board"], unit["car"] = 1, partner
                self.aboard[unit_id] = unit
                carrier["passenger_ids"].append(unit_id)
                self.events.append((self.cur_step, "embarked", unit["color"], unit_id))
            else:
                carrier, unit = self.units.get(unit_id), self.aboard.get(partner)
                if carrier is None or unit is None:
                    continue
                del self.aboard[partner]
                carrier["passenger_ids"].remove(partner)
                unit.update(on_board=0, car=None, cur_hex=carrier["cur_hex"], move_path=[], stop=1, speed=0,
                            move_to_stop_remain_time=0)
                self.units[partner] = unit
                self.events.append((self.cur_step, "disembarked", unit["color"], partner))
        exploding = {}
        for point in self.jm_points:
            if point["status"] == 1:
                owner = self.units.get(point["obj_id"]) or {}
                exploding.setdefault(point["pos"], set()).add(owner.get("color"))
        for unit in self.units.values():
            colours = exploding.get(unit["cur_hex"])
            if colours and self.ground(unit) and unit["color"] in colours:
                self.friendly_exposure[unit["color"]] = self.friendly_exposure.get(unit["color"], 0) + 1
        for point in self.jm_points:
            if point["status"] == 0:
                point["fly_time"] -= 1
                if point["fly_time"] <= 0:
                    point["status"] = 1
            elif point["status"] == 1:
                point["boom_time"] -= 1
                if point["boom_time"] <= 0:
                    point["status"] = 2


def load_scenario(data_root: Path, scenario_id: str) -> Dict[str, Any]:
    return json.loads((Path(data_root) / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8"))
