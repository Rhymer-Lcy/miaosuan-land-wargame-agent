"""The registered two-session engine probe ``ps1-engine-probe-1`` (``docs/PS1_ENGINE_PROBE.md``).

ENGINE PROBE: two diagnostic games, no screen, no promotion. P1 issues the frozen PS-1B stop-and-back-off once, through
the diagnostic hook ``ps1-probe-hook-1`` (``experiments/ps1_probe_hook.py``), in the Sprint 2 deadlock configuration
(scenario 1910631192, C3: the inert control red, the hooked split candidate blue), to observe the engine behaviours
E1 to E4. P2 plays one unmodified game of the split candidate against the inert control in a second scenario
(1930331196, C2: the candidate red) and judges the frozen post-hoc movement model M1c (``evaluation/ps1_model.py``
with ``restart_after_wait`` and ``wait_at_entry``) on it prospectively.

This module holds the registration (rules as data, so the manifest digest covers them), the two game
specifications and the probe's read-only capture (:class:`ProbeCapture`): the residual-516 step capture with a full
snapshot at every decision, plus the pre-execution copy of every submitted action and the hook's notes. Analyses are
``scripts/ps1_probe_analysis.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..decision import INERT_ID
from . import manifest as mf
from . import residual516 as rd
from .execution import RUNTIMES
from .identity import digest_of_files, policy_source_files

SCHEMA = "miaosuan-ps1-engine-probe-manifest/1"
PROBE_ID = "ps1-engine-probe-1"
CAPTURE_SCHEMA = "miaosuan-ps1-probe-capture/1"
SCREEN_ID = "tactical-screen-deployment-split-1"
SPLIT_ID = "tactic-deployment-split-1"
HOOK_ID = "ps1-probe-hook-1"
HOOK_SOURCES_EXTRA = ("experiments/ps1_probe_hook.py", "evaluation/ps1_model.py")
RUNTIME = "baseline-v1-runtime-r2"
WORKERS = 1
MAX_SESSIONS = 2
SAMPLE_EVERY = 1
P1_GAME = "1910631192.C3.p1"
P2_GAME = "1930331196.C2.p2"
SPRINT2_SPLIT_GAME = "1910631192.C3.c.x01"
#: The offline replay of the hook over the Sprint 2 split game (scripts/ps1_probe_verify_hook.py) predicts the
#: trigger here and a group of this size; the P1 premise requires the trigger at this decision index.
PREDICTED_TRIGGER_K = 533
PREDICTED_TRIGGER_CUR_STEP = 530
PREDICTED_GROUP_SIZE = 4
#: Registered analysis parameters.
WATCH_STEPS = 300
E3_WINDOW = (74, 77)
E4_MARGIN = 2
F1_TOLERANCE = 1
MIN_EVENTS = 3
TB_MIN_TAU = 4
RUN_TOLERANCE = 1
K = 4
STOP_PENALTY = 75

QUESTION = ("What does engine 4.1.0 do with a stop order issued to own ground units blocked by the stacking limit "
            "(E1 to E4), and does the frozen post-hoc movement model M1c predict an unseen game (E5 and the "
            "fidelity prerequisite of gate G3)?")

GAMES = (
    {"probe": "P1", "game_id": P1_GAME, "scenario_id": "1910631192", "condition": "C3", "red": INERT_ID,
     "blue": HOOK_ID, "repetition": 1,
     "purpose": "stop on a blocked group: the Sprint 2 deadlock configuration with the diagnostic hook"},
    {"probe": "P2", "game_id": P2_GAME, "scenario_id": "1930331196", "condition": "C2", "red": SPLIT_ID,
     "blue": INERT_ID, "repetition": 1,
     "purpose": "prospective M1c validation: an unmodified split-candidate game, the Sprint 1 smoke configuration "
                "whose 200-step snapshots showed a deadlock cycle"},
)

CAPTURE = {
    "schema": CAPTURE_SCHEMA,
    "base": "the read-only step capture of evaluation/residual516.py (compact per-step log: the complete submitted "
            "batch as serialised after the step, the engine's action feedback, judge_info records new in the step, "
            "units gone, appeared, boarded or landed, watched-field changes)",
    "snapshots": "a full pre-step snapshot at every decision from index 1 (sample_every 1): the all-seeing state, and "
                 "for every policy seat its observation, its memory, its actions and its trace digest; a step that "
                 "carries a code-516 refusal keeps its snapshot among the samples as well",
    "submitted": "per step and seat, a deep copy of every action taken before the engine step (the engine may "
                 "rewrite action objects in place); the serialised batch after the step is kept beside it",
    "hook_notes": "per step and seat, the trace diagnostics beginning 'ps1-probe: ' (P1 only), written at decision "
                  "time",
    "storage": "local/evaluation/ps1-engine-probe-1/capture/<game>.capture.json and <game>.windows.pkl, created "
               "exclusively, git-ignored, never published",
}

MODEL = {
    "module": "src/miaosuan_agent/evaluation/ps1_model.py",
    "configuration": {"restart_after_wait": True, "wait_at_entry": True},
    "assumptions": [
        "M1b: a unit whose hex time ends in front of a full hex stops at its hex centre (waiting); in the first step "
        "its next hex has room it starts the traversal again and enters a hex time later, counting that step "
        "(tau - 1 steps after it)",
        "M1c: a unit that enters a hex whose next hex is full at that moment does not start its traversal; it waits "
        "at once",
        "M2: within one step units are processed in ascending unit index and occupancy is updated after each move",
        "M3: a stop on a waiting unit takes effect at once in its hex; a stop on a traversing unit takes effect after "
        "it enters the hex it is moving into; either way the unit can be re-ordered 75 steps later",
        "M4: enemy units do not count toward the own stacking limit; the opponent never moves",
        "M5: an occupation by a unit standing on an unheld objective flips the flag in the next step",
        "M6: hex time tau = (720 / basic_speed) * cost, rounded to the nearest step, on the setup cost graph of the "
        "unit's movement mode; roadblocks from the observation excluded for vehicle modes",
        "M7: the baseline surrogate: a unit without an outstanding order that stands on an unheld objective occupies "
        "it (one occupation per objective per step); otherwise it is ordered along the cheapest path to the cheapest "
        "unheld objective, ties by lower hex; a unit with an outstanding order is never re-ordered",
        "K = 4 own ground units per hex; aircraft and passengers do not count and are not modelled",
    ],
    "status": "post hoc (Sprint 3): derived from the two Sprint 2 games it reproduces; the replay corpus was inspected "
              "while it was developed; P2 is its first prospective test",
}

HOOK = {
    "policy": HOOK_ID,
    "module": "src/miaosuan_agent/experiments/ps1_probe_hook.py",
    "composition": "the frozen tactic-deployment-split-1 decision (reused by import, unchanged), then the hook",
    "trigger": "the frozen PS-1B trigger (docs/PS1_DESIGN.md 11.8): a non-empty deadlocked set, every unit of it "
               "stalled (no hex change or order for more than 2 hex times + 10 steps), from the seat observation and "
               "the hook's own history; time is the observation's cur_step",
    "verification": "at the trigger, from the seat observation and coded apart from the model: every deadlocked unit "
                    "at speed 0, listing action 10, facing a hex with at least 4 own ground units; otherwise the probe "
                    "ends without any action",
    "selection": "ps1_model.ps1b with Recovery(option='back-off') on a model copy of the observed state: the smallest "
                 "deadlocked group on the cycle (ties: not on an objective, lower hex) whose units can all back off to "
                 "hexes with spare capacity that lie on no deadlocked unit's remaining path; nearest hexes by path "
                 "cost, capacity counted as placed, ties by lower hex, units in ascending index",
    "stops": "one {actor, obj_id, type 10} per selected unit at the trigger step, each passing the hook's own check "
             "(this seat, a controllable unit, action 10 listed, a move path to stop, one action per unit); never "
             "repeated",
    "back_off": f"a stopped unit's planned path is emitted at the first step its observation lists action 1 and shows "
                f"no move path, if within {WATCH_STEPS} steps of the stops and s1 to s4 hold (s1 still in its hex of "
                "the trigger; s2 no hex of the path holds 4 own ground units; s3 the destination's own ground units "
                "plus stopped units already sent there and not arrived stay below 4; s4 the project gate accepts the "
                "move); otherwise the unit is released to the candidate. Until then the candidate's actions for it are "
                "dropped and recorded",
    "scope": "one recovery per game: after every stopped unit is resolved the hook never acts again (the 600-step "
             "recovery window of PS-1B is therefore never exercised; the rule itself is unchanged)",
    "trace": "before the trigger the candidate's actions and trace object unchanged; afterwards trace diagnostics "
             "with the prefix 'ps1-probe: ', among them the canonical JSON of every action the hook emits",
}

P1 = {
    "premise": [
        "P1 is evaluable when the hook emits its stops. If it never does (no trigger, failed verification, no escape "
        "plan), every E verdict is INCONCLUSIVE and no further session is used.",
        f"Reproduction: the P1 record's all-seeing state digests and the inert seat's trace digests equal those of "
        f"the Sprint 2 split-game record {SPRINT2_SPLIT_GAME} at every decision index up to the trigger, the hooked "
        f"seat's trace digests equal its digests at every index before the trigger, and the trigger is at decision "
        f"index {PREDICTED_TRIGGER_K} (cur_step {PREDICTED_TRIGGER_CUR_STEP}) with a group of "
        f"{PREDICTED_GROUP_SIZE}. If the reproduction fails, the expected deadlock did not reproduce: every E verdict "
        "is INCONCLUSIVE and the observations are reported descriptively only.",
    ],
    "time": "s0 is the cur_step of the observation on which the stops were decided; 'step s' is the observation with "
            "cur_step s (one engine step is one second of game time, tick 1.0). A unit's remaining path, position and "
            "listed actions at s are read from the seat observation and, independently, from the all-seeing state; "
            "the analysis refuses to run when the two disagree for an involved unit.",
    "events": [
        "listing: action 10 listed for the unit in the observation the stop was decided on",
        "submission: the stop in the pre-execution copy of the seat's actions at s0 and in the hook's notes (both must "
        "agree)",
        "feedback: fresh entries of the engine's action feedback after the step (entries not already present at the "
        "previous step with the same cur_step) that match the stop (type, obj_id): with an error code, without one, "
        "or none",
        "effect: the first step after s0 at which the unit's remaining path is empty",
        "in place: at the effect step the unit stands in its hex at s0 and entered no hex in between",
        "transition: from the effect step until the first step listing action 1 for the unit; per step the listed "
        "action types, stop, move_to_stop_remain_time, speed, move_state and can_to_move (descriptive)",
        "re-listing: the first step after s0 listing action 1 for the unit; L = its cur_step - s0",
        "new move: the hook's back-off for the unit (emitted or not, and why); for an emitted move, fresh feedback and "
        "the echo (the next observation shows the planned path as the remaining path, or the unit already entered its "
        "first hex), then arrival at the destination",
    ],
    "hypotheses": {
        "E1": "SUPPORTED when every stopped unit's stop is followed, within 300 steps, by a change attributable to the "
              "stop (its remaining path empties while it stands outside the final hex of the path it had at s0, or "
              "move_to_stop_remain_time becomes positive) and no fresh feedback entry for the stop carries an error "
              "code. REFUTED when a stop's feedback carries an error code with no attributable change, or a unit shows "
              "no attributable change within 300 steps (accepted-and-deferred and ignored cannot be told apart while "
              "its next hex stays full). INCONCLUSIVE when the evidence is contradictory (an error code and an "
              "attributable change) or no stop was issued. Mixed outcomes across the group are REFUTED, with counts.",
        "E2": "SUPPORTED when at least one unit's stop took effect (an attributable change without an error code), "
              "every such unit stopped in place, and no unit showed no attributable change. REFUTED when any unit "
              "entered its next hex before its path emptied, or showed no attributable change within 300 steps "
              "while its next hex stayed full (it did not stop at its current hex). INCONCLUSIVE when no unit's "
              "stop took effect (every stop refused or contradictory); a refused unit is E1's failure and is left "
              "out of E2.",
        "E3": f"SUPPORTED when every unit that stopped in place has action 1 listed again within 300 steps with "
              f"{E3_WINDOW[0]} <= L <= {E3_WINDOW[1]} (75 s documented; the transition may start in the submission step "
              "or the next, L = 75 or 76; plus one step either side because whether the engine lists actions before or "
              "after updating the timer in a step is unknown), and every back-off move the hook emitted is accepted "
              "(no error code and the echo). REFUTED when L is outside the window, action 1 is not listed again within "
              "300 steps, or an emitted back-off is refused or not echoed. INCONCLUSIVE when no unit stopped in place. "
              "If no back-off could be emitted (a safety check failed), acceptance of a new move is reported as "
              "untested and the verdict rests on the timing and the re-listing.",
        "E4": f"Transitioning units at step s: units whose stop took effect (in place or after an entry) with "
              f"effect step <= s < their re-listing step (or the effect step + 300 without one). Violation: an "
              f"observation in that span showing more than 4 own ground units in a hex that holds a transitioning "
              f"unit. Discriminating unit-step: a non-transitioning own ground unit at speed 0 (keep flag not set) "
              f"whose next hex holds at least one transitioning unit, at least 4 own ground units with them and fewer "
              f"than 4 without them, at a step at least {E4_MARGIN} after the first effect in that hex. Restart: a "
              f"unit seen in such a discriminating unit-step that later, with the same next hex, shows speed above 0 "
              f"while that hex is still full only by counting transitioning units. SUPPORTED when there is no "
              f"violation, at least one discriminating unit-step and no restart. "
              f"REFUTED when there is a violation or a restart. INCONCLUSIVE (untested) when there is no "
              f"discriminating unit-step.",
    },
    "secondary": [
        "whether and when the deadlock cycle of the trigger disappears from the wait-for graph, the deadlocked set "
        "first empties, and a formerly deadlocked unit first enters a hex",
        "deadlock episodes after the stops: count, largest set, cycle or chain, duration, whether they last to the end",
        "for each emitted back-off, the step its unit reaches the destination, if it does",
        "new cycles after the stops that differ from the trigger's",
        "final flags and occupy points (descriptive only; one game shows no tactical efficacy)",
        "the largest own ground occupancy of any hex, engine refusals by code and type, contract errors, gate "
        "rejections, replay mismatches",
        "P1-S: every accepted order of the hooked seat (moves, stops, occupations) replayed through M1c with M3 from "
        "the first play step; entry agreement reported separately before and after the stops (descriptive; before the "
        "stops P1 repeats a game M1c was derived from)",
    ],
    "offline": [
        "every pre-trigger snapshot of P1 re-decided by a fresh tactic-deployment-split-1 instance from the captured "
        "observation and memory: actions and trace digest equal to the hooked seat's",
        "the trigger recomputed from the seat observation and from the all-seeing state with the Sprint 3 functions "
        "(scripts/ps1_study.py): the same step and the same deadlocked units",
    ],
}

TARGETED = {
    "T-a": ("wait at entry (M1c): an entry of an eligible unit with a remaining path whose next hex holds at least 4 "
            "own ground units both before and after the step, with no own unit leaving that hex in the step and the "
            "keep flag not set, is a discriminating event; M1c predicts speed 0 at the entry observation (M1b: above "
            "0)"),
    "T-b": (f"restart after a blocked wait (M1b): an episode is a unit with a path waiting at speed 0 in front of a "
            f"hex with at least 4 own ground units, keeping its path, until it enters that hex; its steps after the "
            f"start split into maximal runs at speed above 0 (traversals) and at speed 0 (waits). The final run before "
            f"the entry of every entered episode with tau >= {TB_MIN_TAU} and no keep flag, move_state or basic_speed "
            f"change in that run is a discriminating event; M1c predicts a traversal of tau - 1 steps (tolerance "
            f"{RUN_TOLERANCE}); an entry straight from waiting (M1) or a traversal of another length contradicts it"),
    "T-c": (f"interruption and re-wait: in the same episodes, a run at speed above 0 that ends with speed 0 and the "
            f"path kept (a re-wait) is a discriminating event; M1c predicts that the run lasted tau - 1 steps "
            f"(tolerance {RUN_TOLERANCE}) and that the hex held at least 4 own ground units at the first step of the "
            f"re-wait; each run of one episode is a separate event (several traversals per episode are measured per "
            f"segment, never from the first step with room)"),
    "T-d": ("simultaneous-entry arbitration: a step in which, for one hex, at least one eligible unit enters it and at "
            "least one other eligible unit that was traversing towards it (speed above 0 before the step) re-waits "
            "instead (speed 0 after the step, path kept); M1c predicts that the entrants are the lowest-index units "
            "among the two sets; a first-come order (earliest start of the unit's current waiting episode, then lower "
            "index) and the descending index order are evaluated beside it; an event in which the first-come order "
            "predicts the same entrants as ascending index is reported as not discriminating between the two"),
    "T-e": ("processing order: (1) entries of T-a's population in which the three occupancy readings (ascending index, "
            "descending index, end of step) disagree about whether the next hex is full when the unit is processed; "
            "M1c (ascending) predicts speed 0 exactly when it is full in the ascending reading; (2) T-d events; (3) a "
            "waiting unit whose next hex gets room in a step through units leaving it: M1c predicts a restart (speed "
            "above 0) in that step when a leaving unit has a lower index than the waiting unit, and one step later "
            "otherwise"),
}

VERDICT_RULE = (f"A targeted claim is SUPPORTED with at least {MIN_EVENTS} discriminating events, all as predicted "
                f"(T-d also needs at least one event that discriminates ascending index from the first-come order); "
                f"REFUTED when any discriminating event contradicts the prediction; INSUFFICIENT with 1 or 2 "
                f"discriminating events, all as predicted; NOT TESTED with none. Events excluded from a discriminating "
                f"set are counted with their reason.")

P2 = {
    "population": "eligible units: the candidate seat's own ground units (type 1 or 2, listed for the seat, not on "
                  "board) in the observation of the first play decision, plus any that appear later; aircraft, "
                  "passengers and the opponent's units are outside the model's scope and are counted, not compared; "
                  "a unit that leaves the observation or boards is compared up to that step and its removal is applied "
                  "to the model as an observed input; a unit that appears is added to the model at its first "
                  "observation, as an observed input (one already traversing then cannot be timed, and its appearance "
                  "makes the accounting incomplete)",
    "integrity": [
        "I1 the record: COMPLETED, done, the registered policy digests, runtime and capture settings, no observer "
        "error, no replay mismatch",
        "I2 a snapshot at every decision from index 1 to the last; otherwise the analysis refuses",
        "I3 the pre-execution submitted actions by type equal the record's actions_by_type for the candidate seat; "
        "otherwise the analysis refuses; differences between submitted and serialised actions are counted (in-place "
        "rewrites)",
        "I4 the seat observation and the all-seeing state agree on every eligible unit's hex and remaining path at "
        "every snapshot; any disagreement makes F1, F2 and every targeted claim INCONCLUSIVE",
        "I5 every applied move order reappears as the unit's remaining path in the next snapshot (or the unit already "
        "entered its first hex); any failure makes F1 INCONCLUSIVE",
    ],
    "F1": (f"Primary. Replay from the first play decision: the model starts from the observed state and receives every "
           f"pre-execution move and occupation order of an eligible unit whose fresh feedback carries no error code, "
           f"at its decision index, plus the observed removals; it predicts every entry. PASS when every eligible unit's "
           f"predicted hex sequence equals the observed one (0 mismatches), every matched entry is within "
           f"{F1_TOLERANCE} step, the predicted trajectory has no capacity or adjacency violation (independent "
           f"validator, with the observed removals and appearances as inputs, which are never violations themselves), "
           f"no observation shows more than 4 own ground units in a hex, and the accounting is complete "
           f"(every eligible unit and every step compared, no model error). FAIL otherwise. Reported in full: the "
           f"offset distribution, the worst offset, each mismatched unit's first differing entry with its conditions "
           f"(occupancy and contenders at the contested hex, keep flag, move_state and speed changes, feedback), and "
           f"the counts of orders applied, refused and outside the population."),
    "F2": ("Secondary. The same start with the frozen surrogate (M7) issuing every order. PASS when every eligible "
           "unit's predicted hex sequence equals the observed one with every matched entry within 1 step, every "
           "recorded accepted move order of an eligible unit is matched by a predicted order of the same unit to the "
           "same final hex within 1 step, there is no unmatched predicted order, and every recorded accepted "
           "occupation is matched by a predicted occupation of the same objective within 1 step with none extra. "
           "FAIL otherwise. Reported: command equivalence, occupation timing, sequences, and behaviour outside the "
           "surrogate's documented scope (shots, refused orders, occupations not listed, aircraft orders). A passing "
           "F1 does not establish F2."),
    "targeted": TARGETED,
    "verdict_rule": VERDICT_RULE,
    "keep": "every eligible unit-step with the keep flag set and a remaining path, and every entry-rule disagreement "
            "with it set, reported separately; never discarded from F1, never counted as a discriminating event",
    "coverage": "the analysis lists the total observations of each kind, the eligible subset of each test, the "
                "excluded observations with reasons, and exact event counts; a perfect F1 on a game without "
                "discriminating events does not support E5",
    "two_methods": "every central count is extracted twice, from the seat observation and from the all-seeing state, "
                   "by separately written code; any disagreement refuses the claim",
}

GATES = {
    "G1": "Sprint 3's PASS stands as the historical record; audited for contradiction (the P1 reproduction of the "
          "Sprint 2 states; agreement of the two channels and no hex above 4 own ground units in both captures)",
    "G2": "PASS when E1, E2, E3 and E4 are all SUPPORTED and the P1 sequence used only the seat observation and listed "
          "actions (every hook action passed its check, 0 replay mismatches, the offline re-decisions agree). FAIL "
          "when any of E1 to E4 is REFUTED, naming the part of PS-1B it invalidates. UNRESOLVED otherwise.",
    "G3": "PASS when F1 and F2 PASS, T-a, T-b, T-d and T-e are SUPPORTED, T-c is SUPPORTED, INSUFFICIENT or NOT TESTED, "
          "G2 PASSES and the A2 certificate recomputed under M1c is feasible. FAIL when F1 or F2 FAILS or a targeted "
          "claim is REFUTED. UNRESOLVED otherwise. The certificates are recomputed only when everything but the "
          "certificate passes; M1 and M1b keep their failed registered results.",
    "G4": "Sprint 3's PASS for PS-1B stands as the historical record; audited for contradiction (the PS-1B trigger "
          "census of P2 and the pre-trigger part of P1: a firing without a deadlock in the observed state would "
          "contradict it)",
    "G5": "exactly one of: SHELVE when E1 is REFUTED with no stop accepted from any blocked unit (PS-1B's only "
          "intervention is unavailable; no other approved alternative exists); REVISE when otherwise any of E2 to E4 "
          "is REFUTED, F1 or F2 FAILS, or a targeted claim is REFUTED (a correctable requirement fails); "
          "NEEDS_ENGINE_PROBE when nothing is refuted or failed but G2 or G3 is UNRESOLVED (the smallest next probe "
          "is named); READY_FOR_PROSPECTIVE_VALIDATION when G2 and G3 PASS and G1 and G4 are not contradicted",
}

STOP_RULES = (
    "Before P1: R0 verified (registration commit on the public remote, the public issue fetched without "
    "authentication and byte-identical to the canonical body), G0 passed, the server tree at the registration commit.",
    "P1 first, then P2, serially, one session each, through scripts/run_evaluation.sh --plan probe; no repetition, no "
    "replacement, no change of scenario, seed, configuration or code after either game.",
    "After P1: ledger continuity, capture integrity and the frozen identities are verified before P2. A "
    "persistent-installation integrity failure, an unauthorised installation change or a serious safety violation "
    "stops the probe before P2. A P1 that is INCONCLUSIVE or refutes E1 to E4 does not stop P2.",
    "A failed or capped game is preserved and reported, never replaced; an inconclusive probe never authorises a "
    "third session.",
    "An analysis defect found after registration is fixed in a separate, labelled post-hoc analysis; the registered "
    "output is kept and its verdicts stand.",
)

BRANCHES = (
    "P1 INCONCLUSIVE (no trigger, failed verification, no escape plan, or no reproduction): G2 stays UNRESOLVED; the "
    "smallest next probe is named in the report and not run.",
    "P1 refutes an E hypothesis: G2 FAILS; the report states which part of PS-1B the refutation invalidates and "
    "whether a different design would be needed.",
    "P2 F1 FAILS: M1c is not supported prospectively; any corrected model is a new post-hoc candidate needing its own "
    "prospective validation in a later sprint.",
    "P2 without discriminating events: the claims are NOT TESTED or INSUFFICIENT and G3 stays UNRESOLVED.",
)

HARNESS = ("The shared game loop, runner and step capture are those of the registration commit: every probe game "
           "record must carry that commit in its harness block with dirty false, or the game is reported as a "
           "deviation. The probe's own files are frozen by their digests in implementation.files and "
           "implementation.tests.")

NOT_CLAIMED = (
    "No tactical efficacy: P1's score is one game with one intervention.",
    "No general engine-wide correctness: one prospective game supports a mechanism within its observed conditions only.",
    "No promotion of either candidate; T1 stays shelved.",
)


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def hook_policy_source(split_source: Mapping[str, Any]) -> Dict[str, Any]:
    """The hook's policy source: the split candidate's source set plus the hook and the model module it executes."""
    sources = tuple(split_source["sources"]) + HOOK_SOURCES_EXTRA
    files = policy_source_files(sources=sources)
    return {"sha256": digest_of_files(files), "files": files, "sources": list(sources)}


def build(screen: Mapping[str, Any], screen_sha256: str, rt_results: Mapping[str, Any], rt_results_sha256: str,
          files: Mapping[str, str], tests: Mapping[str, str], inputs: Mapping[str, str]) -> Dict[str, Any]:
    """The registered manifest, from the committed screen manifest and runtime results; ``files`` and ``tests`` map
    repository paths of the model, the hook, the capture and the analyses (and their tests) to normalised SHA-256s;
    ``inputs`` holds the digests of the private and public inputs the analyses read."""
    (scheduler,) = rt_results["production_path"]["scheduler"]
    if rt_results["disposition"]["runtime"] != RUNTIME:
        raise ValueError("the runtime qualification did not promote baseline-v1-runtime-r2")
    split = screen["policies"][SPLIT_ID]["policy_source"]
    scenarios = {s["scenario_id"]: s for s in screen["scenarios"]}
    smoke = next(g for g in screen["smoke_games"] if g["scenario_id"] == GAMES[1]["scenario_id"])
    if (smoke["condition"], smoke["red"], smoke["blue"]) != (GAMES[1]["condition"], GAMES[1]["red"], GAMES[1]["blue"]):
        raise ValueError("P2 does not preserve the smoke game's condition and seats")
    original = next(g for g in screen["games"] if g["game_id"] == SPRINT2_SPLIT_GAME)
    if (original["condition"], original["red"], original["blue"]) != (GAMES[0]["condition"], GAMES[0]["red"], SPLIT_ID):
        raise ValueError("P1 does not preserve the Sprint 2 game's condition and seats")
    return {
        "schema": SCHEMA, "probe_id": PROBE_ID, "evaluation_id": PROBE_ID, "purpose": "diagnostic",
        "status": "ENGINE PROBE: two diagnostic sessions; not a screen; not eligible for promotion",
        "question": QUESTION, "max_sessions": MAX_SESSIONS,
        "games": [dict(g, map_id=scenarios[g["scenario_id"]]["map_id"]) for g in GAMES],
        "policies": {SPLIT_ID: {"label": "frozen deployment-split candidate (Sprint 1), unchanged",
                                "policy_source": dict(split)},
                     HOOK_ID: {"label": "diagnostic hook: the split candidate plus one PS-1B stop-and-back-off",
                               "policy_source": hook_policy_source(split)}},
        "control_policy": INERT_ID,
        "execution": {"workers": WORKERS, "runtime": RUNTIME, "scheduler": scheduler},
        "runtime_environment": dict(RUNTIMES[RUNTIME]),
        "scenarios": [dict(scenarios[g["scenario_id"]]) for g in GAMES],
        "players": [dict(p) for p in screen["players"]], "randomness": dict(screen["randomness"]),
        "caps": dict(screen["caps"]),
        "capture": dict(CAPTURE, sample_every=SAMPLE_EVERY),
        "model": dict(MODEL, sha256=files[MODEL["module"]]),
        "hook": dict(HOOK, watch_steps=WATCH_STEPS),
        "parameters": {"K": K, "stop_penalty": STOP_PENALTY, "watch_steps": WATCH_STEPS, "e3_window": list(E3_WINDOW),
                       "e4_margin": E4_MARGIN, "f1_tolerance": F1_TOLERANCE, "min_events": MIN_EVENTS,
                       "tb_min_tau": TB_MIN_TAU, "run_tolerance": RUN_TOLERANCE,
                       "predicted_trigger_k": PREDICTED_TRIGGER_K,
                       "predicted_trigger_cur_step": PREDICTED_TRIGGER_CUR_STEP,
                       "predicted_group_size": PREDICTED_GROUP_SIZE},
        "p1": P1, "p2": P2, "gates": GATES, "stop_rules": list(STOP_RULES), "branches": list(BRANCHES),
        "harness": HARNESS,
        "not_claimed": list(NOT_CLAIMED),
        "implementation": {"files": dict(sorted(files.items())), "tests": dict(sorted(tests.items()))},
        "inputs": dict(sorted(dict(inputs, screen_manifest_sha256=screen_sha256,
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
    return sorted({spec.red, spec.blue} - {INERT_ID})


# ----------------------------------------------------------------------------------------------
# Capture


HOOK_NOTE = "ps1-probe: "


class ProbeCapture(rd.Capture):
    """The residual-516 step capture with a snapshot at every decision, the pre-execution copy of every submitted
    action and the hook's notes. Read-only: nothing reaches the policies or the engine."""

    def __init__(self, policy_seats: Sequence[str]) -> None:
        super().__init__(policy_seats, sample_every=SAMPLE_EVERY)

    def step(self, index: int, before: Any, after: Any, decisions: Sequence[Mapping[str, Any]]) -> None:
        super().step(index, before, after, decisions)
        tick = self.clock()
        entry = self.steps[-1]
        submitted, notes, rewritten = [], {}, 0
        for decision in decisions:
            copies = decision.get("submitted")
            if copies is None:
                raise ValueError("the game loop passed no pre-execution copy of the actions")
            for j, action in enumerate(copies):
                submitted.append({"seat": decision["seat"], "faction": decision["faction"], "j": j,
                                  "action": rd.plain(action)})
                if rd.plain(action) != rd.plain(decision["actions"][j]):
                    rewritten += 1
            hooked = [d for d in decision["trace"].diagnostics if d.startswith(HOOK_NOTE)]
            if hooked:
                notes[str(decision["seat"])] = hooked
        entry["submitted"] = submitted
        entry["rewritten_in_place"] = rewritten
        if notes:
            entry["hook_notes"] = notes
        if self.events and self.events[-1]["k"] == index:  # keep every decision's snapshot among the samples
            self.samples.append(self.ring[-1])
        self.seconds += self.clock() - tick

    def compact(self) -> Dict[str, Any]:
        out = super().compact()
        out["probe_capture_schema"] = CAPTURE_SCHEMA
        return out
