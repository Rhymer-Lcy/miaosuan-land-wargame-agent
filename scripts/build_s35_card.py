"""Build, or check, the Sprint 35 live card (``docs/SPRINT35_COALITION_AGENT.md`` section 11).

    python scripts/build_s35_card.py [--check]

The card is ``evaluation/s35-coalition-live-1/manifest.json`` in the exploratory run-card schema: the 48 scheduled games
(``evaluation.s35_live.schedule``) of the frozen Sprint 35 candidate (``coalition.config.LIVE``) and of the frozen
Sprint 34 control against ``baseline-v2`` and the inert control, the session budget (48 sessions after 2826), the frozen
rules, the normalised SHA-256 of every frozen file of the live infrastructure, the references and the offline
selection. Three policy sources are pinned: ``baseline-v2`` (``7cbaf032...``), the Sprint 34 control (``b107d23e...``,
refused if it differs) and the candidate. A card is never rewritten once it exists with other content; ``--check`` fails
unless the committed card is byte-identical to a fresh build.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from miaosuan_agent.coalition.config import LIVE  # noqa: E402
from miaosuan_agent.coalition.policy import candidate_id  # noqa: E402
from miaosuan_agent.evaluation import exploratory as xp  # noqa: E402
from miaosuan_agent.evaluation import manifest as mf  # noqa: E402
from miaosuan_agent.evaluation import runtime_remediation as rr  # noqa: E402
from miaosuan_agent.evaluation import s35_live as sl  # noqa: E402
from miaosuan_agent.evaluation import shoot_experiment as sx  # noqa: E402
from miaosuan_agent.evaluation.identity import digest_of_files, policy_source_files  # noqa: E402

V2_SOURCES = rr.candidate_sources() + ("experiments/shoot_reservation.py",)
S34_SOURCES = V2_SOURCES + ("integrated",)
CANDIDATE_SOURCES = V2_SOURCES + ("integrated", "coalition")
CANDIDATE_ID = candidate_id(LIVE)
CARD = REPO_ROOT / "evaluation" / sl.CARD_ID / "manifest.json"
RUNTIME = "baseline-v1-runtime-r2"
WORKERS = 1
V2_DIGEST = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
S34_DIGEST = "b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b"
FROZEN_FILES = (
    "src/miaosuan_agent/evaluation/s35_live.py", "src/miaosuan_agent/evaluation/s35_capture.py",
    "src/miaosuan_agent/evaluation/s34_live.py", "src/miaosuan_agent/evaluation/s34_capture.py",
    "scripts/run_s35_game.py", "scripts/run_s35.py", "scripts/s35_analysis.py", "scripts/build_s35_card.py",
    "evaluation/s35-coalition-agent/references.json", "evaluation/s35-coalition-agent/selection.json",
)
TEXTS = {
    "status": "EXPLORATORY TRACK - REGISTERED MULTI-SCENARIO COMPARISON OF AN INTEGRATED AGENT WITH A FRESH CONTROL - "
              "NOT A CONFIRMATION - NOT ELIGIBLE FOR PROMOTION",
    "version": "Sprint 35 coalition-aware integrated agent (docs/SPRINT35_COALITION_AGENT.md)",
    "mechanism": "capability-weighted objective stances (hold, secure, defend with reinforcement deadlines, delay with "
                 "justified withdrawal, coalition capture, skip), last-defender retention and a mobile reserve on top of "
                 "the Sprint 34 integrated decision cycle, independently validated",
    "controls": "a fresh Sprint 34 control in every Stage A configuration (interleaved), and baseline-v2's own games of "
                "the same scenario, condition and seat (references.json); independent stochastic runs, unpaired",
    "safety_checks": "structural stops S1 to S9 per game; severe harm per batch; Stage B only when the A2 gate is open; "
                     "one game per session, serially, exclusive sessions",
    "observations": "scores and margins, objectives first owned, held, lost and recaptured, force losses, traffic "
                    "waits, refusals, fire, module and stance activity, reconstruction and attribution against "
                    "baseline-v2, memory size, latency",
    "next_step_rule": "after every batch the gate of evaluation.s35_live.batch_gate; the disposition of "
                      "evaluation.s35_live.disposition",
}


def frozen_digests(repo: Path = REPO_ROOT) -> Dict[str, str]:
    return {rel: hashlib.sha256((repo / rel).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for rel in FROZEN_FILES}


def policy_source(sources) -> Dict[str, Any]:
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(repo: Path = REPO_ROOT) -> Dict[str, Any]:
    shoot = json.loads((repo / "evaluation" / sx.EXPERIMENT_NAME / "manifest.json").read_text(encoding="utf-8"))
    v2 = policy_source(V2_SOURCES)
    if v2["sha256"] != V2_DIGEST:
        raise ValueError("baseline-v2's policy source is not the frozen one")
    s34 = policy_source(S34_SOURCES)
    if s34["sha256"] != S34_DIGEST:
        raise ValueError("the Sprint 34 control's policy source is not the frozen one")
    policies = [{"id": sl.V2, "label": "baseline-v2 (frozen)", "policy_source": v2},
                {"id": sl.S34_CONTROL, "label": "Sprint 34 integrated agent, variant mission-orchestrator (frozen "
                                                "control)", "policy_source": s34},
                {"id": CANDIDATE_ID, "label": f"Sprint 35 coalition agent, variant {LIVE.name}",
                 "policy_source": policy_source(CANDIDATE_SOURCES)}]
    rows = sl.schedule(CANDIDATE_ID)
    budget = {"batch_sessions": len(rows), "ledger_base_session": sl.LEDGER_BASE_SESSION,
              "sprint_session_cap": sl.SESSION_CAP}
    games = [{"game_id": g["game_id"], "scenario_id": g["scenario_id"], "condition": g["condition"], "red": g["red"],
              "blue": g["blue"]} for g in rows]
    card = xp.build(sl.CARD_ID, TEXTS, shoot, mf.digest(shoot), policies, CANDIDATE_ID, games, RUNTIME, WORKERS, budget)
    for row, game in zip(card["games"], rows):
        row.update(screen_position=game["position"], batch=game["batch"], stage=game["stage"], tag=game["tag"],
                   repetition=game["repetition"], expected_session=game["session"])
    card["screen"] = {"id": sl.STUDY_ID, "rules": sl.RULES_ID, "rules_sha256": sl.rules_digest(),
                      "frozen_files": frozen_digests(repo), "live_config": LIVE.name, "control": sl.S34_CONTROL,
                      "batches": {b: list(r) for b, r in sl.BATCHES.items()},
                      "expected_sessions": [g["session"] for g in rows], "dispositions": list(sl.DISPOSITIONS)}
    return card


def card_problems(card: Mapping[str, Any], repo: Path = REPO_ROOT) -> List[str]:
    problems = []
    screen = card.get("screen") or {}
    if card.get("card_id") != sl.CARD_ID or screen.get("id") != sl.STUDY_ID:
        return ["not the Sprint 35 card"]
    if screen.get("rules") != sl.RULES_ID or screen.get("rules_sha256") != sl.rules_digest():
        problems.append("the card's rules are not the frozen rules")
    current = frozen_digests(repo)
    changed = sorted(rel for rel, d in (screen.get("frozen_files") or {}).items() if current.get(rel) != d)
    if changed or sorted(screen.get("frozen_files") or {}) != sorted(FROZEN_FILES):
        problems.append(f"frozen files differ from the card: {changed}")
    if screen.get("live_config") != LIVE.name or card.get("candidate") != CANDIDATE_ID:
        problems.append("the card's candidate is not the frozen live configuration")
    if screen.get("control") != sl.S34_CONTROL:
        problems.append("the card's control is not the frozen Sprint 34 candidate")
    if [g["game_id"] for g in card.get("games", [])] != [g["game_id"] for g in sl.schedule(CANDIDATE_ID)]:
        problems.append("the card's schedule is not the frozen schedule")
    budget = card.get("budget") or {}
    if (budget.get("ledger_base_session"), budget.get("sprint_session_cap")) != (sl.LEDGER_BASE_SESSION, sl.SESSION_CAP):
        problems.append("the card's session budget is not the proposed one")
    return problems


def dump(data: Any) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    card = build()
    text = dump(card)
    digest = mf.digest(card)
    rel = CARD.relative_to(REPO_ROOT).as_posix()
    if args.check:
        same = CARD.exists() and CARD.read_text(encoding="utf-8") == text
        problems = card_problems(json.loads(CARD.read_text(encoding="utf-8"))) if CARD.exists() else ["no card"]
        print(f"{'OK' if same and not problems else 'MISMATCH'} {rel} sha256(canonical)={digest} {problems or ''}")
        return 0 if same and not problems else 1
    if CARD.exists():
        if CARD.read_text(encoding="utf-8") == text:
            print(f"unchanged {rel} sha256(canonical)={digest}")
            return 0
        print(f"REFUSED: {rel} exists with other content; a card is never rewritten", file=sys.stderr)
        return 1
    CARD.parent.mkdir(parents=True, exist_ok=True)
    CARD.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {rel} sha256(canonical)={digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
