"""Registered analyses of the T7 mechanism probe ``t7-mechanism-probe-1`` (``docs/T7_MECHANISM_PROBE.md``).

    python scripts/t7_probe_analysis.py calibrate [--check]
    python scripts/t7_probe_analysis.py premise [--check]
    python scripts/t7_probe_analysis.py equivalence [--check]
    python scripts/t7_probe_analysis.py dryrun [--check]
    python scripts/t7_probe_analysis.py game --probe P-A|P-B1|P-B2 --out PUBLIC --private PRIVATE
                                        [--work DIR] [--commit SHA]
    python scripts/t7_probe_analysis.py gate --pa PUBLIC --installation REPORT --identities REPORT --out FILE
    python scripts/t7_probe_analysis.py stop --pb1 PUBLIC --installation REPORT --identities REPORT --out FILE
    python scripts/t7_probe_analysis.py pool --pa PUBLIC [--pb1 PUBLIC] [--pb2 PUBLIC] --out FILE

``calibrate``, ``premise``, ``equivalence`` and ``dryrun`` run before registration on existing records (no engine):

* ``calibrate``: the documented visibility model (``evaluation/t7_visibility.py``) against every unconcealed ground
  target-step of the replay corpus H0, both seats (``evaluation/t7-mechanism-probe-1/calibration.json``);
* ``premise``: the registered candidate replayed over the reference game's blue observations: the decisions and units
  of its predicted orders (public counts in ``premise.json``; the unit list private, pinned by digest);
* ``equivalence``: the registered candidate against the Sprint 5 shadow and an independent ``baseline-v2`` on every
  recorded decision of H0, H1 and H2 (``equivalence.json``);
* ``dryrun``: the registered game analysis on real records adapted to the capture format: P-A's analysis on the
  reference game itself (no order: every mechanism endpoint must come out NOT TESTED), the reference's determinism
  against its Sprint 1 repetitions, and E4's machinery on the H0 game of P-B's scenario (``dryrun.json``).

``game`` is the registered analysis of one probe game (public aggregates and a private file with unit-level rows);
``gate`` applies P-A's continuation gate, ``stop`` the P-B1 stop branch, ``pool`` the pooled primary metric, E4 and
the registered disposition. A refusal (an integrity condition of the protocol) exits 3 and writes the reason.
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
from typing import Any, Dict, List, Mapping, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent import sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import ContractError, MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.evaluation import t7_audit as ta  # noqa: E402
from miaosuan_agent.evaluation import t7_candidates as tc  # noqa: E402
from miaosuan_agent.evaluation import t7_probe as tp  # noqa: E402
from miaosuan_agent.evaluation import t7_probe_endpoints as ep  # noqa: E402
from miaosuan_agent.evaluation import t7_probe_metrics as tm  # noqa: E402
from miaosuan_agent.evaluation import t7_visibility as tv  # noqa: E402
from miaosuan_agent.experiments import t7_concealment as cand  # noqa: E402
from miaosuan_agent.experiments import t7_idle_concealment as sh  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / tp.PROBE_ID
MANIFEST = OUT / "manifest.json"
WORK = REPO_ROOT / "local" / "evaluation" / tp.PROBE_ID
PRIVATE = REPO_ROOT / "local" / "diagnostics" / "t7-probe"
DATA = REPO_ROOT / "local" / "evaluation" / "baseline-v1-variance-study-1" / "data"
CORPUS = REPO_ROOT / "evaluation" / "routing-remediation-1" / "corpus.json"
REFERENCE = REPO_ROOT / tp.REFERENCE_WORK
SCREEN_WORK = REPO_ROOT / "local" / "evaluation" / "tactical-screen-deployment-split-1"
PREMISE_PRIVATE = PRIVATE / "premise-private.json"
H_CAPTURES = {"H1": [("t1r-diagnosis-1", "1910631192.C3.b.x01")],
              "H2": [("t1r-diagnosis-1", "1910631192.C3.c.x01"), ("ps1-engine-probe-1", "1930331196.C2.p2")]}
SCHEMA = "miaosuan-t7-probe-analysis/1"
PROBES = {g["probe"]: g for g in tp.GAMES}


def dump(payload: Any) -> str:
    return json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write_or_check(path: Path, payload: Any, check: bool) -> int:
    text = dump(payload)
    if check:
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            print(f"{path} differs from a fresh build", file=sys.stderr)
            return 1
        print(f"{path} identical")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {path}")
    return 0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def inputs_for(root: Path, scenario: str, map_id: str) -> Any:
    return sdk_data.load_inputs(root / scenario / "Data", scenario, map_id)


# ----------------------------------------------------------------------------------------------
# Calibration of the visibility model on H0


def h0_games(wanted: Optional[set] = None):
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    for entry in corpus["files"]:
        if entry["role"] != "replay corpus game":
            continue
        path = REPO_ROOT / entry["path"]
        if sha256_file(path) != entry["sha256"]:
            raise SystemExit(f"{entry['path']} does not match its pinned digest")
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            header = json.loads(next(handle))
            if wanted and header["scenario_id"] not in wanted:
                continue
            by_step: Dict[int, Dict[int, Any]] = collections.defaultdict(dict)
            for line in handle:
                row = json.loads(line)
                by_step[row["step"]][row["faction"]] = typed_json.decode(row["observation"])
        yield header, entry, by_step


def calibrate() -> Dict[str, Any]:
    scenarios: Dict[str, Any] = {}
    for header, entry, by_step in h0_games():
        scenario = header["scenario_id"]
        inputs = inputs_for(DATA, scenario, header["map_id"])
        m = tv.MapData(inputs.basic, inputs.see)
        c = collections.Counter()
        for step in sorted(by_step):
            views = by_step[step]
            if set(views) != {0, 1} or (views[0].get("time") or {}).get("stage") != 2:
                continue
            rows = {f: tm.unit_rows(views[f], f) for f in (0, 1)}
            for f in (0, 1):
                g = 1 - f
                listed = {u.get("obj_id") for u in views[g].get("operators") or () if u.get("color") == f}
                observers = [ep._as_dict(u) for u in rows[g].values() if u.on_map]
                for uid, x in rows[f].items():
                    if x.type not in tv.GROUND or not x.on_map:
                        continue
                    target = ep._as_dict(x)
                    if x.launched:
                        c["launched: listed" if uid in listed else "launched: unlisted"] += 1
                        if any(tv.sees_unconcealed(m, o, target) for o in observers) != (uid in listed):
                            c["launched: model disagrees"] += 1
                            if x.launcher in listed:
                                c["launched: model disagrees, launcher listed"] += 1
                        continue
                    seers = [o for o in observers if tv.sees_unconcealed(m, o, target)]
                    kind = "aerial" if any(tv.is_aerial(o) for o in seers) else "ground" if seers else "none"
                    c[f"predicted by {kind} observers: {'agree' if bool(seers) == (uid in listed) else 'disagree'}"] += 1
                    label, _ = tv.classify(m, observers, target)
                    if label == tv.DISCRIMINATING:
                        c["matched band: " + ("listed" if uid in listed else "unlisted")] += 1
                    if (x.type == tv.VEHICLE and m.covered(x.hex) and not seers and any(
                            tv.normal_distance(o, target) == 25.0 and tv.hex_distance(o["cur_hex"], x.hex) == 13
                            and m.los(tv.AIR_MODE if tv.is_aerial(o) else tv.GROUND_MODE, o["cur_hex"], x.hex)
                            for o in observers)):
                        c["12.5-hex boundary in cover: " + ("listed" if uid in listed else "unlisted")] += 1
        agree = sum(v for k, v in c.items() if k.endswith(": agree"))
        total = agree + sum(v for k, v in c.items() if k.endswith(": disagree"))
        scenarios[scenario] = {"counts": dict(sorted(c.items())), "target_steps": total, "agree": agree}
    total = sum(s["target_steps"] for s in scenarios.values())
    agree = sum(s["agree"] for s in scenarios.values())
    return {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": "calibration",
            "status": "registered before the first probe session; population H0 (replay corpus), no unit concealed",
            "model": "src/miaosuan_agent/evaluation/t7_visibility.py (unconcealed prediction, terrain halving)",
            "scenarios": scenarios, "target_steps": total, "agree": agree, "agreement": agree / total if total else None,
            "launched_units": {key: sum(s["counts"].get(f"launched: {key}", 0) for s in scenarios.values())
                               for key in ("listed", "unlisted", "model disagrees", "model disagrees, launcher listed")}}


# ----------------------------------------------------------------------------------------------
# The premise: the candidate replayed over the reference game


def reference_game() -> tm.Game:
    game = tm.load(REFERENCE, tp.REFERENCE_GAME)
    return game


def premise() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    ref = reference_game()
    inputs = inputs_for(DATA, "1910631192", "92")
    policy = cand.ConcealmentPolicy(MoveCosts.from_raw(inputs.cost))
    memory = sh.ShadowMemory()
    orders: List[Tuple[int, int, int]] = []
    equal_actions = equal_traces = decisions = 0
    for k in sorted(ref.samples):
        sample = ref.samples[k]
        entry = sample["seats"][11]
        raw = pickle.loads(entry["observation"])
        d = policy.decide(Observation.from_raw(raw, Origin.ENGINE), 11, 1, memory)
        memory = d.memory
        decisions += 1
        base = [dict(a) for a in d.actions if not tm.is_order(a)]
        equal_actions += base == [dict(a) for a in entry["actions"]]
        equal_traces += d.trace.baseline_trace_sha256 == ref.steps[k]["traces"]["11"]
        for a in d.actions:
            if tm.is_order(a):
                orders.append((k, sample["cur_step"], a["obj_id"]))
    by_k = collections.Counter(k for k, _, _ in orders)
    first = sorted(by_k)[:2]
    public = {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": "premise",
              "reference": tp.REFERENCE_GAME, "decisions": decisions,
              "baseline_v2_actions_equal_to_recorded": equal_actions,
              "baseline_v2_trace_digest_equal_to_recorded": equal_traces,
              "orders_on_the_recorded_trajectory": len(orders),
              "units_on_the_recorded_trajectory": len({u for _, _, u in orders}),
              "first_order_decisions": [{"k": k, "units": by_k[k]} for k in first],
              "note": "the recorded trajectory never contained a concealed unit, so after the first order the "
                      "replay is not a prediction of the probe game; only the first two order decisions are registered"}
    private = {"first": sorted(u for k, _, u in orders if k == first[0]),
               "second": sorted(u for k, _, u in orders if len(first) > 1 and k == first[1])}
    return public, private


# ----------------------------------------------------------------------------------------------
# Equivalence of the registered candidate with the shadow and baseline-v2 (H0, H1, H2)


def equivalence() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    counts = collections.Counter()

    def compare(raw, seat, faction, policies, memories) -> None:
        obs = Observation.from_raw(raw, Origin.ENGINE)
        c, s, v = policies
        dc = c.decide(obs, seat, faction, memories["c"])
        ds = s.decide(obs, seat, faction, memories["s"])
        dv = v.decide(obs, seat, faction, memories["v"])
        memories.update(c=dc.memory, s=ds.memory, v=dv.memory)
        counts["decisions"] += 1
        counts["candidate actions equal to the shadow's"] += [dict(a) for a in dc.actions] == [dict(a) for a in ds.actions]
        counts["candidate added equal to the shadow's"] += [list(a) for a in dc.trace.added] == [
            [a["obj_id"], a["target_state"]] for a in ds.added]
        counts["candidate skip reasons equal to the shadow's"] += tuple(dc.trace.skipped) == tuple(ds.skipped)
        counts["baseline trace digest equal to baseline-v2's"] += dc.trace.baseline_trace_sha256 == digest(dv.trace)
        counts["candidate actions start with baseline-v2's"] += [dict(a) for a in dc.actions[:len(dv.actions)]] == [
            dict(a) for a in dv.actions]
        counts["orders"] += len(dc.trace.added)
        counts["no t7 error"] += dc.trace.t7_error is None

    for header, entry, by_step in h0_games():
        costs = MoveCosts.from_raw(inputs_for(DATA, header["scenario_id"], header["map_id"]).cost)
        seats: Dict[int, Any] = {}
        path = REPO_ROOT / entry["path"]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            next(handle)
            for line in handle:
                row = json.loads(line)
                if row["seat"] not in seats:
                    seats[row["seat"]] = ((cand.ConcealmentPolicy(costs), sh.IdleConcealmentShadow(costs),
                                           ShootReservationPolicy(costs)),
                                          {"c": sh.ShadowMemory(), "s": sh.ShadowMemory(), "v": Memory()})
                policies, memories = seats[row["seat"]]
                compare(typed_json.decode(row["observation"]), row["seat"], row["faction"], policies, memories)
    out["H0"] = dict(sorted(counts.items()))
    for population, captures in H_CAPTURES.items():
        counts.clear()
        for folder, stem in captures:
            game = tm.load(REPO_ROOT / "local" / "evaluation" / folder, stem)
            scenario = stem.split(".")[0]
            map_id = {"1910631192": "92", "1930331196": "96"}[scenario]
            costs = MoveCosts.from_raw(inputs_for(DATA, scenario, map_id).cost)
            policies = (cand.ConcealmentPolicy(costs), sh.IdleConcealmentShadow(costs), ShootReservationPolicy(costs))
            memories = {"c": sh.ShadowMemory(), "s": sh.ShadowMemory(), "v": Memory()}
            for k in sorted(game.samples):
                (seat, entry2), = game.samples[k]["seats"].items()
                compare(pickle.loads(entry2["observation"]), int(seat), entry2["faction"], policies, memories)
        out[population] = dict(sorted(counts.items()))
    return {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": "equivalence", "populations": out}


# ----------------------------------------------------------------------------------------------
# The registered analysis of one probe game


class Redecider:
    """I5: a fresh candidate (and a fresh baseline-v2 for its seat) re-decides every captured decision from the seat's
    recorded observation and memory; the independent pool predicate re-finds the candidate's orders."""

    def __init__(self, game: tm.Game, costs: MoveCosts) -> None:
        self.game = game
        self.candidate = cand.ConcealmentPolicy(costs)
        self.baseline = ShootReservationPolicy(costs)
        self.pool_memory: Dict[int, tc.SeatMemory] = collections.defaultdict(tc.SeatMemory)
        self.counts = collections.Counter()
        self.activations: set = set()
        self.problems: List[str] = []

    def __call__(self, k: int, glob: Mapping[str, Any], observations: Mapping[int, Any], memories: Mapping[int, Any]):
        for seat, raw in observations.items():
            faction, policy = self.game.seats[seat]
            if policy not in (tp.CANDIDATE_ID, tp.BASELINE_ID):
                continue
            engine = self.candidate if policy == tp.CANDIDATE_ID else self.baseline
            try:
                d = engine.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, memories[seat])
            except ContractError as exc:
                self.problems.append(f"I5: contract error re-deciding seat {seat} at decision {k}: {exc}")
                continue
            self.counts[f"{policy} decisions"] += 1
            if [dict(a) for a in d.actions] != tm.submitted(self.game, seat, k):
                self.problems.append(f"I5: re-decided actions differ for seat {seat} at decision {k}")
            if digest(d.trace) != self.game.steps[k]["traces"][str(seat)]:
                self.problems.append(f"I5: re-decided trace differs for seat {seat} at decision {k}")
            if policy == tp.CANDIDATE_ID and (raw.get("time") or {}).get("stage") == 2:
                base = [a for a in tm.submitted(self.game, seat, k) if not tm.is_order(a)]
                v2 = tc.v2_by_unit(base)
                listed = ta.listings(raw)
                seen = ta.enemy_seen(raw, faction)
                cur_step = (raw.get("time") or {}).get("cur_step")
                for uid, unit in sorted(ta.operators(raw).items()):
                    if unit.get("color") != faction:
                        continue
                    if tc.a2(unit, listed.get(uid, {}), v2.get(uid), seen, cur_step, self.pool_memory[seat]):
                        self.activations.add((seat, k, uid))


def staged_inputs(manifest: Mapping[str, Any], work: Path, scenario: str) -> Any:
    entry = next(s for s in manifest["scenarios"] if s["scenario_id"] == scenario)
    root = work / "data" / scenario / "Data"
    paths = {"scenario": sdk_data.scenario_path(root, scenario), **sdk_data.map_paths(root, entry["map_id"])}
    for role, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["inputs_sha256"][role]:
            raise tm.AnalysisRefused(f"input {role} of {scenario} does not match the manifest")
    return sdk_data.load_inputs(root, scenario, entry["map_id"])


def analyse(probe: str, game: tm.Game, manifest: Mapping[str, Any], inputs: Any, commit: Optional[str],
            reference: Optional[tm.Game] = None, predicted: Optional[Mapping[str, Any]] = None,
            relax: Tuple[str, ...] = ()) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The registered analysis of one game. ``relax`` lists integrity checks a dry run on an adapted record may skip
    (named in the output); a registered run passes none. Raises :class:`tm.AnalysisRefused` on a refusal."""
    (seat,) = game.seats_of(tp.CANDIDATE_ID)
    faction = game.seats[seat][0]
    i1 = tm.integrity_record(game, manifest, commit)
    i2 = tm.integrity_capture(game)
    if i1 and "I1" not in relax:
        raise tm.AnalysisRefused("I1: " + "; ".join(i1))
    if i2 and "I2" not in relax:
        raise tm.AnalysisRefused("I2: " + "; ".join(i2))
    counts = tm.three_way(game, seat)
    order_list = tm.orders(game, seat)
    fresh = tm.fresh_feedback(game.steps)
    costs = MoveCosts.from_raw(inputs.cost)
    redecider = Redecider(game, costs)
    first_k = order_list[0].k if order_list else -1
    horizon = (first_k if order_list else game.last_k) if probe == "P-A" else -1
    snaps = tm.series(game, None if "I5" in relax else redecider, digests_until=horizon)
    if redecider.problems:
        raise tm.AnalysisRefused("; ".join(redecider.problems[:5]))
    found = {(s, k, u) for s, k, u in redecider.activations}
    expected = {(o.seat, o.k, o.unit) for o in order_list}
    if found != expected and "I5" not in relax:
        raise tm.AnalysisRefused(f"I5: the pool predicate finds {len(found)} orders, the capture {len(expected)}; "
                                 f"{len(found - expected)} only in the predicate, {len(expected - found)} only captured")
    affected = sorted({o.unit for o in order_list})
    channel = tm.channel_check(snaps, seat, affected, first_k if order_list else 0)
    records = ep.outcomes(game, snaps, order_list, fresh)
    i6 = ep.check_reconstruction(records, ep.reconstruct(snaps, seat, order_list))
    feedback = ep.order_feedback(game, order_list, fresh)
    result: Dict[str, Any] = {
        "integrity": {"ok": not i1 and not i2, "I1": i1, "I2": i2, "I3": counts, "I4": channel,
                      "I5": dict(redecider.counts, pool_predicate_orders=len(found)), "I6": i6,
                      "relaxed_for_dry_run": list(relax)},
        "S1": ep.s1(feedback), "E1": ep.e1(feedback), "E2": ep.e2(records), "primary": ep.primary(records),
        "S2": ep.s2(snaps, order_list), "E3a": ep.e3a(snaps, records),
        "E3b": ep.e3b(game, snaps, [seat], fresh), "E5": ep.e5(game, snaps, order_list, records, fresh)}
    m = tv.MapData(inputs.basic, inputs.see)
    seat_of = {f: s for s, (f, _) in game.seats.items()}
    e4 = ep.e4_game(m, snaps, seat_of)
    if probe == "P-A":
        ref_snaps = tm.series(reference, digests_until=horizon) if reference is not None else {}
        units_ok = None
        if predicted is not None and order_list:
            units_ok = sorted(o.unit for o in order_list if o.k == first_k) == predicted["first"]
        inert = next(s for s, (_, p) in game.seats.items() if p != tp.CANDIDATE_ID)
        first = manifest["reference"]["predicted_orders"][0]
        result["S3"] = ep.s3(game, snaps, reference, ref_snaps, seat, inert, order_list, units_ok, first["k"],
                             first["units"])
        result["E6"] = ep.e6(snaps, ref_snaps, game, reference, result["S3"]["s3a_premise"], records,
                             order_list[0].k if order_list else None)
        result["E4_descriptive"] = {k: v for k, v in e4.items() if k != "private"}
    else:
        result["S4"] = ep.s4(game, seat)
        result["E4"] = {k: v for k, v in e4.items() if k != "private"}
        result["E4"].update(ep.e4_verdicts([e4]))
    result["orders"] = [{"outcome": r["outcome"], "d": r["d"], "timer_start_offset": None if r["timer_start"] is None
                         else r["timer_start"] - r["cur_step"]} for r in records]
    public = {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "probe": probe, "game_id": game.game_id,
              "session": game.record.get("session"), "steps": game.record.get("steps"),
              "status": game.record.get("status"), "candidate_seat_faction": faction, **_strip(result)}
    private = {"orders": records, "order_feedback": feedback, "S2": result["S2"], "E3a": result["E3a"],
               "E3b": result["E3b"], "E5": result["E5"], "E4_rows": e4["private"],
               "S3": result.get("S3"), "E6": result.get("E6")}
    return public, private


def _strip(result: Mapping[str, Any]) -> Dict[str, Any]:
    """The public form: no unit ids, hexes or per-event rows."""
    out = json.loads(json.dumps(result, default=str))
    for name in ("S2",):
        out[name] = {"verdict": out[name]["verdict"], "units": out[name].get("units"),
                     "violations": [{k: v for k, v in x.items() if k != "unit"} for x in out[name].get("violations", ())],
                     "transients": [{k: v for k, v in x.items() if k != "unit"} for x in out[name].get("transients", ())]}
    if "E3a" in out:
        for key in ("losses", "transients"):
            out["E3a"][key] = [{k: v for k, v in x.items() if k != "unit"} for x in out["E3a"].get(key, ())]
    for name in ("E3b", "E5"):
        if name in out:
            out[name].pop("event_list", None)
    if "S3" in out:
        for item in out["S3"].get("after_first_order", ()):
            item.pop("probe", None)
            item.pop("reference", None)
    if "E6" in out:
        for item in out["E6"].get("first_difference", ()):
            if "units" in item:
                item["units"] = len(item["units"])
    return out


# ----------------------------------------------------------------------------------------------
# Gate, stop branch, pooling


def installation_ok(installation: Mapping[str, Any], identities: Mapping[str, Any]) -> Dict[str, Any]:
    checks = {"integrity": bool(installation["integrity"]["ok"]), "state continuous": bool(installation["state_continuous"]),
              "no unclosed session": not installation["unclosed_session"],
              "identities": all(identities["checks"].values())}
    return {"ok": all(checks.values()), "checks": checks, "sessions_opened": installation["sessions_opened"]}


def pool(results: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    played = [p for p in ("P-A", "P-B1", "P-B2") if p in results]
    pb = [results[p]["E4"] for p in ("P-B1", "P-B2") if p in results]
    e4 = ep.e4_verdicts(pb) if pb else {"E4a": {"verdict": tm.NOT_TESTED}, "E4b": {"verdict": tm.NOT_TESTED}}
    merged = dict(results)
    merged["pooled_e4"] = e4
    primary = collections.Counter()
    for p in played:
        for key in ("orders", "reached_within_76", "censored", "interrupted", "failed"):
            primary[key] += results[p]["primary"][key]
    share = primary["reached_within_76"] / primary["orders"] if primary["orders"] else None
    return {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": "pooled", "games_played": played,
            "primary": dict(primary, share=share, criterion_100_percent=bool(primary["orders"])
                            and primary["reached_within_76"] == primary["orders"]),
            "E4": e4, "disposition": ep.disposition(merged, played)}


# ----------------------------------------------------------------------------------------------
# Dry runs on real records


def adapt_reference(game: tm.Game) -> tm.Game:
    """The reference game in the probe capture's form: its batch as the pre-execution copies (baseline-v2 actions are
    not rewritten in place) and a t7 block carrying its recorded trace digest and no order."""
    steps = []
    for k in sorted(game.steps):
        step = dict(game.steps[k])
        step["submitted"] = [dict(b, action=dict(b["action"])) for b in step["batch"]]
        step["t7"] = {"11": {"baseline_trace_sha256": step["traces"]["11"], "added": [], "skipped": [], "error": None}}
        step["rewritten_in_place"] = 0
        steps.append(step)
    compact = dict(game.compact, steps=steps, t7_capture_schema=tp.CAPTURE_SCHEMA)
    seats = {1: (0, "inert-v0"), 11: (1, tp.CANDIDATE_ID)}
    record = json.loads(json.dumps(game.record))
    for s in record["seats"]:
        if s["seat"] == 11:
            s["policy"] = tp.CANDIDATE_ID
    return tm.Game(game.game_id, record, compact, game.windows, seats)


def dryrun() -> Dict[str, Any]:
    out: Dict[str, Any] = {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": "dry run on real records"}
    # the registered manifest pins this output, so the dry run builds the parts the analysis reads from the
    # registration module instead of reading the manifest
    manifest = {"policies": {}, "execution": {"runtime": tp.RUNTIME},
                "reference": {"predicted_orders": [{"k": tp.PREDICTED_FIRST_K, "units": tp.PREDICTED_FIRST_UNITS}]}}
    ref = reference_game()
    inputs = inputs_for(DATA, "1910631192", "92")
    adapted = adapt_reference(ref)
    public, _ = analyse("P-A", adapted, manifest, inputs, None, reference=ref, relax=("I1", "I2", "I5"))
    out["P-A analysis on the reference game"] = {k: public[k] for k in (
        "integrity", "S1", "E1", "E2", "primary", "S2", "E3a", "E3b", "E5", "S3", "E6")}
    reps = {}
    for rep in ("x01", "x02", "x03"):
        path = SCREEN_WORK / "games" / f"1910631192.C3.b.{rep}.json"
        if path.exists():
            r = json.loads(path.read_text(encoding="utf-8"))
            same_state = r["state_steps"] == ref.record["state_steps"]
            traces = {s["seat"]: s["trace_steps"] for s in r["seats"]}
            rtraces = {s["seat"]: s["trace_steps"] for s in ref.record["seats"]}
            reps[rep] = {"state_digests_equal": same_state, "trace_digests_equal": traces == rtraces,
                         "final_scores_equal": r["final_scores"] == ref.record["final_scores"], "steps": r["steps"]}
    out["reference determinism against the Sprint 1 repetitions"] = reps
    for header, entry, by_step in h0_games({"2120531121"}):
        inputs2 = inputs_for(DATA, "2120531121", header["map_id"])
        m = tv.MapData(inputs2.basic, inputs2.see)
        snaps = {}
        seats = {1: (0, "baseline-v0"), 11: (1, "baseline-v0")}
        for step in sorted(by_step):
            views = by_step[step]
            if set(views) != {0, 1}:
                continue
            units = [u for f in (0, 1) for u in views[f].get("operators") or () if u.get("color") == f]
            glob = {"operators": units, "time": views[0].get("time"), "cities": views[0].get("cities"),
                    "scores": views[0].get("scores"),
                    "valid_actions": {**(views[0].get("valid_actions") or {}), **(views[1].get("valid_actions") or {})}}
            snaps[step] = tm.snap_of(step, (views[0].get("time") or {}).get("cur_step"), glob, {1: views[0], 11: views[1]},
                                     seats)
        e4 = ep.e4_game(m, snaps, {0: 1, 1: 11})
        out["E4 machinery on the H0 game of 2120531121"] = {k: v for k, v in e4.items() if k != "private"}
        out["E4 machinery on the H0 game of 2120531121"].update(ep.e4_verdicts([e4]))
    return out


# ----------------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("calibrate", "premise", "equivalence", "dryrun"):
        p = sub.add_parser(name)
        p.add_argument("--check", action="store_true")
    g = sub.add_parser("game")
    g.add_argument("--probe", required=True, choices=sorted(PROBES))
    g.add_argument("--work", type=Path, default=WORK)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--private", type=Path, required=True)
    g.add_argument("--commit")
    for name, key in (("gate", "--pa"), ("stop", "--pb1")):
        p = sub.add_parser(name)
        p.add_argument(key, type=Path, required=True)
        p.add_argument("--installation", type=Path, required=True)
        p.add_argument("--identities", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("pool")
    p.add_argument("--pa", type=Path, required=True)
    p.add_argument("--pb1", type=Path)
    p.add_argument("--pb2", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "calibrate":
        return write_or_check(OUT / "calibration.json", calibrate(), args.check)
    if args.command == "premise":
        public, private = premise()
        status = write_or_check(OUT / "premise.json", public, args.check)
        private_text = dump(private)
        if args.check:
            if PREMISE_PRIVATE.read_text(encoding="utf-8") != private_text:
                print(f"{PREMISE_PRIVATE} differs", file=sys.stderr)
                return 1
        else:
            PREMISE_PRIVATE.parent.mkdir(parents=True, exist_ok=True)
            PREMISE_PRIVATE.write_text(private_text, encoding="utf-8", newline="\n")
        print(f"private premise SHA-256 {hashlib.sha256(private_text.encode('utf-8')).hexdigest()}")
        return status
    if args.command == "equivalence":
        return write_or_check(OUT / "equivalence.json", equivalence(), args.check)
    if args.command == "dryrun":
        return write_or_check(OUT / "dryrun.json", dryrun(), args.check)
    if args.command == "game":
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        spec = PROBES[args.probe]
        try:
            game = tm.load(args.work, spec["game_id"])
            inputs = staged_inputs(manifest, args.work, spec["scenario_id"])
            reference = predicted = None
            if args.probe == "P-A":
                reference = reference_game()
                text = PREMISE_PRIVATE.read_text(encoding="utf-8")
                pinned = manifest["inputs"]["premise_private_sha256"]
                if hashlib.sha256(text.encode("utf-8")).hexdigest() != pinned:
                    raise tm.AnalysisRefused("the private premise file does not match its registered digest")
                for name, path in (("reference_record_sha256", REFERENCE / "games" / f"{tp.REFERENCE_GAME}.json"),
                                   ("reference_capture_sha256", REFERENCE / "capture" / f"{tp.REFERENCE_GAME}.capture.json"),
                                   ("reference_windows_sha256", REFERENCE / "capture" / f"{tp.REFERENCE_GAME}.windows.pkl")):
                    if sha256_file(path) != manifest["inputs"][name]:
                        raise tm.AnalysisRefused(f"{path.name} does not match its registered digest")
                predicted = json.loads(text)
            public, private = analyse(args.probe, game, manifest, inputs, args.commit, reference, predicted)
        except tm.AnalysisRefused as exc:
            refusal = {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "probe": args.probe, "refused": str(exc)}
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(dump(refusal), encoding="utf-8", newline="\n")
            print(f"REFUSED: {exc}", file=sys.stderr)
            return 3
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(dump(public), encoding="utf-8", newline="\n")
        args.private.parent.mkdir(parents=True, exist_ok=True)
        args.private.write_text(dump(private), encoding="utf-8", newline="\n")
        print(f"wrote {args.out} and {args.private}")
        return 0
    if args.command in ("gate", "stop"):
        result = json.loads((args.pa if args.command == "gate" else args.pb1).read_text(encoding="utf-8"))
        inst = installation_ok(json.loads(args.installation.read_text(encoding="utf-8")),
                               json.loads(args.identities.read_text(encoding="utf-8")))
        if "refused" in result:
            decision = {"refused": result["refused"], "continue": False}
        elif args.command == "gate":
            decision = ep.gate_pa(result, inst["ok"])
        else:
            decision = ep.stop_after_pb1(result, inst["ok"])
        payload = {"schema": SCHEMA, "probe_id": tp.PROBE_ID, "part": args.command, "installation": inst, **decision}
        args.out.write_text(dump(payload), encoding="utf-8", newline="\n")
        print(dump(payload))
        return 0
    if args.command == "pool":
        results = {"P-A": json.loads(args.pa.read_text(encoding="utf-8"))}
        for name, path in (("P-B1", args.pb1), ("P-B2", args.pb2)):
            if path is not None:
                results[name] = json.loads(path.read_text(encoding="utf-8"))
        args.out.write_text(dump(pool(results)), encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
