"""Sprint 26 T6-S stacked-column stagger offline shadow (``docs/SPRINT26_T6S_SHADOW.md``). Offline only.

    python scripts/s26_t6s.py freeze [--check]
    python scripts/s26_t6s.py smoke
    python scripts/s26_t6s.py run [--check]

``freeze`` writes ``evaluation/s26-t6s-shadow/protocol.json`` (the frozen definitions, parameters, thresholds,
disposition order and the normalised SHA-256 of every frozen source) and ``inputs.json`` (Sprint 18's H0 and HH pins,
copied from Sprint 18's committed ``inputs.json``, itself pinned with ``census.json`` and ``admission.json``; Sprint
19's disposition; Sprint 25's private loss rows, read only for the descriptive intersection of section 16).

``smoke`` is the pre-registration known-answer run on the real inputs; it prints no co-departure, trigger, episode or
stagger figure: with the minimum group size set so that no group can form, the shadow must withhold nothing, the
candidate must equal ``baseline-v2`` at every decision, every integrity check must hold and every fidelity anchor
must be reproduced.

``run`` refuses unless every input and frozen source matches its pin. It loads H0 and HH with Sprint 18's census loader
(``scripts/s18_census.py``, unchanged; H0's recorded ``baseline-v0`` actions are read in a separate pass and aligned by
decision), reproduces the registered fidelity anchors (any difference: ``T6_S_INVALID``), applies the frozen shadow
(``experiments/t6s_stagger_shadow.py``) and analysis (``evaluation/s26_t6s.py``) and writes the public aggregates and the
private rows (``local/diagnostics/s26/study-private.json.gz``). ``--check`` rebuilds and compares instead of writing. It
runs on the evaluation server, where the private inputs are.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import sys
import time
import types
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT = REPO_ROOT / "evaluation" / "s26-t6s-shadow"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
S18 = REPO_ROOT / "evaluation" / "s18-frontier-reset"
S19 = REPO_ROOT / "evaluation" / "s19-t6g-shadow"
S25_PRIVATE = "local/diagnostics/s25/study-private.json.gz"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s26"
SCHEMA_PROTOCOL = "miaosuan-s26-protocol/1"
SCHEMA_INPUTS = "miaosuan-s26-inputs/1"
SCHEMA_RESULTS = "miaosuan-s26-results/1"
#: Frozen source files (normalised SHA-256: carriage returns before line feeds removed).
SOURCES = ("src/miaosuan_agent/experiments/t6s_stagger_shadow.py",
           "src/miaosuan_agent/evaluation/s26_t6s.py",
           "scripts/s26_t6s.py",
           "src/miaosuan_agent/evaluation/s18_census.py",
           "scripts/s18_census.py",
           "src/miaosuan_agent/evaluation/t7_candidates.py",
           "src/miaosuan_agent/evaluation/t7_visibility.py",
           "src/miaosuan_agent/experiments/t9_batch.py",
           "src/miaosuan_agent/decision/routing.py",
           "src/miaosuan_agent/experiments/t6_threat_entry_gate.py",
           "src/miaosuan_agent/evaluation/s19_t6g.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s12_screen.py")
#: Sprint 18 and Sprint 24 figures the replay must reproduce exactly (section 11): name -> (block, population, key, value).
T6_ANCHORS = {
    "H0 baseline-v2 move orders": ("H0", "move_orders", 509),
    "HH baseline-v2 move orders": ("HH", "move_orders", 416),
    "H0 threat-exposed move orders": ("H0", "threat_exposed_orders", 230),
    "HH threat-exposed move orders": ("HH", "threat_exposed_orders", 200),
    "H0 threat-exposed orders followed by mover damage within the lookback window": ("H0", "threat_exposed_then_damaged", 88),
    "HH threat-exposed orders followed by mover damage within the lookback window": ("HH", "threat_exposed_then_damaged", 101),
    "H0 damage events on moving ground units": ("H0", "moving_ground_events", 124),
    "HH damage events on moving ground units": ("HH", "moving_ground_events", 117),
    "H0 moving ground events, attacker seen before": ("H0", "moving_ground_seen_before", 120),
    "HH moving ground events, attacker seen before": ("HH", "moving_ground_seen_before", 117),
}
N9_ANCHORS = {"H0": (177, 112), "HH": (130, 70)}
EVENT_TOTALS = {"H0": 205, "HH": 158}
MOVING_STACKED_OFF_OBJECTIVES = {"H0": 57, "HH": 40}
H0_SIDES_STACKED_DAMAGED = 13
S19_GATE_EPISODES = [0, 0, 0, 0]
INTEGRITY = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123}
HH_EQUAL = 11524
SIDE_GAMES = {"H0": 16, "HH": 4}
S25_MULTI_DEFENDER_V_ORDER = 28
#: Largest public file (bytes); larger episode tables are split in order into numbered parts.
PUBLIC_LIMIT = 90_000


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def normalised(path: Path) -> str:
    return sha256_bytes(path.read_bytes().replace(b"\r\n", b"\n"))


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def census_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("s18_census_script", REPO_ROOT / "scripts" / "s18_census.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admission_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("s18_admission_script", REPO_ROOT / "scripts" / "s18_admission.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------
# freeze

def protocol() -> Dict[str, Any]:
    from miaosuan_agent.experiments import t6s_stagger_shadow as ts
    from miaosuan_agent.evaluation import s26_t6s as st
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": st.STUDY_ID, "engine_sessions": 0,
        "own_ground_unit": "own operator of the infantry or vehicle type (artillery included) with a readable hex; passengers are not "
                           "operators",
        "shadow": {"identity": ts.SHADOW_ID, "status": ts.STATUS, "executable": ts.EXECUTABLE,
                   "mover_checks_in_order": list(ts.MOVER_REASONS), "group_outcomes": list(ts.GROUP_REASONS),
                   "minimum_group": ts.MIN_GROUP, "route_prefix_hexes": ts.ROUTE_PREFIX,
                   "threat": "Sprint 18's threat-exposed order predicate: a visible enemy operator of any class with a "
                             "published direct-fire range against the mover's type covers the mover's hex or one of "
                             "the first route_prefix_hexes route hexes (distance at most the range)",
                   "group_trigger": "eligible movers grouped by current hex and route first hex; a group of at least "
                                    "minimum_group movers with at least one threat-exposed member starts an episode",
                   "chain_order": "free-flow arrival, route cost, route length, unit id (experiments/t9_batch.path_times, "
                                  "the unit's type and move_state, basic_speed, the setup cost graph)",
                   "release": "the next pending member is released when the reference unit (initially the leader) is "
                              "absent or observed on a readable hex other than the shared start hex; a released member "
                              "with a baseline-v2 MOVE becomes the reference",
                   "wait_bound": "every pending member is released when the reference has not left and cur_step - "
                                 "reference release step > stall_factor * reference hex time + stall_slack (the PS-1 "
                                 "stall definition)",
                   "stall_factor": ts.STALL_FACTOR, "stall_slack_steps": ts.STALL_SLACK,
                   "one_episode_per_unit": "a member of an active episode cannot join another; after completion each "
                                           "member is spent at the shared start hex until observed on another hex",
                   "release_reasons": list(ts.RELEASE_REASONS), "queue_reasons": list(ts.QUEUE_REASONS),
                   "open_at_end": ts.OPEN_AT_END},
        "follow_up_window_steps": st.FOLLOW_UP, "damage_windows_steps": list(st.WINDOWS),
        "stops": {"A": {"rule": "met when any registered HH side-game has fewer episodes than the minimum (episodes "
                                "counted over every recorded decision, under the frozen state machine), or when the "
                                "HH side-games are not all present",
                        "minimum_episodes_per_hh_side_game": st.STOP_A_MIN_EPISODES,
                        "hh_side_games": st.HH_SIDE_GAMES},
                  "B": {"rule": "met when fewer distinct H0 scenario-sides than the minimum have an episode",
                        "minimum_h0_scenario_sides": st.STOP_B_MIN_SCENARIO_SIDES},
                  "C": {"rule": "over the H0 and HH episodes, replicas de-duplicated (an identical episode counts once, "
                                "and is at risk if at risk in any replica): met when there is no episode, or when twice "
                                "the first-owner-risk episodes exceed the episodes (strictly more than one half)"}},
        "first_owner_risk": "an episode is at risk when at least one withheld follower stands on its ordered "
                            "destination objective at the side's first-ever play-stage ownership of it, after the "
                            "episode start",
        "dispositions_first_match": list(st.DISPOSITIONS),
        "s25_categories_first_match": list(st.S25_CATEGORIES),
        "anchors": {**INTEGRITY, "HH baseline-v2 reconstruction equal": HH_EQUAL,
                    **{k: v[2] for k, v in T6_ANCHORS.items()},
                    **{f"{p} ground damage events": v[0] for p, v in N9_ANCHORS.items()},
                    **{f"{p} ground damage events on a stacked victim": v[1] for p, v in N9_ANCHORS.items()},
                    **{f"{p} damage events": v for p, v in EVENT_TOTALS.items()},
                    **{f"{p} ground events on stacked units moving off objectives": v
                       for p, v in MOVING_STACKED_OFF_OBJECTIVES.items()},
                    "H0 scenario-sides with a stacked ground victim": H0_SIDES_STACKED_DAMAGED,
                    "HH gate episodes of the frozen T6-G gate": S19_GATE_EPISODES,
                    **{f"{p} side-games": v for p, v in SIDE_GAMES.items()}},
        "s25_intersection": {"multi_defender_order_vacating_losses": S25_MULTI_DEFENDER_V_ORDER,
                             "scope": "descriptive only; a mismatch voids the intersection, not the study"},
        "public_file_limit_bytes": PUBLIC_LIMIT,
        "sources": {p: normalised(REPO_ROOT / p) for p in SOURCES},
    }


def inputs() -> Dict[str, Any]:
    s18_inputs = json.loads((S18 / "inputs.json").read_text(encoding="utf-8"))
    for entry in s18_inputs["H0"]["games"]:
        if sha256(REPO_ROOT / entry["path"]) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its Sprint 18 pin")
    for entry in s18_inputs["HH"]["games"]:
        for kind in ("record", "timeline", "timeline_index"):
            if sha256(REPO_ROOT / entry[kind]["path"]) != entry[kind]["sha256"]:
                raise SystemExit(f"{entry[kind]['path']} does not match its Sprint 18 pin")
    return {"schema": SCHEMA_INPUTS, "study_id": "s26-t6s-shadow",
            "sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json", "sha256": sha256(S18 / "inputs.json")},
            "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json", "sha256": sha256(S18 / "census.json")},
            "sprint18_admission": {"path": "evaluation/s18-frontier-reset/admission.json",
                                   "sha256": sha256(S18 / "admission.json")},
            "sprint19_disposition": {"path": "evaluation/s19-t6g-shadow/disposition.json",
                                     "sha256": sha256(S19 / "disposition.json")},
            "sprint25_private_rows": {"path": S25_PRIVATE, "sha256": sha256(REPO_ROOT / S25_PRIVATE),
                                      "use": "descriptive intersection of section 16 only"},
            "H0": s18_inputs["H0"], "HH": s18_inputs["HH"],
            "not_used": "HI, S and R of Sprint 18, every other capture, BOKE-2026 data, the stopped 360-game "
                        "prevalence corpus and any new game"}


def input_problems(committed: Mapping[str, Any], proto: Mapping[str, Any]) -> List[str]:
    problems = []
    for key in ("sprint18_inputs", "sprint18_census", "sprint18_admission", "sprint19_disposition",
                "sprint25_private_rows"):
        if sha256(REPO_ROOT / committed[key]["path"]) != committed[key]["sha256"]:
            problems.append(committed[key]["path"])
    for entry in committed["H0"]["games"]:
        if sha256(REPO_ROOT / entry["path"]) != entry["sha256"]:
            problems.append(entry["path"])
    for entry in committed["HH"]["games"]:
        for kind in ("record", "timeline", "timeline_index"):
            if sha256(REPO_ROOT / entry[kind]["path"]) != entry[kind]["sha256"]:
                problems.append(entry[kind]["path"])
    for path, digest in proto["sources"].items():
        if normalised(REPO_ROOT / path) != digest:
            problems.append(path)
    return problems


# ------------------------------------------------------------------------------------------------
# loading: Sprint 18's census, unchanged, with each analysed side handed to the Sprint 26 analysis

def recorded_h0(committed: Mapping[str, Any]) -> Dict[Tuple[str, int], List[List[Mapping[str, Any]]]]:
    """H0's recorded ``baseline-v0`` actions per (game, faction), one list per decision in step order (the order of
    Sprint 18's frames)."""
    out: Dict[Tuple[str, int], List[List[Mapping[str, Any]]]] = {}
    for entry in committed["H0"]["games"]:
        by_step: Dict[int, Dict[int, List[Mapping[str, Any]]]] = collections.defaultdict(dict)
        with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            for line in handle:
                row = json.loads(line)
                if row["step"] in by_step[row["faction"]]:
                    raise SystemExit(f"{header['game_id']}: two rows for one seat and step")
                by_step[row["faction"]][row["step"]] = [dict(a) for a in row["actions"]]
        for faction, steps in by_step.items():
            out[(header["game_id"], faction)] = [steps[s] for s in sorted(steps)]
    return out


def side_label(population: str, game: Any, faction: int) -> str:
    colour = "red" if faction == 0 else "blue"
    if population == "HH":
        return f"HH {game.game.rsplit('.', 1)[-1]} baseline-v2 {colour}"
    return f"H0 {game.scenario} {colour}"


def make_loader(committed: Mapping[str, Any]) -> Any:
    from miaosuan_agent.evaluation import s18_census as sc
    from miaosuan_agent.evaluation import s19_t6g as s19
    from miaosuan_agent.evaluation import s26_t6s as st
    from miaosuan_agent.experiments import t6s_stagger_shadow as ts
    base = census_script().Census

    class Loader(base):
        """Sprint 18's census, unchanged, with each analysed side also passed to the Sprint 26 analysis."""

        def __init__(self) -> None:
            super().__init__()
            self.pending: Dict[Any, Any] = {}
            self.values: Dict[str, Dict[Any, Any]] = {}
            self.analyses: Dict[str, List[Any]] = {"H0": [], "HH": []}
            self.gate_episodes: List[int] = []
            self.recorded = recorded_h0(committed)
            self.recorded_differs = 0
            proxy = types.SimpleNamespace(**{k: getattr(sc, k) for k in dir(sc) if not k.startswith("__")})

            def frame_from_raw(k, raw, faction, actions=(), concealment=()):
                for c in raw.get("cities") or ():
                    if isinstance(c, Mapping):
                        self.pending[c.get("coord")] = c.get("value")
                frame = sc.frame_from_raw(k, raw, faction, actions, concealment)
                frame.carrying = {u.get("obj_id"): len(u.get("passenger_ids") or ())
                                  for u in raw.get("operators") or ()
                                  if isinstance(u, Mapping) and u.get("color") == faction and u.get("passenger_ids")}
                return frame

            proxy.frame_from_raw = frame_from_raw
            self.sc = proxy

        def side(self, population, game, faction, router, analyse_threat):
            out = super().side(population, game, faction, router, analyse_threat)
            if self.pending:
                self.values[game.game] = self.pending
                self.pending = {}
            if population in self.analyses:
                frames = game.sides[faction]
                if population == "H0":
                    recorded = self.recorded[(game.game, faction)]
                    if len(recorded) != len(frames):
                        raise SystemExit(f"{game.game}: recorded actions do not align with the frames")
                    self.recorded_differs += sum(1 for f, r in zip(frames, recorded)
                                                 if [dict(a) for a in f.actions] != r)
                else:
                    recorded = [[dict(a) for a in f.actions] for f in frames]
                    self.gate_episodes.append(len(s19.shadow_side(frames).episodes))
                side = st.Side(population, side_label(population, game, faction), game.game, game.scenario, faction,
                               frames, recorded, game.events, ts.router_travel(router), self.values.get(game.game, {}))
                self.analyses[population].append(st.analyse_side(side))
            return out

    return Loader()


def load(committed: Mapping[str, Any]) -> Any:
    loader = make_loader(committed)
    loader.h0(committed)
    for entry in committed["HH"]["games"]:
        loader.timeline_game("HH", entry)
    return loader


# ------------------------------------------------------------------------------------------------
# fidelity (section 11)

def fidelity(loader: Any) -> Dict[str, Any]:
    census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))
    admission = json.loads((S18 / "admission.json").read_text(encoding="utf-8"))
    script = census_script()
    families = script.summarise_lists(loader.families)
    scan = script.summarise_lists(loader.scan)
    anchors: Dict[str, Dict[str, Any]] = {}

    def put(name: str, published: Any, replay: Any, also: bool = True) -> None:
        anchors[name] = {"published": published, "replay": replay, "equal": replay == published and also}

    for name, value in INTEGRITY.items():
        put(name, value, loader.integrity.get(name))
    put("H0 recorded actions differ from reconstructed baseline-v2 (separate pass)",
        INTEGRITY["H0 v2 differs from recorded v0"], loader.recorded_differs)
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    put("HH baseline-v2 reconstruction equal to the recorded seat", HH_EQUAL, hh[0], hh[0] == hh[1])
    for name, (pop, key, value) in T6_ANCHORS.items():
        put(name, value, families.get("T6", {}).get(pop, {}).get(key), census["families"]["T6"][pop][key] == value)
    for pop, (ground, stacked) in N9_ANCHORS.items():
        n9 = scan.get("N9", {}).get(pop, {})
        put(f"{pop} ground damage events", ground, n9.get("ground_events"))
        put(f"{pop} ground damage events on a stacked victim", stacked, n9.get("ground_events_victim_stacked"))
    for pop, value in EVENT_TOTALS.items():
        put(f"{pop} damage events", value, sum(families.get("T6", {}).get(pop, {}).get("events_by_victim_state", {}).values()))
    tables = admission_script().tables(loader.private["events"], loader.private["sides"])
    for pop, value in MOVING_STACKED_OFF_OBJECTIVES.items():
        put(f"{pop} ground events on stacked units moving off objectives", value,
            tables[pop]["ground_events_by_state"].get("moving, off objectives, stacked"),
            admission["tables"][pop]["ground_events_by_state"]["moving, off objectives, stacked"] == value)
    stacked_sides = sum(1 for flags in loader.sides if flags.get("scan stacked ground unit damaged"))
    put("H0 scenario-sides with a stacked ground victim", H0_SIDES_STACKED_DAMAGED, stacked_sides,
        census["opportunity_sides"]["sides_with_opportunity"]["scan stacked ground unit damaged"] == H0_SIDES_STACKED_DAMAGED)
    s19 = json.loads((S19 / "disposition.json").read_text(encoding="utf-8"))
    put("HH gate episodes of the frozen T6-G gate", S19_GATE_EPISODES, loader.gate_episodes,
        s19.get("hh_gate_episodes") == S19_GATE_EPISODES)
    for pop, value in SIDE_GAMES.items():
        put(f"{pop} side-games", value, len(loader.analyses[pop]))
    blocks = {f"{item} {pop} block equal to census.json": (families if item == "T6" else scan).get(item, {}).get(pop)
              == (census["families"] if item == "T6" else census["scan"])[item][pop]
              for item in ("T6", "N9", "N6") for pop in ("H0", "HH")}
    blocks.update({f"admission {pop} ground events by state equal to admission.json":
                   tables[pop]["ground_events_by_state"] == admission["tables"][pop]["ground_events_by_state"]
                   for pop in ("H0", "HH")})
    integrity = {a.side.label: all(a.integrity.values()) for pop in ("H0", "HH") for a in loader.analyses[pop]}
    ok = all(a["equal"] for a in anchors.values()) and all(blocks.values()) and all(integrity.values())
    return {"anchors": anchors, "blocks": blocks, "side_integrity": integrity, "ok": ok}


def moving_damage(loader: Any) -> Dict[str, Dict[str, int]]:
    """Section 13: damage events on moving own ground units (not on board), stacked victims against alone, from Sprint
    18's admission cross-tabulation recomputed on the census rows (on and off objectives together)."""
    tables = admission_script().tables(loader.private["events"], loader.private["sides"])
    out: Dict[str, Dict[str, int]] = {}
    for pop in ("H0", "HH"):
        rows = tables[pop]["ground_events_by_state"]
        out[pop] = {"stacked": sum(v for k, v in rows.items() if k.startswith("moving") and k.endswith("stacked")),
                    "alone": sum(v for k, v in rows.items() if k.startswith("moving") and k.endswith("alone"))}
    return out


# ------------------------------------------------------------------------------------------------
# section 16: Sprint 25's collective departures

def s25_intersection(loader: Any, committed: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    from miaosuan_agent.evaluation import s26_t6s as st
    rows = json.loads(gzip.decompress((REPO_ROOT / committed["sprint25_private_rows"]["path"]).read_bytes()))
    by_label = {a.side.label: a for pop in ("H0", "HH") for a in loader.analyses[pop]}
    cases, private = [], []
    for side in rows:
        a = by_label[side["label"]]
        for loss in side["losses"]:
            if loss["v_class"] != "V_ORDER" or len(loss["defenders"]) < 2:
                continue
            orders = {int(k): v for k, v in loss["orders"].items()}
            category, facts = st.s25_category(a, loss["defenders"], orders)
            cases.append({"population": a.side.population, "category": category,
                          "last_defenders": len(loss["defenders"]), **facts})
            private.append({"label": a.side.label, "coord": loss["coord"], "loss_k": loss["loss_k"],
                            "category": category, **facts})
    out = {"cases": len(cases), "anchor_equal": len(cases) == S25_MULTI_DEFENDER_V_ORDER,
           "last_defender_instances": sum(c["last_defenders"] for c in cases),
           "ordered_at_one_decision": sum(1 for c in cases if c["order_decisions"] == 1),
           "note": "descriptive only; not part of any stop. Sprint 25's order decisions are the recorded stream's "
                   "(H0: baseline-v0); the frozen trigger is evaluated on baseline-v2's list at that decision."}
    for name, part in (("H0", [c for c in cases if c["population"] == "H0"]),
                       ("HH", [c for c in cases if c["population"] == "HH"]), ("pooled", cases)):
        out[name] = {c: sum(1 for x in part if x["category"] == c) for c in st.S25_CATEGORIES}
        out[name]["cases"] = len(part)
    return out, private


# ------------------------------------------------------------------------------------------------
# smoke (pre-registration known-answer run; prints no co-departure, trigger, episode or stagger figure)

def smoke(committed: Mapping[str, Any]) -> int:
    from miaosuan_agent.experiments import t6s_stagger_shadow as ts
    started = time.time()
    ts.MIN_GROUP = 10 ** 6
    loader = load(committed)
    fid = fidelity(loader)
    print("fidelity ok" if fid["ok"] else "FIDELITY FAILS",
          {k: v["replay"] for k, v in fid["anchors"].items() if not v["equal"]},
          [k for k, v in fid["blocks"].items() if not v], [k for k, v in fid["side_integrity"].items() if not v])
    for pop in ("H0", "HH"):
        analyses = loader.analyses[pop]
        withheld = sum(len(a.shadow.withheld) for a in analyses)
        unchanged = all(list(a.shadow.candidate[i]) == [dict(x) for x in f.actions]
                        for a in analyses for i, f in enumerate(a.side.frames))
        unexplained = sum(len(a.shadow.unexplained) for a in analyses)
        print(f"{pop}: side-games {len(analyses)}, never-firing shadow: withheld decisions {withheld}, candidate equal "
              f"to baseline-v2 at every decision {unchanged}, unexplained differences {unexplained}")
    print(f"seconds {time.time() - started:.0f}")
    return 0


# ------------------------------------------------------------------------------------------------
# run

def split_rows(name: str, head: Mapping[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """One file, or numbered parts in order when one would exceed the public size limit."""
    whole = {**head, "rows": rows, "part": "1/1"}
    if len(dump(whole).encode("utf-8")) <= PUBLIC_LIMIT:
        return {f"{name}.json": whole}
    parts: List[List[Dict[str, Any]]] = [[]]
    for row in rows:
        trial = {**head, "rows": parts[-1] + [row], "part": "99/99"}
        if parts[-1] and len(dump(trial).encode("utf-8")) > PUBLIC_LIMIT:
            parts.append([])
        parts[-1].append(row)
    return {f"{name}-{i}.json": {**head, "rows": part, "part": f"{i}/{len(parts)}"}
            for i, part in enumerate(parts, start=1)}


def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s26_t6s as st
    loader = load(committed)
    fid = fidelity(loader)
    head = {"schema": SCHEMA_RESULTS, "study_id": st.STUDY_ID,
            "protocol_sha256": sha256(PROTOCOL), "inputs_sha256": sha256(INPUTS)}
    analyses = loader.analyses["H0"] + loader.analyses["HH"]
    integrity_ok = all(all(a.integrity.values()) for a in analyses)
    unexplained = sum(len(a.shadow.unexplained) for a in analyses)
    stop = st.stops(analyses)
    verdict = st.disposition(fid["ok"], integrity_ok, unexplained, stop)
    evidence = ("H0: baseline-v0 trajectories, baseline-v2 reconstructed on them (descriptive unless the recorded "
                "prefix equals baseline-v2); HH: genuine baseline-v2 seats, four games of one scenario, two openings. "
                "Before a side's first divergence the candidate equals baseline-v2; episodes after it are replays on "
                "off-policy recorded states, counted as historical opportunity only.")
    public: Dict[str, Any] = {"fidelity.json": {**head, **fid}}
    public["census.json"] = {**head, "evidence_boundary": evidence,
                             "sides": [st.side_summary(a) for a in analyses],
                             "H0": st.pooled(loader.analyses["H0"]), "HH": st.pooled(loader.analyses["HH"]),
                             "pooled": st.pooled(analyses),
                             "moving_ground_damage_events": moving_damage(loader)}
    public["divergence.json"] = {**head, "evidence_boundary": evidence,
                                 "certificates": [c for c in (st.certificate(a) for a in analyses) if c is not None],
                                 "side_games_without_divergence": [a.side.label for a in analyses
                                                                   if a.shadow.first_divergence is None]}
    distinct = st.distinct_episodes(analyses)
    first_of = {id(occ[0][1]): key for key, occ in distinct.items()}
    risk_of = {key: any(r["first_owner_risk"] for _, r in occ) for key, occ in distinct.items()}
    key_of = {id(r): key for key, occ in distinct.items() for _, r in occ}
    for pop in ("H0", "HH"):
        rows = [st.public_episode(a, r, i, id(r) in first_of, risk_of[key_of[id(r)]])
                for a in loader.analyses[pop] for i, r in enumerate(a.shadow.episodes, start=1)]
        public.update(split_rows(f"episodes-{pop}", {**head, "population": pop}, rows))
    intersection, s25_private = s25_intersection(loader, committed)
    public["intersection.json"] = {**head, **intersection}
    public["disposition.json"] = {**head, **verdict, "stops": stop}
    private_values = loader.hexes | loader.ids
    scenarios = {a.side.scenario for a in analyses}
    for name, data in public.items():
        problems = st.public_problems(data, private_values)
        problems += [f"digit word {w!r}" for w in st.digit_words(data, scenarios)]
        if problems:
            raise SystemExit(f"privacy problems in {name}: {problems[:10]}")
    texts = {name: dump(data) for name, data in public.items()}
    for name, text in texts.items():
        if len(text.encode("utf-8")) > PUBLIC_LIMIT:
            raise SystemExit(f"{name} exceeds the public size limit")

    def episode_private(r: Mapping[str, Any]) -> Dict[str, Any]:
        return {**{k: v for k, v in r.items() if k != "members"},
                "members": {str(u): dataclasses.asdict(m) for u, m in r["members"].items()}}

    private = {"sides": [{"population": a.side.population, "label": a.side.label,
                          "episodes": [episode_private(r) for r in a.shadow.episodes],
                          "withheld": {str(k): list(v) for k, v in a.shadow.withheld.items()},
                          "unexplained": a.shadow.unexplained, "integrity": a.integrity} for a in analyses],
               "s25_intersection": s25_private}
    blob = gzip.compress(json.dumps(private, sort_keys=True, default=str).encode("utf-8"), mtime=0)
    return texts, blob


def run(check: bool) -> int:
    proto = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed, proto)
    if problems:
        print("inputs or frozen sources differ from their pins; refusing to run:", problems[:5])
        return 1
    texts, blob = build(committed)
    if check:
        same = all((OUT / name).exists() and (OUT / name).read_text(encoding="utf-8") == text
                   for name, text in texts.items())
        stale = sorted(p.name for p in OUT.glob("episodes-*.json") if p.name not in texts)
        same &= not stale
        same &= (PRIVATE / "study-private.json.gz").exists() and (PRIVATE / "study-private.json.gz").read_bytes() == blob
        print("study identical" if same else f"MISMATCH {stale}")
        return 0 if same else 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "study-private.json.gz").write_bytes(blob)
    print("wrote", ", ".join(sorted(texts)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "run"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    sub.add_parser("smoke")
    args = parser.parse_args()
    if args.command == "freeze":
        texts = {PROTOCOL: dump(protocol()), INPUTS: dump(inputs())}
        if args.check:
            same = all(p.exists() and p.read_text(encoding="utf-8") == t for p, t in texts.items())
            print("protocol and inputs identical" if same else "MISMATCH")
            return 0 if same else 1
        OUT.mkdir(parents=True, exist_ok=True)
        for p, t in texts.items():
            p.write_text(t, encoding="utf-8", newline="\n")
        print("wrote", ", ".join(p.name for p in texts))
        return 0
    if args.command == "smoke":
        return smoke(inputs())
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
