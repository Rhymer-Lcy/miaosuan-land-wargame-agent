"""Independent cross-check of the E3b configuration search (``t7-e3b-search-1``, protocol section 7).

    python scripts/t7_e3b_crosscheck.py

Written separately from ``scripts/t7_e3b_search.py`` and ``evaluation/t7_e3b.py``, and sharing neither their episode
rules nor their loaders: the trigger is the Sprint 5 pool predicate (``evaluation/t7_candidates.py``, ``a2``) instead
of the frozen candidate; continuity is read from the all-seeing state (the seat view in the replay corpus, which has no
other) and from the engine's own ``judge_info`` instead of the capture's judge delta; the later command is read from
the batch serialised after the step instead of the pre-execution copies; echoes and execution are recomputed. It
recounts, per dataset, the episodes by class (unconditional and conditional) and the W episodes by category, and
writes ``evaluation/t7-e3b-search-1/crosscheck.json``. Only the frozen inputs are read (their digests are verified).
"""

from __future__ import annotations

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
from miaosuan_agent.boundary import MoveCosts, Observation, Origin  # noqa: E402
from miaosuan_agent.decision import Memory, digest  # noqa: E402
from miaosuan_agent.decision.policy import BaselinePolicy  # noqa: E402
from miaosuan_agent.evaluation import t7_candidates as tc  # noqa: E402
from miaosuan_agent.experiments.deployment_split import DeploymentSplitPolicy  # noqa: E402
from miaosuan_agent.experiments.shoot_reservation import ShootReservationPolicy  # noqa: E402

OUT = REPO_ROOT / "evaluation" / "t7-e3b-search-1"
EVAL = REPO_ROOT / "local" / "evaluation"
DATA = EVAL / "baseline-v1-variance-study-1" / "data"
LIMIT = 75
TIMER_FIELDS = ("change_state_remain_time", "move_to_stop_remain_time", "weapon_unfold_time", "get_on_remain_time",
                "get_off_remain_time")
#: Datasets: (id, folder, games, seat, best category). Kept as literal data here, not imported from the search.
FULL = [("A-b", "t1r-diagnosis-1", ["1910631192.C3.b.x01"], 11, "A"),
        ("A-pb1", "t7-mechanism-probe-1", ["2120531121.H1.pb1"], 11, "A"),
        ("A-pb2", "t7-mechanism-probe-1", ["2120531121.H2.pb2"], 1, "A"),
        ("B-c", "t1r-diagnosis-1", ["1910631192.C3.c.x01"], 11, "B"),
        ("B-p2", "ps1-engine-probe-1", ["1930331196.C2.p2"], 1, "B")]
SPARSE = [("B-r516", "baseline-v2-residual-516-diagnostic-1", [f"1930331196.C3.d{i:02d}" for i in range(1, 33)], 11),
          ("B-smoke", "tactical-screen-deployment-split-1-smoke",
           [f"{s}.C2.c.s01" for s in ("1910631192", "1930331196", "2010131194", "2010211129", "201033019601",
                                      "2010431153", "2120531121", "2130511121")], 1)]


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def check_frozen() -> Dict[str, Any]:
    frozen = json.loads((OUT / "inputs.json").read_text(encoding="utf-8"))
    for ds in frozen["datasets"]:
        entries = [e for g in ds.get("games", ()) for e in g["files"].values()] + list(ds.get("files", ()))
        for e in entries:
            if file_digest(REPO_ROOT / e["path"]) != e["sha256"]:
                raise SystemExit(f"frozen input changed: {e['path']}")
    return frozen


def is_conceal(a: Mapping[str, Any]) -> bool:
    return a.get("type") == 6 and a.get("target_state") == 4


def ops(raw: Mapping[str, Any]) -> Dict[int, Mapping[str, Any]]:
    return {u["obj_id"]: u for u in raw.get("operators") or () if isinstance(u, Mapping) and isinstance(u.get("obj_id"), int)}


def listed(raw: Mapping[str, Any]) -> Dict[int, Dict[int, Any]]:
    out: Dict[int, Dict[int, Any]] = {}
    for key, acts in (raw.get("valid_actions") or {}).items():
        try:
            uid = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(acts, Mapping):
            out[uid] = {int(t): v for t, v in acts.items() if str(t).lstrip("-").isdigit()}
    return out


def enemy_visible(raw: Mapping[str, Any], faction: int) -> bool:
    return any(u.get("color") != faction for u in ops(raw).values())


class Row:
    """What this check needs of one decision: units (by id, raw), enemy hexes, judge ids, actions by unit."""

    __slots__ = ("k", "t", "units", "enemy", "judged", "acts", "att")

    def __init__(self, k, t, units, enemy, judged, acts, att=frozenset()):
        self.k, self.t, self.units, self.enemy, self.judged, self.acts, self.att = k, t, units, enemy, judged, acts, att


def broken(u0: Mapping[str, Any], u: Optional[Mapping[str, Any]], row: Row) -> Tuple[Optional[str], bool]:
    """(reason, evidence missing) for the unit at a row."""
    if u is None:
        return "gone", False
    needed = [u.get("blood"), u.get("cur_hex"), u.get("stop"), u.get("keep"), u.get("move_path")]
    needed += [u.get(f) for f in TIMER_FIELDS]
    if any(v is None for v in needed) or not isinstance(u.get("move_path"), list):
        return None, True
    if u.get("on_board") not in (0, None, False):
        return "boarded", False
    if u["blood"] != u0.get("blood") or u["cur_hex"] != u0.get("cur_hex"):
        return "changed", False
    if u["move_path"] or u["stop"] != 1 or u["keep"] != 0 or u.get("flag_force_stop") == 1:
        return "changed", False
    if any(u.get(f) != 0 for f in TIMER_FIELDS):
        return "changed", False
    if u["cur_hex"] in row.enemy or u["obj_id"] in row.judged:
        return "contact", False
    return None, False


def scan(rows: List[Row], i0: int, uid: int) -> Dict[str, Any]:
    u0 = rows[i0].units[uid]
    gaps = 0
    for i in range(i0 + 1, len(rows)):
        row = rows[i]
        if row.t != rows[i - 1].t + 1:
            gaps += 1
        reason, missing = broken(u0, row.units.get(uid), row)
        gaps += missing
        dist = row.t - rows[i0].t
        if reason:
            return {"cls": f"DT {'after' if dist >= LIMIT else 'during'} the transition", "end": i, "d": dist,
                    "gaps": gaps}
        act = row.acts.get(uid)
        if act is not None:
            t = act.get("type")
            cls = ("W" if dist >= LIMIT else "TI") if t in (1, 2) else f"OA type {t}"
            return {"cls": cls, "end": i, "d": dist, "gaps": gaps, "action": act}
    dist = rows[-1].t - rows[i0].t
    return {"cls": f"CE {'after' if dist >= LIMIT else 'during'} the transition", "end": None, "d": dist, "gaps": gaps}


def episodes(rows: List[Row], orders: Dict[int, List[int]]) -> List[Dict[str, Any]]:
    at = {r.k: i for i, r in enumerate(rows)}
    out = []
    for uid in sorted(orders):
        prev = None
        for k in sorted(orders[uid]):
            if prev is not None and (prev["end"] is None or at[k] <= prev["end"]):
                continue
            ep = scan(rows, at[k], uid)
            ep.update(unit=uid, i0=at[k], conditional=prev is not None)
            out.append(ep)
            prev = ep
    return out


def costs(scenario: str, map_id: str) -> MoveCosts:
    return MoveCosts.from_raw(sdk_data.load_inputs(DATA / scenario / "Data", scenario, map_id).cost)


def tally(eps: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    out = {"unconditional": collections.Counter(), "conditional": collections.Counter()}
    for e in eps:
        out["conditional" if e["conditional"] else "unconditional"][e["cls"]] += 1
    return {k: dict(sorted(v.items())) for k, v in out.items()}


def full(folder: str, game: str, seat: int, best: str) -> Tuple[Dict[str, Dict[str, int]], collections.Counter]:
    compact = json.loads((EVAL / folder / "capture" / f"{game}.capture.json").read_text(encoding="utf-8"))
    with (EVAL / folder / "capture" / f"{game}.windows.pkl").open("rb") as f:
        win = pickle.load(f)
    steps = {s["k"]: s for s in compact["steps"]}
    players = {p["seat"]: (p["faction"], p["policy"]) for p in compact["setup"]["players"]}
    faction, policy = players[seat]
    samples = sorted(win["samples"], key=lambda s: s["k"])
    rows: List[Row] = []
    orders: Dict[int, List[int]] = collections.defaultdict(list)
    memory = tc.SeatMemory()
    policy_obj, redecided, total = None, 0, 0
    for s in samples:
        entry = s["seats"].get(seat) or s["seats"].get(str(seat))
        raw, glob = pickle.loads(entry["observation"]), pickle.loads(s["global"])
        if policy_obj is None:
            c = costs(game.split(".")[0], str(glob.get("terrain_id")))
            policy_obj = {"baseline-v2-candidate-shoot-target-reservation": ShootReservationPolicy,
                          "tactic-deployment-split-1": DeploymentSplitPolicy}[policy](c)
        batch = [b["action"] for b in steps[s["k"]].get("batch") or () if b["seat"] == seat]
        d = policy_obj.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, pickle.loads(entry["memory"]))
        total += 1
        redecided += [dict(a) for a in d.actions] == [dict(a) for a in batch] and digest(d.trace) == steps[s["k"]]["traces"][str(seat)]
        play = (raw.get("time") or {}).get("stage") == 2
        acts = {}
        for a in batch:
            if isinstance(a.get("obj_id"), int) and a["obj_id"] not in acts and not is_conceal(a):
                acts[a["obj_id"]] = a
        t = (raw.get("time") or {}).get("cur_step")
        if play:
            lst = listed(raw)
            vis = enemy_visible(raw, faction)
            for uid, u in sorted(ops(raw).items()):
                if u.get("color") == faction and tc.a2(u, lst.get(uid, {}), acts.get(uid), vis, t, memory):
                    orders[uid].append(s["k"])
        everything = ops(glob)
        own = {uid: u for uid, u in everything.items() if u.get("color") == faction}
        enemy = {u.get("cur_hex") for u in everything.values() if u.get("color") != faction}
        judged, att = set(), set()
        for r in glob.get("judge_info") or ():
            if isinstance(r, Mapping):
                judged.update((r.get("att_obj_id"), r.get("target_obj_id")))
                att.add(r.get("att_obj_id"))
        if play:
            rows.append(Row(s["k"], t, own, enemy, judged, acts, frozenset(att)))
    final = win.get("final")
    if final:
        glob = pickle.loads(final["global"])
        everything = ops(glob)
        judged, att = set(), set()
        for r in glob.get("judge_info") or ():
            if isinstance(r, Mapping):
                judged.update((r.get("att_obj_id"), r.get("target_obj_id")))
                att.add(r.get("att_obj_id"))
        rows.append(Row(final["k"], final["cur_step"], {u: x for u, x in everything.items() if x.get("color") == faction},
                        {x.get("cur_hex") for x in everything.values() if x.get("color") != faction}, judged, {},
                        frozenset(att)))
    eps = episodes(rows, orders)
    categories = collections.Counter()
    for e in eps:
        if e["cls"] != "W":
            continue
        row = rows[e["end"]]
        act = e["action"]
        step = steps[row.k]
        prev_step = steps.get(row.k - 1)
        fb = list(step.get("feedback") or ())
        if prev_step is not None and prev_step["cur_step"] == step["cur_step"]:
            fb = []  # the clock stood still: no entry of this step is new (never the case in play)
        echo = []
        for entry in fb:
            msg = entry.get("message") or {}
            if (msg.get("obj_id"), msg.get("type"), msg.get("actor")) == (act.get("obj_id"), act.get("type"), act.get("actor")):
                if act.get("type") == 1 and list(msg.get("move_path") or []) != list(act.get("move_path") or []):
                    continue
                if act.get("type") == 2 and (msg.get("target_obj_id"), msg.get("weapon_id")) != (
                        act.get("target_obj_id"), act.get("weapon_id")):
                    continue
                echo.append(entry)
        ok_echo = len(echo) == 1 and not echo[0].get("error")
        nxt = rows[e["end"] + 1] if e["end"] + 1 < len(rows) else None
        if act.get("type") == 2:
            done = nxt is not None and e["unit"] in nxt.att  # the engine's judge records of the command's step
        else:
            path = list(act.get("move_path") or [])
            later = nxt.units.get(e["unit"]) if nxt is not None else None
            done = bool(path) and later is not None and (later.get("cur_hex") == path[0] or (
                bool(later.get("move_path")) and later["move_path"] == path[len(path) - len(later["move_path"]):]))
        category = "A" if best == "A" and redecided == total and e["gaps"] == 0 and ok_echo and done else "B"
        categories[f"{category} {'conditional' if e['conditional'] else 'unconditional'}"] += 1
    return tally(eps), categories


def sparse(folder: str, game: str, seat: int) -> List[str]:
    compact = json.loads((EVAL / folder / "capture" / f"{game}.capture.json").read_text(encoding="utf-8"))
    with (EVAL / folder / "capture" / f"{game}.windows.pkl").open("rb") as f:
        win = pickle.load(f)
    steps = {s["k"]: s for s in compact["steps"]}
    players = {p["seat"]: (p["faction"], p["policy"]) for p in compact["setup"]["players"]}
    faction, policy = players[seat]
    last = max(steps)
    labels, busy = [], {}
    policy_obj = None
    for s in sorted(win["samples"], key=lambda x: x["k"]):
        entry = s["seats"].get(seat) or s["seats"].get(str(seat))
        raw = pickle.loads(entry["observation"])
        if (raw.get("time") or {}).get("stage") != 2:
            continue
        if policy_obj is None:
            c = costs(game.split(".")[0], str(pickle.loads(s["global"]).get("terrain_id")))
            policy_obj = {"baseline-v2-candidate-shoot-target-reservation": ShootReservationPolicy,
                          "tactic-deployment-split-1": DeploymentSplitPolicy}[policy](c)
        d = policy_obj.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, pickle.loads(entry["memory"]))
        if [dict(a) for a in d.actions] != [dict(a) for a in entry["actions"]] or                 digest(d.trace) != steps[s["k"]]["traces"][str(seat)]:
            continue  # the snapshot's decision is not reproduced: no trigger evaluated there
        acts = {}
        for a in entry["actions"]:
            if isinstance(a.get("obj_id"), int) and a["obj_id"] not in acts:
                acts[a["obj_id"]] = a
        lst, vis = listed(raw), enemy_visible(raw, faction)
        t0 = s["cur_step"]
        for uid, u in sorted(ops(raw).items()):
            if u.get("color") != faction or not tc.a2(u, lst.get(uid, {}), acts.get(uid), vis, t0, tc.SeatMemory()):
                continue
            if uid in busy and (busy[uid] is None or s["k"] <= busy[uid]):
                continue
            conditional = uid in busy
            label, end = None, None
            k = s["k"]
            while k <= last and label is None:
                st = steps[k]
                if k > s["k"]:
                    mine = [b["action"] for b in st.get("batch") or () if b["seat"] == seat and b["action"].get("obj_id") == uid]
                    if mine:
                        t, dist = mine[0].get("type"), st["cur_step"] - t0
                        label = ("W" if dist >= LIMIT else "TI") if t in (1, 2) else "OA"
                        end = k
                        break
                hit = any(r.get("att_obj_id") == uid or r.get("target_obj_id") == uid for r in st.get("judge_new") or ())
                hit = hit or str(uid) in (st.get("changed") or {}) or uid in (st.get("gone") or []) or uid in (st.get("boarded") or [])
                if hit:
                    dist = st["cur_step"] + 1 - t0
                    label, end = f"DT {'after' if dist >= LIMIT else 'during'} the transition", k + 1
                    break
                k += 1
            if label is None:
                dist = steps[last]["cur_step"] + 1 - t0
                label = f"CE {'after' if dist >= LIMIT else 'during'} the transition"
            busy[uid] = end if not label.startswith("CE") else None
            labels.append(("conditional " if conditional else "") + label)
    return labels


def h0(frozen: Mapping[str, Any]) -> Tuple[Dict[str, Dict[str, int]], int]:
    corpus = next(ds for ds in frozen["datasets"] if ds["id"] == "C-h0")
    all_eps, w = [], 0
    for e in corpus["files"]:
        with gzip.open(REPO_ROOT / e["path"], "rt", encoding="utf-8") as f:
            header = json.loads(next(f))
            data = [json.loads(x) for x in f]
        c = costs(header["scenario_id"], header["map_id"])
        for seat in sorted({r["seat"] for r in data}):
            seat_rows = sorted((r for r in data if r["seat"] == seat), key=lambda r: r["step"])
            faction = seat_rows[0]["faction"]
            v0, v2 = BaselinePolicy(c), ShootReservationPolicy(c)
            m0, m2, memory = Memory(), Memory(), tc.SeatMemory()
            rows: List[Row] = []
            orders: Dict[int, List[int]] = collections.defaultdict(list)
            for r in seat_rows:
                raw = typed_json.decode(r["observation"])
                d0 = v0.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, m0)
                m0 = d0.memory
                d2 = v2.decide(Observation.from_raw(raw, Origin.ENGINE), seat, faction, m2)
                m2 = d2.memory
                if (raw.get("time") or {}).get("stage") != 2:
                    continue
                exact = [dict(a) for a in d0.actions] == [dict(a) for a in r["actions"]]
                if exact and [dict(a) for a in d2.actions] != [dict(a) for a in d0.actions]:
                    info = d2.trace.to_dict()
                    flagged = {x["obj_id"] for x in info.get("suppressed", [])} | {
                        x["obj_id"] for x in info.get("shoot_reserved", []) if x["effect"] != "unchanged"}
                    by0 = {a.get("obj_id", "seat"): dict(a) for a in d0.actions}
                    by2 = {a.get("obj_id", "seat"): dict(a) for a in d2.actions}
                    exact = all(by0.get(u) == by2.get(u) or u in flagged for u in set(by0) | set(by2))
                acts = {}
                for a in d2.actions:
                    if isinstance(a.get("obj_id"), int) and a["obj_id"] not in acts:
                        acts[a["obj_id"]] = dict(a)
                t = (raw.get("time") or {}).get("cur_step")
                lst, vis = listed(raw), enemy_visible(raw, faction)
                for uid, u in sorted(ops(raw).items()):
                    if u.get("color") == faction and tc.a2(u, lst.get(uid, {}), acts.get(uid), vis, t, memory):
                        orders[uid].append(r["step"])
                everything = ops(raw)
                judged = set()
                for j in raw.get("judge_info") or ():
                    if isinstance(j, Mapping):
                        judged.update((j.get("att_obj_id"), j.get("target_obj_id")))
                rows.append(Row(r["step"], t, {u: x for u, x in everything.items() if x.get("color") == faction},
                                {x.get("cur_hex") for x in everything.values() if x.get("color") != faction}, judged,
                                acts if exact else {}))
            eps = episodes(rows, orders)
            all_eps += eps
            w += sum(1 for x in eps if x["cls"] == "W")
    return tally(all_eps), w


def main() -> int:
    frozen = check_frozen()
    out: Dict[str, Any] = {"schema": "miaosuan-t7-e3b-crosscheck/1", "study_id": "t7-e3b-search-1", "datasets": {}}
    for ds, folder, games, seat, best in FULL:
        classes, categories = full(folder, games[0], seat, best)
        out["datasets"][ds] = {"classes": classes, "W_categories": dict(sorted(categories.items()))}
    for ds, folder, games, seat in SPARSE:
        labels = collections.Counter()
        for g in games:
            labels.update(sparse(folder, g, seat))
        w = sum(v for k, v in labels.items() if k.endswith("W"))
        cond = sum(v for k, v in labels.items() if k == "conditional W")
        cats = {k: v for k, v in (("B unconditional", w - cond), ("B conditional", cond)) if v}
        out["datasets"][ds] = {"classes": dict(sorted(labels.items())), "W_categories": cats}
    classes, w = h0(frozen)
    cond = classes["conditional"].get("W", 0)
    out["datasets"]["C-h0"] = {"classes": classes,
                               "W_categories": {k: v for k, v in (("C unconditional", w - cond), ("C conditional", cond)) if v}}
    text = json.dumps(out, indent=1, sort_keys=True) + "\n"
    (OUT / "crosscheck.json").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
