"""Sprint 20 T11-O1 kill-first target rule, offline replay (``docs/SPRINT20_T11_REPLAY.md``). Offline only.

    python scripts/s20_t11_replay.py kill-model [--check]
    python scripts/s20_t11_replay.py freeze [--check]
    python scripts/s20_t11_replay.py smoke
    python scripts/s20_t11_replay.py run [--check]

``kill-model`` writes ``evaluation/s20-t11-replay/kill_model.json``, the documentary assessment of section 11, after
checking every quotation against the local documentation snapshot and each quoted file against the snapshot's own
``SHA256SUMS``; it runs on the workstation, where the snapshot is. ``freeze`` writes ``protocol.json`` (the frozen rule,
the registered thresholds, the disposition order, the Sprint 18 anchors, the SHA-256 of ``kill_model.json`` and the
normalised SHA-256 of every frozen source) and ``inputs.json`` (the Sprint 18 H0 and HH pins, copied from Sprint 18's
committed ``inputs.json``, which is pinned with ``census.json``); ``inputs.json`` needs the private inputs, so the
server writes it, while ``protocol.json`` can be written and checked anywhere.

``smoke`` is the pre-freeze known-answer run on the real inputs: both runs use ``baseline-v2``'s ranking, so no
difference may appear anywhere; it prints the fidelity items and the difference count only, no T11 figure.

``run`` refuses unless every input and frozen source matches its pin. It loads H0 and HH with Sprint 18's census
loaders (``scripts/s18_census.py``, unchanged), reproduces Sprint 18's fire-choice anchors and integrity figures
(section 10; any difference is REPLAY_INVALID), decides every analysed seat-decision twice (``baseline-v2``'s ranking,
which must equal the recorded or reconstructed ``baseline-v2`` actions, and the kill-first ranking), classifies every
difference, and writes the public aggregates (``fidelity.json``, ``replay.json``, ``disposition.json``) and the private
rows (``local/diagnostics/s20/replay-private.json.gz``). ``--check`` rebuilds and compares instead of writing. It runs
on the evaluation server, where the private inputs are.
"""

from __future__ import annotations

import argparse
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

OUT = REPO_ROOT / "evaluation" / "s20-t11-replay"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
KILL_MODEL = OUT / "kill_model.json"
S18 = REPO_ROOT / "evaluation" / "s18-frontier-reset"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s20"
SCHEMA_PROTOCOL = "miaosuan-s20-protocol/1"
SCHEMA_INPUTS = "miaosuan-s20-inputs/1"
SCHEMA_KILL_MODEL = "miaosuan-s20-kill-model/1"
SCHEMA_RESULTS = "miaosuan-s20-results/1"
#: Frozen source files (normalised SHA-256: carriage returns before line feeds removed).
SOURCES = ("src/miaosuan_agent/experiments/t11_kill_first.py",
           "src/miaosuan_agent/evaluation/s20_t11.py",
           "scripts/s20_t11_replay.py",
           "src/miaosuan_agent/experiments/shoot_reservation.py",
           "src/miaosuan_agent/decision/candidates.py",
           "src/miaosuan_agent/decision/policy.py",
           "src/miaosuan_agent/evaluation/s18_census.py",
           "scripts/s18_census.py")
#: Sprint 18 figures the replay must reproduce exactly (``census.json`` scan N3; section 10).
ANCHORS = {"H0 baseline-v2 direct-fire shots": ("H0", "shots", 432),
           "H0 shots with two or more targets listed": ("H0", "shots_with_two_or_more_targets", 368),
           "H0 shots with a lower-blood target listed": ("H0", "lower_blood_target_listed", 127),
           "HH baseline-v2 direct-fire shots": ("HH", "shots", 319),
           "HH shots with two or more targets listed": ("HH", "shots_with_two_or_more_targets", 267),
           "HH shots with a lower-blood target listed": ("HH", "lower_blood_target_listed", 97)}
INTEGRITY = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123}
SNAPSHOT_SUMS = REPO_ROOT / "local" / "source-archives" / "SHA256SUMS"


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


# ------------------------------------------------------------------------------------------------
# freeze

def kill_model() -> Dict[str, Any]:
    """The documentary assessment of section 11, with the snapshot digests of the quoted files (from the snapshot's
    ``SHA256SUMS``; the snapshot itself is local and not redistributed)."""
    from miaosuan_agent.evaluation import s20_t11 as st
    sums = {}
    for line in SNAPSHOT_SUMS.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(" ", 1)
        sums[name.lstrip("*").removeprefix("./")] = digest
    files = sorted({name for item in st.KILL_MODEL_ITEMS for name, _ in item["quotes"]})
    snapshot = REPO_ROOT / st.SNAPSHOT
    for name in files:
        if sha256(snapshot / name) != sums[f"docs-live-snapshot-20260929/{name}"]:
            raise SystemExit(f"{name} does not match the snapshot's SHA256SUMS")
    problems = st.quote_problems(st.KILL_MODEL_ITEMS, lambda n: (snapshot / n).read_text(encoding="utf-8"))
    if problems:
        raise SystemExit(f"quotation problems: {problems}")
    return {"schema": SCHEMA_KILL_MODEL, "study_id": "s20-t11-replay",
            "question": "P(immediate destruction of the observed target | its current state, the listed shoot option), "
                        "from the public platform documentation only",
            "snapshot": {"fetched": "2026-09-29T18:41:10+08:00", "path": st.SNAPSHOT,
                         "files_sha256": {name: sums[f"docs-live-snapshot-20260929/{name}"] for name in files}},
            "items": [{**item, "quotes": [list(q) for q in item["quotes"]]} for item in st.KILL_MODEL_ITEMS],
            "rule": "available only if every item is documented; an inferred or undocumented item means an "
                    "unsupported assumption",
            "available": st.kill_model_available(), "gaps": st.kill_model_gaps()}


def protocol() -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s20_t11 as st
    from miaosuan_agent.experiments import t11_kill_first as tk
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": "s20-t11-replay", "engine_sessions": 0,
        "rule": {"identity": tk.SHADOW_ID, "rankings": list(tk.RANKINGS),
                 "selection": "after the same-step reservation's exclusions: the remaining engage candidates whose "
                              "target has the lowest observed blood, then baseline-v2's rank (highest attack level, "
                              "lower target id, lower weapon id)",
                 "blood": "the enemy unit's blood field in the seat's operators: a non-negative int, not a bool",
                 "fail_closed": list(tk.FALLBACKS)},
        "classes": list(st.CLASSES), "kinds": list(st.KINDS),
        "opportunity": {"unit": "changed emitted shoot actions (root and reservation-induced) of one HH side-game",
                        "minimum_per_hh_side_game": st.OPPORTUNITY_MIN, "hh_side_games": st.HH_SIDE_GAMES},
        "pure_target_priority": "fails on any lost, gained or other non-shoot difference in any HH or H0 side-game",
        "kill_edge": "pooled paired HH delta of p_kill_now over changed emitted shots strictly above 0",
        "kill_model": {"path": "evaluation/s20-t11-replay/kill_model.json", "sha256": sha256(KILL_MODEL),
                       "available": st.kill_model_available(), "gaps": st.kill_model_gaps()},
        "dispositions_first_match": list(st.DISPOSITIONS),
        "anchors": {k: v[2] for k, v in ANCHORS.items()}, "integrity": dict(INTEGRITY),
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
    return {"schema": SCHEMA_INPUTS, "study_id": "s20-t11-replay",
            "sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json",
                                "sha256": sha256(S18 / "inputs.json")},
            "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json",
                                "sha256": sha256(S18 / "census.json")},
            "H0": s18_inputs["H0"], "HH": s18_inputs["HH"],
            "not_used": "HI, S and R of Sprint 18, every other capture, BOKE-2026 data and the stopped 360-game "
                        "prevalence corpus; no sensitivity corpus is declared"}


def input_problems(committed: Mapping[str, Any], proto: Mapping[str, Any]) -> List[str]:
    problems = []
    for key in ("sprint18_inputs", "sprint18_census"):
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
    if sha256(KILL_MODEL) != proto["kill_model"]["sha256"]:
        problems.append(proto["kill_model"]["path"])
    return problems


# ------------------------------------------------------------------------------------------------
# loading H0 and HH through Sprint 18's census, with both rankings decided on every analysed seat-decision

def side_label(population: str, game: Any, faction: int) -> str:
    colour = "red" if faction == 0 else "blue"
    if population == "HH":
        return f"HH {game.game.rsplit('.', 1)[-1]} baseline-v2 {colour}"
    return f"H0 {game.scenario} {colour}"


def seat_of(observation: Any, faction: int) -> int:
    seats = [s for s, info in observation.role_and_grouping().items() if info.faction == faction]
    if len(seats) != 1:
        raise SystemExit(f"cannot derive the seat of faction {faction}: {len(seats)} candidates")
    return seats[0]


def make_loader(ranking: str) -> Any:
    from miaosuan_agent.boundary import Observation, Origin
    from miaosuan_agent.decision import Memory
    from miaosuan_agent.evaluation import s18_census as sc
    from miaosuan_agent.evaluation import s20_t11 as st
    from miaosuan_agent.experiments import t11_kill_first as tk
    base = census_script().Census

    class Loader(base):
        """Sprint 18's census, unchanged, with every analysed seat-decision also decided by both rankings."""

        def __init__(self) -> None:
            super().__init__()
            self.analyses: Dict[str, List[Any]] = {"H0": [], "HH": []}
            self.pending: Dict[int, List[Tuple[Any, ...]]] = {}
            self.analysed_factions: Tuple[int, ...] = (0, 1)
            self.current_costs: Any = None
            self.seats: Dict[int, Any] = {}
            self.fresh = True
            self.decided = 0
            proxy = types.SimpleNamespace(**{k: getattr(sc, k) for k in dir(sc) if not k.startswith("__")})
            proxy.frame_from_raw = self.frame_hook
            self.sc = proxy

        def router(self, scenario: str, map_id: str) -> Any:
            router = super().router(scenario, map_id)
            self.current_costs = router.costs
            return router

        def frame_hook(self, k, raw, faction, actions=(), concealment=()):
            frame = sc.frame_from_raw(k, raw, faction, actions, concealment)
            if faction in self.analysed_factions:
                if self.fresh:
                    self.seats, self.fresh = {}, False
                self.pending.setdefault(faction, []).append(self.decide(raw, faction, actions))
            return frame

        def decide(self, raw: Mapping[str, Any], faction: int, reference: Any) -> Tuple[Any, ...]:
            observation = Observation.from_raw(raw, Origin.ENGINE)
            seat = seat_of(observation, faction)
            if seat not in self.seats:
                b = tk.RankedReservationPolicy(self.current_costs, tk.BASELINE)
                c = tk.RankedReservationPolicy(self.current_costs, ranking)
                c.router = b.router  # one deterministic memoised router for both rankings
                self.seats[seat] = [b, c, Memory(), Memory()]
            b, c, b_memory, c_memory = self.seats[seat]
            bd = b.decide(observation, seat, faction, b_memory)
            cd = c.decide(observation, seat, faction, c_memory)
            self.seats[seat][2], self.seats[seat][3] = bd.memory, cd.memory
            time_info = raw.get("time") or {}
            comparison = st.compare_decision(time_info.get("stage"), bd.actions, b.records, cd.actions, c.records,
                                             bd.memory, cd.memory)
            equal = [dict(a) for a in bd.actions] == [dict(a) for a in reference]
            self.decided += 1
            views = dict(c.views) if comparison.diffs else {}
            return time_info.get("cur_step"), time_info.get("stage"), equal, comparison, views

        def h0(self, inputs: Mapping[str, Any]) -> None:
            self.analysed_factions = (0, 1)
            super().h0(inputs)

        def timeline_game(self, population: str, entry: Mapping[str, Any]) -> None:
            record = json.loads((REPO_ROOT / entry["record"]["path"]).read_text(encoding="utf-8"))
            self.analysed_factions = tuple(s["faction"] for s in record["seats"]
                                           if s["policy"] == "baseline-v2-candidate-shoot-target-reservation")
            super().timeline_game(population, entry)

        def side(self, population, game, faction, router, analyse_threat):
            out = super().side(population, game, faction, router, analyse_threat)
            if population in self.analyses:
                rows = sorted(self.pending.pop(faction, []), key=lambda r: r[0])
                frames = game.sides[faction]
                analysis = st.SideAnalysis(population, side_label(population, game, faction))
                if [r[0] for r in rows] != [f.cur_step for f in frames]:
                    analysis.problems.append("the decided steps do not match the side's frames one to one")
                for f, (step, stage, equal, comparison, views) in zip(frames, rows):
                    analysis.add(f.k, step, stage, equal, comparison, views)
                self.analyses[population].append(analysis)
            self.fresh = True
            return out

    return Loader()


def load(committed: Mapping[str, Any], ranking: str) -> Any:
    loader = make_loader(ranking)
    loader.h0(committed)
    for entry in committed["HH"]["games"]:
        loader.timeline_game("HH", entry)
    return loader


# ------------------------------------------------------------------------------------------------
# fidelity

def fidelity(loader: Any) -> Dict[str, Any]:
    census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))
    scan = census_script().summarise_lists(loader.scan)
    anchors = {}
    for name, (pop, key, value) in ANCHORS.items():
        got = scan.get("N3", {}).get(pop, {}).get(key)
        anchors[name] = {"sprint18": value, "replay": got,
                         "equal": got == value and census["scan"]["N3"][pop][key] == value}
    for name, value in INTEGRITY.items():
        got = loader.integrity.get(name)
        anchors[name] = {"sprint18": value, "replay": got, "equal": got == value}
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    anchors["HH baseline-v2 reconstruction equal to the recorded seat"] = {
        "sprint18": 11524, "replay": hh[0], "equal": hh[0] == hh[1] == 11524}
    blocks = {f"fire-choice block {pop} equal to census.json": scan.get("N3", {}).get(pop) == census["scan"]["N3"][pop]
              for pop in ("H0", "HH")}
    sides = {pop: len(v) for pop, v in loader.analyses.items()}
    reproduce = {pop: [sum(a.reference_equal for a in loader.analyses[pop]),
                       sum(a.reference_compared for a in loader.analyses[pop]),
                       sum(a.decisions for a in loader.analyses[pop])] for pop in ("H0", "HH")}
    integrity = {a.label: a.integrity_ok for pop in ("H0", "HH") for a in loader.analyses[pop]}
    problems = {a.label: len(a.problems) for pop in ("H0", "HH") for a in loader.analyses[pop]}
    ok = (all(a["equal"] for a in anchors.values()) and all(blocks.values()) and sides == {"H0": 16, "HH": 4}
          and reproduce["H0"] == [33696, 33696, 33696] and reproduce["HH"] == [11524, 11524, 11524]
          and all(integrity.values()))
    return {"anchors": anchors, "blocks": blocks, "side_games": sides,
            "baseline_ranking_reproduces_baseline_v2": reproduce, "integrity_by_side_game": integrity,
            "problems_by_side_game": problems, "ok": ok}


# ------------------------------------------------------------------------------------------------
# smoke (pre-freeze known-answer run; prints no T11 figure)

def smoke(committed: Mapping[str, Any]) -> int:
    from miaosuan_agent.evaluation import s20_t11 as st
    from miaosuan_agent.experiments import t11_kill_first as tk
    started = time.time()
    loader = load(committed, tk.BASELINE)
    fid = fidelity(loader)
    print("fidelity ok" if fid["ok"] else "FIDELITY FAILS",
          {k: v["replay"] for k, v in fid["anchors"].items() if not v["equal"]})
    print("baseline ranking reproduces baseline-v2 [equal, compared, decisions]:",
          fid["baseline_ranking_reproduces_baseline_v2"])
    for pop in ("H0", "HH"):
        analyses = loader.analyses[pop]
        diffs = sum(a.changed_decisions for a in analyses)
        print(f"{pop}: side-games {len(analyses)}, decisions with a difference {diffs}, "
              f"problems {sum(len(a.problems) for a in analyses)}, nonshoot {sum(st.nonshoot(a) for a in analyses)}")
    print(f"decided {loader.decided}; seconds {time.time() - started:.0f}")
    return 0


# ------------------------------------------------------------------------------------------------
# run

def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s20_t11 as st
    from miaosuan_agent.experiments import t11_kill_first as tk
    loader = load(committed, tk.KILL_FIRST)
    fid = fidelity(loader)
    model = json.loads(KILL_MODEL.read_text(encoding="utf-8"))
    head = {"schema": SCHEMA_RESULTS, "study_id": "s20-t11-replay", "protocol_sha256": sha256(PROTOCOL),
            "inputs_sha256": sha256(INPUTS), "kill_model_sha256": sha256(KILL_MODEL)}
    public: Dict[str, Any] = {"fidelity.json": {**head, **fid}}
    hh, h0 = loader.analyses["HH"], loader.analyses["H0"]
    if not fid["ok"]:
        public["disposition.json"] = {**head, **st.disposition(False, model["available"], None, [], None)}
    else:
        public["replay.json"] = {
            **head,
            "evidence_boundary": "every action list of one seat-decision is decided from the same recorded observation, "
                                 "so each comparison, reservation effects included, is a valid action-level "
                                 "counterfactual; after a side-game's first change the recorded states are off-policy "
                                 "for T11. H0 states are baseline-v0 trajectories with baseline-v2 reconstructed.",
            "kill_model": {"available": model["available"], "gaps": model["gaps"],
                           "p_kill_now": "not computed: the documented model is unavailable" if not model["available"]
                           else "computed"},
            "HH": {"sides": [st.public_side(a) for a in hh], "pooled": st.pooled(hh)},
            "H0": {"sides": [st.public_side(a) for a in h0], "pooled": st.pooled(h0)}}
        public["disposition.json"] = {**head, **st.disposition(True, model["available"], st.coupled(hh + h0),
                                                               st.changed_shot_counts(hh), None),
                                      "coupled_hh": st.coupled(hh), "coupled_h0": st.coupled(h0)}
    private_values = loader.hexes | loader.ids
    for name, data in public.items():
        problems = st.public_problems(data, private_values)
        if problems:
            raise SystemExit(f"privacy problems in {name}: {problems[:10]}")
    texts = {name: dump(data) for name, data in public.items()}
    private = {pop: [{"label": a.label, "rows": a.private_rows, "root_rows": a.root_rows,
                      "induced_rows": a.induced_rows, "problems": a.problems[:200]}
                     for a in loader.analyses[pop]] for pop in ("H0", "HH")}
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
        same &= (PRIVATE / "replay-private.json.gz").exists() and (PRIVATE / "replay-private.json.gz").read_bytes() == blob
        print("replay identical" if same else "MISMATCH")
        return 0 if same else 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "replay-private.json.gz").write_bytes(blob)
    print("wrote", ", ".join(sorted(texts)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--check", action="store_true")
    sub.add_parser("smoke")
    p = sub.add_parser("kill-model")
    p.add_argument("--check", action="store_true")
    p = sub.add_parser("freeze")
    p.add_argument("--check", action="store_true")
    p.add_argument("--protocol-only", action="store_true", help="write or check protocol.json alone (no private data)")
    args = parser.parse_args()
    if args.command in ("kill-model", "freeze"):
        if args.command == "kill-model":
            texts = {KILL_MODEL: dump(kill_model())}
        else:
            texts = {PROTOCOL: dump(protocol())}
            if not args.protocol_only:
                texts[INPUTS] = dump(inputs())
        if args.check:
            same = all(p.exists() and p.read_text(encoding="utf-8") == t for p, t in texts.items())
            print(("identical: " + ", ".join(p.name for p in texts)) if same else "MISMATCH")
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
