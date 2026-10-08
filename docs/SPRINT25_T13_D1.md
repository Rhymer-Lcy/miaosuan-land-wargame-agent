# Sprint 25: T13-D1 held-objective loss anatomy and garrison shadow

**REGISTERED — OFFLINE — NO ENGINE SESSION — DIAGNOSTIC AND ACTION-LEVEL SHADOW, NOT EVIDENCE THAT A GARRISON WORKS — NOTHING PROMOTED**

Sprint 24 ended `NEXT_INCREMENT_SELECTED` with T13-D1: held objectives are lost repeatedly (40 losses in H0, 26 in HH)
and none was lost while an own unit stood on the objective hex, but the immediate cause of the losses was never
measured. On 2026-10-08 the owner approved this offline experiment. It asks whether objective losses are associated
with observable, preventable departures of the last own ground unit from the objective's denial zone, and whether a
frozen garrison rule would have withheld those departures without unacceptable interference with onward objective
capture. No engine session is authorized and session 2797 is not opened; no executable candidate, run card or
promotion follows from this sprint. Dates are business dates in UTC+8.

Sections 1 to 20, the code they name, the frozen `protocol.json` and `inputs.json`, the tests and the mutation record
are committed and pushed before the target analysis is run. Results follow in a separate section; no registered section
is edited afterwards.

## 1. Starting state and the owner's decisions

| Item | Identity |
|---|---|
| Repository | `main` `a19f5322607cf4cb5acc51fa709ff0f1cb8d3291`, tree `fddd465cefbf619646f43176542a2d7042534bfe`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,796 sessions opened and closed, none unclosed, state chain continuous; ledger file SHA-256 `eaae02bb0b1805a6ee0cf757f96fa39ec8e443f821835b6feb994dee55230bea` at the start of the sprint; session 2797 not authorized |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Privacy baseline | 106 accepted hit lines (below) |

**Privacy owner decision.** The owner provisionally approved extending the accepted privacy baseline from 104 to 106
hit lines, limited to the two documentation-wording lines Sprint 24 introduced. Before the baseline was changed, the
start-of-sprint scan of every reachable blob (1,064 blobs) was reproduced and compared as a multiset with the 104
accepted lines: none removed or changed, exactly two added. Each was pinned to its commit, blob and line: the results
commit `07d27489a277933d51984c3737612c656fa0a21d` (blob `054684fa840fbcf8bca7b144a0e89335dc157065`, line 464 of the
Sprint 24 document) and the first close-out commit `a52974c6f1e073310266ad8c8440eb3bc500e35a` (blob
`4ad923660bd15e11f19c5792c1d67175202d68cc`, line 484). Both are matched by one scanner category only, by a single
word that names that category; neither carries a credential, address, host, path, coordinate, private identifier or
capture, and neither exists at the starting head. The scanner's own patterns were read from its source, and the
verification script's checks were themselves mutation-tested. The two exact lines were registered as accepted
exceptions and the 106-line set written as the new private baseline; the former 104-line baseline and both
adjudication records are kept unchanged, and history is not rewritten. Comparison stays exact: any further added or
removed line is a failure that needs its own review.

The historical dispositions stand unchanged: Sprint 24's selection, ranking and sensitivity analysis; T9 SHELVED;
T2-X1 SHELVED; T2-P1 `T2_P1_MECHANISM_SUPPORTED`; T11-O1 closed; every earlier disposition.

## 2. Scope, the evidence boundary and disclosure

* Offline only: no engine session, no executable candidate, no run card, no change to `baseline-v2`, the stable core,
  the evaluators or any historical output.
* Two populations of different evidence strength, never conflated. **H0** is the 8 replay-corpus games (16
  scenario-sides): the recorded actions are `baseline-v0`'s, and `baseline-v2`'s decisions are reconstructed on those
  states. **HH** is the 4 Sprint 12 head-to-head timelines in 2130511121, analysed on the genuine `baseline-v2` seats
  (two openings, each played twice). Both are read through Sprint 18's census loader, unchanged.
* **HI is not used.** Its Sprint 18 timelines carry the v3 and v6 candidates against the inert control, not a
  `baseline-v2` seat; the inert side never occupies, so no held-objective loss exists there; and the shadow's
  enemy-proximity condition cannot fire without a visible enemy by construction, which the synthetic tests show.
* Never used: BOKE-2026, the stopped 360-game prevalence study, unregistered captures, any new game.
* **Disclosure.** Before writing this registration the author read the documents and public files named in the owner's
  brief and the code of Sprints 18, 19 and 23. Two structure probes were run on the private inputs; they printed no
  loss, departure, trigger or garrison figure: (1) both H0 and HH hold one decision per step for each seat (each HH
  game repeats one step once); an own unit's observed `move_path` is its remaining route (its first hex is a neighbour
  of the current hex in every case); the objective flags take the values -1, 0 and 1; recorded H0 actions carry
  `obj_id`, `type` and `move_path`; (2) of the own ground units that disappear for the rest of a game, 68 of 87 in H0
  and 55 of 61 in HH have a positive damage record placed at the decision of their disappearance, 14 and 4 have none,
  and for 5 and 2 the nearest is at least three decisions earlier; no unit ever leaves the operators into the
  passengers or reappears. Probe (2) shaped the destruction evidence of section 6. A smoke run of the full pipeline
  with a never-firing shadow (section 19) checked the fidelity anchors and printed no T13 figure. The author had also
  read Sprint 24's opportunity figures (40 and 26 losses, none with a unit on the hex, 7 of 16 H0 scenario-sides).

## 3. Scientific question

For each held-objective loss: did the last own ground unit leave the objective's denial zone alive under a MOVE order
(V_ORDER), was it destroyed inside the zone (V_LOSS), or did another or an unsupported mechanism remove the last
defender (V_OTHER)? For each order-vacating loss: was the departure observable to the acting seat, did `baseline-v2`
itself order it, was a visible enemy ground unit near, would the frozen garrison rule have withheld that particular
MOVE, and was the departing unit important to the capture of another objective? This is a mechanism and
opportunity-cost analysis. It does not estimate the score effect of garrisoning, and the shadow cannot show that a
withheld move would have prevented a later loss; it can only show that the historical departure command was an eligible
target of the registered rule.

## 4. Populations and inputs

`evaluation/s25-t13-d1/inputs.json` copies Sprint 18's committed H0 and HH pins and pins Sprint 18's `inputs.json` and
`census.json`; `protocol.json` pins the normalised SHA-256 of every source the study depends on (the garrison shadow,
the analysis, the driver, Sprint 18's census module and loader, the published range and distance code, the objective
labels and the sanitizer). `scripts/s25_t13_d1.py run` refuses unless every pin matches. H0's recorded actions are read
in a separate pass of the same pinned files and aligned with Sprint 18's frames by decision; the pass must reproduce
Sprint 18's 123 decisions where the recorded actions differ from `baseline-v2`'s.

## 5. Ownership loss, geometry and units

* **Loss event**: Sprint 18's N4 event, unchanged (`s18_census.objective_defence`): over a side's play-stage decisions
  in order, an objective whose flag read the side's colour at the previous play decision and does not now; the loss is
  placed at that decision. A flag turning neutral after being held is a loss, as in Sprint 18.
* **Objective hex**: a `cities` entry of the seat's observation. **Denial zone**: the objective hex and its six
  neighbours, every hex within distance 1 by the project's cube-coordinate distance
  (`evaluation/t7_visibility.hex_distance`).
* **Own ground unit**: a unit of the seat's own `operators` of type 1 or 2 with a readable hex; artillery (type 2,
  sub_type 3) is an occupant of the zone but is not an eligible defender; passengers are not operators; type 4 units and
  aircraft are not ground units.
* **Decision and step**: each decision has the recorded `cur_step`; in both populations consecutive play decisions are
  one step apart (section 2). A unit's state at a decision is its state in that decision's own observation, before the
  decision's actions take effect.

## 6. Last-defender reconstruction and the V classes

For each loss at decision `k`, the zone's own ground occupants are read at every play decision from the first to `k`.

1. If the zone holds an own ground unit at `k`, the class is V_OTHER (zone occupied at the loss decision).
2. Otherwise `e` is the first decision of the run of empty decisions that ends at `k` (the zone last became empty at
   `e`). If that run starts at the first play decision, there is no observed last defender: V_OTHER. No defender is
   invented.
3. The **last defenders** are the occupants at `e - 1`. Each one's fate between `e - 1` and `e`: **left alive** (in the
   own operators at `e`, necessarily outside the zone); **destroyed** (absent from the own operators and passengers
   from `e` to the end of the game, with a positive damage record on it placed at `e`); **missing** (absent otherwise:
   another or an unrecorded mechanism); **alive, hex unreadable**.
4. **Departure attribution**: a departure is attributable to a recorded MOVE when the unit's latest recorded MOVE at
   or before `e - 1` exists and the unit's hex at `e` lies on that MOVE's route. A listed but not followed MOVE does not
   count; a unit that left alive without such a MOVE is not V_ORDER.
5. **Class**: V_ORDER when every last defender left alive and each departure is attributable (with several last
   defenders the loss is V_ORDER but flagged and not actionable by T13); V_LOSS when every last defender was destroyed;
   otherwise V_OTHER with its reason (mixed fates in the same step, whose causal order is not observable; a missing
   unit; an unattributable departure; an unreadable hex). Exactly one class per loss.

The recorded action stream is `baseline-v0`'s in H0 and the `baseline-v2` seat's in HH. For an H0 V_ORDER departure the
analysis reports separately whether `baseline-v2`'s reconstructed decision at the order's decision contains the same
MOVE (identical action), a different MOVE for the unit, or none. A `baseline-v0` command is never described as a
`baseline-v2` command.

## 7. Departure facts reported

For a single-defender V_ORDER loss: the order's decision and step; whether the unit was in the zone when ordered and
whether it was then the zone's only own ground unit; whether it already had a remaining route; whether the order came
at the last occupied decision; steps from the zone becoming empty to the loss and from the order to the loss; whether
the zone emptied at the loss decision itself; the unit's class; `baseline-v2`'s agreement (H0); the enemy information
at the order (section 12); the frozen trigger's verdict and reason on that MOVE; whether the stateful shadow withheld
it; and the onward facts of section 15. The departure of an own unit is always in its seat's own observation, and the
order was the seat's own action.

## 8. The frozen T13 garrison rule

`src/miaosuan_agent/experiments/t13_garrison_shadow.py`, identity `t13-d1-garrison-shadow`, status **ANALYSIS SHADOW —
NON-EXECUTABLE** (`EXECUTABLE = False`): no agent class, not in `decision.policy.POLICIES`, in no run card, imported only
by this sprint's analysis, driver and tests. It filters an action list that `baseline-v2` has already produced.

**Trigger**, for a `baseline-v2` MOVE at a play decision, checked in this order (the first failure is reported):

1. the mover is in the seat's own operators, is a ground unit, is not artillery and has a readable hex;
2. it stands in the zone of an objective the side holds;
3. that zone holds exactly one own ground unit, the mover (reading of "exactly one own eligible ground unit": an
   artillery unit in the zone also denies capture, so its presence means the move does not empty the zone);
4. the MOVE's route is readable and has a hex outside the zone;
5. the mover's remaining route from an earlier order, if any, lies inside the zone: withholding a new MOVE cannot stop
   an existing movement, so a mover already leaving is outside this rule's actionable scope (`existing_path_exits`);
6. `baseline-v2` gives the mover no embark or disembark at this decision (an active transport commitment;
   `baseline-v2` issues neither in these populations, so this is a structural guard);
7. a qualifying threat exists (section 9);
8. the objective has no active hold and is not in its cooldown (sections 9 and 10).

**Action change**: that MOVE is withheld (dropped from the list). No replacement action, no route change, no stop
command, no reassignment, no attack change, no change to any other unit; the remaining actions keep their order.

## 9. Threat distance and the hold state machine

**Threat** (Sprint 24's "largest published direct-fire range plus one hex", read exactly): a currently visible enemy
operator of type 1 or 2 with a readable hex is a qualifying threat to an objective and a defender when its published
direct-fire range against the defender's class is known and its distance to the objective hex is at most that range plus
one hex. The range is `evaluation/t7_candidates.weapon_range` over the enemy's `carry_weapon_ids`: the longest
published range of its weapons against personnel (type 1 defender) or against vehicles (type 2 defender), the table
Sprint 5 transcribed and Sprints 18 and 19 used. An enemy whose weapons have no published range against that class is
not a threat to this rule: it fails closed, and no capability is invented. Aircraft are not ground threats.

**Hold episode** (per objective, at most one active, owned by one unit). It starts at the triggering decision with
`hold_start_step = cur_step`. At every later play decision, before any action is examined, an active episode is
released by the first that applies of: (1) the objective is no longer held; (2) the defender is absent from the own
operators (destroyed, missing or no longer controllable); (3) the defender is outside the zone; (4) another own ground
unit is in the zone; (5) no qualifying threat remains, threats measured for the defender's class; (6)
`cur_step - hold_start_step >= 300`. While an episode is active every `baseline-v2` MOVE of its defender whose route
leaves the zone is withheld (a repeat); a MOVE inside the zone, or with an unreadable route, passes; a decision
without a MOVE does not end the episode. A release starts a **cooldown** of the objective: no new episode starts on it
while `cur_step - release_step < 300`, so an expired hold cannot be restarted at once and the 300-step cap bounds every
objective to at most 300 held steps in any 600. Every release is a deterministic function of the decision's own
observation and the episode's start step.

## 10. Overlapping zones

A unit owns at most one episode. A MOVE of a unit that owns an episode is judged by that episode only. Otherwise the
held objectives in whose zone the unit stands are taken in order of distance from the unit, then objective hex; the
first that passes every condition owns the new episode, and every other passing objective is recorded as an overlap
(no second withholding, no second episode). An objective's zone counts its own occupants whatever other zones they are
in. No wider assignment machinery is built.

## 11. Fidelity first

The run reproduces, before any T13 conclusion, Sprint 18's published figures: H0 33,696 decisions and 33,680 play
decisions; 123 decisions where reconstructed `baseline-v2` differs from the recorded `baseline-v0` (also reproduced by
the separate recorded-action pass); HH 11,524 reconstructed `baseline-v2` decisions equal to the recorded seat; 40 H0
and 26 HH held-objective losses, both by this sprint's own enumeration and in the census block; 0 losses with an own
unit on the objective hex at the previous decision in each; 7 of the 16 H0 scenario-sides with a loss; 16 H0 and 4 HH
side-games; Sprint 18's N4 and N6 (first ownership) blocks equal to `census.json`. Each side also passes its integrity
checks: decision positions equal decision indices; one recorded action list per decision; its losses equal Sprint
18's per-side N4 count; no loss with an own unit on the hex; no inconsistent touch category; the candidate equals
`baseline-v2` before the first divergence; only MOVEs are withheld. Any unexplained discrepancy makes the study `T13_D1_INVALID`; no definition is changed to fit.

## 12. Loss-anatomy outputs

Per population (H0, HH), pooled, and per side-game: held-objective losses; V_ORDER, V_LOSS, V_OTHER (with reasons);
losses with an identified last defender; losses whose zone became empty; the number of last defenders; for
single-defender departures, the **enemy information at the order** (ground enemies only, first match): a qualifying
threat visible; a ground enemy visible but none qualifying; a ground enemy seen within the previous 300 steps
(`step - 300 <= seen < step`, Sprint 18's window); seen earlier only; never seen. Also: steps from departure and from the
order to the loss; same-decision versus later loss; the departing unit's class; `baseline-v2` agreement in H0; the
trigger's reason; the nearest visible enemy's distance; the margin of the nearest qualifying threat. Counts are given
as events, games, side-games, scenario-sides, distinct setups (scenario-side and objective) and defender units. No
unit identifier, hex or coordinate is published; objectives are named by Sprint 11's value labels.

## 13. Shadow, action comparison and the divergence boundary

The shadow runs on every recorded decision of each analysed side from an empty memory, on `baseline-v2`'s list. At
every decision the candidate list is compared with `baseline-v2`'s: unchanged; a registered MOVE withheld; or an
unexplained difference. A withheld action counts as registered only if an independent restatement from the frame's raw
fields confirms it is a MOVE of an own non-artillery ground unit standing alone among own ground units in the zone of an
objective the side holds, with a readable route leaving that zone and a visible enemy ground unit within its published
range plus one hex of that objective; any added, reordered or other removed action is unexplained. Zero unexplained
differences are required.

**First valid divergence**: the first decision of a side at which the candidate's list differs from `baseline-v2`'s.
Before it the candidate equals `baseline-v2` (a certificate per side). In HH the recorded prefix is the `baseline-v2`
seat's own trajectory, so the first divergence is a valid action-level fact. In H0 it is valid only if the recorded
`baseline-v0` actions equal `baseline-v2`'s at every decision of that seat before it (Sprint 23's boundary); otherwise it
is descriptive. **Post-divergence opportunity**: a later recorded decision at which the trigger, evaluated statelessly,
would also fire; such states are not on the candidate's trajectory, and repeated replays after the divergence are not
counted as candidate behaviour. Hold episodes after the first divergence are synthetic replays on recorded states.

## 14. Touched losses

A loss is **touched at a valid first divergence** only if: it is V_ORDER with a single last defender; that defender was
ordered from inside the zone; `baseline-v2`'s list at the order's decision contains exactly the departing MOVE (always
in HH; in H0 the identical action); the trigger, evaluated statelessly on that MOVE, passes for the lost objective (as
owner or overlap); that decision is the side's first divergence; the stateful shadow withheld that MOVE there; and, in
H0, the recorded prefix is supported. Every loss gets exactly one category: **touched at a valid first divergence**;
**first divergence without prefix support** (H0, opportunity only); **later historical-state opportunity only** (the
trigger passes after the side's first divergence); **non-actionable** (V_LOSS, several last defenders, ordered before
entering the zone, `baseline-v2` did not emit the MOVE, the trigger fails with its reason, or withheld for another
objective only); **classification ambiguity** (V_OTHER). Before or at the first divergence the stateless trigger and the
stateful shadow must agree; a disagreement is an integrity failure. Categories are never combined to meet a threshold.

## 15. Onward capture and the cost of the hold

For every single-defender V_ORDER departure (registered for the touched ones, descriptive for the rest): the MOVE's
destination (its route's last hex) as an objective the side holds, an objective it does not hold, not an objective,
the lost objective, or unreadable; the historical travel time to the destination; and the **next objective**: the
destination when it is an objective other than the lost one, otherwise the first objective other than the lost one that
the unit stands on after the order (none if it stands on no objective again). **First owner** (the registered risk
flag, Sprint 23's measure): the side's first-ever play-stage ownership of the next objective comes after the order and
the unit stands on that objective's hex at that decision. Also reported: steps from the order to that first ownership;
whether only other own units were the first owners; whether the next objective was already first owned before the
order or never owned; whether the unit was an owner at the next ownership transition (capture or recapture); whether it
was the first owner of any objective after the order; whether it was later lost and when. These labels come from the
historical trajectory, for analysis only; future ownership is never an online trigger, and no delay of an actual first
ownership is claimed.

## 16. Stop conditions and disposition

Denominators and boundaries, fixed now:

* **STOP A, departure not dominant**: for H0, HH and the pooled losses separately, met when
  `2 * V_ORDER < losses` (fewer than half; exactly half passes) or when there is no loss; met overall if met in any of
  the three, so pooling cannot hide one population's failure.
* **STOP B, insufficient actionable coverage**: the touched losses (section 14), de-duplicated across replica games by
  scenario-side, objective, order step, departing unit and route; met when fewer than 4 remain or they cover fewer than
  2 distinct scenario-sides (scenario and colour, so HH's sides and H0's 2130511121 sides coincide).
* **STOP C, onward capture interference**: among the same de-duplicated touched losses, met when the departing unit is
  a first owner of its next objective in strictly more than half (`2 * first owners > touched`), or when there is no
  touched loss. A departure with no next objective counts as not a first owner; it is reported, not dropped.

**Disposition, first match**: `T13_D1_INVALID` (a fidelity anchor or block fails, a side's integrity check fails, or any
unexplained action difference); `T13_D1_NOT_READY` (any stop met); `T13_D1_READY_FOR_SMALL_EXPLORATORY_PROPOSAL`. Every
stop is computed and reported whatever decides the disposition. Ready is research readiness, not evidence of tactical
improvement.

## 17. If ready, and if not

If ready, a DRAFT registration of a two-session head-to-head mechanism probe (2130511121, both seat orders, the T13
add-on on `baseline-v2` against frozen `baseline-v2`) is written for the owner's review, with the candidate identity,
memory semantics, actions, capture, sources, mechanism endpoints and the stops of the brief; it is not executed and
session 2797 is not opened. If not ready, T13 is not patched in this sprint, no wider threat memory, extra defenders,
formation, route, prediction, suppression or fire change is introduced, the T13-D1 increment is closed with its
evidence, and exactly one next research task is recommended from the actual failure.

## 18. Outputs, privacy and checks

* Public, `evaluation/s25-t13-d1/`: `protocol.json` and `inputs.json` (this registration), `mutation.json`, then
  `fidelity.json`, `anatomy.json` (per side-game and pooled tables), `shadow.json` (per side-game shadow summaries and
  first-divergence certificates), `losses-H0.json` and `losses-HH.json` (one sanitised row per loss; a table over 90,000
  bytes is split in order into numbered parts) and `disposition.json` (the three stops and the disposition). Aggregates,
  steps, distances and labels only; every file passes the project sanitizer (forbidden keys anywhere; the private
  hexes and unit identifiers of the inputs as keys or words, numeric leaves masked) or the run writes nothing; `run
  --check` regenerates every file byte for byte.
* Private: `local/diagnostics/s25/study-private.json.gz` on the evaluation server.
* Code: `experiments/t13_garrison_shadow.py`, `evaluation/s25_t13.py`, `scripts/s25_t13_d1.py`,
  `scripts/mutate_s25.py`; tests `tests/test_t13_garrison_shadow.py`, `tests/test_s25_t13.py`,
  `tests/test_s25_driver.py`, `tests/test_s25_results.py` (binds the protocol to the sources and, after the run, the
  results to the rules) and `tests/test_real_s25.py` (server regeneration).
* Close-out: deterministic regeneration; mutation; a private documentation gate with planted errors; the earlier
  current gates; the workstation suite, a clean GitHub clone and the server's private suite; the privacy scan compared
  exactly with the 106 accepted lines; the platform canary rebuilt; a read-only ledger verify (2,796 sessions, none
  unclosed, no session 2797).

## 19. Validation before this registration

* Synthetic tests: the shadow (34 tests: each trigger condition and its boundary, the six neighbours, artillery and
  aircraft, the threat distance at the range plus one and one beyond for vehicles and infantry, no published range, an
  existing route, the exact 300-step boundary, the cooldown edge, every release, release precedence, overlap owner and
  single withholding, action preservation, determinism, identity and the files that may name it); the analysis (50
  tests: loss transitions, every V class and reason, the H0 `baseline-v0`/`baseline-v2` distinction, prefix support,
  every touch category, enemy information at the window edge, onward first ownership, the stop thresholds at one half, four losses, two
  scenario-sides and one half, replica de-duplication, disposition precedence, the action comparison, the sanitizer);
  the driver (8 tests); the protocol pin (`tests/test_s25_results.py`, with six result checks that run after the study).
* Mutation (`scripts/mutate_s25.py`, record `evaluation/s25-t13-d1/mutation.json`): the first run killed 46 of 47
  planted defects; the survivor (a first ownership before the order counted as a risk) was a test gap, closed with a
  test that kills it; the final run on the registered tests and sources killed 47 of 47 after the unmutated tests passed
  in the copy.
* Smoke on the evaluation server with a never-firing shadow: every fidelity anchor and block held, every side passed
  its integrity checks, nothing was withheld and the candidate equalled `baseline-v2` at every decision.

## 20. Not claimed

No tactic is shown to work or fail. A V_ORDER share describes recorded trajectories (H0's are `baseline-v0`'s); a
touched loss is an eligible historical target of the registered rule, not a prevented loss; onward labels are
historical, not counterfactual; nothing here estimates a score effect.

## Amendment A1 (before the rerun)

The registration (`ac9ac6e` to `10fd841ddd37c55d3de2660125cf42dc97662ae4`, tree
`2b10e7986a5346944125f01a41a6027d7a420610`) was pushed at 2026-10-08T19:48:52+08:00; a fresh GitHub clone had the same
commit and tree and byte-identical files, and its suite passed (2,097 tests, 109 skipped). The evaluation server's main
clone was fast-forwarded to it by bundle, `freeze --check` passed there, and `run` was started once. **It refused before
writing any file**: the public sanitizer found, in `anatomy.json`, the first entry of the enemy-information tally of the
H0 table and of the pooled table to be a label with a word made only of digits, equal to a private hex or unit
identifier. That label was the third enemy-information category of section 12, which named the lookback window by its
length.

**What the refusal revealed** (disclosed in full): `fidelity.json`, checked first, carried no private value (whether its
anchors held was not printed); in H0 and in the pooled table the alphabetically first enemy-information category among
the single-defender departures was that third category, so H0 has at least one single-defender departure in it and
neither population has one whose enemy was "never seen" or "seen earlier only"; HH's table did not contain the
category; and the number is among the private hexes or unit identifiers. Nothing else was printed or written.

**Change**: only the public text of that label, now "seen within the lookback window"; the window itself is unchanged
(300 steps, `step - 300 <= seen < step`). No definition, parameter, threshold, stop, disposition rule or input changed.
A test now refuses any registered label or public string with a word made only of digits (it fails on the original
label); the mutation record was regenerated on the amended sources (47 of 47 killed); `protocol.json` was re-frozen and
differs only in that label and the analysis module's digest. The registration did not map a sanitizer refusal to a
disposition (section 18: the run writes nothing), so the run under this amendment is the study's run of record; the
refused attempt produced no result.

## Results (2026-10-08)

Every figure below is read from the committed public files of `evaluation/s25-t13-d1/`, which `scripts/s25_t13_d1.py
run --check` regenerates byte for byte on the evaluation server, unless it is labelled post hoc.

### R1. Order of work

The privacy decision was applied first (section 1). The registration was pushed at 2026-10-08T19:48:52+08:00 after the
workstation suite passed on it (2,100 tests, 101 skipped); a fresh GitHub clone had the same commit and tree, its 13
registered files were byte-identical, and its suite passed (2,097 tests, 109 skipped). The first run refused before
writing anything; Amendment A1 (`f620291` to `b9372d74989803ffea6a7ab8611d0642fda33bb4`, tree
`6cb995b12be142cc38e3a8a682ee3f80ea1e9730`) was pushed at 2026-10-08T20:06:41+08:00 after the workstation suite passed
(2,101 tests, 101 skipped) and the privacy scan matched the 106 accepted lines exactly; the clone again matched. The
server's main clone was fast-forwarded to it, `freeze --check` passed, and `run` wrote the six result files and the
private rows once. No engine was called and no definition, threshold or stop was changed after the run.

### R2. Fidelity

All 12 anchors and the four Sprint 18 blocks (N4 and N6, H0 and HH) are reproduced exactly (`fidelity.json`): H0 33,696
decisions, 33,680 play decisions, 123 recorded/`baseline-v2` differences (also by the separate recorded-action pass);
HH 11,524 of 11,524 reconstructions equal to the recorded seat; 40 and 26 held-objective losses; 0 losses with an own
unit on the hex; 7 H0 scenario-sides with a loss; 16 and 4 side-games. All 20 side-games pass every integrity check, and
there is no unexplained action difference at any decision.

### R3. V classes

| | H0 | HH | Pooled |
|---|---:|---:|---:|
| held-objective losses | 40 | 26 | 66 |
| V_ORDER | 39 | 20 | 59 |
| of which one last defender | 19 | 12 | 31 |
| of which several last defenders, all leaving under recorded MOVEs | 20 | 8 | 28 |
| V_LOSS (destroyed in the zone) | 0 | 4 | 4 |
| V_OTHER | 1 | 2 | 3 |

V_OTHER: one H0 loss whose several last defenders had different fates in the same step, and two HH losses with a last
defender missing without a damage record at its disappearance. A last defender was identified and the zone had become
empty before every one of the 66 losses; no zone was occupied at a loss decision. In other count units the losses cover
7 scenario-sides (HH's two coincide with H0's 2130511121 sides), 27 distinct setups (scenario-side and objective), 8
games, 11 side-games and 59 defender units; V_ORDER alone covers the same 7 scenario-sides, 27 setups and 52 defender
units.

### R4. Loss anatomy by side-game

| Side-game | Losses | V_ORDER | V_LOSS | V_OTHER | Touched | No prefix support | Later opportunity | Non-actionable | Ambiguity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H0 1910631192 red | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| H0 1910631192 blue | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 | 0 |
| H0 1930331196 red | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 10 | 0 |
| H0 1930331196 blue | 12 | 12 | 0 | 0 | 0 | 0 | 3 | 9 | 0 |
| H0 2120531121 red | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| H0 2130511121 red | 7 | 6 | 0 | 1 | 0 | 1 | 1 | 4 | 1 |
| H0 2130511121 blue | 6 | 6 | 0 | 0 | 0 | 1 | 0 | 5 | 0 |
| HH p01 baseline-v2 blue | 5 | 4 | 1 | 0 | 1 | 0 | 0 | 4 | 0 |
| HH p02 baseline-v2 red | 6 | 4 | 1 | 1 | 0 | 0 | 0 | 5 | 1 |
| HH p03 baseline-v2 blue | 4 | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 0 |
| HH p04 baseline-v2 red | 11 | 8 | 2 | 1 | 0 | 0 | 0 | 10 | 1 |

The other nine H0 side-games have no loss.

### R5. The 31 single-defender departures

Every one is a vehicle sent to an objective its side did not hold, by a MOVE that `baseline-v2` itself issues (H0: the
identical action in all 19; HH: the recorded seat). 28 were ordered from inside the lost objective's zone (H0 16, HH 12),
none at the last decision the zone was occupied and none while the unit already had a remaining route: the order came a
median 162 steps before the loss (41 to 715) and the zone was empty a median 121 steps before it (1 to 675; H0 140, HH
81), never at the loss decision itself; 23 of the 31 orders (H0 12, HH 11) came within 300 steps of the loss. At the
order a qualifying threat was visible in 30 (the nearest visible enemy a median 5 hexes from the objective, at most 11;
the nearest threat a median 15.5 hexes inside its range plus one), and in the other one an enemy had been seen within
the lookback window; 24 also had a visible enemy without a published range against the departing class.

**The trigger at the departing MOVE**: `zone_not_single` in 22 (H0 11, HH 11), eligible in 8 (H0 7, HH 1),
`no_qualifying_threat` in 1. The single-occupant condition is what the departures fail: the last unit to leave was
ordered while another own ground unit was still in the zone.

### R6. Touch categories

| Category | H0 | HH | Reasons |
|---|---:|---:|---|
| touched at a valid first divergence | 0 | 1 | withheld at the side's first divergence |
| first divergence without prefix support | 2 | 0 | recorded actions differ from `baseline-v2` earlier |
| later historical-state opportunity only | 4 | 0 | after the side's first divergence |
| non-actionable | 33 | 23 | several last defenders 20 / 8; trigger `zone_not_single` 9 / 11; ordered before entering the zone 3 / 0; trigger `no_qualifying_threat` 1 / 0; destroyed in the zone 0 / 4 |
| classification ambiguity | 1 | 2 | V_OTHER |

### R7. The shadow and the divergence boundary

The shadow examined every `baseline-v2` MOVE (H0 509, HH 416, Sprint 18's published move-order counts): `zone_not_single`
230 and 193, not in a held zone 146 and 102, not a ground unit (aircraft) 118 and 114, no qualifying threat 2 and 2,
eligible 13 and 5. It started 18 synthetic episodes (H0 13 in 4 side-games, HH 5 in 3), with no repeat, overlap or
in-zone pass: on the recorded trajectory the withheld unit always moved on, so the episodes ended by the defender
leaving the zone (H0 9, HH 1), the threat clearing (H0 3), a backup entering (HH 1), the defender's absence (HH 1) or
stayed open at the end (H0 1, HH 2). These hold lengths describe the replay, not holds the candidate would make.

First divergences occur in 7 side-games; in the other 13 the candidate equals `baseline-v2` throughout.

| Side-game | Decision | Step | Prefix supported | Withheld unit | Objective | Qualifying threats | Nearest threat (hexes) | Precedes a loss of it |
|---|---:|---:|---|---|---|---:|---:|---|
| H0 1930331196 red | 2305 | 2304 | no | infantry | 50-point objective A | 1 | 9 | no |
| H0 1930331196 blue | 743 | 742 | no | vehicle | 50-point objective A | 4 | 5 | no |
| H0 2130511121 red | 701 | 700 | no | vehicle | 50-point objective B | 7 | 4 | yes |
| H0 2130511121 blue | 422 | 421 | no | vehicle | 80-point objective A | 11 | 5 | yes |
| HH p01 baseline-v2 blue | 422 | 421 | yes | vehicle | 80-point objective A | 12 | 5 | yes |
| HH p02 baseline-v2 red | 2738 | 2737 | yes | infantry | 50-point objective C | 2 | 3 | no |
| HH p04 baseline-v2 red | 562 | 561 | yes | vehicle | 50-point objective C | 6 | 2 | no |

Eleven later episodes (H0 9, HH 2) are post-divergence replays and are not counted as candidate behaviour. H0's four
first divergences all come after that side's first recorded/`baseline-v2` difference, so none is a valid action-level
fact; H0 2130511121 blue's falls at the same decision and step, on the same objective, as HH p01's (the same
opening).

### R8. The touched loss and the cost of withholding

One loss is touched at a valid first divergence: HH p01, `baseline-v2` blue, the 80-point objective A. The departing
vehicle's MOVE at step 421 was the side's first divergence; the zone was empty 61 steps before the loss at step 562;
12 qualifying threats were visible, the nearest 5 hexes from the objective. Its destination was an objective the side
did not hold; it was not among that objective's first owners, and it was lost later in the game. Over all 31
single-defender departures (descriptive): every destination an objective not held; the departing unit a first owner of
its next objective in 3 (all H0), and of any objective after the order also in 3; the departing unit lost later in 25
(H0 17, HH 8).

### R9. Stop conditions

| Stop | Registered quantity | Result | Met |
|---|---|---|---|
| A, departure not dominant | V_ORDER share, each population and pooled | H0 39/40, HH 20/26, pooled 59/66 | no |
| B, insufficient actionable coverage | distinct touched losses (at least 4) and their scenario-sides (at least 2) | 1 touched (raw 1), 1 scenario-side | **yes** |
| C, onward capture interference | first owners among the distinct touched losses (more than one half) | 0/1 | no |

### R10. Disposition: T13_D1_NOT_READY

Fidelity is intact and no action difference is unexplained, so the study is valid; stop B is met. Held-objective
losses are dominated by departures under `baseline-v2`'s own MOVEs, but the frozen garrison rule reaches one of them at
a valid first divergence, in one scenario-side. No engine probe is drafted, nothing is promoted, and session 2797 is
not opened. The T13-D1 increment is closed with this evidence; T13 is not patched in this sprint.

### R11. Post-hoc facts (read after the disposition; they change nothing)

From `local/diagnostics/s25/posthoc.py` on the evaluation server (aggregates only):

* **The vacating units are stacked groups.** Every one of the 81 last-defender instances of the 28 multi-defender exits
  was stacked (79 vehicles, 2 infantry), and in 27 of those 28 the recorded stream ordered all last defenders at one
  decision.
* **The vacating order often empties the zone at once.** At the decision of the last defender's order, every own ground
  unit then in the zone was ordered out of it in 22 of the 59 V_ORDER losses (H0 16, HH 6); in the others some occupant
  left the zone without an order at that decision, or the departing unit was not yet in the zone (in 8 losses the zone
  was empty at the order, and the unit entered it later). A qualifying threat was visible at that decision in 45 of the
  59; in H0, `baseline-v2` issues the same MOVEs there in all 39.
* **The evidence capacity is small.** Only 23 of the 59 V_ORDER losses had their departure order on a valid prefix: all
  20 in HH (one scenario, two openings) and 3 in H0 (2 in 1910631192 red, whose recorded actions equal `baseline-v2`'s
  throughout, and 1 in 1930331196 red). With one first divergence per side-game, the registered coverage of four
  distinct touched losses on two scenario-sides needs nearly every valid side-game to diverge first on a loss
  departure.

### R12. What Sprint 25 shows

1. **Held objectives are lost to departures, not to destruction**: 59 of 66 losses follow the last defenders' departure
   under recorded MOVEs, in both populations (HH 20 of 26 on genuine `baseline-v2` seats); only 4 follow a destruction
   in the zone. The capture rule's premise holds on these data: the zone was empty before every loss.
2. **The departures are collective.** `baseline-v2` sends stacked groups off held objectives, often in one decision;
   the last unit to leave was alone in the zone when ordered in only 8 of the 59 V_ORDER losses. A single-occupant
   garrison trigger therefore sees few of the departures that matter.
3. **The recorded-state evidence boundary binds.** Valid first divergences come almost only from HH, one scenario, and
   each side-game offers one.
4. **Descriptively, the onward cost looked small**: the departing unit was a first owner elsewhere in 3 of 31
   single-defender departures and was lost later in 25. This is a historical label, not a counterfactual estimate.

### R13. Process notes

* The first registered run was refused by the public sanitizer (Amendment A1): a label named the lookback window by its
  length, a number word equal to a private value. Sprints 20 and 23 met the same class of collision; the registered
  labels are now tested for number words.
* The first mutation run caught 46 of 47 planted defects; the survivor was a test gap (a first ownership before the
  order counted as a risk), closed before registration.
* Two disclosure sentences were corrected before registration: the HH step repetition (one repeated step per game, not
  located) and the reading of the damage-record offsets.

### R14. Recommendation (one)

Run Sprint 24's runner-up experiment, **T6-S, the stacked-column stagger offline shadow** (its entry in
`evaluation/s24-tactical-frontier-reselection/experiments.json`), with no engine session, after its definitions and
stops are registered in the manner of this sprint and the owner approves. Why this one: T13-D1 failed because held
objectives are emptied by stacked groups that `baseline-v2` orders off together, which a single-unit garrison cannot
see; T6-S's trigger acts on stacked groups sent off a shared hex under a visible threat, so its shadow measures the
population this study found, with its own onward first-owner stop; Sprint 24 placed T6-S inside its tie band and named
the offline shadows of T13 and T6 as what would separate them; and it needs no engine session. Not recommended: a
group-level retention variant of T13 (T13-D1 with a modified trigger, and the post-hoc evidence capacity, 23 of 59
order-vacating losses on a valid prefix, would bind it as it bound this study) and any engine probe (stop B is met).
The T13 family stays `IDEA`; any later T13 increment needs a genuinely different mechanism and the owner's decision.

### R15. Close-out

* The results were pushed as `a192fb99cd325ecdf0d7bce123fe20c7edd563a0` (tree
  `c090fee8654c3a3be01372b19d63d0c4ccb45f24`) at 2026-10-08T20:36:56+08:00; a fresh clone from GitHub had the same commit
  and tree and byte-identical files. The evaluation server's run outputs were confirmed byte-identical to the committed
  files before its main clone was fast-forwarded to the commit by bundle; there `freeze --check` and `run --check`
  (public files and private rows) passed. All 21 sprint commits up to the results were audited as a set (author,
  single-line ASCII subjects of at most 72 characters, no body).
* Tests at that commit: the workstation tree ran 2,101 tests (95 skipped) with exit 0; a clean clone from GitHub 2,098
  (103 skipped) with exit 0; the evaluation server's private tree 2,114 (7 skipped; 7,387 s) with exit 0, including
  this sprint's regeneration and mutation-record tests, with the ledger file byte-identical before and after.
* Documentation gates: this sprint's private gate (`local/diagnostics/s25/doc_gate.py`) binds the results to the public
  files and the copied logs and catches all its planted errors; all 27 current gates pass with their plants, and the
  four retired `_v1` copies fail as at Sprint 24's close-out.
* Privacy: the scan of every reachable blob at the results commit (1,091 blobs) gives 106 hit lines, identical to the
  accepted set; no line was added or removed.
* Platform canary: rebuilt on the workstation and the server, SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, no smoke mismatch on either host.
* Engine ledger: read-only verify after the server suite, 2,796 sessions opened and closed, none unclosed, integrity
  ok, state chain continuous, the last event the close of session 2796; ledger file SHA-256 unchanged from the start of
  the sprint; no session 2797. No engine installation, configuration or historical result was touched, and the server's
  development worktree was removed.

