# Sprint 22: T2-P1 transport mechanism qualification

**REGISTERED — EXPLORATORY TRACK — MECHANISM PROBE, NOT A SCORE SCREEN — AT MOST ONE ENGINE SESSION (2796) — NOTHING PROMOTED**

On 2026-10-07 the owner approved moving to the T2 family (transport and infantry defence) after Sprint 21 closed
T11-O1 with `DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED`, and authorized the first frozen T2 increment of Sprint 18, T2-P1:
can engine 4.1.0 execute the complete practical infantry-transport chain (infantry on the ground, embark, infantry aboard
an infantry fighting vehicle, the vehicle moving normally to an objective, disembark, infantry back on the ground at the
objective) without corrupting `baseline-v2`'s unrelated behaviour? It is a mechanism study: no score, margin, winner or
kill count enters any rule, and nothing can be promoted. At most one engine session is authorized, session 2796, and only
after every offline prerequisite below is frozen and passes; session 2797 is not authorized. Dates are business dates in
UTC+8.

Sections 1 to 9 (the starting state, the offline semantics audit, the timing basis and the witness-selection
procedure) were committed and pushed before the witness search was run. The rest of the registration follows in later
sections, committed and pushed before session 2796 is opened; results follow in a separate section, and no registered
section is edited after the engine is used.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `7d843d32fbb47a7320b722cfaefef27f53ae187a`, tree `b3f0f2add7eca37040731bdabd6d648332363a3c`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,795 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `65c803504b6f93f6e6d2a7e36892078a9cd116924fbb819a8dbb595a4039e8de`; session 2796 never opened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close and reproduced since, compared as a set of lines |
| Documentation snapshot | `local/source-archives/docs-live-snapshot-20260929` (fetched 2026-09-29T18:41:10+08:00; `rules_rules.txt` SHA-256 `db2542608d115e982ef4d2c1bc5969bf3760d6f7b86b1c708b51fcb6728402c1`, `reference_actions.txt` `8a9149fa967557f0b6e73afe4e3bc50edca5dae30a8270eb79e093eea79a8337`, `reference_observations.txt` `04a779ac5c6717f820213c6d886ee87097b5936ee4535d62e8c9000579ab71fa`) |

## 2. Frozen history

Not reinterpreted: T9 `SHELVED`; Sprint 18 `NEXT_FAMILY_SELECTED` (eligible order T6, T11, then T2); Sprint 19
`T6_G_OFFLINE_INADEQUATE_OPPORTUNITY`; Sprint 20 `T11_OFFLINE_MODEL_UNAVAILABLE`; Sprint 21
`DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED`, which closed T11-O1 under its registered endpoint. No direct-fire adjudication
work is continued here. The active family is T2.

## 3. Sprint 18's T2 facts (preserved)

From `docs/SPRINT18_FRONTIER_RESET.md` and `evaluation/s18-frontier-reset/`: infantry and infantry fighting vehicles
coexist in 47 of the 50 scenarios; `baseline-v2` issued no embark or disembark in the analysed corpora; H0 infantry
move orders have a median free-flow time of 2,304 steps against 140 for vehicles, and 20 of 51 could not arrive before
the end; HH infantry 1,584 against 120, 8 of 32 unable to arrive. Listings existed: H0 embark in 77 decisions (39
infantry unit-decisions), disembark in 256; HH embark in 937 decisions (957 infantry unit-decisions), disembark in 2.
Sprint 18 selected T2-P1 because one deterministic session answers embark, carry and disembark.

## 4. Question and scope

The question is whether the transport mechanism is usable, not whether transport improves the score. Exactly one
infantry-carrier pair is tested in one deterministic game against the inert control, in the configuration of a witness
selected offline by a procedure frozen in sections 8 and 9. If no witness meets the minimum criteria, or if the action
semantics cannot be specified safely, the sprint ends offline and session 2796 is not opened.

## 5. The registered intervention

The candidate (section 11) runs `baseline-v2` on the candidate's own current observation and memory at every decision.
Outside the selected pair its actions are `baseline-v2`'s. Only these edits are permitted:

1. **Embark** at the registered trigger: the selected infantry's `baseline-v2` move is replaced by EMBARK.
2. **Carrier hold**: the selected carrier's `baseline-v2` MOVE is withheld while the pair is in a registered transport
   transition: the embark transition, and, at the destination, the stop transition and the disembark transition.
3. **Disembark** at the destination: DISEMBARK is issued from the carrier for the same infantry.

No route redesign, objective reassignment, threat logic, fire rule, T9 allocation, scenario-specific exception, second
passenger or second pair.

**Owner clarification of edit 2 (2026-10-07, before the witness search).** The owner's brief named the hold for the
embark transition. The offline audit (section 6) found that, under that wording alone, disembark at the objective could
never become legal: disembark is listed only for a settled carrier (it is never listed during the 75-step stop
transition), while `baseline-v2` gives a vehicle that ends its move on an objective a new move almost at once (on an
objective its side already holds, at the same decision in 107 of 155 corpus arrivals; on one it does not hold, it
occupies and moves on one or two decisions later in 37 of 81). Asked with that evidence, the owner chose to extend edit
2 to the destination: from the carrier's arrival on its own `baseline-v2` destination until the infantry is back on the
ground (or the pair ends), the carrier's `baseline-v2` MOVE is withheld; every other `baseline-v2` action of the carrier
passes; the route and the objective stay `baseline-v2`'s. This is an operational clarification of the mechanism probe,
not a tactical rule.

## 6. Offline transport-semantics audit

Sources: the documentation snapshot of section 1 (`reference_actions`, `reference_observations`, `rules_rules`,
`tutorials_basic`), the SDK's own sample agent (`local/sdk-reference/land_wargame_sdk/ai/agent.py`, which builds both
actions by copying `target_obj_id` from the listing under the actor's id), and aggregate counts over the corpus of
section 8 (`evaluation/s22-t2-transport-probe/semantics.json`, regenerated byte for byte by
`scripts/s22_analysis.py semantics --check`; 12 inert-control games, 33,492 seat decisions).

| Item | Finding |
|---|---|
| Action 3 (embark) schema | `{actor: seat, obj_id: passenger, type: 3, target_obj_id: vehicle}` (reference_actions, 上车) |
| Action 4 (disembark) schema | `{actor: seat, obj_id: vehicle, type: 4, target_obj_id: passenger}` (reference_actions, 下车) |
| Actor | embark: the passenger (listed under the infantry's id); disembark: the vehicle (listed under the carrier's id) |
| Identification | the listing option's only key, `target_obj_id`: the vehicle for embark, the passenger for disembark; observed key set exactly `target_obj_id` in all 22,018 embark and 43,538 disembark options |
| Eligibility (observed) | embark listed for infantry (type 1, sub_type 2) in 457 unit-decisions and for unmanned ground vehicles in 21,561, always targeting an own infantry fighting vehicle (type 2, sub_type 1) in the same hex, both units stationary |
| Capacity | carriers expose `valid_passenger_types` and `max_passenger_nums` per passenger sub_type; every infantry fighting vehicle in the corpus reads `[2, 4, 7]` and `{2: 1, 4: 1, 7: 2}` (one infantry unit, one unmanned ground vehicle, two loitering munitions); the undocumented field `loading_capacity` reads 3 or 4 and is not used |
| Same hex, stationary | required by rule: “上车单位与车辆位于同一格，且上车单位与车辆均处于停止状态，可执行上下车命令。” (`rules_rules.txt` line 39); embark and disembark must wait for the 75-step stop transition to end (line 9) |
| Transition | “上下车均需要75秒时间，在此过程中不可执行其它命令，也不可取消上下车命令。” (line 40); fields `get_on_remain_time`, `get_on_partner_id`, `get_off_remain_time`, `get_off_partner_id` on both units |
| Aboard | the passenger is in `observation["passengers"]` (same fields as an operator) with `on_board` 1 and `car` = the carrier, and the carrier lists it in `passenger_ids`: all 69,144 passenger unit-decisions of the corpus (all loitering munitions) |
| Disembark completed | the passenger is back in `operators`, not in `passengers`, absent from the carrier's `passenger_ids`, both units' `get_off` fields cleared |
| Disembark listing | listed in 21,769 of 21,769 unit-decisions of a settled carrier with passengers, in none of 921 during its stop transition and none of 11,882 while it moved |
| Suppression | a suppressed unit or vehicle cannot start embark or disembark; suppression interrupts embark (lines 41-42); a suppressed vehicle cannot disembark its passengers (line 107) |
| Movement and march | march state forbids embark and disembark (line 25); embark and disembark wait for the stop transition (line 9) |
| Stacking | “在同一个六角格内，不可堆叠超过4个本方地面单位。如果六角格内已存在4个本方地面单位，则格外本方地面单位不能再进入或通过该六角格。” (line 54) |
| Same-hex engagement | interrupts embark and disembark (line 169) |
| Runtime evidence | no corpus game issued an embark or disembark order (0 of either; the reader counts the corpus's moves and occupations), so the transition has never been observed on this engine |

Both actions can therefore be constructed unambiguously by copying a listed option: `T2_P1_PROTOCOL_AMBIGUOUS` does not
apply.

## 7. Transition timing

**Basis: `DOCUMENTED_75`.** The embark and disembark time is documented as 75 seconds in its own rule (line 40) and in
the tutorial (“上下车均会需要75秒倒计时时间”), not inferred from the stop transition. One engine step is one second in
the observation (`time.tick` 1.0, `max_time` equal to `max_step`, 2,880). Because no embark has ever been observed,
completion is nevertheless detected from state, never from a timer alone: aboard (or back on the ground) with the
transition fields cleared on both units. The frozen bound of every transition is 150 steps (twice the documented
time): aboard within 150 steps of the embark order, disembark listed within 150 steps of the carrier's arrival on the
destination, back on the ground within 150 steps of the disembark order. The bounds were set before any engine use and
are not tuned to a result.

## 8. Witness corpus and minimum criteria

**Corpus.** Sprint 21's frozen list of usable full-step captures (`evaluation/s21-direct-fire-semantics/inputs.json`,
every record, compact log and snapshot file pinned by SHA-256; a changed file refuses the search), restricted to games
against the inert control: 12 games. Tier 1: the three actual `baseline-v2` games (Sprint 10, sessions 2774, 2776 and
2778). Tier 2, considered only if no tier-1 game meets every minimum: the other nine, whose seat must equal reconstructed
`baseline-v2` at every decision up to and including the trigger decision. Not used: BOKE-2026, the stopped 360-game
prevalence data, hidden holdouts, sparse captures (Sprint 2's game b, the residual-516 games, the PS-1 games).

**Trigger.** The witness of a game is the candidate's own first trigger in it (`t2_transport_p1.trigger`, section 12),
evaluated on the seat's own observation and `baseline-v2`'s reconstructed decision: own infantry in ascending id, then
its embark options in ascending carrier id; the first pair where both units are controlled by the seat, stand in the same
hex, have no move path, zero speed, no stop transition, no suppression and no embark or disembark under way, the
infantry is not aboard, the carrier carries no infantry and has infantry capacity, the option's key set is exactly
`target_obj_id`, and `baseline-v2` emits exactly one action for each unit and it is a MOVE.

**Minimum criteria** (all required; `s22_probe.MINIMUMS`): a full-step capture; an inert opponent; `baseline-v2`
reconstructed from the seat's observation and memory equals the recorded actions at every decision up to the trigger;
the trigger fires; the trigger decision precedes the game's first fire order or judge record (the trajectory up to it is
deterministic); `baseline-v2`'s move for the carrier at the trigger ends on an objective; and the trigger step plus
three documented transitions (embark, stop, disembark) plus the carrier's free-flow time to that objective is below
`max_step`.

## 9. Witness selection

Among games meeting every minimum, the witness is the first in this frozen lexicographic order (`s22_probe.RANKING`):

1. tier (1 before 2);
2. the carrier's predicted destination (the objective at the end of its `baseline-v2` move at the trigger) never held
   four own ground units from the trigger to the end of the historical game;
3. that destination was not already held by the side, with the carrier not on it, at the trigger step plus the
   documented embark time in the historical game (it is still the carrier's natural destination when it is released);
4. a positive free-flow saving: the infantry's free-flow time on foot to the destination (cheapest infantry path,
   `720 / basic_speed * cost` per hex) exceeds the carrier's along its `baseline-v2` route;
5. the infantry cannot reach the destination on foot before the end;
6. the earliest trigger step;
7. the game id.

The preferences only choose the witness; they change no rule of the candidate. The search
(`scripts/s22_analysis.py witness`) publishes, for every corpus game, the minimum criteria, the preference values and
the trigger decision and step, with objectives by value label only (`evaluation/s22-t2-transport-probe/witness.json`);
unit ids, hexes and paths go only to the private reference `local/diagnostics/s22/witness-reference.json`, whose
SHA-256 the registration pins. If no game meets every minimum, the disposition is `T2_P1_NO_DETERMINISTIC_WITNESS` and
session 2796 is not opened.

## 10. Witness search result and rehearsal

Sections 1 to 9 and the code they name were pushed as commit `441034a29c55895739148030cf89aa2d3ff751a6` at
2026-10-07T22:18:26+08:00. The search then ran once on the evaluation server from that commit and regenerates byte for
byte (`scripts/s22_analysis.py witness --check`).

| Corpus game | Tier | Minimum criteria | Trigger (decision, step) | Destination | Carrier free flow | Infantry on foot | Peak own ground units on the destination | Infantry can arrive on foot |
|---|---:|---|---|---|---:|---:|---:|---|
| 1930331196 C3, Sprint 10 g04 (session 2776) | 1 | all met | 1, 0 | 80-point objective A | 560 | 3,456 | 2 | no |
| 2120531121 C3, Sprint 10 g02 (session 2774) | 1 | all met | 1, 0 | 50-point objective B | 420 | 3,024 | 3 | no |
| 1930331196 C2, Sprint 10 g02 (session 2778) | 1 | all met | 1, 0 | 50-point objective A | 440 | 2,736 | 3 | yes |
| 1910631192 C3, Sprint 6 P-A (session 2462) | 2 | all met | 1, 0 | 50-point objective A | 480 | 3,312 | 4 | no |
| eight other tier-2 games (Sprint 10 T9-v1, Sprint 16, Sprint 17) | 2 | the seat differs from `baseline-v2` before any trigger | none | | | | | |

In every eligible game the trigger is the first play decision. No eligible game's destination was taken by another own
unit before release, and every free-flow saving is positive. **Selected: 1930331196 C3**, `baseline-v2` blue against the
inert red (Sprint 10's game g04). The 2120531121 C3 game equals it on every preference and is separated only by the last
rule, the game id; the 1930331196 C2 game ranks third because its infantry could arrive on foot; the tier-2 game is not
considered because tier-1 games qualify. At the trigger the selected pair is the infantry and the infantry fighting
vehicle that start in the same hex; `baseline-v2` sends both to the 80-point objective A, the infantry along a route of
3,456 free-flow steps (it cannot arrive before the end, at 2,880) and the carrier along one of 560. The private reference
`local/diagnostics/s22/witness-reference.json` has SHA-256 `3e918de23c5615f9ec7c889ad3c1f6deffc48cf8c2252da7988cb422b8b7712a`.

**Rehearsal** (`scripts/s22_analysis.py rehearse`, server): the candidate replayed over the witness game's decisions 0
and 1 equals `baseline-v2` at decision 0 (deployment), and at decision 1 emits exactly `baseline-v2`'s 20 move orders
with the infantry's move replaced in place by the embark copied from its listing and the carrier's move removed; its
memory is EMBARK_REQUESTED for the registered pair; no difference from `baseline-v2` is outside the registered edits.
Nothing later can be rehearsed on recorded data: after the trigger the game is the candidate's own.

**Post-selection context** (read privately after the selection, disclosed, changing nothing): the infantry and the
carrier are the only own ground units in their start hex and the carrier carries nothing; in the historical game no enemy
unit ever stood on the destination and no same-hex engagement occurred (no judge record at distance 0); the destination
was first owned at decision 522 by another own unit, before the carrier's own historical arrival at decision 561. The
loaded carrier, held about 75 steps at the start, is therefore likely to arrive on an objective its side already holds,
where `baseline-v2` would send it on at once: the destination hold of section 5 is expected to be exercised.

**Expectation under the documented semantics** (an expectation, not a rule): aboard about 75 steps after the order,
arrival at the earliest about 560 steps after release, disembark listed about 75 steps after arrival, the infantry on
the ground about 75 steps after the order, all well before step 2,880.

## 11. The candidate `t2-transport-p1`

`src/miaosuan_agent/experiments/t2_transport_p1.py` (identity `t2-transport-p1`, add-on `t2_transport_p1`) is a new
exploratory mechanism identity, not a baseline. It runs `baseline-v2` first through the existing add-on wrapper
(`experiments/exploratory_addon.py`, unchanged) and then applies only the edits of section 5 for one pair. It reads only
the seat's own observation and its bounded memory; it holds no numeric literal other than the documented action and
class codes, the documented 75-step transition, its 150-step bound and the stacking limit of 4 (a test enumerates them);
it imports no analysis module; its memory is empty at the start of every game (`AddonAgent.setup` and `reset`). If the
add-on raises anything other than a contract violation, the wrapper plays `baseline-v2`'s decision and records the error
(an S7 stop). Source identity: 24 files, `baseline-v2`'s set, the add-on wrapper and the candidate module, digest
`1cb53199a246557bb0e564a7f5156b68396680c4b3a39a39c12023b98b96f65f` (line endings normalised).

## 12. Transport state machine

| State | Entered when (seat-observable conditions) | Carrier MOVE | Leaves to |
|---|---|---|---|
| READY | start of the game (empty memory) | `baseline-v2`'s | EMBARK_REQUESTED at the trigger (section 8): the infantry's move replaced in place by the listed embark, the carrier's move withheld |
| EMBARK_REQUESTED | the embark was emitted | withheld | ABOARD when the infantry is in `passengers` with `car` the carrier and `on_board` 1, listed in the carrier's `passenger_ids`, not in `operators`, and both units' `get_on` fields are cleared; FAILED if the carrier is absent, the representation is inconsistent (in both lists, or aboard another unit), or 150 steps pass |
| ABOARD | as above (same decision) | `baseline-v2`'s | CARRIER_RELEASED at once |
| CARRIER_RELEASED | the hold ended | `baseline-v2`'s | the destination is fixed at the end hex of the first `baseline-v2` MOVE of the carrier; AT_DESTINATION when the carrier stands on it with no move path; FAILED if the infantry leaves the carrier, either unit is absent or the representation is inconsistent |
| AT_DESTINATION | arrival | withheld | DISEMBARK_REQUESTED when the carrier's own listing offers disembark for the infantry (key set exactly `target_obj_id`) and the hex holds fewer than 4 own ground units: the carrier's action replaced in place by the listed disembark, or the disembark appended if it has none; FAILED (destination at the stacking limit) if the hex holds 4 then, or (disembark not listed) if 150 steps pass, classified as the stacking limit if the hex holds 4 at that moment; FAILED if the carrier leaves the hex or the infantry leaves it |
| DISEMBARK_REQUESTED | the disembark was emitted | withheld | DISEMBARKED when the infantry is in `operators`, not in `passengers` and not in the carrier's `passenger_ids`, both units' `get_off` fields cleared; FAILED if the carrier is absent or leaves the hex, the representation is inconsistent, or 150 steps pass |
| DISEMBARKED | as above (same decision) | `baseline-v2`'s | DONE at once |
| DONE, FAILED | terminal | `baseline-v2`'s | none: the decision is `baseline-v2`'s exactly for the rest of the game |

Inside the two transitions the infantry may be in neither list for a step; the pair then waits within the bound. Memory
that cannot be interpreted ends the pair (FAILED) without any edit. Every other `baseline-v2` action of the carrier
(an occupation, for example) passes in every state.

## 13 to 19. Mechanism endpoints

The analysis reads every endpoint from the seat's own observations, the emitted actions and the engine's echoes, not
from the candidate's memory (`s22_probe.transport_facts` and the endpoint functions).

* **Embark** (section 13) succeeds only if the registered embark was emitted at the trigger decision, its echo carries
  no error, the infantry is represented aboard the selected carrier with the `get_on` fields cleared within 150 steps,
  no decision in that window shows an inconsistent representation, and the carrier stays present and controlled by the
  seat. Otherwise `T2_P1_MECHANISM_REFUTED`; no second parameterization is tried.
* **Hold and release** (section 14): recorded per decision, `baseline-v2`'s carrier action, the candidate's action, the
  passenger and transition state; after release the carrier is `baseline-v2`'s; no other path or objective is imposed.
* **Carry** (section 15) succeeds only if, after release, a `baseline-v2` move of the carrier is emitted and not refused,
  the carrier changes hex, the infantry is aboard the same carrier at every decision until the disembark order with
  its position equal to the carrier's, no action is emitted for it while aboard, and the carrier stands on the
  destination with no move path before the end. The travel time is compared with the route's free-flow time and the
  infantry's foot estimate, descriptively.
* **Destination** (section 16): the end hex of the first `baseline-v2` move of the carrier after release; it must be an
  objective; whether it equals the predicted 80-point objective A is reported.
* **Stacking** (section 17): the own ground units standing on the destination (passengers excluded) at the decision
  disembark would be issued (its listing present), or at the end of the 150-step settle bound without a listing. At 4
  or more nothing is issued and, if embark and carry succeeded, the disposition is
  `T2_P1_DESTINATION_CAPACITY_BLOCKED`; no other objective or pair is tried.
* **Disembark** (section 18) succeeds only if it is listed within 150 steps of arrival, emitted exactly once as listed,
  not refused, and within 150 steps the infantry is again an own operator on the destination hex, not aboard, with the
  `get_off` fields cleared, no inconsistent representation in between, and the carrier present.
* **After disembark** (section 19, reported, not gated): the infantry's listed action types, whether occupation is
  listed, suppression, the cleared passenger fields and the destination's ownership. No occupation is forced.

## 20. On-policy fidelity

At every candidate decision the live timeline re-decides `baseline-v2` and the candidate from the seat's own
observation and carried memory, requires equality with the emitted actions, the add-on's change records, the recorded
state, `baseline-v2`'s trace digest, no add-on error, and the memory chain (empty before the first decision); and it
requires every difference between the emitted actions and `baseline-v2`'s to be a registered edit
(`s22_probe.unregistered_differences`: the embark at READY to EMBARK_REQUESTED, a carrier MOVE removed when the decision
ends in a hold state, the disembark issued at the destination, the remaining actions in `baseline-v2`'s order). The
analysis repeats all of it offline from an empty memory. Any difference is `CAPTURE_INVALID`.

## 21. Capture

Three read-only observers through Sprint 9's `Tee`: `T9Capture` and the exploratory capture, unchanged, and the Sprint 22
timeline (`evaluation/s22_capture.py`), which keeps for every step the all-seeing state, the seat's observation (operators,
passengers, listings for the pair, transition fields, objective ownership), memory, emitted actions and their
pre-execution copies, the engine's echoes, units boarded and landed, and the final post-step state. Record and five
capture files are written exclusively under the ignored `local/evaluation/s22-t2-transport-probe-1/`, digested in the
record; nothing is overwritten.

## 22. Card, runner and the one session

The card is `evaluation/s22-t2-transport-probe-1/manifest.json` (built and checked by `scripts/build_s22_card.py`): one
game, `1930331196.C3.s22-t2-transport-probe-1.p01`, the inert control red and the candidate blue (Sprint 10's seats),
runtime `baseline-v1-runtime-r2`, ledger base session 2795, ceiling 1, expected session 2796; it pins the normalised
SHA-256 of every file of `s22_probe.FROZEN_FILES`. `scripts/run_s22_probe.py` refuses to start unless the tree is clean
and committed, the card rebuilds byte for byte with every pin equal to the checkout, the private witness reference has
the digest `inputs.json` pins, and the ledger audit passes; it plays the game through `scripts/run_s22_game.py` in the
registered evaluator's isolation with a hard timeout. The game entry point refuses, before the engine is touched, any
other card, a changed pin, another candidate digest, a dirty tree, an existing record or capture, a session beyond the
ceiling, a wrong thread environment, or a missing or altered witness reference. Session 2797 is not authorized; no
retry or replacement of an opened session, which counts even if it fails.

**Whitelist.** A new safeguard (`tests/test_s22_probe.py`): the identity `t2-transport-p1` may appear in exactly one run
card, this one, bound to the registered digest; any other JSON naming it lies in `evaluation/s22-t2-transport-probe/`
and is never executable; the generic builders and runners do not name it; only the Sprint 22 scripts import the module.

## 23. Structural stops

| Stop | Meaning |
|---|---|
| S1 | engine-installation integrity failure (session close or the ledger's state chain) |
| S2 | a session after 2795 that is not this card's game under its digest and the candidate's registered digest, an unclosed session, or more than one session (any session other than 2796) |
| S3 | a file outside the ignored tree appeared, or a tracked file changed, during the game |
| S4 | a contract error, a margin that is not the engine's `<side>_win`, or a game that did not complete |
| S6 | a replay mismatch |
| S7 | an observer error; a missing or digest-mismatched capture; a live decision, change record, state or memory that differs from the seat-local reconstruction; a difference from `baseline-v2` that is not a registered edit; a candidate add-on error; captures and record disagreeing on steps or on the seat's move orders; a decision not reconstructed; a wrong scenario, condition or seat; a `max_step` other than 2,880 |
| SP | the candidate differs from `baseline-v2` before the registered trigger decision, or its actions at decision 1 are not the registered trigger actions, or the pair is not the registered one |

Any structural stop ends the study at once; nothing is retried. A wrong engine installation, a ledger inconsistency, a
wrong session number, scenario, seat or card, a digest or identity mismatch, a dirty tree, a capture or reconstruction
failure, a privacy exposure, an unclosed session, a wrong action schema or an unexplained candidate action are all
covered by these stops.

## 24. Dispositions (first match)

| Disposition | Rule |
|---|---|
| `T2_P1_PROTOCOL_AMBIGUOUS` | the transport actions cannot be specified from the documentation and listings (offline; no session) |
| `T2_P1_NO_DETERMINISTIC_WITNESS` | no corpus game meets every minimum criterion (offline; no session) |
| `CAPTURE_INVALID` | a session occurred and any structural, fidelity, prefix or registered-difference requirement fails |
| `T2_P1_DESTINATION_CAPACITY_BLOCKED` | embark and carry succeeded and the destination held 4 own ground units when disembark would have been issued |
| `T2_P1_MECHANISM_REFUTED` | any core transition failed: embark refused, voided or never aboard; the passenger relation not established or broken; the carrier unable to move with it or never reaching the destination; disembark never listed within the bound, refused or voided; the infantry not back on the ground at the destination coherently |
| `T2_P1_MECHANISM_SUPPORTED` | every endpoint of sections 13 to 18 holds and no unexplained behaviour occurred |

The first two cannot apply any more: the semantics are specified (section 6) and a witness was selected (section 10).
`T2_P1_MECHANISM_SUPPORTED` means only that transport is mechanically usable in this one deterministic probe; it does
not mean a score improvement, general safety, promotion or readiness for confirmation.

## 25. Score

Scores, margin, winner and kills are recorded as record facts if the harness produces them and enter no rule.

## 26. Validation before session 2796

* **Tests** (`tests/test_t2_transport_p1.py`, 31; `tests/test_s22_probe.py`, 36): both action schemas as copies of the
  listed options; the exact pair, the wrong pair (another class, another side, not controlled), the same-hex
  requirement, stationarity (path, speed, stop transition), suppression, transitions under way, passenger capacity, a
  carrier already carrying infantry and one carrying other passenger types, a missing listing and a wrong key set,
  `baseline-v2` giving either unit something other than a move; the infantry's move replaced in place and nothing
  else changed; the carrier hold exactly in the hold states with its other actions passing; every transition and each
  bound at its exact boundary (150 passes, 151 fails); the passenger appearing only with the transition over; the
  passenger leaving independent ground control; the carrier resuming `baseline-v2`; the destination from its first move
  after release; occupancy 3 (disembark issued) and 4 (blocked, nothing issued); the disembark listing; a refused
  disembark; the passenger back on the ground; game reset; the disappearance of either unit; inconsistent
  representations; malformed memory; the source digest; the session ceiling of exactly 2796 and every ledger defect; the
  structural checks; the registered-difference and prefix checks clause by clause; every endpoint fact with planted
  defects; the disposition order; the public sanitizer; the observer's reconstruction, memory chain and difference
  check against a live agent, with tampering detected; and the whitelist. Two of the tests play the real game loop
  (`evaluation.game.play`) with the three observers against a stand-in transport engine (`tests/fixtures/s22_engine.py`,
  documented semantics only): the complete chain is `T2_P1_MECHANISM_SUPPORTED` with no reconstruction or difference
  finding, a refused embark `T2_P1_MECHANISM_REFUTED`, and three immobile own tanks on the destination
  `T2_P1_DESTINATION_CAPACITY_BLOCKED`. `tests/test_real_s22.py` (server, 4) regenerates the semantics, witness and
  inputs files, repeats the rehearsal, and, once they exist, the result files and the mutation record.
* **Mutation** (`scripts/mutate_s22.py`, `evaluation/s22-t2-transport-probe/mutation.json`): 64 of 64 planted defects
  caught, each with the card rebuilt in the copy and, for candidate defects, the source digest re-pinned in the copy so
  that only the logic tests can catch them: the action schemas, the in-place replacement, every hold, the hold's scope,
  every bound, both transition-cleared conditions, the stacking boundary and its absence, the trigger's conditions, the
  passenger leaving, the destination, the carrier leaving, malformed memory, a second trigger after a terminal state, the
  carrier's absence; the selection's tiers, ranking and feasibility; the ledger ceiling, expected session, digest and
  integrity; the stops; the difference check's scope, order, holds and disembark; every prefix clause; the endpoint
  bounds, refusal, passenger, position, arrival, stacking, emission and destination clauses; the disposition's problem
  and precedence clauses; the facts' aboard conditions and control; the observer's comparisons and digests. The first
  run caught 58 of 64: four test gaps (the infantry given a non-move action, a refused embark judged on its echo alone,
  aboard before the transition fields clear, the prefix digests with another seat's actions present), closed before the
  record; and two equivalent defects (a terminal state's early return, whose omission changes nothing, and the tier
  restriction, which the ranking's first key enforces as well), replaced by a second trigger after a terminal state and
  tier 2 preferred to tier 1.
* **Stand-in rehearsal of the runner** (private, `local/diagnostics/s22/standin_rehearsal.py`; the transport stand-in,
  a session context that records nothing, the ledger file byte-identical before and after): a 40-step game completed,
  wrote its record and five captures with matching digests, raised S7 and SP, and the runner stopped with one game
  recorded; a full-length game completed with SP as its only stop (the stand-in is not the witness), all 2,881
  decisions reconstructed live with no consistency or difference finding; with the prefix check disabled inside the game
  module only, the analysis re-derived and memory-compared all 2,881 decisions with no difference, found the prefix
  failure on its own and decided `CAPTURE_INVALID`, and its public files passed the privacy checks; pointed at the
  stand-in's own pair and trigger, the analysis found no problem and decided `T2_P1_MECHANISM_SUPPORTED` (states
  EMBARK_REQUESTED, CARRIER_RELEASED, AT_DESTINATION, DISEMBARK_REQUESTED, DONE; the carrier's move withheld at 74
  destination decisions); a refused embark gave `T2_P1_MECHANISM_REFUTED` and three immobile tanks on the destination
  `T2_P1_DESTINATION_CAPACITY_BLOCKED`; an unknown game, an existing record, a dirty-tree flag and an altered witness
  reference were refused.
* **Server rehearsal and regeneration**: the semantics, witness and inputs files regenerate byte for byte, and the
  rehearsal of section 10 passes, on the server from the committed tree.
* **Registration checks**: the registration pushed and fetched back byte for byte; the server fast-forwarded; the
  workstation, GitHub and server at the same commit and tree; the full non-engine suites; the privacy scan compared as a
  set; the canary rebuilt; a read-only engine verify; the ledger still at 2,795 with none unclosed. Their results are
  reported in the results section.

## 27. Outputs and privacy

* Public (`evaluation/s22-t2-transport-probe/`): before the session `semantics.json`, `witness.json`, `inputs.json` (the
  corpus pins, the digests of the semantics, witness and private reference files, the card's canonical digest, the
  candidate digest, the rules digest) and `mutation.json`; after it `games.json` (session, reconstruction counts,
  structural stops, prefix result, record facts), `mechanism.json` (every endpoint fact and verdict, the candidate's state
  sequence, the holds, the destination label, travel times) and `disposition.json`, all regenerating byte for byte
  (`scripts/s22_analysis.py run --check`; its ledger read stops at session 2796 so that it regenerates after later
  sprints, while the runner audits the whole live ledger). Every public file passes the forbidden-key and private-value
  checks: no unit id, hex or path.
* Private (ignored `local/`): the record and captures, `local/diagnostics/s22/witness-reference.json`,
  `local/diagnostics/s22/analysis-private.json` (ids, hexes, decisions of every event).

## 28. Not claimed

No score, effect, population or generality claim. One deterministic probe shows one trajectory of one pair.

## Results (2026-10-08)

Every figure below comes from the committed public files of `evaluation/s22-t2-transport-probe/`, which
`scripts/s22_analysis.py run --check` regenerates byte for byte from the private record and captures, or from the private
logs and post-hoc listing named where used. Scores are record facts that enter no rule.

### R1. Registration and pre-engine checks

Sections 1 to 9 were pushed as `441034a29c55895739148030cf89aa2d3ff751a6` before the witness search; the complete
registration, every frozen file, the card, the inputs, the tests and the mutation record as
`75b35b2ca0b63832a64d0be634af3cbc40a63e90` (tree `57d069bbb3d7b49bb0cbbcbdbe89d18cd3e64a44`) at
2026-10-07T22:58:12+08:00, after an audit of its 16 commits. A fresh clone from GitHub had the same commit and tree and
all 18 sprint files byte for byte; the evaluation server was fast-forwarded to the same commit by bundle, and on that
committed tree the card, the semantics, witness and inputs files regenerated, the rehearsal passed and the stand-in
rehearsal passed with the clean-tree guards in force. Before session 2796: the workstation tree ran 1,889 tests (89
skipped) with exit 0, a clean clone from GitHub 1,886 (97 skipped) with exit 0, and the server's private tree 1,902 (8
skipped; 6,899 s) with exit 0 and the ledger file byte-identical before and after; the privacy scan over every reachable
blob (1,012 blobs) found 104 hit lines, identical as a set to the accepted 104; the platform canary rebuilt byte for byte
on both hosts; a read-only verify reported 2,795 sessions, integrity ok, state continuous, the last event a close.

### R2. Session and capture integrity

| Session | Game | Candidate seat | Wall time | Structural stops | Decisions reconstructed offline, memory compared, differences |
|---:|---|---|---:|---|---|
| 2796 | `1930331196.C3.s22-t2-transport-probe-1.p01` | blue | 111.8 s | none | 2,881, 2,881, 0 |

The game was opened once (server clock 2026-10-07T17:16:01Z, a host clock that runs ahead by the offset recorded in
`docs/ENGINE_INSTALL.md`), completed 2,881 steps, and closed with integrity ok; nothing was retried or replaced and no
second session was opened. The ledger audit found exactly one session after 2795, the card's game under the card's
digest and the candidate's registered digest. The live timeline found no consistency error and no difference from
`baseline-v2` outside the registered edits; the offline replay re-derived every decision and memory from an empty memory
with no difference. `CAPTURE_INVALID` does not apply.

### R3. Prefix

The candidate equalled `baseline-v2` at decision 0, and at decision 1 emitted exactly the registered trigger actions for
the registered pair (SP passed live and offline): the infantry's move replaced in place by the embark copied from its
listing, the carrier's move withheld, every other move unchanged.

### R4. Endpoints

| Endpoint | Observed | Verdict |
|---|---|---|
| Embark | emitted at the trigger, accepted; the infantry represented aboard the carrier with the transition fields cleared 75 steps after the order (the relation itself also appeared at 75); no inconsistent representation; the carrier present and controlled throughout | holds |
| Hold and release | the carrier's `baseline-v2` move withheld at the trigger decision only, because neither unit listed any action during the embark transition; released 75 steps after the order | as registered |
| Carry | `baseline-v2`'s first move of the carrier after release accepted; the carrier moved and stood on its destination 560 steps after release, equal to the route's free-flow time of 560; the infantry aboard at all 635 decisions from boarding to the disembark order, its position equal to the carrier's, no action emitted for it | holds |
| Destination | 80-point objective A, the predicted objective; an objective | holds |
| Stacking | 1 own ground unit (the carrier) on the destination when disembark was listed | not blocked |
| Destination hold | the carrier's `baseline-v2` move withheld at 75 decisions after arrival, while the carrier settled | as registered |
| Disembark | listed 75 steps after arrival, emitted once as listed, accepted; the infantry an own operator on the destination hex again 75 steps after the order, with the transition fields cleared, no inconsistent representation, the carrier present | holds |
| After disembark (reported) | listed actions move, embark, change state and split; occupation not listed (the objective was already the side's); not suppressed; the passenger fields cleared | reported |

The candidate's own state sequence agreed: EMBARK_REQUESTED at step 0, CARRIER_RELEASED at 75, AT_DESTINATION at 635,
DISEMBARK_REQUESTED at 710 and DONE at 785. The infantry, whose foot route to the same objective takes 3,456 free-flow
steps and cannot be completed in a 2,880-step game, stood on the objective at step 785.

### R5. Disposition

Embark, carry and disembark succeeded at the registered destination, the destination was below the stacking limit, and
no structural, fidelity, prefix or registered-difference problem occurred. By the rule of section 24:

**T2_P1_MECHANISM_SUPPORTED.**

It means only that engine 4.1.0 executed the complete infantry-transport chain for this one registered pair in this one
deterministic probe, with `baseline-v2` driving everything else unchanged. It is not a score improvement, not general
safety, not a promotion and not readiness for confirmation; nothing was promoted, and no further engine use is
authorized.

### R6. Post-hoc facts (read from the private capture after the disposition; they change nothing)

From `local/diagnostics/s22/posthoc.py`:

* The only actions emitted for the pair in the whole game were the embark, the carrier's single `baseline-v2` move at
  release and the disembark. The candidate seat's only refused action was one shot by an unrelated unit (code 516, the
  target already removed), `baseline-v2`'s known residual class.
* Neither unit listed any action during either transition; during its stop transition on the destination the carrier
  listed move and change of state, which is why `baseline-v2` proposed a move at every one of those 75 decisions: without
  the destination hold the owner approved in section 5 the carrier would have left before disembark was listed.
* After landing the infantry stayed on the objective at every one of the remaining 2,095 decisions and was present at
  the end of the game.
* Record facts (enter no rule): blue margin 550, occupation 310, attack 78.

### R7. What Sprint 22 shows

1. **Both transport actions are specified by their listings.** Embark is listed under the passenger and disembark under
   the carrier, each with the single key `target_obj_id`; copying the listed option was accepted both times.
2. **The documented 75-step transitions hold exactly in this probe**: aboard 75 steps after embark, disembark listed 75
   steps after arrival (the stop transition), on the ground 75 steps after disembark.
3. **Carrying cost no speed here**: the loaded carrier took exactly its route's free-flow time.
4. **The integration constraint is `baseline-v2`'s, not the engine's**: `baseline-v2` re-orders a vehicle that ends a
   move on an objective its side holds, so any transport policy built on it must keep the carrier still for the stop
   transition before disembark can be listed.

### R8. Recommendation (one)

Design, offline and for the owner's approval only, the smallest T2 exploratory policy and screen built on the observed
mechanics: the same seat-local trigger generalised to every co-located infantry-carrier pair whose infantry `baseline-v2`
sends to an objective, the carrier's destination hold kept, with the evidence needed to size a screen (how often the
trigger is available, how many infantry orders it would replace, and the travel time saved) computed on the existing
captures before any engine request. The screen itself is not run in this sprint, and session 2797 is not opened.

### R9. Close-out

* **Maintenance found by the close-out.** The first close-out run of the server's private suite at the results commit
  `6755ea058b3fdea25ce29ecfa123585c3269b1ff` failed one test, Sprint 21's regeneration test: Sprint 21's inventory lists
  every capture folder under `local/evaluation/`, so this sprint's new capture folder entered a fresh inventory (one more
  usable game) and `freeze --check` reported a mismatch, although nothing of Sprint 21 had changed; the registration-time
  run could not see it because the folder did not exist yet. Commit `186556d473f64bb3edfdbae55b2285aaf7bf9eb6` changes
  only that test: it runs Sprint 21's frozen driver unchanged, in process, with its folder listing bounded to the folders
  Sprint 21's committed `inputs.json` names, and still runs `run --check` as a program; Sprint 21's driver, pins and
  public files are untouched. With the new folder admitted the bounded comparison fails, and bounded it passes.
* Tests at `186556d473f64bb3edfdbae55b2285aaf7bf9eb6` (tree `550fab103cd04357c8e39e0c08dc81532b60fb67`): the
  workstation tree ran 1,894 tests (89 skipped) with exit 0; a clean clone from GitHub at the results commit ran 1,891
  (97 skipped) with exit 0 (the maintenance commit changes a test that skips off the server); the evaluation server's
  private tree ran 1,907 tests (7 skipped; 6,962 s) with exit 0, regenerating the
  semantics, witness and inputs files, the rehearsal, the three result files and the mutation record, with the ledger
  file byte-identical before and after.
* Documentation gates: Sprint 22's private gate (`local/diagnostics/s22/doc_gate.py`) binds the registration and the
  results to the public files and the copied logs and catches every planted error; every earlier current gate passes
  with its plants (the four retired `_v1` copies fail as at Sprint 21's close-out), and Sprint 10's gate on the server
  reports 40 checks with no failure and catches its 15 plants.
* Privacy: the scan over every reachable blob at the results commit (1,019 blobs) found 104 hit lines, identical as a
  set to the accepted 104.
* Platform canary: rebuilt byte for byte on the workstation and the server.
* Engine ledger: read-only verify after the session, 2,796 sessions opened and closed, none unclosed, integrity ok,
  state chain continuous; the Sprint 22 audit of the whole live ledger passes (session 2796 the card's game, no other
  session after 2795). Session 2797 was not opened. The server's development worktree was removed; the evidence stays
  under the ignored `local/` tree.
