"""The registered three-game mechanism probe ``t7-mechanism-probe-1`` (``docs/T7_MECHANISM_PROBE.md``).

MECHANISM PROBE: at most three diagnostic games, no tactical A/B, no promotion, nothing uploaded. P-A plays the
candidate ``t7-idle-concealment`` (``experiments/t7_concealment.py``) as blue against the inert control in the
deterministic configuration of Sprint 2 game ``b`` (scenario 1910631192, C3), whose captured record is the reference;
P-B1 and P-B2 play it head to head against ``baseline-v2`` in scenario 2120531121, once in each seat, and only if
P-A passes its registered continuation gate.

This module holds the registration (every rule as data, so the manifest digest covers it), the game specifications
and the probe's read-only capture (:class:`T7Capture`). The analyses are ``scripts/t7_probe_analysis.py``.
"""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..decision import INERT_ID
from . import manifest as mf
from . import residual516 as rd
from .execution import RUNTIMES
from .identity import digest_of_files, policy_source_files

SCHEMA = "miaosuan-t7-mechanism-probe-manifest/1"
PROBE_ID = "t7-mechanism-probe-1"
CAPTURE_SCHEMA = "miaosuan-t7-probe-capture/1"
SCREEN_ID = "tactical-screen-deployment-split-1"
SHOOT_ID = "baseline-v2-candidate-shoot-target-reservation-ab-1"
BASELINE_ID = "baseline-v2-candidate-shoot-target-reservation"  # baseline-v2 (the code keeps the candidate name)
CANDIDATE_ID = "t7-idle-concealment"
CANDIDATE_SOURCES_EXTRA = ("experiments/t7_idle_concealment.py", "experiments/t7_concealment.py")
BASELINE_V2_SOURCE_SHA256 = "7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae"
RUNTIME = "baseline-v1-runtime-r2"
WORKERS = 1
MAX_SESSIONS = 3
SAMPLE_EVERY = 1
PA_GAME = "1910631192.C3.pa"
PB1_GAME = "2120531121.H1.pb1"
PB2_GAME = "2120531121.H2.pb2"
REFERENCE_GAME = "1910631192.C3.b.x01"
REFERENCE_WORK = "local/evaluation/t1r-diagnosis-1"
REFERENCE_SESSION = "2459"

#: The candidate replayed offline over the reference game's blue observations (scripts/t7_probe_analysis.py
#: premise): its first concealment orders at decision index 717 (cur_step 716) to two units, then at 736 (cur_step 735)
#: to two more units of the same hex; the unit identifiers are private (pinned by digest in ``inputs``).
PREDICTED_FIRST_K = 717
PREDICTED_FIRST_CUR_STEP = 716
PREDICTED_FIRST_UNITS = 2
PREDICTED_SECOND_K = 736
PREDICTED_SECOND_UNITS = 2

#: Registered analysis parameters.
COMPLETION_WINDOW = 76     # steps from the decision's cur_step to the completed state (documented 75 s)
TIMER_START = (1, 2)       # the transition timer must be positive at s0 + 1 or s0 + 2
TRANSIENT = 1              # at most this many consecutive snapshots of a listing loss count as transient
EXIT_STEPS = 1             # move_state must have left 4 at the first snapshot after a real move or shot
REPEAT_WINDOW = 75         # the candidate's own repeat window (frozen in the shadow)
CONTROL_AGREEMENT = 0.999  # E4: the documented model must agree with this share of unconcealed control target-steps
MATCHED_AGREEMENT = 0.99   # E4: and with this share of the matched-band control target-steps
MATCHED_MINIMUM = 20       # E4: with at least this many matched-band control target-steps
REFUTE_SHARE = 0.5         # E4a: listed share of discriminating concealed target-steps at or above which E4a is REFUTED

QUESTION = ("Does engine 4.1.0 accept a concealment order (action 6, target_state 4) from an idle, stationary own "
            "ground unit that baseline-v2 leaves without an action, complete the documented 75-second transition, keep "
            "the unit's listed actions and let a later move or shot leave concealment without delay (E1 to E3, E5), "
            "change nothing else in a deterministic game (E6), and halve the distance at which an active opponent "
            "observes the concealed unit (E4), without engine errors or locked units (S1 to S4)?")

GAMES = (
    {"probe": "P-A", "game_id": PA_GAME, "scenario_id": "1910631192", "condition": "C3", "red": INERT_ID,
     "blue": CANDIDATE_ID, "repetition": 1,
     "purpose": "deterministic mechanism and non-interference probe: the configuration of Sprint 2 game b with "
                "baseline-v2 replaced by the candidate"},
    {"probe": "P-B1", "game_id": PB1_GAME, "scenario_id": "2120531121", "condition": "H1", "red": CANDIDATE_ID,
     "blue": BASELINE_ID, "repetition": 1,
     "purpose": "observation probe against an active opponent: the candidate red, baseline-v2 blue"},
    {"probe": "P-B2", "game_id": PB2_GAME, "scenario_id": "2120531121", "condition": "H2", "red": BASELINE_ID,
     "blue": CANDIDATE_ID, "repetition": 1,
     "purpose": "observation probe against an active opponent, seats swapped: baseline-v2 red, the candidate blue"},
)

CANDIDATE = {
    "policy": CANDIDATE_ID,
    "module": "src/miaosuan_agent/experiments/t7_concealment.py",
    "rule_module": "src/miaosuan_agent/experiments/t7_idle_concealment.py (the Sprint 5 shadow, imported unchanged)",
    "rule": ("docs/T7_DESIGN.md section 14: baseline-v2 decides first, unchanged, and its actions are emitted unchanged "
             "and in its order; then each own unit in ascending obj_id that received no baseline-v2 action is ordered "
             "{actor, obj_id, type 6, target_state 4} when it is a ground unit (type 1 or 2) listed in operators, "
             "valid_actions lists action 6 for it with an option whose target_state is 4, move_state is not 4, "
             "change_state_remain_time, move_to_stop_remain_time, weapon_unfold_time, get_on_remain_time and "
             "get_off_remain_time are numbers equal to 0, stop is 1, move_path is an empty list, keep is 0, no "
             "operator of another faction is in the seat view and the candidate has not ordered the unit to change "
             "state in the last 75 steps; the order passes the candidate's own check (option listed, exact key set, "
             "one action per unit). Nothing in deployment; no stop, march, charge, lock, unfold or path change; no "
             "other seat's view, all-seeing state or hidden information; a missing or malformed field fails closed"),
    "trace": ("baseline-v2's trace with the candidate's identity and every emitted action, plus a t7 block: the SHA-256 "
              "of baseline-v2's own trace for the decision, every added order and the skip reasons counted by reason"),
    "fail_closed": ("an exception other than a contract violation after baseline-v2 decided makes the decision "
                    "baseline-v2's alone and is recorded in the trace (t7 error); a contract violation gives no action, "
                    "as for baseline-v2"),
}

CAPTURE = {
    "schema": CAPTURE_SCHEMA,
    "base": ("the read-only step capture of evaluation/residual516.py: per step the complete batch as serialised after "
             "the step, the engine's action feedback, judge_info records new in the step, units gone, appeared, "
             "boarded or landed, watched-field changes, every seat's trace digest"),
    "snapshots": ("a full pre-step snapshot at every decision from index 0: the all-seeing state, and for BOTH seats "
                  "(the inert control included) the seat observation, the memory, the actions and the trace digest; "
                  "plus the final state after the last step (all-seeing state and both seat observations)"),
    "submitted": "per step and seat, a deep copy of every action taken before the engine step (the engine may rewrite "
                 "action objects in place); the serialised batch after the step is kept beside it",
    "candidate_trace": "per step, the candidate seat's t7 trace block (baseline-v2 trace digest, added orders, skip "
                       "reasons by count, error)",
    "storage": "local/evaluation/t7-mechanism-probe-1/capture/<game>.capture.json and <game>.windows.pkl, created "
               "exclusively, git-ignored, never published",
}

DEFINITIONS = {
    "order": ("a concealment order: an action {actor, obj_id, type 6, target_state 4} in the candidate seat's "
              "pre-execution copy of decision k; s0 is the cur_step of the observation it was decided on; the engine "
              "step that executes it leads to the snapshot of decision k + 1 (cur_step s0 + 1)"),
    "fresh_feedback": ("the entries of the engine's action feedback after a step that were not already reported at the "
                       "previous step while the clock stood still; an entry matches an action when its message has the "
                       "same actor, type, obj_id and, for action 6, target_state"),
    "unit_series": ("an affected unit's fields at every snapshot from decision k on (move_state, "
                    "change_state_remain_time and the four other transition timers, stop, keep, move_path, cur_hex, "
                    "flag_force_stop, speed, blood, on_board, listed action types and change-state options), read from "
                    "the all-seeing state and independently from the candidate seat's observation; the analysis refuses "
                    "when the two disagree for an affected unit"),
    "transition": "a unit is in a documented transition at a snapshot when any of the five transition timers is positive",
    "concealed": "move_state 4 with change_state_remain_time 0",
    "completion": ("the first snapshot after decision k whose cur_step s satisfies s - s0 <= 76 and at which the unit is "
                   "concealed; d = s - s0 is the order's duration"),
    "outcomes": {
        "COMPLETED": "the timer was positive at s0 + 1 or s0 + 2 and completion was reached (d <= 76)",
        "COMPLETED_TIMER_ANOMALY": "completion was reached (d <= 76) but the timer was not positive at s0 + 1 or s0 + 2",
        "LATE": "no completion within 76 steps, the unit concealed later, and no documented interrupter before",
        "NOT_COMPLETED": ("the window was fully observed (the game lasted past s0 + 76), no completion within it, no "
                          "documented interrupter, and the unit never concealed later"),
        "INTERRUPTED": ("before completion and within the window, a documented interrupter: the unit suppressed (keep "
                        "above 0), an enemy unit in its hex (same-hex engagement), the unit firing (a judge_info record "
                        "of it), a baseline-v2 action for it that the engine accepted, or the unit gone or boarded"),
        "CENSORED": "the game ended before s0 + 76 without completion or interruption",
    },
}

SAFETY = {
    "S1": "PASS when no fresh feedback entry matching a concealment order carries an error code; FAIL otherwise",
    "S2": (f"over the affected units (units that received at least one order), from their first order to the end: FAIL "
           f"when flag_force_stop is 1 at any snapshot; or when an alive unit on the map has an empty or absent "
           f"valid_actions entry for more than {TRANSIENT} consecutive snapshot(s) outside a documented transition; or "
           f"when a unit that listed action 1 at its order decision does not list it for more than {TRANSIENT} "
           f"consecutive snapshot(s) at which it is alive, on the map, outside a transition, with keep 0 and an empty "
           f"move path. PASS when none occurs and at least one order was issued; NOT TESTED without an order. Every "
           f"transient loss and every listing change is reported"),
    "S3": ("P-A only. S3a premise: at every decision k below the first decision with a concealment order, and at that "
           "decision itself, the all-seeing state digest of the record equals the reference's, the candidate seat's "
           "observation digest equals the reference blue observation's (capture channel), the candidate's baseline-v2 "
           "trace digest equals the reference's blue trace digest, the inert seat's trace digest equals the reference's "
           "red trace digest, and the submitted actions equal the reference's actions (the full dictionaries, in "
           "order; at the first decision the reference's actions followed by the concealment orders); and the first "
           "order is at the predicted decision index with the predicted units. S3b: at every later decision the "
           "candidate seat's submitted actions without its concealment orders equal the reference's blue actions, the "
           "inert seat's equal the reference's red actions, the game has the reference's number of steps and the final "
           "scores equal the reference's. PASS when S3a and S3b hold; FAIL when S3a holds and S3b does not (the first "
           "differing decision, its actions and units characterised); INCONCLUSIVE when S3a does not hold (the reference "
           "was not reproduced before the intervention) or the game did not complete"),
    "S4": ("P-B. PASS when every refusal of the candidate seat (record refusal facts: action type, code, message class) "
           "belongs to a class in baseline-v2's registered records (the shoot-reservation experiment's group C: "
           "1/404 CantMoveKeptPeople, 2/203 CantControlDiedOperator, 2/516 CantShootToDiedBop, 5/203 "
           "CantControlDiedOperator), every candidate decision carries its t7 trace block, no t7 error was recorded, "
           "and the record shows no contract error, no replay mismatch and no observer error; FAIL otherwise. The "
           "opponent seat's refusal classes outside that set are reported, not judged"),
}

MECHANISM = {
    "E1": ("per order, exactly one matching fresh feedback entry: SUPPORTED when at least one order was issued and every "
           "order has one matching entry without an error code; REFUTED when any order's matching entry carries an "
           "error code; INCONCLUSIVE when an order has no matching entry or several (and none carries an error code); "
           "NOT TESTED without an order. An echo without error is not taken as evidence of the transition"),
    "E2": ("per order, the outcome of definitions.outcomes. SUPPORTED when at least one order was issued and every "
           "order is COMPLETED; REFUTED when any order is COMPLETED_TIMER_ANOMALY, LATE or NOT_COMPLETED; "
           "INCONCLUSIVE when none is refuted and some order is INTERRUPTED or CENSORED; NOT TESTED without an order. "
           "Every duration d, the first step move_state read 4, the timer's first positive value and its trajectory are "
           "reported"),
    "E3a": (f"retained listings: for every completed order, the action types the unit listed at its order decision "
            f"except 6 must be listed at every later snapshot while the unit stays concealed, alive, on the map, outside "
            f"a transition and with keep 0; a type absent for more than {TRANSIENT} consecutive snapshot(s) is a loss. "
            f"SUPPORTED with at least one such snapshot and no loss; REFUTED with any loss (the type named); NOT "
            f"TESTED without a completed order. The change-state options listed while concealed are reported"),
    "E3b": (f"exit by a real action: every baseline-v2 action of type 1 (move) or 2 (shoot) submitted for a unit that is "
            f"concealed at the decision. Per event: listed at the decision, submitted, fresh feedback, executed (a move: "
            f"the next snapshot shows the ordered path as the remaining path or the unit entered its first hex; a shot: "
            f"a judge_info record of the unit new in that step), move_state at the next snapshot, and for a move the "
            f"speed at the next snapshot. An event is consistent when it is accepted (no error code), executed, "
            f"move_state is not 4 at the first snapshot after the step (within {EXIT_STEPS}) and a move shows speed "
            f"above 0 or has entered its first hex there; an event whose first hex holds 4 own ground units at the next "
            f"snapshot is excluded (stacking wait). SUPPORTED with at least one consistent event and none inconsistent; "
            f"REFUTED with any inconsistent event; INCONCLUSIVE when every event is excluded; NOT TESTED without an "
            f"event. Moves of unconcealed stationary units of the same game are reported as the matched comparison "
            f"(speed at the next snapshot). Other action types issued to concealed units are reported"),
    "E4": ("P-B only; the documented visibility model (src/miaosuan_agent/evaluation/t7_visibility.py), calibrated on "
           "the replay corpus before registration (calibration.json). Targets: every own ground unit on the map of "
           "either seat at every snapshot, excluding units with a launcher relation (H0: listed whenever their launcher "
           "was, undocumented). A concealed target (move_state 4, timer 0) is classified against every opposing unit "
           "on the map (ground observers: line of sight in see mode 0; aerial observers: mode 2; distances 10 against "
           "infantry and 25 against vehicles, 2 for unmanned aerial vehicles and loitering munitions; band by distance: "
           "within the concealed distance, between it and the normal distance, on the 12.5-hex boundary, beyond, no "
           "line of sight) into exactly one class: terrain (target in a forest or town hex with a relevant observer), "
           "exception (a vehicle lower than a ground observer within its normal distance), ambiguous aerial (a concealed "
           "vehicle with an aerial observer within its normal distance), expected listed (an observer within the "
           "concealed distance), ambiguous boundary, discriminating (an observer between the concealed and the normal "
           "distance and none closer), expected unlisted (none within the normal distance). The outcome is whether "
           "the opposing seat's observation lists the target. Unconcealed targets (move_state 0, every timer 0) are the "
           "control: predicted listed exactly when some opposing unit sees them under the model (terrain halving "
           "applied); the matched band is the control target-steps whose only seeing observers are beyond half their "
           "distance (the steps concealment would change). Control validity: model agreement on at least 0.999 of the "
           "control target-steps and on at least 0.99 of at least 20 matched-band target-steps, per game. E4a: "
           "SUPPORTED when the control is valid, at least one discriminating concealed target-step exists and none is "
           "listed; REFUTED when the control is valid and at least half of the discriminating concealed target-steps "
           "are listed; INCONCLUSIVE when the control is invalid or between none and half are listed (each listed step "
           "characterised); NOT TESTED without a discriminating target-step. E4b (consistency): concealed target-steps "
           "expected listed are listed (SUPPORTED / REFUTED with any unlisted / NOT TESTED). Terrain, exception and "
           "ambiguous classes are reported with both predictions and never enter E4a. Pairs and classes are computed "
           "twice (from the all-seeing state, and from the two seats' own views) and the analysis refuses when they "
           "disagree. Reported: target-steps, distinct targets, distinct (target, observer) pairs and episodes per "
           "class, per game and pooled over P-B1 and P-B2; target-steps are serially dependent and are not "
           "independent trials"),
    "E5": ("events during an unfinished transition (timer positive or before completion within the window): a "
           "baseline-v2 action submitted for the unit, the unit suppressed, an enemy unit in its hex, or the unit firing. "
           "Documented: no other command executes during the transition (an order is refused or not executed until the "
           "transition ends); a tank's shot executes and interrupts it; suppression and same-hex engagement interrupt "
           "it. SUPPORTED with at least one event, all as documented; REFUTED with any event contradicting it; "
           "INCONCLUSIVE when an event cannot be classified; NOT TESTED without an event. No event is manufactured"),
    "E6": ("P-A only: at every snapshot the position (hex, on the map or not) and blood of every unit of both seats, "
           "the objectives' flags and the scores equal the reference's at the same decision index, and the final scores "
           "equal it. SUPPORTED when at least one order completed and all are equal; REFUTED with any difference (the "
           "first characterised); INCONCLUSIVE when S3a does not hold; NOT TESTED without an order"),
}

PRIMARY = ("the share of issued concealment orders that reach the concealed state (move_state 4 with the timer at 0) "
           "within 76 steps of the decision's cur_step, per game and pooled over the games played; every order issued "
           "is in the denominator (censored and interrupted orders included and reported as such); the mechanism "
           "criterion needs 100% with every applicable safety check passed")

INTEGRITY = (
    "I1 the record: COMPLETED, done, the registered policy digests, the registered runtime and capture settings, "
    "harness commit = the registration commit and not dirty, no observer error, no replay mismatch",
    "I2 a snapshot at every decision index from 0 to the last, with both seats' observations and the all-seeing state, "
    "plus the final state; otherwise the analysis refuses",
    "I3 the candidate seat's orders counted three ways agree: its t7 trace blocks, its pre-execution copies (type 6) "
    "and the record's actions_by_type; and every seat's pre-execution copies by type equal the record's counts; "
    "otherwise the analysis refuses (in-place rewrites counted, not refused)",
    "I4 the two channels (all-seeing state and seat observation) agree on every affected unit's series; otherwise the "
    "analysis refuses",
    "I5 offline re-decision: a fresh candidate instance re-decides every captured candidate decision from the seat's "
    "recorded observation and memory and reproduces the submitted actions and the trace digest; the independent pool "
    "predicate (evaluation/t7_candidates.py a2, written separately) finds exactly the captured orders; otherwise the "
    "analysis refuses",
    "I6 transition start and completion are reconstructed twice (a forward scan per order over the all-seeing state, "
    "and one pass over the seat observations for every unit); otherwise the analysis refuses",
)

GATE_PA = ("continue to P-B only when P-A's integrity checks I1 to I6 pass, S1 PASS, S2 PASS, S3 PASS and E2 SUPPORTED, "
           "and after P-A the ledger is continuous with no unclosed session, the persistent installation passes its "
           "integrity check and the frozen identities recompute. Anything else stops the probe: P-B is not run")
STOP_PB = ("after P-B1, P-B2 runs unless P-B1's integrity checks fail, S1, S2 or S4 FAIL, or the ledger, the installation "
           "or a frozen identity fails its check; an E verdict of P-B1 does not stop P-B2")
DISPOSITION = (
    "evaluated in this order on the registered results of every game played (E verdicts pooled over the games in which "
    "they apply):",
    "SHELVE when S1 or S2 FAIL in any game, or E1, E3b or E4a is REFUTED, or E2 is REFUTED with an order NOT_COMPLETED",
    "REVISE when otherwise an integrity check fails or S4 FAIL (a correctable implementation or measurement defect), S3 "
    "FAIL or E6 REFUTED, E3a or E5 REFUTED, or E2 REFUTED by LATE or COMPLETED_TIMER_ANOMALY outcomes only",
    "NEEDS_TARGETED_PROBE when nothing is refuted or failed, E2 is SUPPORTED, and any indispensable endpoint (E1, E3a, "
    "E3b, E4a, E6) is NOT TESTED or INCONCLUSIVE, or a game was not played; the smallest missing verification is named",
    "READY_FOR_TACTICAL_SCREEN when all three games were played, E1, E2, E3a, E3b, E4a and E6 are SUPPORTED and S1 to "
    "S4 PASS wherever they apply; E4b and E5 are reported but do not decide it",
    "otherwise (E2 not SUPPORTED without a refutation, e.g. INCONCLUSIVE or NOT TESTED): NEEDS_TARGETED_PROBE",
)

STOP_RULES = (
    "Before P-A: the registration verified (commit on the public remote; the public issue fetched without "
    "authentication and byte-identical to the canonical body), G0 passed, the server tree at the registration commit.",
    "P-A first and alone, then (only if the continuation gate passes) P-B1, then (unless the P-B stop branch applies) "
    "P-B2; one exclusive session each, serially, through scripts/run_evaluation.sh --plan t7-probe with one game per "
    "invocation; at most 3 sessions.",
    "No repetition, no replacement, no fourth game, no change of scenario, seed, configuration, candidate, trigger or "
    "analysis after any game. A failed or capped game is preserved and reported, never replaced.",
    "An analysis defect found after the first game is fixed only in a separate, labelled post-hoc analysis; the "
    "registered outputs and verdicts stand.",
    "Any integrity failure (ledger, installation, frozen identity, dirty harness, capture, count disagreement) stops the "
    "probe at once.",
)

NOT_CLAIMED = (
    "No tactical efficacy: P-A's opponent is inert, and P-B's two seat-swapped games are a mechanism study, not an A/B; "
    "no score, win or rate difference is estimated.",
    "No engine-wide generality: each verdict holds within the scenarios and unit populations observed.",
    "No promotion and no platform upload of the candidate; baseline-v2 is unchanged.",
)

LIMITATIONS = (
    "The engine's own random source is not controlled by the harness's Python and NumPy seeds; P-A's reference was "
    "deterministic in Sprint 1 and Sprint 2 (no shot), P-B is stochastic.",
    "E3b and E5 need events the registered policies produce on their own; none is forced.",
    "E4 rests on the documented visibility model calibrated on unconcealed units; terrain stacking, aerial observers of "
    "concealed vehicles and the 12.5-hex boundary stay outside its verdict.",
)

REFUSAL_CLASSES = (
    {"action_type": 1, "code": 404, "message_class": "CantMoveKeptPeople"},
    {"action_type": 2, "code": 203, "message_class": "CantControlDiedOperator"},
    {"action_type": 2, "code": 516, "message_class": "CantShootToDiedBop"},
    {"action_type": 5, "code": 203, "message_class": "CantControlDiedOperator"},
)


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def candidate_policy_source(baseline_source: Mapping[str, Any]) -> Dict[str, Any]:
    """The candidate's policy source: baseline-v2's source set plus the shadow rule and its agent module."""
    sources = tuple(baseline_source["sources"]) + CANDIDATE_SOURCES_EXTRA
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(screen: Mapping[str, Any], screen_sha256: str, shoot: Mapping[str, Any], shoot_sha256: str,
          rt_results: Mapping[str, Any], rt_results_sha256: str, files: Mapping[str, str], tests: Mapping[str, str],
          inputs: Mapping[str, str]) -> Dict[str, Any]:
    """The registered manifest from committed inputs: the deployment-split screen manifest (scenarios, players,
    randomness, caps, the reference game's seats), the shoot-reservation manifest (baseline-v2's source set), the
    runtime qualification's results (runtime and scheduler), the normalised SHA-256 of every implementation and test
    file, and the digests of the private and public inputs the analyses read."""
    (scheduler,) = rt_results["production_path"]["scheduler"]
    if rt_results["disposition"]["runtime"] != RUNTIME:
        raise ValueError("the runtime qualification did not promote baseline-v1-runtime-r2")
    baseline = dict(shoot["groups"]["C"]["policy_source"])
    if baseline["sha256"] != BASELINE_V2_SOURCE_SHA256:
        raise ValueError("the shoot-reservation group C source is not baseline-v2's")
    if screen["policies"][BASELINE_ID]["policy_source"]["sha256"] != BASELINE_V2_SOURCE_SHA256:
        raise ValueError("the screen's baseline-v2 source is not baseline-v2's")
    scenarios = {s["scenario_id"]: s for s in screen["scenarios"]}
    reference = next(g for g in screen["games"] if g["game_id"] == REFERENCE_GAME)
    if (reference["condition"], reference["red"], reference["blue"]) != ("C3", INERT_ID, BASELINE_ID):
        raise ValueError("P-A does not preserve the reference game's condition and seats")
    for game, label in ((GAMES[1], "H1"), (GAMES[2], "H2")):
        h2h = next(g for g in screen["games"] if g["scenario_id"] == game["scenario_id"] and g["condition"] == label)
        replaced = {h2h["red"], h2h["blue"]} - {BASELINE_ID}
        if (h2h["red"] == BASELINE_ID) != (game["red"] == BASELINE_ID) or len(replaced) != 1:
            raise ValueError(f"{game['probe']} does not keep the seats of the screen's head-to-head condition {label}")
    return {
        "schema": SCHEMA, "probe_id": PROBE_ID, "evaluation_id": PROBE_ID, "purpose": "diagnostic",
        "status": "MECHANISM PROBE: at most three diagnostic sessions; not a tactical A/B; not eligible for promotion",
        "question": QUESTION, "max_sessions": MAX_SESSIONS,
        "games": [dict(g, map_id=scenarios[g["scenario_id"]]["map_id"]) for g in GAMES],
        "reference": {"game_id": REFERENCE_GAME, "work": REFERENCE_WORK, "session": REFERENCE_SESSION,
                      "policies": {"red": INERT_ID, "blue": BASELINE_ID},
                      "predicted_orders": [{"k": PREDICTED_FIRST_K, "cur_step": PREDICTED_FIRST_CUR_STEP,
                                            "units": PREDICTED_FIRST_UNITS},
                                           {"k": PREDICTED_SECOND_K, "cur_step": PREDICTED_SECOND_K - 1,
                                            "units": PREDICTED_SECOND_UNITS}]},
        "policies": {BASELINE_ID: {"label": "baseline-v2, frozen", "policy_source": baseline},
                     CANDIDATE_ID: {"label": "t7-idle-concealment: baseline-v2 plus the frozen concealment rule",
                                    "policy_source": candidate_policy_source(baseline)}},
        "control_policy": INERT_ID,
        "execution": {"workers": WORKERS, "runtime": RUNTIME, "scheduler": scheduler},
        "runtime_environment": dict(RUNTIMES[RUNTIME]),
        "scenarios": [dict(scenarios[s]) for s in sorted({g["scenario_id"] for g in GAMES})],
        "players": [dict(p) for p in screen["players"]], "randomness": dict(screen["randomness"]),
        "caps": dict(screen["caps"]),
        "capture": dict(CAPTURE, sample_every=SAMPLE_EVERY),
        "candidate": CANDIDATE,
        "parameters": {"completion_window": COMPLETION_WINDOW, "timer_start": list(TIMER_START),
                       "transient": TRANSIENT, "exit_steps": EXIT_STEPS, "repeat_window": REPEAT_WINDOW,
                       "control_agreement": CONTROL_AGREEMENT, "matched_agreement": MATCHED_AGREEMENT,
                       "matched_minimum": MATCHED_MINIMUM, "refute_share": REFUTE_SHARE},
        "definitions": DEFINITIONS, "safety": SAFETY, "mechanism": MECHANISM, "primary": PRIMARY,
        "integrity": list(INTEGRITY), "gate_pa": GATE_PA, "stop_pb": STOP_PB, "disposition": list(DISPOSITION),
        "stop_rules": list(STOP_RULES), "not_claimed": list(NOT_CLAIMED), "limitations": list(LIMITATIONS),
        "refusal_classes": [dict(c) for c in REFUSAL_CLASSES],
        "implementation": {"files": dict(sorted(files.items())), "tests": dict(sorted(tests.items()))},
        "inputs": dict(sorted(dict(inputs, screen_manifest_sha256=screen_sha256, shoot_manifest_sha256=shoot_sha256,
                                   runtime_results_sha256=rt_results_sha256).items())),
    }


def digest(manifest: Mapping[str, Any]) -> str:
    return mf.digest(manifest)


def is_probe(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("schema") == SCHEMA


def scheduled_games(manifest: Mapping[str, Any]) -> List[mf.GameSpec]:
    scenarios = {s["scenario_id"]: s for s in manifest["scenarios"]}
    return [mf.GameSpec(game_id=g["game_id"], scenario_id=g["scenario_id"], map_id=g["map_id"], condition=g["condition"],
                        red=g["red"], blue=g["blue"], repetition=g["repetition"],
                        max_time=int(scenarios[g["scenario_id"]]["max_time"])) for g in manifest["games"]]


def game_policies(spec: mf.GameSpec) -> List[str]:
    """The policies of a game whose sources are pinned (the inert control is not)."""
    return sorted({spec.red, spec.blue} - {INERT_ID})


def captured_policies(spec: mf.GameSpec) -> List[str]:
    """Every policy whose seat the capture snapshots: both seats, the inert control included."""
    return sorted({spec.red, spec.blue})


# ----------------------------------------------------------------------------------------------
# Capture


class T7Capture(rd.Capture):
    """The residual-516 step capture extended for the probe: a snapshot of both seats at every decision from index 0,
    the final state after the last step, the pre-execution copy of every submitted action and the candidate's t7 trace
    block. Read-only: nothing reaches the policies or the engine."""

    def __init__(self, policy_seats: Sequence[str]) -> None:
        super().__init__(policy_seats, sample_every=SAMPLE_EVERY)
        self.final: Optional[Dict[str, Any]] = None
        self._after: Any = None
        self._seats: List[Mapping[str, Any]] = []
        self._last = -1

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        tick = self.clock()
        entry = self.steps[-1]
        submitted, blocks, rewritten = [], {}, 0
        for decision in decisions:
            copies = decision.get("submitted")
            if copies is None:
                raise ValueError("the game loop passed no pre-execution copy of the actions")
            for j, action in enumerate(copies):
                submitted.append({"seat": decision["seat"], "faction": decision["faction"], "j": j,
                                  "action": rd.plain(action)})
                if rd.plain(action) != rd.plain(decision["actions"][j]):
                    rewritten += 1
            trace = decision["trace"]
            if hasattr(trace, "baseline_trace_sha256"):
                blocks[str(decision["seat"])] = {"baseline_trace_sha256": trace.baseline_trace_sha256,
                                                 "added": [list(a) for a in trace.added],
                                                 "skipped": [list(s) for s in trace.skipped],
                                                 "error": trace.t7_error}
        entry["submitted"] = submitted
        entry["rewritten_in_place"] = rewritten
        entry["t7"] = blocks
        if index == 0 or (self.events and self.events[-1]["k"] == index):
            self.samples.append(self.ring[-1])  # index 0 and event steps keep their snapshot among the samples too
        self._after, self._seats, self._last = after, [(d["seat"], d["faction"]) for d in decisions], index
        self.seconds += self.clock() - tick

    def _final(self) -> Optional[Dict[str, Any]]:
        if self._after is None:
            return None
        g = self._after.global_observation
        return {"k": self._last + 1, "cur_step": g.time().cur_step,
                "global": pickle.dumps(dict(g.fields), protocol=4),
                "seats": {seat: {"faction": faction,
                                 "observation": pickle.dumps(dict(self._after.for_faction(faction).fields), protocol=4)}
                          for seat, faction in self._seats}}

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        out["t7_capture_schema"] = CAPTURE_SCHEMA
        return out

    def windows(self) -> Dict[str, Any]:
        out = super().windows()
        out["final"] = self._final()
        return out
