"""Sprint 22 T2-P1 transport mechanism probe: offline audit, witness search, rehearsal and analysis
(``docs/SPRINT22_T2_TRANSPORT_PROBE.md``).

    python scripts/s22_analysis.py semantics [--check]   # transport semantics aggregates over the frozen corpus
    python scripts/s22_analysis.py witness [--check]     # the registered witness search and the private reference
    python scripts/s22_analysis.py rehearse              # the candidate replayed over the witness game's prefix

Runs on the evaluation server (the captures are private, under the ignored ``local/``). The corpus is Sprint 21's
frozen list of usable full-step captures (``evaluation/s21-direct-fire-semantics/inputs.json``, every file pinned by
SHA-256), restricted to games against the inert control; a pinned file that changed refuses the run. Public outputs
go to ``evaluation/s22-t2-transport-probe/``; private ones (unit ids, hexes, digests of the trigger) to
``local/diagnostics/s22/``. ``--check`` regenerates and compares byte for byte without writing.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin, Stage  # noqa: E402
from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.decision.routing import move_mode  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s22_probe as sp  # noqa: E402
from miaosuan_agent.experiments import t2_transport_p1 as t2  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

PUBLIC = REPO_ROOT / "evaluation" / sp.STUDY_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s22"
S21_INPUTS = REPO_ROOT / "evaluation" / "s21-direct-fire-semantics" / "inputs.json"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
SEMANTICS = PUBLIC / "semantics.json"
WITNESS = PUBLIC / "witness.json"
REFERENCE = PRIVATE / "witness-reference.json"
V2_CLASS = "baseline-v2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
                          ).hexdigest()


def key_int(value: Any) -> Any:
    return int(value) if isinstance(value, str) and value.lstrip("-").isdigit() else value


def unpickle(value: Any) -> Any:
    return pickle.loads(value) if isinstance(value, (bytes, bytearray)) else value


def baseline_memory(memory: Any) -> Any:
    """baseline-v2's part of a seat memory (the add-on and shadow memories carry it as ``baseline``)."""
    return memory.baseline if hasattr(memory, "baseline") else memory


def policy_class(policy: str) -> str:
    if policy.startswith("baseline-v2"):
        return V2_CLASS
    if policy == INERT_ID:
        return "inert control"
    return "other"


# ------------------------------------------------------------------------------------------------
# the frozen corpus


def corpus() -> List[Dict[str, Any]]:
    """Sprint 21's usable captures against the inert control, every pinned file checked."""
    committed = json.loads(S21_INPUTS.read_text(encoding="utf-8"))
    out = []
    for entry in committed["corpus"]:
        files = {k: REPO_ROOT / v["path"] for k, v in entry["files"].items()}
        for kind, f in entry["files"].items():
            if not files[kind].exists() or sha256(files[kind]) != f["sha256"]:
                raise SystemExit(f"refused: a pinned corpus file changed or is missing: {f['path']}")
        record = json.loads(files["record"].read_text(encoding="utf-8"))
        classes = {s["seat"]: policy_class(s["policy"]) for s in record["seats"]}
        if sorted(classes.values()).count("inert control") != 1:
            continue
        seat = next(s for s in record["seats"] if policy_class(s["policy"]) != "inert control")
        out.append({"folder": entry["folder"], "game": entry["game"], "files": files, "record": record,
                    "seat": seat["seat"], "faction": seat["faction"],
                    "tier": 1 if policy_class(seat["policy"]) == V2_CLASS else 2})
    return out


def costs_of(entry: Mapping[str, Any]) -> MoveCosts:
    card = json.loads((REPO_ROOT / "evaluation" / entry["folder"] / "manifest.json").read_text(encoding="utf-8"))
    scenario = entry["record"]["scenario_id"]
    map_id = next(s["map_id"] for s in card["scenarios"] if s["scenario_id"] == scenario)
    inputs = sdk_data.load_inputs(LOCAL_EVAL / entry["folder"] / "data" / scenario / "Data", scenario, map_id)
    return MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


class Game:
    """One corpus game: the seat's raw observations, memories and submitted actions per decision."""

    def __init__(self, entry: Mapping[str, Any]) -> None:
        self.entry = entry
        self.seat, self.faction = entry["seat"], entry["faction"]
        compact = json.loads(entry["files"]["compact"].read_text(encoding="utf-8"))
        with entry["files"]["windows"].open("rb") as handle:
            windows = pickle.load(handle)
        self.steps = compact["steps"]
        samples = sorted(windows["samples"], key=lambda s: s["k"])
        if [s["k"] for s in samples] != list(range(len(self.steps))):
            raise SystemExit(f"refused: {entry['game']}: snapshots do not cover every step")
        self.samples = samples
        self.final = windows.get("final")

    def raw(self, k: int) -> Dict[str, Any]:
        snap = self.samples[k]["seats"].get(self.seat) or self.samples[k]["seats"].get(str(self.seat))
        return pickle.loads(snap["observation"])

    def memory(self, k: int) -> Any:
        snap = self.samples[k]["seats"].get(self.seat) or self.samples[k]["seats"].get(str(self.seat))
        return unpickle(snap["memory"])

    def submitted(self, k: int) -> List[Dict[str, Any]]:
        return [a["action"] for a in self.steps[k].get("submitted") or () if a["seat"] == self.seat]

    def first_fire(self) -> Optional[int]:
        for k, step in enumerate(self.steps):
            if step.get("judge_new") or any((a.get("action") or {}).get("type") in sp.FIRE_TYPES
                                            for a in step.get("submitted") or ()):
                return k
        return None


# ------------------------------------------------------------------------------------------------
# semantics aggregates (section 6)


def unit_class(u: Optional[Mapping[str, Any]]) -> str:
    if not u:
        return "absent"
    return f"type {u.get('type')} sub {u.get('sub_type')}"


def stationary(u: Mapping[str, Any]) -> bool:
    return not u.get("move_path") and not (u.get("speed") or 0) and not (u.get("move_to_stop_remain_time") or 0)


def carrier_state(u: Mapping[str, Any]) -> str:
    if u.get("move_path"):
        return "moving"
    return "stop transition" if (u.get("move_to_stop_remain_time") or 0) else "settled"


def semantics() -> Dict[str, Any]:
    listings: collections.Counter = collections.Counter()
    shapes: collections.Counter = collections.Counter()
    capacity: collections.Counter = collections.Counter()
    four: collections.Counter = collections.Counter()
    passengers: collections.Counter = collections.Counter()
    arrivals: collections.Counter = collections.Counter()
    issued: collections.Counter = collections.Counter()
    games = []
    for entry in corpus():
        game = Game(entry)
        games.append({"game": entry["game"], "tier": entry["tier"], "decisions": len(game.steps)})
        prev: Dict[int, Mapping[str, Any]] = {}
        cities = None
        for k in range(len(game.steps)):
            raw = game.raw(k)
            if cities is None:
                cities = {c["coord"] for c in raw.get("cities") or ()}
            flags = {c["coord"]: c.get("flag") for c in raw.get("cities") or ()}
            own = {u["obj_id"]: u for u in raw.get("operators") or () if u.get("color") == game.faction}
            aboard = {u["obj_id"]: u for u in raw.get("passengers") or () if u.get("color") == game.faction}
            for u in aboard.values():
                passengers[(unit_class(u), f"on_board {u.get('on_board')}",
                            "car is an own operator" if u.get("car") in own else "car not an own operator",
                            "listed by its car" if u["obj_id"] in ((own.get(u.get("car")) or {}).get("passenger_ids")
                                                                   or ()) else "not listed by its car")] += 1
            for u in own.values():
                if u.get("type") == 2 and u.get("sub_type") == 1:
                    capacity[(f"valid_passenger_types {sorted(u.get('valid_passenger_types') or ())}",
                              "max_passenger_nums " + json.dumps({str(k2): v for k2, v in
                                                                  (u.get("max_passenger_nums") or {}).items()},
                                                                 sort_keys=True),
                              f"loading_capacity {u.get('loading_capacity')}")] += 1
                    if u.get("passenger_ids"):
                        listed4 = 4 in {key_int(t) for t in ((raw.get("valid_actions") or {}).get(u["obj_id"]) or
                                                             (raw.get("valid_actions") or {}).get(str(u["obj_id"]))
                                                             or {})}
                        four[(carrier_state(u), "disembark listed" if listed4 else "disembark not listed")] += 1
                p = prev.get(u["obj_id"])
                if p and p.get("move_path") and not u.get("move_path") and u.get("cur_hex") in cities \
                        and u.get("type") == 2:
                    nxt_move = nxt_occ = None
                    for j in range(k, min(k + 300, len(game.steps))):
                        for a in game.submitted(j):
                            if a.get("obj_id") == u["obj_id"] and a.get("type") == sp.MOVE and nxt_move is None:
                                nxt_move = j - k
                            if a.get("obj_id") == u["obj_id"] and a.get("type") == sp.OCCUPY and nxt_occ is None:
                                nxt_occ = j - k
                        if nxt_move is not None:
                            break
                    held = flags.get(u["cur_hex"]) == game.faction
                    arrivals[("objective held at arrival" if held else "objective not held at arrival",
                              "occupy at the arrival decision" if nxt_occ == 0 else
                              ("no occupy" if nxt_occ is None else "occupy later"),
                              "no move within 300 decisions" if nxt_move is None else
                              f"next move after {nxt_move} decisions" if nxt_move <= 2 else
                              "next move after more than 2 decisions")] += 1
            for step_action in game.steps[k].get("submitted") or ():
                a_type = (step_action.get("action") or {}).get("type")
                if a_type in (sp.EMBARK, sp.DISEMBARK):
                    issued[(a_type, "candidate seat" if step_action.get("seat") == game.seat else "other seat")] += 1
            valid = raw.get("valid_actions") or {}
            for actor_key, per in valid.items():
                actor_id = key_int(actor_key)
                actor = own.get(actor_id) or aboard.get(actor_id)
                for akey, options in (per or {}).items():
                    a = key_int(akey)
                    if a not in (sp.EMBARK, sp.DISEMBARK):
                        continue
                    for opt in options or ():
                        shapes[(a, ",".join(sorted(opt)))] += 1
                        tid = opt.get("target_obj_id")
                        target = own.get(tid) or aboard.get(tid)
                        listings[(a, unit_class(actor), unit_class(target),
                                  "target an own operator" if tid in own else
                                  "target an own passenger" if tid in aboard else "target not own",
                                  "same hex" if actor and target and actor.get("cur_hex") == target.get("cur_hex")
                                  else "different hex",
                                  "actor stationary" if actor and stationary(actor) else "actor not stationary",
                                  "target stationary" if target and stationary(target) else "target not stationary")] += 1
            prev = own

    def table(counter: collections.Counter, names: Sequence[str]) -> List[Dict[str, Any]]:
        return [{**dict(zip(names, key)), "count": n} for key, n in sorted(counter.items(), key=lambda i: repr(i[0]))]

    return {"schema": sp.SCHEMA + "/semantics", "study_id": sp.STUDY_ID, "games": games,
            "issued_transport_orders": table(issued, ("action", "seat")),
            "listings": table(listings, ("action", "actor_class", "target_class", "target_relation", "co_location",
                                         "actor_state", "target_state")),
            "option_key_sets": table(shapes, ("action", "keys")),
            "ifv_capacity_fields": table(capacity, ("valid_passenger_types", "max_passenger_nums",
                                                     "loading_capacity")),
            "disembark_listing_by_carrier_state": table(four, ("carrier_state", "listing")),
            "passenger_representation": table(passengers, ("passenger_class", "on_board", "car", "carrier_listing")),
            "vehicle_arrivals_on_objectives": table(arrivals, ("ownership", "occupy", "next_move"))}


# ------------------------------------------------------------------------------------------------
# witness search (sections 8 and 9)


def free_flow(router, unit: Mapping[str, Any], path: Sequence[int]) -> Optional[int]:
    times, _ = tb.path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                             unit.get("cur_hex"), list(path))
    return None if times is None else sum(times)


def scan(entry: Mapping[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """One corpus game: the public row (minimums, preferences) and the private facts of its trigger, if any."""
    game = Game(entry)
    costs = costs_of(entry)
    row: Dict[str, Any] = {"game": entry["game"], "folder": entry["folder"], "tier": entry["tier"],
                           "scenario_id": entry["record"]["scenario_id"], "condition": entry["record"]["condition"],
                           "seat_side": "red" if entry["faction"] == 0 else "blue", "full_step_capture": True,
                           "inert_opponent": True, "decisions": len(game.steps)}
    first_fire = game.first_fire()
    row["first_fire_decision"] = first_fire
    found = None
    mismatch = None
    for k in range(len(game.steps)):
        raw = game.raw(k)
        observation = Observation.from_raw(raw, Origin.ENGINE)
        policy = ShootReservationPolicy(costs)
        base = policy.decide(observation, game.seat, game.faction, baseline_memory(game.memory(k)))
        if rd.plain(base.actions) != rd.plain(game.submitted(k)):
            mismatch = k
            break
        if observation.time().stage != Stage.PLAY:
            continue
        hit = t2.trigger(t2.View(observation, game.seat, game.faction), base.actions)
        if hit is not None:
            found = (k, raw, observation, base, policy, hit)
            break
    row["reconstruction_exact"] = mismatch is None or (found is not None and mismatch > found[0])
    row["first_reconstruction_difference"] = mismatch
    row["trigger"] = found is not None
    if found is None:
        return row, None
    k, raw, observation, base, policy, (inf_id, car_id, option) = found
    own = {u["obj_id"]: u for u in raw["operators"] if u.get("color") == game.faction}
    inf, car = own[inf_id], own[car_id]
    cities = {c["coord"]: c.get("value") for c in raw.get("cities") or ()}
    names = tl.labels(cities)
    car_move = next(a for a in base.actions if a.get("obj_id") == car_id)
    inf_move = next(a for a in base.actions if a.get("obj_id") == inf_id)
    dest = list(car_move["move_path"])[-1]
    t_car = free_flow(policy.router, car, car_move["move_path"])
    foot = policy.router.shortest_paths(inf["cur_hex"], move_mode(1, inf.get("move_state"))).path_to(dest)
    t_foot = free_flow(policy.router, inf, foot) if foot else None
    t_own = free_flow(policy.router, inf, inf_move["move_path"])
    now = observation.time().cur_step
    max_step = observation.time().max_step
    peak, taken = 0, False
    for j in range(k, len(game.steps)):
        later = game.raw(j)
        standing = [u["obj_id"] for u in later.get("operators") or ()
                    if u.get("color") == game.faction and u.get("type") in (1, 2) and u.get("cur_hex") == dest]
        peak = max(peak, len(standing))
        if later["time"]["cur_step"] == now + t2.DOCUMENTED_TRANSITION:
            flag = next((c.get("flag") for c in later.get("cities") or () if c["coord"] == dest), None)
            taken = flag == game.faction and car_id not in standing
    row.update({
        "trigger_decision": k, "trigger_step": now, "max_step": max_step,
        "before_first_fire": first_fire is None or k < first_fire,
        "carrier_route_to_objective": dest in cities,
        "destination": names.get(dest), "infantry_own_objective": names.get(list(inf_move["move_path"])[-1]),
        "carrier_free_flow": t_car, "infantry_free_flow_to_destination": t_foot,
        "infantry_free_flow_to_own_objective": t_own,
        "free_flow_saving": (t_foot - t_car) if (t_foot is not None and t_car is not None) else 0,
        "infantry_cannot_arrive_on_foot": t_foot is None or now + t_foot >= max_step,
        "time_feasible": t_car is not None and sp.feasible(now, t_car, max_step),
        "destination_peak_own_ground_units_from_trigger": peak,
        "destination_saturated_in_history": peak >= t2.STACK_LIMIT,
        "destination_taken_by_another_unit_before_release": taken,
        "infantry_listed_embark_options": len(((observation.valid_actions().get(inf_id) or {}).get(t2.EMBARK)) or ()),
    })
    trigger_actions = list(t2.step(observation, game.seat, game.faction, base.actions, ())[0])
    private = {"game": entry["game"], "folder": entry["folder"], "seat": game.seat, "faction": game.faction,
               "trigger_decision": k, "trigger_step": now, "pair": [inf_id, car_id], "shared_hex": inf["cur_hex"],
               "option": dict(option), "destination_hex": dest, "carrier_path": list(car_move["move_path"]),
               "infantry_path": list(inf_move["move_path"]), "infantry_foot_path_to_destination": list(foot or ()),
               "baseline_actions": rd.plain(base.actions), "trigger_actions": rd.plain(trigger_actions),
               "trigger_actions_sha256": canonical_sha256(rd.plain(trigger_actions)),
               "observation_sha256": canonical_sha256(raw)}
    return row, private


PUBLIC_ROW_KEYS = ("game", "tier", "scenario_id", "condition", "seat_side", "decisions", "full_step_capture",
                   "inert_opponent", "reconstruction_exact", "trigger", "before_first_fire",
                   "carrier_route_to_objective", "time_feasible", "first_fire_decision", "trigger_decision",
                   "trigger_step", "destination", "infantry_own_objective", "carrier_free_flow",
                   "infantry_free_flow_to_destination", "infantry_free_flow_to_own_objective", "free_flow_saving",
                   "infantry_cannot_arrive_on_foot", "destination_peak_own_ground_units_from_trigger",
                   "destination_saturated_in_history", "destination_taken_by_another_unit_before_release",
                   "infantry_listed_embark_options")


def witness() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    rows, privates = [], {}
    for entry in corpus():
        row, private = scan(entry)
        rows.append(row)
        if private is not None:
            privates[row["game"]] = private
    selection = sp.select_witness(rows)
    chosen = selection["chosen"]
    public = {"schema": sp.SCHEMA + "/witness", "study_id": sp.STUDY_ID, "tiers": {str(k): v for k, v in sp.TIERS.items()},
              "minimums": list(sp.MINIMUMS), "ranking": list(sp.RANKING),
              "rows": [{k: r.get(k) for k in PUBLIC_ROW_KEYS} for r in rows],
              "eligible_in_rank_order": selection["eligible"], "minimum_failures": selection["failures"],
              "selected": None if chosen is None else chosen["game"]}
    reference = {"schema": sp.SCHEMA + "/witness-reference", "selected": None if chosen is None else privates[chosen["game"]],
                 "triggers": privates}
    return public, reference


def private_values(reference: Mapping[str, Any]) -> set:
    values = set()
    for p in (reference.get("triggers") or {}).values():
        values.update(p["pair"])
        values.update([p["shared_hex"], p["destination_hex"]])
        values.update(p["carrier_path"] + p["infantry_path"] + p["infantry_foot_path_to_destination"])
    return values


# ------------------------------------------------------------------------------------------------
# rehearsal (section 10)


def rehearse() -> int:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    chosen = reference["selected"]
    if chosen is None:
        print("no witness: nothing to rehearse")
        return 1
    entry = next(e for e in corpus() if e["game"] == chosen["game"])
    game = Game(entry)
    costs = costs_of(entry)
    k = chosen["trigger_decision"]
    policy = t2.TransportPolicy(costs)
    memory = AddonMemory(baseline_memory(game.memory(0)), ())
    problems = []
    for j in range(k + 1):
        observation = Observation.from_raw(game.raw(j), Origin.ENGINE)
        v2 = ShootReservationPolicy(costs).decide(observation, game.seat, game.faction, baseline_memory(game.memory(j)))
        decision = policy.decide(observation, game.seat, game.faction,
                                 AddonMemory(baseline_memory(game.memory(j)), memory.addon))
        live = rd.plain(decision.actions)
        if j < k:
            if live != rd.plain(v2.actions) or decision.memory.addon != ():
                problems.append(f"decision {j}: the candidate differs from baseline-v2 before the trigger")
        else:
            if live != chosen["trigger_actions"]:
                problems.append("the trigger actions are not the registered ones")
            record = t2.decode(decision.memory.addon)
            if not record or record.get(t2.F_STATE) != t2.EMBARK_REQUESTED or [record[t2.F_INF], record[t2.F_CAR]] \
                    != chosen["pair"]:
                problems.append("the memory after the trigger is not EMBARK_REQUESTED for the registered pair")
            emb = [a for a in decision.actions if a.get("type") == t2.EMBARK]
            if len(emb) != 1 or {k2: v for k2, v in emb[0].items() if k2 not in ("actor", "obj_id", "type")} \
                    != chosen["option"]:
                problems.append("the embark action is not a copy of the listed option")
            diff = sp.unregistered_differences(v2.actions, decision.actions, "READY", "EMBARK_REQUESTED",
                                               tuple(chosen["pair"]))
            problems.extend(diff)
        memory = decision.memory
    print(f"rehearsal over decisions 0..{k}: {'PASS' if not problems else 'FAIL'}")
    for p in problems[:20]:
        print("  ", p)
    return 0 if not problems else 1


# ------------------------------------------------------------------------------------------------
# inputs (registration) and the post-game analysis (results)

INPUTS = PUBLIC / "inputs.json"
GAMES_OUT = PUBLIC / "games.json"
MECHANISM = PUBLIC / "mechanism.json"
DISPOSITION = PUBLIC / "disposition.json"
WORK = LOCAL_EVAL / sp.CARD_ID
ANALYSIS_PRIVATE = PRIVATE / "analysis-private.json"
LEDGER = REPO_ROOT / "local" / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"


def load_script(name: str) -> Any:
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"s22_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inputs() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import manifest as mf
    card = load_script("build_s22_card").build()
    witness_public = json.loads(WITNESS.read_text(encoding="utf-8"))
    corpus_pins = [{"folder": e["folder"], "game": e["game"], "tier": e["tier"],
                    "files": {k: {"file": p.relative_to(REPO_ROOT).as_posix(), "sha256": sha256(p)}
                              for k, p in sorted(e["files"].items())}} for e in corpus()]
    return {"schema": sp.SCHEMA + "/inputs", "study_id": sp.STUDY_ID, "card_id": sp.CARD_ID,
            "card_canonical_sha256": mf.digest(card), "candidate": sp.CANDIDATE_ID,
            "candidate_policy_source_sha256": sp.CANDIDATE_DIGEST, "rules_sha256": sp.rules_digest(),
            "corpus": corpus_pins, "s21_inputs_sha256": sha256(S21_INPUTS),
            "semantics_sha256": sha256(SEMANTICS), "witness_sha256": sha256(WITNESS),
            "witness_reference_sha256": sha256(REFERENCE), "selected_witness": witness_public["selected"],
            "expected_sessions": list(sp.EXPECTED_SESSIONS), "ledger_base_session": sp.LEDGER_BASE_SESSION}


def read_ledger() -> List[Dict[str, Any]]:
    """The ledger up to the last authorized session (2796), so that the public files regenerate after later sprints'
    sessions; the runner and the game entry point audit the whole live ledger, and the close-out verifies separately
    that no session after 2796 was opened in this sprint."""
    records = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in records if r.get("session") is None or int(r["session"]) <= sp.EXPECTED_SESSIONS[-1]]


def analyse() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """games.json, mechanism.json, disposition.json and the private analysis, from the record and captures."""
    the_card = json.loads((REPO_ROOT / "evaluation" / sp.CARD_ID / "manifest.json").read_text(encoding="utf-8"))
    game_entry = load_script("run_s22_game")
    entry = the_card["games"][0]
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))["selected"]
    problems: List[str] = []
    stops = game_entry.recorded_stops(the_card, entry, WORK)
    audit = sp.ledger_audit(read_ledger(), the_card)
    for code, found in audit["problems"].items():
        stops.setdefault(code, []).extend(found)
    codes = sp.structural_stops(stops)
    problems.extend(f"{c}: {p}" for c in codes for p in stops[c])
    record = json.loads((WORK / "games" / f"{entry['game_id']}.json").read_text(encoding="utf-8"))
    timeline = json.loads((WORK / "capture" / f"{entry['game_id']}.timeline.json").read_text(encoding="utf-8"))
    with (WORK / "capture" / f"{entry['game_id']}.timeline.pkl").open("rb") as handle:
        windows = pickle.load(handle)
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == sp.CANDIDATE_ID)
    faction = next(s["faction"] for s in record["seats"] if s["policy"] == sp.CANDIDATE_ID)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    steps = timeline["steps"]
    if [s["k"] for s in samples] != list(range(len(steps))):
        problems.append("the timeline does not hold one snapshot per decision")
    scenario = entry["scenario_id"]
    map_id = next(s["map_id"] for s in the_card["scenarios"] if s["scenario_id"] == scenario)
    costs = MoveCosts.from_raw(sdk_data.load_inputs(WORK / "data" / scenario / "Data", scenario, map_id).cost,
                               Origin.ENGINE, "setup_info.cost_data")
    # offline re-derivation from an empty memory (section 20)
    from miaosuan_agent.decision import Memory
    from miaosuan_agent.evaluation import s22_capture as cap
    base_memory: Any = Memory()
    addon_memory: Tuple[Tuple[int, int], ...] = ()
    raws, submitted, feedback, states, differences = [], [], [], [], 0
    memory_compared = 0
    for k, sample in enumerate(samples):
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        raw = pickle.loads(snap["observation"])
        live_memory = pickle.loads(snap["memory"])
        live_actions = [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]
        if cap.split_memory(live_memory) != (base_memory, addon_memory):
            problems.append(f"decision {k}: the carried memory differs from the offline chain")
        memory_compared += 1
        rebuilt = cap.reconstruct(raw, seat, faction, AddonMemory(base_memory, addon_memory), costs)
        if rebuilt["actions"] != rd.plain(live_actions):
            differences += 1
            problems.append(f"decision {k}: the live actions differ from the offline reconstruction")
        found = sp.unregistered_differences(rebuilt["baseline_actions"], live_actions, rebuilt["state_before"],
                                            rebuilt["state_after"], rebuilt["pair"])
        if found:
            problems.append(f"decision {k}: {found[0]}")
        base_memory, addon_memory = rebuilt["baseline_memory_out"], tuple(tuple(p) for p in rebuilt["memory_out"])
        raws.append(raw)
        submitted.append(live_actions)
        feedback.append([f for f in steps[k].get("feedback") or () if (f.get("message") or {}).get("actor") == seat])
        states.append((rebuilt["state_before"], rebuilt["state_after"], rebuilt["cur_step"]))
    live = cap.prefix_inputs(timeline, seat, reference["trigger_decision"])
    prefix = sp.prefix_problems({"trigger_decision": reference["trigger_decision"], "pair": reference["pair"],
                                 "trigger_actions": cap.actions_digest(reference["trigger_actions"])},
                                live["live"], live["baseline"], live["trigger_actions"], live["pair"])
    problems.extend(f"SP: {p}" for p in prefix)
    frames = [sp.Frame(raw, faction, seat) for raw in raws]
    facts = sp.transport_facts(frames, submitted, feedback, reference["pair"], reference["trigger_decision"])
    embark = sp.embark_endpoint(facts["embark"])
    carry = sp.carry_endpoint(facts["carry"]) if "carry" in facts else None
    stacking = sp.stacking_endpoint(facts["stacking"]) if "stacking" in facts else None
    disembark = sp.disembark_endpoint(facts["disembark"]) if "disembark" in facts else None
    verdict = sp.disposition(None, problems, embark, carry, stacking, disembark)
    # descriptive: the candidate's state sequence, the holds, the destination against the prediction, travel time
    sequence = []
    for before, after, cur in states:
        if after != (sequence[-1]["state"] if sequence else "READY"):
            sequence.append({"state": after, "cur_step": cur})
    holds = collections.Counter()
    for k in range(len(steps)):
        row = (steps[k].get("s22") or {}).get(str(seat)) or {}
        for change in row.get("changes") or ():
            c = json.loads(change)
            if c.get("kind") == "carrier-move-withheld":
                holds[c["state"]] += 1
    names = tl.labels({c["coord"]: c.get("value") for c in raws[0].get("cities") or ()})
    private = facts["private"]
    destination = private.get("destination")
    descriptive: Dict[str, Any] = {
        "candidate_states": sequence,
        "carrier_move_withheld_decisions": dict(sorted(holds.items())),
        "destination": names.get(destination) if destination is not None else None,
        "destination_equals_prediction": destination == reference["destination_hex"] if destination else None,
    }
    if private.get("route"):
        arrival = private["decisions"].get("arrival")
        car = next(u for u in raws[private["decisions"]["move"]]["operators"] if u["obj_id"] == reference["pair"][1])
        descriptive["carrier_route_free_flow"] = free_flow(ShootReservationPolicy(costs).router, car, private["route"])
        descriptive["release_to_arrival_steps"] = facts["carry"].get("release_to_arrival_steps")
        descriptive["infantry_foot_free_flow_to_destination_predicted"] = \
            sp.RULES["witness"]["infantry_free_flow_to_destination"]
        descriptive["arrival_cur_step"] = None if arrival is None else raws[arrival]["time"]["cur_step"]
    public_facts = {k: v for k, v in facts.items() if k != "private"}
    scores = record.get("final_scores") or {}
    games_public = {"schema": sp.SCHEMA + "/games", "study_id": sp.STUDY_ID, "game_id": entry["game_id"],
                    "session": record.get("session"), "status": record.get("status"), "steps": record.get("steps"),
                    "candidate_side": sp.candidate_side(entry), "structural_stops": codes,
                    "ledger_sessions_after_base": audit["sessions"], "decisions_reconstructed_offline": len(samples),
                    "memory_compared": memory_compared, "offline_differences": differences,
                    "live_consistency_errors": len(timeline.get("consistency_errors") or ()),
                    "live_unregistered_differences": len(timeline.get("unregistered_differences") or ()),
                    "prefix_problems": len(prefix),
                    "record_facts_not_used": {"scores": {k: scores.get(k) for k in sorted(scores)}}}
    mechanism_public = {"schema": sp.SCHEMA + "/mechanism", "study_id": sp.STUDY_ID, "facts": public_facts,
                        "endpoints": {"embark": embark, "carry": carry, "stacking": stacking, "disembark": disembark},
                        "descriptive": descriptive}
    disposition_public = {"schema": sp.SCHEMA + "/disposition", "study_id": sp.STUDY_ID, **verdict,
                          "order": list(sp.DISPOSITIONS)}
    private_out = {"facts": facts, "states": states, "problems": problems, "reference": reference}
    return games_public, mechanism_public, disposition_public, private_out


def result_private_values(reference: Mapping[str, Any], facts_private: Mapping[str, Any]) -> set:
    """The private values the result files are checked against: the selected witness's unit ids, hexes and paths and
    the live game's destination and route (the other corpus games' values cannot occur in facts about this game)."""
    selected = reference["selected"]
    values = private_values({"triggers": {selected["game"]: selected}})
    values.update(v for v in [facts_private.get("destination")] + list(facts_private.get("route") or ())
                  if v is not None)
    return values


def run(check: bool) -> int:
    games_public, mechanism_public, disposition_public, private_out = analyse()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    values = result_private_values(reference, private_out["facts"]["private"])
    for name, data in (("games", games_public), ("mechanism", mechanism_public), ("disposition", disposition_public)):
        found = sp.public_check(data, values)
        if found:
            print(f"REFUSED: public {name} fails the privacy check: {found[:5]}", file=sys.stderr)
            return 1
    ok = True
    if not check:
        PRIVATE.mkdir(parents=True, exist_ok=True)
        ANALYSIS_PRIVATE.write_text(json.dumps(private_out, indent=1, sort_keys=True, default=repr) + "\n",
                                    encoding="utf-8")
    for path, data in ((GAMES_OUT, games_public), (MECHANISM, mechanism_public), (DISPOSITION, disposition_public)):
        ok = write_or_check(path, sp.dump(data), check) and ok
    print(f"disposition {disposition_public['disposition']}")
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------


def write_or_check(path: Path, text: str, check: bool) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if check:
        same = path.exists() and path.read_text(encoding="utf-8") == text
        print(f"{'OK' if same else 'MISMATCH'} {rel}")
        return same
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {rel}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("semantics", "witness", "inputs", "run"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    sub.add_parser("rehearse")
    args = parser.parse_args()
    if args.command == "inputs":
        data = inputs()
        problems = sp.public_check(data, private_values(json.loads(REFERENCE.read_text(encoding="utf-8"))))
        if problems:
            print(f"REFUSED: public inputs fail the privacy check: {problems[:5]}", file=sys.stderr)
            return 1
        return 0 if write_or_check(INPUTS, sp.dump(data), args.check) else 1
    if args.command == "run":
        return run(args.check)
    if args.command == "semantics":
        data = semantics()
        problems = sp.public_check(data)
        if problems:
            print(f"REFUSED: public semantics fail the privacy check: {problems[:5]}", file=sys.stderr)
            return 1
        return 0 if write_or_check(SEMANTICS, sp.dump(data), args.check) else 1
    if args.command == "witness":
        public, reference = witness()
        problems = sp.public_check(public, private_values(reference))
        if problems:
            print(f"REFUSED: public witness file fails the privacy check: {problems[:5]}", file=sys.stderr)
            return 1
        ok = write_or_check(REFERENCE, sp.dump(reference), args.check)
        ok = write_or_check(WITNESS, sp.dump(public), args.check) and ok
        return 0 if ok else 1
    return rehearse()


if __name__ == "__main__":
    sys.exit(main())
