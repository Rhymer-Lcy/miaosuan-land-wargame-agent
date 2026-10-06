"""Sprint 18 supplemental capability and opportunity census (``docs/SPRINT18_FRONTIER_RESET.md``).

    python scripts/s18_census.py freeze [--check]
    python scripts/s18_census.py run [--check]

``freeze`` pins every input of the census by SHA-256 in ``evaluation/s18-frontier-reset/inputs.json`` before the
census runs: the SDK archive (population S), the 8 replay-corpus games (H0, as pinned by the routing remediation's
corpus list), the record, timeline and timeline index of the 4 Sprint 12 head-to-head games (HH) and of the 5 Sprint 16
and 17 games against the inert control (HI), and the inventory of every completed game record (R) except the
prevalence study's, whose registered stop keeps its data unexamined. The record inventory itself is private (the
evaluation server's ``local/diagnostics/s18/record-inventory.txt``); the public file holds its digest and the record
counts by folder.

``run`` refuses unless every pinned file and the private record inventory match the committed ``inputs.json`` (the
live folder listing is not rebuilt, so records added by later sprints do not disturb it); it then computes the census of sections 6
and 7 (``evaluation/s18_census.py``) and writes the public aggregates ``evaluation/s18-frontier-reset/census.json``
(checked by the project's privacy sanitizer) and the private per-event rows
``local/diagnostics/s18/census-private.json.gz``. ``--check`` rebuilds and compares instead of writing. It runs on the
evaluation server, where the private inputs are.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import io
import json
import pickle
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "evaluation" / "s18-frontier-reset"
INPUTS = OUT_DIR / "inputs.json"
CENSUS = OUT_DIR / "census.json"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "s18"
DATA = LOCAL_EVAL / "baseline-v1-variance-study-1" / "data"
ARCHIVE = "local/source-archives/land_wargame_sdk.zip"
ARCHIVE_SHA256 = "ed4c9fc03cb6eb1e64821d2efbc61024d90735e3dc489dc7ffe0515e653ea725"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
FROZEN = REPO_ROOT / "evaluation" / "baseline-v2-candidate-shoot-target-reservation" / "manifest.json"
HH_FOLDER = "s12-v3-primary-1"
HH_GAMES = ("2130511121.H1.s12-v3-primary-1.p01", "2130511121.H2.s12-v3-primary-1.p02",
            "2130511121.H1.s12-v3-primary-1.p03", "2130511121.H2.s12-v3-primary-1.p04")
HI_GAMES = (("s16-v3-mechanism-capture-1", "1930331196.C3.s16-v3-mechanism-capture-1.p01"),
            ("s16-v3-mechanism-capture-1", "1930331196.C2.s16-v3-mechanism-capture-1.p02"),
            ("s16-v3-mechanism-capture-1", "2120531121.C3.s16-v3-mechanism-capture-1.p03"),
            ("s17-post-stage-v6-probe-1", "1930331196.C2.s17-post-stage-v6-probe-1.p01"),
            ("s17-post-stage-v6-probe-1", "2120531121.C3.s17-post-stage-v6-probe-1.p02"))
#: Record folders the census does not read, and why (section 5 of the registration).
EXCLUDED_RECORD_FOLDERS = {
    "baseline-v2-target-ownership-prevalence-1": "registered stop: its data stay unexamined",
}
V2 = "baseline-v2-candidate-shoot-target-reservation"
INERT = "inert-v0"
SCHEMA_INPUTS = "miaosuan-s18-inputs/1"
SCHEMA_CENSUS = "miaosuan-s18-census/1"
#: Published figures the census reproduces as consistency checks (Sprint 1 census, Sprint 5 audit and shadow).
PUBLISHED = {"H0 decisions": 33696, "H0 play decisions": 33680, "H0 v2 differs from recorded v0": 123,
             "H0 A2 orders": 234, "H0 A2 units": 49,
             "H0 decisions listing 03": 77, "H0 decisions listing 04": 256, "H0 decisions listing 07": 1687,
             "H0 decisions listing 09": 1}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def game_files(folder: str, game: str) -> Dict[str, str]:
    base = f"local/evaluation/{folder}"
    return {"record": f"{base}/games/{game}.json", "timeline": f"{base}/capture/{game}.timeline.pkl",
            "timeline_index": f"{base}/capture/{game}.timeline.json"}


def record_inventory(root: Path = REPO_ROOT) -> Tuple[List[str], Dict[str, int]]:
    """Every completed record outside the excluded folders, as ``relative path:sha256`` lines, and counts by folder."""
    lines: List[str] = []
    counts: Dict[str, int] = {}
    for folder in sorted(p for p in (root / "local" / "evaluation").iterdir() if p.is_dir()):
        if folder.name in EXCLUDED_RECORD_FOLDERS or not (folder / "games").is_dir():
            continue
        n = 0
        for path in sorted((folder / "games").glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") != "COMPLETED":
                continue
            lines.append(f"{path.relative_to(root).as_posix()}:{sha256(path)}")
            n += 1
        if n:
            counts[folder.name] = n
    return lines, counts


def freeze(root: Path = REPO_ROOT) -> Tuple[Dict[str, Any], str]:
    if sha256(root / ARCHIVE) != ARCHIVE_SHA256:
        raise SystemExit("the SDK archive does not match its pinned digest")
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    h0 = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        if sha256(root / entry["path"]) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        h0.append({"path": entry["path"], "sha256": entry["sha256"], "decisions": entry["decisions"]})
    hh = [{"game": g, **{k: {"path": p, "sha256": sha256(root / p)} for k, p in game_files(HH_FOLDER, g).items()}}
          for g in HH_GAMES]
    hi = [{"game": g, **{k: {"path": p, "sha256": sha256(root / p)} for k, p in game_files(f, g).items()}}
          for f, g in HI_GAMES]
    lines, counts = record_inventory(root)
    inventory = "\n".join(lines) + "\n"
    out = {"schema": SCHEMA_INPUTS, "study_id": "s18-frontier-reset",
           "S": {"path": ARCHIVE, "sha256": ARCHIVE_SHA256},
           "H0": {"corpus_list": "evaluation/routing-remediation-1/corpus.json", "games": h0},
           "HH": {"games": hh, "analysed_side": "the baseline-v2 seat"},
           "HI": {"games": hi, "use": "listing, starting-configuration and movement-timing figures only"},
           "R": {"records": len(lines), "records_by_folder": counts,
                 "inventory_sha256": hashlib.sha256(inventory.encode("utf-8")).hexdigest(),
                 "inventory_line": "<relative path>:<sha256 of the record file>, sorted, one per line",
                 "excluded_folders": dict(EXCLUDED_RECORD_FOLDERS)}}
    return out, inventory


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------------------------------------
# census run

def summary(values: Sequence[float]) -> Dict[str, Any]:
    from miaosuan_agent.evaluation import s18_census as sc
    return {"n": len(values), "median": sc.median(values), "p90": sc.quantile(values, 0.9),
            "max": max(values) if values else None}


def add_counts(total: Dict[str, Any], part: Mapping[str, Any]) -> None:
    """Sums integer leaves of nested dictionaries; list leaves are concatenated (summarised later)."""
    for key, value in part.items():
        if isinstance(value, Mapping):
            add_counts(total.setdefault(key, {}), value)
        elif isinstance(value, list):
            total.setdefault(key, []).extend(value)
        elif isinstance(value, bool):
            total[key] = total.get(key, 0) + int(value)
        elif isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value


def summarise_lists(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {k: summarise_lists(v) for k, v in sorted(node.items())}
    if isinstance(node, list):
        return summary(node)
    return node


def policy_class(policy: str) -> str:
    """The public label of a recorded policy. Candidate identities are not repeated in public files outside their
    owner-approved folders (the whitelist tests of Sprints 12 and 17), so every non-baseline policy is one class."""
    if policy == V2:
        return "baseline-v2"
    if policy == INERT:
        return "inert control"
    if policy.startswith("baseline-"):
        return "earlier baselines (v0, v1 and the v1 routing runtime candidate)"
    return "exploratory and tactical candidates"


class Census:
    def __init__(self) -> None:
        from miaosuan_agent.evaluation import s18_census as sc
        from miaosuan_agent.experiments import t9_batch as tb
        from miaosuan_agent.decision.routing import Router
        self.sc, self.tb, self.Router = sc, tb, Router
        self.routers: Dict[str, Any] = {}
        self.populations: Dict[str, Dict[str, Any]] = {}
        self.families: Dict[str, Dict[str, Any]] = collections.defaultdict(dict)
        self.scan: Dict[str, Dict[str, Any]] = collections.defaultdict(dict)
        self.sides: List[Dict[str, Any]] = []
        self.integrity: Dict[str, Any] = {}
        self.private: Dict[str, Any] = {"events": [], "sides": []}
        self.hexes: set = set()
        self.ids: set = set()

    def router(self, scenario: str, map_id: str) -> Any:
        from miaosuan_agent import sdk_data
        from miaosuan_agent.boundary import MoveCosts
        key = f"{scenario}:{map_id}"
        if key not in self.routers:
            costs = MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario / "Data", scenario, map_id).cost)
            self.routers[key] = self.Router(costs)
        return self.routers[key]

    def costs(self, scenario: str, map_id: str) -> Any:
        return self.router(scenario, map_id).costs

    # -- per side ------------------------------------------------------------------------------
    def side(self, population: str, game: Any, faction: int, router: Any, analyse_threat: bool) -> Dict[str, Any]:
        sc = self.sc
        frames = game.sides[faction]
        for f in frames:
            for u in list(f.own.values()) + list(f.enemies.values()) + list(f.aboard.values()):
                if sc.as_int(u.get("cur_hex")) is not None:
                    self.hexes.add(u["cur_hex"])
                self.ids.add(u["obj_id"])
            self.hexes.update(c for c in f.flags if sc.as_int(c) is not None)
        rows = sc.event_rows(game, faction) if analyse_threat else []
        fam: Dict[str, Any] = {
            "T2": sc.t2(game, faction, rows, lambda f: router, self.tb.path_times),
            "T5": {"listings": sc.listing_counts(frames, (9, 17)),
                   "guide_capable_units_at_first_play": sum(1 for u in next((f.own for f in frames if f.stage == 2), {}).values()
                                                           if u.get("guide_ability"))},
            "T8": {"listings": sc.listing_counts(frames, (14, 15, 16, 18, 19, 20))},
        }
        scan: Dict[str, Any] = {"N1": {"listings": sc.listing_counts(frames, range(1, 21)),
                                       "issued_by_baseline_v2": sc.issued_counts(frames)}}
        if analyse_threat:
            fam["T7-C"] = sc.t7c(game, faction, rows)
            fam["T6"] = sc.t6(game, faction, rows)
            fam["T3"] = sc.t3(game, faction, rows)
            scan.update({"N2": sc.suppression(game, faction, rows), "N3": sc.fire_choice(game, faction),
                         "N4": sc.objective_defence(game, faction),
                         "N5": sc.idle(game, faction), "N6": {"first_ownership_steps": sc.first_ownership_steps(game, faction)},
                         "N7": sc.close_combat(game, faction, rows), "N8": sc.aircraft(rows), "N9": sc.stacking(rows),
                         "distances_by_judgement_type": sc.distances_by_type(rows)})
            for r in rows:
                self.private["events"].append({"population": population, "game": game.game, "faction": faction, **r})
        flags = {
            "T7-C": fam.get("T7-C", {}).get("orders", 0) > 0,
            "T2": any(k.startswith(("decisions_3", "decisions_4")) and v > 0 for k, v in fam["T2"].get("listings", {}).items()),
            "T6": fam.get("T6", {}).get("moving_ground_seen_before", 0) > 0,
            "T3": fam.get("T3", {}).get("events_attacker_unseen_but_seen_within_window", 0) > 0,
            "T5": fam["T5"]["listings"].get("decisions_09", 0) > 0,
            "T8": any(fam["T8"]["listings"].get(f"decisions_{t:02d}", 0) > 0 for t in (16, 18, 19, 20)),
        }
        if analyse_threat:
            n2 = scan["N2"]
            flags.update({
                "scan remove-suppression listed while suppressed": n2["remove_suppression_unit_decisions"].get("keep_1", 0) > 0,
                "scan infantry suppressed at least once": n2["onsets_by_class"].get("infantry", 0) > 0,
                "scan infantry hit while already suppressed": n2["infantry_events_already_suppressed"] > 0,
                "scan shot with two or more targets": scan["N3"]["shots_with_two_or_more_targets"] > 0,
                "scan objective lost after being held": scan["N4"]["objective_losses"] > 0,
                "scan idle ground unit with an enemy visible": any(k.endswith("_enemy_visible") and v > 0 for k, v in scan["N5"].items()),
                "scan unit in close combat": scan["N7"]["unit_decisions_in_close_combat"] > 0,
                "scan aircraft damaged": scan["N8"]["events"] > 0,
                "scan stacked ground unit damaged": scan["N9"]["ground_events_victim_stacked"] > 0,
                "scan ground unit lost with a move path": fam["T6"]["ground_units_lost_with_a_move_path"] > 0,
            })
        out = {"population": population, "game": game.game, "faction": faction, "families": fam, "scan": scan,
               "flags": flags}
        self.private["sides"].append(out)
        return out

    def accumulate(self, population: str, side: Mapping[str, Any]) -> None:
        for name, values in side["families"].items():
            add_counts(self.families[name].setdefault(population, {}), values)
        for name, values in side["scan"].items():
            add_counts(self.scan[name].setdefault(population, {}), values)
        if population == "H0":
            self.sides.append(side["flags"])

    # -- H0 ------------------------------------------------------------------------------------
    def h0(self, inputs: Mapping[str, Any]) -> None:
        from miaosuan_agent import typed_json
        from miaosuan_agent.boundary import Observation, Origin
        from miaosuan_agent.experiments import t7_idle_concealment as sh
        sc = self.sc
        decisions = play = differs = orders = 0
        units_ordered: set = set()
        for entry in inputs["H0"]["games"]:
            with gzip.open(REPO_ROOT / entry["path"], "rt", encoding="utf-8") as handle:
                header = json.loads(next(handle))
                router = self.router(header["scenario_id"], header["map_id"])
                state: Dict[int, Dict[str, Any]] = {}
                frames: Dict[int, Dict[Any, Any]] = collections.defaultdict(dict)
                raw_judge: Dict[Any, List[Any]] = collections.defaultdict(list)
                for line in handle:
                    row = json.loads(line)
                    seat, faction = row["seat"], row["faction"]
                    s = state.setdefault(seat, {"shadow": sh.IdleConcealmentShadow(router.costs), "m": sh.ShadowMemory(),
                                                "faction": faction})
                    raw = typed_json.decode(row["observation"])
                    decision = s["shadow"].decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, s["m"])
                    s["m"] = decision.memory
                    v2 = [dict(a) for a in decision.baseline.actions]
                    decisions += 1
                    play += (raw.get("time") or {}).get("stage") == 2
                    differs += v2 != [dict(a) for a in row["actions"]]
                    added = [a["obj_id"] for a in decision.added]
                    orders += len(added)
                    units_ordered.update((header["game_id"], seat, o) for o in added)
                    frames[faction][row["step"]] = sc.frame_from_raw(0, raw, faction, v2, added)
                    raw_judge[row["step"]].append(raw.get("judge_info") or [])
            steps = sorted(set(frames[0]) | set(frames[1]))
            if set(frames[0]) != set(frames[1]):
                raise SystemExit(f"{header['game_id']}: the two seats decided at different steps")
            collector = sc.EventCollector()
            sides = {0: [], 1: []}
            for i, step in enumerate(steps):
                for faction in (0, 1):
                    f = frames[faction][step]
                    f.k = i
                    sides[faction].append(f)
                for records in raw_judge[step]:
                    collector.add(i, records)
            game = sc.Game("H0", header["game_id"], str(header["scenario_id"]), sides, collector.events, (0, 1))
            for faction in (0, 1):
                self.accumulate("H0", self.side("H0", game, faction, router, True))
        self.populations["H0"] = {"games": len(inputs["H0"]["games"]), "decisions": decisions, "play_decisions": play,
                                  "scenario_sides": 2 * len(inputs["H0"]["games"])}
        self.integrity.update({"H0 decisions": decisions, "H0 play decisions": play,
                               "H0 v2 differs from recorded v0": differs, "H0 A2 orders": orders,
                               "H0 A2 units": len(units_ordered)})

    # -- timelines -----------------------------------------------------------------------------
    def timeline_game(self, population: str, entry: Mapping[str, Any]) -> None:
        from miaosuan_agent.boundary import Observation, Origin
        from miaosuan_agent.experiments import t7_idle_concealment as sh
        sc = self.sc
        record = json.loads((REPO_ROOT / entry["record"]["path"]).read_text(encoding="utf-8"))
        router = self.router(str(record["scenario_id"]), str(record["map_id"]))
        with (REPO_ROOT / entry["timeline"]["path"]).open("rb") as handle:
            windows = pickle.load(handle)
        samples = sorted(windows["samples"], key=lambda s: s["k"])
        if [s["k"] for s in samples] != list(range(len(samples))):
            raise SystemExit(f"{entry['game']}: the timeline does not hold one snapshot per decision")
        seats = {s["seat"]: s for s in record["seats"]}
        v2_seats = [seat for seat, s in seats.items() if s["policy"] == V2]
        active = [seat for seat, s in seats.items() if s["policy"] != INERT]
        analysed = v2_seats if population == "HH" else active
        sides: Dict[int, List[Any]] = {0: [], 1: []}
        collector = sc.EventCollector()
        shadow = {seat: (sh.IdleConcealmentShadow(router.costs), [sh.ShadowMemory()]) for seat in v2_seats}
        equal = compared = 0
        for i, sample in enumerate(samples):
            for seat_key, snap in sample["seats"].items():
                seat = int(seat_key)
                faction = seats[seat]["faction"]
                raw = pickle.loads(snap["observation"])
                actions = snap.get("submitted") or []
                added: List[int] = []
                if seat in shadow:
                    policy, memory = shadow[seat]
                    decision = policy.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memory[0])
                    memory[0] = decision.memory
                    added = [a["obj_id"] for a in decision.added]
                    compared += 1
                    equal += [dict(a) for a in decision.baseline.actions] == [dict(a) for a in actions]
                sides[faction].append(sc.frame_from_raw(i, raw, faction, actions, added))
            collector.add(i, (pickle.loads(sample["global"]).get("judge_info") or []))
        game = sc.Game(population, entry["game"], str(record["scenario_id"]), sides, collector.events,
                       tuple(seats[s]["faction"] for s in analysed))
        for seat in analysed:
            self.accumulate(population, self.side(population, game, seats[seat]["faction"], router, population == "HH"))
        key = f"{population} baseline-v2 reconstruction equal"
        prior = self.integrity.get(key, [0, 0])
        self.integrity[key] = [prior[0] + equal, prior[1] + compared]
        pop = self.populations.setdefault(population, {"games": 0, "decisions": 0, "analysed_sides": 0})
        pop["games"] += 1
        pop["decisions"] += len(samples)
        pop["analysed_sides"] += len(analysed)

    # -- S ---------------------------------------------------------------------------------------
    def scenarios(self) -> Dict[str, Any]:
        frozen = {str(s["scenario_id"]) for s in json.loads(FROZEN.read_text(encoding="utf-8"))["scenarios"]}
        presence = collections.Counter()
        frozen_presence = collections.Counter()
        aboard = collections.Counter()
        count = {"all": 0, "frozen": 0}
        with zipfile.ZipFile(REPO_ROOT / ARCHIVE) as outer:
            (name,) = [n for n in outer.namelist() if n.lower().endswith("data.zip")]
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                for member in sorted(n for n in inner.namelist() if "/scenarios/" in n and n.endswith(".json")):
                    scenario = json.loads(inner.read(member))
                    ops = scenario["operators"]
                    codes = {(u.get("type"), u.get("sub_type")) for u in ops}
                    infantry = [u for u in ops if u.get("type") == 1]
                    preds = {
                        "T2 infantry and infantry fighting vehicle": (1, 2) in codes and (2, 1) in codes,
                        "T3 any unit": bool(ops), "T6 any unit": bool(ops),
                        "T5 guide-capable unit and infantry fighting vehicle": any(u.get("guide_ability") for u in ops) and (2, 1) in codes,
                        "T7-C ground vehicle or infantry": any(u.get("type") in (1, 2) for u in ops),
                        "T8 helicopter (3.6) or transport helicopter (3.8)": (3, 6) in codes or (3, 8) in codes,
                        "T8 fortification (type 4)": any(c[0] == 4 for c in codes),
                        "T8 mine layer (2.13)": (2, 13) in codes,
                        "TO-1 any unit": bool(ops),
                        "scan infantry (1.2)": (1, 2) in codes,
                        "scan aircraft (type 3)": any(c[0] == 3 for c in codes),
                        "scan infantry starting on board": any(u.get("on_board") for u in infantry),
                    }
                    is_frozen = str(scenario["scenario_id"]) in frozen
                    count["all"] += 1
                    count["frozen"] += is_frozen
                    for key, value in preds.items():
                        presence[key] += bool(value)
                        frozen_presence[key] += bool(value) and is_frozen
                    for u in infantry:
                        aboard["infantry units on board at start" if u.get("on_board") else "infantry units on the ground at start"] += 1
        return {"scenarios": count, "presence_all": dict(sorted(presence.items())),
                "presence_frozen": dict(sorted(frozen_presence.items())), "infantry_start": dict(sorted(aboard.items()))}

    # -- R ---------------------------------------------------------------------------------------
    def records(self) -> Dict[str, Any]:
        inventory = (PRIVATE / "record-inventory.txt").read_text(encoding="utf-8").splitlines()
        issued: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
        seats_by_policy = collections.Counter()
        composition: Dict[str, Dict[str, List[float]]] = collections.defaultdict(lambda: collections.defaultdict(list))
        identity = collections.Counter()
        for line in inventory:
            rel, digest = line.rsplit(":", 1)
            path = REPO_ROOT / rel
            if sha256(path) != digest:
                raise SystemExit(f"{rel} changed after the freeze")
            record = json.loads(path.read_text(encoding="utf-8"))
            seats = record.get("seats") or []
            for s in seats:
                seats_by_policy[policy_class(s["policy"])] += 1
                for t, n in (s.get("actions_by_type") or {}).items():
                    issued[policy_class(s["policy"])][f"type_{int(t):02d}" if str(t).isdigit() else f"type_{t}"] += n
            policies = {s["faction"]: s["policy"] for s in seats}
            scores = record.get("final_scores") or {}
            for s in seats:
                if s["policy"] != V2:
                    continue
                other = policies.get(1 - s["faction"])
                if other is None or other == INERT:
                    continue
                kind = "mirror" if other == V2 else "against another acting policy"
                colour = "red" if s["faction"] == 0 else "blue"
                values = {k: scores.get(f"{colour}_{k}") for k in ("occupy", "attack", "remain", "remain_max", "total")}
                if not all(isinstance(v, (int, float)) for v in values.values()):
                    identity["unreadable"] += 1
                    continue
                for k, v in values.items():
                    composition[kind][k].append(v)
                if values["remain_max"]:
                    composition[kind]["remain_lost_share"].append(round(1 - values["remain"] / values["remain_max"], 4))
                identity["total equals occupy + attack + remain" if values["total"] == values["occupy"] + values["attack"] + values["remain"]
                         else "total differs from occupy + attack + remain"] += 1
        return {"records": len(inventory), "seats_by_policy": dict(sorted(seats_by_policy.items())),
                "issued_action_types_by_policy": {p: dict(sorted(c.items())) for p, c in sorted(issued.items())},
                "baseline_v2_against_acting_opponents": {k: {m: summary(v) for m, v in sorted(d.items())}
                                                          for k, d in sorted(composition.items())},
                "score_identity": dict(sorted(identity.items()))}

    # -- assembly --------------------------------------------------------------------------------
    def build(self, inputs: Mapping[str, Any]) -> Dict[str, Any]:
        s = self.scenarios()
        self.h0(inputs)
        for entry in inputs["HH"]["games"]:
            self.timeline_game("HH", entry)
        for entry in inputs["HI"]["games"]:
            self.timeline_game("HI", entry)
        h0_listing = (self.scan["N1"].get("H0") or {}).get("listings", {})
        for t in ("03", "04", "07", "09"):
            self.integrity[f"H0 decisions listing {t}"] = h0_listing.get(f"decisions_{t}", 0)
        checks = {key: {"published": value, "census": self.integrity.get(key), "equal": self.integrity.get(key) == value}
                  for key, value in PUBLISHED.items()}
        hh_equal = self.integrity.get("HH baseline-v2 reconstruction equal", [0, 0])
        checks["HH baseline-v2 reconstruction equal"] = {"published": hh_equal[1], "census": hh_equal[0],
                                                         "equal": hh_equal[0] == hh_equal[1] and hh_equal[1] > 0}
        n_sides = len(self.sides)
        opportunity = {k: sum(1 for f in self.sides if f.get(k)) for k in sorted({k for f in self.sides for k in f})}
        return {"schema": SCHEMA_CENSUS, "study_id": "s18-frontier-reset",
                "inputs_sha256": hashlib.sha256(INPUTS.read_bytes()).hexdigest(),
                "populations": self.populations, "consistency": checks, "S": s,
                "families": summarise_lists(self.families), "scan": summarise_lists(self.scan),
                "records": self.records(),
                "opportunity_sides": {"of": n_sides, "sides_with_opportunity": opportunity},
                "note": "aggregates only; H0 figures are baseline-v2 decisions on baseline-v0 trajectories; "
                        "HH is four games in one scenario; HI is against the inert control"}


def input_problems(committed: Mapping[str, Any], root: Path = REPO_ROOT) -> List[str]:
    """Every pinned file against its committed digest, and the private record inventory against its committed digest.
    The live folder listing is not rebuilt, so later records do not disturb the check (each listed record's own
    digest is checked when it is read)."""
    problems = []
    if sha256(root / committed["S"]["path"]) != committed["S"]["sha256"]:
        problems.append(committed["S"]["path"])
    for entry in committed["H0"]["games"]:
        if sha256(root / entry["path"]) != entry["sha256"]:
            problems.append(entry["path"])
    for population in ("HH", "HI"):
        for entry in committed[population]["games"]:
            for kind in ("record", "timeline", "timeline_index"):
                if sha256(root / entry[kind]["path"]) != entry[kind]["sha256"]:
                    problems.append(entry[kind]["path"])
    inventory = PRIVATE / "record-inventory.txt"
    if not inventory.exists() or hashlib.sha256(inventory.read_bytes()).hexdigest() != committed["R"]["inventory_sha256"]:
        problems.append("record inventory")
    return problems


def mask_numbers(node: Any) -> Any:
    """The same structure with every numeric leaf replaced by ``None``."""
    if isinstance(node, Mapping):
        return {k: mask_numbers(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [mask_numbers(v) for v in node]
    if isinstance(node, (int, float)) and not isinstance(node, bool):
        return None
    return node


def public_problems(data: Any, private_values: Any) -> List[str]:
    """The project's sanitizer (``s12_screen.privacy_problems``): forbidden keys anywhere, and the private hexes and unit
    identifiers as keys or as words of strings. Numeric leaves are aggregates by construction and are not compared:
    hexes and unit identifiers overlap the range of ordinary counts (implementation reading, disclosed)."""
    from miaosuan_agent.evaluation.s12_screen import privacy_problems
    return privacy_problems(data) + privacy_problems(mask_numbers(data), sorted(private_values))


def run(check: bool) -> int:
    committed = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = input_problems(committed)
    if problems:
        print("inputs differ from the committed inputs.json; refusing to run:", problems[:5])
        return 1
    census = Census()
    data = census.build(committed)
    problems = public_problems(data, census.hexes | census.ids)
    if problems:
        print("privacy problems:", problems[:10])
        return 1
    if not all(c["equal"] for c in data["consistency"].values()):
        print("consistency checks fail:", {k: v for k, v in data["consistency"].items() if not v["equal"]})
        return 1
    text = dump(data)
    private = gzip.compress(json.dumps(census.private, sort_keys=True, default=str).encode("utf-8"), mtime=0)
    if check:
        same = CENSUS.exists() and CENSUS.read_text(encoding="utf-8") == text
        print("census identical" if same else "MISMATCH")
        return 0 if same else 1
    CENSUS.write_text(text, encoding="utf-8", newline="\n")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    (PRIVATE / "census-private.json.gz").write_bytes(private)
    print(f"wrote {CENSUS.relative_to(REPO_ROOT).as_posix()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "run"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.command == "freeze":
        data, inventory = freeze()
        text = dump(data)
        if args.check:
            same = INPUTS.exists() and INPUTS.read_text(encoding="utf-8") == text
            print("inputs identical" if same else "MISMATCH")
            return 0 if same else 1
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        INPUTS.write_text(text, encoding="utf-8", newline="\n")
        PRIVATE.mkdir(parents=True, exist_ok=True)
        (PRIVATE / "record-inventory.txt").write_text(inventory, encoding="utf-8", newline="\n")
        print(f"wrote {INPUTS.relative_to(REPO_ROOT).as_posix()} ({data['R']['records']} records)")
        return 0
    return run(args.check)


if __name__ == "__main__":
    sys.exit(main())
