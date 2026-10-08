"""Sprint 23 offline T2 policy design: input freeze, fidelity smoke and the opportunity study
(``docs/SPRINT23_T2_POLICY_DESIGN.md``).

    python scripts/s23_t2_design.py freeze [--check]   # pin every input and source; writes inputs.json
    python scripts/s23_t2_design.py smoke              # fidelity only: reconstructions and known answers, no counts
    python scripts/s23_t2_design.py run [--check]      # the registered opportunity study

Runs on the evaluation server (the captures are private, under the ignored ``local/``). Populations (section 11): H0,
``baseline-v2`` reconstructed on the 8 replay-corpus games of Sprint 18's frozen inputs, both seats; HH, the
``baseline-v2`` seat of Sprint 18's 4 head-to-head timelines; HI, the 3 actual ``baseline-v2`` games against the inert
control of Sprint 22's tier 1. ``run`` refuses unless every pinned input and source matches the committed
``evaluation/s23-t2-policy-design/inputs.json``. Public outputs go to ``evaluation/s23-t2-policy-design/``; private
ones (unit ids, hexes, decisions) to ``local/diagnostics/s23/``. ``--check`` regenerates and compares byte for byte.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
import multiprocessing
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin, Stage  # noqa: E402
from miaosuan_agent.decision.routing import Router  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s12_screen as sc  # noqa: E402
from miaosuan_agent.evaluation import s12_timeline as tl  # noqa: E402
from miaosuan_agent.evaluation import s23_design as sd  # noqa: E402
from miaosuan_agent.experiments import t2_transport_x1 as x1  # noqa: E402
from miaosuan_agent.experiments import t9_batch as tb  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / sd.STUDY_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s23"
INPUTS = OUT / "inputs.json"
PREVALENCE = OUT / "prevalence.json"
EPISODES = OUT / "episodes.json"
DISPOSITION = OUT / "disposition.json"
S18_INPUTS = REPO_ROOT / "evaluation" / "s18-frontier-reset" / "inputs.json"
S22_INPUTS = REPO_ROOT / "evaluation" / "s22-t2-transport-probe" / "inputs.json"
S22_WITNESS = REPO_ROOT / "evaluation" / "s22-t2-transport-probe" / "witness.json"
S22_REFERENCE = REPO_ROOT / "local" / "diagnostics" / "s22" / "witness-reference.json"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
V2 = "baseline-v2-candidate-shoot-target-reservation"
#: Sources the study's results depend on (normalised SHA-256 pinned in inputs.json).
SOURCES = ("src/miaosuan_agent/experiments/t2_transport_x1.py", "src/miaosuan_agent/evaluation/s23_design.py",
           "scripts/s23_t2_design.py", "src/miaosuan_agent/experiments/t9_batch.py",
           "src/miaosuan_agent/experiments/exploratory_addon.py", "scripts/s22_analysis.py",
           "src/miaosuan_agent/experiments/" + "t2_transport_" + "p1.py")
#: Published figures the study reproduces (Sprint 18's census consistency checks).
PUBLISHED = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123,
             "HH decisions": 11524}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
                          ).hexdigest()


def load_script(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(f"s23_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------
# inputs


def jobs_from(s18: Mapping[str, Any], s22_corpus: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    jobs = [{"population": "H0", "game": Path(e["path"]).name.replace(".jsonl.gz", ""), "path": e["path"],
             "sha256": e["sha256"]} for e in s18["H0"]["games"]]
    jobs += [{"population": "HH", "game": e["game"], "record": e["record"], "timeline": e["timeline"]}
             for e in s18["HH"]["games"]]
    jobs += [{"population": "HI", "game": e["game"], "folder": e["folder"],
              "files": {k: v for k, v in sorted(e["files"].items())}} for e in s22_corpus if e["tier"] == 1]
    return jobs


def scenario_costs(job: Mapping[str, Any]) -> Tuple[str, str, MoveCosts]:
    """(scenario, map id, cost data) of one job, from the same data folders Sprint 18 (H0, HH) and Sprint 22 (HI)
    read."""
    if job["population"] == "H0":
        with gzip.open(REPO_ROOT / job["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
        scenario, map_id, root = str(header["scenario_id"]), str(header["map_id"]), DATA
    elif job["population"] == "HH":
        record = json.loads((REPO_ROOT / job["record"]["path"]).read_text(encoding="utf-8"))
        scenario, map_id, root = str(record["scenario_id"]), str(record["map_id"]), DATA
    else:
        record = json.loads((REPO_ROOT / job["files"]["record"]["file"]).read_text(encoding="utf-8"))
        card = json.loads((REPO_ROOT / "evaluation" / job["folder"] / "manifest.json").read_text(encoding="utf-8"))
        scenario = str(record["scenario_id"])
        map_id = str(next(s["map_id"] for s in card["scenarios"] if str(s["scenario_id"]) == scenario))
        root = LOCAL_EVAL / job["folder"] / "data"
    inputs = sdk_data.load_inputs(root / scenario / "Data", scenario, map_id)
    return scenario, map_id, MoveCosts.from_raw(inputs.cost, Origin.ENGINE, "setup_info.cost_data")


def cost_digest(job: Mapping[str, Any]) -> str:
    scenario, map_id, _ = scenario_costs(job)
    root = DATA if job["population"] in ("H0", "HH") else LOCAL_EVAL / job["folder"] / "data"
    inputs = sdk_data.load_inputs(root / scenario / "Data", scenario, map_id)
    return canonical_sha256(inputs.cost)


def freeze() -> Dict[str, Any]:
    s18 = json.loads(S18_INPUTS.read_text(encoding="utf-8"))
    s22 = json.loads(S22_INPUTS.read_text(encoding="utf-8"))
    jobs = jobs_from(s18, s22["corpus"])
    problems = file_problems(jobs)
    if problems:
        raise SystemExit(f"refused: pinned corpus files differ: {problems[:5]}")
    return {"schema": sd.SCHEMA + "/inputs", "study_id": sd.STUDY_ID, "rules_sha256": sd.rules_digest(),
            "readiness": sd.READINESS, "candidate": {"identity": x1.CANDIDATE_ID, "status": x1.STATUS,
                                                     "executable": x1.EXECUTABLE},
            "sources": {rel: sc.normalized_sha256(REPO_ROOT / rel) for rel in SOURCES},
            "s18_inputs_sha256": sha256(S18_INPUTS), "s22_inputs_sha256": sha256(S22_INPUTS),
            "s22_witness_sha256": sha256(S22_WITNESS), "s22_witness_reference_sha256": sha256(S22_REFERENCE),
            "jobs": jobs, "cost_data": {j["game"]: cost_digest(j) for j in jobs},
            "excluded": ["BOKE-2026", "the stopped 360-game prevalence study", "sparse captures"]}


def file_problems(jobs: Sequence[Mapping[str, Any]]) -> List[str]:
    problems = []
    for job in jobs:
        pins = []
        if job["population"] == "H0":
            pins = [(job["path"], job["sha256"])]
        elif job["population"] == "HH":
            pins = [(job[k]["path"], job[k]["sha256"]) for k in ("record", "timeline")]
        else:
            pins = [(v["file"], v["sha256"]) for v in job["files"].values()]
        for rel, digest in pins:
            if not (REPO_ROOT / rel).exists() or sha256(REPO_ROOT / rel) != digest:
                problems.append(rel)
    return problems


def input_problems(committed: Mapping[str, Any]) -> List[str]:
    problems = file_problems(committed["jobs"])
    for rel, digest in committed["sources"].items():
        if sc.normalized_sha256(REPO_ROOT / rel) != digest:
            problems.append(rel)
    for path, key in ((S18_INPUTS, "s18_inputs_sha256"), (S22_INPUTS, "s22_inputs_sha256"),
                      (S22_WITNESS, "s22_witness_sha256"), (S22_REFERENCE, "s22_witness_reference_sha256")):
        if sha256(path) != committed[key]:
            problems.append(path.relative_to(REPO_ROOT).as_posix())
    if committed["rules_sha256"] != sd.rules_digest() or committed["readiness"] != sd.READINESS:
        problems.append("rules")
    return problems


# ------------------------------------------------------------------------------------------------
# one side-game


def raw_free_flow(router: Router):
    def free_flow(unit: Mapping[str, Any], path: Sequence[Any]) -> Optional[int]:
        times, _ = tb.path_times(router, unit.get("type"), unit.get("move_state"), unit.get("basic_speed"),
                                 unit.get("cur_hex"), list(path))
        return None if times is None else sum(times)
    return free_flow


def moment(k: int, raw: Mapping[str, Any], faction: int, base: Sequence[Mapping[str, Any]]) -> sd.Moment:
    ground: Dict[Any, int] = collections.Counter()
    where: Dict[int, Tuple[Any, bool]] = {}
    for u in raw.get("operators") or ():
        if u.get("color") == faction and u.get("type") in (sd.INFANTRY, sd.VEHICLE):
            ground[u.get("cur_hex")] += 1
            where[u["obj_id"]] = (u.get("cur_hex"), bool(u.get("move_path") or ()))
    orders = {a["obj_id"]: list(a["move_path"])[-1] for a in base if a.get("type") == sd.MOVE and a.get("move_path")}
    flags = {c.get("coord"): c.get("flag") for c in raw.get("cities") or ()}
    return sd.Moment(k=k, cur_step=(raw.get("time") or {}).get("cur_step"), flags=flags, ground=dict(ground),
                     where=where, orders=orders)


def decisions(job: Mapping[str, Any]):
    """Yields, per analysed side of the job, (side key, seat, faction, iterator of (raw, recorded actions, recorded
    baseline-v2 memory or None))."""
    if job["population"] == "H0":
        rows: Dict[int, List[Tuple[Any, Any]]] = collections.defaultdict(list)
        factions: Dict[int, int] = {}
        with gzip.open(REPO_ROOT / job["path"], "rt", encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                row = json.loads(line)
                rows[row["seat"]].append((row["observation"], row["actions"]))
                factions[row["seat"]] = row["faction"]
        for seat in sorted(rows):
            yield seat, seat, factions[seat], ((typed_json.decode(o), a, None) for o, a in rows[seat])
    elif job["population"] == "HH":
        record = json.loads((REPO_ROOT / job["record"]["path"]).read_text(encoding="utf-8"))
        with (REPO_ROOT / job["timeline"]["path"]).open("rb") as handle:
            windows = pickle.load(handle)
        samples = sorted(windows["samples"], key=lambda s: s["k"])
        seat = next(s["seat"] for s in record["seats"] if s["policy"] == V2)
        faction = next(s["faction"] for s in record["seats"] if s["policy"] == V2)

        def it():
            for sample in samples:
                snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
                yield pickle.loads(snap["observation"]), snap.get("submitted") or [], None
        yield seat, seat, faction, it()
    else:
        s22 = load_script("s22_analysis")
        entry = next(e for e in s22.corpus() if e["game"] == job["game"])
        game = s22.Game(entry)

        def it():
            for k in range(len(game.steps)):
                yield game.raw(k), game.submitted(k), s22.baseline_memory(game.memory(k))
        yield entry["seat"], entry["seat"], entry["faction"], it()


def baseline(costs: MoveCosts):
    """baseline-v2's decision for one side: on the recorded baseline-v2 memory when the record carries it (HI), else
    on its own memory chained from an empty memory (H0, HH; Sprint 18's reconstruction)."""
    from miaosuan_agent.decision import Memory
    chained = ShootReservationPolicy(costs)
    state = {"memory": Memory()}

    def decide(observation: Observation, seat: int, faction: int, recorded_memory: Any) -> Sequence[Any]:
        if recorded_memory is None:
            decision = chained.decide(observation, seat, faction, state["memory"])
            state["memory"] = decision.memory
        else:
            decision = ShootReservationPolicy(costs).decide(observation, seat, faction, recorded_memory)
        return decision.actions
    return decide


def side_game(job: Mapping[str, Any], smoke: bool = False) -> List[Dict[str, Any]]:
    scenario, map_id, costs = scenario_costs(job)
    router = Router(costs)
    ff_obs = x1.router_free_flow(router)
    ff_raw = raw_free_flow(router)
    results = []
    for side_key, seat, faction, stream in decisions(job):
        out = run_side(job, scenario, seat, faction, stream, baseline(costs), ff_obs, ff_raw, smoke)
        results.append(out)
    return results


def run_side(job, scenario, seat, faction, stream, decide, ff_obs, ff_raw, smoke) -> Dict[str, Any]:
    """One analysed side: baseline-v2 at every decision (``decide``), the fidelity counts, the recorded history, the
    funnel of the nine conditions on every play decision, the candidate's first divergence and the recorded-state
    episodes with their projections."""
    population = job["population"]
    history: List[sd.Moment] = []
    funnel: Dict[str, int] = collections.Counter()
    distinct: Dict[str, set] = collections.defaultdict(set)
    selections: List[Tuple[int, List[x1.Pair]]] = []
    problems: List[str] = []
    private_values: set = set()
    first_difference = None  # first decision where baseline-v2 differs from the recorded actions
    differs = decisions_n = play_n = 0
    first_trigger = None
    certificates = 0
    order_sensitive = 0
    infantry_moves = 0
    max_step = None
    city_values: Dict[Any, Any] = {}
    faction_label = "red" if faction == 0 else "blue"
    for k, (raw, recorded, recorded_memory) in enumerate(stream):
        decisions_n += 1
        observation = Observation.from_raw(raw, Origin.ENGINE)
        actions = decide(observation, seat, faction, recorded_memory)
        base = rd.plain(list(actions))
        if [dict(a) for a in actions] != [dict(a) for a in recorded]:
            differs += 1
            if first_difference is None:
                first_difference = k
        history.append(moment(k, raw, faction, base))
        if not city_values:
            city_values = {c.get("coord"): c.get("value") for c in raw.get("cities") or ()}
        for u in list(raw.get("operators") or ()) + list(raw.get("passengers") or ()):
            private_values.add(u.get("obj_id"))
            private_values.add(u.get("cur_hex"))
        private_values.update(c.get("coord") for c in raw.get("cities") or ())
        max_step = (raw.get("time") or {}).get("max_step")
        if observation.time().stage != Stage.PLAY:
            continue
        play_n += 1
        if smoke:
            continue
        view = x1.p1.View(observation, seat, faction)
        own_inf = [u for u, x in view.own.items() if x1.p1.is_class(x, x1.INFANTRY_TYPE, x1.INFANTRY_SUB)]
        own_ifv = [u for u, x in view.own.items() if x1.p1.is_class(x, x1.VEHICLE_TYPE, x1.IFV_SUB)]
        distinct["infantry_present"].update(own_inf)
        distinct["ifv_present"].update(own_ifv)
        infantry_moves += sum(1 for a in base if a.get("obj_id") in own_inf and a.get("type") == sd.MOVE)
        for inf in own_inf:
            options = [o for o in (view.valid.get(inf) or {}).get(x1.EMBARK) or ()
                       if o.get("target_obj_id") in own_ifv]
            if options:
                funnel["embark_listing_unit_decisions"] += 1
                funnel["embark_listing_options"] += len(options)
        cands = x1.pairs(observation, view, base, (), ff_obs)
        selected, outcome = x1.match(cands, view, {})
        alternative, _ = x1.match(cands, view, {}, order=x1.id_key)
        if {(p.infantry, p.carrier) for p in selected} != {(p.infantry, p.carrier) for p in alternative}:
            order_sensitive += 1
        stages = ["co_located"] + list(x1.CONDITIONS)
        for p in cands:
            key = (p.infantry, p.carrier)
            reached = stages.index(p.failed) if p.failed else len(stages)
            for name in stages[:reached]:
                passed = "co_located" if name == "co_located" else f"pass_{name}"
                funnel[f"{passed}_pair_decisions"] += 1
                distinct[passed].add(key)
            if p.failed is None:
                funnel[f"outcome_{outcome[key]}_pair_decisions"] += 1
                distinct[f"outcome_{outcome[key]}"].add(key)
                if p.unable_on_foot:
                    distinct["unable_on_foot"].add(key)
        dests = [p.destination for p in selected]
        if len(dests) != len(set(dests)) or any(v == "c9_destination" for v in outcome.values()):
            funnel["decisions_with_destination_contention"] += 1
        if not selected:
            if first_trigger is None:
                live = x1.step(observation, seat, faction, base, (), ff_obs)[0]
                certificates += rd.plain(list(live)) == base
            continue
        funnel["decisions_with_a_selection"] += 1
        funnel["selected_pair_decisions"] += len(selected)
        live, changes, _ = x1.step(observation, seat, faction, base, (), ff_obs)
        live = rd.plain(list(live))
        embarks = sorted((c["obj_id"], c["target_obj_id"]) for c in changes if c.get("kind") == "embark")
        if embarks != sorted((p.infantry, p.carrier) for p in selected):
            problems.append(f"{job['game']} seat {seat} decision {k}: the step's embarks differ from the matching")
        found = sd.batch_problems(raw, seat, faction, base, live, embarks, ff_raw)
        problems.extend(f"{job['game']} seat {seat} decision {k}: {f}" for f in found)
        selections.append((k, selected))
        if first_trigger is None:
            first_trigger = k
    out: Dict[str, Any] = {"population": population, "game": job["game"], "scenario": scenario, "seat": seat,
                           "faction": faction, "side": faction_label, "decisions": decisions_n,
                           "play_decisions": play_n, "baseline_v2_differs_from_recorded": differs,
                           "first_difference_from_recorded": first_difference, "problems": problems,
                           "private_values": sorted(v for v in private_values if isinstance(v, int)),
                           "max_step": max_step, "labels": tl.labels(city_values)}
    if smoke:
        out["history_steps"] = [m.cur_step for m in history[:3]]
        return out
    # episodes on recorded states: maximal runs of consecutive decisions selecting the same pair
    chosen = {(k, (p.infantry, p.carrier)): p for k, selected in selections for p in selected}
    episodes: List[Dict[str, Any]] = []
    for k, key in sd.group_runs([(k, [(p.infantry, p.carrier) for p in selected]) for k, selected in selections]):
        p = chosen[(k, key)]
        episodes.append({"k": k, "pair": key, "destination": p.destination, "carrier_free_flow": p.carrier_free_flow,
                         "infantry_free_flow": p.infantry_free_flow, "saving": p.saving})
    for e in episodes:
        e.update(sd.project(history, e["k"], faction, max_step, e["pair"], e["destination"], e["carrier_free_flow"],
                            e["infantry_free_flow"]))
    valid_first = (first_trigger is not None
                   and (population != "H0" or first_difference is None or first_difference >= first_trigger))
    first = [dict(e) for e in episodes if e["k"] == first_trigger] if first_trigger is not None else []
    for e in first:
        e["valid_first_divergence"] = valid_first
    out.update({"funnel": dict(funnel), "distinct": {k: len(v) for k, v in distinct.items()},
                "infantry_move_actions": infantry_moves, "order_sensitive_decisions": order_sensitive,
                "pre_trigger_certificates": certificates, "first_trigger_decision": first_trigger,
                "first_trigger_valid": valid_first, "first_batch": first, "episodes": episodes,
                "selected_decisions": [k for k, _ in selections]})
    return out


# ------------------------------------------------------------------------------------------------
# the study


def worker(args: Tuple[Mapping[str, Any], bool]) -> List[Dict[str, Any]]:
    job, smoke = args
    return side_game(job, smoke)


def compute(committed: Mapping[str, Any], smoke: bool, workers: int) -> List[Dict[str, Any]]:
    jobs = committed["jobs"]
    with multiprocessing.Pool(min(workers, len(jobs))) as pool:
        parts = pool.map(worker, [(job, smoke) for job in jobs])
    return [side for part in parts for side in part]


def consistency(sides: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    h0 = [s for s in sides if s["population"] == "H0"]
    hh = [s for s in sides if s["population"] == "HH"]
    hi = [s for s in sides if s["population"] == "HI"]
    got = {"H0 decisions": sum(s["decisions"] for s in h0), "H0 play decisions": sum(s["play_decisions"] for s in h0),
           "H0 v2 differs from recorded v0": sum(s["baseline_v2_differs_from_recorded"] for s in h0),
           "HH decisions": sum(s["decisions"] for s in hh)}
    checks = {k: {"published": v, "study": got[k], "equal": got[k] == v} for k, v in PUBLISHED.items()}
    checks["HH baseline-v2 reconstruction equals the recorded seat"] = {
        "published": sum(s["decisions"] for s in hh),
        "study": sum(s["decisions"] - s["baseline_v2_differs_from_recorded"] for s in hh),
        "equal": all(s["baseline_v2_differs_from_recorded"] == 0 for s in hh) and len(hh) == 4}
    checks["HI baseline-v2 reconstruction equals the recorded seat"] = {
        "published": None, "study": sum(s["decisions"] - s["baseline_v2_differs_from_recorded"] for s in hi),
        "equal": all(s["baseline_v2_differs_from_recorded"] == 0 for s in hi) and len(hi) == 3}
    return checks


def known_answers(sides: Sequence[Mapping[str, Any]], witness: Mapping[str, Any],
                  reference: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Sprint 22's published tier-1 trigger rows: the candidate keeps a pair whose two routes end on the same objective
    and drops the one whose routes end on different objectives (condition 5); the Sprint 22 witness pair is in the
    first batch of its game."""
    rows = {r["game"]: r for r in witness["rows"] if r.get("tier") == 1 and r.get("trigger")}
    out = {}
    for side in sides:
        if side["population"] != "HI" or side["game"] not in rows:
            continue
        row = rows[side["game"]]
        pair = tuple((reference["triggers"].get(side["game"]) or {}).get("pair") or ())
        same = row["destination"] == row["infantry_own_objective"]
        in_first = any(tuple(e["pair"]) == pair for e in side.get("first_batch") or ())
        agrees = (in_first and side.get("first_trigger_decision") == row["trigger_decision"]) if same else not in_first
        out[side["game"]] = {"same_objective_in_sprint22": same, "pair_in_first_batch": in_first, "agrees": agrees}
    return out


def build(committed: Mapping[str, Any], workers: int) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any],
                                                                 Dict[str, Any], set]:
    sides = compute(committed, False, workers)
    witness = json.loads(S22_WITNESS.read_text(encoding="utf-8"))
    reference = json.loads(S22_REFERENCE.read_text(encoding="utf-8"))
    checks = consistency(sides)
    answers = known_answers(sides, witness, reference)
    invalid = [f"consistency: {k}" for k, v in checks.items() if not v["equal"]]
    invalid += [f"known answer: {g}" for g, v in answers.items() if not v["agrees"]]
    invalid += [p for s in sides for p in s["problems"]]
    private_values = {v for s in sides for v in s["private_values"]}
    # public rows
    side_rows, first_rows, recorded_rows, batches = [], [], [], []
    for s in sides:
        label = s["labels"]
        side_rows.append({"population": s["population"], "game": s["game"], "scenario": s["scenario"],
                          "side": s["side"], "decisions": s["decisions"], "play_decisions": s["play_decisions"],
                          "baseline_v2_differs_from_recorded": s["baseline_v2_differs_from_recorded"],
                          "first_difference_from_recorded": s["first_difference_from_recorded"],
                          "funnel": dict(sorted(s["funnel"].items())),
                          "distinct": dict(sorted(s["distinct"].items())),
                          "infantry_move_actions": s["infantry_move_actions"],
                          "order_sensitive_decisions": s["order_sensitive_decisions"],
                          "pre_trigger_certificates": s["pre_trigger_certificates"],
                          "first_trigger_decision": s["first_trigger_decision"],
                          "first_trigger_valid": s["first_trigger_valid"],
                          "first_batch_size": len(s["first_batch"]),
                          "recorded_state_episodes": len(s["episodes"]),
                          "recorded_state_distinct_infantry": len({e["pair"][0] for e in s["episodes"]})})
        batches.append({"population": s["population"], "game": s["game"], "scenario": s["scenario"],
                        "condition": s["game"].split(".")[1], "side": s["side"],
                        "batch_size": len(s["first_batch"]) if s["first_trigger_valid"] else 0})
        for e in s["episodes"]:
            row = public_episode(s, e, label)
            row["first_divergence"] = bool(s["first_trigger_valid"] and e["k"] == s["first_trigger_decision"])
            row["evidence"] = ("first divergence" if row["first_divergence"] else
                               "recorded state, off-policy for the candidate")
            recorded_rows.append(row)
            if row["first_divergence"]:
                first_rows.append(row)
    verdict = sd.disposition(invalid, first_rows)
    proposal = sd.screen(first_rows, batches) if verdict["disposition"] == sd.READY else None
    prevalence = {"schema": sd.SCHEMA + "/prevalence", "study_id": sd.STUDY_ID, "sides": side_rows,
                  "pooled": pooled(side_rows), "consistency": checks, "known_answers": answers}
    episodes = {"schema": sd.SCHEMA + "/episodes", "study_id": sd.STUDY_ID, "roles": sd.ROLES,
                "first_divergence": first_rows, "first_divergence_summary": summary(first_rows),
                "recorded_state_summary": {p: summary([r for r in recorded_rows if r["population"] == p
                                                       and not r["first_divergence"]]) for p in sd.POPULATIONS},
                "note": "projected mechanical quantities; after the first divergence every recorded state is "
                        "off-policy for the candidate"}
    disposition = {"schema": sd.SCHEMA + "/disposition", "study_id": sd.STUDY_ID, **verdict,
                   "order": list(sd.DISPOSITIONS), "readiness": sd.READINESS, "screen": proposal,
                   "invalid_problem_count": len(invalid)}
    private = {"sides": [{k: v for k, v in s.items() if k not in ("private_values",)} for s in sides],
               "invalid": invalid}
    return prevalence, episodes, disposition, private, private_values


PUBLIC_EPISODE_KEYS = ("trigger_step", "carrier_free_flow", "infantry_free_flow", "projected_carrier_arrival",
                       "projected_delivery", "foot_arrival", "projected_saving", "unable_on_foot",
                       "on_objective_gain", "occupancy_at_trigger", "others_at_projected_arrival",
                       "saturated_at_arrival", "saturated_through_settle_bound", "role", "carrier_arrived_in_history",
                       "first_move_delay", "moves_in_expected_hold", "claimant_elsewhere",
                       "destination_held_at_arrival", "projected_suppressed_decisions")


def public_episode(side: Mapping[str, Any], e: Mapping[str, Any], labels: Mapping[Any, str]) -> Dict[str, Any]:
    row = {"population": side["population"], "game": side["game"], "scenario": side["scenario"],
           "side": side["side"], "trigger_decision": e["k"], "destination": labels.get(e["destination"]),
           "same_decision_pairs_to_destination": sum(1 for o in side["episodes"]
                                                     if o["k"] == e["k"] and o["destination"] == e["destination"])}
    row.update({k: e.get(k) for k in PUBLIC_EPISODE_KEYS})
    return row


def summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    def dist(values: Sequence[Any]) -> Dict[str, Any]:
        values = sorted(v for v in values if v is not None)
        if not values:
            return {"n": 0}
        return {"n": len(values), "min": values[0], "median": values[len(values) // 2] if len(values) % 2 else
                (values[len(values) // 2 - 1] + values[len(values) // 2]) / 2, "max": values[-1]}
    return {"episodes": len(rows), "side_games": len({(r["game"], r["side"]) for r in rows}),
            "scenarios": len({r["scenario"] for r in rows}),
            "roles": dict(sorted(collections.Counter(r["role"] for r in rows).items())),
            "unable_on_foot": sum(1 for r in rows if r["unable_on_foot"]),
            "saturated_at_arrival": sum(1 for r in rows if r["saturated_at_arrival"]),
            "saturated_through_settle_bound": sum(1 for r in rows if r["saturated_through_settle_bound"]),
            "claimant_elsewhere": sum(1 for r in rows if r["claimant_elsewhere"]),
            "carrier_arrived_in_history": sum(1 for r in rows if r["carrier_arrived_in_history"]),
            "destination_held_at_arrival": sum(1 for r in rows if r["destination_held_at_arrival"]),
            "projected_saving": dist([r["projected_saving"] for r in rows]),
            "on_objective_gain": dist([r["on_objective_gain"] for r in rows]),
            "first_move_delay": dist([r["first_move_delay"] for r in rows]),
            "projected_suppressed_decisions": dist([r["projected_suppressed_decisions"] for r in rows])}


def pooled(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for population in list(sd.POPULATIONS) + ["all"]:
        part = [r for r in rows if population == "all" or r["population"] == population]
        funnel: Dict[str, int] = collections.Counter()
        for r in part:
            funnel.update(r["funnel"])
        out[population] = {"side_games": len(part), "decisions": sum(r["decisions"] for r in part),
                           "play_decisions": sum(r["play_decisions"] for r in part), "funnel": dict(sorted(funnel.items())),
                           "infantry_move_actions": sum(r["infantry_move_actions"] for r in part),
                           "side_games_with_a_trigger": sum(1 for r in part if r["first_trigger_decision"] is not None),
                           "side_games_with_a_valid_first_divergence": sum(1 for r in part if r["first_trigger_valid"]),
                           "first_divergence_pairs": sum(r["first_batch_size"] for r in part if r["first_trigger_valid"]),
                           "recorded_state_episodes": sum(r["recorded_state_episodes"] for r in part),
                           "order_sensitive_decisions": sum(r["order_sensitive_decisions"] for r in part)}
    return out


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
    for name in ("freeze", "run"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
        p.add_argument("--workers", type=int, default=8)
    p = sub.add_parser("smoke")
    p.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.command == "freeze":
        return 0 if write_or_check(INPUTS, sd.dump(freeze()), args.check) else 1
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed)
    if problems:
        print(f"REFUSED: inputs differ from the committed inputs.json: {problems[:5]}", file=sys.stderr)
        return 1
    if args.command == "smoke":
        sides = compute(committed, True, args.workers)
        checks = consistency(sides)
        for name, value in checks.items():
            print(f"{'OK  ' if value['equal'] else 'FAIL'} {name}: published {value['published']} study {value['study']}")
        print("side-games", len(sides), "problems", sum(len(s["problems"]) for s in sides))
        return 0 if all(v["equal"] for v in checks.values()) else 1
    prevalence, episodes, disposition, private, private_values = build(committed, args.workers)
    for name, data in (("prevalence", prevalence), ("episodes", episodes), ("disposition", disposition)):
        found = sd.public_problems(data, private_values)
        if found:
            print(f"REFUSED: public {name} fails the privacy check: {found[:5]}", file=sys.stderr)
            return 1
    ok = True
    if not args.check:
        PRIVATE.mkdir(parents=True, exist_ok=True)
        (PRIVATE / "study-private.json.gz").write_bytes(
            gzip.compress(json.dumps(private, sort_keys=True, default=repr).encode("utf-8"), mtime=0))
    for path, data in ((PREVALENCE, prevalence), (EPISODES, episodes), (DISPOSITION, disposition)):
        ok = write_or_check(path, sd.dump(data), args.check) and ok
    print(f"disposition {disposition['disposition']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
