# Sprint 23: the smallest T2 exploratory policy and its screen design

**REGISTERED — EXPLORATORY TRACK — OFFLINE DESIGN STUDY — NO ENGINE SESSION — NOTHING PROMOTED**

Sprint 22 closed with `T2_P1_MECHANISM_SUPPORTED`: engine 4.1.0 executed embark, carriage and disembark for one
registered infantry-carrier pair in one deterministic game against the inert control. On 2026-10-08 the owner approved
the next step: design, offline and from existing evidence only, the smallest generalisable T2 transport policy and its
first exploratory screen. This sprint opens no engine session (session 2797 is not authorized), runs no tactical
comparison and promotes nothing. The question is whether the one-pair mechanism can become a credible, deterministic,
seat-local, multi-pair exploratory tactic. Dates are business dates in UTC+8.

Sections 1 to 18 (the candidate, the matching, the time model, the occupancy rule, the failure handling, the corpus,
the evidence boundary, the outputs, the readiness rule and the screen rule), the code they name and the frozen
`inputs.json` were committed and pushed before the opportunity study was run. Results follow in a separate section; no
registered section is edited after the study.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `9748d5c6b11dbe45c9ba163a34316f825c234d1e`, tree `aed82424a5e7781a3c230c5afc5612defc261f54`, identical on the workstation, GitHub and the evaluation server |
| Engine ledger | 2,796 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only verify at the start of the sprint); ledger file SHA-256 `eaae02bb0b1805a6ee0cf757f96fa39ec8e443f821835b6feb994dee55230bea`; session 2797 not authorized |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close and reproduced since, compared as a set |

## 2. Frozen evidence (not reinterpreted)

From `docs/SPRINT22_T2_TRANSPORT_PROBE.md` (session 2796, 1930331196 C3, `baseline-v2` blue against the inert red):
embark accepted and the infantry aboard 75 steps after the order; the loaded carrier at its destination 560 steps after
release, equal to its route's free-flow time; disembark listed 75 steps after arrival, once the carrier's stop
transition ended; the infantry on the 80-point objective A at step 785, against a foot route of 3,456 free-flow steps in
a 2,880-step game; the carrier had to be held on the destination because `baseline-v2` re-orders a vehicle that ends a
move on an objective its side holds; 2,881 decisions reconstructed with no difference. One deterministic pair; no
performance claim. It is not an A/B result and is not treated as one here.

From `docs/SPRINT18_FRONTIER_RESET.md` and `evaluation/s18-frontier-reset/census.json`: infantry and infantry fighting
vehicles coexist in 47 of the 50 scenarios; `baseline-v2` issued no embark or disembark in the analysed corpora; in H0
the infantry move orders have a median free-flow time of 2,304 steps (20 of 51 cannot arrive before the end), in HH
1,584 (8 of 32); embark was listed to infantry in 39 H0 and 957 HH unit-decisions. From Sprint 22's public witness
search (`evaluation/s22-t2-transport-probe/witness.json`): in the three actual `baseline-v2` games against the inert
control the single-pair trigger fired at decision 1, and in two of them `baseline-v2` sent the infantry and the carrier
to the same objective. These published aggregates were known before this registration; no T2-X1 prevalence figure was
computed before the freeze.

## 3. Question and scope

Can Sprint 22's transport intervention be generalised from one selected pair to several independent eligible pairs of
a seat without sending infantry to unintended objectives, consuming carrier capacity incorrectly, holding carriers
without bound, creating avoidable stacking conflicts, sacrificing major `baseline-v2` movement opportunities, creating
unexplained interactions between pairs, or needing hidden information or scenario-specific exceptions? The output is a
proposed policy, an opportunity study on existing records, a frozen readiness disposition and, only if ready, one small
proposed screen. Nothing is executed on the engine.

## 4. The proposed candidate `t2-transport-x1`

`src/miaosuan_agent/experiments/t2_transport_x1.py`, identity `t2-transport-x1`, status **PROPOSED — NON-EXECUTABLE —
UNAPPROVED** (`EXECUTABLE = False`). It is in no run card; its agent class refuses `setup`; only this sprint's scripts
import it (`tests/test_t2_transport_x1.py` pins all three). It runs `baseline-v2` first through the existing add-on
wrapper and edits that decision only as section 5 allows. It imports Sprint 22's frozen module unchanged for its
observation helpers and constants (the documented 75-step transition, the 150-step bound and the stacking limit of 4);
the Sprint 22 candidate, its tests, card and results are not modified.

**Trigger** (play stage; read from the seat's own observation and `baseline-v2`'s decision; a pair is recorded with
the first condition it fails, in this order):

| # | Condition |
|---:|---|
| 1 | an own infantry (type 1, sub_type 2) and an own infantry fighting vehicle (type 2, sub_type 1) stand in the same hex, both as operators |
| 2 | both controlled by the seat; both stationary (no move path, zero speed, no stop transition), not suppressed, not in an embark or disembark, the infantry not aboard; neither unit has been in an episode of this game |
| 3 | the infantry's listing offers embark naming that carrier, with the key set exactly `target_obj_id` |
| 4 | `baseline-v2` emits exactly one action for each of the two units and it is a MOVE with a route |
| 5 | both routes end on the same hex, and that hex is an objective |
| 6 | the infantry has no competitive timely arrival on foot: its foot arrival is at or after the end of the game, or later than the transported arrival |
| 7 | the transported arrival is strictly before the end of the game and strictly earlier than the foot arrival |
| 8 | the carrier lists infantry among its passenger types, carries no infantry, and its documented per-type infantry capacity is at least one; passengers of other types do not count against it |
| 9 | the destination admits the episode (section 8) |

The same-objective requirement (condition 5) is the minimal generalisation: the transported infantry goes exactly where
`baseline-v2` was already sending it. It is not relaxed after the study. Destination-alignment designs that would
transport infantry towards an objective other than its own (the carrier's objective, the nearest unheld objective) are
future hypotheses only.

## 5. Mechanism preservation

Only Sprint 22's three intervention classes:

* **A. Embark**: a selected infantry's `baseline-v2` MOVE is replaced, in place, by the embark copied from its listing.
* **B. Carrier hold**: the selected carrier's `baseline-v2` MOVE is withheld during the embark transition and, at the
  registered objective, while the carrier settles and the infantry disembarks. Every other `baseline-v2` action of the
  carrier (an occupation, a shot) passes.
* **C. Disembark at the registered objective**: the carrier's `baseline-v2` action (if any) is replaced by the disembark
  copied from the carrier's listing, when it is listed for the infantry and the hex holds fewer than 4 own ground units.

Failure handling **R** (section 9) is not a tactical edit: it uses the same two actions to return a live passenger to the
ground after a failed episode, within bounds. All other `baseline-v2` actions pass unchanged and in `baseline-v2`'s
order. Nothing else is introduced: no new route, no objective reassignment, no T9 capacity allocation, no enemy belief,
no threat-aware movement, no target selection change, no occupation or fire rule. No T2-v2 feature is stacked on this
candidate.

## 6. Multiple-pair matching

At each decision the pairs that pass conditions 1 to 8 are ranked, in this frozen order:

1. the same destination (already required by condition 5, so it is a filter, not a key);
2. the larger projected saving (section 7);
3. infantry unable to arrive on foot before the end, first;
4. the earlier transported arrival;
5. the lower infantry id, then the lower carrier id.

In that order a pair is selected unless its infantry or its carrier has already been selected at this decision (an
*infantry conflict* or a *carrier conflict*), or its destination does not admit it (section 8). A unit takes part in at
most one episode per game, an infantry never switches carriers, a carrier takes at most one new infantry, and the
selection does not depend on the order of the observation's lists (tested by permutation). The order was fixed before
any prevalence was computed and is not tuned to outcomes. As a sensitivity diagnostic only, the study also matches with
Sprint 22's order (infantry id, then carrier id) and reports at how many decisions the selected set differs.

## 7. Transport time model

For a pair triggered at step *s*, with *c* the free-flow time of the carrier's `baseline-v2` route and *f* that of the
infantry's own `baseline-v2` route (`720 / basic_speed * cost` per hex, Sprint 11's lower bound, both measured from the
units' current hex at the trigger, so no travel already completed is subtracted):

* projected carrier arrival *A* = *s* + 75 + *c* (embark, then carriage);
* transported arrival (delivery) *D* = *s* + 75 + *c* + 75 + 75 (embark, carriage, the carrier's stop transition,
  disembark), Sprint 22's observed chain;
* foot arrival *F* = *s* + *f*;
* projected saving = *F* − *D*; condition 7 requires *D* < `max_step` and *F* − *D* > 0, both strict;
* infantry unable to arrive on foot: *F* ≥ `max_step`;
* on-objective gain = min(*F*, `max_step`) − *D*, the projected extra steps on the objective within the game.

These are projected mechanical quantities. They do not say that a transported infantry would arrive at *D* in a
counterfactual game, nor that the gain is a combat or score benefit. Waiting in front of a full hex, suppression, the
opponent and congestion can only delay the transported chain.

## 8. Destination occupancy and admission

The engine allows at most 4 own ground units in a hex (`rules_rules.txt` line 54); passengers aboard are not counted as
ground units (Sprint 22's reading, consistent with its observation of one ground unit on the destination when disembark
was listed). A transport episode adds two ground places to its destination at disembark: the carrier and the infantry.

**Admission (condition 9)**, online and seat-local: own ground units standing on the destination now, plus the places
still needed there by this seat's active episodes heading to it (one for a carrier not yet standing on it, one for an
infantry not yet on the ground on it), plus two for every pair already selected to it at this decision, plus two for the
pair itself, must not exceed 4. Reservations exist only for active episodes, which are bounded (section 9) and whose
arrival is feasible by condition 7; they never cross objectives and never touch another unit's movement. No far-future
or global allocation is made: units of other policies' moves heading to the objective are not reserved for, so the rule
does not guarantee room at arrival. The real guard is at the destination: disembark is issued only when the hex holds
fewer than 4 own ground units (the carrier included). The admission is deliberately conservative (an objective already
holding 3 own ground units admits nothing); the study reports how many otherwise eligible pairs it rejects.

## 9. Episode states and failure handling

Each episode has its own bounded state; one episode's failure never edits another's units. Bounds are Sprint 22's
registered 150 steps (twice the documented 75), unchanged.

| State | Carrier MOVE | Leaves when (seat-observable) |
|---|---|---|
| EMBARK_REQUESTED | withheld | CARRIER_RELEASED when the infantry is aboard this carrier with both units' `get_on` fields cleared; FAILED_GROUND when, at a later step than the order, the infantry is still an operator with cleared `get_on` fields (embark refused or interrupted; Sprint 22's capture shows the fields set one step after the order) or after 150 steps |
| CARRIER_RELEASED | `baseline-v2`'s | AT_DESTINATION when the carrier stands on the registered objective with no move path; RECOVERY_WAIT if that has not happened 150 steps after release plus the carrier's free-flow time; FAILED_GROUND if the infantry has left the carrier |
| AT_DESTINATION | withheld | DISEMBARK_REQUESTED when disembark is listed for the infantry and the hex holds fewer than 4 own ground units (the carrier's action replaced by the listed disembark); RECOVERY_WAIT if the carrier leaves the hex, or 150 steps after arrival (reason: stacking limit or not listed) |
| DISEMBARK_REQUESTED | withheld | DONE when the infantry is an operator again, absent from the carrier's passengers, `get_off` fields cleared; the listed disembark is issued again if, after the order, the infantry is still aboard with cleared fields and it is listed (an interrupted or refused disembark); RECOVERY_WAIT if the carrier leaves or after 150 steps |
| RECOVERY_WAIT | `baseline-v2`'s | RECOVERY_HOLD at a later decision when the carrier has no move path and its hex holds fewer than 4 own ground units; RECOVERED if the infantry is on the ground |
| RECOVERY_HOLD | withheld | RECOVERY_DISEMBARK when disembark is listed there and the hex has room; back to RECOVERY_WAIT (or STRANDED after the last attempt) after 150 steps or if the carrier leaves |
| RECOVERY_DISEMBARK | withheld | RECOVERED when the infantry is on the ground; as DISEMBARK_REQUESTED otherwise |
| DONE, FAILED_GROUND, RECOVERED, STRANDED, LOST, INCONSISTENT | `baseline-v2`'s | terminal: no further edit for this pair, and its units are never selected again |

At most 2 recovery attempts. Handling of the named cases: a missing or dead carrier, or an infantry absent outside a
transition (or beyond its bound inside one): LOST; a passenger represented inconsistently (in both lists, or aboard
another unit): INCONSISTENT; a refused or interrupted embark: FAILED_GROUND, both units back to `baseline-v2` at once;
a suppressed carrier or a disembark that is never listed: the bounded wait, then recovery; destination capacity
reached: the bounded wait at the objective, then recovery; an unexpected route completion (the carrier stopping short):
`baseline-v2` keeps control of it until the carriage bound, then recovery; game end: nothing (the episode simply stops).
The longest possible carrier hold is the embark bound plus the destination wait plus the disembark bound plus two
recovery attempts, each of a 150-step wait and a 150-step disembark: bounded, and tested over a whole game.

**Stranded-passenger exclusion.** After the last recovery attempt the infantry stays aboard for the rest of the game
(STRANDED), and a carrier waiting indefinitely in front of a full hex is never stationary, so no recovery can start;
the candidate cannot resolve either without a rule outside the three classes. This risk is not resolved by the design:
it is an exclusion from engine readiness that every screen must carry as a registered stop (section 15), and the
offline study measures how often the projected arrival meets a saturated destination.

Memory: integer pairs per episode (state, the two units, the destination, the embark step, the carrier's free-flow time,
the release, arrival and disembark steps, the end, the reason, the attempts and the recovery hex and step); empty at the
start of every game; memory that cannot be interpreted disables the add-on for the rest of the game without any edit.

## 10. Carrier opportunity cost (measured offline)

For every episode, from the recorded history after its trigger: whether the carrier reached the destination in the
record (on the hex, no move path); the delay from that arrival to `baseline-v2`'s first MOVE order for the carrier and
the number of such orders within the expected destination hold of 150 steps (settling and disembark); whether that
first order goes to another objective the side does not hold at that decision (a *potential claimant elsewhere*);
whether the destination was already held at the carrier's recorded arrival; and the projected suppressed decisions
(150 minus the delay), since `baseline-v2` re-proposes a withheld move at every decision (Sprint 22: 75 of 75). The
transported carrier arrives 75 steps later than the recorded one; the recorded arrival is used as the nearest
available proxy, labelled as such.

The delivered infantry is classified at its projected delivery step from the recorded objective flags: **A** potential
first-capture contributor (the side never owned the objective up to that step); **B** reinforcement of an objective
already held (the side owns it at that step); **C** arrival too late to matter (delivery at or after the end; excluded
by condition 7, so expected empty among selected episodes); **D** unclassifiable (owned earlier but not at that step, or
no recorded state that late). The classification is descriptive and never feeds the candidate. An additional infantry on
an objective already held is not claimed to increase the score.

## 11. Corpus, populations and pins

| Population | Content | Seat analysed | Opponent | `baseline-v2` actions |
|---|---|---|---|---|
| H0 | the 8 replay-corpus games of Sprint 18's frozen inputs (`baseline-v0` mirror games, condition C1) | both seats (16 side-games) | `baseline-v0`, acting | reconstructed on `baseline-v0`'s trajectories, memory chained from empty (Sprint 18's reconstruction) |
| HH | the 4 Sprint 12 head-to-head timelines of Sprint 18's frozen inputs (2130511121 H1, H2) | the `baseline-v2` seat (4 side-games) | the Sprint 12 candidate, acting | the recorded seat; reconstructed from empty memory and required equal |
| HI | the 3 actual `baseline-v2` games against the inert control of Sprint 22's tier 1 (Sprint 10's captures: 1930331196 C2 and C3, 2120531121 C3), included prospectively | the `baseline-v2` seat (3 side-games) | inert control | the recorded seat; reconstructed on its recorded memory and required equal |
| W | the Sprint 22 mechanism witness (session 2796) | | | cited from Sprint 22's public results only; not part of any count |

Never used: BOKE-2026, the stopped 360-game prevalence study, hidden holdouts and sparse captures. Every file of every
population is pinned by SHA-256 in `evaluation/s23-t2-policy-design/inputs.json` (copied from Sprint 18's and Sprint
22's committed input files, re-verified), together with the digests of Sprint 18's and Sprint 22's input files, Sprint
22's witness file and its private reference, the cost data of every scenario, the rules digest
(`s23_design.rules_digest`) and the normalised SHA-256 of the sources the study depends on. `scripts/s23_t2_design.py
run` refuses unless all of them match.

## 12. Evidence boundary

1. **Pre-first-divergence certificates**: at every play decision of a side before its first trigger, the candidate's
   actions from an empty memory equal `baseline-v2`'s; counted per side.
2. **First-divergence action-level opportunities**: the batch the candidate emits at a side's first trigger. Valid in HH
   and HI (the recorded seat is `baseline-v2`'s own trajectory), and in H0 only if `baseline-v2`'s reconstructed actions
   equalled the recorded `baseline-v0` actions at every decision of that seat before the trigger (otherwise the state
   is already off-policy for `baseline-v2`). A batch counts only if the independent batch check passes
   (`s23_design.batch_problems`: every pair meets conditions 1 to 8 recomputed from the raw observation; no unit in two
   pairs; every destination admits its pairs; only the registered edits differ from `baseline-v2`, in its order, with no
   duplicate action; and no admissible pair with both units free was left unselected).
3. **Post-divergence recorded-state opportunities**: every later trigger, evaluated statelessly (no active episodes) on
   the recorded states. After the first divergence every recorded state is off-policy for the candidate, so these are
   opportunity diagnostics only, never the candidate's trajectory; each such batch is also checked independently.

Not claimed: that all prospective pairs could transport simultaneously; that recorded arrival, capture or survival
states would stay unchanged; that a projected saving is a combat benefit; that recorded survival implies passenger
survival. The readiness rule (section 14) reads first-divergence episodes only.

## 13. Outputs and denominators

Public (`evaluation/s23-t2-policy-design/`, regenerating byte for byte with `run --check`): `prevalence.json` (per
side-game and pooled per population and overall: decisions, play decisions, the fidelity counts, infantry and IFVs
present, embark listings, co-located pairs and the pairs passing each condition as pair-decisions and as distinct pairs,
the matching outcomes, decisions with destination contention, selected pairs, `baseline-v2` infantry MOVE actions, the
order-sensitivity count, certificates, the first trigger and its validity, recorded-state episodes and distinct
infantry; the consistency checks and the known answers), `episodes.json` (every first-divergence episode with its
projections, role and carrier-hold facts, by objective value label only; summaries of first-divergence and
recorded-state episodes per population) and `disposition.json`. Unit ids, hexes and routes go only to the private
`local/diagnostics/s23/study-private.json.gz`; every public file passes the project's sanitizer against every unit id
and hex seen. A recorded-state *episode* is a maximal run of consecutive decisions selecting the same pair (thousands
of repeated listings of one pair are one episode); distinct units, pairs and episodes are reported separately. The
fraction of infantry MOVE actions affected is the selected pair-decisions over `baseline-v2`'s infantry MOVE actions;
each selected pair delays one carrier MOVE at its trigger (by the 75-step embark).

**Consistency checks** (any failure is `T2_DESIGN_INVALID`): Sprint 18's published H0 figures (33,696 decisions,
33,680 play decisions, 123 decisions where `baseline-v2` differs from `baseline-v0`) and HH's 11,524 decisions all equal
to the recorded seat; the HI seats equal to the reconstruction at every decision; and the known answers from Sprint 22's
public witness rows: in each HI game whose single-pair trigger sent both units to the same objective, Sprint 22's pair
is in the candidate's first batch at the same decision, and in the game whose units went to different objectives it is
not.

## 14. Readiness rule (frozen thresholds; first match)

| Disposition | Rule |
|---|---|
| `T2_DESIGN_INVALID` | an input or source pin differs (the study refuses to run), a consistency check or known answer fails, any batch check fails, the candidate's step disagrees with its own matching, or a public file fails the sanitizer |
| `T2_NO_GENERALIZABLE_OPPORTUNITY` | fewer than 4 valid first-divergence episodes, or fewer than 2 of them in acting-opponent populations (H0, HH), or fewer than 2 scenarios among them |
| `T2_UNRESOLVED_INTERACTION_RISK` | among the valid first-divergence episodes, the share saturated at the projected carrier arrival (3 or more own ground units other than the pair on the destination, so that disembark cannot be issued) exceeds 1/4, or the share whose carrier would be a potential claimant elsewhere (section 10) exceeds 1/2 |
| `T2_READY_FOR_SMALL_EXPLORATORY_PROPOSAL` | otherwise |

Justification, fixed before the study: the first divergence can be observed at most once per side-game (23 here), and a
screen of a few sessions can only learn something if the trigger recurs; 4 is the smallest count that leaves at least
two acting-opponent observations, one acting observation cannot separate a recurring opportunity from a configuration
accident, and one scenario cannot show generalisation. The two shares are judgment thresholds: with more than one
delivery in four projected onto a saturated objective, capacity failures and stranded passengers rather than transport
would dominate what a small screen observes; with more than half of the carriers foregoing a move to an unheld
objective, the hold's cost would be confounded with any transport benefit in every game of a small screen. Stranding is
an exclusion carried by the screen (section 9), not a readiness criterion beyond the saturation share. A ready
disposition authorizes drafting an exploratory proposal for the owner, not running it.

## 15. The screen-construction rule (applied only if ready)

Built mechanically from the first-divergence evidence (`s23_design.screen`):

* **Phase M** (concurrency mechanism, deterministic, inert opponent): only if an HI side-game's first batch holds two
  or more pairs (concurrent transport has never been observed on the engine): that configuration (the largest batch,
  then the game label), one game, the candidate in that seat against the inert control. Otherwise no phase M; Sprint
  22 already covers the single-pair mechanism.
* **Phase H** (acting opponent): the scenario with the most valid first-divergence episodes in H0 or HH (ties: HH
  before H0, then the scenario id), played head to head against `baseline-v2` once in each seat order (conditions H1 and
  H2).
* At most 3 sessions; no automatic continuation, no large campaign.

Measures: transport episodes and their states; embark and disembark acceptance and completion; distinct infantry
delivered; delivered infantry present on the objective (at delivery and at the end); delivery timing against the
projection; objectives first owned and their timing; destination capacity failures; recoveries and strandings; carrier
holds and withheld moves; carrier losses; infantry losses aboard and after disembark; every action differing from
`baseline-v2` outside the registered classes (expected none); the game margin as exploratory context only.

Registered tactical stops for any future engine session of this screen: (1) an action difference outside classes A,
B, C and R, a duplicate action or a contract error: stop at once; (2) a STRANDED episode, or a carrier lost with its
passenger aboard, in phase M: stop before phase H; (3) in phase M, any objective first owned by the candidate's side
later than in Sprint 10's `baseline-v2` game of that configuration, or not at all, or more own losses than in it: stop
before phase H (the inert games are deterministic, so the reference is exact); (4) in phase H, if half or more of the
first game's episodes end in recovery, stranding or loss: no second game. A mechanism success does not override an
objective-timing or survival regression, and a negative screen leaves Sprint 22's result intact.

## 16. Validation before the study

* **Tests**: `tests/test_t2_transport_x1.py` (the nine conditions in order, the time model at its end-of-game boundary,
  matching conflicts both ways, independent pairs, permutation invariance, admission at occupancy 2 and 3, a nearly
  full objective with two pairs, reservations of an active episode, every state and bound at its boundary, disembark at
  occupancy 3 and a hold at 4, the bounded retry, recovery and its exhaustion, a whole-game bounded hold, independence of
  episodes, malformed memory, the identity's status and whitelist); `tests/test_s23_design.py` (the batch check on the
  candidate's batches and on planted defects, the projections, saturation, roles, the carrier-hold facts, the
  readiness rule at every threshold and in order, the screen rule, the sanitizer); `tests/test_s23_driver.py` (a
  stand-in side-game through the whole per-side pipeline with a scripted `baseline-v2`, including the H0 validity rule
  and the known answers); `tests/test_real_s23.py` (server: `freeze --check` and `run --check`).
* **Mutation**: `scripts/mutate_s23.py` plants defects in the selection, capacity, timing, matching, admission, state
  machine, projections and disposition logic, each in a copied tree, and records whether the tests catch it
  (`evaluation/s23-t2-policy-design/mutation.json`): 57 of 57 caught, after the unmutated tests passed in the copy. The
  first run caught 53 of 56: three test gaps (a carrier action carrying a route that is not a MOVE, an exact tie
  between the foot and the transported arrival, and an active episode whose carrier already stands on the destination
  in the reservations), closed by new tests before the freeze; a mutant added in the second run (a zero saving accepted
  under condition 7) was equivalent, since condition 6 already rejects it, and was replaced by the unable-on-foot
  boundary.
* **Fidelity smoke** (`scripts/s23_t2_design.py smoke`, no prevalence computed): run before the freeze on the evaluation
  server, it reproduced every published figure of section 13 (H0 33,696, 33,680 and 123; HH 11,524 equal) and found the
  HI seats equal to the reconstruction at all 8,643 decisions, with no problem.

## 17. Integrity and privacy

No engine session, no engine installation change, no `.engine_config` change, no reset, restore or reinstall, no
historical result rewritten, no change to `baseline-v2` or to any Sprint 22 file. Private data stay under the ignored
`local/`. The close-out compares the privacy scan with the accepted 104 lines as a set, rebuilds the platform canary,
runs the full non-engine suites and the documentation gates with their plants, and verifies the ledger read-only: 2,796
sessions, none unclosed, the state chain continuous, no session 2797.

## 18. Not claimed

No score, margin, safety or effect claim; no claim that transported infantry would arrive as projected; nothing is
promoted, and no engine use is authorized by any outcome of this sprint.

## 19. Amendment A1 (2026-10-08, before any result was read)

The registration (sections 1 to 18) was pushed as `151624b09e547842823a83a5f805826b13b63a54` (tree
`4c1edbdc2fcaa642c11f5817e0ddf3905e971efd`) at 2026-10-08T12:42:56+08:00; a fresh clone from GitHub had the same
commit, tree and files, and the evaluation server was fast-forwarded to it. The study then ran once from that tree and
**refused to write anything**: the sanitizer reported `saturated_share: private value in text` in the disposition.
The share was published as a reduced fraction of two counts (`str(Fraction(...))`), and a reduced share such as `0`
or `1` equals a small private unit id as a word of a string, the trap Sprint 20 met with bare small integers. The
field holds no unit id or hex by construction, so this is a defect of the registered public format, not an exposure.
No public or private file was written, and no figure was printed.

What the refused run revealed, disclosed here: a disposition carries the two shares only when it has passed the
opportunity minimums of section 14, so the registered run did not end in `T2_NO_GENERALIZABLE_OPPORTUNITY`; and one
share's text equals a small integer. Nothing else was seen.

The amendment changes only the representation: both shares are published unreduced as `part/whole` (for example
`0/7`), and a new test checks the disposition against private ids 0 to 49. The thresholds, the comparisons (still on
exact fractions), the order of the rule and every other file of the registration are unchanged. Read strictly, the
clause of section 14 that makes a sanitizer failure `T2_DESIGN_INVALID` applies to this refusal; it was written for
an exposure of private content, and the owner may still apply it literally. The rules module's digest therefore
changes in `inputs.json` and in the mutation record (57 of 57 caught again), which are regenerated and committed with
this section before the study is run again, once.

## Results (2026-10-08)

Every figure below comes from the committed public files of `evaluation/s23-t2-policy-design/`, which
`scripts/s23_t2_design.py run --check` regenerates byte for byte on the evaluation server, unless it is marked post hoc.

### R1. Registration, amendment and run

The registration was pushed as `151624b09e547842823a83a5f805826b13b63a54` after the local suite passed (1,960 tests,
92 skipped, exit 0) and an audit of its 11 commits; Amendment A1 as `488881edf12a3e172de22838501c8b7fccfd954f` (tree
`9eab516a9dab9a356f4267e7a4911d58b045df80`) at 2026-10-08T12:49:23+08:00, fetched back identical and fast-forwarded
onto the server's clean main clone. From that tree `freeze --check` reproduced `inputs.json`, the study ran once (about
69 s, 15 worker processes) and `run --check` then regenerated all three public files byte for byte.

### R2. Fidelity

| Check | Published | Study |
|---|---:|---:|
| H0 decisions | 33,696 | 33,696 |
| H0 play decisions | 33,680 | 33,680 |
| H0 decisions where `baseline-v2` differs from the recorded `baseline-v0` | 123 | 123 |
| HH decisions, all equal to the recorded `baseline-v2` seat | 11,524 | 11,524 |
| HI decisions equal to the recorded `baseline-v2` seat (recorded memory) | | 8,643 of 8,643 |

The three known answers hold: in 1930331196 C2 and C3, whose Sprint 22 single-pair trigger sent both units to the same
objective, Sprint 22's pair is in the candidate's first batch at decision 1; in 2120531121 C3, whose units went to
different objectives, it is not. The independent batch check found no problem in any batch, the candidate's step agreed
with its own matching at every decision with a selection, and every play decision of a side before its first trigger
is a certificate (the candidate equals `baseline-v2`). No invalidating problem: `T2_DESIGN_INVALID` does not apply.

### R3. Opportunity funnel (pooled over the 23 side-games)

| Stage | H0 | HH | HI | All |
|---|---:|---:|---:|---:|
| side-games | 16 | 4 | 3 | 23 |
| infantry present (distinct per side-game) | 39 | 24 | 15 | 78 |
| infantry fighting vehicles present | 39 | 24 | 15 | 78 |
| embark listed to infantry (unit-decisions) | 39 | 957 | 222 | 1,218 |
| co-located pairs (distinct) | 44 | 27 | 17 | 88 |
| pass conditions 2 to 4 (distinct; both moved by `baseline-v2`) | 39 | 24 | 15 | 78 |
| pass condition 5, the same objective (distinct) | 21 | 14 | 4 | 39 |
| pass conditions 6 to 8 (distinct) | 21 | 14 | 4 | 39 |
| rejected by destination admission, condition 9 (pair-decisions) | 3 | 6 | 0 | 9 |
| infantry or carrier conflicts | 0 | 0 | 0 | 0 |
| selected pairs = distinct infantry helped | 18 | 8 | 4 | 30 |
| decisions with a selection | 10 | 2 | 2 | 14 |
| `baseline-v2` infantry MOVE actions (whole games) | 49 | 28 | 15 | 92 |

Every selection happens at decision 1 (step 0), the first play decision, and nowhere else: the 14 decisions with a
selection are the first triggers of 14 side-games (10 H0, 2 HH, 2 HI), all valid first divergences (in H0 the first
difference between `baseline-v2` and `baseline-v0` comes at decision 136 or later). There is therefore no
post-divergence recorded-state opportunity at all: after the opening, no recorded decision has a co-located pair
that `baseline-v2` moves together to the same objective. The same-objective condition halves the eligible pairs (78 to 39);
of the 957 HH embark listings only 24 pair-decisions have `baseline-v2` moving both units. The selected
pair-decisions are 30 against 92 `baseline-v2` infantry MOVE actions; each delays one carrier MOVE by the 75-step
embark. Matching order made no difference (the identity order selected the same pairs at every decision).

### R4. First-divergence episodes (30)

| | H0 | HH | HI | All |
|---|---:|---:|---:|---:|
| episodes | 18 | 8 | 4 | 30 |
| side-games | 10 | 2 | 2 | 14 |
| scenarios | 6 | 1 | 1 | 6 |
| infantry unable to arrive on foot | 8 | 0 | 2 | 10 |
| role A (potential first capture) | 2 | 0 | 0 | 2 |
| role B (reinforcement of a held objective) | 9 | 4 | 4 | 17 |
| role D (unclassifiable) | 7 | 4 | 0 | 11 |
| saturated at the projected arrival | 0 | 0 | 0 | 0 |
| potential claimant elsewhere | 13 | 8 | 4 | 25 |

Projected savings range from 375 to 2,815 steps (median 1,439); the projected on-objective gain within the game from 375
to 2,095 (median 1,243). No destination held an own ground unit at the trigger, and at the projected carrier arrival the
recorded destination held no other own ground unit in 24 episodes, one in 5 and two in 1: never three, so no projected
delivery meets a saturated objective. All four HI episodes and 26 of all 30 go to a destination shared with a second
pair of the same batch.

**Carrier opportunity cost.** In 28 of the 30 episodes the carrier reached the destination in the record; there the
destination was already held in 23. In 25 episodes `baseline-v2` gave the carrier its next MOVE 0 steps (23) or 1 step
(2) after that arrival, to another objective the side did not hold: the destination hold would suppress about 150
decisions of that order (the median projected suppression is 150). `baseline-v2` gave the carrier 1 to 3 MOVE orders
within the expected 150-step hold in 25 episodes.

### R5. Disposition

The opportunity minimums are met (30 episodes, 26 in acting-opponent populations, 6 scenarios). The saturated share is
0/30, within its maximum of 1/4; the claimant share is 25/30, above its maximum of 1/2. By the rule of section 14:

**T2_UNRESOLVED_INTERACTION_RISK.**

The frozen same-objective transport trigger has enough opening opportunities, deterministic matching and an
independently checked batch, but the carrier hold that disembark requires collides with `baseline-v2`'s own onward
routing in most episodes: the carrier that would wait 150 steps on a held objective is, in 25 of 30 episodes, the unit
`baseline-v2` sends straight on to an objective the side does not yet hold. No screen is proposed (the screen rule of
section 15 applies only when ready); nothing is promoted and no engine use is authorized. Sprint 22's mechanism result
stands unchanged.

### R6. Post-hoc facts (read after the disposition; they change nothing)

From `local/diagnostics/s23/posthoc.py` on the private study file:

* **The episodes repeat openings.** HH's two triggered side-games and H0's 2130511121 blue side start from the same
  state, as do HI's two games and H0's 1930331196 sides; the 30 episodes are 17 distinct pair configurations in 10
  opening scenario-sides of 6 scenarios. The claimant flag holds in 15 of the 17 configurations (3 differ between
  populations because their recorded trajectories differ).
* **The hold rarely delays a recorded first capture.** Of the 25 claimant episodes, the carrier was among the side's
  first owners of the objective `baseline-v2` sent it to next in 5 (that ownership came 61 to 181 steps after the
  order); in 20 that objective was first owned without this carrier. The claimant measure therefore bounds the cost from
  above; it is the registered measure and the disposition stands.

### R7. What Sprint 23 shows

1. **T2 as specified is an opening tactic.** Under `baseline-v2`, co-located, stationary infantry-carrier pairs that are
   both sent to the same objective exist only at the first play decision; no later opportunity appears in any of the 23
   side-games.
2. **Stacking is not the binding constraint.** No projected delivery meets a saturated objective, and the admission rule
   rejects only 9 pair-decisions, all in 2130511121's blue opening, where seven eligible pairs aim at two objectives
   together and four are admitted.
3. **The carrier's onward move is the binding constraint.** Disembark needs a settled carrier, and `baseline-v2` moves a
   vehicle on from a held objective at once; holding it is the price of every delivery, and in most episodes the held
   carrier is one `baseline-v2` would send to an unheld objective.
4. **Stranding remains an exclusion** carried by the design (section 9), untested on the engine.

### R8. Recommendation (one)

An offline frontier re-selection for the owner: re-score the Sprint 18 rubric with the evidence of Sprints 19 to 23
(T6-G inadequate opportunity, T11-O1 closed, T2 mechanism supported and T2-X1 `T2_UNRESOLVED_INTERACTION_RISK` as an
opening-only tactic whose hold competes with `baseline-v2`'s onward routing) and choose the next increment, with no
engine use. Session 2797 is not opened.
