"""Offline search for an E3b configuration (``t7-e3b-search-1``, ``docs/T7_E3B_SEARCH.md``).

    python scripts/t7_e3b_search.py freeze      # write evaluation/t7-e3b-search-1/inputs.json (once, before the search)
    python scripts/t7_e3b_search.py validate    # the known-answer test on the excluded candidate seats
    python scripts/t7_e3b_search.py search      # the search over the frozen eligible datasets
    python scripts/t7_e3b_search.py decide      # the decision rule, after scripts/t7_e3b_crosscheck.py
    python scripts/t7_e3b_search.py check       # rebuild validation, search and decision; compare byte for byte

No engine. Every input is read through the frozen selection ``inputs.json`` (the search refuses when a named file is
missing or changed and reads no other record). Private inputs on the evaluation server: the captures and records named
there, the replay corpus, the staged scenario data and Sprint 5's private post-hoc rows (the two H0 leads). Public
outputs in ``evaluation/t7-e3b-search-1/`` (aggregates and sanitised certificates, no unit identifiers or hexes);
private outputs with identifiers in ``local/diagnostics/e3b/``.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import hashlib
import json
import pickle
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.evaluation import t7_audit as ta  # noqa: E402
from miaosuan_agent.evaluation import t7_candidates as tc  # noqa: E402
from miaosuan_agent.evaluation import t7_e3b as te  # noqa: E402
from miaosuan_agent.evaluation import t7_probe_metrics as tm  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t7_concealment as cand  # noqa: E402
from miaosuan_agent.experiments import t7_idle_concealment as sh  # noqa: E402
from miaosuan_agent.experiments.deployment_split import DeploymentSplitPolicy  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

STUDY = "t7-e3b-search-1"
SCHEMA = "miaosuan-t7-e3b-search/1"
OUT = REPO_ROOT / "evaluation" / STUDY
INPUTS = OUT / "inputs.json"
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "e3b"
LOCAL_EVAL = REPO_ROOT / "local" / "evaluation"
DATA = LOCAL_EVAL / "baseline-v1-variance-study-1" / "data"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
LEAD_ROWS = REPO_ROOT / "local" / "diagnostics" / "t7" / "posthoc-private.json"
PROBE_MANIFEST = REPO_ROOT / "evaluation" / "t7-mechanism-probe-1" / "manifest.json"
SPLIT_MANIFEST = REPO_ROOT / "evaluation" / "tactical-screen-deployment-split-1" / "manifest.json"
POOL_FILES = ("src/miaosuan_agent/evaluation/t7_candidates.py", "src/miaosuan_agent/evaluation/t7_audit.py")

V2, SPLIT, CAND, INERT = ("baseline-v2-candidate-shoot-target-reservation", "tactic-deployment-split-1",
                          "t7-idle-concealment", "inert-v0")
PLAY = 2

#: Full captures (section 6.1). ``base``: the category a W episode can reach at best; ``deterministic``: whether
#: earlier records show identical repetitions of the configuration (rubric criterion 1), with the evidence.
FULL = (
    {"id": "A-b", "folder": "t1r-diagnosis-1", "game": "1910631192.C3.b.x01", "seat": 11, "base": "A",
     "deterministic": True, "evidence": "three Sprint 1 games, Sprint 2 game b and P-A's prefix identical (no shot)"},
    {"id": "A-pb1", "folder": "t7-mechanism-probe-1", "game": "2120531121.H1.pb1", "seat": 11, "base": "A",
     "deterministic": False, "evidence": "single stochastic game (units fire)"},
    {"id": "A-pb2", "folder": "t7-mechanism-probe-1", "game": "2120531121.H2.pb2", "seat": 1, "base": "A",
     "deterministic": False, "evidence": "single stochastic game (units fire)"},
    {"id": "B-c", "folder": "t1r-diagnosis-1", "game": "1910631192.C3.c.x01", "seat": 11, "base": "B",
     "deficit": "policy identity", "deterministic": True,
     "evidence": "three Sprint 1 games identical; Sprint 4 P1 reproduced it before its stop"},
    {"id": "B-p2", "folder": "ps1-engine-probe-1", "game": "1930331196.C2.p2", "seat": 1, "base": "B",
     "deficit": "policy identity", "deterministic": False, "evidence": "no repetition compared"},
)
SPARSE = (
    {"id": "B-r516", "folder": "baseline-v2-residual-516-diagnostic-1", "seat": 11, "deficit": "sparse snapshots",
     "games": tuple(f"1930331196.C3.d{i:02d}" for i in range(1, 33))},
    {"id": "B-smoke", "folder": "tactical-screen-deployment-split-1-smoke", "seat": 1,
     "deficit": "sparse snapshots; policy identity",
     "games": tuple(f"{s}.C2.c.s01" for s in ("1910631192", "1930331196", "2010131194", "2010211129", "201033019601",
                                               "2010431153", "2120531121", "2130511121"))},
)
KNOWN = (
    {"id": "K-pa", "folder": "t7-mechanism-probe-1", "game": "1910631192.C3.pa", "seat": 11},
    {"id": "K-pb1", "folder": "t7-mechanism-probe-1", "game": "2120531121.H1.pb1", "seat": 1},
    {"id": "K-pb2", "folder": "t7-mechanism-probe-1", "game": "2120531121.H2.pb2", "seat": 11},
)


class Refused(Exception):
    """A stopping condition of protocol section 10: report a blocker, never a result."""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    text = json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return text


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()


# ----------------------------------------------------------------------------------------------
# Frozen input selection


def game_files(folder: str, game: str) -> Dict[str, Path]:
    base = LOCAL_EVAL / folder
    return {"record": base / "games" / f"{game}.json", "compact": base / "capture" / f"{game}.capture.json",
            "windows": base / "capture" / f"{game}.windows.pkl"}


def identities() -> Dict[str, Any]:
    probe = json.loads(PROBE_MANIFEST.read_text(encoding="utf-8"))
    split = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    out = {}
    for name, sources in ((V2, probe["policies"][V2]["policy_source"]["sources"]),
                          (CAND, probe["policies"][CAND]["policy_source"]["sources"])):
        out[name] = {"registered": probe["policies"][name]["policy_source"]["sha256"],
                     "recomputed": digest_of_files(policy_source_files(sources=tuple(sources)))}
    split_policy = split["policies"][SPLIT]["policy_source"]
    out[SPLIT] = {"registered": split_policy["sha256"],
                  "recomputed": digest_of_files(policy_source_files(sources=tuple(split_policy["sources"])))}
    out["pool predicate"] = {f: normalized_sha256(REPO_ROOT / f) for f in POOL_FILES}
    return out


def freeze_payload() -> Dict[str, Any]:
    datasets, scenarios = [], set()
    for spec in FULL + KNOWN:
        files = game_files(spec["folder"], spec["game"])
        record = json.loads(files["record"].read_text(encoding="utf-8"))
        scenarios.add(record["scenario_id"])
        datasets.append({"id": spec["id"], "kind": "known answer" if spec["id"].startswith("K-") else "full",
                         "games": [{"game": spec["game"], "session": record.get("session"),
                                    "policies": record.get("policies"),
                                    "files": {k: {"path": rel(p), "sha256": sha256(p)} for k, p in files.items()}}],
                         "seat": spec["seat"]})
    for spec in SPARSE:
        games = []
        for game in spec["games"]:
            files = game_files(spec["folder"], game)
            record = json.loads(files["record"].read_text(encoding="utf-8"))
            scenarios.add(record["scenario_id"])
            games.append({"game": game, "session": record.get("session"), "policies": record.get("policies"),
                          "files": {k: {"path": rel(p), "sha256": sha256(p)} for k, p in files.items()}})
        datasets.append({"id": spec["id"], "kind": "sparse", "games": games, "seat": spec["seat"]})
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    h0 = []
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise Refused(f"{entry['path']} does not match its pinned digest")
        h0.append({"path": entry["path"], "sha256": entry["sha256"]})
        scenarios.add(Path(entry["path"]).name.split(".")[0])
    datasets.append({"id": "C-h0", "kind": "replay corpus", "files": h0})
    setup = {}
    for scenario in sorted(scenarios):
        for path in sorted((DATA / scenario / "Data").rglob("*")):
            if path.is_file():
                setup[rel(path)] = sha256(path)
    ids = identities()
    for name in (V2, CAND, SPLIT):
        if ids[name]["registered"] != ids[name]["recomputed"]:
            raise Refused(f"the policy source of {name} does not recompute to its registered digest")
    return {"schema": "miaosuan-t7-e3b-inputs/1", "study_id": STUDY, "datasets": datasets, "setup_data": setup,
            "lead_rows": {"path": rel(LEAD_ROWS), "sha256": sha256(LEAD_ROWS)}, "identities": ids,
            "note": "frozen before any eligible seat was searched; the search reads only these files"}


def verified_inputs() -> Dict[str, Any]:
    if not INPUTS.exists():
        raise Refused("inputs.json is missing: run freeze first")
    frozen = json.loads(INPUTS.read_text(encoding="utf-8"))
    problems = []
    for ds in frozen["datasets"]:
        for game in ds.get("games", ()):
            for entry in game["files"].values():
                path = REPO_ROOT / entry["path"]
                if not path.exists() or sha256(path) != entry["sha256"]:
                    problems.append(entry["path"])
        for entry in ds.get("files", ()):
            path = REPO_ROOT / entry["path"]
            if not path.exists() or sha256(path) != entry["sha256"]:
                problems.append(entry["path"])
    for name, digest_ in frozen["setup_data"].items():
        path = REPO_ROOT / name
        if not path.exists() or sha256(path) != digest_:
            problems.append(name)
    lead = REPO_ROOT / frozen["lead_rows"]["path"]
    if not lead.exists() or sha256(lead) != frozen["lead_rows"]["sha256"]:
        problems.append(frozen["lead_rows"]["path"])
    if identities() != frozen["identities"]:
        problems.append("code identities")
    if problems:
        raise Refused(f"inputs changed or missing: {problems[:5]}")
    return frozen


# ----------------------------------------------------------------------------------------------
# Loading one seat of a full capture


def costs_for(scenario: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario / "Data", scenario, map_id).cost)


def policy_for(name: str, costs: MoveCosts) -> Any:
    return {V2: ShootReservationPolicy, SPLIT: DeploymentSplitPolicy, CAND: cand.ConcealmentPolicy}[name](costs)


def own_units(raw: Mapping[str, Any], faction: int, with_listings: bool) -> Dict[int, te.UnitState]:
    return te.rows_from_raw(raw, faction, with_listings)


def enemy_hexes(raw: Mapping[str, Any], faction: int) -> frozenset:
    return frozenset(u.get("cur_hex") for u in raw.get("operators") or ()
                     if isinstance(u, Mapping) and u.get("color") not in (faction, None))


def judge_ids(records: Iterable[Mapping[str, Any]]) -> Tuple[frozenset, frozenset]:
    records = [r for r in records or () if isinstance(r, Mapping)]
    return (frozenset(r.get("att_obj_id") for r in records), frozenset(r.get("target_obj_id") for r in records))


def first_by_unit(actions: Sequence[Mapping[str, Any]]) -> Dict[int, Mapping[str, Any]]:
    out: Dict[int, Mapping[str, Any]] = {}
    for a in actions:
        if ta.integer(a.get("obj_id")) is not None and a["obj_id"] not in out:
            out[a["obj_id"]] = a
    return out


def plain(actions: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(a) for a in actions]


class Seat:
    """One searched seat of a full capture, read in one pass."""

    def __init__(self, folder: str, game_id: str, seat: int) -> None:
        self.game = tm.load(LOCAL_EVAL / folder, game_id)
        self.game_id, self.seat = game_id, seat
        self.faction, self.policy = self.game.seats[seat]
        others = [s for s in self.game.seats if s != seat]
        self.opponent = others[0] if others else None
        self.opponent_policy = self.game.seats[self.opponent][1] if self.opponent is not None else None
        self.scenario = game_id.split(".")[0]
        self.decisions: List[te.Decision] = []
        self.global_units: Dict[int, Dict[int, te.UnitState]] = {}
        self.listings_raw: Dict[int, Mapping[str, Any]] = {}
        self.opponent_lists: Dict[int, frozenset] = {}
        self.stage: Dict[int, Any] = {}
        self.orders: Dict[int, List[int]] = collections.defaultdict(list)
        self.pool_orders: set = set()
        self.reasons: Dict[Tuple[int, int], str] = {}
        self.counts = collections.Counter()
        self.differences: List[Dict[str, Any]] = []
        self.first_judge_step: Optional[int] = None
        self._read()

    def recorded(self, k: int, entry: Mapping[str, Any]) -> List[Dict[str, Any]]:
        step = self.game.steps.get(k, {})
        if "submitted" in step:
            return plain(s["action"] for s in step["submitted"] if s["seat"] == self.seat)
        return plain(entry["actions"])

    def _read(self) -> None:
        costs = None
        candidate, candidate_memory = None, sh.ShadowMemory()
        pool_memory = tc.SeatMemory()
        previous_k = None
        for k in sorted(self.game.samples):
            sample = self.game.samples[k]
            entry = sample["seats"].get(self.seat) or sample["seats"].get(str(self.seat))
            raw = pickle.loads(entry["observation"])
            glob = pickle.loads(sample["global"])
            if costs is None:
                costs = costs_for(self.scenario, str(glob.get("terrain_id")))
                redecider = policy_for(self.policy, costs)
                candidate = cand.ConcealmentPolicy(costs)
            stage = (raw.get("time") or {}).get("stage")
            self.stage[k] = stage
            actions = self.recorded(k, entry)
            baseline_actions = [a for a in actions if not tm.is_order(a)]  # a candidate seat's orders removed
            # Re-decision of the recorded policy from the recorded observation and memory (section 6.1, step 2).
            memory = pickle.loads(entry["memory"])
            try:
                d = redecider.decide(Observation.from_raw(raw, Origin.ENGINE), self.seat, self.faction, memory)
                same_actions = plain(d.actions) == actions
                same_trace = digest(d.trace) == self.game.steps[k]["traces"][str(self.seat)]
            except ContractError as exc:
                same_actions = same_trace = False
                self.differences.append({"k": k, "what": f"contract error: {exc}"[:200]})
            self.counts["decisions"] += 1
            self.counts["re-decided actions equal"] += same_actions
            self.counts["re-decided traces equal"] += same_trace
            if not (same_actions and same_trace):
                self.differences.append({"k": k, "actions": same_actions, "trace": same_trace})
            # The frozen candidate, sequentially from the first captured decision with its own memory (step 3).
            observation = Observation.from_raw(raw, Origin.ENGINE)
            last = dict(candidate_memory.last_order)
            dc = candidate.decide(observation, self.seat, self.faction, candidate_memory)
            candidate_memory = dc.memory
            base = [a for a in plain(dc.actions) if not tm.is_order(a)]
            if stage == PLAY:
                self.counts["play decisions"] += 1
                self.counts["candidate baseline part equal to the recorded play decision"] += base == baseline_actions
                cur_step = (raw.get("time") or {}).get("cur_step")
                acted = {a.get("obj_id") for a in base}
                listed = observation.valid_actions()
                seen = any(u.color != self.faction for u in observation.operators())
                for unit in sorted(observation.operators(), key=lambda u: u.obj_id):
                    if unit.color == self.faction and unit.obj_id not in acted:
                        reason = sh.refusal(unit, listed.get(unit.obj_id) or {}, seen, cur_step, last)
                        self.reasons[(k, unit.obj_id)] = reason or "ordered"
                v2 = tc.v2_by_unit(baseline_actions)
                raw_listed = ta.listings(raw)
                enemy = ta.enemy_seen(raw, self.faction)
                for uid, unit in sorted(ta.operators(raw).items()):
                    if unit.get("color") == self.faction and tc.a2(unit, raw_listed.get(uid, {}), v2.get(uid), enemy,
                                                                   cur_step, pool_memory):
                        self.pool_orders.add((k, uid))
            for a in dc.actions:
                if tm.is_order(a):
                    self.orders[a["obj_id"]].append(k)
            self.counts["candidate t7 errors"] += dc.trace.t7_error is not None
            # Rows (section 4): seat channel, all-seeing channel, the opponent's listed enemies.
            attackers, targets = judge_ids(self.game.steps.get(previous_k, {}).get("judge_new") if previous_k is not None
                                           else ())
            self.decisions.append(te.Decision(k, sample["cur_step"], own_units(raw, self.faction, True),
                                              first_by_unit(baseline_actions) if stage == PLAY else {},
                                              enemy_hexes(glob, self.faction), attackers, targets))
            self.global_units[k] = own_units(glob, self.faction, False)
            self.listings_raw[k] = {"valid_actions": raw.get("valid_actions")}
            if self.opponent is not None:
                other = sample["seats"].get(self.opponent) or sample["seats"].get(str(self.opponent))
                if other is not None:
                    raw_o = pickle.loads(other["observation"])
                    self.opponent_lists[k] = frozenset(u.get("obj_id") for u in raw_o.get("operators") or ()
                                                       if isinstance(u, Mapping) and u.get("color") == self.faction)
            previous_k = k
        final = self.game.windows.get("final")
        if final:
            glob = pickle.loads(final["global"])
            raw = pickle.loads((final["seats"].get(self.seat) or final["seats"][str(self.seat)])["observation"])
            attackers, targets = judge_ids(self.game.steps.get(previous_k, {}).get("judge_new"))
            self.decisions.append(te.Decision(final["k"], final["cur_step"], own_units(raw, self.faction, True), {},
                                              enemy_hexes(glob, self.faction), attackers, targets))
            self.global_units[final["k"]] = own_units(glob, self.faction, False)
        judged = [s["cur_step"] for s in self.game.compact.get("steps", ()) if s.get("judge_new")]
        self.first_judge_step = min(judged) if judged else None
        self.play_decisions = [d for d in self.decisions if self.stage.get(d.k, PLAY) == PLAY]

    def candidate_orders(self) -> set:
        return {(k, u) for u, ks in self.orders.items() for k in ks}


# ----------------------------------------------------------------------------------------------
# Evidence for one episode


def acceptance(seat: Seat, episode: te.Episode, fresh: Mapping[int, List[Mapping[str, Any]]]) -> Dict[str, Any]:
    """Echo, execution and listing of the episode's later command in the original game (section 4)."""
    k1, action = episode.k1, dict(episode.later_action or {})
    serial = [b["action"] for b in seat.game.steps[k1].get("batch") or () if b["seat"] == seat.seat
              and b["action"].get("obj_id") == episode.unit]
    index = {d.k: i for i, d in enumerate(seat.decisions)}
    nxt = seat.decisions[index[k1] + 1] if index[k1] + 1 < len(seat.decisions) else None
    return te.command_evidence(action, serial, fresh.get(k1, ()), seat.game.steps[k1].get("judge_new") or (),
                               None if nxt is None else nxt.units.get(episode.unit),
                               te.listing_of(seat.listings_raw[k1]).get(episode.unit, {}))


def channels_agree(seat: Seat, episode: te.Episode) -> Tuple[bool, int]:
    """The unit's fields in the seat view and the all-seeing state over [k0, k1 + 1] (section 5)."""
    compared, equal = 0, True
    ks = [d.k for d in seat.decisions]
    hi = ks[min(ks.index(episode.k1) + 1, len(ks) - 1)]
    for d in seat.decisions:
        if episode.k0 <= d.k <= hi:
            a, b = d.units.get(episode.unit), seat.global_units.get(d.k, {}).get(episode.unit)
            compared += 1
            if (a is None) != (b is None) or (a is not None and a.state_key() != b.state_key()):
                equal = False
    return equal, compared


def divergence(seat: Seat, episode: te.Episode) -> Dict[str, Any]:
    """Section 8: earlier activations of the whole policy and what the opponent saw of them."""
    first = {u: min(ks) for u, ks in seat.orders.items()}
    index = {d.k: d for d in seat.decisions}
    k_first = min(first.values())
    earlier = {u: k for u, k in first.items() if u != episode.unit and k < episode.k0}
    before_k1 = {u: k for u, k in first.items() if u != episode.unit and k < (episode.k1 or episode.k0)}
    seen_before_s0 = 0
    completes, seen_after = 0, 0
    inert = seat.opponent_policy == INERT
    for u, k in earlier.items():
        if not inert and any(u in seat.opponent_lists.get(j, ()) for j in index if k < j <= episode.k0):
            seen_before_s0 += 1
    for u, k in before_k1.items():
        s = index[k].cur_step
        if s + te.TRANSITION < (episode.s1 or 0):
            completes += 1
            if not inert and any(u in seat.opponent_lists.get(j, ()) for j, d in index.items()
                                 if s + te.TRANSITION <= d.cur_step < (episode.s1 or 0)):
                seen_after += 1
    return {"k_first": k_first, "s_first": index[k_first].cur_step, "target_in_k_first": first.get(episode.unit) == k_first
            and not episode.conditional, "earlier_first_orders": len(earlier), "earlier_seen_by_opponent": seen_before_s0,
            "first_ordered_before_k1": len(before_k1), "transitions_completing_before_s1": completes,
            "of_which_seen_by_opponent_after_completion": seen_after, "first_judge_step": seat.first_judge_step,
            "opponent_policy": seat.opponent_policy, "opponent_inert": inert}


def unit_class(seat: Seat, episode: te.Episode) -> Tuple[Any, Any]:
    state = next(d.units[episode.unit] for d in seat.decisions if d.k == episode.k0)
    return state.type, state.sub_type


# ----------------------------------------------------------------------------------------------
# Full-capture datasets


def summarise(episodes: Sequence[te.Episode]) -> Dict[str, Any]:
    out = {"episodes": len(episodes), "unconditional": collections.Counter(), "conditional": collections.Counter(),
           "TI_d": sorted(e.d for e in episodes if e.cls == te.TI),
           "W_d": sorted(e.d for e in episodes if e.cls == te.W),
           "DT_reasons": collections.Counter(), "with_gaps": sum(1 for e in episodes if e.gaps)}
    for e in episodes:
        out["conditional" if e.conditional else "unconditional"][e.label()] += 1
        if e.cls == te.DT:
            out["DT_reasons"][f"{e.reason} ({'after' if e.completed else 'during'} the transition)"] += 1
    for key in ("unconditional", "conditional", "DT_reasons"):
        out[key] = dict(sorted(out[key].items()))
    return out


def d2(seat_decisions: Sequence[te.Decision], orders: Mapping[int, Sequence[int]],
       reasons: Mapping[Tuple[int, int], str]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    runs = te.idle_runs(seat_decisions, orders)
    public = {"runs": len(runs), "by_type": dict(sorted(collections.Counter(str(r.later_type) for r in runs).items())),
              "first_refusal": collections.Counter(), "refusals_in_runs": collections.Counter()}
    private = []
    ks = [d.k for d in seat_decisions]
    for r in runs:
        inside = [reasons.get((k, r.unit)) for k in ks if r.start_k <= k < r.k1]
        inside = [x for x in inside if x is not None]
        public["first_refusal"][inside[0] if inside else "no reason recorded"] += 1
        for x in set(inside):
            public["refusals_in_runs"][x] += 1
        private.append({"unit": r.unit, "start_k": r.start_k, "k1": r.k1, "s1": r.s1, "length": r.length,
                        "type": r.later_type, "reasons": dict(collections.Counter(inside))})
    public["first_refusal"] = dict(sorted(public["first_refusal"].items()))
    public["refusals_in_runs"] = dict(sorted(public["refusals_in_runs"].items()))
    return public, private


def full_dataset(spec: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[te.Configuration], List[Dict[str, Any]]]:
    seat = Seat(spec["folder"], spec["game"], spec["seat"])
    candidate = seat.candidate_orders()
    if candidate != seat.pool_orders:
        raise Refused(f"{spec['id']}: the two trigger implementations disagree "
                      f"({len(candidate - seat.pool_orders)} candidate-only, {len(seat.pool_orders - candidate)} pool-only)")
    episodes = te.episodes(seat.play_decisions, seat.orders)
    fresh = tm.fresh_feedback(seat.game.steps)
    whole_reproduced = (seat.counts["re-decided actions equal"] == seat.counts["decisions"]
                        and seat.counts["re-decided traces equal"] == seat.counts["decisions"])
    baseline_equal = seat.counts["candidate baseline part equal to the recorded play decision"] == seat.counts["play decisions"]
    configs, certificates, private_rows = [], [], []
    for e in episodes:
        row = {"unit": e.unit, "k0": e.k0, "s0": e.s0, "class": e.label(), "d": e.d, "k1": e.k1, "s1": e.s1,
               "reason": e.reason, "previous": e.previous, "gaps": e.gaps, "unit_class": list(unit_class(seat, e))}
        if e.cls in (te.W, te.TI, te.OA):
            row["later_action"] = dict(e.later_action)
            row["acceptance"] = acceptance(seat, e, fresh)
        if e.cls in (te.W, te.TI):
            agree, compared = channels_agree(seat, e)
            row["channels"] = {"agree": agree, "snapshots": compared}
        if e.cls == te.W:
            div = divergence(seat, e)
            row["divergence"] = div
            deficits = []
            if spec["base"] != "A":
                deficits.append(spec["deficit"])
            if not whole_reproduced:
                deficits.append("re-decision differs")
            if not baseline_equal:
                deficits.append("candidate baseline part differs from the recorded decision")
            if not row["channels"]["agree"]:
                deficits.append("channel disagreement")
            if e.gaps:
                deficits.append("missing snapshot or field")
            if row["acceptance"]["echoes"] != 1:
                deficits.append("missing or ambiguous feedback")
            category = "A" if not deficits and row["acceptance"]["accepted"] and row["acceptance"]["executed"] else "B"
            if category == "B" and not deficits:
                deficits.append("later command not accepted or not executed")
            row["category"], row["deficits"] = category, deficits
            config = te.Configuration(spec["id"], category, e, row["acceptance"]["accepted"], row["acceptance"]["executed"],
                                      div["first_judge_step"], div["opponent_inert"], div["earlier_first_orders"],
                                      div["earlier_seen_by_opponent"], div["first_ordered_before_k1"],
                                      spec["deterministic"], te.long_wait(seat.play_decisions, e.s1 or 0))
            row["feasibility"] = {"F1": config.f1(), "F2": config.f2(), "F3": config.f3(), "feasible": config.feasible(),
                                  "rank_key": list(te.rank_key(config))}
            configs.append(config)
            certificates.append(certificate(spec["id"], seat.scenario, seat.faction, row, spec))
        private_rows.append(row)
    d2_public, d2_private = d2(seat.play_decisions, seat.orders, seat.reasons)
    public = {"kind": "full", "game": spec["game"], "seat_policy": seat.policy, "opponent_policy": seat.opponent_policy,
              "decisions": seat.counts["decisions"], "play_decisions": seat.counts["play decisions"],
              "redecision": {"actions_equal": seat.counts["re-decided actions equal"],
                             "traces_equal": seat.counts["re-decided traces equal"],
                             "differences": len(seat.differences)},
              "candidate_replay": {"orders": len(candidate), "units": len(seat.orders),
                                   "baseline_part_equal": seat.counts["candidate baseline part equal to the recorded play decision"],
                                   "t7_errors": seat.counts["candidate t7 errors"]},
              "pool_predicate_orders": len(seat.pool_orders), "trigger_implementations_agree": True,
              "first_judge_step": seat.first_judge_step, "summary": summarise(episodes),
              "D1": sum(1 for e in episodes if e.cls in (te.CE, te.OA) and e.completed),
              "D2": d2_public, "base_category": spec["base"],
              "W_categories": dict(sorted(collections.Counter(
                  f"{r['category']} {'conditional' if r['previous'] else 'unconditional'}"
                  for r in private_rows if r["class"] == te.W).items()))}
    private = {"episodes": private_rows, "d2": d2_private, "redecision_differences": seat.differences[:50]}
    return public, private, configs, certificates


def certificate(dataset: str, scenario: str, faction: Any, row: Mapping[str, Any], spec: Mapping[str, Any]) -> Dict[str, Any]:
    acc = row["acceptance"]
    return {"dataset": dataset, "scenario": scenario, "seat_colour": "red" if faction == 0 else "blue",
            "unit_type": row["unit_class"][0], "unit_sub_type": row["unit_class"][1], "category": row["category"],
            "deficits": row["deficits"], "conditional_on": row["previous"],
            "observed_historical_facts": {
                "decision_k0": row["k0"], "cur_step_s0": row["s0"], "decision_k1": row["k1"], "cur_step_s1": row["s1"],
                "interval_d": row["d"], "later_command_type": row["later_action"].get("type"),
                "later_command_listed": acc["listed"], "echoes": acc["echoes"], "error_codes": acc["codes"],
                "executed": acc["executed"], "undisturbed_from_k0_to_k1": True,
                "channels_agree": row["channels"]["agree"], "first_judge_step_of_game": row["divergence"]["first_judge_step"]},
            "offline_replay_decisions": {
                "candidate_first_order_here": not row["previous"], "pool_predicate_agrees": True,
                "seat_first_order_k_first": row["divergence"]["k_first"],
                "other_units_first_ordered_before_k0": row["divergence"]["earlier_first_orders"],
                "other_units_first_ordered_before_k1": row["divergence"]["first_ordered_before_k1"],
                "of_those_seen_by_opponent_before_s0": row["divergence"]["earlier_seen_by_opponent"],
                "transitions_completing_before_s1": row["divergence"]["transitions_completing_before_s1"],
                "of_which_seen_by_opponent_after_completion": row["divergence"]["of_which_seen_by_opponent_after_completion"]},
            "hypothetical_consequences": [
                "with the candidate, the unit would be ordered into concealment at k0 and, if the transition behaves as "
                "in Sprint 6, be concealed from s0 + 75",
                "the recorded later command is not an observation of the altered game: concealment of this and earlier "
                "units can change the opponent's observations and decisions and the seat's own listings",
                "acceptance of the command from concealment and the end of concealment without delay are E3b itself "
                "and are untested"],
            "feasibility": row["feasibility"], "deterministic_configuration": spec.get("deterministic")}


# ----------------------------------------------------------------------------------------------
# Sparse captures (section 6.2)


def sparse_game(folder: str, game_id: str, seat_no: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    game = tm.load(LOCAL_EVAL / folder, game_id)
    faction, policy = game.seats[seat_no]
    scenario = game_id.split(".")[0]
    steps = game.steps
    counts = collections.Counter()
    episodes: List[Dict[str, Any]] = []
    open_until: Dict[int, int] = {}  # unit -> step index at which its last episode ended (or a large number: CE)
    last_k = max(steps)
    costs = None
    for k in sorted(game.samples):
        sample = game.samples[k]
        entry = sample["seats"].get(seat_no) or sample["seats"].get(str(seat_no))
        raw = pickle.loads(entry["observation"])
        if costs is None:
            costs = costs_for(scenario, str(pickle.loads(sample["global"]).get("terrain_id")))
            redecider, candidate = policy_for(policy, costs), cand.ConcealmentPolicy(costs)
        memory = pickle.loads(entry["memory"])
        observation = Observation.from_raw(raw, Origin.ENGINE)
        d = redecider.decide(observation, seat_no, faction, memory)
        same = plain(d.actions) == plain(entry["actions"]) and digest(d.trace) == steps[k]["traces"][str(seat_no)]
        counts["snapshots"] += 1
        counts["re-decided equal"] += same
        if (raw.get("time") or {}).get("stage") != PLAY:
            continue
        if not same:
            counts["play snapshots excluded: re-decision differs"] += 1
            continue
        counts["play snapshots"] += 1
        # The trigger at the snapshot with an empty repeat memory, on baseline-v2's play decision.
        dc = candidate.decide(observation, seat_no, faction, sh.ShadowMemory(baseline=memory))
        base = [a for a in plain(dc.actions) if not tm.is_order(a)]
        counts["candidate baseline part equal"] += base == plain(entry["actions"])
        pool = set()
        v2 = tc.v2_by_unit(plain(entry["actions"]))
        raw_listed, seen = ta.listings(raw), ta.enemy_seen(raw, faction)
        for uid, unit in sorted(ta.operators(raw).items()):
            if unit.get("color") == faction and tc.a2(unit, raw_listed.get(uid, {}), v2.get(uid), seen,
                                                     sample["cur_step"], tc.SeatMemory()):
                pool.add(uid)
        orders = {a["obj_id"] for a in dc.actions if tm.is_order(a)}
        if orders != pool:
            raise Refused(f"{game_id}: the two trigger implementations disagree at snapshot {k}")
        units = ta.operators(raw)
        for uid in sorted(orders):
            if uid in open_until and k <= open_until[uid]:
                continue
            ep = sparse_episode(steps, k, uid, seat_no, last_k)
            ep["previous"] = None if uid not in open_until else "an earlier sparse episode"
            ep["unit_class"] = [units[uid].get("type"), units[uid].get("sub_type")]
            episodes.append(ep)
            open_until[uid] = ep["end_k"] if ep["class"] != te.CE else 10 ** 9
    return dict(counts), episodes


def sparse_episode(steps: Mapping[int, Mapping[str, Any]], k0: int, uid: int, seat: int, last_k: int) -> Dict[str, Any]:
    s0 = steps[k0]["cur_step"]
    for k in range(k0, last_k + 1):
        step = steps[k]
        if k > k0:
            for b in step.get("batch") or ():
                if b["seat"] == seat and b["action"].get("obj_id") == uid:
                    t, d = b["action"].get("type"), step["cur_step"] - s0
                    cls = (te.W if d >= te.TRANSITION else te.TI) if t in (te.MOVE, te.SHOOT) else te.OA
                    return {"k0": k0, "s0": s0, "class": cls, "d": d, "type": t, "end_k": k, "unit": uid}
        disturbed = None
        if any(r.get("att_obj_id") == uid or r.get("target_obj_id") == uid for r in step.get("judge_new") or ()):
            disturbed = "judge record"
        elif str(uid) in (step.get("changed") or {}):
            disturbed = "changed: " + ",".join(sorted(step["changed"][str(uid)]))
        elif uid in (step.get("gone") or ()) or uid in (step.get("boarded") or ()):
            disturbed = "gone or boarded"
        if disturbed:
            d = step["cur_step"] + 1 - s0
            return {"k0": k0, "s0": s0, "class": te.DT, "d": d, "reason": disturbed, "end_k": k + 1, "unit": uid}
    d = steps[last_k]["cur_step"] + 1 - s0
    return {"k0": k0, "s0": s0, "class": te.CE, "d": d, "end_k": last_k + 1, "unit": uid}


def sparse_dataset(spec: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[te.Configuration], List[Dict[str, Any]]]:
    counts, rows, configs, certificates = collections.Counter(), [], [], []
    by = collections.Counter()
    for game in spec["games"]:
        c, eps = sparse_game(spec["folder"], game, spec["seat"])
        counts.update(c)
        for e in eps:
            e["game"] = game
            label = e["class"] if e["class"] not in (te.DT, te.CE) else \
                f"{e['class']} {'after' if e['d'] >= te.TRANSITION else 'during'} the transition"
            by[("conditional " if e["previous"] else "") + label] += 1
            rows.append(e)
            if e["class"] == te.W:
                ep = te.Episode(e["unit"], e["k0"], e["s0"], te.W, e["d"], e["end_k"], e["s0"] + e["d"], e["type"],
                                previous=e["previous"])
                configs.append(te.Configuration(spec["id"], "B", ep, None, None, None, True, 0, 0, 0, False, False))
                certificates.append({"dataset": spec["id"], "game": game, "scenario": game.split(".")[0],
                                     "unit_type": e["unit_class"][0], "unit_sub_type": e["unit_class"][1],
                                     "category": "B", "deficits": [spec["deficit"]], "conditional_on": e["previous"],
                                     "observed_historical_facts": {
                                         "snapshot_k": e["k0"], "cur_step": e["s0"], "decision_k1": e["end_k"],
                                         "interval_lower_bound_d": e["d"], "later_command_type": e["type"],
                                         "no_action_judge_record_or_watched_change_before_k1": True},
                                     "offline_replay_decisions": {"trigger_holds_at_snapshot": True,
                                                                  "pool_predicate_agrees": True},
                                     "hypothetical_consequences": [
                                         "the first eligible decision lies at or before the snapshot and is not located",
                                         "position, move path and enemy presence between snapshots are not observed",
                                         "the recorded command is not an observation of the altered game"]})
    public = {"kind": "sparse", "games": len(spec["games"]), "counts": dict(sorted(counts.items())),
              "classes": dict(sorted(by.items())), "W_d_lower_bounds": sorted(e["d"] for e in rows if e["class"] == te.W),
              "TI_d": sorted(e["d"] for e in rows if e["class"] == te.TI), "base_category": "B",
              "W_categories": dict(sorted(collections.Counter(
                  f"B {'conditional' if e['previous'] else 'unconditional'}" for e in rows if e["class"] == te.W).items()))}
    return public, {"episodes": rows}, configs, certificates


# ----------------------------------------------------------------------------------------------
# The replay corpus (section 6.3) and the two leads (section 6.4)


def h0_dataset(frozen: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[te.Configuration], List[Dict[str, Any]], Dict[Tuple[str, int], Any]]:
    corpus = next(ds for ds in frozen["datasets"] if ds["id"] == "C-h0")
    totals, by = collections.Counter(), {"unconditional": collections.Counter(), "conditional": collections.Counter()}
    rows, configs, certificates, d2_total = [], [], [], collections.Counter()
    seats_out: Dict[Tuple[str, int], Any] = {}
    for entry in corpus["files"]:
        path = REPO_ROOT / entry["path"]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            lines = [json.loads(line) for line in handle]
        game, scenario = header["game_id"], header["scenario_id"]
        costs = costs_for(scenario, header["map_id"])
        by_seat: Dict[int, List[Dict[str, Any]]] = collections.defaultdict(list)
        for row in lines:
            by_seat[row["seat"]].append(row)
        for seat_no, seat_rows in sorted(by_seat.items()):
            faction = seat_rows[0]["faction"]
            v0, v2, candidate = BaselinePolicy(costs), ShootReservationPolicy(costs), cand.ConcealmentPolicy(costs)
            m0, m2, mc, pool_memory = Memory(), Memory(), sh.ShadowMemory(), tc.SeatMemory()
            decisions, orders, pool_orders, reasons = [], collections.defaultdict(list), set(), {}
            recorded_v0 = {}
            for row in sorted(seat_rows, key=lambda r: r["step"]):
                raw = typed_json.decode(row["observation"])
                observation = Observation.from_raw(raw, Origin.ENGINE)
                k, cur_step = row["step"], (raw.get("time") or {}).get("cur_step")
                totals["decisions"] += 1
                try:
                    d0 = v0.decide(observation, seat_no, faction, m0)
                except ContractError:
                    totals["excluded: contract error"] += 1
                    continue
                m0 = d0.memory
                exact = plain(d0.actions) == plain(row["actions"]) and digest(d0.trace) == row["trace_digest"]
                d2_ = v2.decide(Observation.from_raw(raw, Origin.ENGINE), seat_no, faction, m2)
                m2 = d2_.memory
                last = dict(mc.last_order)
                dc = candidate.decide(Observation.from_raw(raw, Origin.ENGINE), seat_no, faction, mc)
                mc = dc.memory
                totals["baseline-v0 exact"] += exact
                explained = explained_against_v0(d0, d2_)
                totals["baseline-v2 difference explained"] += explained
                v2_actions = plain(d2_.actions)
                base = [a for a in plain(dc.actions) if not tm.is_order(a)]
                totals["candidate baseline part equal to reconstructed baseline-v2"] += base == v2_actions
                stage = (raw.get("time") or {}).get("stage")
                missing = not (exact and explained)
                if stage == PLAY:
                    acted = {a.get("obj_id") for a in base}
                    listed = observation.valid_actions()
                    seen = any(u.color != faction for u in observation.operators())
                    for unit in sorted(observation.operators(), key=lambda u: u.obj_id):
                        if unit.color == faction and unit.obj_id not in acted:
                            reasons[(k, unit.obj_id)] = sh.refusal(unit, listed.get(unit.obj_id) or {}, seen, cur_step,
                                                                   last) or "ordered"
                    v2u = tc.v2_by_unit(v2_actions)
                    raw_listed, enemy = ta.listings(raw), ta.enemy_seen(raw, faction)
                    for uid, unit in sorted(ta.operators(raw).items()):
                        if unit.get("color") == faction and tc.a2(unit, raw_listed.get(uid, {}), v2u.get(uid), enemy,
                                                                  cur_step, pool_memory):
                            pool_orders.add((k, uid))
                    for a in dc.actions:
                        if tm.is_order(a):
                            orders[a["obj_id"]].append(k)
                    attackers, targets = judge_ids(raw.get("judge_info"))
                    units = own_units(raw, faction, True)
                    if missing:
                        totals["play decisions excluded: baseline-v0 not reproduced or baseline-v2 unexplained"] += 1
                    decisions.append(te.Decision(k, cur_step, units, {} if missing else first_by_unit(v2_actions),
                                                 enemy_hexes(raw, faction), attackers, targets))
                    recorded_v0[k] = first_by_unit(plain(row["actions"]))
            cand_orders = {(k, u) for u, ks in orders.items() for k in ks}
            if cand_orders != pool_orders:
                raise Refused(f"C-h0 {game} seat {seat_no}: the two trigger implementations disagree")
            totals["orders"] += len(cand_orders)
            eps = te.episodes(decisions, orders)
            index = {d.k: i for i, d in enumerate(decisions)}
            for e in eps:
                key = "conditional" if e.conditional else "unconditional"
                by[key][e.label()] += 1
                row = {"game": game, "seat": seat_no, "unit": e.unit, "k0": e.k0, "s0": e.s0, "class": e.label(),
                       "d": e.d, "k1": e.k1, "s1": e.s1, "reason": e.reason, "previous": e.previous, "gaps": e.gaps}
                if e.cls in (te.W, te.TI, te.OA):
                    v0a = recorded_v0.get(e.k1, {}).get(e.unit)
                    nxt = decisions[index[e.k1] + 1] if index[e.k1] + 1 < len(decisions) else None
                    executed = None
                    if v0a is not None and nxt is not None and e.unit in nxt.units:
                        if v0a.get("type") == te.SHOOT:
                            executed = e.unit in nxt.attackers
                        elif v0a.get("type") == te.MOVE:
                            path = tuple(v0a.get("move_path") or ())
                            later = nxt.units[e.unit]
                            executed = bool(path) and (later.hex == path[0] or bool(later.path))
                    row["later_action"] = dict(e.later_action)
                    row["recorded_baseline_v0"] = {"same_action": v0a is not None and dict(v0a) == dict(e.later_action),
                                                   "action_type": None if v0a is None else v0a.get("type"),
                                                   "executed_in_recorded_trajectory": executed}
                if e.cls == te.W:
                    first = {u: min(ks) for u, ks in orders.items()}
                    ep_unit = decisions[index[e.k0]].units[e.unit]
                    config = te.Configuration("C-h0", "C", e, None, None, None, False,
                                              sum(1 for u, k in first.items() if u != e.unit and k < e.k0), 0,
                                              sum(1 for u, k in first.items() if u != e.unit and k < e.k1), False,
                                              te.long_wait(decisions, e.s1 or 0))
                    configs.append(config)
                    certificates.append({"dataset": "C-h0", "scenario": scenario,
                                         "seat_colour": "red" if faction == 0 else "blue",
                                         "unit_type": ep_unit.type, "unit_sub_type": ep_unit.sub_type, "category": "C",
                                         "deficits": ["off-policy: baseline-v2 reconstructed on baseline-v0's trajectory",
                                                      "no feedback or all-seeing state in the corpus"],
                                         "conditional_on": e.previous,
                                         "observed_historical_facts": {
                                             "recorded_policy": "baseline-v0", "decision_k0": e.k0, "cur_step_s0": e.s0,
                                             "decision_k1": e.k1, "cur_step_s1": e.s1, "interval_d": e.d,
                                             "undisturbed_in_recorded_trajectory": True,
                                             "recorded_baseline_v0_at_k1": row["recorded_baseline_v0"]},
                                         "offline_replay_decisions": {
                                             "reconstructed_baseline_v2_later_command_type": e.later_type,
                                             "candidate_first_order_here": not e.previous, "pool_predicate_agrees": True,
                                             "other_units_first_ordered_before_k0": config.earlier_first_orders,
                                             "other_units_first_ordered_before_k1": config.first_ordered_before_k1},
                                         "hypothetical_consequences": [
                                             "baseline-v2 did not generate this trajectory; its later command is a "
                                             "decision on baseline-v0's states",
                                             "the recorded command is not an observation of any game with concealment"]})
                rows.append(row)
            pub, _ = d2(decisions, orders, reasons)
            d2_total["runs"] += pub["runs"]
            for kx, v in pub["first_refusal"].items():
                d2_total[f"first refusal: {kx}"] += v
            seats_out[(game, seat_no)] = {"decisions": decisions, "orders": orders, "episodes": eps,
                                          "recorded_v0": recorded_v0}
    public = {"kind": "replay corpus", "games": len(corpus["files"]), "counts": dict(sorted(totals.items())),
              "classes": {k: dict(sorted(v.items())) for k, v in by.items()},
              "W_d": sorted(r["d"] for r in rows if r["class"] == te.W),
              "TI_d": sorted(r["d"] for r in rows if r["class"] == te.TI),
              "D1": sum(1 for r in rows if (r["class"].startswith("CE after") or r["class"].startswith("OA"))
                        and (r["d"] or 0) >= te.TRANSITION),
              "D2": dict(sorted(d2_total.items())), "base_category": "C",
              "W_categories": dict(sorted(collections.Counter(
                  f"C {'conditional' if r['previous'] else 'unconditional'}" for r in rows if r["class"] == te.W).items()))}
    return public, {"episodes": rows}, configs, certificates, seats_out


def explained_against_v0(v0: Any, v2: Any) -> bool:
    """Every unit on which baseline-v2 differs from baseline-v0 carries baseline-v2's own reservation record (the
    Sprint 5 reconstruction rule, ``scripts/t7_study.py``)."""
    old = {a.get("obj_id", "seat"): dict(a) for a in v0.actions}
    new = {a.get("obj_id", "seat"): dict(a) for a in v2.actions}
    payload = v2.trace.to_dict()
    marked = {s["obj_id"] for s in payload.get("suppressed", [])}
    marked |= {e["obj_id"] for e in payload.get("shoot_reserved", []) if e["effect"] != "unchanged"}
    return all(old.get(k) == new.get(k) or k in marked for k in set(old) | set(new))


def leads(seats_out: Mapping[Tuple[str, int], Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    data = json.loads(LEAD_ROWS.read_text(encoding="utf-8"))
    rows = data["a2_rows"] if isinstance(data, Mapping) and "a2_rows" in data else data
    if isinstance(rows, Mapping):
        rows = next(v for v in rows.values() if isinstance(v, list))
    chosen = [r for r in rows if r.get("ended") == "acted or moved" and not r.get("repeat")]
    if len(chosen) != 2:
        raise Refused(f"expected the 2 Sprint 5 leads, found {len(chosen)}")
    public, private = [], []
    for r in chosen:
        hits = [(key, s) for key, s in seats_out.items() if key[0] == r["game"]
                and any(e.unit == r["unit"] and e.k0 == r["k"] and not e.conditional for e in s["episodes"])]
        if len(hits) != 1:
            raise Refused(f"lead {r['game']} not matched to exactly one H0 episode ({len(hits)})")
        (game, seat_no), s = hits[0]
        e = next(e for e in s["episodes"] if e.unit == r["unit"] and e.k0 == r["k"] and not e.conditional)
        decisions = s["decisions"]
        index = {d.k: i for i, d in enumerate(decisions)}
        label_k = r["k"] + r["idle_after"] + 1
        at = decisions[index[label_k]] if label_k in index else None
        unit_now = at.units.get(r["unit"]) if at is not None else None
        v0a = s["recorded_v0"].get(label_k, {}).get(r["unit"])
        v2a = at.actions.get(r["unit"]) if at is not None else None
        fired = []
        if v0a is not None:
            fired.append("recorded baseline-v0 action")
        if unit_now is not None and unit_now.stop != 1:
            fired.append("stop not 1")
        if unit_now is not None and unit_now.path:
            fired.append("move path")
        start = decisions[index[r["k"]]].units[r["unit"]]
        item = {"scenario": game.split(".")[0], "unit_type": start.type, "unit_sub_type": start.sub_type,
                "decision_k0": r["k"], "label_decision": label_k, "label_d": None if at is None else at.cur_step - e.s0,
                "label_fired_by": fired, "recorded_baseline_v0_action_type": None if v0a is None else v0a.get("type"),
                "reconstructed_baseline_v2_action_type": None if v2a is None else v2a.get("type"),
                "episode_class": e.label(), "episode_d": e.d, "episode_later_type": e.later_type,
                "episode_reason": e.reason,
                "is_move_or_direct_fire_by_baseline_v2": v2a is not None and v2a.get("type") in (te.MOVE, te.SHOOT)}
        public.append(item)
        private.append(dict(item, game=game, seat=seat_no, unit=r["unit"]))
    return public, private


# ----------------------------------------------------------------------------------------------
# Known-answer validation (section 7)


def validate() -> Dict[str, Any]:
    out, problems = {}, []
    total_orders = total_units = 0
    for spec in KNOWN:
        seat = Seat(spec["folder"], spec["game"], spec["seat"])
        recorded = set()
        for k, step in seat.game.steps.items():
            for s in step.get("submitted") or ():
                if s["seat"] == spec["seat"] and tm.is_order(s["action"]):
                    recorded.add((k, s["action"]["obj_id"]))
        replay = seat.candidate_orders()
        eps = te.episodes(seat.play_decisions, seat.orders)
        expected = all(e.cls == te.DT and e.reason == "transition" and e.d == 1 and not e.conditional for e in eps)
        result = {"recorded_orders": len(recorded), "replay_orders": len(replay), "orders_equal": replay == recorded,
                  "pool_predicate_equal": seat.pool_orders == recorded,
                  "decisions": seat.counts["decisions"], "re-decided_actions_equal": seat.counts["re-decided actions equal"],
                  "re-decided_traces_equal": seat.counts["re-decided traces equal"],
                  "episodes": len(eps), "classes": dict(collections.Counter(e.label() for e in eps)),
                  "reasons": dict(collections.Counter(str(e.reason) for e in eps)),
                  "d": sorted({e.d for e in eps}), "all_DT_transition_at_d1": expected}
        if not (result["orders_equal"] and result["pool_predicate_equal"] and expected
                and result["re-decided_actions_equal"] == result["decisions"]
                and result["re-decided_traces_equal"] == result["decisions"] and len(eps) == len(recorded)):
            problems.append(spec["id"])
        total_orders += len(recorded)
        total_units += len({u for _, u in recorded})
        out[spec["id"]] = result
    passed = not problems and total_orders == 16 and total_units == 16
    return {"schema": SCHEMA, "study_id": STUDY, "part": "known-answer validation", "seats": out,
            "orders": total_orders, "units": total_units, "passed": passed, "problems": problems}


# ----------------------------------------------------------------------------------------------
# Search and decision


def search() -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    frozen = verified_inputs()
    public: Dict[str, Any] = {"schema": SCHEMA, "study_id": STUDY, "part": "search",
                              "inputs_sha256": sha256(INPUTS), "datasets": {}}
    private: Dict[str, Any] = {"datasets": {}}
    configs: List[te.Configuration] = []
    certificates: List[Dict[str, Any]] = []
    for spec in FULL:
        pub, priv, cfg, cert = full_dataset(spec)
        public["datasets"][spec["id"]] = pub
        private["datasets"][spec["id"]] = priv
        configs += cfg
        certificates += cert
    for spec in SPARSE:
        pub, priv, cfg, cert = sparse_dataset(spec)
        public["datasets"][spec["id"]] = pub
        private["datasets"][spec["id"]] = priv
        configs += cfg
        certificates += cert
    pub, priv, cfg, cert, seats_out = h0_dataset(frozen)
    public["datasets"]["C-h0"] = pub
    private["datasets"]["C-h0"] = priv
    configs += cfg
    certificates += cert
    lead_public, lead_private = leads(seats_out)
    public["leads"] = lead_public
    private["leads"] = lead_private
    witnesses = collections.Counter()
    for c in configs:
        witnesses[f"{c.category} {'conditional' if c.episode.conditional else 'unconditional'}"] += 1
    public["W_episodes_by_category"] = dict(sorted(witnesses.items()))
    public["feasible_configurations"] = sum(1 for c in configs if c.feasible())
    ranked = sorted((c for c in configs if c.feasible()), key=te.rank_key)
    public["ranking"] = [{"dataset": c.dataset, "rank_key": list(te.rank_key(c)), "d": c.episode.d,
                          "s0": c.episode.s0, "s1": c.episode.s1} for c in ranked]
    return public, private, certificates


def decide() -> Dict[str, Any]:
    searched = json.loads((OUT / "search.json").read_text(encoding="utf-8"))
    cross = json.loads((OUT / "crosscheck.json").read_text(encoding="utf-8"))
    validation = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))
    agrees = True
    differences = []
    for ds, counts in cross["datasets"].items():
        mine = searched["datasets"][ds]
        ours = mine["summary"] if "summary" in mine else mine["classes"]
        theirs_cmp = counts["classes"]
        mine_cmp = ({"unconditional": ours["unconditional"], "conditional": ours["conditional"]}
                    if "unconditional" in ours else ours)
        if mine_cmp != theirs_cmp or mine["W_categories"] != counts["W_categories"]:
            agrees = False
            differences.append(ds)
    if set(cross["datasets"]) != set(searched["datasets"]):
        agrees = False
        differences.append("dataset sets differ")
    w = searched["W_episodes_by_category"]
    feasible = searched["feasible_configurations"]
    stopped = not validation["passed"]
    if stopped or not agrees:
        verdict = te.BLOCKED
    elif feasible:
        verdict = te.IDENTIFIED
    elif any(v for v in w.values()):
        verdict = te.UNCERTAIN
    else:
        verdict = te.NONE_FOUND
    return {"schema": SCHEMA, "study_id": STUDY, "part": "decision", "crosscheck_agrees": agrees,
            "crosscheck_differences": differences, "validation_passed": validation["passed"],
            "W_episodes_by_category": w, "feasible_configurations": feasible, "disposition": verdict}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("freeze", "validate", "search", "decide", "check"))
    args = parser.parse_args()
    try:
        if args.command == "freeze":
            if INPUTS.exists():
                print("inputs.json exists; the selection is frozen and is not rewritten")
                return 1
            write_json(INPUTS, freeze_payload())
            print(f"wrote {rel(INPUTS)}")
        elif args.command == "validate":
            verified_inputs()
            result = validate()
            write_json(OUT / "validation.json", result)
            print("known-answer validation " + ("PASSED" if result["passed"] else f"FAILED {result['problems']}"))
            return 0 if result["passed"] else 1
        elif args.command == "search":
            validation = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))
            if not validation["passed"]:
                raise Refused("the known-answer validation has not passed")
            public, private, certificates = search()
            write_json(OUT / "search.json", public)
            write_json(OUT / "certificates.json", {"schema": SCHEMA, "study_id": STUDY, "certificates": certificates})
            write_json(PRIVATE / "search-private.json", private)
            print(f"W episodes by category: {public['W_episodes_by_category']}; "
                  f"feasible configurations: {public['feasible_configurations']}")
        elif args.command == "decide":
            result = decide()
            write_json(OUT / "decision.json", result)
            print(f"disposition: {result['disposition']}")
        else:
            verified_inputs()
            ok = True
            expected = {"validation.json": json.dumps(validate(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"}
            public, _, certificates = search()
            expected["search.json"] = json.dumps(public, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            expected["certificates.json"] = json.dumps({"schema": SCHEMA, "study_id": STUDY, "certificates": certificates},
                                                       indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            expected["decision.json"] = json.dumps(decide(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"
            for name, text in expected.items():
                same = (OUT / name).read_text(encoding="utf-8") == text
                ok &= same
                print(f"{name}: {'identical' if same else 'MISMATCH'}")
            return 0 if ok else 1
    except Refused as exc:
        print(f"REFUSED: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
