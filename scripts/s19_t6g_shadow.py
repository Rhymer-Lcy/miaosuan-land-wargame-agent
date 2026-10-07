"""Sprint 19 T6-G offline shadow study (``docs/SPRINT19_T6G_SHADOW.md``). Offline only: no engine session.

    python scripts/s19_t6g_shadow.py freeze [--check]
    python scripts/s19_t6g_shadow.py smoke never|exposure
    python scripts/s19_t6g_shadow.py run [--check]

``freeze`` writes ``evaluation/s19-t6g-shadow/protocol.json`` (the frozen gate parameters, the registered thresholds,
the disposition order and the normalised SHA-256 of every frozen source file) and ``inputs.json`` (the Sprint 18
H0 and HH pins, copied from Sprint 18's committed ``inputs.json``, which is itself pinned with ``census.json``).

``smoke`` is the pre-freeze known-answer run on the real inputs; it prints no T6-G figure. ``never`` applies the gate
with an empty route prefix (expected: nothing dropped); ``exposure`` replaces the condition with Sprint 18's
threat-exposure predicate, with no hold limit and no cooldown (expected: the dropped moves equal Sprint 18's
threat-exposed orders, 230 in H0 and 200 in HH).

``run`` refuses unless every input and every frozen source matches its pin. It loads H0 and HH with Sprint 18's
census loaders (``scripts/s18_census.py``, unchanged), reproduces Sprint 18's T6 and first-ownership figures (fidelity,
section 8; any difference ends the run as REPLAY_INVALID), applies the frozen gate to every side, and writes the public
aggregates (``fidelity.json``, ``shadow.json``, ``certificates.json``, ``objectives.json``, ``disposition.json``) and the
private rows (``local/diagnostics/s19/shadow-private.json.gz``). ``--check`` rebuilds and compares instead of
writing. It runs on the evaluation server, where the private inputs are.
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
from typing import Any, Dict, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT = REPO_ROOT / "evaluation" / "s19-t6g-shadow"
PROTOCOL = OUT / "protocol.json"
INPUTS = OUT / "inputs.json"
S18 = REPO_ROOT / "evaluation" / "s18-frontier-reset"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s19"
SCHEMA_PROTOCOL = "miaosuan-s19-protocol/1"
SCHEMA_INPUTS = "miaosuan-s19-inputs/1"
SCHEMA_RESULTS = "miaosuan-s19-results/1"
#: Frozen source files (normalised SHA-256: carriage returns before line feeds removed).
SOURCES = ("src/miaosuan_agent/experiments/t6_threat_entry_gate.py",
           "src/miaosuan_agent/evaluation/s19_t6g.py",
           "scripts/s19_t6g_shadow.py",
           "src/miaosuan_agent/evaluation/s18_census.py",
           "scripts/s18_census.py",
           "src/miaosuan_agent/evaluation/t7_candidates.py",
           "src/miaosuan_agent/evaluation/t7_visibility.py")
#: Sprint 18 figures the replay must reproduce exactly (``census.json``; section 8).
ANCHORS = {"H0 threat-exposed move orders": ("H0", "threat_exposed_orders", 230),
           "H0 threat-exposed orders followed by mover damage within 300 steps": ("H0", "threat_exposed_then_damaged", 88),
           "H0 damage events on moving ground units": ("H0", "moving_ground_events", 124),
           "H0 of those, attacker seen before": ("H0", "moving_ground_seen_before", 120),
           "H0 baseline-v2 move orders": ("H0", "move_orders", 509),
           "HH threat-exposed move orders": ("HH", "threat_exposed_orders", 200),
           "HH threat-exposed orders followed by mover damage within 300 steps": ("HH", "threat_exposed_then_damaged", 101),
           "HH damage events on moving ground units": ("HH", "moving_ground_events", 117),
           "HH of those, attacker seen before": ("HH", "moving_ground_seen_before", 117),
           "HH baseline-v2 move orders": ("HH", "move_orders", 416)}
EVENT_TOTALS = {"H0": 205, "HH": 158}
INTEGRITY = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123}


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
    from miaosuan_agent.experiments import t6_threat_entry_gate as tg
    from miaosuan_agent.evaluation import s19_t6g as st
    return {
        "schema": SCHEMA_PROTOCOL, "study_id": "s19-t6g-shadow", "engine_sessions": 0,
        "gate": {"identity": tg.GATE_ID, "route_prefix": tg.ROUTE_PREFIX, "hold_limit_steps": tg.HOLD_LIMIT,
                 "cooldown_steps": tg.COOLDOWN, "release_reasons": list(tg.RELEASE_REASONS) + [st.OPEN_AT_END],
                 "condition_reasons": list(tg.CHECK_REASONS),
                 "range_source": "evaluation/t7_candidates.weapon_range: longest published direct-fire range of the "
                                 "enemy's carried weapons against the mover's class (type 1 personnel, type 2 vehicles)",
                 "distance": "evaluation/t7_visibility.hex_distance"},
        "opportunity": {"unit": "first gate of a hold episode, every recorded decision of the side-game",
                        "minimum_per_hh_side_game": st.OPPORTUNITY_MIN, "hh_side_games": st.HH_SIDE_GAMES},
        "capturer": {"definition": "own ground unit standing on the objective hex at the side's first decision whose "
                                   "flag reads its own colour",
                     "metric": "pooled over the HH side-games, distinct gated units de-duplicated within a side-game",
                     "fails_when": "participants * 2 > gated (strictly more than one half)"},
        "damage_windows_steps": list(st.WINDOWS), "episode_reference_after_release_steps": st.AFTER_RELEASE,
        "dispositions_first_match": list(st.DISPOSITIONS),
        "anchors": {k: v[2] for k, v in ANCHORS.items()},
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
    return {"schema": SCHEMA_INPUTS, "study_id": "s19-t6g-shadow",
            "sprint18_inputs": {"path": "evaluation/s18-frontier-reset/inputs.json",
                                "sha256": sha256(S18 / "inputs.json")},
            "sprint18_census": {"path": "evaluation/s18-frontier-reset/census.json",
                                "sha256": sha256(S18 / "census.json")},
            "H0": s18_inputs["H0"], "HH": s18_inputs["HH"],
            "not_used": "HI, S and R of Sprint 18, every other capture, BOKE-2026 data and the stopped 360-game "
                        "prevalence corpus"}


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
# loading H0 and HH through Sprint 18's census, with the shadow attached to each side

def side_label(population: str, game: Any, faction: int) -> str:
    colour = "red" if faction == 0 else "blue"
    if population == "HH":
        return f"HH {game.game.rsplit('.', 1)[-1]} baseline-v2 {colour}"
    return f"H0 {game.scenario} {colour}"


def make_loader(rules: Any) -> Any:
    from miaosuan_agent.evaluation import s18_census as sc
    from miaosuan_agent.evaluation import s19_t6g as st
    base = census_script().Census

    class Loader(base):
        """Sprint 18's census, unchanged, with each analysed side also passed through the T6-G shadow."""

        def __init__(self) -> None:
            super().__init__()
            self.pending: Dict[Any, Any] = {}
            self.values: Dict[str, Dict[Any, Any]] = {}
            self.analyses: Dict[str, List[Any]] = {"H0": [], "HH": []}
            self.values_by_label: Dict[str, Dict[Any, Any]] = {}
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
                label = side_label(population, game, faction)
                values = self.values.get(game.game, {})
                self.values_by_label[label] = values
                self.analyses[population].append(st.analyse_side(population, label, game, faction, values, rules))
            return out

    return Loader()


def load(committed: Mapping[str, Any], rules: Any) -> Any:
    loader = make_loader(rules)
    loader.h0(committed)
    for entry in committed["HH"]["games"]:
        loader.timeline_game("HH", entry)
    return loader


# ------------------------------------------------------------------------------------------------
# fidelity

def fidelity(loader: Any) -> Dict[str, Any]:
    census = json.loads((S18 / "census.json").read_text(encoding="utf-8"))
    script = census_script()
    families = script.summarise_lists(loader.families)
    scan = script.summarise_lists(loader.scan)
    anchors = {}
    for name, (pop, key, value) in ANCHORS.items():
        got = families.get("T6", {}).get(pop, {}).get(key)
        anchors[name] = {"sprint18": value, "replay": got, "equal": got == value
                         and census["families"]["T6"][pop][key] == value}
    for pop, value in EVENT_TOTALS.items():
        got = sum(families.get("T6", {}).get(pop, {}).get("events_by_victim_state", {}).values())
        anchors[f"{pop} damage events"] = {"sprint18": value, "replay": got, "equal": got == value}
    for name, value in INTEGRITY.items():
        got = loader.integrity.get(name)
        anchors[name] = {"sprint18": value, "replay": got, "equal": got == value}
    hh = loader.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
    anchors["HH baseline-v2 reconstruction equal to the recorded seat"] = {
        "sprint18": 11524, "replay": hh[0], "equal": hh[0] == hh[1] == 11524}
    blocks = {f"T6 {pop} block equal to census.json": families.get("T6", {}).get(pop) == census["families"]["T6"][pop]
              for pop in ("H0", "HH")}
    blocks.update({f"first ownership {pop} equal to census.json": scan.get("N6", {}).get(pop) == census["scan"]["N6"][pop]
                   for pop in ("H0", "HH")})
    sides = {pop: len(v) for pop, v in loader.analyses.items()}
    shadow_integrity = {a.label: all(a.integrity.values()) for pop in ("H0", "HH") for a in loader.analyses[pop]}
    ok = (all(a["equal"] for a in anchors.values()) and all(blocks.values()) and sides == {"H0": 16, "HH": 4}
          and all(shadow_integrity.values()))
    return {"anchors": anchors, "blocks": blocks, "side_games": sides,
            "shadow_integrity_by_side_game": shadow_integrity, "ok": ok}


# ------------------------------------------------------------------------------------------------
# smoke (pre-freeze known-answer runs; prints no T6-G figure)

def exposure_condition(mover: Optional[Mapping[str, Any]], route: Any, enemies: Any) -> Any:
    """Sprint 18's ``threat_exposed`` restated as a gate condition (the mover's hex or any of the first five route
    hexes inside a visible enemy's range); used only by ``smoke exposure``."""
    from miaosuan_agent.evaluation import s18_census as sc
    from miaosuan_agent.experiments import t6_threat_entry_gate as tg
    from miaosuan_agent.evaluation.t7_visibility import hex_distance
    if mover is None or sc.as_int(mover.get("cur_hex")) is None:
        return tg.EntryCheck(False, "unreadable_mover")
    hexes = tuple([mover["cur_hex"]] + [h for h in list(route or ())[:sc.THREAT_PATH_HEXES] if sc.as_int(h) is not None])
    threats = tg.qualifying_threats(enemies, mover.get("type"))
    causing = tuple(t for t in threats if any(hex_distance(h, t.hex) <= t.reach for h in hexes))
    if not causing:
        return tg.EntryCheck(False, "no_route_entry", threats)
    first = min(i for i, h in enumerate(hexes) if any(hex_distance(h, t.hex) <= t.reach for t in threats))
    return tg.EntryCheck(True, "eligible", threats, causing, hexes, first)


def smoke(mode: str, committed: Mapping[str, Any]) -> int:
    from miaosuan_agent.experiments import t6_threat_entry_gate as tg
    if mode == "never":
        rules = tg.GateRules(route_prefix=0)
    else:
        rules = tg.GateRules(hold_limit=10 ** 9, cooldown=0, condition=exposure_condition)
    started = time.time()
    loader = load(committed, rules)
    fid = fidelity(loader)
    print("fidelity ok" if fid["ok"] else "FIDELITY FAILS", {k: v["replay"] for k, v in fid["anchors"].items()
                                                             if not v["equal"]})
    for pop in ("H0", "HH"):
        analyses = loader.analyses[pop]
        dropped = sum(a.shadow.gated_decisions for a in analyses)
        starts = sum(a.shadow.route_starts_at_current_hex for a in analyses)
        integrity = all(all(a.integrity.values()) for a in analyses)
        print(f"{pop}: side-games {len(analyses)}, dropped moves {dropped}, routes starting at the current hex {starts}, "
              f"integrity {'ok' if integrity else 'FAILS'}")
    print(f"seconds {time.time() - started:.0f}")
    return 0


# ------------------------------------------------------------------------------------------------
# run

def build(committed: Mapping[str, Any]) -> Tuple[Dict[str, str], bytes]:
    from miaosuan_agent.evaluation import s19_t6g as st
    from miaosuan_agent.experiments import t6_threat_entry_gate as tg
    loader = load(committed, tg.FROZEN)
    fid = fidelity(loader)
    head = {"schema": SCHEMA_RESULTS, "study_id": "s19-t6g-shadow",
            "protocol_sha256": sha256(PROTOCOL), "inputs_sha256": sha256(INPUTS)}
    public: Dict[str, Any] = {"fidelity.json": {**head, **fid}}
    if not fid["ok"]:
        public["disposition.json"] = {**head, **st.disposition(False, [], 0, 0)}
    else:
        hh, h0 = loader.analyses["HH"], loader.analyses["H0"]
        cap = st.capturer_fraction(hh)
        public["shadow.json"] = {
            **head,
            "evidence_boundary": "before a side-game's first gate the candidate equals baseline-v2; the first gate is "
                                 "an action-level fact; later gates are opportunity diagnostics on off-policy "
                                 "recorded states. H0 states are baseline-v0 trajectories throughout.",
            "HH": {"sides": [st.public_side(a) for a in hh], "pooled": st.pooled(hh)},
            "H0": {"sides": [st.public_side(a) for a in h0], "pooled": st.pooled(h0)}}
        public["certificates.json"] = {**head, "HH": [st.certificate(a, loader.values_by_label[a.label]) for a in hh]}
        public["objectives.json"] = {**head, "HH": st.objective_timing(hh, loader.values_by_label)}
        public["disposition.json"] = {**head, **st.disposition(True, st.gate_episode_counts(hh),
                                                                 cap["participants"], cap["gated"])}
    private_values = loader.hexes | loader.ids
    for name, data in public.items():
        problems = st.public_problems(data, private_values)
        if problems:
            raise SystemExit(f"privacy problems in {name}: {problems[:10]}")
    texts = {name: dump(data) for name, data in public.items()}
    private = {pop: [{"label": a.label, "episodes": a.episodes, "exposed_not_gated": a.exposed_not_gated,
                      "ownerships": [{**o, "participants": sorted(o["participants"], key=str)} for o in a.ownerships],
                      "gated": sorted(a.gated, key=str), "integrity": a.integrity}
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
        same &= (PRIVATE / "shadow-private.json.gz").exists() and (PRIVATE / "shadow-private.json.gz").read_bytes() == blob
        print("shadow identical" if same else "MISMATCH")
        return 0 if same else 1
    for name, text in texts.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "shadow-private.json.gz").write_bytes(blob)
    print("wrote", ", ".join(sorted(texts)))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "run"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    p = sub.add_parser("smoke")
    p.add_argument("mode", choices=("never", "exposure"))
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
        return smoke(args.mode, inputs())
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
