"""Build or check Sprint 10's versioned frozen-policy T9 diagnostic run cards."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.decision import INERT_ID  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402
from miaosuan_agent.experiments import t9_allocation as t9  # noqa: E402

CARD_ID = "s10-t9-v1-diagnosis"
C2_CARD_ID = "s10-t9-v1-c2-diagnosis"
V2_ID = sx.CANDIDATE_ID
V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
T9_SOURCES = V2_SOURCES + ("experiments/exploratory_addon.py", "experiments/t9_allocation.py")
T9_DIGEST = "0a0b7174f52e6a6a9d30959ef6a1589c185fb82e70290ceb2b80c889109d77fa"
RUNTIME = "baseline-v1-runtime-r2"
GAMES = (
    ("2120531121", "C3", INERT_ID, t9.CANDIDATE_ID),
    ("2120531121", "C3", INERT_ID, V2_ID),
    ("1930331196", "C3", INERT_ID, t9.CANDIDATE_ID),
    ("1930331196", "C3", INERT_ID, V2_ID),
)
C2_GAMES = (
    ("1930331196", "C2", t9.CANDIDATE_ID, INERT_ID),
    ("1930331196", "C2", V2_ID, INERT_ID),
)


def load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def policy_source(sources: Tuple[str, ...]) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(card_id: str = CARD_ID) -> Dict[str, Any]:
    if card_id not in (CARD_ID, C2_CARD_ID):
        raise ValueError(f"unknown Sprint 10 diagnostic card {card_id}")
    shoot = load(REPO_ROOT / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json")
    baseline, candidate = policy_source(V2_SOURCES), policy_source(T9_SOURCES)
    if baseline["sha256"] != V2_DIGEST:
        raise SystemExit(f"baseline-v2 source is {baseline['sha256']}, not the frozen digest")
    if candidate["sha256"] != T9_DIGEST:
        raise SystemExit(f"T9-v1 source is {candidate['sha256']}, not the frozen digest")
    policies = [
        {"id": V2_ID, "label": "baseline-v2 (frozen)", "policy_source": baseline},
        {"id": t9.CANDIDATE_ID, "label": "T9 capacity allocation v1 (frozen)", "policy_source": candidate},
    ]
    schedule = GAMES if card_id == CARD_ID else C2_GAMES
    games = [{"game_id": f"{scenario}.{condition}.{card_id}.g{k:02d}", "scenario_id": scenario,
              "condition": condition, "red": red, "blue": blue}
             for k, (scenario, condition, red, blue) in enumerate(schedule, start=1)]
    common = {
        "status": "EXPLORATORY DIAGNOSIS - NOT ELIGIBLE FOR BASELINE PROMOTION",
        "mechanism": "freeze both policies; capture every step and reconstruct baseline-v2 plus T9-v1 capacity "
                     "decisions from each seat's own observation, including commitments, alternatives and rejections",
        "safety_checks": [
            "persistent engine installation and append-only ledger; no reset, reinstall, restore or authentication change",
            "clean committed tree and byte-identical card before play; frozen policy source digests checked before every game",
            "at most 14 Sprint 10 sessions after closed session 2772; this card contains exactly four sessions",
            "records and captures are never overwritten or retried; stop on integrity, privacy or systemic contract failure",
            "the diagnostic observer is read-only and its seat-local T9 reconstruction must equal the live T9 trace and actions",
        ],
        "intended_observations": [
            "every step's all-seeing state and both seat observations, kept private under local/",
            "unit position, move path and state; objective value, flag and occupants; visibility and legal actions",
            "baseline-v2 pre-add-on actions, submitted pre-execution actions, T9 commitments and all alternative tests",
            "feedback, firing options and orders, targets, judge damage and removals, score and objective transitions",
            "earliest action-level divergence and downstream opportunity timeline, with stochastic counterfactual limits",
        ],
        "next_step_rule": "write a three-configuration diagnosis before any new candidate; implement T9-v2 only if the "
                          "captured mechanism supports one narrow correction that preserves the capacity guard",
    }
    if card_id == CARD_ID:
        texts = {**common,
                 "version": "Sprint 10 frozen T9-v1 full-capture diagnosis, batch 1",
                 "controls": "one fresh baseline-v2 diagnostic trajectory beside one frozen T9-v1 trajectory in each "
                             "adverse C3 configuration; games identify actions and mechanisms, not population causal effects",
                 "configurations": "2120531121 C3 traces the missed 80-point objective; 1930331196 C3 traces reduced "
                                   "damage against the inert control"}
        batch_sessions = 4
    else:
        texts = {**common,
                 "version": "Sprint 10 frozen T9-v1 full-capture diagnosis, conditional C2 batch",
                 "controls": "one fresh frozen T9-v1 trajectory and one fresh baseline-v2 trajectory in the adverse "
                             "1930331196 C2 configuration; games identify actions and mechanisms, not population effects",
                 "configurations": "1930331196 C2 traces the damage reduction unresolved by Sprint 9 aggregate and "
                                   "50-step captures"}
        batch_sessions = 2
    return xp.build(card_id, texts, shoot, mf.digest(shoot), policies, t9.CANDIDATE_ID, games, RUNTIME, 1,
                    {"batch_sessions": batch_sessions, "ledger_base_session": 2772, "sprint_session_cap": 14})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--card", choices=(CARD_ID, C2_CARD_ID), default=CARD_ID)
    args = parser.parse_args()
    out = REPO_ROOT / "evaluation" / args.card / "manifest.json"
    text = json.dumps(build(args.card), indent=1, sort_keys=True) + "\n"
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != text:
            print(f"{out} differs from a fresh build", file=sys.stderr)
            return 1
        print(f"{out} matches a fresh build (canonical SHA-256 {mf.digest(json.loads(text))})")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out} (canonical SHA-256 {mf.digest(json.loads(text))})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
