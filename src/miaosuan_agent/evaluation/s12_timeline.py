"""Per-game facts of the Sprint 12 screen from its private captures (``docs/SPRINT12_V3_SCREEN.md``).

Reads one game's record, Sprint 9's ``T9Capture`` file, the compact v3 capture and the full-step timeline
(:mod:`.s12_capture`), and derives, for the v3 seat:

* the immediate stops a game can trigger by itself (S4 to S13, and S14 in 2120531121 C3), each recomputed here from
  the seat's observations and the emitted actions rather than taken from the policy's own bookkeeping;
* the classification facts (margin, coverage, attack, occupy) and the replication trigger facts;
* the mechanism endpoints: for every place v3 selected, the selection, the free-flow estimate, the predicted arrival,
  the arrival, path end, stationarity, first occupation listing, occupation order and response, the objective's
  ownership, the arrival slack and delay and the place's outcome; unproductive places; counted against raw
  commitments; staging, staging-hex occupancy and staging-induced waits; hold episodes; direct-fire availability,
  orders and responses; capture order.

Definitions (fixed at registration; the draft's section 9.3 with its exhaustive completion):

* a state is the post-step all-seeing state with the seat's observation; state ``j`` is the one decision ``j``
  observed (state 0 the first, the last state the one after the final step);
* arrival: the first state after the selection in which the unit stands on its objective; path end: the first state
  from arrival on with an empty path there; stationary: the first state from path end on with ``stop`` equal to 1;
  first occupation opportunity: the first state from arrival on whose observation lists an occupation (type 5) for
  the unit; occupation order: the first emitted occupation of the unit from arrival on, and the engine's response
  (feedback after that step);
* slack: ``max_step`` minus the arrival step; predicted arrival: the selection step plus the free-flow time; delay:
  arrival minus predicted arrival (negative contradicts the free-flow lower bound and is reported as a premise
  violation, never corrected);
* outcome of a place, first match: LOST (the unit left the seat's units before arriving), NEVER_ARRIVED, OCCUPIED (its
  own occupation accepted and the flag own after that step), HELD (it stands on the objective at the end while the
  objective is own), REDUNDANT (it arrived while the objective was already own), TOO_LATE (the objective is not own at
  the end), ARRIVED_NOT_DECISIVE (any other arrival: it arrived before own control, did not occupy, did not stand
  there at the end, and the objective is own at the end);
* "can arrive before ``max_step``" is the policy's admission test only; it is never read as a claim that the unit can
  usefully occupy before the end. Usefulness is the outcome above.

Units appear here by private id; :func:`public` keeps aggregates and per-objective labels only.
"""

from __future__ import annotations

import collections
import pickle
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from ..boundary import MoveCosts, Observation, Origin
from ..experiments.shoot_reservation import ShootReservationPolicy
from . import s12_screen as sc
from . import t9_batch_replay as rp
from .t9_confirmation import latency_ms, refusal_classes

GROUND = (1, 2)
KIND = {1: "infantry", 2: "vehicle"}
MOVE, SHOOT, OCCUPY = 1, 2, 5
OUTCOMES = ("LOST", "NEVER_ARRIVED", "OCCUPIED", "HELD", "REDUNDANT", "TOO_LATE", "ARRIVED_NOT_DECISIVE")


def labels(values: Mapping[int, Any]) -> Dict[int, str]:
    """Sprint 11's public objective labels: value, then a letter by an internal order that is not published."""
    out, seen = {}, collections.Counter()
    for coord in sorted(values, key=lambda c: (-(values[c] or 0), int(c))):
        seen[values[coord]] += 1
        out[coord] = f"{values[coord]}-point objective {chr(64 + seen[values[coord]])}"
    return out


class State:
    """What the analysis keeps of one state for the v3 seat."""

    __slots__ = ("cur_step", "stage", "units", "present", "flags", "valid", "kinds", "max_step")

    def __init__(self, global_raw: Mapping[str, Any], seat_raw: Mapping[str, Any], faction: int) -> None:
        time_info = seat_raw.get("time") or {}
        self.cur_step = time_info.get("cur_step")
        self.stage = time_info.get("stage")
        self.max_step = time_info.get("max_step")
        self.units: Dict[int, Tuple[Any, Tuple[Any, ...], Any, Any]] = {}
        self.kinds: Dict[int, Any] = {}
        for u in seat_raw.get("operators") or ():
            if u.get("color") == faction and u.get("type") in GROUND:
                self.units[u["obj_id"]] = (u.get("cur_hex"), tuple(u.get("move_path") or ()), u.get("stop"),
                                           u.get("speed"))
                self.kinds[u["obj_id"]] = u.get("type")
        self.present: Set[int] = {u["obj_id"] for key in ("operators", "passengers")
                                  for u in (seat_raw.get(key) or ()) if u.get("color") == faction}
        self.flags = {c["coord"]: c.get("flag") for c in (global_raw.get("cities") or ())}
        listed = seat_raw.get("valid_actions") or {}
        self.valid = {u: {int(k) for k in (listed.get(u) or {})} for u in self.units}


def load_states(windows: Mapping[str, Any], seat: int, faction: int) -> Tuple[List[State], List[Mapping[str, Any]]]:
    """States 0..N (N decisions, the last state the final one) and the seat's raw observations of decisions 0..N-1."""
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    if [s["k"] for s in samples] != list(range(len(samples))):
        raise ValueError("the timeline does not hold one snapshot per decision")
    states, raws = [], []
    for sample in samples:
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        raw = pickle.loads(snap["observation"])
        states.append(State(pickle.loads(sample["global"]), raw, faction))
        raws.append(raw)
    final = windows.get("final")
    if final is None:
        raise ValueError("the timeline holds no final state")
    snap = final["seats"].get(seat) or final["seats"].get(str(seat))
    states.append(State(pickle.loads(final["global"]), pickle.loads(snap["observation"]), faction))
    return states, raws


def stood_on(states: Sequence[State], unit: int, coord: Any, start: int) -> Optional[int]:
    """The first state index ``>= start`` in which ``unit`` stands on ``coord``."""
    for j in range(start, len(states)):
        position = states[j].units.get(unit)
        if position is not None and position[0] == coord:
            return j
    return None


def seat_feedback(entry: Mapping[str, Any], seat: int) -> List[Mapping[str, Any]]:
    return [f for f in entry.get("feedback") or () if (f.get("message") or {}).get("actor") == seat]


def response(entry: Mapping[str, Any], seat: int, action: Mapping[str, Any]) -> str:
    """``accepted`` or the engine's error code for one emitted action (feedback after its step)."""
    for f in seat_feedback(entry, seat):
        message = f.get("message") or {}
        if message.get("obj_id") == action.get("obj_id") and message.get("type") == action.get("type"):
            error = f.get("error")
            if error:
                return str(error.get("code") if isinstance(error, Mapping) else error)
            return "accepted"
    return "no feedback"


def place_outcome(states: Sequence[State], steps: Sequence[Mapping[str, Any]], seat: int, faction: int,
                  place: Mapping[str, Any]) -> Dict[str, Any]:
    unit, coord, k = place["unit"], place["objective"], place["k"]
    end = len(states) - 1
    out: Dict[str, Any] = {"arrival_state": None}
    lost_at = next((j for j in range(k + 1, len(states)) if unit not in states[j].present), None)
    arrival = stood_on(states, unit, coord, k + 1)
    if arrival is None or (lost_at is not None and lost_at <= arrival):
        out["outcome"] = "LOST" if lost_at is not None else "NEVER_ARRIVED"
        return out
    out["arrival_state"] = arrival
    out["arrival_step"] = states[arrival].cur_step
    out["arrival_slack"] = states[arrival].max_step - states[arrival].cur_step
    out["arrival_delay"] = out["arrival_step"] - place["predicted_arrival"] if place["predicted_arrival"] is not None else None
    path_end = next((j for j in range(arrival, len(states)) if unit in states[j].units
                     and states[j].units[unit][0] == coord and not states[j].units[unit][1]), None)
    out["path_end_step"] = None if path_end is None else states[path_end].cur_step
    stationary = None if path_end is None else next(
        (j for j in range(path_end, len(states)) if unit in states[j].units and states[j].units[unit][2] == 1), None)
    out["stationary_step"] = None if stationary is None else states[stationary].cur_step
    listing = next((j for j in range(arrival, end) if OCCUPY in states[j].valid.get(unit, ())
                    and unit in states[j].units and states[j].units[unit][0] == coord), None)
    out["first_occupation_listing_step"] = None if listing is None else states[listing].cur_step
    order = None
    for j in range(arrival, end):
        action = next((a["action"] for a in steps[j].get("submitted") or () if a["seat"] == seat
                       and a["action"].get("type") == OCCUPY and a["action"].get("obj_id") == unit), None)
        if action is not None:
            order = (j, response(steps[j], seat, action))
            break
    out["occupation_order_step"] = None if order is None else states[order[0]].cur_step
    out["occupation_response"] = None if order is None else order[1]
    own_at_end = states[end].flags.get(coord) == faction
    own_at_arrival = states[arrival].flags.get(coord) == faction
    occupied = (order is not None and order[1] == "accepted" and states[order[0] + 1].flags.get(coord) == faction)
    held = own_at_end and unit in states[end].units and states[end].units[unit][0] == coord
    if occupied:
        out["outcome"] = "OCCUPIED"
    elif held:
        out["outcome"] = "HELD"
    elif own_at_arrival:
        out["outcome"] = "REDUNDANT"
    elif not own_at_end:
        out["outcome"] = "TOO_LATE"
    else:
        out["outcome"] = "ARRIVED_NOT_DECISIVE"
    return out


def s14_findings(config: str, history: Mapping[Any, Mapping[str, Any]], holds: Sequence[Mapping[str, Any]],
                 arrival: Any, names: Mapping[Any, str]) -> List[str]:
    """S14, structural design failure, 2120531121 C3 only: an objective not own at the end whose selectable claimant
    v3 staged or withheld at a decision where every counted place was held by units that never stood on it before the
    end (no unit standing there, at least one counted place), while the claimant's free-flow arrival at that decision
    was earlier than the actual arrival of every place holder or none of them arrived. ``arrival(unit, objective,
    state)`` is the step a unit first stands on the objective from that state on, or None."""
    findings = []
    if config != "2120531121 C3":
        return findings
    for coord, info in history.items():
        if info["own_at_end"]:
            continue
        for hold in holds:
            if hold["objective"] != coord or hold["physical"] or not hold["holders"] or hold["free_flow"] is None:
                continue
            arrivals = [arrival(u, coord, hold["k"] + 1) for u in hold["holders"]]
            if any(a is not None for a in arrivals):
                continue  # a holder stood on the objective: the place was honoured
            predicted = hold["cur_step"] + hold["free_flow"]
            if all(a is None or predicted < a for a in arrivals):
                findings.append(f"{names.get(coord, 'an objective')}: a claimant held at decision {hold['k']} behind "
                                "places that were never honoured")
                break
    return findings


def staging_excess(units: Mapping[int, Tuple[Any, Tuple[Any, ...], Any, Any]], baseline: Sequence[Mapping[str, Any]],
                   emitted: Sequence[Mapping[str, Any]], stage_cap: int) -> List[Tuple[Any, int]]:
    """S9 recount: for every endpoint of an emitted own ground move that is not baseline-v2's move for that unit, the
    own ground units standing there or with a path ending there before the decision plus this decision's such moves
    ending there, when above ``stage_cap``."""
    endpoints = collections.Counter()
    for hex_, path, _, _ in units.values():
        endpoints[path[-1] if path else hex_] += 1
    base_paths = {a.get("obj_id"): tuple(a.get("move_path") or ()) for a in baseline if a.get("type") == MOVE}
    added = collections.Counter(tuple(a["move_path"])[-1] for a in emitted
                                if a.get("type") == MOVE and a.get("obj_id") in units and a.get("move_path")
                                and tuple(a["move_path"]) != base_paths.get(a.get("obj_id")))
    return [(hex_, endpoints[hex_] + n) for hex_, n in sorted(added.items()) if endpoints[hex_] + n > stage_cap]


def objective_history(states: Sequence[State], faction: int) -> Dict[Any, Dict[str, Any]]:
    out = {}
    for coord in states[0].flags:
        transitions, previous = [], None
        for state in states:
            flag = state.flags.get(coord)
            if flag != previous:
                transitions.append((state.cur_step, flag))
                previous = flag
        own = [step for step, flag in transitions if flag == faction]
        out[coord] = {"transitions": transitions, "first_own_step": own[0] if own else None,
                      "last_to_own_step": own[-1] if own else None,
                      "own_at_end": states[-1].flags.get(coord) == faction}
    return out


def analyze(entry: Mapping[str, Any], card_id: str, record: Mapping[str, Any], t9cap: Mapping[str, Any],
            v3cap: Mapping[str, Any], timeline: Mapping[str, Any], windows: Mapping[str, Any], costs: MoveCosts,
            capture_digests: Mapping[str, Tuple[Optional[str], Optional[str]]] = (),
            extra_known: Iterable[Tuple[Any, Any, str]] = (), rules: Mapping[str, Any] = sc.RULES) -> Dict[str, Any]:
    """Private facts of one screen game. ``capture_digests`` maps a capture name to (digest in the record, digest of
    the file); ``extra_known`` are refusal classes seen in baseline-v2 seats of earlier screen games. ``rules`` is the
    frozen rule set; only stand-in tests pass another (their games end before step 2,880)."""
    side = sc.candidate_side(entry["red"], entry["blue"])
    faction = 0 if side == "red" else 1
    other = "blue" if side == "red" else "red"
    seat = next(s["seat"] for s in record.get("seats", []) if s["policy"] == sc.V3_ID)
    config = sc.config_key(entry["scenario_id"], entry["condition"])
    stops: Dict[str, List[str]] = {code: [] for code in sc.STOP_CODES}
    facts: Dict[str, Any] = {"game_id": entry["game_id"], "card": card_id, "screen_position": entry["screen_position"],
                             "scenario_id": entry["scenario_id"], "condition": entry["condition"],
                             "candidate_side": side, "status": record.get("status"), "steps": record.get("steps"),
                             "session": record.get("session")}

    # S1, S4, S6, S13 (record level)
    if not ((record.get("session_close") or {}).get("integrity") or {}).get("ok", False):
        stops["S1"].append("the session did not close with integrity ok")
    if record.get("status") != "COMPLETED":
        stops["S4"].append(f"status {record.get('status')}")
    for s in record.get("seats", []):
        if s["contract_errors"]:
            stops["S4"].append(f"{s['contract_errors']} contract errors in the {s['policy']} seat")
        if s["replay_mismatches"]:
            stops["S6"].append(f"{s['replay_mismatches']} replay mismatches in the {s['policy']} seat")
        if s.get("gate_rejections"):
            stops["S13"].append(f"gate rejections in the {s['policy']} seat")
    known = {tuple(c) for c in sc.KNOWN_REFUSAL_CLASSES} | {tuple(c) for c in extra_known}
    for s in record.get("seats", []):
        if s["policy"] == sc.V2_ID:
            known |= set(refusal_classes(s))
    v3_seat = next(s for s in record.get("seats", []) if s["policy"] == sc.V3_ID)
    classes = refusal_classes(v3_seat)
    facts["refusal_classes"] = {f"{k[0]}/{k[1]}/{k[2]}": n for k, n in sorted(classes.items(), key=str)}
    for key in classes:
        if key not in known:
            stops["S13"].append(f"unexplained refusal class {key[0]}/{key[1]}/{key[2]}")
    scores = record.get("final_scores") or {}
    if scores:
        own_total, other_total = scores.get(f"{side}_total"), scores.get(f"{other}_total")
        if scores.get(f"{side}_win") != own_total - other_total:
            stops["S4"].append("the margin is not the engine's <side>_win")
        facts.update(margin=scores.get(f"{side}_win"), attack=scores.get(f"{side}_attack"),
                     occupy=scores.get(f"{side}_occupy"), remain=scores.get(f"{side}_remain"),
                     opponent_total=other_total,
                     scores={k: v for k, v in sorted(scores.items()) if k.startswith(side)})
    facts["latency"] = latency_ms(v3_seat.get("latency_us") or [])

    # S7 (observers, capture integrity and the two independent counts)
    if record.get("observer_errors"):
        stops["S7"].append(f"{len(record['observer_errors'])} observer errors")
    for name, (recorded, actual) in dict(capture_digests).items():
        if recorded is None or recorded != actual:
            stops["S7"].append(f"capture {name} missing or not the recorded digest")
    if timeline.get("consistency_errors"):
        stops["S7"].append(f"{len(timeline['consistency_errors'])} decisions differ from the seat-local reconstruction")
    steps = timeline.get("steps") or []
    if len(steps) != record.get("steps") or t9cap.get("steps") != record.get("steps"):
        stops["S7"].append("the captures and the record disagree on the number of steps")
    seat_facts = (t9cap.get("seats") or {}).get(str(faction)) or {}
    if (seat_facts.get("moves") or {}).get("emitted") != int((v3_seat.get("actions_by_type") or {}).get("1", 0)):
        stops["S7"].append("the T9 capture and the record disagree on the seat's move orders")
    policy_seats = sum(1 for s in record.get("seats", []) if s["policy"] in (sc.V3_ID, sc.V2_ID))
    if timeline.get("reconstructed_decisions") != policy_seats * len(steps):
        stops["S7"].append("not every baseline-v2 and v3 decision was reconstructed")
    errors = (v3cap.get("v3") or {}).get("errors") or []
    if errors:
        stops["S5"].append(f"{len(errors)} add-on errors")

    objectives = seat_facts.get("objectives") or {}
    facts.update(coverage=objectives.get("mean_held"), held_at_end=objectives.get("held_at_end"),
                 lost=(seat_facts.get("losses") or {}).get("lost"),
                 waiting_unit_steps=(seat_facts.get("waiting_in_front_of_full_hex") or {}).get("sum"),
                 waiting_max=(seat_facts.get("waiting_in_front_of_full_hex") or {}).get("max"))

    states, raws = load_states(windows, seat, faction)
    if len(raws) != len(steps):
        stops["S7"].append("the timeline's snapshots and its step log differ in length")
    router = ShootReservationPolicy(costs).router
    values = {c["coord"]: c.get("value") for c in (raws[0].get("cities") or ())}
    names = labels(values)
    end = len(states) - 1
    max_step = next((s.max_step for s in states if s.max_step is not None), None)
    if max_step != rules["max_step"]:
        stops["S7"].append(f"max_step {max_step} is not the registered {rules['max_step']}")

    places: List[Dict[str, Any]] = []
    holds: List[Dict[str, Any]] = []
    commitments = {"max_counted": 0, "max_raw": 0, "raw_above_capacity": 0, "raw_above_capacity_with_released": 0}
    staged_total, stage_rejected, last_order = 0, 0, {}
    staging_hexes: Dict[Any, int] = {}
    staging_occupancy: Dict[Any, int] = collections.Counter()
    waits: Dict[int, List[int]] = {}
    wait_episodes: List[Dict[str, Any]] = []
    fire = {"decisions_with_shot_listed": 0, "shots_listed": 0, "orders": 0, "responses": collections.Counter()}
    occupation = {"listed_unit_states": 0, "orders": 0, "responses": collections.Counter()}
    reference = sc.REFERENCE_FIRE_DECISIONS.get(config, ())
    reference_rows = {}
    structure = collections.Counter()
    claimed: Dict[int, Any] = {}

    for k in range(len(steps)):
        state, raw, entry_k = states[k], raws[k], steps[k]
        row = (entry_k.get("s12") or {}).get(str(seat))
        submitted = [a["action"] for a in entry_k.get("submitted") or () if a["seat"] == seat]
        # staging-induced waits in state k (orders up to decision k-1)
        if k > 0:
            occupants = collections.defaultdict(list)
            for unit, position in state.units.items():
                occupants[position[0]].append(unit)
            waiting_now = set()
            for unit, (hex_, path, stop, speed) in state.units.items():
                if not path or speed != 0:
                    continue
                nxt = path[0]
                here = occupants.get(nxt, [])
                if len(here) >= rules["capacity"] and any(
                        last_order.get(u) == ("staged", nxt) and not state.units[u][1] for u in here):
                    waiting_now.add(unit)
            for unit in list(waits):
                if unit not in waiting_now:
                    first, last = waits.pop(unit)
                    wait_episodes.append({"steps": last - first + 1, "to_end": False})
            for unit in waiting_now:
                waits.setdefault(unit, [state.cur_step, state.cur_step])[1] = state.cur_step
            for hex_ in staging_hexes:
                staging_occupancy[hex_] = max(staging_occupancy[hex_], len(occupants.get(hex_, [])))
            stacked = max((len(v) for v in occupants.values()), default=0)
            if stacked > rules["capacity"]:
                stops["S8"].append(f"{stacked} own ground units on one hex at step {state.cur_step}")
        # fire and occupation listings
        if state.stage == 2:
            shots = sum(1 for u in state.valid if SHOOT in state.valid[u])
            fire["shots_listed"] += shots
            fire["decisions_with_shot_listed"] += int(shots > 0)
            occupation["listed_unit_states"] += sum(1 for u in state.valid if OCCUPY in state.valid[u])
        for action in submitted:
            if action.get("type") == SHOOT:
                fire["orders"] += 1
                fire["responses"][response(entry_k, seat, action)] += 1
            elif action.get("type") == OCCUPY:
                occupation["orders"] += 1
                occupation["responses"][response(entry_k, seat, action)] += 1
        if k in reference:
            reference_rows[str(k)] = {"shot_listed": any(SHOOT in v for v in state.valid.values()),
                                      "orders": sum(1 for a in submitted if a.get("type") == SHOOT)}
        if row is None:
            stops["S7"].append(f"no reconstruction of decision {k}")
            continue
        allocation = row["allocation"]
        if allocation.get("error"):
            stops["S5"].append(f"allocation error at decision {k}")
        # every emitted move updates the unit's last order (staged or not)
        staged_now = {int(u): tuple(p) for u, p in allocation["staged"].items()}
        stage_rejected += sum(1 for c in allocation["changes"] if c.get("kind") == "stage-rejected")
        for action in submitted:
            if action.get("type") == MOVE and action.get("obj_id") in state.units:
                unit = action["obj_id"]
                path = tuple(action.get("move_path") or ())
                if unit in staged_now and path == staged_now[unit]:
                    last_order[unit] = ("staged", path[-1])
                    staging_hexes.setdefault(path[-1], k)
                    staged_total += 1
                else:
                    last_order[unit] = ("move", path[-1] if path else None)
        if state.stage != 2 or not any(a.get("type") == MOVE for a in row["baseline_actions"]):
            continue
        observation = Observation.from_raw(raw, Origin.ENGINE)
        baseline = row["baseline_actions"]
        checks = rp.structural(observation, faction, baseline, submitted, router)
        before = rp.commitments(observation, faction, router)
        capacity = rp.capacity_check(before, checks["owners"])
        for key in ("prefix_failures", "cross_objective", "unrelated_changed", "invented"):
            structure[key] += checks.get(key, 0)
        if checks.get("prefix_failures"):
            stops["S10"].append(f"decision {k}: {checks['prefix_failures']} staged moves not a strict off-objective prefix")
        if checks.get("cross_objective"):
            stops["S11"].append(f"decision {k}: {checks['cross_objective']} cross-objective moves")
        if checks.get("unrelated_changed") or checks.get("invented"):
            stops["S12"].append(f"decision {k}: unrelated actions changed or moves invented")
        if capacity.get("caused") or capacity.get("inherited"):
            stops["S8"].append(f"decision {k}: counted places above four")
        for hex_, count in staging_excess(state.units, baseline, submitted, rules["stage_cap"]):
            stops["S9"].append(f"decision {k}: a staging endpoint holds {count}")
        # counted and raw commitments, selections and holds (v3's own allocation)
        for coord_text, info in allocation["objectives"].items():
            selected = [int(u) for u in info["selected"]]
            counted = info["physical"] + info["movers"] + len(selected)
            raw_count = counted + info["phantom"]
            commitments["max_counted"] = max(commitments["max_counted"], counted)
            commitments["max_raw"] = max(commitments["max_raw"], raw_count)
            if counted > rules["capacity"]:
                stops["S8"].append(f"decision {k}: {counted} counted places")
            if raw_count > rules["capacity"]:
                commitments["raw_above_capacity"] += 1
                commitments["raw_above_capacity_with_released"] += int(info["phantom"] > 0)
            coord = int(coord_text)
            holders = [int(u) for u in info["mover_bounds"]] + selected
            for unit in selected:
                claimant = allocation["claimants"][str(unit)]
                free_flow = claimant["free_flow"]
                places.append({"unit": unit, "objective": coord, "k": k, "cur_step": state.cur_step,
                               "free_flow": free_flow, "kind": KIND.get(state.kinds.get(unit), "other"),
                               "predicted_arrival": None if free_flow is None else state.cur_step + free_flow})
            for unit_text, claimant in allocation["claimants"].items():
                claimed[int(unit_text)] = claimant["objective"]
                if claimant["objective"] != coord or int(unit_text) in selected:
                    continue
                if claimant["status"] == "no place under capacity":
                    holds.append({"unit": int(unit_text), "objective": coord, "k": k, "cur_step": state.cur_step,
                                  "free_flow": claimant["free_flow"], "physical": info["physical"],
                                  "holders": holders})

    for unit, (first, last) in waits.items():
        wait_episodes.append({"steps": last - first + 1, "to_end": True})

    for place in places:
        place.update(place_outcome(states, steps, seat, faction, place))
    history = objective_history(states, faction)
    stood_cache: Dict[Tuple[int, Any, int], Optional[int]] = {}

    def stood(unit: int, coord: Any, start: int) -> Optional[int]:
        key = (unit, coord, start)
        if key not in stood_cache:
            stood_cache[key] = stood_on(states, unit, coord, start)
        return stood_cache[key]

    unproductive_holds, unproductive_units = 0, set()
    for hold in holds:
        bad = [u for u in hold["holders"] if stood(u, hold["objective"], hold["k"] + 1) is None]
        unproductive_units.update((u, hold["objective"]) for u in bad)
        hold["unproductive_holders"] = bad
        unproductive_holds += int(bool(bad))

    stops["S14"].extend(s14_findings(config, history, holds, lambda u, c, j: (
        None if stood(u, c, j) is None else states[stood(u, c, j)].cur_step), names))

    # objectives, the fifth objective and its attribution
    own_end = [c for c, h in history.items() if h["own_at_end"]]
    fifth = max(own_end, key=lambda c: (history[c]["last_to_own_step"], c)) if len(own_end) == len(history) else None
    facts["objectives_at_end"] = len(own_end)
    facts["fifth_objective_last_to_own_step"] = None if fifth is None else history[fifth]["last_to_own_step"]
    facts["fifth_objective_attributed_to_v3_selection"] = fifth is not None and any(
        p["objective"] == fifth and p["outcome"] in ("OCCUPIED", "HELD") for p in places)
    order = sorted((h["first_own_step"], names[c]) for c, h in history.items() if h["first_own_step"] is not None)
    facts["capture_order"] = [name for _, name in order]
    facts["objectives"] = {names[c]: {"first_own_step": h["first_own_step"], "last_to_own_step": h["last_to_own_step"],
                                      "own_at_end": h["own_at_end"], "transitions": len(h["transitions"]) - 1,
                                      "places_selected": sum(1 for p in places if p["objective"] == c),
                                      "outcomes": dict(sorted(collections.Counter(
                                          p["outcome"] for p in places if p["objective"] == c).items()))}
                           for c, h in sorted(history.items(), key=lambda i: names[i[0]])}

    # aggregates
    def distribution(values: Sequence[Any]) -> Dict[str, Any]:
        values = sorted(v for v in values if v is not None)
        if not values:
            return {"n": 0}
        return {"n": len(values), "min": values[0], "median": values[(len(values) - 1) // 2], "max": values[-1]}

    arrived = [p for p in places if p.get("arrival_state") is not None]
    facts["places"] = {
        "selected": len(places),
        "by_kind": dict(sorted(collections.Counter(p["kind"] for p in places).items())),
        "outcomes": {o: sum(1 for p in places if p["outcome"] == o) for o in OUTCOMES},
        "arrival_slack": distribution([p.get("arrival_slack") for p in arrived]),
        "arrival_slack_by_outcome": {o: distribution([p.get("arrival_slack") for p in arrived if p["outcome"] == o])
                                     for o in OUTCOMES if any(p["outcome"] == o for p in arrived)},
        "predicted_slack": distribution([max_step - p["predicted_arrival"] for p in places
                                         if p["predicted_arrival"] is not None]),
        "arrival_delay": distribution([p.get("arrival_delay") for p in arrived]),
        "arrival_to_path_end": distribution([p["path_end_step"] - p["arrival_step"] for p in arrived
                                             if p.get("path_end_step") is not None]),
        "path_end_to_stationary": distribution([p["stationary_step"] - p["path_end_step"] for p in arrived
                                                if p.get("stationary_step") is not None]),
        "arrival_to_first_occupation_listing": distribution([p["first_occupation_listing_step"] - p["arrival_step"]
                                                             for p in arrived
                                                             if p.get("first_occupation_listing_step") is not None]),
        "occupation_responses": dict(sorted(collections.Counter(p["occupation_response"] for p in arrived
                                                                if p.get("occupation_response")).items())),
    }
    facts["premise"] = {"arrivals_earlier_than_free_flow": sum(1 for p in arrived if (p.get("arrival_delay") or 0) < 0)}
    facts["unproductive"] = {"holds": len(holds), "holds_behind_an_unproductive_place": unproductive_holds,
                             "unproductive_holders": len(unproductive_units)}
    facts["commitments"] = commitments
    facts["staging"] = {"staged_moves": staged_total, "stage_rejected": stage_rejected,
                        "staging_hexes": len(staging_hexes),
                        "max_staging_hex_occupancy": max(staging_occupancy.values(), default=0),
                        "waits": distribution([w["steps"] for w in wait_episodes]),
                        "waits_above_flag": sum(1 for w in wait_episodes
                                                if w["steps"] > rules["staging_wait_flag_steps"])}
    facts["staging_blocks_to_end"] = sum(1 for w in wait_episodes if w["to_end"])
    episodes = (v3cap.get("v3") or {}).get("hold_episodes") or []
    mine = [e for e in episodes if e["faction"] == faction]
    long_holds = 0
    for episode in mine:
        if episode["decisions"] < rules["long_hold_flag_decisions"]:
            continue
        objective = claimed.get(episode["obj_id"])
        state = states[min(episode["end"], end)]
        long_holds += int(objective is None or state.flags.get(objective) != faction)
    facts["holds"] = {"episodes": len(mine), "longest_decisions": max((e["decisions"] for e in mine), default=0),
                      "long_holds_flagged": long_holds,
                      "changes": (v3cap.get("v3") or {}).get("changes") or {}}
    facts["fire"] = {"decisions_with_shot_listed": fire["decisions_with_shot_listed"],
                     "shots_listed": fire["shots_listed"], "orders": fire["orders"],
                     "responses": dict(sorted(fire["responses"].items())), "reference_decisions": reference_rows}
    facts["occupation"] = {"listed_unit_states": occupation["listed_unit_states"], "orders": occupation["orders"],
                           "responses": dict(sorted(occupation["responses"].items()))}
    facts["consistency"] = {"reconstructed_decisions": timeline.get("reconstructed_decisions"),
                            "differences": len(timeline.get("consistency_errors") or []),
                            "structural": dict(sorted(structure.items()))}
    facts["capture_digests"] = {name: recorded == actual for name, (recorded, actual) in dict(capture_digests).items()}
    facts["observer_seconds"] = {"timeline": timeline.get("observer_seconds")}

    # classification facts
    if entry["condition"] in ("H1", "H2"):
        if facts.get("margin") is not None and facts.get("coverage") is not None:
            facts["t9v2_like"] = sc.t9v2_like(entry["condition"], facts, rules)
            facts["collapse"] = sc.collapse(entry["condition"], facts, rules)
        flags = []
        if (facts.get("waiting_unit_steps") or 0) > rules["queue_flag_above"][entry["condition"]]:
            flags.append("waiting unit-steps above the largest T9-v1 value of the seat")
    else:
        if facts.get("occupy") is not None:
            facts["adverse_class"] = sc.adverse_class(config, facts, rules)
            facts["replication_triggers"] = sc.replication_triggers(config, facts, rules)
        flags = []
    if facts["staging"]["waits_above_flag"]:
        flags.append("staging-induced wait longer than 144 steps")
    if long_holds:
        flags.append("a unit staged or withheld for 1,440 or more consecutive decisions while its objective was not own")
    if facts["premise"]["arrivals_earlier_than_free_flow"]:
        flags.append("an arrival earlier than its free-flow time (premise violation)")
    if commitments["raw_above_capacity"]:
        flags.append("raw commitment above four (released places)")
    latency = facts["latency"]
    if latency.get("p99_ms", 0) > rules["latency_flag_p99_ms"] or latency.get("max_ms", 0) > rules["latency_flag_max_ms"]:
        flags.append("latency")
    facts["flags"] = flags
    facts["stops"] = {code: details for code, details in stops.items() if details}
    facts["stop_details_count"] = sum(len(v) for v in stops.values())
    facts["places_private"] = places
    facts["holds_private"] = holds
    return facts


def public(facts: Mapping[str, Any]) -> Dict[str, Any]:
    """The game's public facts: the stop codes without private details, and no per-unit rows."""
    out = dict(facts)
    out["stops"] = {code: len(details) for code, details in (facts.get("stops") or {}).items()}
    return sc.public_game(out)
