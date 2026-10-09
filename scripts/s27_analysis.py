"""Sprint 27 T6-S two-seat mechanism probe: references, rehearsal, inputs and the post-game analysis
(``docs/SPRINT27_T6S_PROBE.md``).

    python scripts/s27_analysis.py references [--check]   # the frozen HH references (P1, P2, descriptive)
    python scripts/s27_analysis.py rehearse [--check]     # the candidate against Sprint 26's frozen rule
    python scripts/s27_analysis.py inputs [--check]       # the registration's pins
    python scripts/s27_analysis.py game --position N [--check]   # one game: stops, fidelity, P1, P2, mechanism, gate
    python scripts/s27_analysis.py disposition [--check]  # the probe's registered disposition

Runs on the evaluation server (the captures are private, under the ignored ``local/``). ``references`` and
``rehearse`` read the four Sprint 12 head-to-head timelines (and, for the rehearsal, Sprint 26's H0 population) through
Sprint 26's own driver and loader (``scripts/s26_t6s.py``, unchanged), refusing unless every Sprint 26 input pin
matches. Public outputs go to ``evaluation/s27-t6s-probe/``; private ones (unit ids, hexes, routes) to
``local/diagnostics/s27/``. ``--check`` regenerates and compares byte for byte without writing.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import importlib.util
import json
import pickle
import statistics
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data  # noqa: E402
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory  # noqa: E402
from miaosuan_agent.decision.routing import Router  # noqa: E402
from miaosuan_agent.evaluation import residual516 as rd  # noqa: E402
from miaosuan_agent.evaluation import s18_census as sc  # noqa: E402
from miaosuan_agent.evaluation import s26_t6s as st  # noqa: E402
from miaosuan_agent.evaluation import s27_capture as cap  # noqa: E402
from miaosuan_agent.evaluation import s27_probe as sp  # noqa: E402
from miaosuan_agent.experiments import t6s_column_stagger_p1 as cand  # noqa: E402
from miaosuan_agent.experiments.exploratory_addon import AddonMemory  # noqa: E402

PUBLIC = REPO_ROOT / "evaluation" / sp.STUDY_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s27"
S26 = REPO_ROOT / "evaluation" / "s26-t6s-shadow"
REFERENCES = PUBLIC / "references.json"
REHEARSAL = PUBLIC / "rehearsal.json"
INPUTS = PUBLIC / "inputs.json"
DISPOSITION = PUBLIC / "disposition.json"
WORK = REPO_ROOT / "local" / "evaluation" / sp.CARD_ID
LEDGER = REPO_ROOT / "local" / "engines" / "sdk-4.1.0" / "usage-ledger.jsonl"
HH_FIRST_DIVERGENCE = {"HH p01 baseline-v2 blue": (162, 161), "HH p02 baseline-v2 red": (402, 401),
                       "HH p03 baseline-v2 blue": (162, 161), "HH p04 baseline-v2 red": (402, 401)}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalised(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def load_script(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"s27_{name}", REPO_ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def write_private(path: Path, data: Any, check: bool) -> bool:
    blob = gzip.compress(json.dumps(data, sort_keys=True, default=repr).encode("utf-8"), mtime=0)
    if check:
        same = path.exists() and path.read_bytes() == blob
        print(f"{'OK' if same else 'MISMATCH'} private {path.name}")
        return same
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return True


def dist(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


# ------------------------------------------------------------------------------------------------
# Sprint 26's driver and loader, unchanged


def s26_committed() -> Tuple[types.ModuleType, Dict[str, Any]]:
    driver = load_script("s26_t6s")
    committed = json.loads((S26 / "inputs.json").read_text(encoding="utf-8"))
    proto = json.loads((S26 / "protocol.json").read_text(encoding="utf-8"))
    problems = driver.input_problems(committed, proto)
    if problems:
        raise SystemExit(f"refused: Sprint 26 inputs or frozen sources differ from their pins: {problems[:5]}")
    return driver, committed


def hh_loader() -> Any:
    driver, committed = s26_committed()
    loader = driver.make_loader(committed)
    for entry in committed["HH"]["games"]:
        loader.timeline_game("HH", entry)
    return loader


def first_ownership_steps(frames: Sequence[Any], faction: int, names: Mapping[Any, str]) -> Dict[str, Optional[int]]:
    """Per objective label, the cur_step of the side's first play-stage ownership (``s26_t6s.first_ownership``)."""
    out = {}
    for coord, label in names.items():
        k = st.first_ownership(frames, faction, coord)
        out[label] = None if k is None else frames[k].cur_step
    return dict(sorted(out.items()))


def moving_damage(rows: Sequence[Mapping[str, Any]]) -> Dict[str, int]:
    """Damage events on moving own ground units (not on board), stacked victims against alone (Sprint 18's event
    rows; Sprint 26's moving-damage split)."""
    ground = [r for r in rows if r["victim_class"] in ("infantry", "vehicle", "artillery") and not r["aboard"]
              and r["moving"]]
    return {"moving_ground_damage_events": len(ground),
            "moving_ground_damage_events_stacked": sum(1 for r in ground if r["stacked"]),
            "moving_ground_damage_events_alone": sum(1 for r in ground if not r["stacked"])}


# ------------------------------------------------------------------------------------------------
# references (registration)


def references() -> Tuple[Dict[str, Any], set]:
    loader = hh_loader()
    published = {s["side_game"]: s for s in json.loads((S26 / "census.json").read_text(encoding="utf-8"))["sides"]}
    sides = {}
    for a in loader.analyses["HH"]:
        label = a.side.label
        names = st.objective_labels(a.side.values)
        rows = [r for r in loader.private["events"] if r["population"] == "HH" and r["game"] == a.side.game
                and r["faction"] == a.side.faction]
        sides[label] = {"colour": a.side.colour, "decisions": len(a.side.frames),
                        "play_decisions": sum(1 for f in a.side.frames if f.stage == 2),
                        "exposure": a.exposure, "exposure_equal_to_sprint26_published": a.exposure
                        == published[label]["exposure"],
                        "first_ownership_steps": first_ownership_steps(a.side.frames, a.side.faction, names),
                        "objective_labels": sorted(names.values()),
                        "first_divergence_sprint26": published[label]["first_divergence"],
                        **moving_damage(rows)}
    p1 = {colour: {label: sides[label]["exposure"].get("moving_stacked_inside_envelope", 0) for label in labels}
          for colour, labels in sp.HH_LABELS.items()}
    p2 = {colour: {obj: {label: sides[label]["first_ownership_steps"][obj] for label in labels}
                   for obj in sp.OBJECTIVES} for colour, labels in sp.HH_LABELS.items()}
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    anchors = {"every HH exposure equals Sprint 26's published per-side exposure":
               all(s["exposure_equal_to_sprint26_published"] for s in sides.values()),
               "HH side-games": len(sides) == 4 and sorted(sides) == sorted(l for ls in sp.HH_LABELS.values() for l in ls),
               "every HH side carries the registered seven objective labels":
               all(s["objective_labels"] == sorted(sp.OBJECTIVES) for s in sides.values()),
               "HH baseline-v2 reconstruction equal to the recorded seat at every decision": hh[0] == hh[1] == 11524,
               "P1 references equal the frozen rules": p1 == sp.RULES["p1"]["references"],
               "P2 references equal the frozen rules": p2 == sp.RULES["p2"]["references"]}
    out = {"schema": sp.SCHEMA + "/references", "study_id": sp.STUDY_ID,
           "sprint26_inputs_sha256": sha256(S26 / "inputs.json"), "sprint26_census_sha256": sha256(S26 / "census.json"),
           "sprint26_protocol_sha256": sha256(S26 / "protocol.json"),
           "evidence_boundary": "historical and descriptive: the four HH games (card s12-v3-primary-1) played "
                                "baseline-v2 against a different candidate (the batch-capacity allocator), so these "
                                "are exploratory benchmarks, not a randomized or paired control",
           "sides": sides, "p1_references": p1, "p2_references": p2, "anchors": anchors,
           "ok": all(anchors.values())}
    return out, loader.hexes | loader.ids


# ------------------------------------------------------------------------------------------------
# rehearsal (registration): the candidate against Sprint 26's frozen rule


def frozen_rule_file() -> Path:
    """Sprint 26's frozen rule file, located through Sprint 26's protocol pins (never named here) and checked
    against its pinned digest."""
    proto = json.loads((S26 / "protocol.json").read_text(encoding="utf-8"))
    paths = [p for p in proto["sources"] if p.startswith("src/miaosuan_agent/experiments/") and p.endswith("_shadow.py")]
    if len(paths) != 1:
        raise SystemExit("refused: Sprint 26's protocol does not pin exactly one experiments shadow")
    path = REPO_ROOT / paths[0]
    if normalised(path) != proto["sources"][paths[0]]:
        raise SystemExit("refused: Sprint 26's frozen rule differs from its pin")
    return path


def copied_block_problems(candidate_text: str, frozen_text: str) -> List[str]:
    """The candidate's marked block must equal the frozen file from its first documented code to its end."""
    frozen = frozen_text.replace("\r\n", "\n").split("\n")
    mine = candidate_text.replace("\r\n", "\n").split("\n")
    if mine.count(cand.COPY_BEGIN) != 1 or mine.count(cand.COPY_END) != 1:
        return ["the candidate does not carry exactly one marked copy"]
    block = mine[mine.index(cand.COPY_BEGIN) + 1:mine.index(cand.COPY_END)]
    original = frozen[frozen.index("MOVE = 1"):]
    while original and original[-1] == "":
        original.pop()
    return [] if block == original else ["the candidate's copy differs from Sprint 26's frozen rule"]


def event_tuple(e: Any) -> Tuple[Any, ...]:
    return (e.kind, e.eid, e.unit, e.step, e.index, e.reason, e.moved)


def frames_equivalence(a: Any) -> Dict[str, Any]:
    """The candidate's copied rule over one Sprint 26 side, from an empty memory, against Sprint 26's run of its frozen
    rule on the same frames: lists, withheld indices, events, mover checks and group outcomes at every decision."""
    memory = cand.StaggerMemory()
    differ = 0
    for f in a.side.frames:
        r = cand.decide(f.cur_step, f.stage, f.own, f.enemies.values(), f.valid, f.actions, memory, a.side.travel)
        memory = r.memory
        shadow_events = [event_tuple(e) for k, e in a.shadow.events if k == f.k]
        shadow_checks = [(i, u, c.eligible, c.reason) for k, i, u, c in a.shadow.checks if k == f.k]
        shadow_groups = [(o, h, units, outcome) for k, o, h, units, outcome in a.shadow.groups if k == f.k]
        same = (list(r.actions) == list(a.shadow.candidate[f.k])
                and list(r.withheld) == list(a.shadow.withheld.get(f.k, ()))
                and [event_tuple(e) for e in r.events] == shadow_events
                and [(i, u, c.eligible, c.reason) for i, u, c in r.checks] == shadow_checks
                and [tuple(g) for g in r.groups] == shadow_groups)
        differ += not same
    return {"decisions": len(a.side.frames), "differing_decisions": differ}


def hh_raw_equivalence(a: Any, entry: Mapping[str, Any], router: Any) -> Dict[str, Any]:
    """The executable candidate (``StaggerPolicy``: baseline-v2 then the add-on, on the raw seat observation and the
    recorded memory) over one HH side's recorded states, against Sprint 26's frozen rule on the same decisions."""
    record = json.loads((REPO_ROOT / entry["record"]["path"]).read_text(encoding="utf-8"))
    with (REPO_ROOT / entry["timeline"]["path"]).open("rb") as handle:
        windows = pickle.load(handle)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    seat = next(s["seat"] for s in record["seats"] if s["faction"] == a.side.faction)
    policy = cand.StaggerPolicy(router.costs)
    addon: Tuple[Tuple[int, int], ...] = ()
    differ = baseline_differ = errors = 0
    first = None
    for k, sample in enumerate(samples):
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        raw = pickle.loads(snap["observation"])
        recorded_memory = pickle.loads(snap["memory"])
        decision = policy.decide(Observation.from_raw(raw, Origin.ENGINE), seat, a.side.faction,
                                 AddonMemory(recorded_memory, addon))
        addon = decision.memory.addon
        errors += decision.trace.addon_error is not None
        live = [dict(x) for x in decision.actions]
        differ += rd.plain(live) != rd.plain(list(a.shadow.candidate[k]))
        baseline_differ += rd.plain(list(policy.baseline.decide(Observation.from_raw(raw, Origin.ENGINE), seat,
                                                                a.side.faction, recorded_memory).actions)) \
            != rd.plain(snap.get("submitted") or [])
        if first is None and len(live) != len(a.side.frames[k].actions):
            first = (k, a.side.frames[k].cur_step)
    expected = HH_FIRST_DIVERGENCE[a.side.label]
    return {"decisions": len(samples), "differing_decisions": differ, "baseline_v2_differs_from_recorded": baseline_differ,
            "addon_errors": errors, "first_divergence_decision": None if first is None else first[0],
            "first_divergence_step": None if first is None else first[1],
            "first_divergence_equals_sprint26": first == expected}


def rehearse() -> Dict[str, Any]:
    driver, committed = s26_committed()
    text_problems = copied_block_problems(
        (REPO_ROOT / "src" / "miaosuan_agent" / "experiments" / "t6s_column_stagger_p1.py").read_text(encoding="utf-8"),
        frozen_rule_file().read_text(encoding="utf-8"))
    loader = driver.load(committed)
    sides = {}
    scenarios = set()
    for pop in ("H0", "HH"):
        for a in loader.analyses[pop]:
            sides[a.side.label] = {"population": pop, **frames_equivalence(a)}
            scenarios.add(a.side.scenario)
    raw = {}
    for entry, a in zip(committed["HH"]["games"], loader.analyses["HH"]):
        record = json.loads((REPO_ROOT / entry["record"]["path"]).read_text(encoding="utf-8"))
        router = loader.router(str(record["scenario_id"]), str(record["map_id"]))
        raw[a.side.label] = hh_raw_equivalence(a, entry, router)
    totals = {"frames_decisions": sum(s["decisions"] for s in sides.values()),
              "frames_differing": sum(s["differing_decisions"] for s in sides.values()),
              "hh_raw_decisions": sum(s["decisions"] for s in raw.values()),
              "hh_raw_differing": sum(s["differing_decisions"] for s in raw.values()),
              "hh_baseline_v2_differs_from_recorded": sum(s["baseline_v2_differs_from_recorded"] for s in raw.values()),
              "hh_addon_errors": sum(s["addon_errors"] for s in raw.values())}
    ok = (not text_problems and totals["frames_differing"] == 0 and totals["hh_raw_differing"] == 0
          and totals["hh_baseline_v2_differs_from_recorded"] == 0 and totals["hh_addon_errors"] == 0
          and len(sides) == 20 and len(raw) == 4 and all(r["first_divergence_equals_sprint26"] for r in raw.values()))
    return {"schema": sp.SCHEMA + "/rehearsal", "study_id": sp.STUDY_ID, "scenarios": sorted(scenarios),
            "copied_rule_text_problems": text_problems,
            "frames_equivalence_by_side": sides, "hh_executable_candidate_by_side": raw, "totals": totals, "ok": ok,
            "note": "Sprint 26's frozen rule enters only through Sprint 26's own analysis (run_shadow on its loader); "
                    "its text is located through Sprint 26's protocol pins"}


# ------------------------------------------------------------------------------------------------
# inputs (registration)


def card_build() -> Dict[str, Any]:
    return load_script("build_s27_card").build()


def inputs() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import manifest as mf
    card = card_build()
    committed = json.loads((S26 / "inputs.json").read_text(encoding="utf-8"))
    return {"schema": sp.SCHEMA + "/inputs", "study_id": sp.STUDY_ID, "card_id": sp.CARD_ID,
            "card_canonical_sha256": mf.digest(card), "candidate": sp.CANDIDATE_ID,
            "candidate_policy_source_sha256": sp.CANDIDATE_DIGEST, "baseline_v2_policy_source_sha256": sp.V2_DIGEST,
            "rules_sha256": sp.rules_digest(), "references_sha256": sha256(REFERENCES),
            "rehearsal_sha256": sha256(REHEARSAL), "sprint26_inputs_sha256": sha256(S26 / "inputs.json"),
            "sprint26_protocol_sha256": sha256(S26 / "protocol.json"), "sprint26_census_sha256": sha256(S26 / "census.json"),
            "hh_pins": [{"game": entry["game"],
                         **{kind: {"file": entry[kind]["path"], "sha256": entry[kind]["sha256"]}
                            for kind in ("record", "timeline", "timeline_index")}}
                        for entry in committed["HH"]["games"]],
            "expected_sessions": list(sp.EXPECTED_SESSIONS),
            "ledger_base_session": sp.LEDGER_BASE_SESSION, "stages": dict(sp.STAGES)}


# ------------------------------------------------------------------------------------------------
# one game


def read_ledger(upto: int) -> List[Dict[str, Any]]:
    """The ledger up to session ``upto``, so that a game's public file regenerates after later sessions; the runner and
    the game entry point audit the whole live ledger."""
    records = [json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in records if r.get("session") is None or int(r["session"]) <= upto]


def card_and_entry(position: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    card = json.loads((REPO_ROOT / "evaluation" / sp.CARD_ID / "manifest.json").read_text(encoding="utf-8"))
    entry = next(g for g in card["games"] if g["screen_position"] == position)
    return card, entry


def costs_of(card: Mapping[str, Any], scenario: str) -> MoveCosts:
    map_id = next(s["map_id"] for s in card["scenarios"] if s["scenario_id"] == scenario)
    inputs_ = sdk_data.load_inputs(WORK / "data" / scenario / "Data", scenario, map_id)
    return MoveCosts.from_raw(inputs_.cost, Origin.ENGINE, "setup_info.cost_data")


def frame(k: int, raw: Mapping[str, Any], faction: int, actions: Sequence[Mapping[str, Any]]) -> Any:
    """Sprint 18's census frame, with the carrier counts Sprint 26's loader adds."""
    f = sc.frame_from_raw(k, raw, faction, actions)
    f.carrying = {u.get("obj_id"): len(u.get("passenger_ids") or ()) for u in raw.get("operators") or ()
                  if isinstance(u, Mapping) and u.get("color") == faction and u.get("passenger_ids")}
    return f


def public_episode(e: Mapping[str, Any], ordinal: int) -> Dict[str, Any]:
    out = {k: v for k, v in e.items() if k not in ("private", "followers")}
    out["episode_ordinal"] = ordinal
    out["followers"] = [dict(f) for f in e["followers"]]
    return out


def analyse_game(position: int) -> Tuple[Dict[str, Any], Dict[str, Any], set]:
    card, entry = card_and_entry(position)
    game_entry = load_script("run_s27_game")
    gid = entry["game_id"]
    stops = {k: list(v) for k, v in game_entry.recorded_stops(card, entry, WORK).items()}
    audit = sp.ledger_audit(read_ledger(sp.LEDGER_BASE_SESSION + position), card)
    for code, found in audit["problems"].items():
        stops.setdefault(code, []).extend(found)
    if audit["sessions"] != position or audit["games"].get(gid) != str(sp.LEDGER_BASE_SESSION + position):
        stops.setdefault("S2", []).append(f"the game is not session {sp.LEDGER_BASE_SESSION + position}")
    record = json.loads((WORK / "games" / f"{gid}.json").read_text(encoding="utf-8"))
    compact = json.loads((WORK / "capture" / f"{gid}.timeline.json").read_text(encoding="utf-8"))
    with (WORK / "capture" / f"{gid}.timeline.pkl").open("rb") as handle:
        windows = pickle.load(handle)
    side_name = sp.candidate_side(entry)
    faction = 0 if side_name == "red" else 1
    seat = next(s["seat"] for s in record["seats"] if s["policy"] == sp.CANDIDATE_ID)
    opp_seat = next(s["seat"] for s in record["seats"] if s["policy"] == sp.V2_ID)
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    steps = compact["steps"]
    fidelity: Dict[str, Any] = {"one_snapshot_per_decision": [s["k"] for s in samples] == list(range(len(steps)))}
    costs = costs_of(card, entry["scenario_id"])
    travel = cand.router_travel(Router(costs))
    # offline re-derivation of both seats from empty memories, against the carried memories and emitted actions
    base_mem: Any = Memory()
    addon_mem: Tuple[Tuple[int, int], ...] = ()
    v2_mem: Any = Memory()
    raws, opp_raws, baseline, live, opp_live, feedback, rule_events, withheld = [], [], [], [], [], [], [], []
    differ = memory_differ = unregistered = opp_differ = opp_memory_differ = 0
    for k, sample in enumerate(samples):
        snap = sample["seats"].get(seat) or sample["seats"].get(str(seat))
        osnap = sample["seats"].get(opp_seat) or sample["seats"].get(str(opp_seat))
        raw, oraw = pickle.loads(snap["observation"]), pickle.loads(osnap["observation"])
        emitted = [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == seat]
        oemitted = [a["action"] for a in steps[k].get("submitted") or () if a["seat"] == opp_seat]
        memory_differ += cap.split_memory(pickle.loads(snap["memory"])) != (base_mem, addon_mem)
        rebuilt = cap.reconstruct(raw, seat, faction, AddonMemory(base_mem, addon_mem), costs, travel)
        differ += rebuilt["actions"] != rd.plain(emitted)
        unregistered += bool(sp.unregistered_differences(rebuilt["baseline_actions"], emitted, rebuilt["withheld"]))
        base_mem, addon_mem = rebuilt["baseline_memory_out"], tuple(tuple(p) for p in rebuilt["memory_out"])
        opp_memory_differ += pickle.loads(osnap["memory"]) != v2_mem
        orebuilt = cap.reconstruct_v2(oraw, opp_seat, 1 - faction, v2_mem, costs)
        opp_differ += orebuilt["baseline_actions"] != rd.plain(oemitted)
        v2_mem = orebuilt["memory_out"]
        raws.append(raw)
        opp_raws.append(oraw)
        baseline.append(rebuilt["baseline_actions"])
        live.append(rd.plain(emitted))
        opp_live.append(rd.plain(oemitted))
        feedback.append([f for f in steps[k].get("feedback") or () if (f.get("message") or {}).get("actor") == seat])
        rule_events.append(rebuilt["events"])
        withheld.append(rebuilt["withheld"])
    fidelity.update(decisions=len(samples), candidate_offline_differences=differ,
                    candidate_memory_chain_differences=memory_differ, candidate_unregistered_differences=unregistered,
                    opponent_offline_differences=opp_differ, opponent_memory_chain_differences=opp_memory_differ,
                    live_consistency_errors=len(compact.get("consistency_errors") or ()),
                    live_unregistered_differences=len(compact.get("unregistered_differences") or ()),
                    live_reconstructed_decisions=compact.get("reconstructed_decisions"))
    frames = [frame(k, raw, faction, baseline[k]) for k, raw in enumerate(raws)]
    opp_frames = [frame(k, raw, 1 - faction, opp_live[k]) for k, raw in enumerate(opp_raws)]
    collector = sc.EventCollector()
    for k, sample in enumerate(samples):
        collector.add(k, pickle.loads(sample["global"]).get("judge_info") or [])
    values = {c.get("coord"): c.get("value") for c in raws[0].get("cities") or () if isinstance(c, Mapping)}
    names = st.objective_labels(values)
    if sorted(names.values()) != sorted(sp.OBJECTIVES):
        stops.setdefault("S7", []).append("the game's objective labels are not the registered seven")
    label = f"S27 p{position:02d} candidate {side_name}"
    side = st.Side("S27", label, gid, entry["scenario_id"], faction, frames, live, collector.events, travel, values)
    run = st.run_shadow(side)
    frozen_equal = sum(1 for k in range(len(frames)) if rd.plain(list(run.candidate[k])) == live[k])
    shadow_events = [[] for _ in frames]
    for k, e in run.events:
        shadow_events[k].append([e.kind, e.eid, e.unit, e.step, e.index, e.reason, e.moved])
    events_equal = shadow_events == rule_events
    checker = st.IndependentCheck(travel)
    independent = []
    for k, f in enumerate(frames):
        if f.stage == 2:
            independent.extend(checker.step(f, live[k]))
    first = run.first_divergence
    prefix_ok = all(live[k] == baseline[k] for k in range(first if first is not None else len(frames)))
    fidelity.update(frozen_rule_equal_decisions=frozen_equal, frozen_rule_events_equal=events_equal,
                    independent_check_unexplained=len(independent),
                    candidate_equals_baseline_v2_before_the_first_withholding=prefix_ok)
    sf = sp.fidelity_problems(fidelity)
    if sf:
        stops.setdefault("SF", []).extend(sf)
    codes = sp.structural_stops(stops)
    completed = record.get("status") == "COMPLETED"
    # endpoints
    exposure = st.exposure(side)
    e4 = int(exposure.get("moving_stacked_inside_envelope", 0))
    p1 = sp.p1(e4, sp.RULES["p1"]["references"][side_name])
    first_steps = first_ownership_steps(frames, faction, names)
    p2 = sp.p2(first_steps, sp.RULES["p2"]["references"][side_name]) if sorted(first_steps) == sorted(sp.OBJECTIVES) \
        else {"rows": [], "triggered": True, "objectives_without_reference": [], "invalid": "objective labels"}
    all_four = {obj: {**sp.RULES["p2"]["references"]["blue"][obj], **sp.RULES["p2"]["references"]["red"][obj]}
                for obj in sp.OBJECTIVES}
    sensitivity = sp.p2_sensitivity(first_steps, all_four) if sorted(first_steps) == sorted(sp.OBJECTIVES) else None
    hits = st.damage_steps(side)
    lost = sc.lost_units(frames)
    episodes = [sp.episode_facts(frames, row, live, feedback, hits, lost, names, faction) for row in run.episodes]
    observed = sp.mechanism_observed(episodes)
    gate = sp.stage_gate(codes, completed, p1, p2, observed)
    game = sc.Game("S27", gid, entry["scenario_id"], {faction: frames, 1 - faction: opp_frames}, collector.events,
                   (faction,))
    damage = moving_damage(sc.event_rows(game, faction))
    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))
    same_colour = {label_: refs["sides"][label_] for label_ in sp.HH_LABELS[side_name]}
    followers = {u for row in run.episodes for u in row["chain"][1:]}
    follower_moving = sum(1 for f in frames if f.stage == 2 for u in followers if u in f.own and sc.moving(f.own[u]))
    inside = exposure.get("moving_stacked_inside_envelope", 0) + exposure.get("moving_alone_inside_envelope", 0)
    first_row = run.episodes[0] if run.episodes else None
    opening = {"first_withholding_decision": first, "first_withholding_step": None if first is None else frames[first].cur_step,
               "expected_step_from_sprint26": sp.RULES["expected_opening_divergence_steps"][side_name],
               "occurs_at_the_expected_step": first is not None and frames[first].cur_step
               == sp.RULES["expected_opening_divergence_steps"][side_name],
               "first_episode_group_size": None if first_row is None else len(first_row["chain"]),
               "first_episode_classes": None if first_row is None else episodes[0]["classes"]}
    completed_eps = [e for e in episodes if e["completed"]]
    descriptive = {
        "exposure": exposure, "moving_inside_envelope_unit_decisions": inside,
        "stacked_share_of_moving_inside_envelope": f"{e4}/{inside}" if inside else None,
        "e4_per_moving_unit_decision": round(e4 / exposure["moving_unit_decisions"], 4)
        if exposure.get("moving_unit_decisions") else None,
        "same_colour_reference_exposure": {k: v["exposure"] for k, v in same_colour.items()},
        "same_colour_reference_e4_per_moving_unit_decision": {
            k: round(v["exposure"].get("moving_stacked_inside_envelope", 0) / v["exposure"]["moving_unit_decisions"], 4)
            for k, v in same_colour.items()},
        "follower_moving_unit_decisions": follower_moving,
        "episodes": len(episodes), "episodes_completed": len(completed_eps), "episodes_executed": sum(e["executed"] for e in episodes),
        "completed_episode_duration_steps": dist([e["end_steps_after_start"] for e in completed_eps]),
        "moving_ground_damage": damage,
        "same_colour_reference_moving_ground_damage": {k: {x: v[x] for x in damage} for k, v in same_colour.items()},
        "followers_destroyed_before_departure": sum(f["destroyed_before_departure"] for e in episodes for f in e["followers"]),
        "follower_damage_events_while_waiting_on_the_start_hex": sum(
            f["damage_events_while_waiting_on_the_start_hex"] for e in episodes for f in e["followers"]),
        "evidence_boundary": "one game of one scenario against one opponent policy; the references are historical "
                             "seat-games against a different opponent; nothing here is a damage, survival or score "
                             "effect of the rule"}
    scores = record.get("final_scores") or {}
    public = {"schema": sp.SCHEMA + "/game", "study_id": sp.STUDY_ID, "game_id": gid, "position": position,
              "stage": next(k for k, v in sp.STAGES.items() if v == position), "candidate_side": side_name,
              "session": int(record["session"]) if str(record.get("session", "")).isdigit() else None,
              "status": record.get("status"), "steps": record.get("steps"),
              "structural_stops": codes, "structural_stop_counts": {c: len(stops[c]) for c in codes},
              "ledger_sessions_after_base": audit["sessions"], "fidelity": fidelity, "opening": opening,
              "p1": p1, "p2": p2, "p2_sensitivity_four_games": sensitivity,
              "mechanism_observed": observed, "episodes": [public_episode(e, i) for i, e in enumerate(episodes, 1)],
              "descriptive": descriptive, "stage_gate": gate,
              "record_facts_not_used": {"scores": {k: scores.get(k) for k in sorted(scores)}}}
    private_values = set()
    for f in frames + opp_frames:
        for u in list(f.own.values()) + list(f.enemies.values()) + list(f.aboard.values()):
            if sc.as_int(u.get("cur_hex")) is not None:
                private_values.add(u["cur_hex"])
            private_values.update(h for h in u.get("move_path") or () if sc.as_int(h) is not None)
            private_values.add(u["obj_id"])
        private_values.update(c for c in f.flags if sc.as_int(c) is not None)
    for row in run.episodes:
        for m in row["members"].values():
            private_values.update(m.route)
    private = {"stops": stops, "episodes": [{**e, "private": e["private"]} for e in episodes],
               "rows": [{k: v for k, v in r.items() if k != "members"} | {"routes": {str(u): list(m.route)
                                                                                    for u, m in r["members"].items()}}
                        for r in run.episodes],
               "independent": independent[:50], "first_ownership_steps": first_steps}
    return public, private, private_values


def run_game(position: int, check: bool) -> int:
    public, private, values = analyse_game(position)
    problems = sp.public_problems(public, values)
    if problems:
        print(f"REFUSED: the public game file fails the privacy check: {problems[:5]}", file=sys.stderr)
        return 1
    ok = write_or_check(PUBLIC / f"game-p{position:02d}.json", sp.dump(public), check)
    ok = write_private(PRIVATE / f"game-p{position:02d}-private.json.gz", private, check) and ok
    print(f"structural stops {public['structural_stops']}, P1 triggered {public['p1']['triggered']}, P2 triggered "
          f"{public['p2']['triggered']}, mechanism observed {public['mechanism_observed']}, stage B authorized "
          f"{public['stage_gate']['stage_b_authorized']}")
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------
# disposition


def disposition() -> Dict[str, Any]:
    card, _ = card_and_entry(1)
    ledger = read_ledger(sp.EXPECTED_SESSIONS[-1])
    audit = sp.ledger_audit(ledger, card)
    sessions = []
    stage_b_authorized = False
    for position in (1, 2):
        _, entry = card_and_entry(position)
        if entry["game_id"] not in audit["games"]:
            continue
        public, _, _ = analyse_game(position)
        if position == 1:
            stage_b_authorized = public["stage_gate"]["stage_b_authorized"]
        sessions.append({"position": position, "session": public["session"], "candidate_side": public["candidate_side"],
                         "structural_stops": public["structural_stops"], "completed": public["status"] == "COMPLETED",
                         "mechanism_observed": public["mechanism_observed"], "p1_triggered": public["p1"]["triggered"],
                         "p2_triggered": public["p2"]["triggered"],
                         "game_file_sha256": sha256(PUBLIC / f"game-p{position:02d}.json")})
    _, second = card_and_entry(2)
    verdict = sp.disposition(sessions, stage_b_authorized, second["game_id"] in audit["games"])
    return {"schema": sp.SCHEMA + "/disposition", "study_id": sp.STUDY_ID, **verdict, "sessions": sessions,
            "stage_b_authorized": stage_b_authorized, "ledger_sessions_after_base": audit["sessions"],
            "ledger_problems": {k: v for k, v in audit["problems"].items() if v},
            "meaning": "MECHANISM_SUPPORTED would mean only that the registered stagger executed and passed the P1 and "
                       "P2 checks in both seat orders of this one scenario; it is not a score improvement, a damage "
                       "or survival effect of the rule, a confirmation or readiness for promotion"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("references", "rehearse", "inputs", "disposition"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    g = sub.add_parser("game")
    g.add_argument("--position", type=int, required=True, choices=(1, 2))
    g.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.command == "game":
        return run_game(args.position, args.check)
    if args.command == "references":
        data, values = references()
        problems = sp.public_problems(data, values)
        if problems or not data["ok"]:
            print(f"REFUSED: references fail ({problems[:5]}, anchors {data['anchors']})", file=sys.stderr)
            return 1
        return 0 if write_or_check(REFERENCES, sp.dump(data), args.check) else 1
    if args.command == "rehearse":
        data = rehearse()
        problems = sp.public_problems(data, (), data["scenarios"])
        if problems:
            print(f"REFUSED: the rehearsal file fails the privacy check: {problems[:5]}", file=sys.stderr)
            return 1
        print(f"rehearsal {'PASS' if data['ok'] else 'FAIL'}: {data['totals']}")
        ok = write_or_check(REHEARSAL, sp.dump(data), args.check)
        return 0 if ok and data["ok"] else 1
    if args.command == "inputs":
        data = inputs()
        problems = sp.public_problems(data, ())
        if problems:
            print(f"REFUSED: the inputs file fails the privacy check: {problems[:5]}", file=sys.stderr)
            return 1
        return 0 if write_or_check(INPUTS, sp.dump(data), args.check) else 1
    data = disposition()
    problems = sp.public_problems(data, ())
    if problems:
        print(f"REFUSED: the disposition file fails the privacy check: {problems[:5]}", file=sys.stderr)
        return 1
    print(f"disposition {data['disposition']}")
    return 0 if write_or_check(DISPOSITION, sp.dump(data), args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
