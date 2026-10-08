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
