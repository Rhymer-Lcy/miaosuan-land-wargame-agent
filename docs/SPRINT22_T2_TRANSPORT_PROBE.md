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
