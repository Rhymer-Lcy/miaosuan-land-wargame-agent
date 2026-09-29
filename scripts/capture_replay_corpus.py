"""Record a replay corpus: every start-of-step observation baseline-v0 decided on in one game.

    python scripts/capture_replay_corpus.py --game-id ID --engine-install DIR --out FILE.jsonl.gz

Plays one game id of the registered baseline-v0 plan with its registered policies, inside the
evaluation isolation, as an engine session with purpose ``replay-capture``. It writes a gzipped
JSON-lines file under the git-ignored ``local/`` tree: a header line, then one line per decision
with the seat, the exact observation the seat's agent received (typed JSON, so integer keys
survive), the actions the agent emitted and the digest of its decision trace. The corpus holds
scenario content and is never committed. The game is not part of any registered result.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from miaosuan_agent import engine_install, sdk_data, typed_json  # noqa: E402
from miaosuan_agent.boundary import Origin, normalize_state  # noqa: E402
from miaosuan_agent.decision import digest  # noqa: E402
from miaosuan_agent.evaluation import randomness  # noqa: E402

import run_evaluation as rev  # noqa: E402

SCHEMA = "miaosuan-replay-corpus/1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--engine-install", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=REPO_ROOT / "local" / "evaluation" / "baseline-v0",
                        help="work directory holding the staged baseline-v0 inputs (read only)")
    parser.add_argument("--harness-commit", default="unknown")
    args = parser.parse_args()

    manifest = rev.load_manifest(rev.DEFAULT_MANIFEST)
    spec = rev.all_games(manifest).get(args.game_id)
    if spec is None:
        print(f"unknown game id {args.game_id}", file=sys.stderr)
        return 2
    source = rev.registered_policy_source(manifest)
    if source != manifest["policy_source"]["sha256"]:
        print("REFUSED: the baseline-v0 policy source differs from the registered one", file=sys.stderr)
        return 2
    if args.out.exists():
        print(f"REFUSED: {args.out} exists", file=sys.stderr)
        return 2
    rev.verify_inputs(manifest, args.work, spec.scenario_id, spec.map_id)
    inputs = sdk_data.load_inputs(rev.data_root(args.work, spec.scenario_id), spec.scenario_id, spec.map_id)
    randomness.seed_globals(int(manifest["randomness"]["global_seed"]))
    players = manifest["players"]
    install = engine_install.EngineInstall(args.engine_install.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    decisions = inexact = 0
    harness = {"script": "capture_replay_corpus", "game_id": spec.game_id, "commit": args.harness_commit,
               "policy_source_sha256": source}
    with engine_install.session(install, "replay-capture", harness) as handle, \
            gzip.open(args.out, "wt", encoding="utf-8") as out:
        out.write(json.dumps({"schema": SCHEMA, "game_id": spec.game_id, "scenario_id": spec.scenario_id,
                              "map_id": spec.map_id, "policies": {"red": spec.red, "blue": spec.blue},
                              "players": players, "session": handle.opened["session"], "harness": harness},
                             sort_keys=True) + "\n")
        env = rev.engine_factory(install)()
        state = env.setup({"scenario_data": inputs.scenario, "basic_data": inputs.basic, "cost_data": inputs.cost,
                           "see_data": inputs.see, "player_info": [dict(p) for p in players]})
        agents = []
        for player in players:
            agent = rev.FACTORIES[spec.red if player["faction"] == 0 else spec.blue]()
            agent.setup({"seat": player["seat"], "faction": player["faction"], "cost_data": inputs.cost})
            agents.append(agent)
        view = normalize_state(state, Origin.ENGINE)
        done, steps = False, 0
        while not done and steps < spec.step_cap:
            emitted = []
            for player, agent in zip(players, agents):
                observation = view.for_faction(player["faction"]).fields
                actions = agent.step(observation)
                encoded, lossy = typed_json.encode(dict(observation))
                inexact += len(lossy)
                out.write(json.dumps({"step": steps, "seat": player["seat"], "faction": player["faction"],
                                      "observation": encoded, "actions": actions,
                                      "trace_digest": digest(agent.last_trace)}, sort_keys=True,
                                     separators=(",", ":")) + "\n")
                decisions += 1
                emitted.extend(actions)
            state, done = env.step(emitted)
            steps += 1
            view = normalize_state(state, Origin.ENGINE)
        handle.outcome = {"status": "COMPLETED" if done else "CAPPED", "steps": steps, "game_id": spec.game_id,
                          "decisions": decisions}
        env.reset()
    print(json.dumps({"game_id": spec.game_id, "session": handle.opened["session"], "steps": steps, "done": bool(done),
                      "decisions": decisions, "inexact_values": inexact}))
    return 0 if done and not inexact else 1


if __name__ == "__main__":
    sys.exit(main())
