"""Diagnostic, not part of any registered evaluation: what preceded each engine refusal in one game.

Plays one registered game id with the registered policies, inside the evaluation isolation, as an
engine session with purpose ``diagnostic``, and records for every action the engine refused (an
entry of the all-seeing ``actions`` field carrying an ``error``) what the start of that step looked
like:

* occupation: the objective's flag at the start of the step, and how many occupation actions the
  same seat issued for that hex in that step;
* shot: whether the target and the shooter were on the map at the start of the step, and how many
  shots the same seat aimed at that target in that step.

The output JSON holds counts and per-refusal rows without unit ids or hexes; it is written under
the git-ignored ``local/`` tree. Like ``run_evaluation.py game`` it needs the persistent engine
installation on ``PYTHONPATH`` and refuses to run if the policy source differs from the registered one.

    python scripts/diagnose_engine_refusals.py --game-id ID --engine-install DIR --work DIR --out FILE
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent import engine_install, sdk_data  # noqa: E402
from miaosuan_agent.boundary import Origin, normalize_state  # noqa: E402
from miaosuan_agent.evaluation import effects, randomness  # noqa: E402
from miaosuan_agent.evaluation.identity import policy_source_digest  # noqa: E402

import run_evaluation as rev  # noqa: E402

OCCUPY, SHOOT = 5, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--engine-install", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="a work directory with staged inputs")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=rev.DEFAULT_MANIFEST)
    args = parser.parse_args()

    manifest = rev.load_manifest(args.manifest)
    spec = rev.all_games(manifest).get(args.game_id)
    if spec is None:
        print(f"unknown game id {args.game_id}", file=sys.stderr)
        return 2
    if policy_source_digest()[0] != manifest["policy_source"]["sha256"]:
        print("REFUSED: the policy source differs from the registered one", file=sys.stderr)
        return 2
    rev.verify_inputs(manifest, args.work, spec.scenario_id, spec.map_id)
    inputs = sdk_data.load_inputs(rev.data_root(args.work, spec.scenario_id), spec.scenario_id, spec.map_id)
    randomness.seed_globals(int(manifest["randomness"]["global_seed"]))
    players = manifest["players"]
    install = engine_install.EngineInstall(args.engine_install.resolve())
    rows = []
    with engine_install.session(install, "diagnostic", {"script": "diagnose_engine_refusals",
                                                        "game_id": spec.game_id}) as handle:
        env = rev.engine_factory(install)()
        state = env.setup({"scenario_data": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                           "see_data": inputs.see, "player_info": [dict(p) for p in players]})
        agents = []
        for player in players:
            agent = rev.FACTORIES[spec.red if player["faction"] == 0 else spec.blue]()
            agent.setup({"seat": player["seat"], "faction": player["faction"], "cost_data": inputs.cost})
            agents.append(agent)
        faction_of = {p["seat"]: p["faction"] for p in players}
        view = normalize_state(state, Origin.ENGINE)
        done, steps = False, 0
        while not done and steps < spec.step_cap:
            start = view.global_observation
            hexes = {unit.obj_id: unit.cur_hex for unit in start.operators()}
            flags = {city.coord: city.flag for city in (start.cities() or ())}
            emitted = []
            for player, agent in zip(players, agents):
                emitted.extend(agent.step(view.for_faction(player["faction"]).fields))
            state, done = env.step(emitted)
            steps += 1
            view = normalize_state(state, Origin.ENGINE)
            for entry in view.global_observation.action_feedback() or ():
                code = effects.feedback_error_code(entry)
                if code is None:
                    continue
                action = entry.get("message") or {}
                actor, kind, obj_id = action.get("actor"), action.get("type"), action.get("obj_id")
                row = {"step": steps, "code": code, "action_type": kind, "faction": faction_of.get(actor)}
                if kind == OCCUPY:
                    hex_ = hexes.get(obj_id)
                    row["objective_flag_at_step_start"] = flags.get(hex_)
                    row["occupations_same_hex_same_step"] = sum(
                        1 for a in emitted if a.get("type") == OCCUPY and a.get("actor") == actor
                        and hexes.get(a.get("obj_id")) == hex_)
                elif kind == SHOOT:
                    target = action.get("target_obj_id")
                    row["target_on_map_at_step_start"] = target in hexes
                    row["shooter_on_map_at_step_start"] = obj_id in hexes
                    row["shots_same_target_same_step"] = sum(
                        1 for a in emitted if a.get("type") == SHOOT and a.get("actor") == actor
                        and a.get("target_obj_id") == target)
                rows.append(row)
        handle.outcome = {"status": "COMPLETED" if done else "CAPPED", "steps": steps, "game_id": spec.game_id}
        env.reset()

    summary = {"game_id": spec.game_id, "session": handle.opened["session"], "steps": steps, "done": bool(done),
               "refusals_by_code_and_type": dict(sorted(Counter(f"{r['code']}/{r['action_type']}" for r in rows).items())),
               "rows": rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
