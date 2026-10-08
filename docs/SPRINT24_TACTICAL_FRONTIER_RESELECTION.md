# Sprint 24: evidence-updated tactical frontier re-selection

**REGISTERED — OFFLINE — NO ENGINE SESSION — RESEARCH SELECTION, NOT EVIDENCE THAT ANY TACTIC WORKS — NOTHING PROMOTED**

On 2026-10-08 the owner accepted Sprint 23's substantive finding and opened Sprint 24: an offline re-selection of the
next tactical research experiment from all evidence through Sprint 23. No engine session is authorized; session 2797
is not opened. No candidate policy is built, no run card is created and nothing can be promoted by this sprint. Dates
are business dates in UTC+8.

Sections 1 to 13 are the registration. They are committed and pushed, with the frozen rubric
(`evaluation/s24-tactical-frontier-reselection/rubric.json`), the selection rule and its tests, the mutation record and
the input pins (`inputs.json`), before any candidate experiment is written down and before any score is assigned, and
are not edited afterwards. Results follow in a separate section.

## 1. Starting state and the owner's decisions

| Item | Identity |
|---|---|
| Repository | `main` `d5d12c0b8b45ba3001a46f6a44e11734a1cd0d5f`, tree `e48141650b0c3e0e94990387278355f451769050`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,796 sessions opened and closed, none unclosed, integrity ok, state chain continuous, last event the close of session 2796 (read-only verify at the start of the sprint); ledger file SHA-256 `eaae02bb0b1805a6ee0cf757f96fa39ec8e443f821835b6feb994dee55230bea`; session 2797 not authorized |
| Privacy baseline | the 104 accepted hit lines, reproduced as the same set at the start of the sprint (1,045 reachable blobs) |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |

The owner's decisions, recorded in the frontier's hypothesis register (T2 row) by the first commit of this sprint
(`63a123e`): (1) Sprint 22's `T2_P1_MECHANISM_SUPPORTED` is preserved; (2) the T2-X1 multi-pair transport increment is
SHELVED; (3) the T2 family is not closed; (4) Sprint 23's Amendment A1 qualification is recorded explicitly (section
2); (5) the next tactical research increment is selected from all evidence through Sprint 23; (6) engine session 2797
is not opened.

## 2. The Sprint 23 Amendment A1 qualification

Sprint 23's first frozen run refused to write anything because its public sanitizer failed on the representation of a
share (a reduced fraction whose text equalled a small private unit id). Its protocol (section 14) maps a public
sanitizer failure to `T2_DESIGN_INVALID`. Amendment A1 changed only the public representation of the two shares
(unreduced `part/whole`), was committed and pushed before the successful rerun, and disclosed what the refusal had
revealed: that the opportunity minimums had passed and that one reduced share was a small integer. Both readings are
recorded here and in the frontier:

| Reading | Outcome |
|---|---|
| ORIGINAL-PROTOCOL, the section 14 clause applied literally to the refused first run | `T2_DESIGN_INVALID` |
| AMENDED-PROTOCOL, the rerun under Amendment A1 | `T2_UNRESOLVED_INTERACTION_RISK` |

Sprint 23's document and its historical disposition file are not changed. Its amended result was not obtained under an
entirely unchanged original protocol. Both readings prohibit an engine screen of T2-X1. Sprint 23 is not reopened or
rerun.

## 3. T2: preserved, shelved, open

* **Preserved (OBSERVED ENGINE MECHANISM, one deterministic game):** an infantry unit was carried to an objective it could
  not reach on foot within the game, through an engine transport chain completed as registered (Sprint 22, session
  2796).
* **Shelved:** T2-X1, the multi-pair same-objective transport increment. No T2-X2 repair is authorized.
* **Retained as descriptive facts of Sprint 23 (not causal estimates):** 30 first-divergence transport opportunities, 26
  against acting opponents, in 6 scenarios; no projected saturated destination; all at the opening decision; in 25 of 30
  episodes the held carrier is one `baseline-v2` sends straight on toward an unheld objective; post hoc, 17 distinct pair
  setups, the carrier among the first owners of its next objective in 5 of the 25 claimant episodes; passenger-stranding
  recovery unverified.
* **Open:** the T2 family, as a research idea. A T2 increment is scored in this sprint only if it is genuinely distinct
  from T2-X1 (section 9): a different trigger and a different action change, not T2-X1 with a restricted trigger, a
  different matching or a modified hold.

## 4. Scope, the evidence boundary and disclosure

* Offline only. No engine session, no candidate policy, no run card, no change to `baseline-v2`, the stable core, the
  registered evaluators or any historical output.
* **Inputs are committed public files only**, pinned by SHA-256 (normalised line endings) in `inputs.json` before any
  candidate or score is written: the published results of Sprints 18 to 23, Sprint 1's census and the historical
  sprint documents they cite (the list is `SOURCES` in `scripts/s24_select.py`). The living frontier and the README are
  not pinned, since they change after this sprint. No private record or capture is read, and no new figure is computed
  from private data in this sprint; every quantitative claim is a published figure or arithmetic on published figures.
  The minimum offline analysis of each candidate is described, not run.
* Never used: BOKE-2026, the stopped 360-game prevalence study, any hidden holdout.
* T9, PS-1, T1 and T4 are not reopened. T11-O1 stays closed under its original probability endpoint.
* **Disclosure.** Before writing sections 1 to 13 the author read: the frontier; the documents of Sprints 18 to 23 and
  their public result files; Sprint 18's census, admission tables, experiment entries, scores and selection; the PS-1
  design study's corpus findings; and the published rules and action reference in the local documentation snapshot
  (notably the capture rule: a unit on an objective's centre may occupy it when the objective's hex and its six
  neighbours hold no enemy ground unit; the stacking limit; suppression; concealment; close combat; the remove-suppression
  action's fields). The author had also already considered candidate increments, among them an objective-retention
  family suggested by Sprint 18's published losses of held objectives. To limit the effect of that knowledge, the
  rubric's criteria, anchors, weights, thresholds and the E anchors are Sprint 18's verbatim; the additions of this
  sprint (sections 8 to 11) are rules about evidence, cost, history and robustness, and every one of them is fixed here,
  before any candidate entry or score.

## 5. Evidence levels and count units

Every quantitative claim of the candidate entries is an evidence item in `experiments.json` with a level, a count unit, a
population, the number of distinct scenario-sides it covers (or null) and its source. The levels:

| Level | Meaning |
|---|---|
| REGISTERED RESULT | a figure or disposition produced by a registered study or census under rules fixed before it was computed |
| OBSERVED ENGINE MECHANISM | engine behaviour observed in a registered engine session or a captured game |
| OFFLINE ACTION COUNTERFACTUAL | what a frozen rule would have emitted on recorded states, up to its first divergence |
| POST-HOC DIAGNOSTIC | a figure read after a registered result, or arithmetic on published figures, labelled post hoc |
| HYPOTHESIS | a documented rule not yet observed on the engine, a conjecture or an expected mechanism |

Count units are kept apart: games, side-games, scenario-sides, distinct setups, opportunities, units affected, events,
orders, decisions, unit-decisions, scenarios. Repeated side-games that start from the same opening (HH repeats one
scenario's two openings; HI and H0 share openings) are not independent evidence of generality: generality and
opportunity are counted over the 16 distinct H0 scenario-sides and the 50 scenarios. Recorded states after a
candidate's first divergence are never read as on-policy performance.

`scripts/s24_select.py run` reads every evidence value back from its pinned source and refuses on any difference: a keyed
JSON value must be equal in value and type; a quoted passage must occur verbatim in its document (whitespace normalised,
so a hard line break does not hide it) and contain the value as a whole number.

## 6. Candidates

**Families evaluated, each on ONE concrete next experiment:** T2 (only a genuinely distinct increment), T3
reconnaissance and enemy belief, T6 (an independently defined movement branch, not the threat-entry gate), T7-C
concealment including its unresolved exit behaviour, T8 specialised assets, T10 removal of suppression, T12
objective-zone dispersion, and any new family admitted below.

**Excluded** (not scored): T1, T1-r, PS-1, T4, T9. **Carried forward unchanged, not rescored**, each with its reason
written in the results: T5 (Sprint 18 found no guided-fire listing to act on), TO-1 (its registered next step is a
360-session campaign, beyond this sprint's session cap), T11 (T11-O1 closed; a T11 increment would be scored only as a
distinct fire-allocation family under the admission rule).

**Closed increments** that no candidate may repair or restate: the T6-G threat-entry gate, the T11-O1 kill-first rule,
T2-X1 multi-pair transport, PS-1B stalled-movement recovery, the T9 allocator line (T9-v1 to the post-stage-any v6
rule), the T1 deployment split, the T4 indirect-fire versions 1 to 3 and the TO-1 prevalence campaign.

**New families (T13 on).** A structured scan of the possibilities named by the owner (objective defence and local
reserves, infantry tactical positioning, deterministic fire allocation without a kill model, suppression recovery,
local movement congestion prevention, post-capture defence, protection of surviving combat power) and of anything
else the published evidence shows. A new family is admitted only if all seven hold, each with the published figure or
rule that shows it: (1) its trigger is observable seat-locally; (2) its action is listed in `valid_actions`, or is the
withholding or replacement of a `baseline-v2` action, or has a small specific mechanism probe; (3) it is general (no
scenario, map or unit id, no fixed coordinate); (4) it has a mechanism measurable below the game score; (5) its first
experiment needs no large engine campaign; (6) it is distinct from every closed increment and is not a reopened shelved
family; (7) its endpoint does not depend on the unidentified direct-fire probability law. Admission entries are written
in `experiments.json` before any score; ideas not admitted are listed with the condition they fail; identifiers are
given in order of admission.

## 7. The next-experiment entry

Each candidate's entry gives: the tactical hypothesis; the seat-observable trigger; the specific action change; why the
mechanism might help; the measured historical opportunity with its evidence items; the minimum offline analysis; the
smallest engine experiment, if one is needed; the engine sessions of the next experiment and of the engine step it leads
to; the engineering class K and the interaction class X; the largest known interaction risk; a prospectively measurable
stopping condition; what a negative result would teach; and a distinctness statement for every related closed
increment. Experiments are preferred that are directly observable, generalisable, tactically meaningful, quick, local
in their action effects and able to produce new mechanism evidence even when they fail; nothing is rewarded for a
speculative score gain without a measurable mechanism.

## 8. The rubric (`rubric.json`)

**Criteria and weights**: Sprint 18's seven, unchanged: G generality 0.20, L leverage 0.25, O observability 0.15, I
isolation 0.10, M measurability 0.10, R risk (reversed) 0.10, P opportunity 0.10; weighted score W. Integers 0 to 5 with
Sprint 18's anchors verbatim. Sprint 18's historical scores are not changed. **E**, expected information per engine
session, stays a separate dimension with Sprint 18's anchors, scored on the experiment's engine step (for an offline
experiment, on the engine step it leads to).

**Computed criteria.** G is the share of the 50 scenarios with the capability the trigger needs, from a published
count, with Sprint 18's thresholds. P is the share of the 16 H0 scenario-sides with at least one published opportunity,
with Sprint 18's thresholds, then lowered by one level (never below 0) unless the published side count is the trigger's
own condition: a count of the harm the tactic acts on (basis STAKE) or of a listing or capability the trigger needs
(basis CAPABILITY) leaves the trigger itself unmeasured. A candidate with no published opportunity scores P 0, with a
stated reason.

**Leverage cap.** L may exceed 3 only when at least one stake item it cites is a REGISTERED RESULT, an OBSERVED ENGINE
MECHANISM or an OFFLINE ACTION COUNTERFACTUAL covering at least 2 distinct scenario-sides. A post-hoc or hypothetical
stake cannot buy leverage.

**Classes.** K, the engineering class of the next experiment and of the engine step it leads to (the higher): 0 a reading
of published files; 1 a new analysis rule through an existing pinned pipeline; 2 a new observer, capture field or
interpretation model; 3 a new engine-side hook, diagnostic command or candidate add-on executed on the engine; 4 a new
framework. X, the interaction class of the action change: 0 acts only on units `baseline-v2` leaves idle or with action
types it never issues; 1 replaces some `baseline-v2` actions, never a MOVE toward an unheld objective; 2 withholds or
replaces `baseline-v2` MOVEs that can carry a unit toward an objective its side does not hold, the binding constraint of
T9 and of T2-X1. X2 caps I at 3.

**Cost economy C** (computed, used only in two sensitivity variants): 5 less the engine sessions of the next experiment
and of the engine step it leads to, less every engineering class above 1, never below 0.

Every judgement score (L, O, I, M, R, E) carries a one-line reason; G, P, C and the caps are computed by
`scripts/s24_select.py`, never typed.

## 9. Eligibility, and how earlier failures enter

A scored candidate is eligible when all of these hold:

1. its family is not excluded, and the experiment repairs or restates no closed increment; its distinctness statement
   names every related closed increment and says how the trigger and the action change differ;
2. a new family was admitted under section 6 before scoring;
3. its endpoint does not depend on a semantics registered as unidentified (Sprint 21's probability law of the
   direct-fire draw), and it reads no stopped or withheld data;
4. O >= 3, M >= 3, R >= 2 and E >= 2 (Sprint 18's minima);
5. its next experiment needs at most 4 engine sessions, the engine step it leads to at most 4, and its engineering class
   is at most 3;
6. if its interaction class is X2, its next experiment is offline and measures the conflict with `baseline-v2`'s onward
   moves (the claimant measure of Sprint 23, or its equivalent for the candidate) before any engine session.

Earlier failures enter in four ways: a closed increment cannot return (rule 1); a semantics found unidentified blocks
any endpoint that needs it (rule 3); the withholding conflict that shelved T9 and T2-X1 must be measured first wherever
it can recur (rule 6, and the cap on I); and an opportunity that was never measured costs a level of P (section 8).
Family history otherwise enters through the judgement scores, each with its reason; a family with a closed branch is
not penalised for that branch beyond these rules.

## 10. Selection and outcome

1. Eligible candidates are ranked by W.
2. **Tie band.** Every eligible candidate whose W is within 0.15 of the first's (difference at most 0.15) competes in this
   order: higher E; then fewer engine sessions to the mechanism answer (the next experiment's plus the follow step's);
   then lower engineering class K. If the first two in that order are equal on all three, the outcome is FRONTIER_TIE
   among those equal. This is how engine-session and engineering cost enter the choice: through E and the tie order,
   through the eligibility caps, and through the two cost variants of section 11.
3. **Robustness** (section 11): if the selected candidate fails either robustness rule, the outcome is FRONTIER_TIE.
4. **Outcome.** NEXT_INCREMENT_SELECTED: one experiment wins and is eligible; the results then describe the complete
   next experiment, which is not executed and returns to the owner for approval. FRONTIER_TIE: two increments are
   effectively tied; the results then name the specific inexpensive diagnostic that separates them. NO_READY_INCREMENT: no
   candidate is eligible; the results then name the smallest census or mechanism study that would make one ready.

No outcome of this sprint authorizes an engine session or promotes anything. Confirmation stays separately registered
and stricter.

## 11. Sensitivity and robustness

**Weight variants (27).** Sprint 18's 25 (equal weights; each of the seven weights raised and lowered by 0.05 in turn,
the others rescaled to keep the sum at 1; each criterion left out in turn; leverage 0.40; E added as an eighth weighted
criterion at 0.10 and at 0.20), plus C added as an eighth weighted criterion at 0.10 and at 0.20. Eligibility is not
recomputed in the weight variants; each variant's first candidate is chosen with the band and the order E, sessions,
K, L, R, identifier. **Rule 1:** the selected candidate must be first in at least 19 of the 27 (Sprint 18 required 17
of 25); otherwise FRONTIER_TIE between it and the candidate first in the most other variants.

**Judgement perturbations.** Every judgement score (L, O, I, M, R, E) of the selected candidate and of the runner-up
(the next eligible candidate by W) is moved by one point in turn, within 0 to 5 and, for L, within its cap; the main rule
(sections 9 and 10.1 to 10.2, eligibility recomputed) is applied to each. **Rule 2:** if the selected candidate is not
the winner in more than 1/3 of these perturbations, the outcome is FRONTIER_TIE between the selected candidate and the
runner-up. Every variant and every perturbation is reported.

The tie band, the tie order, the thresholds 19 and 1/3, the caps and the eligibility minima are fixed now and are not
changed after candidates are written or scored.

## 12. Outputs, privacy and checks

* Public, `evaluation/s24-tactical-frontier-reselection/`: `rubric.json` and `inputs.json` (this registration),
  `mutation.json` (the selection rule's mutation record), then `experiments.json` (candidate entries, admission entries
  and evidence items, committed before any score), `scores.json` (judgement scores with reasons and the sources of G and
  P) and `selection.json` (computed). Every file is aggregates and text only; `run` refuses if any of them carries a
  forbidden public key or a registered candidate identity string; `freeze --check` and `run --check` regenerate
  `inputs.json` and `selection.json` byte for byte anywhere.
* Code: `src/miaosuan_agent/evaluation/s24_selection.py` (the rule), `scripts/s24_select.py` (pins, evidence check,
  computed criteria and caps, selection), `tests/test_s24_selection.py`, `scripts/mutate_s24.py`.
* Validation before this registration: the tests plant values at every threshold and edge (computed levels and the basis
  penalty, the leverage cap, C, each eligibility rule, the band edge, the tie order, a main-stage tie, 18 and 19 variant
  firsts, the challenger, flip shares of 6/18, 7/19 and 9/19, the evidence checker's planted defects and a quote across a
  line break, the pins). Mutation: 42 of 42 planted defects caught, after the unmutated tests passed in the copy and the
  inputs were re-pinned inside it; the first run caught 36 of 42, and the six survivors were test gaps (the band edge,
  the robustness threshold, the challenger choice, the flip-share edge, a number followed by a separator, the
  rules digest in the pins), closed before this registration.
* Checks before the close: deterministic regeneration of every public file; a private documentation gate binding the
  results' numbers to these files with planted errors; every current earlier documentation gate with its plants; the
  full non-engine suites on the workstation tree, a clean clone and the server's private tree; the privacy scan compared
  as a set with the 104 accepted hit lines; the platform canary rebuilt; a read-only ledger verify showing 2,796
  sessions, none unclosed, no session 2797.

## 13. Not claimed

No tactic is shown to work or fail here. A selected experiment is a research priority under a rubric fixed before
scoring; a family not selected keeps its state. Published figures are re-used as they stand: H0 describes
`baseline-v2`'s decisions on `baseline-v0` trajectories, HH is four games in one scenario, and no figure from recorded
states after a divergence is an on-policy estimate.

## Results (2026-10-08)

Every figure below is read from the committed public files of `evaluation/s24-tactical-frontier-reselection/`, which
`scripts/s24_select.py run --check` regenerates byte for byte, or from the pinned sources their evidence items cite.

### R1. Order of work

The owner's decisions were recorded first (`63a123e`). The registration (`14ac1e4` to
`5509ad3377b9f1a6a8534a47d541da75caa8d139`, tree `7f8729e2f5209afea634ef0d1bc148b46a47cebb`) was pushed at
2026-10-08T15:57:26+08:00 after the workstation suite passed on it (1,995 tests, 93 skipped, exit 0); a fresh clone
from GitHub had the same commit and tree and byte-identical files, and regenerated the input pins and the mutation
record. The candidate entries and their evidence items (`experiments.json`, `fd4eb30`) were then written, checked
against their sources and pushed at 2026-10-08T16:05:50+08:00, before any score existed. The judgement scores
(`scores.json`) followed, and `run` computed the selection once. No private record or capture was read, no figure
was computed from private data, and no engine was called.

### R2. The Sprint 23 qualification and T2

Recorded as registered (sections 2 and 3, and the frontier's T2 row): ORIGINAL-PROTOCOL `T2_DESIGN_INVALID`,
AMENDED-PROTOCOL `T2_UNRESOLVED_INTERACTION_RISK`; both prohibit an engine screen; Sprint 23's files are unchanged.
T2-P1 stays `T2_P1_MECHANISM_SUPPORTED`; T2-X1 is SHELVED; the T2 family stays open, and its distinct increment
scored here (T2-S) is not eligible (R4).

### R3. Evidence changes since Sprint 18

| Sprint | What changed | Level | Consequence for the frontier |
|---|---|---|---|
| 19 | T6-G never fires: 0 gate episodes in each of the four HH side-games; every threat-exposed order already started inside an envelope (`T6_G_OFFLINE_INADEQUATE_OPPORTUNITY`) | OFFLINE ACTION COUNTERFACTUAL | T6's timing branch is closed; T6 is scored on a distinct branch |
| 20 | T11-O1 has no defensible kill probability (`T11_OFFLINE_MODEL_UNAVAILABLE`) | REGISTERED RESULT | T11 is not rescored as T11 |
| 21 | the probability law of the direct-fire draw is not identified (`DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED`); post hoc, an already suppressed infantry loses a squad outside `damage` (25 of 25) | REGISTERED RESULT; POST-HOC DIAGNOSTIC | any endpoint that needs a kill probability is ineligible (rule 3); the cost of suppression for infantry is clearer |
| 22 | embark, carriage and disembark run on the engine (`T2_P1_MECHANISM_SUPPORTED`; the infantry on the ground 75 steps after the disembark order); `baseline-v2` gives a vehicle that ends a move on an objective its side holds a new move at the same decision in 107 of 155 corpus arrivals | OBSERVED ENGINE MECHANISM; REGISTERED RESULT | transport is mechanically available; holding a vehicle on a held objective works against `baseline-v2`'s routing |
| 23 | T2-X1 opportunities only at the opening; claimant share 25/30; post hoc, the carrier among the first owners of its next objective in 5 of the 25 claimant episodes | OFFLINE ACTION COUNTERFACTUAL; POST-HOC DIAGNOSTIC | T2-X1 shelved; wherever a withholding conflict can recur it must be measured offline first (rule 6) |

Sprint 18's census remains the opportunity base: its figures are re-used, not recomputed.

### R4. Candidates

| Family | Next experiment | Next / follow sessions | K | X | Eligible |
|---|---|---|---:|---:|---|
| T2 | T2-S opening dismount of infantry that start on board | 1 / 0 | 3 | 2 | no: X2 without an offline conflict measure (no capture holds the configuration) |
| T3 | T3-O2 short memory of enemies near held objectives | 0 / 0 | 1 | 0 | no: E below 2 (no engine step of its own) |
| T6 | T6-S stacked-column stagger: offline shadow, then a two-session probe | 0 / 2 | 3 | 2 | yes |
| T7-C | T7-E3b controlled concealment-exit diagnostic | 2 / 0 | 3 | 0 | yes |
| T8 | T8-A helicopter altitude probe | 1 / 2 | 3 | 0 | yes |
| T10 | T10-P1 remove-suppression probe | 3 / 0 | 3 | 0 | yes |
| T12 | T12-O1 objective-zone dispersion: offline count, then one deterministic and two head-to-head sessions | 0 / 3 | 3 | 2 | yes |
| T13 (new) | T13-D1 held-objective loss anatomy and garrison shadow (offline), then a two-session garrison probe | 0 / 2 | 3 | 2 | yes |

**New family admitted: T13, objective retention** (post-capture denial): keep the last own ground unit in a held
objective's denial zone (its hex and the six neighbours) while a visible enemy ground unit is near. Its admission entry
gives each of the seven conditions. **Not admitted**, with the condition each fails (`experiments.json`,
`not_admitted`): objective defence and local reserves (no mechanism beyond T13 and T12), infantry tactical positioning
(holding infantry that cannot arrive restates the T9 batch allocator's rule, condition 6), deterministic fire allocation
without a kill model (conditions 4 and 7: its benefit runs through kills or a scored comparison, and a suppressed unit
can still occupy), local movement congestion prevention (condition 6: the deadlock is PS-1's problem, reopened only by
the owner; 10 deadlock episodes in the 8-game corpus, post hoc), protection of surviving combat power (condition 4),
close-combat avoidance (Sprint 18's reason and condition 4). Suppression recovery is T10; post-capture defence is T13.
**Carried forward, not rescored:** T5, TO-1, T11 (section 6).

### R5. Opportunity and interaction-risk evidence

Every figure here is an evidence item read back from its pinned source (63 items: 46 REGISTERED RESULT, 3 OBSERVED
ENGINE MECHANISM, 4 OFFLINE ACTION COUNTERFACTUAL, 10 POST-HOC DIAGNOSTIC; 56 keyed, 7 quoted). Counts are H0 / HH
unless marked; H0 is 16 distinct scenario-sides, HH four side-games of two distinct openings.

| Candidate | Stake and opportunity | Largest interaction risk |
|---|---|---|
| T13 | 40 / 26 losses of objectives the side had held, none with an own unit on the hex before (0 / 0); losses on 7 of 16 H0 scenario-sides; 25 first ownerships in HH; median occupy score 80 against acting policies (REGISTERED RESULT) | the hold competes with `baseline-v2`'s onward move (Sprint 23: 25/30 claimant carriers); post hoc, stationary units on objectives took 13 alone and 40 stacked of the 177 H0 ground damage events |
| T6 | stacked victims in 112 of 177 / 70 of 130 ground damage events, on 13 of 16 H0 scenario-sides (REGISTERED RESULT); post hoc, 57 / 40 on stacked units moving off objectives | a withholding of one hex time; the stacking correction's effect size unidentified |
| T12 | post hoc, 40 / 10 events on stationary stacked holders, on 10 of 16 H0 scenario-sides | the withholding interaction; vehicles leave held objectives at once (107 of 155 corpus arrivals) |
| T7-C | the trigger fires on 11 of 16 H0 scenario-sides (234 shadow orders); damage on a concealable unit 0 / 4 events | an injected diagnostic command; says nothing about benefit |
| T10 | infantry suppression onsets 15 / 4, on 6 of 16 H0 scenario-sides; remove suppression listed in 1,709 H0 unit-decisions, all while suppressed | an undocumented cost; few events per session |
| T8 | altitude listed in 6,957 H0 decisions; 13 aircraft damage events in H0, none while moving, on 4 of 16 H0 scenario-sides | the effect on attack helicopters undocumented |
| T2-S | 74 infantry on board at the start in 10 of 50 scenarios, none in the 8 frozen ones: no historical opportunity | the opening carrier hold, unmeasurable offline |
| T3-O2 | out-of-view attackers caused 15 of 205 / 4 of 158 damage events | phantom threats |

One reading the evidence items do not show by themselves: H0's 40 losses happened on `baseline-v0`'s recorded
trajectories (H0 records `baseline-v0` playing itself; `baseline-v2`'s decisions are reconstructed on them), so only
HH's 26 losses are from genuine `baseline-v2` seats. T13's next experiment therefore classifies each H0 loss by the
recorded order and reports separately whether `baseline-v2`'s reconstructed decision issued the same move.

### R6. Raw and weighted scores

G and P computed (P after the basis penalty), the others judgement scores with the reasons in `scores.json`; no cap
changed any score.

| Candidate | G | L | O | I | M | R | P (basis) | W | E | C | Eligible |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|
| T13 | 5 | 4 | 5 | 3 | 4 | 5 | 1 (STAKE, 7 of 16) | **4.05** | 4 | 1 | yes |
| T6 | 5 | 3 | 5 | 3 | 3 | 5 | 3 (STAKE, 13 of 16) | 3.90 | 3 | 1 | yes |
| T12 | 5 | 3 | 5 | 3 | 4 | 4 | 2 (STAKE, 10 of 16) | 3.80 | 3 | 0 | yes |
| T7-C | 5 | 1 | 5 | 5 | 5 | 4 | 3 (TRIGGER, 11 of 16) | 3.70 | 4 | 1 | yes |
| T10 | 5 | 2 | 5 | 5 | 4 | 3 | 2 (TRIGGER, 6 of 16) | 3.65 | 3 | 0 | yes |
| T3 | 5 | 2 | 4 | 3 | 3 | 5 | 3 (STAKE, 12 of 16) | 3.50 | 1 | 5 | no (E) |
| T8 | 3 | 2 | 5 | 4 | 4 | 3 | 1 (CAPABILITY, 4 of 16) | 3.05 | 4 | 0 | yes |
| T2 | 1 | 2 | 5 | 3 | 5 | 4 | 0 (no H0 side) | 2.65 | 4 | 2 | no (X2) |

G sources: 50 of 50 scenarios with ground units (T13, T12, T7-C) or any unit (T6, T3); infantry 47 (T10); helicopters 26
(T8); infantry starting on board 10 (T2).

### R7. Information per engine session and cost

T13, T7-C and T8 have E 4; T6, T12 and T10 have E 3. T13's and T6's next experiments are offline (0 sessions) and each
leads to a two-session head-to-head step; T12's leads to three, T7-C's diagnostic needs up to two, T8's one plus two,
T10's three. Every engine step executes a new add-on or command (K 3), so the engineering class does not separate the
eligible candidates; the cost economy C ranges from 0 to 1 among them.

### R8. Sensitivity and robustness

* **Main rule.** T13 leads on W (4.05); T6 is 0.15 behind, exactly the band, so the tie order applies and E decides
  (4 against 3). T12 (0.25 behind) is outside the band.
* **Weight variants (rule 1).** T13 is first in 26 of the 27; the exception is the variant without leverage, where
  T7-C (L 1) is first. The threshold is 19.
* **Judgement perturbations (rule 2).** Of the 20 single-point perturbations of T13's and T6's judgement scores, 2 move
  the winner: T13's E lowered to 3 and T6's E raised to 4, each of which makes the two equal on E, sessions and K and
  turns the outcome into a tie. Lowering T13's L to 3 does not: T6 would then lead on W, but within the band E still
  decides. The limit is more than 1/3.
* **What the selection rests on.** Not on T13's leverage score but on E inside the band: T13's next engine step
  (frequent, directly observed held-objective losses and garrison holds) is judged more informative per session than
  T6-S's (a derived exposure rate). A reader who scores those two E values equal obtains a FRONTIER_TIE between T13 and
  T6, which the next experiment's offline shadows of both would separate.

### R9. Outcome: NEXT_INCREMENT_SELECTED, T13-D1

**Selected: T13-D1, the held-objective loss anatomy and garrison shadow**, an offline diagnostic with no engine
session. The selection is a research priority under the rubric registered before scoring; nothing is promoted, and
T13 enters the hypothesis register as `IDEA`.

### R10. The next experiment, described (not executed)

**Question.** Are held objectives lost because the last own ground unit is ordered out of the objective's denial zone,
and would a garrison rule that keeps that unit in the zone while a visible enemy ground unit is near have touched those
losses at an acceptable cost in onward captures?

**Populations and evidence boundary.** H0 (the 8 replay-corpus games, 16 scenario-sides; the recorded actions are
`baseline-v0`'s, and `baseline-v2` is reconstructed as in Sprint 18) and HH (the 4 Sprint 12 head-to-head timelines, the
`baseline-v2` seats, 2 distinct openings), pinned by Sprint 18's frozen input file; HI has no loss (the inert side never
occupies) and serves only as a check that the shadow never fires there without an enemy. Sprint 23's evidence
boundary: certificates before a side's first divergence, first-divergence opportunities, later recorded-state
opportunities descriptive only. Never: BOKE-2026, the stopped prevalence study.

**Definitions to freeze in its registration.** Denial zone: the objective's hex and its six neighbours. Loss: Sprint
18's N4 event (the side held the objective at the previous decision and not now). Departure classes for the last own
ground unit to leave the zone before the enemy's occupation: V-ORDER (it left alive under a recorded MOVE; in H0 also
whether `baseline-v2`'s reconstructed decision issued the same MOVE), V-LOSS (it was destroyed in the zone), V-OTHER
(anything else, listed). For V-ORDER: steps from departure to loss; the nearest visible enemy ground unit at departure;
whether the capturing enemy was in view, seen within 300 steps before (T3-O2's question) or never seen; the departing
unit's next destination, held or unheld; whether it was among the first owners there. The garrison shadow: the trigger
and hold of the T13 entry, with its distance (proposed: the largest published direct-fire range plus one hex) and its
bound (proposed: 300 steps) fixed in the registration before any count.

**Fidelity first.** The diagnostic must reproduce Sprint 18's published figures (H0 33,696 decisions, the 123
`baseline-v2` differences, HH 11,524 decisions equal to the recorded seat, the 40 and 26 held-objective losses, none with an
own unit on the hex) or stop as invalid.

**Prospective stop conditions** (any one ends the line with no engine step):

1. V-ORDER in fewer than half of the losses, H0 and HH separately and pooled (losses come from destruction: a fire or
   formation problem);
2. fewer than 4 losses the garrison shadow would have touched at a valid first divergence, or touched losses on fewer
   than 2 distinct scenario-sides;
3. the departing unit among the first owners of its next objective in more than half of the touched V-ORDER losses (the
   hold's cost would be confounded with its benefit, as in T2-X1).

Otherwise the disposition is ready for a separately registered two-session mechanism probe, returned to the owner for
approval: 2130511121 head to head against `baseline-v2`, both seat orders, the garrison add-on on `baseline-v2`;
endpoints: garrison episodes and holds, losses of a garrisoned objective while the garrison lives in the zone (none
expected by the capture rule), losses after release or destruction, garrison losses, first-ownership steps against the
four HH games; stops: a garrisoned objective lost with the garrison alive in the zone, garrisons destroyed in half or more
of the episodes with an enemy approach, or any objective first owned later than in all four HH games.

**Engineering.** One rules module and a driver that subclasses Sprint 18's census reader (as Sprints 19 to 23 did),
with tests and mutation tests; a run of minutes on the evaluation server; K 1 for the diagnostic.

**What a negative result teaches.** Held objectives are lost to destruction or to situations one garrison cannot cover,
so retention needs fire or formation (T12) rather than holding; or the onward moves are worth more than retention,
which bounds every hold-type tactic on `baseline-v2`. Either way the anatomy of objective losses, unmeasured so far, is
learned.

### R11. Expected engine-session cost

Zero for the selected experiment. Two sessions for the mechanism probe it can lead to, only after a ready disposition,
a separate registration and the owner's approval. Session 2797 is not opened by this sprint.

### R12. Families not selected

Their states are unchanged: T6 (`IDEA`; its stagger branch is the runner-up), T12, T7-C, T10, T8, T3 and T2 (`IDEA`;
T2-P1 supported, T2-X1 shelved, T2-S ineligible because its opening hold cannot be measured offline and no historical
side has the configuration).

### R13. Process notes

* The first mutation run caught 36 of 42 planted defects; the six survivors were test gaps at boundaries (the band edge,
  the robustness threshold, the challenger choice, the flip-share edge, a number followed by a separator, the rules digest
  in the pins), closed with configurations found by a small search before the registration; 42 of 42 since, and again
  after the results were bound.
* A commit subject of 73 characters was reworded before the first push (tree unchanged), and a word matching one of the
  privacy scanner's patterns was removed from the new files before the first commit.
* Review before committing the candidate entries found two denominators printed without an evidence item and one side
  count bound to the wrong census flag (aircraft damage, not the altitude listing); fixed, and a test now requires every
  number in an entry's text to be one of its own evidence values or a declared constant.

### R14. Close-out

* The results were pushed as `113d233fd3c51ec4ada7ae349d3f6a23e13d58fa` (tree
  `95be0b7a62bb2f84b21c0e28525c48b1d4e6c392`) at 2026-10-08T16:17:16+08:00; a fresh clone from GitHub had the same commit
  and tree and regenerated `inputs.json` and `selection.json` byte for byte, and the evaluation server's main clone was
  fast-forwarded to it by bundle and is clean. All 17 sprint commits were audited as a set (author, single-line ASCII
  subjects of at most 72 characters, no body).
* Tests at that commit: the workstation tree ran 1,998 tests (92 skipped) with exit 0; a clean clone from GitHub 1,995
  (100 skipped) with exit 0; the evaluation server's private tree 2,011 (7 skipped; 7,127 s) with exit 0 and the ledger
  file byte-identical before and after.
* Documentation gates: this sprint's private gate (`local/diagnostics/s24/doc_gate.py`) binds the results to the public
  files and the copied logs and catches all its planted errors; every earlier current gate passes with its plants, and
  the four retired `_v1` copies fail as at Sprint 23's close-out.
* Privacy: the scan over every reachable blob at the results commit (1,062 blobs) found 105 hit lines: the accepted 104,
  identical as a set, plus one new line, the process note of R13 as first written, which described a removed scanner
  word by using it. It names no secret, credential, host, path or private value and is adjudicated benign
  (`local/diagnostics/s24/privacy-adjudication.txt`); it was pushed before the scan and stays in history unless the
  branch is rewritten, which was not done. The note was reworded in this close-out so later revisions add no further
  hit. Proposed baseline: 105, pending the owner's confirmation.
* Platform canary: rebuilt on the workstation and the server, SHA-256 `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`,
  no smoke mismatch on either host.
* Engine ledger: read-only verify after the server suite, 2,796 sessions opened and closed, none unclosed, integrity ok,
  state chain continuous, the last event the close of session 2796; ledger file SHA-256 unchanged from the start of the
  sprint; no session 2797. No engine installation, configuration or historical result was touched.

### R15. Recommendation (one)

Register and run T13-D1, the offline held-objective loss anatomy and garrison shadow of R10, with no engine session:
freeze its definitions, distance, bound, fidelity figures and the three stop conditions first, then run it once on H0
and HH. If it ends ready, write the two-session garrison probe's registration for the owner's approval; the engine is
not called without that approval.
