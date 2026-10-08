"""Sprint 25 T13-D1: held-objective loss anatomy and garrison shadow (``docs/SPRINT25_T13_D1.md``). Offline only.

    python scripts/s25_t13_d1.py freeze [--check]
    python scripts/s25_t13_d1.py smoke
    python scripts/s25_t13_d1.py run [--check]

``freeze`` writes ``evaluation/s25-t13-d1/protocol.json`` (the frozen definitions, parameters, thresholds, disposition
order and the normalised SHA-256 of every frozen source) and ``inputs.json`` (Sprint 18's H0 and HH pins, copied from
Sprint 18's committed ``inputs.json``, itself pinned with ``census.json``).

``smoke`` is the pre-registration known-answer run on the real inputs; it prints no loss, departure, trigger or garrison
figure: with the threat margin set so that no enemy can qualify, the shadow must withhold nothing, the candidate must
equal ``baseline-v2`` at every decision, and every fidelity anchor must hold.

``run`` refuses unless every input and frozen source matches its pin. It loads H0 and HH with Sprint 18's census loader
(``scripts/s18_census.py``, unchanged; H0's recorded ``baseline-v0`` actions are read in a separate pass and aligned by
decision), reproduces the registered fidelity anchors (any difference: ``T13_D1_INVALID``), applies the frozen anatomy
and shadow (``evaluation/s25_t13.py``, ``experiments/t13_garrison_shadow.py``) and writes the public aggregates
(``fidelity.json``, ``anatomy.json``, ``shadow.json``, ``losses-H0.json``, ``losses-HH.json``, ``disposition.json``) and
the private rows (``local/diagnostics/s25/study-private.json.gz``). ``--check`` rebuilds and compares instead of writing.
It runs on the evaluation server, where the private inputs are.
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

OUT = REPO_ROOT / "evaluation" / "s25-t13-d1"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
S18 = REPO_ROOT / "evaluation" / "s18-frontier-reset"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s25"
SCHEMA_PROTOCOL = "miaosuan-s25-protocol/1"
SCHEMA_INPUTS = "miaosuan-s25-inputs/1"
SCHEMA_RESULTS = "miaosuan-s25-results/1"
#: Frozen source files (normalised SHA-256: carriage returns before line feeds removed).
SOURCES = ("src/miaosuan_agent/experiments/t13_garrison_shadow.py",
           "src/miaosuan_agent/evaluation/s25_t13.py",
           "scripts/s25_t13_d1.py",
           "src/miaosuan_agent/evaluation/s18_census.py",
           "scripts/s18_census.py",
           "src/miaosuan_agent/evaluation/t7_candidates.py",
           "src/miaosuan_agent/evaluation/t7_visibility.py",
           "src/miaosuan_agent/evaluation/s12_timeline.py",
           "src/miaosuan_agent/evaluation/s12_screen.py")
#: Sprint 18 figures the replay must reproduce exactly (section 11).
INTEGRITY = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123}
HH_EQUAL = 11524
LOSSES = {"H0": 40, "HH": 26}
ON_HEX = {"H0": 0, "HH": 0}
H0_SIDES_WITH_LOSS = 7
SIDE_GAMES = {"H0": 16, "HH": 4}
#: Largest public file (bytes); larger loss tables are split in order into numbered parts (section 18).
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


# ------------------------------------------------------------------------------------------------
# freeze

def protocol() -> Dict[str, Any]:
    from miaosuan_agent.experiments import t13_garrison_shadow as tg
    from miaosuan_agent.evaluation import s25_t13 as st
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": st.STUDY_ID, "engine_sessions": 0,
        "loss_event": "Sprint 18 N4: over the play-stage decisions of a side in order, an objective whose flag read the "
                      "side's colour at the previous play decision and does not now; placed at that decision",
        "denial_zone": {"radius_hexes": tg.ZONE_RADIUS,
                        "distance": "evaluation/t7_visibility.hex_distance (cube coordinates of the four-digit hex)"},
        "own_ground_unit": "own operator of type 1 or 2 with a readable hex; artillery (type 2, sub_type 3) counts as an "
                           "occupant but is not an eligible defender; passengers are not operators",
        "v_classes": list(st.V_CLASSES), "fates": [st.ALIVE_OUT, st.DESTROYED, st.MISSING, st.UNREADABLE],
        "shadow": {"identity": tg.SHADOW_ID, "status": tg.STATUS, "executable": tg.EXECUTABLE,
                   "threat_margin_hexes": tg.THREAT_MARGIN, "hold_limit_steps": tg.HOLD_LIMIT,
                   "cooldown_steps": tg.COOLDOWN, "trigger_reasons": list(tg.TRIGGER_REASONS),
                   "release_reasons_first_match": list(tg.RELEASE_REASONS),
                   "range_source": "evaluation/t7_candidates.weapon_range: the longest published direct-fire range "
                                   "of a visible enemy ground unit's carried weapons against the defender's class "
                                   "(type 1 personnel, type 2 vehicles); unknown range = not a threat",
                   "proximity": "enemy hex to objective hex at most range + threat margin"},
        "enemy_information_first_match": list(st.ENEMY_INFO), "lookback_steps": st.LOOKBACK,
        "touched_categories": list(st.CATEGORIES),
        "stops": {"A": "for H0, HH and pooled separately: met when 2 * V_ORDER < losses (or no loss)",
                  "B": f"met when distinct touched losses < {st.STOP_B_MIN_TOUCHED} or their distinct scenario-sides "
                       f"< {st.STOP_B_MIN_SCENARIO_SIDES}",
                  "C": "met when no distinct touched loss, or 2 * first-owner departures > distinct touched losses"},
        "dispositions_first_match": list(st.DISPOSITIONS),
        "anchors": {**INTEGRITY, "HH baseline-v2 reconstruction equal": HH_EQUAL,
                    **{f"{p} held-objective losses": v for p, v in LOSSES.items()},
                    **{f"{p} losses with an own unit on the hex before": v for p, v in ON_HEX.items()},
                    "H0 scenario-sides with a loss": H0_SIDES_WITH_LOSS,
                    **{f"{p} side-games": v for p, v in SIDE_GAMES.items()}},
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
    return {"schema": SCHEMA_INPUTS, "study_id": "s25-t13-d1",
            "sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json",
                                "sha256": sha256(S18 / "inputs.json")},
            "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json",
                                "sha256": sha256(S18 / "census.json")},
            "H0": s18_inputs["H0"], "HH": s18_inputs["HH"],
            "not_used": "HI, S and R of Sprint 18, every other capture, BOKE-2026 data, the stopped 360-game "
                        "prevalence corpus and any new game"}


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
    return problems


# ------------------------------------------------------------------------------------------------
# loading: Sprint 18's census, unchanged, with each analysed side handed to the Sprint 25 analysis

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
    from miaosuan_agent.evaluation import s25_t13 as st
    base = census_script().Census

    class Loader(base):
        """Sprint 18's census, unchanged, with each analysed side also passed to the Sprint 25 analysis."""

        def __init__(self) -> None:
            super().__init__()
            self.pending: Dict[Any, Any] = {}
            self.values: Dict[str, Dict[Any, Any]] = {}
            self.analyses: Dict[str, List[Any]] = {"H0": [], "HH": []}
            self.recorded = recorded_h0(committed)
            self.recorded_differs = 0
            proxy = types.SimpleNamespace(**{k: getattr(sc, k) for k in dir(sc) if not k.startswith("__")})

            def frame_from_raw(k, raw, faction, actions=(), concealment=()):
                for c in raw.get("cities") or ():
                    if isinstance(c, Mapping):
                        self.pending[c.get("coord")] = c.get("value")
                return sc.frame_from_raw(k, raw, faction, actions, concealment)

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
                side = st.Side(population, side_label(population, game, faction), game.game, game.scenario, faction,
                               frames, recorded, game.events, self.values.get(game.game, {}))
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
    script = census_script()
    scan = script.summarise_lists(loader.scan)
    anchors: Dict[str, Dict[str, Any]] = {}
    for name, value in INTEGRITY.items():
        got = loader.integrity.get(name)
        anchors[name] = {"sprint18": value, "replay": got, "equal": got == value}
    anchors["H0 recorded actions differ from reconstructed baseline-v2 (separate pass)"] = {
        "sprint18": INTEGRITY["H0 v2 differs from recorded v0"], "replay": loader.recorded_differs,
        "equal": loader.recorded_differs == INTEGRITY["H0 v2 differs from recorded v0"]}
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    anchors["HH baseline-v2 reconstruction equal to the recorded seat"] = {
        "sprint18": HH_EQUAL, "replay": hh[0], "equal": hh[0] == hh[1] == HH_EQUAL}
    for pop in ("H0", "HH"):
        mine = sum(len(a.losses) for a in loader.analyses[pop])
        anchors[f"{pop} held-objective losses"] = {"sprint18": LOSSES[pop], "replay": mine,
                                                   "equal": mine == LOSSES[pop]
                                                   and census["scan"]["N4"][pop]["objective_losses"] == LOSSES[pop]}
        on_hex = scan.get("N4", {}).get(pop, {}).get("losses_with_own_unit_on_it_before")
        anchors[f"{pop} losses with an own unit on the hex before"] = {"sprint18": ON_HEX[pop], "replay": on_hex,
                                                                     "equal": on_hex == ON_HEX[pop]}
        anchors[f"{pop} side-games"] = {"sprint18": SIDE_GAMES[pop], "replay": len(loader.analyses[pop]),
                                        "equal": len(loader.analyses[pop]) == SIDE_GAMES[pop]}
    with_loss = sum(1 for a in loader.analyses["H0"] if a.losses)
    anchors["H0 scenario-sides with a loss"] = {
        "sprint18": H0_SIDES_WITH_LOSS, "replay": with_loss,
        "equal": with_loss == H0_SIDES_WITH_LOSS
        == census["opportunity_sides"]["sides_with_opportunity"]["scan objective lost after being held"]}
    blocks = {f"{item} {pop} block equal to census.json": scan.get(item, {}).get(pop) == census["scan"][item][pop]
              for item in ("N4", "N6") for pop in ("H0", "HH")}
    integrity = {a.side.label: all(a.integrity.values()) for pop in ("H0", "HH") for a in loader.analyses[pop]}
    ok = all(a["equal"] for a in anchors.values()) and all(blocks.values()) and all(integrity.values())
    return {"anchors": anchors, "blocks": blocks, "side_integrity": integrity, "ok": ok}


# ------------------------------------------------------------------------------------------------
# smoke (pre-registration known-answer run; prints no loss, departure, trigger or garrison figure)

def smoke(committed: Mapping[str, Any]) -> int:
    from miaosuan_agent.experiments import t13_garrison_shadow as tg
    started = time.time()
    tg.THREAT_MARGIN = -10 ** 6
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
    """One file, or numbered parts in order when one would exceed the public size limit (section 18)."""
    whole = {**head, "rows": rows, "part": "1/1"}
    if len(dump(whole).encode("utf-8")) <= PUBLIC_LIMIT:
        return {f"{name}.json": whole}
    parts: List[List[Dict[str, Any]]] = [[]]
    for row in rows:
        trial = {**head, "rows": parts[-1] + [row], "part": "9/9"}
        if parts[-1] and len(dump(trial).encode("utf-8")) > PUBLIC_LIMIT:
            parts.append([])
        parts[-1].append(row)
    return {f"{name}-{i}.json": {**head, "rows": part, "part": f"{i}/{len(parts)}"}
            for i, part in enumerate(parts, start=1)}


def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s25_t13 as st
    loader = load(committed)
    fid = fidelity(loader)
    head = {"schema": SCHEMA_RESULTS, "study_id": st.STUDY_ID,
            "protocol_sha256": sha256(PROTOCOL), "inputs_sha256": sha256(INPUTS)}
    analyses = loader.analyses["H0"] + loader.analyses["HH"]
    public: Dict[str, Any] = {"fidelity.json": {**head, **fid}}
    integrity_ok = all(all(a.integrity.values()) for a in analyses)
    unexplained = sum(len(a.shadow.unexplained) for a in analyses)
    stop = st.stops(analyses)
    verdict = st.disposition(fid["ok"], integrity_ok, unexplained, stop)
    evidence = ("H0: baseline-v0 trajectories, baseline-v2 reconstructed on them (descriptive unless the recorded "
                "prefix equals baseline-v2); HH: genuine baseline-v2 seats, four games of one scenario, two openings. "
                "Before a side's first divergence the candidate equals baseline-v2; later shadow states are off-policy.")
    public["anatomy.json"] = {
        **head, "evidence_boundary": evidence,
        "sides": [{k: v for k, v in st.side_summary(a).items()
                   if k in ("side_game", "population", "scenario_side", "losses", "v_classes", "categories")}
                  for a in analyses],
        "H0": st.pooled_table(loader.analyses["H0"]), "HH": st.pooled_table(loader.analyses["HH"]),
        "pooled": st.pooled_table(analyses)}
    public["shadow.json"] = {**head, "evidence_boundary": evidence,
                             "sides": [st.side_summary(a) for a in analyses],
                             "certificates": [c for c in (st.certificate(a) for a in analyses) if c is not None]}
    counted = {id(r) for _, r in st.distinct_touched(analyses)[1]}
    for pop in ("H0", "HH"):
        rows = [st.public_loss(a, r, i, id(r) in counted) for a in loader.analyses[pop]
                for i, r in enumerate(a.losses, start=1)]
        public.update(split_rows(f"losses-{pop}", {**head, "population": pop}, rows))
    public["disposition.json"] = {**head, **verdict, "stops": stop}
    private_values = loader.hexes | loader.ids
    for name, data in public.items():
        problems = st.public_problems(data, private_values)
        if problems:
            raise SystemExit(f"privacy problems in {name}: {problems[:10]}")
    texts = {name: dump(data) for name, data in public.items()}
    for name, text in texts.items():
        if len(text.encode("utf-8")) > PUBLIC_LIMIT:
            raise SystemExit(f"{name} exceeds the public size limit")
    private = [{"population": a.side.population, "label": a.side.label, "losses": a.losses,
                "withheld": {str(k): list(v) for k, v in a.shadow.withheld.items()},
                "unexplained": a.shadow.unexplained, "integrity": a.integrity} for a in analyses]
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
        stale = sorted(p.name for p in OUT.glob("losses-*.json") if p.name not in texts)
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
