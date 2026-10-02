"""Analyses of the registered PS-1 engine probe ``ps1-engine-probe-1`` (``docs/PS1_ENGINE_PROBE.md``).

    PYTHON scripts/ps1_probe_analysis.py p1 [--work DIR] [--sprint2 DIR] [--private DIR] [--public DIR]
    PYTHON scripts/ps1_probe_analysis.py p2 [--work DIR] [--private DIR] [--public DIR]
    PYTHON scripts/ps1_probe_analysis.py gates [--public DIR] [--t1r DIR] [--private DIR]

``p1`` judges E1 to E4 on the P1 game (the hooked split candidate in 1910631192 C3), checks its premise against the
Sprint 2 split-game record, re-decides every pre-trigger snapshot offline, recomputes the trigger with the Sprint 3
functions, and reports the secondary outcomes and the descriptive M1c replay P1-S. ``p2`` judges the frozen M1c model
on the P2 game (fidelity F1, the surrogate F2, the targeted claims T-a to T-e, the keep flag, the trigger census).
``gates`` applies the registered gate rules to the two public outputs. Every rule is the registered one
(``evaluation/ps1-engine-probe-1/manifest.json``); this file implements it and refuses to run when its cross-checks
disagree. Private outputs (unit ids, hexes) go to ``--private`` (default ``local/diagnostics/ps1-probe``); the public
outputs hold counts, step indices and verdicts only.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, NamedTuple, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import INERT_ID, digest  # noqa: E402
from miaosuan_agent.decision.routing import ROADBLOCKED_MODES, move_mode  # noqa: E402
from miaosuan_agent.evaluation import effects  # noqa: E402
from miaosuan_agent.evaluation import ps1_model as pm  # noqa: E402
from miaosuan_agent.evaluation import ps1_probe as pp  # noqa: E402
from miaosuan_agent.evaluation.refusals import same_action  # noqa: E402
from miaosuan_agent.evaluation.residual516 import plain  # noqa: E402
from miaosuan_agent.experiments import ps1_probe_hook as hook  # noqa: E402
from miaosuan_agent.experiments.deployment_split import DeploymentSplitPolicy  # noqa: E402


def _load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


study = _load_script("ps1_study")
posthoc = _load_script("ps1_posthoc")

GROUND = (1, 2)
AIRCRAFT = 3
MOVE, SHOOT, OCCUPY, STOP = 1, 2, 5, 10
K = pp.K


class Refused(SystemExit):
    """The analysis refuses to produce a verdict (a cross-check disagreed or an input is incomplete)."""


def refuse(message: str) -> None:
    raise Refused(f"REFUSED: {message}")


def canonical(value: Any) -> str:
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"))


# ----------------------------------------------------------------------------------------------
# rows and tables (two channels, extracted by separate code)


class Row(NamedTuple):
    hex: int
    path: Tuple[int, ...]
    speed: Any
    keep: Any
    move_state: Any
    basic_speed: Any
    type: int
    stop: Any
    mtsrt: Any
    can_to_move: Any
    actions: FrozenSet[int]


def _row(record: Mapping[str, Any], listed: Any) -> Row:
    return Row(int(record["cur_hex"]), tuple(int(h) for h in (record.get("move_path") or ())), record.get("speed"),
               record.get("keep"), record.get("move_state"), record.get("basic_speed"), int(record["type"]),
               record.get("stop"), record.get("move_to_stop_remain_time"), record.get("can_to_move"),
               frozenset(int(t) for t in (listed or {})))


def rows_b(observation: Mapping[str, Any], seat: int) -> Dict[int, Row]:
    """Channel B, the seat observation: units listed for the seat, of a ground type, not on board."""
    info = observation.get("role_and_grouping_info") or {}
    listed = set((info.get(seat) or info.get(str(seat)) or {}).get("operators") or ())
    valid = observation.get("valid_actions") or {}
    out: Dict[int, Row] = {}
    for record in observation.get("operators") or ():
        oid = record.get("obj_id")
        if oid in listed and record.get("type") in GROUND and record.get("on_board") in (0, None, False):
            out[oid] = _row(record, valid.get(oid))
    return out


def rows_a(state: Mapping[str, Any], faction: int) -> Dict[int, Row]:
    """Channel A, the all-seeing state: units of the seat's colour, of a ground type, not on board."""
    valid = state.get("valid_actions") or {}
    return {int(r["obj_id"]): _row(r, valid.get(r["obj_id"])) for r in state.get("operators") or ()
            if r.get("color") == faction and r.get("type") in GROUND and not r.get("on_board")}


class Tables(NamedTuple):
    ks: List[int]
    b: Dict[int, Dict[int, Row]]
    a: Dict[int, Dict[int, Row]]
    cur_step: Dict[int, int]
    stage: Dict[int, int]
    cities: Dict[int, Dict[int, Tuple[int, int]]]  # k -> objective hex -> (value, flag)
    aircraft: Dict[int, int]
    passengers: Dict[int, int]
    roadblocks: FrozenSet[int]


class Game:
    """One probe game: record, compact log, snapshots (one per decision from index 1)."""

    def __init__(self, record: Mapping[str, Any], compact: Mapping[str, Any], windows: Mapping[str, Any]) -> None:
        self.record, self.compact = record, compact
        self.steps: List[Mapping[str, Any]] = list(compact["steps"])
        self.samples: Dict[int, Mapping[str, Any]] = {s["k"]: s for s in windows["samples"]}
        seat = next(s for s in record["seats"] if s["policy"] != INERT_ID)
        self.seat, self.faction, self.policy = seat["seat"], seat["faction"], seat["policy"]
        self.seat_record = seat
        self.colour = "red" if self.faction == 0 else "blue"

    @classmethod
    def read(cls, work: Path, game_id: str) -> "Game":
        record = json.loads((work / "games" / f"{game_id}.json").read_text(encoding="utf-8"))
        compact = json.loads((work / "capture" / f"{game_id}.capture.json").read_text(encoding="utf-8"))
        windows = pickle.loads((work / "capture" / f"{game_id}.windows.pkl").read_bytes())
        return cls(record, compact, windows)

    def require_complete(self) -> List[int]:
        expected = list(range(1, len(self.steps)))
        if sorted(self.samples) != expected:
            missing = sorted(set(expected) - set(self.samples))
            refuse(f"I2: snapshots missing at {len(missing)} decisions (first {missing[:5]})")
        return expected

    def entry(self, k: int) -> Mapping[str, Any]:
        seats = self.samples[k]["seats"]
        return seats.get(self.seat) or seats[str(self.seat)]

    def observation(self, k: int) -> Mapping[str, Any]:
        return pickle.loads(self.entry(k)["observation"])

    def global_state(self, k: int) -> Mapping[str, Any]:
        return pickle.loads(self.samples[k]["global"])

    def tables(self) -> Tables:
        ks = self.require_complete()
        b, a, cur, stage, cities, air, pas = {}, {}, {}, {}, {}, {}, {}
        roadblocks: FrozenSet[int] = frozenset()
        for k in ks:
            obs, state = self.observation(k), self.global_state(k)
            b[k], a[k] = rows_b(obs, self.seat), rows_a(state, self.faction)
            cur[k], stage[k] = int(obs["time"]["cur_step"]), int(obs["time"]["stage"])
            cities[k] = {int(c["coord"]): (int(c["value"]), int(c["flag"])) for c in obs.get("cities") or ()}
            air[k] = sum(1 for r in obs.get("operators") or () if r.get("color") == self.faction
                         and r.get("type") == AIRCRAFT and not r.get("on_board"))
            pas[k] = sum(1 for r in obs.get("passengers") or () if r.get("color") == self.faction)
            roadblocks = roadblocks | frozenset(Observation.from_raw(obs, Origin.ENGINE).roadblocks() or ())
        return Tables(ks, b, a, cur, stage, cities, air, pas, roadblocks)

    def first_play_k(self) -> int:
        return next(s["k"] for s in self.steps if s.get("stage") == 2)


# ----------------------------------------------------------------------------------------------
# submitted actions and fresh feedback


def fresh_feedback(steps: Sequence[Mapping[str, Any]]) -> Dict[int, List[Mapping[str, Any]]]:
    """Per step, the feedback entries not already reported at the previous step while the clock stood still."""
    out: Dict[int, List[Mapping[str, Any]]] = {}
    previous = None
    for step in steps:
        entries = list(step["feedback"])
        if previous is not None and step["cur_step"] == previous["cur_step"]:
            pool = collections.Counter(canonical(e) for e in previous["feedback"])
            fresh = []
            for entry in entries:
                key = canonical(entry)
                if pool[key] > 0:
                    pool[key] -= 1
                else:
                    fresh.append(entry)
            entries = fresh
        out[step["k"]] = entries
        previous = step
    return out


class Action(NamedTuple):
    k: int
    j: int
    submitted: Mapping[str, Any]  # pre-execution copy
    serialised: Mapping[str, Any]  # the batch entry serialised after the step
    codes: Tuple[Any, ...]  # error codes of the matching fresh feedback entries (None: no error)


def seat_actions(game: Game, fresh: Mapping[int, List[Mapping[str, Any]]]) -> List[Action]:
    """Every action of the policy seat, pre-execution, paired with its serialised form and its fresh feedback."""
    out: List[Action] = []
    for step in game.steps:
        submitted = [s for s in step.get("submitted", ()) if s["seat"] == game.seat]
        batch = [b for b in step["batch"] if b["seat"] == game.seat]
        if "submitted" not in step:
            refuse(f"k {step['k']}: the capture holds no pre-execution copy of the actions")
        if len(submitted) != len(batch) or [s["j"] for s in submitted] != [b["j"] for b in batch]:
            refuse(f"k {step['k']}: submitted and serialised actions do not pair up")
        for s, b in zip(submitted, batch):
            codes = tuple(effects.feedback_error_code(e) for e in fresh.get(step["k"], ())
                          if same_action(e.get("message") or {}, b["action"]))
            out.append(Action(step["k"], s["j"], s["action"], b["action"], codes))
    return out


def check_counts(game: Game, actions: Sequence[Action]) -> Dict[str, Any]:
    """I3: submitted actions by type against the record's own count (taken before the engine step)."""
    mine = collections.Counter(str(a.submitted.get("type")) for a in actions)
    recorded = {k: v for k, v in game.seat_record["actions_by_type"].items() if v}
    if dict(mine) != recorded:
        refuse(f"I3: submitted actions by type {dict(mine)} differ from the record's {recorded}")
    rewritten = sum(1 for a in actions if canonical(a.submitted) != canonical(a.serialised))
    return {"by_type": dict(sorted(mine.items())), "rewritten_in_place": rewritten,
            "with_error_feedback": sum(1 for a in actions if any(c is not None for c in a.codes)),
            "without_feedback_entry": sum(1 for a in actions if not a.codes)}


def accepted(action: Action) -> bool:
    return not any(code is not None for code in action.codes)


def record_check(game: Game, manifest: Mapping[str, Any], policy: str) -> Dict[str, Any]:
    """I1: completion, registered digests, runtime, capture settings, observer errors, replay checks."""
    record = game.record
    problems = []
    if record.get("status") != "COMPLETED" or not record.get("done"):
        problems.append(f"status {record.get('status')}")
    harness = record.get("harness") or {}
    for name, entry in manifest["policies"].items():
        if name in (harness.get("policy_sources") or {}) and harness["policy_sources"][name] != entry["policy_source"]["sha256"]:
            problems.append(f"policy digest of {name}")
    if game.policy != policy:
        problems.append(f"policy {game.policy}")
    if harness.get("runtime") != manifest["execution"]["runtime"]:
        problems.append(f"runtime {harness.get('runtime')}")
    if (harness.get("capture") or {}).get("sample_every") != pp.SAMPLE_EVERY:
        problems.append("capture setting")
    if record.get("observer_errors"):
        problems.append(f"{len(record['observer_errors'])} observer errors")
    if harness.get("dirty"):
        problems.append("the harness tree was dirty")
    seat = game.seat_record
    if seat["replay_mismatches"] or not seat["replay_checks"]:
        problems.append(f"replay checks {seat['replay_checks']}, mismatches {seat['replay_mismatches']}")
    return {"ok": not problems, "problems": problems, "steps": record.get("steps"),
            "session": record.get("session"), "harness_commit": harness.get("commit"),
            "harness_dirty": harness.get("dirty"), "replay_checks": seat["replay_checks"],
            "replay_mismatches": seat["replay_mismatches"], "contract_errors": seat["contract_errors"],
            "gate_rejections": sum(seat["gate_rejections"].values()),
            "feedback_errors_by_code_and_type": seat["feedback_errors_by_code_and_type"]}


def channel_agreement(t: Tables, units: Optional[Set[int]] = None) -> Dict[str, Any]:
    """I4: both channels list the same units with the same hex and remaining path (all of them, or ``units``)."""
    disagreements, steps = 0, 0
    first = None
    for k in t.ks:
        a = {u: (r.hex, r.path) for u, r in t.a[k].items() if units is None or u in units}
        b = {u: (r.hex, r.path) for u, r in t.b[k].items() if units is None or u in units}
        if a != b:
            disagreements += len(set(a.items()) ^ set(b.items()))
            steps += 1
            first = first if first is not None else k
    return {"disagreeing_unit_entries": disagreements, "steps_with_disagreement": steps, "first_k": first}


def max_occupancy(t: Tables) -> Dict[str, int]:
    out = {}
    for name, channel in (("seat observation", t.b), ("all-seeing state", t.a)):
        out[name] = max((max(collections.Counter(r.hex for r in rows.values()).values(), default=0)
                         for rows in channel.values()), default=0)
    return out


def edges_of(costs: MoveCosts) -> Dict[int, pm.Edges]:
    return {int(m): costs.edges[m] for m in range(len(costs.edges))}


def load_costs(work: Path, manifest: Mapping[str, Any], scenario: str) -> MoveCosts:
    entry = next(s for s in manifest["scenarios"] if s["scenario_id"] == scenario)
    path = sdk_data.map_paths(work / "data" / scenario / "Data", entry["map_id"])["cost"]
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry["inputs_sha256"]["cost"]:
        refuse(f"{path} does not match the manifest's cost digest")
    return MoveCosts.from_raw(sdk_data.load_cost(path), Origin.ENGINE)


# ----------------------------------------------------------------------------------------------
# M1c replay (F1, F2, P1-S)


def observed_entries(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int], k0: int) -> List[Tuple[int, int, int]]:
    out = []
    for prev, k in zip(ks, ks[1:]):
        if k <= k0:
            continue
        for uid, row in channel[k].items():
            before = channel[prev].get(uid)
            if before is not None and before.hex != row.hex:
                out.append((k, uid, row.hex))
    return out


def removals(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int], k0: int) -> Dict[int, List[int]]:
    out: Dict[int, List[int]] = collections.defaultdict(list)
    for prev, k in zip(ks, ks[1:]):
        if k > k0:
            for uid in sorted(set(channel[prev]) - set(channel[k])):
                out[k].append(uid)
    return dict(out)


def appearances(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int], k0: int) -> Dict[int, List[int]]:
    out: Dict[int, List[int]] = collections.defaultdict(list)
    for prev, k in zip(ks, ks[1:]):
        if k > k0:
            for uid in sorted(set(channel[k]) - set(channel[prev])):
                out[k].append(uid)
    return dict(out)


def model_unit(uid: int, r: Row) -> pm.Unit:
    return pm.Unit(uid=uid, hex=r.hex, speed=float(r.basic_speed), mode=int(move_mode(r.type, r.move_state)), path=r.path,
                   waiting=bool(r.path))


class Replay(NamedTuple):
    entries: List[Tuple[int, int, int]]
    orders: List[Tuple[int, int, int]]  # (k, uid, destination) predicted (surrogate) or applied (replay)
    occupations: List[Tuple[int, int, int]]  # (k, uid, hex)
    inapplicable: Dict[str, int]
    error: Optional[str]
    start: Dict[int, int]
    modes: Dict[int, int]


def replay(t: Tables, k0: int, edges: Mapping[int, pm.Edges], faction: int,
           orders: Optional[Mapping[int, Sequence[Tuple[str, int, Tuple[int, ...]]]]] = None,
           surrogate: bool = False) -> Replay:
    """The frozen M1c model (M1b timing, wait at entry, ascending processing) from the observed state at ``k0`` up to
    the last snapshot: recorded orders (``orders``) or the M7 surrogate, plus the observed removals as inputs."""
    start_rows = t.b[k0]
    if any(r.path and (r.speed or 0) != 0 for r in start_rows.values()):
        refuse(f"k {k0}: a unit is traversing at the start of the replay (its timing is not observed)")
    units = [model_unit(uid, r) for uid, r in sorted(start_rows.items())]
    modes = {u.uid: u.mode for u in units}
    blocked = {int(m): t.roadblocks for m in ROADBLOCKED_MODES}
    sim = pm.Simulation(units=units, edges_by_mode=edges, step=k0, faction=faction, end_step=t.ks[-1],
                        objectives={h: flag for h, (_, flag) in t.cities[k0].items()}, blocked_by_mode=blocked,
                        restart_after_wait=True, wait_at_entry=True)
    gone, new = removals(t.b, t.ks, k0), appearances(t.b, t.ks, k0)
    skipped: collections.Counter = collections.Counter()
    occupations: List[Tuple[int, int, int]] = []
    start = {uid: r.hex for uid, r in start_rows.items()}

    def policy(s: pm.Simulation) -> None:
        for uid in gone.get(s.step, ()):
            s.units = [u for u in s.units if u.uid != uid]
        for uid in new.get(s.step, ()):
            r = t.b[s.step][uid]
            if r.path and (r.speed or 0) != 0:
                skipped["appeared while traversing (timing not observed)"] += 1
                continue
            s.units = s.units + [model_unit(uid, r)]
            modes[uid] = int(move_mode(r.type, r.move_state))
            start.setdefault(uid, r.hex)
        present = {u.uid for u in s.units}
        if surrogate:
            before = len(s.events)
            pm.surrogate(s)
            occupations.extend((e.step, e.uid, s.unit(e.uid).hex) for e in s.events[before:] if e.kind == "occupy")
            return
        for kind, uid, path in (orders or {}).get(s.step, ()):
            if uid not in present:
                skipped[f"{kind}: unit not in the model"] += 1
                continue
            try:
                if kind == "move":
                    s.order_move(uid, path)
                elif kind == "stop":
                    s.order_stop(uid)
                elif kind == "occupy":
                    s.occupy(uid)
                    occupations.append((s.step, uid, s.unit(uid).hex))
            except pm.ModelError:
                skipped[f"{kind}: not applicable in the model state"] += 1

    error = None
    try:
        sim.run(policy)
    except pm.ModelError as exc:
        error = str(exc)
    entries = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "enter"]
    predicted = [(e.step, e.uid, e.detail[0]) for e in sim.events if e.kind == "order"]
    return Replay(entries, predicted, occupations, dict(skipped), error, start, modes)


def validate(start: Mapping[int, int], entries: Sequence[Tuple[int, int, int]], gone: Mapping[int, Sequence[int]],
             new: Mapping[int, Sequence[int]], new_hexes: Mapping[int, int], adjacent: Any) -> List[str]:
    """The predicted entries re-checked against the stacking limit and adjacency, independently of the simulator, with
    the observed removals and appearances applied as inputs after the entries of their step (as the replay applies
    them); an input itself is never a violation. Without inputs it must equal ``pm.validate_trajectory``."""
    pos = dict(start)
    occ = collections.Counter(pos.values())
    problems = [f"start: a hex holds {n} ground units" for h, n in sorted(occ.items()) if n > K]
    events = [(k, 0, uid, h) for k, uid, h in entries] + [(k, 1, uid, None) for k, us in gone.items() for uid in us]         + [(k, 1, uid, new_hexes[uid]) for k, us in new.items() for uid in us]
    for k, kind, uid, h in sorted(events, key=lambda e: (e[0], e[1])):
        if kind == 1:
            if h is None:
                occ[pos.pop(uid)] -= 1
            else:
                pos[uid] = h
                occ[h] += 1
            continue
        if not adjacent(uid, pos[uid], h):
            problems.append(f"step {k}: unit {uid} moved to a non-adjacent hex")
        if occ[h] >= K:
            problems.append(f"step {k}: unit {uid} entered a hex already holding {occ[h]}")
        occ[pos[uid]] -= 1
        occ[h] += 1
        pos[uid] = h
    if not gone and not new:
        frozen = pm.validate_trajectory(start, list(entries), adjacent, {})
        if frozen != problems:
            refuse("the trajectory validators disagree")
    return problems


def offsets(simulated: Sequence[Tuple[int, int, int]], observed: Sequence[Tuple[int, int, int]]) -> collections.Counter:
    """Simulated minus observed step of every entry of the units whose hex sequences agree."""
    obs, sim = collections.defaultdict(list), collections.defaultdict(list)
    for k, u, h in observed:
        obs[u].append((k, h))
    for k, u, h in simulated:
        sim[u].append((k, h))
    out: collections.Counter = collections.Counter()
    for u in set(obs) | set(sim):
        if [h for _, h in obs[u]] == [h for _, h in sim[u]]:
            for (ko, _), (ks, _) in zip(obs[u], sim[u]):
                out[ks - ko] += 1
    return out


def mismatch_conditions(t: Tables, simulated: Sequence[Tuple[int, int, int]], observed: Sequence[Tuple[int, int, int]],
                        units: Iterable[int], refused_units: Set[int]) -> List[Dict[str, Any]]:
    """For each mismatched unit, its first differing entry and the conditions around it (private)."""
    obs, sim = collections.defaultdict(list), collections.defaultdict(list)
    for k, u, h in observed:
        obs[u].append((k, h))
    for k, u, h in simulated:
        sim[u].append((k, h))
    rows = []
    for u in sorted(units):
        o, s = obs[u], sim[u]
        i = next((j for j, (a, b) in enumerate(zip(o, s)) if a[1] != b[1]), min(len(o), len(s)))
        k = o[i][0] if i < len(o) else (s[i][0] if i < len(s) else t.ks[-1])
        prev = max((x for x in t.ks if x < k), default=t.ks[0])
        contested = (o[i][1] if i < len(o) else s[i][1]) if (i < len(o) or i < len(s)) else None
        occ = collections.Counter(r.hex for r in t.b[prev].values())
        window = [x for x in t.ks if k - 50 <= x <= k]
        rows.append({"unit": u, "index": i, "observed": o[i] if i < len(o) else None,
                     "simulated": s[i] if i < len(s) else None,
                     "observed_entries": len(o), "simulated_entries": len(s),
                     "contested_occupancy_before": occ.get(contested, 0) if contested is not None else None,
                     "contenders_before": sum(1 for r in t.b[prev].values() if r.path and r.path[0] == contested),
                     "keep_set_in_window": any(t.b[x].get(u) and t.b[x][u].keep for x in window),
                     "move_state_changes": len({t.b[x][u].move_state for x in t.ks if u in t.b[x]}) - 1,
                     "basic_speed_changes": len({t.b[x][u].basic_speed for x in t.ks if u in t.b[x]}) - 1,
                     "had_refused_order": u in refused_units})
    return rows


def fidelity_f1(t: Tables, k0: int, edges: Mapping[int, pm.Edges], faction: int,
                orders: Mapping[int, Sequence[Tuple[str, int, Tuple[int, ...]]]], refused_units: Set[int]) -> Dict[str, Any]:
    run = replay(t, k0, edges, faction, orders=orders)
    observed = observed_entries(t.b, t.ks, k0)
    cmp = study.compare_entries(run.entries, observed, k0)
    off = offsets(run.entries, observed)
    new = appearances(t.b, t.ks, k0)
    violations = validate({u: r.hex for u, r in t.b[k0].items()}, run.entries, removals(t.b, t.ks, k0), new,
                          {u: t.b[k][u].hex for k, us in new.items() for u in us},
                          lambda uid, a, b: b in edges[run.modes[uid]].get(a, {}))
    occupancy = max_occupancy(t)
    eligible = set().union(*(set(t.b[k]) for k in t.ks if k >= k0))
    compared = set(u for _, u, _ in observed) | set(u for _, u, _ in run.entries)
    accounting = {"eligible_units": len(eligible), "units_with_entries": len(compared),
                  "units_outside_population": len(compared - eligible),
                  "steps_compared": t.ks[-1] - k0, "model_error": run.error,
                  "orders_not_applicable": run.inapplicable}
    complete = (run.error is None and not run.inapplicable and not (compared - eligible))
    passed = (cmp["hex_sequences_differ"] == 0 and cmp["worst_step_offset"] <= pp.F1_TOLERANCE and not violations
              and max(occupancy.values()) <= K and complete)
    mismatched = cmp["private"]["mismatched_units"]
    return {"pass": passed, "hex_sequences_differ": cmp["hex_sequences_differ"],
            "worst_step_offset": cmp["worst_step_offset"], "observed_entries": cmp["observed_entries"],
            "simulated_entries": cmp["simulated_entries"],
            "offset_histogram": {str(k): v for k, v in sorted(off.items())},
            "entries_within_tolerance": sum(v for k, v in off.items() if abs(k) <= pp.F1_TOLERANCE),
            "capacity_or_adjacency_violations": len(violations), "max_observed_occupancy": occupancy,
            "accounting": accounting, "accounting_complete": complete,
            "private": {"mismatched": mismatch_conditions(t, run.entries, observed, mismatched, refused_units),
                        "violations": violations[:20]}}


def fidelity_f2(t: Tables, k0: int, edges: Mapping[int, pm.Edges], faction: int,
                recorded_moves: Sequence[Tuple[int, int, int]], recorded_occupations: Sequence[Tuple[int, int, int]]) -> Dict[str, Any]:
    run = replay(t, k0, edges, faction, surrogate=True)
    observed = observed_entries(t.b, t.ks, k0)
    cmp = study.compare_entries(run.entries, observed, k0)
    matched = [r for r in recorded_moves if any(r[1] == s[1] and r[2] == s[2] and abs(r[0] - s[0]) <= 1 for s in run.orders)]
    extra = [s for s in run.orders if not any(r[1] == s[1] and r[2] == s[2] and abs(r[0] - s[0]) <= 1 for r in recorded_moves)]
    occ_matched = [r for r in recorded_occupations if any(r[2] == s[2] and abs(r[0] - s[0]) <= 1 for s in run.occupations)]
    occ_extra = [s for s in run.occupations if not any(r[2] == s[2] and abs(r[0] - s[0]) <= 1 for r in recorded_occupations)]
    passed = (run.error is None and cmp["hex_sequences_differ"] == 0 and cmp["worst_step_offset"] <= 1
              and len(matched) == len(recorded_moves) and not extra
              and len(occ_matched) == len(recorded_occupations) and not occ_extra)
    return {"pass": passed, "hex_sequences_differ": cmp["hex_sequences_differ"],
            "worst_step_offset": cmp["worst_step_offset"], "model_error": run.error,
            "orders": {"recorded": len(recorded_moves), "recorded_matched": len(matched),
                       "predicted": len(run.orders), "predicted_unmatched": len(extra)},
            "occupations": {"recorded": len(recorded_occupations), "recorded_matched": len(occ_matched),
                            "predicted": len(run.occupations), "predicted_unmatched": len(occ_extra),
                            "recorded_steps": sorted(r[0] for r in recorded_occupations),
                            "predicted_steps": sorted(s[0] for s in run.occupations)}}


# ----------------------------------------------------------------------------------------------
# targeted claims (computed from one channel's table; run on both channels and compared)


def _occ(rows: Mapping[int, Row]) -> collections.Counter:
    return collections.Counter(r.hex for r in rows.values())


def _ordered_occupancy(prev: Mapping[int, Row], cur: Mapping[int, Row], order: Sequence[int]) -> Dict[int, collections.Counter]:
    occ = _occ(prev)
    seen = {}
    for uid in order:
        if cur[uid].hex != prev[uid].hex:
            occ[prev[uid].hex] -= 1
            occ[cur[uid].hex] += 1
        seen[uid] = collections.Counter(occ)
    return seen


def entry_events(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int]) -> Dict[str, Any]:
    """T-a, T-e(1), the general entry rule and its keep-flag exceptions."""
    counts: collections.Counter = collections.Counter()
    ta: List[Tuple[int, int, bool]] = []  # (k, uid, as predicted)
    te: List[Tuple[int, int, bool]] = []
    for prev_k, k in zip(ks, ks[1:]):
        prev, cur = channel[prev_k], channel[k]
        if set(prev) != set(cur):
            counts["transitions skipped: the unit set changed"] += 1
            continue
        asc = _ordered_occupancy(prev, cur, sorted(cur))
        desc = _ordered_occupancy(prev, cur, sorted(cur, reverse=True))
        end, start = _occ(cur), _occ(prev)
        for uid, row in sorted(cur.items()):
            if row.hex == prev[uid].hex or not row.path:
                continue
            nh = row.path[0]
            waited = (row.speed or 0) == 0
            counts["entries with a path left"] += 1
            counts["waited at once" if waited else "started"] += 1
            full = {"ascending": asc[uid][nh] >= K, "descending": desc[uid][nh] >= K, "end of step": end[nh] >= K}
            for name, value in full.items():
                counts[f"{name} agrees" if value == waited else f"{name} disagrees"] += 1
            if full["ascending"] != waited:
                counts["ascending disagreements with the keep flag set" if row.keep else
                       "ascending disagreements without the keep flag"] += 1
            if row.keep:
                counts["entries with the keep flag set"] += 1
                continue
            left = any(prev[v].hex == nh and cur[v].hex != nh for v in cur)
            if start[nh] >= K and end[nh] >= K and not left:
                ta.append((k, uid, waited))
            if len(set(full.values())) > 1:
                te.append((k, uid, full["ascending"] == waited))
    return {"counts": dict(sorted(counts.items())), "T-a": ta, "T-e1": te}


def tau_of(row: Row, target: int, edges: Mapping[int, pm.Edges]) -> Optional[int]:
    mode = move_mode(row.type, row.move_state)
    cost = edges[int(mode)].get(row.hex, {}).get(target) if mode is not None else None
    return None if cost is None else pm.hex_time(float(row.basic_speed), cost)


def episodes(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int], edges: Mapping[int, pm.Edges]) -> List[Dict[str, Any]]:
    """Blocked-wait episodes: a unit with a path at speed 0 in front of a hex holding K own ground units, keeping its
    path (or its tail after an entry), until it enters that hex; per step its speed, the hex's occupancy and its keep
    flag, move_state and basic_speed. Episodes ended by a path change or the unit's absence are excluded."""
    out: List[Dict[str, Any]] = []
    open_: Dict[int, Dict[str, Any]] = {}
    for k in ks:
        rows = channel[k]
        occ = _occ(rows)
        for uid, ep in list(open_.items()):
            r = rows.get(uid)
            if r is None or r.path not in (ep["path"], ep["path"][1:]):
                out.append(dict(ep, end=k, outcome="excluded: path changed or unit absent"))
                del open_[uid]
                continue
            if r.hex == ep["target"]:
                out.append(dict(ep, end=k, outcome="entered"))
                del open_[uid]
                continue
            ep["steps"].append((k, r.speed, occ[ep["target"]], bool(r.keep), r.move_state, r.basic_speed))
        for uid, r in rows.items():
            if uid in open_ or not r.path or (r.speed or 0) != 0 or occ[r.path[0]] < K:
                continue
            tau = tau_of(r, r.path[0], edges)
            if tau is None:
                continue
            open_[uid] = {"uid": uid, "start": k, "target": r.path[0], "path": r.path, "tau": tau, "steps": []}
    for ep in open_.values():
        out.append(dict(ep, end=None, outcome="open at the end"))
    return out


def runs_of(ep: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Maximal runs of steps at speed above 0 / at speed 0 after the episode's start; each with its first step, length,
    the target's occupancy at its first step, whether a keep flag, move_state or basic_speed change occurred in it."""
    runs: List[Dict[str, Any]] = []
    for k, speed, occ, keep, state, basic in ep["steps"]:
        moving = bool(speed)
        if runs and runs[-1]["moving"] == moving:
            run = runs[-1]
            run["length"] += 1
            run["keep"] = run["keep"] or keep
            run["changed"] = run["changed"] or (state, basic) != run["state"]
        else:
            runs.append({"moving": moving, "first": k, "length": 1, "occ_first": occ, "keep": keep,
                         "state": (state, basic), "changed": False})
    return runs


def restart_events(eps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """T-b: the final run before the entry of every entered episode (M1c: a traversal of tau - 1 steps; an entry
    straight from waiting, as M1 predicts, contradicts it). T-c: every traversal run followed by a re-wait."""
    tb, tc = [], []
    excluded: collections.Counter = collections.Counter()
    for ep in eps:
        if ep["outcome"] != "entered":
            excluded[f"episode {ep['outcome']}"] += 1
            continue
        runs = runs_of(ep)
        tau = ep["tau"]
        for i, run in enumerate(runs[:-1]):
            if not run["moving"]:
                continue
            if run["keep"] or run["changed"]:
                excluded["re-wait run with a keep flag or a move_state or basic_speed change"] += 1
                continue
            ok = abs(run["length"] - (tau - 1)) <= pp.RUN_TOLERANCE and runs[i + 1]["occ_first"] >= K
            tc.append((run["first"], ep["uid"], tau, run["length"], ok))
        final = runs[-1] if runs else None
        if final is not None and (final["keep"] or final["changed"]):
            excluded["final run with a keep flag or a move_state or basic_speed change"] += 1
        elif tau < pp.TB_MIN_TAU:
            excluded[f"final run with tau below {pp.TB_MIN_TAU}"] += 1
        elif final is None or not final["moving"]:
            tb.append((ep["end"], ep["uid"], tau, 0, False))  # entered straight from waiting
        else:
            tb.append((final["first"], ep["uid"], tau, final["length"],
                       abs(final["length"] - (tau - 1)) <= pp.RUN_TOLERANCE))
    return {"T-b": tb, "T-c": tc, "excluded": dict(sorted(excluded.items()))}


def _wait_starts(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int]) -> Dict[Tuple[int, int], int]:
    """(k, uid) -> first step of the unit's current or most recent run at speed 0 with a path (first-come key)."""
    out: Dict[Tuple[int, int], int] = {}
    current: Dict[int, int] = {}
    last_start: Dict[int, int] = {}
    for k in ks:
        for uid, r in channel[k].items():
            if r.path and (r.speed or 0) == 0:
                current.setdefault(uid, k)
                last_start[uid] = current[uid]
            else:
                current.pop(uid, None)
            if uid in last_start:
                out[(k, uid)] = last_start[uid]
    return out


def arbitration_events(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int]) -> List[Dict[str, Any]]:
    """T-d: in one step, for one hex, traversing units that entered it and traversing units that re-waited instead."""
    starts = _wait_starts(channel, ks)
    out = []
    for prev_k, k in zip(ks, ks[1:]):
        prev, cur = channel[prev_k], channel[k]
        targets = collections.defaultdict(list)
        for uid, r in prev.items():
            if r.path and (r.speed or 0) != 0 and uid in cur:
                targets[r.path[0]].append(uid)
        for h, members in sorted(targets.items()):
            entered = sorted(u for u in members if cur[u].hex == h)
            rewaited = sorted(u for u in members if cur[u].hex != h and (cur[u].speed or 0) == 0
                              and cur[u].path and cur[u].path[0] == h)
            if not entered or not rewaited:
                continue
            pool = sorted(entered + rewaited)
            n = len(entered)
            keep = any(prev[u].keep or cur[u].keep for u in pool)
            fifo = sorted(pool, key=lambda u: (starts.get((prev_k, u), prev_k), u))[:n]
            out.append({"k": k, "hex": h, "entered": entered, "rewaited": rewaited, "keep": keep,
                        "ascending": pool[:n] == entered, "descending": sorted(pool[-n:]) == entered,
                        "first_come": sorted(fifo) == entered, "fifo_differs": sorted(fifo) != pool[:n]})
    return out


def restart_delay_events(channel: Mapping[int, Mapping[int, Row]], ks: Sequence[int]) -> List[Dict[str, Any]]:
    """T-e(3): a waiting unit whose next hex gets room in a step through units leaving it."""
    out = []
    for prev_k, k in zip(ks, ks[1:]):
        prev, cur = channel[prev_k], channel[k]
        if set(prev) != set(cur):
            continue
        start, end = _occ(prev), _occ(cur)
        for w, r in sorted(prev.items()):
            if not r.path or (r.speed or 0) != 0 or start[r.path[0]] < K or r.keep or cur[w].keep:
                continue
            h = r.path[0]
            if cur[w].path != r.path or cur[w].hex != r.hex or end[h] >= K:
                continue
            leavers = [v for v in cur if prev[v].hex == h and cur[v].hex != h]
            if not leavers:
                continue
            entrants = [v for v in cur if prev[v].hex != h and cur[v].hex == h]

            def restarts(before: Iterable[int]) -> bool:
                before = set(before)
                return start[h] - sum(1 for v in leavers if v in before) + sum(1 for v in entrants if v in before) < K

            ascending = restarts(v for v in cur if v < w)
            descending = restarts(v for v in cur if v > w)
            end_of_step = restarts(cur)
            observed = (cur[w].speed or 0) != 0
            out.append({"k": k, "unit": w, "ascending": ascending, "descending": descending, "end_of_step": end_of_step,
                        "observed_restart": observed, "as_predicted": observed == ascending,
                        "discriminating": ascending != descending or ascending != end_of_step})
    return out


def verdict(events: Sequence[bool], extra_ok: bool = True) -> str:
    n = len(events)
    if n == 0:
        return "NOT TESTED"
    if not all(events):
        return "REFUTED"
    if n < pp.MIN_EVENTS:
        return "INSUFFICIENT"
    return "SUPPORTED" if extra_ok else "INSUFFICIENT"


def targeted(t: Tables, k0: int, edges: Mapping[int, pm.Edges]) -> Dict[str, Any]:
    """Every targeted claim from both channels (separate extractions); a disagreement makes the claim INCONCLUSIVE."""
    ks = [k for k in t.ks if k >= k0]
    results = {}
    for name, channel in (("b", t.b), ("a", t.a)):
        ent = entry_events(channel, ks)
        eps = episodes(channel, ks, edges)
        rs = restart_events(eps)
        arb = arbitration_events(channel, ks)
        rd_ = restart_delay_events(channel, ks)
        results[name] = (ent, eps, rs, arb, rd_)
    same = {key: results["a"][i] == results["b"][i] for i, key in enumerate(("entry", "episodes", "restart", "arbitration", "delay"))}
    ent, eps, rs, arb, rd_ = results["b"]
    arb_used = [e for e in arb if not e["keep"]]
    delay_used = [e for e in rd_ if e["discriminating"]]
    claims = {
        "T-a": verdict([ok for _, _, ok in ent["T-a"]]) if same["entry"] else "INCONCLUSIVE",
        "T-b": verdict([ok for *_, ok in rs["T-b"]]) if same["episodes"] and same["restart"] else "INCONCLUSIVE",
        "T-c": verdict([ok for *_, ok in rs["T-c"]]) if same["episodes"] and same["restart"] else "INCONCLUSIVE",
        "T-d": (verdict([e["ascending"] for e in arb_used], any(e["fifo_differs"] for e in arb_used))
                if same["arbitration"] else "INCONCLUSIVE"),
        "T-e": (verdict([ok for _, _, ok in ent["T-e1"]] + [e["ascending"] for e in arb_used]
                        + [e["as_predicted"] for e in delay_used])
                if same["entry"] and same["arbitration"] and same["delay"] else "INCONCLUSIVE"),
    }
    public = {
        "claims": claims, "channels_agree": same,
        "entry_rule": ent["counts"],
        "T-a": {"discriminating": len(ent["T-a"]), "as_predicted": sum(ok for *_, ok in ent["T-a"])},
        "T-b": {"discriminating": len(rs["T-b"]), "as_predicted": sum(ok for *_, ok in rs["T-b"]),
                "length_minus_tau_histogram": dict(sorted(collections.Counter(
                    str(n - tau) for _, _, tau, n, _ in rs["T-b"]).items()))},
        "T-c": {"discriminating": len(rs["T-c"]), "as_predicted": sum(ok for *_, ok in rs["T-c"])},
        "episodes": {"total": len(eps), "by_outcome": dict(sorted(collections.Counter(e["outcome"] for e in eps).items())),
                     "runs_excluded": rs["excluded"]},
        "T-d": {"contention_events": len(arb), "with_keep_flag_excluded": len(arb) - len(arb_used),
                "ascending_as_predicted": sum(e["ascending"] for e in arb_used),
                "descending_as_predicted": sum(e["descending"] for e in arb_used),
                "first_come_as_predicted": sum(e["first_come"] for e in arb_used),
                "discriminating_from_first_come": sum(e["fifo_differs"] for e in arb_used)},
        "T-e": {"entry_rule_discriminating": len(ent["T-e1"]), "entry_rule_as_predicted": sum(ok for *_, ok in ent["T-e1"]),
                "arbitration_events": len(arb_used), "restart_delay_events": len(rd_),
                "restart_delay_discriminating": len(delay_used),
                "restart_delay_as_predicted": sum(e["as_predicted"] for e in delay_used)},
    }
    private = {"T-a": ent["T-a"], "T-e1": ent["T-e1"], "T-b": rs["T-b"], "T-c": rs["T-c"], "T-d": arb,
               "T-e3": rd_, "episodes": [{k: v for k, v in e.items() if k != "steps"} for e in eps]}
    return {"public": public, "private": private}


def cross_check_frozen(t: Tables, ks: Sequence[int], game: Game, edges: Mapping[int, pm.Edges],
                       ent_counts: Mapping[str, int], eps: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """The entry rule and the restart episodes recomputed by the Sprint 3 functions (written independently) on the
    raw seat observations; both must agree with this script's extraction."""
    pairs = [(t.cur_step[k], game.observation(k)) for k in ks]
    frozen_entry = posthoc.entry_rule(pairs, game.seat)
    keys = ("entries", "waited at once", "ascending agrees", "descending agrees", "end of step agrees")
    mine = {"entries": ent_counts.get("entries with a path left", 0), "waited at once": ent_counts.get("waited at once", 0),
            "ascending agrees": ent_counts.get("ascending agrees", 0), "descending agrees": ent_counts.get("descending agrees", 0),
            "end of step agrees": ent_counts.get("end of step agrees", 0)}
    theirs = {key: frozen_entry.get(key, 0) for key in keys}
    frozen_eps = study.restart_episodes(pairs, game.seat, game.faction, edges, trace=True)
    frozen_d = sorted((e["tau"], e["d"]) for e in frozen_eps)
    my_d = []
    for e in eps:
        if e["outcome"] != "entered":
            continue
        room = next((k for k, _, occ, *_ in e["steps"] if occ < K), e["end"])
        my_d.append((e["tau"], e["end"] - room))
    return {"entry_rule": {"mine": mine, "frozen": theirs, "agree": mine == theirs},
            "episodes": {"mine": len(my_d), "frozen": len(frozen_d), "agree": sorted(my_d) == frozen_d}}


# ----------------------------------------------------------------------------------------------
# P1


def hook_events(game: Game) -> Dict[str, Any]:
    """The hook's notes per step (written at decision time) and the trigger step."""
    notes = {s["k"]: (s.get("hook_notes") or {}).get(str(game.seat), []) for s in game.steps}
    trigger_k = next((k for k in sorted(notes) if any("trigger at step" in n for n in notes[k])), None)
    return {"notes": {k: v for k, v in notes.items() if v}, "trigger_k": trigger_k}


def stop_units(game: Game, actions: Sequence[Action], trigger_k: Optional[int], notes: Mapping[int, List[str]]) -> List[int]:
    """Units the hook stopped: the pre-execution stops at the trigger, which must equal the hook's emit notes."""
    if trigger_k is None:
        return []
    submitted = sorted(a.submitted["obj_id"] for a in actions if a.k == trigger_k and a.submitted.get("type") == STOP)
    noted = sorted(json.loads(n.split("emit ", 1)[1])["obj_id"] for n in notes.get(trigger_k, ())
                   if n.startswith(pp.HOOK_NOTE + "emit ") and '"type":10' in n)
    if submitted != noted:
        refuse("the stops in the submitted actions differ from the hook's notes")
    if any(a.submitted.get("type") == STOP for a in actions if a.k != trigger_k):
        refuse("a stop was submitted at another step than the trigger")
    return submitted


def unit_course(t: Tables, uid: int, k0: int, actions: Sequence[Action], notes: Mapping[int, List[str]]) -> Dict[str, Any]:
    """Every registered event of one stopped unit, from both channels."""
    s0 = t.cur_step[k0]
    before_b, before_a = t.b[k0].get(uid), t.a[k0].get(uid)
    if before_b is None or before_a is None or (before_b.hex, before_b.path) != (before_a.hex, before_a.path):
        refuse(f"unit {uid}: the two channels disagree at the trigger")
    final_hex = before_b.path[-1] if before_b.path else None
    stop = next(a for a in actions if a.k == k0 and a.submitted.get("type") == STOP and a.submitted["obj_id"] == uid)
    horizon = [k for k in t.ks if k0 < k <= k0 + pp.WATCH_STEPS]
    effect = entered_before = None
    mtsrt_positive = None
    for k in horizon:
        rb, ra = t.b[k].get(uid), t.a[k].get(uid)
        if (rb is None) != (ra is None) or (rb and (rb.hex, rb.path, rb.actions) != (ra.hex, ra.path, ra.actions)):
            refuse(f"unit {uid}: the two channels disagree at k {k}")
        if rb is None:
            break
        if mtsrt_positive is None and isinstance(rb.mtsrt, (int, float)) and rb.mtsrt > 0:
            mtsrt_positive = k
        if rb.hex != before_b.hex and entered_before is None and effect is None:
            entered_before = k
        if effect is None and not rb.path:
            effect = k
    relist = next((k for k in [k for k in t.ks if k > k0] if t.b[k].get(uid) and MOVE in t.b[k][uid].actions), None)
    relist_a = next((k for k in [k for k in t.ks if k > k0] if t.a[k].get(uid) and MOVE in t.a[k][uid].actions), None)
    if relist != relist_a:
        refuse(f"unit {uid}: the channels disagree on the re-listing of action 1")
    transition = []
    if effect is not None:
        for k in t.ks:
            if effect <= k < (relist if relist is not None else effect + pp.WATCH_STEPS) and uid in t.b[k]:
                r = t.b[k][uid]
                transition.append((k, tuple(sorted(r.actions)), r.stop, r.mtsrt, r.speed, r.move_state, r.can_to_move))
    in_place = effect is not None and entered_before is None and t.b[effect][uid].hex == before_b.hex
    attributable = ((effect is not None and t.b[effect][uid].hex != final_hex) or mtsrt_positive is not None)
    errors = [c for c in stop.codes if c is not None]
    if errors and attributable:
        outcome = "contradictory"
    elif errors:
        outcome = "refused"
    elif not attributable:
        outcome = "no attributable change"
    elif in_place:
        outcome = "accepted in place"
    else:
        outcome = "accepted after entry"
    move = next((a for a in actions if a.k > k0 and a.submitted.get("type") == MOVE and a.submitted["obj_id"] == uid
                 and any(f"emit {canonical(a.submitted)}" in n for n in notes.get(a.k, ()))), None)
    released = [n for k in sorted(notes) for n in notes[k] if n.startswith(f"{pp.HOOK_NOTE}unit {uid}: released")]
    back = None
    if move is not None:
        path = tuple(move.submitted["move_path"])
        nxt = t.b.get(move.k + 1, {}).get(uid)
        echo = nxt is not None and (nxt.path == path or (nxt.hex == path[0] and nxt.path == path[1:]))
        arrival = next((k for k in t.ks if k > move.k and t.b[k].get(uid) and t.b[k][uid].hex == path[-1]), None)
        back = {"k": move.k, "accepted": accepted(move) and echo, "error_codes": [c for c in move.codes if c is not None],
                "echo": echo, "arrival_k": arrival, "path_length": len(path)}
    return {"unit": uid, "s0": s0, "listed_10": STOP in before_b.actions, "feedback_codes": list(stop.codes),
            "effect_k": effect, "effect_cur_step": t.cur_step.get(effect) if effect else None,
            "entered_before_effect": entered_before, "in_place": in_place, "attributable": attributable,
            "mtsrt_positive_k": mtsrt_positive, "outcome": outcome, "relist_k": relist,
            "L": (t.cur_step[relist] - s0) if relist is not None else None,
            "transition": transition, "back_off": back, "released": released}


def e_verdicts(courses: Sequence[Mapping[str, Any]], e4: Mapping[str, Any]) -> Dict[str, str]:
    outcomes = [c["outcome"] for c in courses]
    if not courses:
        return {e: "INCONCLUSIVE" for e in ("E1", "E2", "E3", "E4")}
    if "contradictory" in outcomes:
        e1 = "INCONCLUSIVE"
    elif all(o in ("accepted in place", "accepted after entry") for o in outcomes):
        e1 = "SUPPORTED"
    else:
        e1 = "REFUTED"
    effective = [c for c in courses if c["outcome"] in ("accepted in place", "accepted after entry")]
    if any(c["outcome"] == "accepted after entry" for c in courses) or "no attributable change" in outcomes:
        e2 = "REFUTED"
    elif effective and all(c["outcome"] == "accepted in place" for c in effective):
        e2 = "SUPPORTED"
    else:
        e2 = "INCONCLUSIVE"
    placed = [c for c in courses if c["outcome"] == "accepted in place"]
    lo, hi = pp.E3_WINDOW
    if not placed:
        e3 = "INCONCLUSIVE"
    elif any(c["relist_k"] is None or c["L"] > pp.WATCH_STEPS or not (lo <= c["L"] <= hi) for c in placed) \
            or any(c["back_off"] is not None and not c["back_off"]["accepted"] for c in placed):
        e3 = "REFUTED"
    else:
        e3 = "SUPPORTED"
    return {"E1": e1, "E2": e2, "E3": e3, "E4": e4["verdict"]}


def e4_analysis(t: Tables, courses: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """E4 from the seat observation: violations, discriminating waiting unit-steps and restarts during transitions."""
    spans = {c["unit"]: (c["effect_k"], c["relist_k"] if c["relist_k"] is not None else c["effect_k"] + pp.WATCH_STEPS)
             for c in courses if c["outcome"] in ("accepted in place", "accepted after entry")}
    if not spans:
        return {"verdict": "INCONCLUSIVE", "reason": "no unit's stop took effect", "violations": 0,
                "discriminating_unit_steps": 0, "restarts": 0}
    first_effect: Dict[int, int] = {}
    for uid, (a, _) in spans.items():
        h = t.b[a][uid].hex
        first_effect[h] = min(first_effect.get(h, a), a)
    violations, discriminating, restarts = 0, 0, 0
    waited: Set[Tuple[int, int]] = set()
    lo, hi = min(a for a, _ in spans.values()), max(b for _, b in spans.values())
    for k in t.ks:
        if not (lo <= k < hi):
            continue
        rows = t.b[k]
        transitioning = {u for u, (a, b) in spans.items() if a <= k < b and u in rows}
        occ_all = _occ(rows)
        occ_t = collections.Counter(rows[u].hex for u in transitioning)
        for h in occ_t:
            if occ_all[h] > K:
                violations += 1
        for v, r in rows.items():
            if v in transitioning or not r.path:
                continue
            h = r.path[0]
            if occ_t[h] == 0 or not (occ_all[h] >= K and occ_all[h] - occ_t[h] < K) or r.keep:
                continue
            if k < first_effect.get(h, k) + pp.E4_MARGIN:
                continue
            if (r.speed or 0) == 0:
                discriminating += 1
                waited.add((v, h))
            elif (v, h) in waited:
                restarts += 1
    if violations or restarts:
        result = "REFUTED"
    elif discriminating:
        result = "SUPPORTED"
    else:
        result = "INCONCLUSIVE"
    return {"verdict": result, "violations": violations, "discriminating_unit_steps": discriminating,
            "units_waiting_on_a_transitioning_hex": len(waited), "restarts": restarts,
            "window_steps": hi - lo}


def secondary_p1(t: Tables, k0: int, courses: Sequence[Mapping[str, Any]], trigger_cycles: Sequence[Tuple[int, ...]],
                 faction: int) -> Dict[str, Any]:
    """Descriptive mechanism outcomes after the stops (seat observation; model functions for the wait-for graph)."""
    def units_at(k: int) -> List[pm.Unit]:
        return [pm.Unit(uid, r.hex, float(r.basic_speed), int(move_mode(r.type, r.move_state)), r.path)
                for uid, r in sorted(t.b[k].items())]
    dead0 = pm.deadlocked(units_at(k0))
    after = [k for k in t.ks if k > k0]
    cycle_gone = next((k for k in after if not any(c in pm.cycles(units_at(k)) for c in trigger_cycles)), None)
    empty = next((k for k in after if not pm.deadlocked(units_at(k))), None)
    progress = next((k for k in after if any(u in t.b[k] and u in t.b[k - 1] and t.b[k][u].hex != t.b[k - 1][u].hex
                                             for u in dead0)), None)
    eps, cur = [], None
    new_cycles = set()
    for k in after:
        units = units_at(k)
        dead = pm.deadlocked(units)
        cyc = pm.cycles(units)
        new_cycles |= {c for c in cyc if c not in trigger_cycles}
        if dead:
            if cur is None:
                cur = {"start": k, "max_units": 0, "cycle": False}
            cur["end"] = k
            cur["max_units"] = max(cur["max_units"], len(dead))
            cur["cycle"] = cur["cycle"] or bool(cyc)
        elif cur is not None:
            eps.append(cur)
            cur = None
    if cur is not None:
        cur["lasts_to_end"] = True
        eps.append(cur)
    final = t.cities[t.ks[-1]]
    return {"deadlocked_at_trigger": len(dead0), "trigger_cycle_lengths": [len(c) for c in trigger_cycles],
            "trigger_cycle_absent_from_k": cycle_gone, "deadlocked_set_first_empty_k": empty,
            "first_entry_by_a_formerly_deadlocked_unit_k": progress,
            "deadlock_episodes_after": [{"start": e["start"], "end": e["end"], "steps": e["end"] - e["start"] + 1,
                                         "max_units": e["max_units"], "kind": "cycle" if e["cycle"] else "chain",
                                         "lasts_to_end": bool(e.get("lasts_to_end"))} for e in eps],
            "new_cycles_after": len(new_cycles),
            "back_off_arrivals": sorted(c["back_off"]["arrival_k"] for c in courses
                                        if c["back_off"] and c["back_off"]["arrival_k"] is not None),
            "back_off_emitted": sum(1 for c in courses if c["back_off"]),
            "final_objective_values_held": sorted(v for _, (v, f) in final.items() if f == faction)}


def premise(game: Game, sprint2: Mapping[str, Any], trigger_k: Optional[int], group: Sequence[int],
            parameters: Mapping[str, Any]) -> Dict[str, Any]:
    """The P1 reproduction premise against the Sprint 2 split-game record and the registered prediction."""
    if trigger_k is None:
        return {"reproduced": False, "reason": "no trigger"}
    rec = game.record
    same_states = rec["state_steps"][:trigger_k + 1] == sprint2["state_steps"][:trigger_k + 1]
    seats = {s["policy"]: s for s in rec["seats"]}
    seats2 = {s["policy"]: s for s in sprint2["seats"]}
    inert_same = seats[INERT_ID]["trace_steps"][:trigger_k + 1] == seats2[INERT_ID]["trace_steps"][:trigger_k + 1]
    hooked = seats[pp.HOOK_ID]["trace_steps"][:trigger_k]
    split = seats2[pp.SPLIT_ID]["trace_steps"][:trigger_k]
    predicted_k, predicted_size = parameters["predicted_trigger_k"], parameters["predicted_group_size"]
    reproduced = (same_states and inert_same and hooked == split and trigger_k == predicted_k
                  and len(group) == predicted_size)
    return {"reproduced": reproduced, "state_digests_equal_to_trigger": same_states,
            "inert_trace_digests_equal_to_trigger": inert_same, "hooked_trace_digests_equal_before_trigger": hooked == split,
            "trigger_k": trigger_k, "predicted_trigger_k": predicted_k, "group_size": len(group),
            "predicted_group_size": predicted_size}


def offline_redecisions(game: Game, trigger_k: int, costs: MoveCosts) -> Dict[str, Any]:
    """Every pre-trigger snapshot re-decided by a fresh split candidate: actions and trace digest as captured."""
    fresh = DeploymentSplitPolicy(costs)
    checked = 0
    for k in range(1, trigger_k):
        entry = game.entry(k)
        memory = pickle.loads(entry["memory"])
        decision = fresh.decide(Observation.from_raw(game.observation(k), Origin.ENGINE), game.seat, game.faction,
                                memory.inner)
        submitted = [s["action"] for s in game.steps[k]["submitted"] if s["seat"] == game.seat]
        if plain([dict(a) for a in decision.actions]) != submitted or digest(decision.trace) != entry["trace"]:
            refuse(f"k {k}: the offline re-decision differs from the hooked seat's")
        checked += 1
    return {"pre_trigger_decisions_rechecked": checked}


def trigger_recomputed(game: Game, costs: MoveCosts, trigger_k: int) -> Dict[str, Any]:
    """The trigger recomputed with the Sprint 3 functions from the all-seeing state (``ps1_study.reconstruct``)."""
    cap = study.Capture(game.record, game.compact, {"samples": list(game.samples.values())})
    recon = study.reconstruct(cap, costs)
    detections = recon["private"]["detections"]
    return {"first_detection_k": detections[0] if detections else None,
            "agrees_with_hook": bool(detections) and detections[0] == trigger_k}


def analyze_p1(game: Game, manifest: Mapping[str, Any], sprint2: Mapping[str, Any], costs: MoveCosts) -> Dict[str, Any]:
    edges = edges_of(costs)
    integrity = record_check(game, manifest, pp.HOOK_ID)
    t = game.tables()
    fresh = fresh_feedback(game.steps)
    actions = seat_actions(game, fresh)
    counts = check_counts(game, actions)
    channels = channel_agreement(t)
    hooks = hook_events(game)
    trigger_k = hooks["trigger_k"]
    group = stop_units(game, actions, trigger_k, hooks["notes"])
    prem = premise(game, sprint2, trigger_k, group, manifest["parameters"])
    public: Dict[str, Any] = {"schema": "miaosuan-ps1-probe-p1/1", "game": pp.P1_GAME, "integrity": integrity,
                              "actions": counts, "channels": channels, "max_occupancy": max_occupancy(t),
                              "premise": prem, "stops": len(group)}
    if not group:
        reason = next((n for k in sorted(hooks["notes"]) for n in hooks["notes"][k] if "ended:" in n), "no trigger")
        public.update(evaluable=False, reason="no stop was emitted", verdicts={e: "INCONCLUSIVE" for e in ("E1", "E2", "E3", "E4")})
        return {"public": public, "private": {"notes": hooks["notes"], "reason": reason}}
    public["offline"] = offline_redecisions(game, trigger_k, costs)
    public["trigger_recomputed"] = trigger_recomputed(game, costs, trigger_k)
    courses = [unit_course(t, uid, trigger_k, actions, hooks["notes"]) for uid in group]
    e4 = e4_analysis(t, courses)
    verdicts = e_verdicts(courses, e4)
    if not prem["reproduced"]:
        verdicts = {e: "INCONCLUSIVE" for e in verdicts}
    trigger_note = next(n for n in hooks["notes"][trigger_k] if "trigger at step" in n)
    cycles = [tuple(c) for c in json.loads(trigger_note.split("cycles ", 1)[1].replace("(", "[").replace(")", "]"))]
    k0 = game.first_play_k()
    orders: Dict[int, List[Tuple[str, int, Tuple[int, ...]]]] = collections.defaultdict(list)
    for a in actions:
        if a.k >= k0 and accepted(a) and a.submitted.get("obj_id") in t.b.get(a.k, {}):
            kind = {MOVE: "move", STOP: "stop", OCCUPY: "occupy"}.get(a.submitted.get("type"))
            if kind:
                orders[a.k].append((kind, a.submitted["obj_id"], tuple(a.submitted.get("move_path") or ())))
    try:
        s_run = replay(t, k0, edges, game.faction, orders=orders)
    except Refused as exc:
        s_run = None
        p1_s = {"computed": False, "reason": str(exc)}
    if s_run is not None:
        observed = observed_entries(t.b, t.ks, k0)
        before = study.compare_entries([e for e in s_run.entries if e[0] <= trigger_k],
                                       [e for e in observed if e[0] <= trigger_k], k0)
        after = study.compare_entries([e for e in s_run.entries if e[0] > trigger_k],
                                      [e for e in observed if e[0] > trigger_k], trigger_k)
        p1_s = {"computed": True, "model_error": s_run.error, "orders_not_applicable": s_run.inapplicable,
                "before_stops": {k: v for k, v in before.items() if k != "private"},
                "after_stops": {k: v for k, v in after.items() if k != "private"},
                "private": {"before": before["private"], "after": after["private"]}}
    public.update(
        evaluable=True, trigger_k=trigger_k, trigger_cur_step=t.cur_step[trigger_k],
        units=[{k: v for k, v in c.items() if k not in ("unit", "transition", "released")}
               | {"transition_listed_types": sorted({str(x[1]) for x in c["transition"]}),
                  "transition_stop_values": sorted({str(x[2]) for x in c["transition"]}),
                  "transition_mtsrt_max": max((x[3] for x in c["transition"] if isinstance(x[3], (int, float))), default=None),
                  "released": len(c["released"])} for c in courses],
        outcomes=dict(sorted(collections.Counter(c["outcome"] for c in courses).items())),
        E4=e4, verdicts=verdicts, secondary=secondary_p1(t, trigger_k, courses, cycles, game.faction),
        p1_s={k: v for k, v in p1_s.items() if k != "private"})
    private = {"group": group, "courses": courses, "notes": hooks["notes"], "cycles": cycles,
               "p1_s_mismatched": p1_s.get("private")}
    return {"public": public, "private": private}


# ----------------------------------------------------------------------------------------------
# P2


def analyze_p2(game: Game, manifest: Mapping[str, Any], costs: MoveCosts) -> Dict[str, Any]:
    edges = edges_of(costs)
    integrity = record_check(game, manifest, pp.SPLIT_ID)
    t = game.tables()
    fresh = fresh_feedback(game.steps)
    actions = seat_actions(game, fresh)
    counts = check_counts(game, actions)
    k0 = game.first_play_k()
    play_ks = [k for k in t.ks if k >= k0]
    first = set(t.b[k0])
    eligible = set().union(*(set(t.b[k]) for k in play_ks))
    channels = channel_agreement(t)
    channels_ok = channels["disagreeing_unit_entries"] == 0
    orders: Dict[int, List[Tuple[str, int, Tuple[int, ...]]]] = collections.defaultdict(list)
    scope: collections.Counter = collections.Counter()
    refused_units: Set[int] = set()
    recorded_moves, recorded_occ, echo_bad = [], [], 0
    for a in actions:
        kind = a.submitted.get("type")
        uid = a.submitted.get("obj_id")
        if a.k < k0 or kind is None:
            continue
        if uid not in eligible:
            scope[f"type {kind} by a unit outside the population"] += 1
            continue
        if not accepted(a):
            scope[f"type {kind} refused"] += 1
            refused_units.add(uid)
            continue
        if kind == MOVE:
            path = tuple(a.submitted["move_path"])
            orders[a.k].append(("move", uid, path))
            recorded_moves.append((a.k, uid, path[-1]))
            nxt = t.b.get(a.k + 1, {}).get(uid)
            if nxt is None or not (nxt.path == path or (nxt.hex == path[0] and nxt.path == path[1:])):
                echo_bad += 1
        elif kind == OCCUPY:
            orders[a.k].append(("occupy", uid, ()))
            recorded_occ.append((a.k, uid, t.b[a.k][uid].hex))
        elif kind == STOP:
            orders[a.k].append(("stop", uid, ()))
        else:
            scope[f"type {kind} accepted (not modelled)"] += 1
    population = {"eligible_units": len(eligible), "eligible_at_first_play": len(first),
                  "aircraft_at_first_play": t.aircraft[k0], "passengers_at_first_play": t.passengers[k0],
                  "units_appearing_later": len(eligible - first),
                  "removals": sum(len(v) for v in removals(t.b, t.ks, k0).values()),
                  "orders_applied": sum(len(v) for v in orders.values()), "orders_echo_mismatch": echo_bad,
                  "outside_scope": dict(sorted(scope.items()))}
    f1 = fidelity_f1(t, k0, edges, game.faction, orders, refused_units)
    if not channels_ok or echo_bad:
        f1["verdict"] = "INCONCLUSIVE"
    else:
        f1["verdict"] = "PASS" if f1["pass"] else "FAIL"
    f2 = fidelity_f2(t, k0, edges, game.faction, recorded_moves, recorded_occ)
    f2["verdict"] = "INCONCLUSIVE" if not channels_ok else "PASS" if f2["pass"] else "FAIL"
    tg = targeted(t, k0, edges)
    if not channels_ok:
        tg["public"]["claims"] = {c: "INCONCLUSIVE" for c in tg["public"]["claims"]}
    eps_b = episodes(t.b, play_ks, edges)
    frozen = cross_check_frozen(t, play_ks, game, edges, tg["public"]["entry_rule"], eps_b)
    if not (frozen["entry_rule"]["agree"] and frozen["episodes"]["agree"]):
        refuse(f"the frozen Sprint 3 extractors disagree with this analysis: {frozen}")
    keep_steps = sum(1 for k in play_ks for r in t.b[k].values() if r.keep and r.path)
    census = study.census_sequence([(t.cur_step[k], game.observation(k),
                                     [s["action"] for s in game.steps[k]["submitted"] if s["seat"] == game.seat])
                                    for k in play_ks], game.seat, game.faction, edges)
    deadlocks = posthoc.deadlock_episodes([(t.cur_step[k], game.observation(k)) for k in play_ks], game.seat, edges)
    public = {"schema": "miaosuan-ps1-probe-p2/1", "game": pp.P2_GAME, "integrity": integrity, "actions": counts,
              "channels": channels, "first_play_k": k0, "last_k": t.ks[-1], "population": population,
              "F1": {k: v for k, v in f1.items() if k not in ("private", "pass")},
              "F2": {k: v for k, v in f2.items() if k != "pass"},
              "targeted": tg["public"], "frozen_extractors": frozen,
              "keep": {"eligible_unit_steps_with_keep_and_a_path": keep_steps,
                       "entry_rule_disagreements_with_keep": tg["public"]["entry_rule"].get(
                           "ascending disagreements with the keep flag set", 0),
                       "f1_mismatched_units_with_keep": sum(1 for m in f1["private"]["mismatched"] if m["keep_set_in_window"])},
              "trigger_census": {k: v for k, v in census["counts"].items() if k in (
                  "ps1b_trigger_steps", "unit_steps", "unit_steps_blocked", "unit_steps_deadlocked")},
              "deadlock_episodes": {"episodes": len(deadlocks), "fired": sum(1 for e in deadlocks if e["trigger_steps"]),
                                    "trigger_steps_inside_episodes": sum(e["trigger_steps"] for e in deadlocks),
                                    "kinds": dict(sorted(collections.Counter(e["kind"] for e in deadlocks).items()))}}
    if public["trigger_census"].get("ps1b_trigger_steps", 0) != public["deadlock_episodes"]["trigger_steps_inside_episodes"]:
        refuse("the trigger census and the deadlock episodes count different trigger steps")
    return {"public": public, "private": {"F1": f1["private"], "targeted": tg["private"]}}


# ----------------------------------------------------------------------------------------------
# gates


def gates(p1: Mapping[str, Any], p2: Mapping[str, Any], certificate: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """The registered gate rules applied to the two public outputs."""
    v = p1.get("verdicts", {})
    claims = p2["targeted"]["claims"]
    p1_clean = (p1["channels"]["disagreeing_unit_entries"] == 0 and max(p1["max_occupancy"].values()) <= K)
    p2_clean = (p2["channels"]["disagreeing_unit_entries"] == 0 and max(p2["F1"]["max_observed_occupancy"].values()) <= K)
    g1 = "PASS (Sprint 3; not contradicted)" if (p1_clean and p2_clean and p1["premise"].get("state_digests_equal_to_trigger", True)) \
        else "PASS (Sprint 3) with a contradiction recorded"
    expressible = (p1.get("evaluable") and p1["integrity"]["replay_mismatches"] == 0
                   and p1.get("offline", {}).get("pre_trigger_decisions_rechecked", 0) > 0
                   and p1["integrity"]["gate_rejections"] == 0 and p1["integrity"]["contract_errors"] == 0)
    if any(v.get(e) == "REFUTED" for e in ("E1", "E2", "E3", "E4")):
        g2 = "FAIL"
    elif all(v.get(e) == "SUPPORTED" for e in ("E1", "E2", "E3", "E4")) and expressible:
        g2 = "PASS"
    else:
        g2 = "UNRESOLVED"
    refuted = [c for c, x in claims.items() if x == "REFUTED"]
    if p2["F1"]["verdict"] == "FAIL" or p2["F2"]["verdict"] == "FAIL" or refuted:
        g3 = "FAIL"
    elif (p2["F1"]["verdict"] == "PASS" and p2["F2"]["verdict"] == "PASS"
          and all(claims[c] == "SUPPORTED" for c in ("T-a", "T-b", "T-d", "T-e"))
          and claims["T-c"] in ("SUPPORTED", "INSUFFICIENT", "NOT TESTED") and g2 == "PASS"):
        g3 = "PASS" if certificate is not None and certificate.get("verdict") == "feasible" else "UNRESOLVED"
    else:
        g3 = "UNRESOLVED"
    g4 = "PASS (Sprint 3; not contradicted)"
    if v.get("E1") == "REFUTED" and not any(o in p1.get("outcomes", {}) for o in ("accepted in place", "accepted after entry")):
        g5 = "SHELVE"
    elif g2 == "FAIL" or g3 == "FAIL":
        g5 = "REVISE"
    elif g2 == "UNRESOLVED" or g3 == "UNRESOLVED":
        g5 = "NEEDS_ENGINE_PROBE"
    else:
        g5 = "READY_FOR_PROSPECTIVE_VALIDATION"
    return {"schema": "miaosuan-ps1-probe-gates/1", "G1": g1, "G2": g2, "G3": g3, "G4": g4, "G5": g5,
            "inputs": {"E": dict(v), "F1": p2["F1"]["verdict"], "F2": p2["F2"]["verdict"], "targeted": dict(claims),
                       "p1_expressible": bool(expressible), "certificate": (certificate or {}).get("verdict")}}


# ----------------------------------------------------------------------------------------------


FORBIDDEN = ("obj_id", "cur_hex", "move_path")


def write(public: Mapping[str, Any], private: Mapping[str, Any], public_path: Path, private_path: Path) -> None:
    text = json.dumps(public, indent=1, sort_keys=True, default=list) + "\n"
    for word in FORBIDDEN:
        if word in text:
            refuse(f"the public output contains {word}")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_text(json.dumps(private, indent=1, sort_keys=True, default=list) + "\n", encoding="utf-8")
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("p1", "p2", "gates"))
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / pp.PROBE_ID)
    parser.add_argument("--sprint2", type=Path, default=REPO_ROOT / "local" / "evaluation" / "t1r-diagnosis-1")
    parser.add_argument("--private", type=Path, default=REPO_ROOT / "local" / "diagnostics" / "ps1-probe")
    parser.add_argument("--public", type=Path, default=REPO_ROOT / "evaluation" / pp.PROBE_ID)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "evaluation" / pp.PROBE_ID / "manifest.json")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if args.command == "gates":
        p1 = json.loads((args.public / "p1.json").read_text(encoding="utf-8"))
        p2 = json.loads((args.public / "p2.json").read_text(encoding="utf-8"))
        certificate = None
        if gates(p1, p2, {"verdict": "feasible"})["G3"] == "PASS":  # everything but the certificate passes
            cap = study.Capture.read(args.sprint2, study.CANDIDATE_GAME)
            costs = study.load_costs(args.sprint2, json.loads((REPO_ROOT / "evaluation" / study.SCREEN / "manifest.json").read_text(encoding="utf-8")), study.SCENARIO)[0]
            recon = study.reconstruct(cap, costs)
            cert = study.certificate("A2", "PS-1B back-off under M1c (re-evaluated)", cap, costs, recon,
                                     recon["first_detection_k"], "ps1b-back-off", ["M1c"], [], entry_wait=True)
            certificate = cert["public"]
        result = gates(p1, p2, certificate)
        if certificate is not None:
            result["certificate"] = {k: certificate[k] for k in ("verdict", "cycle_broken_at_k", "deadlocked_at_end",
                                                                 "capacity_violations", "occupy_points_at_end")}
        write(result, {"certificate": certificate}, args.public / "gates.json", args.private / "gates-private.json")
        print(json.dumps({k: result[k] for k in ("G1", "G2", "G3", "G4", "G5")}))
        return 0
    game_id = pp.P1_GAME if args.command == "p1" else pp.P2_GAME
    spec = next(g for g in manifest["games"] if g["game_id"] == game_id)
    game = Game.read(args.work, game_id)
    costs = load_costs(args.work, manifest, spec["scenario_id"])
    if args.command == "p1":
        path = args.sprint2 / "games" / f"{pp.SPRINT2_SPLIT_GAME}.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["inputs"]["sprint2_split_record_sha256"]:
            refuse(f"{path} is not the registered Sprint 2 record")
        sprint2 = json.loads(path.read_text(encoding="utf-8"))
        result = analyze_p1(game, manifest, sprint2, costs)
    else:
        result = analyze_p2(game, manifest, costs)
    write(result["public"], result["private"], args.public / f"{args.command}.json",
          args.private / f"{args.command}-private.json")
    print(f"wrote {args.public / (args.command + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
