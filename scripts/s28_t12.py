"""Sprint 28 T12-O1 objective-zone dispersion offline qualification (``docs/SPRINT28_T12_O1.md``). Offline only.

    python scripts/s28_t12.py freeze [--check]
    python scripts/s28_t12.py smoke
    python scripts/s28_t12.py run [--check]

``freeze`` writes ``evaluation/s28-t12-o1/protocol.json`` (the frozen definitions, parameters, thresholds, disposition
order and the normalised SHA-256 of every frozen source) and ``inputs.json`` (Sprint 18's H0 and HH pins, copied from
Sprint 18's committed ``inputs.json``, itself pinned with ``census.json`` and ``admission.json``, and Sprint 24's frozen
experiment definitions).

``smoke`` is the pre-registration known-answer run on the real inputs; it prints no idle, trigger, legality, episode
or dispersion figure: with the minimum number of idle units set so that no trigger can hold, the shadow must add and
withhold nothing, the candidate must equal ``baseline-v2`` at every decision, every integrity check must hold and
every fidelity anchor must be reproduced; the public files are then assembled and sanitised (only their names are
printed, and nothing is written).

``run`` refuses unless every input and frozen source matches its pin. It loads H0 and HH with Sprint 18's census loader
(``scripts/s18_census.py``, unchanged; H0's recorded ``baseline-v0`` actions are read in a separate pass and aligned by
decision; the raw transition fields of the own ground operators and the roadblock hexes are captured through the
loader's frame hook), reproduces the registered fidelity anchors (any difference: ``T12_O1_OFFLINE_INVALID``), applies
the frozen shadow (``experiments/t12_dispersion_shadow.py``) and analysis (``evaluation/s28_t12.py``) and writes the
public aggregates and the private rows (``local/diagnostics/s28/study-private.json.gz``). If the public sanitizer
refuses a result file, only ``disposition.json`` is written, with ``T12_O1_OFFLINE_INVALID``. ``--check`` rebuilds and
compares instead of writing. It runs on the evaluation server, where the private inputs are.
"""

from __future__ import annotations

import argparse
import collections
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

OUT = REPO_ROOT / "evaluation" / "s28-t12-o1"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
S18 = REPO_ROOT / "evaluation" / "s18-frontier-reset"
S24 = REPO_ROOT / "evaluation" / "s24-tactical-frontier-reselection"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s28"
SCHEMA_PROTOCOL = "miaosuan-s28-protocol/1"
SCHEMA_INPUTS = "miaosuan-s28-inputs/1"
SCHEMA_RESULTS = "miaosuan-s28-results/1"
#: Frozen source files (normalised SHA-256: carriage returns before line feeds removed).
SOURCES = ("src/miaosuan_agent/experiments/t12_dispersion_shadow.py",
           "src/miaosuan_agent/evaluation/s28_t12.py",
           "scripts/s28_t12.py",
           "src/miaosuan_agent/evaluation/s18_census.py",
           "scripts/s18_census.py",
           "scripts/s18_admission.py",
           "src/miaosuan_agent/evaluation/t7_visibility.py",
           "src/miaosuan_agent/decision/gate.py",
           "src/miaosuan_agent/decision/routing.py",
           "src/miaosuan_agent/boundary/terrain.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s12_screen.py")
INTEGRITY = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123}
HH_EQUAL = 11524
SIDE_GAMES = {"H0": 16, "HH": 4}
MOVE_ORDERS = {"H0": 509, "HH": 416}
#: Sprint 18's admission table: ground damage events on stationary units on an objective, (stacked, alone).
STATIONARY_ON_OBJECTIVE = {"H0": (40, 13), "HH": (10, 3)}
H0_SIDES_STATIONARY_STACKED_HIT = 10
#: Largest public file (bytes); larger row tables are split in order into numbered parts.
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


def load_script(name: str, file: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / "scripts" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------------------------------------------
# freeze

def protocol() -> Dict[str, Any]:
    from miaosuan_agent.experiments import t12_dispersion_shadow as ts
    from miaosuan_agent.evaluation import s28_t12 as st
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": st.STUDY_ID, "engine_sessions": 0,
        "own_ground_unit": "own operator of type 1 or 2 (artillery included) with an integer hex; passengers are not "
                           "operators",
        "shadow": {"identity": ts.SHADOW_ID, "status": ts.STATUS, "executable": ts.EXECUTABLE,
                   "idle_levels_in_order": list(ts.IDLE_LEVELS), "transition_fields": list(ts.TRANSITION_FIELDS),
                   "minimum_idle_units": ts.MIN_IDLE, "stacking_limit": ts.STACK_LIMIT,
                   "passable_modes": [int(m) for m in ts.GROUND_MODES],
                   "trigger": "a held objective with at least minimum_idle_units idle own ground units on its centre, "
                              "none under an active hold, and a neighbour (distance 1, inside the map) that is a "
                              "cost-graph neighbour of the centre in a passable mode and holds fewer than "
                              "stacking_limit own ground units",
                   "legal_reasons_first_match": list(ts.LEGAL_REASONS),
                   "admissible_reasons_first_match": list(ts.ADMISSIBLE_REASONS),
                   "holder": "the idle centre unit with the fewest admissible destinations, then the lowest unit id",
                   "destination": "the admissible destination with the fewest own ground units after the moves "
                                  "already assigned at this decision, then the lowest entry cost in the unit's mode, "
                                  "then the lowest hex, while the count stays within the stacking limit; objectives "
                                  "in increasing hex order share one count per decision",
                   "batch_outcomes": list(ts.BATCH_OUTCOMES),
                   "action": "one appended MOVE per dispersed unit with a one-hex route, after baseline-v2's "
                             "unchanged actions",
                   "hold": "every baseline-v2 MOVE of a dispersed unit is withheld until the objective is not held "
                           "or the unit is absent",
                   "release_reasons_first_match": list(ts.RELEASE_REASONS)},
        "episode": "a maximal run of consecutive play decisions at which one objective meets the tier; tiers: trigger "
                   "(theoretical) and legal (the frozen batch disperses at least one unit)",
        "distinct_episode_key": "scenario-side, objective, start step and the idle centre units at the start",
        "damage_window_steps": st.WINDOW,
        "opportunity_stop": {"rule": "met when any of the four HH side-games has fewer than one distinct trigger "
                                     "episode, or the HH side-games are not all present",
                             "minimum_per_hh_side_game": st.STOP_MIN_EPISODES_PER_HH_SIDE_GAME,
                             "h0": "reported under two readings (each side-game; total against side-games), not "
                                   "part of the disposition"},
        "legality_gate": "met when any of the four HH side-games has no distinct legal-tier episode",
        "interaction_criteria": {
            "I1_tactical_isolation": "dispersed units (first replica of each distinct legal episode) that receive a "
                                     "baseline-v2 MOVE to an objective the side does not hold while the origin "
                                     "objective is still held, more than half of the dispersed units",
            "I2_holder_ordered_off": "distinct legal episodes whose holder receives a baseline-v2 MOVE while the "
                                     "origin objective is still held, more than half of the episodes",
            "I3_partial_dispersion": "distinct legal episodes in which an idle non-holder stays for lack of an "
                                     "admissible destination or of room, more than half of the episodes",
            "met": "a criterion is met when it is met in HH, in H0 or pooled, each with a non-empty denominator"},
        "dispositions_first_match": list(st.DISPOSITIONS),
        "anchors": {**INTEGRITY, "HH baseline-v2 reconstruction equal": HH_EQUAL,
                    **{f"{p} side-games": v for p, v in SIDE_GAMES.items()},
                    **{f"{p} baseline-v2 move orders": v for p, v in MOVE_ORDERS.items()},
                    **{f"{p} stationary on-objective ground events, stacked": v[0]
                       for p, v in STATIONARY_ON_OBJECTIVE.items()},
                    **{f"{p} stationary on-objective ground events, alone": v[1]
                       for p, v in STATIONARY_ON_OBJECTIVE.items()},
                    "H0 side-games with a stationary stacked hit on an objective": H0_SIDES_STATIONARY_STACKED_HIT},
        "blocks": ["census N4, N5, N6 and T6 blocks (H0 and HH) equal to Sprint 18's census.json",
                   "admission ground events by state (H0 and HH) equal to Sprint 18's admission.json"],
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
    return {"schema": SCHEMA_INPUTS, "study_id": "s28-t12-o1",
            "sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json", "sha256": sha256(S18 / "inputs.json")},
            "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json", "sha256": sha256(S18 / "census.json")},
            "sprint18_admission": {"path": "evaluation/s18-frontier-reset/admission.json",
                                   "sha256": sha256(S18 / "admission.json")},
            "sprint24_experiments": {"path": "evaluation/s24-tactical-frontier-reselection/experiments.json",
                                     "sha256": sha256(S24 / "experiments.json")},
            "H0": s18_inputs["H0"], "HH": s18_inputs["HH"],
            "not_used": "HI, S and R of Sprint 18, every other capture, BOKE-2026 data, the stopped 360-game "
                        "prevalence corpus and any new game"}


def input_problems(committed: Mapping[str, Any], proto: Mapping[str, Any]) -> List[str]:
    problems = []
    for key in ("sprint18_inputs", "sprint18_census", "sprint18_admission", "sprint24_experiments"):
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
# loading: Sprint 18's census, unchanged, with each analysed side handed to the Sprint 28 analysis

def recorded_h0(committed: Mapping[str, Any]) -> Dict[Tuple[str, int], List[List[Mapping[str, Any]]]]:
    """H0's recorded ``baseline-v0`` actions per (game, faction), one list per decision in step order."""
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


def seat_of(recorded: List[List[Mapping[str, Any]]], frames: List[Any]) -> Tuple[Any, bool]:
    """The seat id carried by the side's actions, and whether exactly one id occurs."""
    actors = {a.get("actor") for lst in recorded for a in lst} | {a.get("actor") for f in frames for a in f.actions}
    actors.discard(None)
    return (next(iter(actors)) if len(actors) == 1 else None), len(actors) == 1


def make_loader(committed: Mapping[str, Any]) -> Any:
    from miaosuan_agent.evaluation import s18_census as sc
    from miaosuan_agent.evaluation import s28_t12 as st
    from miaosuan_agent.experiments import t12_dispersion_shadow as ts
    base = load_script("s18_census_script", "s18_census.py").Census

    class Loader(base):
        """Sprint 18's census, unchanged, with each analysed side also passed to the Sprint 28 analysis."""

        def __init__(self) -> None:
            super().__init__()
            self.pending: Dict[Any, Any] = {}
            self.values: Dict[str, Dict[Any, Any]] = {}
            self.analyses: Dict[str, List[Any]] = {"H0": [], "HH": []}
            self.recorded = recorded_h0(committed)
            self.recorded_differs = 0
            self.side_checks: Dict[str, Dict[str, bool]] = {}
            proxy = types.SimpleNamespace(**{k: getattr(sc, k) for k in dir(sc) if not k.startswith("__")})

            def frame_from_raw(k, raw, faction, actions=(), concealment=()):
                for c in raw.get("cities") or ():
                    if isinstance(c, Mapping):
                        self.pending[c.get("coord")] = c.get("value")
                frame = sc.frame_from_raw(k, raw, faction, actions, concealment)
                frame.extras = {u.get("obj_id"): {name: u.get(name) for name in ts.TRANSITION_FIELDS}
                                for u in raw.get("operators") or ()
                                if isinstance(u, Mapping) and u.get("color") == faction and u.get("type") in (1, 2)}
                marks = raw.get("landmarks") if isinstance(raw.get("landmarks"), Mapping) else {}
                frame.roadblocks = frozenset(h for h in (marks.get("roadblocks") or ()) if sc.as_int(h) is not None)
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
                label = side_label(population, game, faction)
                blocks = {f.roadblocks for f in frames}
                actor, one = seat_of(recorded, frames)
                self.side_checks[label] = {"one roadblock set per game": len(blocks) == 1,
                                           "one seat id in the side's actions": one}
                side = st.Side(population, label, game.game, game.scenario, faction, frames, recorded,
                               router.costs, next(iter(blocks)) if blocks else frozenset(),
                               [f.extras for f in frames], sc.event_rows(game, faction),
                               self.values.get(game.game, {}), actor)
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
# fidelity (section 14)

def fidelity(loader: Any) -> Dict[str, Any]:
    census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))
    admission = json.loads((S18 / "admission.json").read_text(encoding="utf-8"))
    script = load_script("s18_census_script", "s18_census.py")
    families = script.summarise_lists(loader.families)
    scan = script.summarise_lists(loader.scan)
    tables = load_script("s18_admission_script", "s18_admission.py").tables(loader.private["events"], loader.private["sides"])
    anchors: Dict[str, Dict[str, Any]] = {}

    def put(name: str, published: Any, replay: Any, also: bool = True) -> None:
        anchors[name] = {"published": published, "replay": replay, "equal": replay == published and also}

    for name, value in INTEGRITY.items():
        put(name, value, loader.integrity.get(name))
    put("H0 recorded actions differ from reconstructed baseline-v2 (separate pass)",
        INTEGRITY["H0 v2 differs from recorded v0"], loader.recorded_differs)
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    put("HH baseline-v2 reconstruction equal to the recorded seat", HH_EQUAL, hh[0], hh[0] == hh[1])
    for pop, value in SIDE_GAMES.items():
        put(f"{pop} side-games", value, len(loader.analyses[pop]))
    for pop, value in MOVE_ORDERS.items():
        put(f"{pop} baseline-v2 move orders", value, families.get("T6", {}).get(pop, {}).get("move_orders"),
            census["families"]["T6"][pop]["move_orders"] == value)
    for pop, (stacked, alone) in STATIONARY_ON_OBJECTIVE.items():
        rows = tables[pop]["ground_events_by_state"]
        published = admission["tables"][pop]["ground_events_by_state"]
        put(f"{pop} stationary on-objective ground events, stacked", stacked,
            rows.get("stationary, on an objective, stacked"), published["stationary, on an objective, stacked"] == stacked)
        put(f"{pop} stationary on-objective ground events, alone", alone,
            rows.get("stationary, on an objective, alone"), published["stationary, on an objective, alone"] == alone)
        mine = [r for a in loader.analyses[pop] for r in a.damage]
        put(f"{pop} stationary on-objective ground events in this study's own enumeration", stacked + alone, len(mine))
        put(f"{pop} of which stacked in this study's own enumeration", stacked, sum(1 for r in mine if r["stacked"]))
    put("H0 side-games with a stationary stacked hit on an objective", H0_SIDES_STATIONARY_STACKED_HIT,
        tables["H0"].get("sides_with_a_stationary_stacked_hit_on_an_objective"),
        admission["tables"]["H0"]["sides_with_a_stationary_stacked_hit_on_an_objective"] == H0_SIDES_STATIONARY_STACKED_HIT)
    blocks = {f"{item} {pop} block equal to census.json": (families if item == "T6" else scan).get(item, {}).get(pop)
              == (census["families"] if item == "T6" else census["scan"])[item][pop]
              for item in ("T6", "N4", "N5", "N6") for pop in ("H0", "HH")}
    blocks.update({f"admission {pop} ground events by state equal to admission.json":
                   tables[pop]["ground_events_by_state"] == admission["tables"][pop]["ground_events_by_state"]
                   for pop in ("H0", "HH")})
    integrity = {a.side.label: all(a.integrity.values()) and all(loader.side_checks[a.side.label].values())
                 for pop in ("H0", "HH") for a in loader.analyses[pop]}
    ok = all(a["equal"] for a in anchors.values()) and all(blocks.values()) and all(integrity.values())
    return {"anchors": anchors, "blocks": blocks, "side_integrity": integrity, "ok": ok}


# ------------------------------------------------------------------------------------------------
# smoke (pre-registration known-answer run; prints no T12 figure)

def smoke(committed: Mapping[str, Any]) -> int:
    from miaosuan_agent.experiments import t12_dispersion_shadow as ts
    started = time.time()
    ts.MIN_IDLE = 10 ** 6
    loader = load(committed)
    fid = fidelity(loader)
    print("fidelity ok" if fid["ok"] else "FIDELITY FAILS",
          {k: v["replay"] for k, v in fid["anchors"].items() if not v["equal"]},
          [k for k, v in fid["blocks"].items() if not v], [k for k, v in fid["side_integrity"].items() if not v])
    for pop in ("H0", "HH"):
        analyses = loader.analyses[pop]
        changed = sum(len(a.shadow.added) + len(a.shadow.withheld) for a in analyses)
        unchanged = all(list(a.shadow.candidate[i]) == [dict(x) for x in f.actions]
                        for a in analyses for i, f in enumerate(a.side.frames))
        unexplained = sum(len(a.shadow.unexplained) for a in analyses)
        print(f"{pop}: side-games {len(analyses)}, never-firing shadow: changed decisions {changed}, candidate equal "
              f"to baseline-v2 at every decision {unchanged}, unexplained differences {unexplained}")
    texts, blob = assemble(loader)
    print("assembled public files:", ", ".join(sorted(texts)), "| private rows written:", bool(blob))
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


def refused(head: Mapping[str, Any], fid_ok: bool) -> Dict[str, str]:
    """The only file written when the public sanitizer refuses a result file (section 20: serializer failure)."""
    from miaosuan_agent.evaluation import s28_t12 as st
    data = {**head, "disposition": st.DISPOSITIONS[0], "fidelity_ok": bool(fid_ok),
            "reason": "the public sanitizer refused a result file; no other result is published"}
    return {"disposition.json": dump(data)}


def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    return assemble(load(committed))


def assemble(loader: Any) -> Tuple[Dict[str, str], bytes]:
    """The public texts and the private rows of a loaded study (only ``disposition.json`` on a sanitizer refusal)."""
    from miaosuan_agent.evaluation import s28_t12 as st
    fid = fidelity(loader)
    head = {"schema": SCHEMA_RESULTS, "study_id": st.STUDY_ID,
            "protocol_sha256": sha256(PROTOCOL), "inputs_sha256": sha256(INPUTS)}
    analyses = loader.analyses["H0"] + loader.analyses["HH"]
    integrity_ok = all(all(a.integrity.values()) for a in analyses) and all(
        all(v.values()) for v in loader.side_checks.values())
    unexplained = sum(len(a.shadow.unexplained) for a in analyses)
    stop = st.stops(analyses)
    inter = st.interaction(analyses)
    verdict = st.disposition(fid["ok"], integrity_ok, unexplained, stop, inter)
    evidence = ("H0: baseline-v0 trajectories, baseline-v2 reconstructed on them (descriptive unless the recorded "
                "prefix equals baseline-v2); HH: genuine baseline-v2 seats, four games of one scenario, two openings. "
                "Before a side's first divergence the candidate equals baseline-v2; episodes after it lie on "
                "off-policy recorded states and are historical opportunity only. Onward and damage facts are "
                "historical labels, not causal estimates.")
    public: Dict[str, Any] = {"fidelity.json": {**head, **fid}}
    public["census.json"] = {**head, "evidence_boundary": evidence,
                             "H0": st.pooled(loader.analyses["H0"]), "HH": st.pooled(loader.analyses["HH"]),
                             "pooled": st.pooled(analyses)}
    public.update(split_rows("sides", head, [st.side_summary(a) for a in analyses]))
    public["divergence.json"] = {**head, "evidence_boundary": evidence,
                                 "certificates": [c for c in (st.certificate(a) for a in analyses) if c is not None],
                                 "side_games_without_divergence": [a.side.label for a in analyses
                                                                   if a.shadow.first_divergence is None]}
    counted = {id(occ[0][1]) for occ in st.distinct(analyses, "legal").values()}
    for pop in ("H0", "HH"):
        rows = [st.public_episode(a, r, i, id(r) in counted)
                for a in loader.analyses[pop] for i, r in enumerate(a.legal_episodes, start=1)]
        public.update(split_rows(f"episodes-{pop}", {**head, "population": pop}, rows))
    damage_rows = [st.public_damage_row(a, r) for a in analyses for r in a.damage]
    public.update(split_rows("damage", {**head, "summary": st.damage_summary(analyses)}, damage_rows))
    public["disposition.json"] = {**head, **verdict, "stops": stop, "interaction": inter,
                                  "readiness_risks": st.readiness_risks(analyses)}
    private_values = loader.hexes | loader.ids
    scenarios = {a.side.scenario for a in analyses}
    for name, data in public.items():
        problems = st.public_problems(data, private_values)
        problems += [f"digit word {w!r}" for w in st.digit_words(data, scenarios)]
        if problems:
            print(f"the public sanitizer refused {name} ({len(problems)} findings)")
            return refused(head, fid["ok"]), b""
    texts = {name: dump(data) for name, data in public.items()}
    for name, text in texts.items():
        if len(text.encode("utf-8")) > PUBLIC_LIMIT:
            print(f"{name} exceeds the public size limit")
            return refused(head, fid["ok"]), b""

    def check_private(c: Any) -> Dict[str, Any]:
        return {"objective": c.objective, "centre_units": c.centre_units, "idle": c.idle, "trigger": c.trigger,
                "legal_tier": c.legal_tier, "units": [vars(x) for x in c.units]}

    def episode_private(r: Mapping[str, Any]) -> Dict[str, Any]:
        return {**{k: v for k, v in r.items() if k != "check"}, "check": check_private(r["check"])}

    private = {"sides": [{"population": a.side.population, "label": a.side.label,
                          "trigger_episodes": [episode_private(r) for r in a.trigger_episodes],
                          "legal_episodes": [episode_private(r) for r in a.legal_episodes],
                          "damage": a.damage, "added": {str(k): list(v) for k, v in a.shadow.added.items()},
                          "withheld": {str(k): list(v) for k, v in a.shadow.withheld.items()},
                          "unexplained": a.shadow.unexplained, "integrity": a.integrity} for a in analyses]}
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
    stale = sorted(p.name for p in OUT.glob("*.json")
                   if p.name not in texts and p.name not in ("protocol.json", "inputs.json", "mutation.json"))
    if check:
        same = all((OUT / name).exists() and (OUT / name).read_text(encoding="utf-8") == text
                   for name, text in texts.items()) and not stale
        if blob:
            same &= (PRIVATE / "study-private.json.gz").exists() and (PRIVATE / "study-private.json.gz").read_bytes() == blob
        print("study identical" if same else f"MISMATCH {stale}")
        return 0 if same else 1
    if stale:
        print("result files from an earlier run are present; refusing to write:", stale)
        return 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    if blob:
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
