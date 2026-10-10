"""Sprint 36 reconstruction of recorded live games (``docs/SPRINT36_TACTICAL_RECOVERY.md`` section 5).

    python scripts/s36_reconstruct.py --data DIR --card CARD --positions N [N ...] --out FILE [--shadow NAME ...]

For each recorded position of a live card (Sprint 34 ``s34-integrated-live-1`` or Sprint 35 ``s35-coalition-live-1``)
the policy under test is re-decided from its recorded observations with its own memory chain (a fresh agent; every
re-decided action set must equal the submitted one, else the game is reported unreconstructable), and each named shadow
policy decides the same observations with its own memory chain (open loop: the shadow's actions never reach the
recorded trajectory, so a shadow difference is a decision difference at that state, never an outcome). From the
all-seeing compact timeline it extracts, per game:

* objective ownership changes; for every loss of an objective the side held: the standing defenders at the last held
  step and 150 steps before (their plan module, kind and reason), their fate, the enemy ground units in the zone, the
  stance of the objective (Sprint 35 candidate) at 300, 150 and 0 steps before, the free units of the seat;
* waiting runs (a ground unit with a path and zero speed): duration, the plan that issued the path, the own units
  standing on the blocking hex and their plans;
* destroyed own ground units: where (zone, moving, aboard), their last plan, the stance of their zone's objective;
* stance counts (capture opportunities skipped, delays, holds), guided-fire listings and use;
* the first decision at which each shadow differs from the policy under test, and the differing units' modules.

Output is PRIVATE (unit ids and hexes; written under ``local/``); ``scripts/s36_episodes.py`` publishes aggregates.
"""

from __future__ import annotations

import argparse
import collections
import json
import multiprocessing as mp
import pickle
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.evaluation.s36_capture import wait_cause  # noqa: E402

STANCE_ROW = re.compile(r"^objective (\d+): (\w+) threat ([\d.]+) \(visible ([\d.]+)\) eta (\w+) defence ([\d.]+) "
                        r"want ([\d.]+) places (\d+) keep (\[.*?\]) withdraw (\[.*?\]): (.*)$")
GROUND = (1, 2)


def agent_for(name: str, seat: int, faction: int, cost: Any):
    """A fresh agent for a policy name: ``S34-MO`` (frozen Sprint 34), ``CM`` / ``CA`` (frozen Sprint 35), or a Sprint 36
    variant name (``tactical.config.VARIANTS``)."""
    from miaosuan_agent.integrated.agent import CommanderAgent
    from miaosuan_agent.integrated.config import LIVE as S34_LIVE
    if name == "S34-MO":
        agent = CommanderAgent(S34_LIVE)
    elif name in ("CM", "CA"):
        from miaosuan_agent.coalition.agent import CoalitionAgent
        from miaosuan_agent.coalition.config import VARIANTS
        agent = CoalitionAgent(VARIANTS[name])
    else:
        from miaosuan_agent.tactical.agent import TacticalAgent
        from miaosuan_agent.tactical.config import VARIANTS as T
        agent = TacticalAgent(T[name])
    agent.setup({"seat": seat, "faction": faction, "cost_data": cost})
    return agent


def key(action: Mapping[str, Any]) -> str:
    return json.dumps({str(k): v for k, v in dict(action).items()}, sort_keys=True)


def stances_of(trace: Any) -> Dict[int, Dict[str, Any]]:
    out = {}
    for row in getattr(trace, "diagnostics", ()) or ():
        m = STANCE_ROW.match(str(row))
        if m:
            out[int(m.group(1))] = {"stance": m.group(2), "threat": float(m.group(3)), "visible": float(m.group(4)),
                                    "eta": m.group(5), "defence": float(m.group(6)), "want": float(m.group(7)),
                                    "places": int(m.group(8)), "keep": json.loads(m.group(9)),
                                    "withdraw": json.loads(m.group(10).replace("(", "[").replace(")", "]")),
                                    "note": m.group(11)}
    return out


def plans_of(trace: Any) -> Dict[int, Tuple[str, str, int, int, str]]:
    return {p[0]: (p[1], p[2], p[3], p[4], p[5]) for p in getattr(trace, "plans", ()) or ()}


def policy_name(policy_id: str) -> str:
    if policy_id.startswith("s34-integrated"):
        return "S34-MO"
    if policy_id.startswith("s35-coalition-coalition-mission-planner"):
        return "CM"
    if policy_id.startswith("s35-coalition-coalition-allocator"):
        return "CA"
    if policy_id.startswith("s36-tactical-"):
        return policy_id[len("s36-tactical-"):].rsplit("-", 1)[0]
    raise ValueError(f"unknown policy under test {policy_id}")


def _zone(hex_: int) -> frozenset:
    from miaosuan_agent.integrated import facts as F
    return F.zone(hex_)


def _distance(a: int, b: int) -> int:
    from miaosuan_agent.integrated import facts as F
    return F.hex_distance(a, b)


def reconstruct(job: Tuple[str, str, int, Sequence[str]]) -> Dict[str, Any]:
    from miaosuan_agent import sdk_data
    from miaosuan_agent.boundary import Observation, Origin
    data, card, position, shadows = job
    work = REPO_ROOT / "local" / "evaluation" / card
    record_path = next((work / "games").glob(f"*.p{position:02d}.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    game_id = record["game_id"]
    compact = json.loads((work / "capture" / f"{game_id}.timeline.json").read_text(encoding="utf-8"))
    windows = pickle.load(open(work / "capture" / f"{game_id}.timeline.pkl", "rb"))
    tested = [s for s in record["seats"] if s["policy"] not in ("baseline-v2-candidate-shoot-target-reservation",
                                                                    "inert-v0")]
    if len(tested) != 1:
        raise ValueError(f"{game_id}: expected one policy under test, found {[s['policy'] for s in tested]}")
    seat, colour, policy_id = tested[0]["seat"], tested[0]["faction"], tested[0]["policy"]
    name = policy_name(policy_id)
    inputs = sdk_data.load_inputs(Path(data), record["scenario_id"], record["map_id"])
    agents = {n: agent_for(n, seat, colour, inputs.cost) for n in [name, *shadows]}
    samples = sorted(windows["samples"], key=lambda s: s["k"])
    decisions: Dict[int, Dict[str, Any]] = {}
    fidelity = {"decisions": 0, "differing": 0}
    first_diff: Dict[str, Optional[Dict[str, Any]]] = {n: None for n in shadows}
    diff_counts: Dict[str, collections.Counter] = {n: collections.Counter() for n in shadows}
    guided = {"steps_listed": 0, "units_listed": 0, "issued": 0}
    halted: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
    for sample in samples:
        snap = sample["seats"].get(str(seat))
        if snap is None:
            continue
        raw = pickle.loads(snap["observation"])
        step = sample["cur_step"]
        for u in raw.get("operators") or ():
            if u.get("color") == colour and u.get("move_path") and not u.get("speed") and u.get("type") in GROUND:
                halted[(step, u["obj_id"])] = (u["move_path"][0], int(bool(u.get("keep"))),
                                               int(bool(u.get("flag_force_stop"))))
        produced = {}
        for n, agent in agents.items():
            produced[n] = ([dict(a) for a in agent.step(raw)], agent.last_trace)
        actions, trace = produced[name]
        fidelity["decisions"] += 1
        same = sorted(key(a) for a in actions) == sorted(key(a) for a in snap["submitted"])
        fidelity["differing"] += not same
        listed = Observation.from_raw(raw, Origin.ENGINE).valid_actions()
        units_guided = [u for u, opts in listed.items() if 9 in opts]
        guided["steps_listed"] += bool(units_guided)
        guided["units_listed"] += len(units_guided)
        guided["issued"] += sum(1 for a in actions if a.get("type") == 9)
        plans = plans_of(trace)
        decisions[step] = {"actions": actions, "plans": plans, "stances": stances_of(trace),
                           "stats": dict(getattr(trace, "stats", ()) or ())}
        mine = {a.get("obj_id"): key(a) for a in actions}
        for n in shadows:
            theirs = {a.get("obj_id"): key(a) for a in produced[n][0]}
            units = sorted(u for u in set(mine) | set(theirs) if mine.get(u) != theirs.get(u))
            if units and (world_stage(raw) == 2):
                for u in units:
                    diff_counts[n][plans.get(u, ("outside the plans",))[0]] += 1
                if first_diff[n] is None:
                    first_diff[n] = {"step": step, "units": units,
                                     "tested": [plans.get(u) for u in units],
                                     "shadow": [plans_of(produced[n][1]).get(u) for u in units],
                                     "tested_actions": [mine.get(u) for u in units],
                                     "shadow_actions": [theirs.get(u) for u in units]}
    steps = [s for s in compact["steps"] if s["k"] >= 0]
    result = {"position": position, "card": card, "game_id": game_id, "scenario_id": record["scenario_id"],
              "condition": record["condition"], "policy": name, "seat": seat, "colour": colour,
              "scores": record["final_scores"], "fidelity": fidelity, "guided": guided,
              "first_difference": first_diff, "differing_units_by_tested_module": {n: dict(c) for n, c in
                                                                                   diff_counts.items()}}
    result.update(episodes(steps, decisions, colour, halted))
    return result


def world_stage(raw: Mapping[str, Any]) -> Any:
    return (raw.get("time") or {}).get("stage")


def plan_near(decisions: Mapping[int, Mapping[str, Any]], step: int, unit: int, back: int = 3):
    for b in range(0, back + 1):
        d = decisions.get(step - b)
        if d and unit in d["plans"]:
            return d["plans"][unit]
    return None


def stance_near(decisions: Mapping[int, Mapping[str, Any]], step: int, objective: int, back: int = 3):
    for b in range(0, back + 1):
        d = decisions.get(step - b)
        if d and objective in d["stances"]:
            return d["stances"][objective]
    return None


def episodes(steps: List[Mapping[str, Any]], decisions: Mapping[int, Mapping[str, Any]], colour: int,
             halted: Mapping[Tuple[int, int], Tuple[int, int, int]] = None) -> Dict[str, Any]:
    """Losses, waits, destroyed units and stance counts from the all-seeing timeline (unit rows: id, colour, type,
    sub_type, hex, path length, speed, blood, value, aboard)."""
    by_step = {s["cur_step"]: s for s in steps}
    order = [s["cur_step"] for s in steps]
    objectives = {c[0]: c[2] for c in steps[0]["cities"]}
    losses = []
    prev: Dict[int, Any] = {}
    for i, s in enumerate(steps):
        for coord, flag, value in s["cities"]:
            if prev.get(coord) == colour and flag != colour:
                losses.append(loss_episode(steps, i, coord, value, decisions, colour))
            prev[coord] = flag
    waits = wait_runs(steps, decisions, colour, halted or {})
    destroyed = []
    for i in range(len(steps) - 1):
        now = {r[0]: r for r in steps[i]["units"] if r[1] == colour and r[2] in GROUND}
        nxt = {r[0] for r in steps[i + 1]["units"] if r[1] == colour}
        for uid in sorted(set(now) - nxt):
            r = now[uid]
            zone_of = next((c for c in objectives if r[4] in _zone(c) and not r[9]), None)
            plan = plan_near(decisions, steps[i]["cur_step"], uid)
            st = stance_near(decisions, steps[i]["cur_step"], zone_of) if zone_of else None
            destroyed.append({"step": steps[i + 1]["cur_step"], "unit": uid, "sub_type": r[3], "value": r[8],
                              "where": "aboard" if r[9] else ("moving" if r[5] else
                                                              ("in zone" if zone_of else "standing elsewhere")),
                              "objective": zone_of, "plan": plan, "stance": st["stance"] if st else None})
    stance_counts = collections.Counter()
    skip_steps = collections.Counter()
    for step, d in decisions.items():
        for obj, st in d["stances"].items():
            stance_counts[st["stance"]] += 1
            if st["stance"] == "skip":
                skip_steps[obj] += 1
    flags = {c: [] for c in objectives}
    for s in steps:
        for coord, flag, _ in s["cities"]:
            if not flags[coord] or flags[coord][-1][1] != flag:
                flags[coord].append((s["cur_step"], flag))
    return {"objectives": {str(c): v for c, v in objectives.items()}, "ownership": {str(c): f for c, f in flags.items()},
            "losses": losses, "waits": waits, "destroyed": destroyed, "stance_counts": dict(stance_counts),
            "skip_steps": {str(k): v for k, v in skip_steps.items()}}


def loss_episode(steps, i, coord, value, decisions, colour) -> Dict[str, Any]:
    zone = _zone(coord)
    t_loss = steps[i]["cur_step"]
    last = steps[i - 1] if i > 0 else steps[i]

    def standing(s):
        return [r for r in s["units"] if r[1] == colour and r[2] in GROUND and not r[9] and r[4] in zone and r[5] == 0]

    def enemies(s, radius=0):
        return [r for r in s["units"] if r[1] != colour and r[2] in GROUND and not r[9]
                and (r[4] in zone if radius == 0 else _distance(r[4], coord) <= radius)]

    index = {s["cur_step"]: j for j, s in enumerate(steps)}
    out = {"objective": coord, "value": value, "step": t_loss, "windows": {}}
    for back in (0, 150, 300):
        j = max(0, i - 1 - back)
        s = steps[j]
        st = stance_near(decisions, s["cur_step"], coord)
        defenders = standing(s)
        out["windows"][str(back)] = {
            "cur_step": s["cur_step"],
            "defenders": [{"unit": r[0], "sub_type": r[3], "blood": r[7], "value": r[8],
                           "plan": plan_near(decisions, s["cur_step"], r[0])} for r in defenders],
            "enemy_in_zone": sorted(r[3] for r in enemies(s)),
            "enemy_within_8": sorted(r[3] for r in enemies(s, 8)),
            "own_ground": sum(1 for r in s["units"] if r[1] == colour and r[2] in GROUND),
            "stance": st,
        }
    fates = []
    for j in range(i - 1, max(-1, i - 1800), -1):
        st = standing(steps[j])
        if not st:
            continue
        nxt = {r[0]: r for r in steps[j + 1]["units"]}
        for r in st:
            if r[0] not in nxt:
                fates.append({"unit": r[0], "sub_type": r[3], "fate": "destroyed", "step": steps[j + 1]["cur_step"]})
            else:
                fates.append({"unit": r[0], "sub_type": r[3], "fate": "left", "step": steps[j]["cur_step"],
                              "plan": plan_near(decisions, steps[j]["cur_step"], r[0])})
        break
    out["last_defenders"] = fates
    return out


def wait_runs(steps, decisions, colour, halted) -> List[Dict[str, Any]]:
    """Runs of consecutive steps in which an own ground unit has a path and zero speed, each step's cause read from
    the seat's own observation (next hex, keep and stop flags) and the all-seeing unit rows (own and enemy ground
    units on the next hex at the decision of that step)."""
    runs: Dict[int, Dict[str, Any]] = {}
    done = []
    by_step = {s["cur_step"]: s for s in steps}
    for s in steps:
        waiting = {r[0]: r for r in s["units"] if r[1] == colour and r[2] in GROUND and not r[9] and r[5] > 0
                   and not r[6]}
        for uid, r in waiting.items():
            if uid not in runs:
                runs[uid] = {"unit": uid, "sub_type": r[3], "start": s["cur_step"], "length": 0,
                             "plan": plan_near(decisions, s["cur_step"], uid, back=1800), "causes": {}}
            runs[uid]["length"] += 1
            seen = halted.get((s["cur_step"] + 1, uid)) or halted.get((s["cur_step"], uid))
            if seen is None:
                cause = "not observed"
            else:
                nxt, keep, stop = seen
                ref = by_step.get(s["cur_step"], s)
                own = sum(1 for o in ref["units"] if o[1] == colour and o[2] in GROUND and not o[9] and o[4] == nxt)
                enemy = sum(1 for o in ref["units"] if o[1] != colour and o[2] in GROUND and not o[9] and o[4] == nxt)
                cause = wait_cause(own, keep, stop, enemy)
            runs[uid]["causes"][cause] = runs[uid]["causes"].get(cause, 0) + 1
        for uid in list(runs):
            if uid not in waiting:
                done.append(runs.pop(uid))
    done.extend(runs.values())
    return sorted(done, key=lambda r: (r["start"], r["unit"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--card", required=True)
    parser.add_argument("--positions", type=int, nargs="+", required=True)
    parser.add_argument("--shadow", nargs="*", default=["S34-MO"])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        relative = args.out.absolute().relative_to(REPO_ROOT.absolute())
    except ValueError:
        relative = None
    if relative is None or relative.parts[0] != "local":
        raise SystemExit("private output must stay under the ignored local/ tree")
    jobs = [(str(args.data), args.card, p, [s for s in args.shadow]) for p in args.positions]
    with mp.Pool(min(args.workers, len(jobs))) as pool:
        results = pool.map(reconstruct, jobs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, sort_keys=True, default=list) + "\n", encoding="utf-8")
    for r in results:
        print(r["position"], r["policy"], r["scenario_id"], r["condition"], "fidelity", r["fidelity"],
              "losses", len(r["losses"]), "waits", sum(w["length"] for w in r["waits"]), "destroyed",
              len(r["destroyed"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
