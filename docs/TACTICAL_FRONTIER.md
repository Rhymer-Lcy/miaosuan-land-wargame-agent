# Tactical frontier

The project moves from infrastructure to tactics. Its primary objective is now a competitive, generalisable
land-wargame agent, a fast loop of tactical hypotheses tested locally, and a feedback loop with real platform play.
Engineering correctness stays mandatory and serves that objective; it no longer delays it.

Method, as in the project's other research: hypothesise boldly, preregister before confirmatory measurement, keep
exploration and confirmation apart, keep negative results, freeze experiment identities, never tune on confirmatory
results, and promote only evidence-backed improvements. A tactic is not turned into a multi-day infrastructure study
when a light mechanism check suffices. From Sprint 8 tactics are explored on the `EXPLORATORY` track (versioned run
cards, small batches, `docs/EXPLORATORY_TRACK.md`); any claim of improvement still goes through a registered
`CONFIRMATORY` study.

## Phase transition (2026-10-02, UTC+8)

* The ownership prevalence diagnostic (`docs/OWNERSHIP_PREVALENCE_DIAGNOSTIC.md`) stays as recorded: blocked by its
  own failed instrumentation check, prevalence withheld, its captures unexamined. It is not rerun now.
* The target-ownership line is **backlogged**, not deleted (`docs/TARGET_OWNERSHIP_DESIGN.md`).
* No historical result, record or registration is changed by this transition.

## Architecture

| Layer | Contents | Rule |
|---|---|---|
| Stable core | observation boundary and contract, legality gate, runtime identities, scheduler, ledger, reproducibility tooling, platform packaging | changes only to fix correctness, reproducibility or platform compatibility, or when a selected tactic is blocked by it |
| General doctrine | capability-driven tactics: what an operator can do, read from its observed fields and legal actions; terrain, objectives, enemy information | no scenario id, map id, unit id or fixed coordinate anywhere; unit-specific doctrine is encouraged ("general first does not mean unit-agnostic") |
| Competition profiles | optional scenario- or map-specific tactics (terrain, chokepoints, timing, force composition) | later stage; behind an explicit profile flag; never silently merged into the general doctrine |

## Research states

Every hypothesis is in exactly one state: `IDEA`, `MECHANISM-VALIDATED`, `EXPLORATORY`, `PREREGISTERED`, `CONFIRMED`,
`REJECTED`, `BLOCKED`. Exploratory findings are never reported as confirmed improvements; only `CONFIRMED` can lead to
a baseline promotion, through its own registered experiment.

The loop: local hypothesis, mechanism smoke, exploratory A/B; then platform AI test (package, upload, run, replay,
inspect compatibility and tactics); then confirmation (a fresh local A/B and external platform evidence); then
competition. Platform results are kept apart as environment-compatibility evidence, tactical result and
opponent-specific result; one human win confirms nothing, but real losses feed new hypotheses.

## Tactical capability census

From `evaluation/tactical-frontier-1/census.json` (`scripts/tactical_census.py`): the 50 historical scenarios of the
SDK 4.1.0 archive and the 8 frozen scenarios (operator archetypes by (type, sub_type) code), and every decision of the
pinned replay corpus (8 games of the frozen scenarios under C1, both seats: 16 deployment and 33,680 play decisions)
for what `valid_actions` lists on engine 4.1.0. Aggregates only.

| Family | Applicable capabilities | Generality | Opportunity | Risk | Leverage |
|---|---|---|---|---|---|
| T1 deployment disaggregation | every ground operator except artillery with 2 or more vehicles or squads: deployment split 314 (not listed in `valid_actions`, as documented), play split 14 | splittable operators in 50 of 50 scenarios; each starts with 3 or 4 | every frozen scenario side (16 of 16); split 14 listed in 1,693 play and 6 deployment decisions; 892 of 2,096 operators start stacked | 314 acceptance, control of the new operators and stacking limits unverified on 4.1.0 | per the live rules each half keeps the full ammunition and acts independently; stacked targets take adverse modifiers |
| T2 transport and infantry defence | infantry in 47 of 50 scenarios; vehicles with passenger capacity (infantry fighting vehicles 47 of 50) | high | embark listed in 77 and disembark in 256 play decisions | moderate: timing, suppression rules | infantry holds objectives and fires guided weapons; mobility via vehicles |
| T3 reconnaissance and enemy belief | every unit observes; UAV in 30, loitering munitions in 42, helicopters in 26 of 50 scenarios | high | an enemy is visible in 19,970 of 33,680 play decisions | low action risk; belief modelling effort | indirect: enables fire and movement decisions |
| T4 indirect artillery fire | artillery: 29 of 50 scenarios, 3 of 8 frozen | medium | indirect fire listed in 17,280 play decisions; artillery lists only change state, indirect fire and weapon lock, and baseline-v2 leaves it idle | target selection, dispersion, flight time, friendly fire unknown | high where artillery exists: an idle weapon system |
| T5 guided fire and correction | operators with guide ability; correction radar (sub_type 10, 5 of 50 scenarios) | low | guided fire listed once, correction radar in 2 play decisions | semantics barely observed | moderate where available |
| T6 threat-aware movement | every moving operator | high | move listed in 21,897 play decisions; an enemy visible in 59% of play decisions | changes the shared router | reduces losses en route; size unknown |
| T7 movement-state micro | change state (23,660 play decisions), stop (27,220), weapon lock (23,118) | high | most decisions of most operators | moderate: timing interactions | concealment and march trade survival against speed |
| T8 specialised assets | mines (sub_type 13, 7 of 50), fortifications (type 4, 2 to 4 of 50), altitude (helicopters), air defence | low | lay mine listed in 1 play decision; altitude in 6,957 | rare, scenario-dependent | local |
| T9 intent and task allocation | the whole force | high | every game | architectural change across all behaviour | potentially largest, hardest to isolate |

T1's open risks were then measured by its screen (`docs/SCREEN_DEPLOYMENT_SPLIT.md`): on engine 4.1.0 deployment
splits were accepted in 3 of the 8 frozen scenarios and refused with code 103 in the other 5; the new operators are
the seat's own and obey orders; the stacking limit voids a split silently.

## Engine facts (4.1.0) and how they were established

| Fact | Established by |
|---|---|
| Deployment split 314 is accepted per scenario (3 of 8 frozen), refused with code 103 elsewhere; no observation field tells the groups apart | Sprint 1 mechanism smoke, 8 captured games |
| The engine rewrites the action object in place during the step (314 becomes 14) | Sprint 1 smoke captures against the records |
| Split mode 4 = 2 + 2, 3 = 2 + 1, 2 = 1 + 1; products in the parent's hex under the lowest free ids; a carrier's passengers split with it; products are controllable | Sprint 1 smoke captures |
| A split into a hex already holding four own ground units is voided silently | Sprint 1 smoke; offline replay predicted 6 of 6 split rounds |
| While `cur_step` stands still the engine re-reports earlier feedback at every step | Sprint 1 smoke captures |
| A unit whose next hex holds four own ground units does not advance, keeps its move path and gets no error; two such groups block each other for the rest of the game | Sprint 2 diagnosis, two captured games with a snapshot every step (`docs/T1R_DIAGNOSIS.md`) |
| On the diagnosed route vehicles advance one hex per 20 steps, infantry one per 144 | Sprint 2 diagnosis |
| `speed` is 0 while a unit with a move path waits in front of a full hex and one hex per hex time while it traverses; `valid_actions` then lists only the stop action 10 | Sprint 3 design study, both Sprint 2 games at every step (`docs/PS1_DESIGN.md`, 11.2) |
| Hex time `(720 / basic_speed) * cost` predicts every unimpeded entry on the diagnosed route (138 of 138 and 235 of 235) | Sprint 3 design study |
| `can_to_move`, `stop`, `flag_force_stop` and `move_state` do not tell a blocked unit from a moving one | Sprint 3 design study |
| Restarting after a wait takes a full hex time, counting the restart step: prospectively supported in one game (113 of 113 final traversals exactly one hex time less one step) | Sprint 4 probe P2 (`docs/PS1_ENGINE_PROBE.md`); the Sprint 3 registered corpus check had not supported it (58 of 71) |
| A unit entering a hex in front of a full hex waits at once: prospectively supported in one game (103 of 103) | Sprint 4 probe P2 |
| Hypothesis, not fact: simultaneous movements are processed in ascending unit index with the occupancy updated after each move (the registered arbitration rule of P2 was refuted, 8 of 9, because it ignored leaving units; post hoc, the order-aware reading agrees with all 15 contention steps) | Sprint 4 probe P2 and its post-hoc descriptions |
| Hypothesis, not fact (post hoc): a unit ordered while its first hex holds four own ground units waits at once (M1d); it accounts for 79 of P2's 81 entries M1c predicted early | Sprint 4 post-hoc descriptions |
| A stop (action 10) issued to a unit waiting in front of a full hex is echoed without an error, sets `flag_force_stop` to 1, withdraws every listed action (another stop included) and leaves the move path; it does not take effect while the next hex stays full (4 units, 1,269 steps to the end of the game) | Sprint 4 probe P1, one game |
| Unknown: a stop on a unit that is still traversing; whether a stopped unit counts toward its hex's stacking limit; the transition length | no stop took effect in P1 |
| Change state (action 6) is listed only for units without a move path, stationary or in the move-to-stop transition; vehicles are offered concealment and half speed (half speed only while suppressed), infantry both charge levels and concealment; normal and march were never listed | Sprint 5 audit of the replay corpus and four captured games (`docs/T7_DESIGN.md`, 13.2) |
| Stop (action 10) is listed only for units with a move path; weapon lock (action 11) only for stationary, unfolded, unsuppressed vehicles; weapon unfold (action 12) never, since no unit ever locked | Sprint 5 audit |
| At the natural end of a path a ground unit serves 75 steps before `stop` is 1 (every settled arrival); movement is listed again at once; non-tank units list a shoot option only after those 75 steps | Sprint 5 audit |
| No frozen policy has ever issued a change-state, lock or unfold order, so no movement-state transition has been observed on engine 4.1.0; the documented unit field `target_state` is absent from every record | Sprint 5 audit of 1,284 game records and the observations |
| A concealment order (action 6, `target_state` 4) from an idle, stationary ground vehicle is echoed without an error, `change_state_remain_time` is positive in the next observation, and the unit is concealed (`move_state` 4, timer 0) exactly 75 steps after the order: 16 of 16 orders (tanks, infantry fighting vehicles, artillery) | Sprint 6 probe, three games (`docs/T7_MECHANISM_PROBE.md`) |
| A concealed unit keeps its listed actions (types 1, 6, 11 for tanks and infantry fighting vehicles; 6, 8, 11 for artillery), with change-state options {0, 5}; no lock; in a deterministic game nothing else changes (positions, flags, scores, `baseline-v2`'s actions) | Sprint 6 probe |
| A concealed artillery unit is not listed by opposing ground vehicles between half and the full documented distance (two games, one unit each); concealed vehicles with a helicopter between those distances were always listed (post hoc, outside the verdict) | Sprint 6 probe, P-B1 and P-B2 |
| Unknown: whether a concealed unit's later move or shot is accepted and ends concealment at once; what an order or a suppression does during the transition; concealed infantry; aerial observers | no such event in the three probe games |
| Artillery lists indirect fire as `{8: [{weapon_id: 72}]}` with no target; an order `{actor, obj_id, type 8, jm_pos, weapon_id}` was accepted at 15 to 65 hexes (367 of 367 orders); `weapon_cool_time` becomes 299 after an order and action 8 is not listed until it returns to 0; the ammunition counters stay 0 | Sprint 8 exploratory games, 11 games (`docs/SPRINT8_EXPLORATION.md`, section 4) |
| A round lands 150 steps after the order; the hex then explodes, usually for 300 steps; units in the hex are judged on landing and units entering it later on entry, own units included; observation by own ground units at landing gives correction (`align_status` 2) and most of the damage | Sprint 8 exploratory games |

## Selection rubric (committed before scoring)

`evaluation/tactical-frontier-1/rubric.json` fixes the criteria, their 0 to 5 anchors and the weights before any
family is scored: G generality 0.20, L leverage 0.25, O observability 0.15, I isolation 0.10, M measurability 0.10,
R risk (reversed) 0.10, P opportunity 0.10. The family with the highest weighted score is selected (ties by L, then
R); the sensitivity checks (equal weights, each weight plus or minus 0.05, each criterion left out, leverage 0.40)
are declared with it. The rubric prioritises research; it is not evidence that any tactic works.

## Scores and selection

`evaluation/tactical-frontier-1/scores.json` (each score with its reason) and `selection.json`
(`scripts/tactical_rubric.py`), scored after the rubric was public:

| Family | G | L | O | I | M | R | P | Weighted |
|---|---|---|---|---|---|---|---|---|
| T1 deployment disaggregation | 5 | 4 | 5 | 5 | 5 | 3 | 5 | **4.55** |
| T7 movement-state micro | 5 | 3 | 5 | 3 | 4 | 4 | 5 | 4.10 |
| T9 intent and task allocation | 5 | 5 | 4 | 1 | 2 | 3 | 5 | 3.95 |
| T2 transport and infantry defence | 4 | 3 | 5 | 3 | 3 | 4 | 3 | 3.60 |
| T4 indirect artillery fire | 3 | 4 | 4 | 5 | 4 | 3 | 2 | 3.60 |
| T6 threat-aware movement | 5 | 3 | 3 | 2 | 2 | 4 | 5 | 3.50 |
| T3 reconnaissance and belief | 4 | 3 | 3 | 2 | 2 | 4 | 4 | 3.20 |
| T8 specialised assets | 2 | 2 | 4 | 4 | 3 | 2 | 2 | 2.60 |
| T5 guided fire and correction | 1 | 3 | 4 | 4 | 3 | 2 | 1 | 2.55 |

**Selected: T1**, 0.45 ahead of T7. It stays first in all 23 declared weight variants (equal weights, each weight
plus or minus 0.05, each criterion left out, leverage 0.40); the runner-up is T7, or T9 when leverage, isolation,
measurability or observability is reweighted. Its two judgement scores are not decisive either: with L 3 and R 2,
T1 would score 4.20, still above T7. This is a research priority, not evidence that the tactic works.

## Hypothesis register

| Id | Hypothesis | State |
|---|---|---|
| TO-1 | target ownership by the highest attack level in isolated single-target collisions | `BLOCKED` (prevalence-1 stopped before interpretation); backlogged |
| T1 | deployment disaggregation: split eligible ground operators during deployment | `SHELVED` (2026-10-02): screen 1 REVISE BEFORE CONFIRMATION ([issue #1](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/1), `docs/SCREEN_DEPLOYMENT_SPLIT.md`); the diagnosed loss is a stacking-limit block that only a play-stage change removes (`docs/T1R_DIAGNOSIS.md`, `docs/T1R_SPEC.md`, gate G6 failed) |
| T1-r | T1 revised: probe once and stop on code 103, skip splits the stacking limit voids | specified, not implemented; the play-stage remedy it waited for (PS-1) is shelved |
| PS-1 | capacity-aware movement on `baseline-v2`'s play stage; selected form PS-1B, stalled-movement recovery: stop the deadlocked group that can back off, re-order it after the transition | `SHELVED` (2026-10-02): design study (Sprint 3, `docs/PS1_DESIGN.md`), then the registered engine probe ([issue #2](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/2), `docs/PS1_ENGINE_PROBE.md`): the stop on a waiting unit is deferred indefinitely (E1, E2 refuted, G2 FAIL) and the movement model failed its prospective fidelity test (G3 FAIL); disposition SHELVE |
| T7-C | concealment of idle stationary units: own ground units that `baseline-v2` leaves idle, stationary and unsuppressed while no enemy is seen are ordered into concealment (`docs/T7_DESIGN.md`, section 14) | `IDEA` (2026-10-03): the registered three-game mechanism probe ([issue #3](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/3), `docs/T7_MECHANISM_PROBE.md`) supports acceptance, the 75-step transition (16 of 16), retained listings, non-interference and the halved observation distance for ground observers; exit by a real move or shot is untested; disposition NEEDS_TARGETED_PROBE. The offline search for a natural E3b configuration (`docs/T7_E3B_SEARCH.md`, 2026-10-03) found no on-policy witness: E3B_CONFIGURATION_UNCERTAIN. Sprint 18's census found its benefit channel empty in the historical play (no damage to a concealable unit in the replay corpus; 4 events in the head-to-head captures, none by a ground attacker beyond half its observation distance); not selected |
| T4 | indirect artillery fire for the artillery `baseline-v2` leaves idle | `SHELVED` (2026-10-03): three exploratory versions in 11 games (`docs/SPRINT8_EXPLORATION.md`); every order executed, but version 2's damage came with friendly fire (own units entering exploding hexes near objectives) and version 3, which avoids it, sat at the control mean |
| T9 | capacity-limited objective allocation: at most 4 ground units committed per objective, the rest re-assigned or held | `SHELVED` (2026-10-06, owner decision): no deterministic, seat-local T9 revision found through Sprint 17 has simultaneously preserved or restored the primary redistribution mechanism and avoided the registered adverse mechanisms. This is not a rejection of Sprint 9's positive primary result, which stands as registered (+305.47, interval 172.87 to 611.24 in 2130511121); nothing was ever promoted, and no historical result file is changed. Sprint 18 re-selects the next tactical family offline. The state before shelving was `NEEDS_REVISION` (2026-10-04), recorded as follows. Sprint 9's registered result remains PRIMARY_SUPPORTED_NEEDS_REVISION (+305.47, interval 172.87 to 611.24 in 2130511121). Sprint 10's full-step diagnosis and T9-v2 same-route staging screen (`docs/SPRINT10_T9_DIAGNOSIS.md`, 14 sessions) repaired both 1930331196 firing regressions, but still missed the fifth 2120531121 objective, worsened its margin, and directionally lost most of the primary benefit; disposition PARTIAL_REPAIR_NOT_READY_FOR_CONFIRMATION, nothing promoted. Sprint 11's offline design (`docs/SPRINT11_BATCH_ALLOCATOR.md`, no engine session) ranks each objective's claimants together by free-flow arrival and gives no place to a unit that cannot arrive before the game ends; on the frozen captures it would seat the units T9-v1 held back from the missed objective; disposition READY_FOR_SMALL_EXPLORATORY_PROPOSAL. Sprint 12's registered screen of it (`docs/SPRINT12_V3_SCREEN.md`, 4 sessions) stopped after its first stage: all four primary games were T9-v2-like; disposition NOT_PRESERVED_IN_PRIMARY, nothing promoted. Sprint 13's offline diagnosis (`docs/SPRINT13_V3_DIAGNOSIS.md`, no engine session) found the lost cross-objective reallocation to be the main actionable difference (REDISTRIBUTION_DOMINANT). Sprint 14's offline design competition (`docs/SPRINT14_REDISTRIBUTION.md`, no engine session) replayed eight feasibility-gated redistribution rules on those games and the Sprint 10 adverse captures: the unconstrained rules restore most of T9-v1's opening redistribution, but every rule also redirects at the openings of both 1930331196 configurations; disposition NO_ENGINE_CANDIDATE. Sprint 15's offline study of delayed, memory-triggered redistribution (`docs/SPRINT15_DELAYED_REDISTRIBUTION.md`, no engine session) froze six stateful rules and an evidence-adequacy rule before its replay: no rule passed the restoration items (disposition NO_RESTORING_TRIGGER), every adverse configuration stayed untested for every rule, and two design defects found afterwards are disclosed with a post-hoc sensitivity analysis. Sprint 16's registered mechanism capture (`docs/SPRINT16_MECHANISM_CAPTURE.md`, 3 sessions) played the frozen v3 in the three adverse configurations and evaluated the delayed rules as analysis-side shadows up to their first divergence: the post-staging trigger never acts in 1930331196 C3 and first diverges inside the risk window in C2 and 2120531121 C3 without recreating a diagnosed mechanism (disposition MECHANISM_AMBIGUOUS). Sprint 17's registered probe (`docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md`, 2 sessions) played an executable form of the post-staging rule (`t9-delayed-post-stage-any-v6`) across both divergences: in 1930331196 C2 the protected fire at decisions 611 and 686 survived and the capture order was unchanged, but in 2120531121 C3 the early redirected vehicles held every counted place of the problem objective while 45 later claimant-decisions were blocked behind them (45 EARLY-PLACE BLOCK events; disposition MECHANISM_REFUTED_212); the rule is retired, nothing was promoted, and shelving the line is recommended to the owner. The owner shelved the line on 2026-10-06 (state above) |
| T6 | threat-aware movement; first increment T6-G, the threat-entry gate: withhold a `baseline-v2` move that would carry a ground unit from outside every visible enemy's published direct-fire envelope into one, for at most 150 steps per episode | `IDEA` (2026-10-07): selected by Sprint 18's frozen rubric (`docs/SPRINT18_FRONTIER_RESET.md`, W 4.35, first in 24 of 25 variants). Timing branch CLOSED (2026-10-07): Sprint 19's offline shadow (`docs/SPRINT19_T6G_SHADOW.md`, no engine session) reproduced every Sprint 18 figure and found no move that enters a visible enemy's envelope from outside (0 gate episodes in every HH and H0 side-game; all 200 HH and 230 H0 threat-exposed orders started inside an envelope); disposition T6_G_OFFLINE_INADEQUATE_OPPORTUNITY; no probe drafted. Movement inside envelopes, route choice and formation stay open and need a frontier decision |
| T2 | transport and infantry defence: carry infantry on a co-located infantry fighting vehicle to its objective and dismount it there | `IDEA` (2026-10-08): the owner moved to T2 after Sprint 21. First increment T2-P1, the registered one-session transport mechanism probe (`docs/SPRINT22_T2_TRANSPORT_PROBE.md`, session 2796, 1930331196 C3 against the inert control, one infantry-carrier pair chosen by a witness rule frozen before the search): embark accepted and aboard after exactly 75 steps, the loaded carrier at its free-flow time to the 80-point objective A, disembark listed after the 75-step stop transition and the infantry on the objective 75 steps after the order (its foot route takes 3,456 steps against a 2,880-step game); no reconstruction or registered-difference finding; disposition T2_P1_MECHANISM_SUPPORTED. The carrier had to be held on the destination (owner's clarification) because `baseline-v2` re-orders a vehicle that ends a move on a held objective. Mechanism only: no score claim, nothing promoted. Sprint 23's offline design (`docs/SPRINT23_T2_POLICY_DESIGN.md`, no engine session) specified the smallest multi-pair generalisation T2-X1 (proposed, non-executable: same-objective trigger, deterministic matching, admission under the stacking limit, bounded holds and recovery) and measured it on H0, HH and HI: 30 valid first-divergence episodes in 6 scenarios, all at the opening and none later, no saturated destination, but in 25 of 30 the held carrier is one `baseline-v2` sends straight on to an objective its side does not hold; disposition T2_UNRESOLVED_INTERACTION_RISK, no screen proposed |
| T3, T5, T8 | the other families above (T7's march, charge, stop and lock mechanisms: not selected, `docs/T7_DESIGN.md` 13.5) | `IDEA`; scored on their next increments in Sprint 18 and not selected (T5 not eligible) |
| T10 | suppression relief: remove suppression (action 7) for suppressed own infantry | `IDEA` (2026-10-07): admitted by Sprint 18's scan; listed only while suppressed, never issued, effect undocumented |
| T11 | direct-fire target priority: prefer the listed target most likely to be destroyed | `IDEA` (2026-10-07): admitted by Sprint 18's scan; Sprint 18's runner-up. First increment T11-O1, the kill-first rule (lowest observed blood, then `baseline-v2`'s rank), replayed offline by Sprint 20 (`docs/SPRINT20_T11_REPLAY.md`, no engine session): the public rules do not support a defensible immediate-kill probability (how a result and its correction combine, and whether a listed attack level includes the elevation correction, are undocumented); disposition T11_OFFLINE_MODEL_UNAVAILABLE; no probe drafted. Descriptively the rule changes only targets (0 non-shoot differences) and has 15, 33, 19 and 27 changed shots in the four HH side-games. Its endpoint needs the adjudication semantics settled first. Sprint 21's offline audit of the existing direct-fire judge records (`docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md`, no engine session; 18 games, 975 paired shots) found the listed attack level equal to the adjudicated one in every paired shot, but no permitted evidence states the probability law of the result-table draw; disposition DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED. T11-O1 is CLOSED as blocked by an unidentifiable registered endpoint; nothing was promoted |
| T12 | objective-zone dispersion: spread stacked holders of a held objective over adjacent hexes | `IDEA` (2026-10-07): admitted by Sprint 18's scan; inherits T9's withholding interaction |

## Roadmap

1. **Done (Sprint 2)**: the deterministic loss of screen 1 (as blue against the inert control in 1910631192 the
   candidate scores 78 where `baseline-v2` scores 158) was diagnosed with two captured games: a stacking-limit block
   at the first objective, never resolved because an issued move is never changed. T1 is shelved; T1-r is specified
   but not implemented.
2. **Done (Sprint 3)**: the offline design study of PS-1 (`docs/PS1_DESIGN.md`). The block is observable from seat
   fields; under the movement model a stalled-movement recovery releases it, but that model failed its registered
   fidelity check and the recovery relies on an untested stop, so the disposition is NEEDS_ENGINE_PROBE. The same
   deadlock also occurs in ordinary `baseline-v0` replay play.
3. **Done (Sprint 4)**: the PS-1 engine probe, two registered sessions (`docs/PS1_ENGINE_PROBE.md`). A stop issued
   to a waiting unit is registered but deferred while the next hex stays full, so stop-based recovery cannot release a
   formed deadlock; the post-hoc movement model predicted every hex of a fresh game but not every timing. PS-1 is
   SHELVED. The deadlock remains an open problem of `baseline-v2`'s play stage (it also occurs in `baseline-v0` corpus
   play); a future remedy would have to prevent the column forming, not recover from it.
4. **Done (Sprint 5)**: the offline design study of T7 movement-state micro (`docs/T7_DESIGN.md`), no engine
   session. The listings are frequent but nothing in T7 has ever been executed; march was never offered, and both stop
   tactics fail on Sprint 4's frozen-unit fact. One mechanism survives: concealment of idle stationary units, selected
   in all 28 rubric variants, with an offline shadow that leaves `baseline-v2` unchanged. Disposition
   READY_FOR_MECHANISM_PROBE; the three-game probe (`docs/T7_SCREEN_PROPOSAL.md`) awaits the owner's approval.
5. **Done (Sprint 6)**: the registered T7 mechanism probe, three sessions (`docs/T7_MECHANISM_PROBE.md`). Every
   concealment order was accepted and completed in exactly 75 steps; concealed units kept their listings, nothing else
   changed in the deterministic game, and a concealed unit was not seen by ground observers beyond half the distance.
   No game produced a concealed unit that `baseline-v2` later moved or fired, so exit from concealment (E3b) is
   untested; disposition NEEDS_TARGETED_PROBE. No tactical A/B is proposed until that behaviour is observed.
6. **Done (Sprint 7)**: the offline search for a natural E3b configuration (`docs/T7_E3B_SEARCH.md`), no engine
   session. In the three genuine full-step `baseline-v2` seats the candidate would order 16 units that `baseline-v2`
   never commands again, and none of its 198 moves and shots follows 75 idle steps; the only witnesses are off-policy
   (one tank in an H0 game, stochastic before the trigger). Disposition E3B_CONFIGURATION_UNCERTAIN; no probe is
   proposed. A deterministic test of the exit mechanism would need a separate, owner-approved diagnostic command.
7. **Done (Sprint 8)**: the exploratory track and the first exploratory batches (`docs/SPRINT8_EXPLORATION.md`), 23
   engine sessions. T4 indirect fire works mechanically but its versions either damaged own units or gained nothing;
   shelved. T9 capacity-limited allocation was above the historical `baseline-v2` control in 10 of 12 games and in all
   6 head-to-head games of the largest scenario.
8. **Done (Sprint 9)**: the registered, staged confirmatory study of T9 (`docs/T9_CONFIRMATION.md`), 285 engine
   sessions. The primary head-to-head improvement in 2130511121 was supported, and the small-scenario safety screen
   showed identical margins. Against the inert control in the large scenarios the candidate gained as red in two
   scenarios but lost as blue in two beyond the registered threshold (one objective missed under long withholding,
   less fire on the inert side), so the study stopped before its head-to-head phase in the other scenarios.
   Disposition PRIMARY_SUPPORTED_NEEDS_REVISION; nothing promoted.
9. **Done (Sprint 10)**: six full-step diagnostics tied all three adverse configurations to emission-order capacity
   reservations and cross-objective route changes. T9-v2 retained baseline routes and staged overflow units; eight
   exploratory games restored both 1930331196 firing configurations but still missed the 2120531121 fifth objective
   and directionally eroded the primary benefit (`docs/SPRINT10_T9_DIAGNOSIS.md`). Disposition
   PARTIAL_REPAIR_NOT_READY_FOR_CONFIRMATION; no promotion or confirmation proposal.
10. **Done (Sprint 11)**: an offline design of a batch capacity allocator (`docs/SPRINT11_BATCH_ALLOCATOR.md`), no
    engine session. No established operation can re-order a unit already moving, so the allocator never displaces one;
    it ranks each objective's claimants together by free-flow arrival, counts no reservation that cannot be honoured
    before the game ends, and stages the rest on their own route. Replayed on the frozen Sprint 10 captures it would
    have seated the units T9-v1 held back from the missed 2120531121 objective and made no cross-objective move.
    Disposition READY_FOR_SMALL_EXPLORATORY_PROPOSAL; whether it keeps any of the primary benefit, which T9-v1 obtained
    with redistribution, is unknown offline.
11. **Next**: a small exploratory proposal for the batch allocator, written for the owner's approval before any
    engine session. Drafted on 2026-10-05 (`docs/SPRINT12_BATCH_ALLOCATOR_PROPOSAL_DRAFT.md`): at most 12 sessions,
    the primary scenario first; unapproved and unregistered, so it authorizes no engine session. Approved by the owner
    for registration only and registered the same day (`docs/SPRINT12_V3_SCREEN.md`): every stage rule, observer and
    classification frozen and pinned in the stage cards, only the P1 card built; no engine session, ledger still
    closed through 2786; execution awaits the owner's review.
12. **Done (Sprint 12)**: the registered screen of the batch allocator ran its first stage (sessions 2787 to 2790,
    four head-to-head games in 2130511121). All four games were T9-v2-like (red coverage 0.5691 and 0.2885, below
    T9-v1's lowest; blue margins 481 and 585, below T9-v1's lowest), so the frozen interim rule stopped the screen; P2,
    A1 and A2 were not run. Disposition NOT_PRESERVED_IN_PRIMARY: v3 is not pursued in this form; nothing promoted.
13. **Done (Sprint 13)**: an offline diagnosis of that result from the four games' full-step captures
    (`docs/SPRINT13_V3_DIAGNOSIS.md`), no engine session. On v3's own states T9-v1 would have redirected 0.3061 to
    0.7910 of its emitted ground moves (0.4107 to 0.8444 in Sprint 9's real T9-v1 seats; redistribution material in all
    four games), while reservations held by units destroyed en route mattered in two games and no seat-local feature
    predicted them. Disposition
    REDISTRIBUTION_DOMINANT; the next step is an offline design study of a feasibility-gated cross-objective allocator
    replayed on these games and on the Sprint 10 adverse captures.
14. **Done (Sprint 14)**: that offline design study (`docs/SPRINT14_REDISTRIBUTION.md`), no engine session. Eight
    deterministic, seat-local rules (O2 stated as a policy, horizon and corridor bounds, a batch assignment, a cost
    ranking) were frozen with their gate before any replay. The unconstrained rules recover 12 of T9-v1's 14 (red) and
    17 or 18 of its 19 (blue) first-decision redirects (the minimal rule cuts v3's slot divergence from T9-v1 to
    0.4036 of it), but every rule also redirects at the opening of both 1930331196 configurations, in C3 two units
    that later fired; no bound tried separates the two openings. Disposition NO_ENGINE_CANDIDATE; session 2791 was not opened. Next: an offline test
    of whether the primary redistribution needs its opening redirects (a persistence-triggered variant).
15. **Done (Sprint 15)**: that offline study (`docs/SPRINT15_DELAYED_REDISTRIBUTION.md`), no engine session. Six
    deterministic, seat-local rules with memory (repeat, stable-alternative, post-staging and saturated-source triggers)
    were frozen with a gate and an evidence-adequacy rule before the replay. None redirects at the opening; persistence
    triggers restore at most 2 of the 15 units T9-v1 redirects after the opening as red, the post-staging trigger 9,
    and no existing adverse capture can exercise a staging-based trigger. Disposition NO_RESTORING_TRIGGER; two design
    defects (a memory reset on held objectives, a restoration measure that recorded states bias against bounded
    recourse) are disclosed with a post-hoc analysis that changes no disposition: corrected, the persistence triggers
    become testable and stay safe but still restore at most 3 red units, and the post-staging trigger stays untestable.
    Session 2791 was not opened.
    Next: an owner decision on a registered three-session mechanism capture of the frozen v3 in the three adverse
    configurations, not a score screen.
16. **Done (Sprint 16)**: that capture (`docs/SPRINT16_MECHANISM_CAPTURE.md`), sessions 2791 to 2793, frozen v3 against
    the inert control, every decision reconstructed without a difference. The delayed rules were evaluated only as
    analysis-side shadows (`s16-delayed-shadow-v6`, Sprint 15's memory correction) up to their first divergence from
    v3. The post-staging trigger never acts in 1930331196 C3 and first diverges inside the risk window in C2 (decision
    421) and 2120531121 C3 (decision 361), on units with no firing role and without a bad reservation: disposition
    MECHANISM_AMBIGUOUS. Nothing was promoted.
    Next: an owner decision on designing the smallest probe that crosses those two first divergences.
17. **Done (Sprint 17)**: that probe (`docs/SPRINT17_FIRST_DIVERGENCE_PROBE.md`), sessions 2794 and 2795, the executable
    candidate `t9-delayed-post-stage-any-v6` against the inert control, every decision and its memory reconstructed
    without a difference and both registered first divergences reproduced exactly. In 1930331196 C2 the protected direct
    fire at decisions 611 and 686 was listed, ordered and accepted and the capture order was unchanged; in 2120531121 C3
    the problem objective was first owned at decision 522, before v3's 564, but the four redirected vehicles held all
    its counted places from the first later claim to the capture and 45 claimant-decisions, v3's own two capturers
    among them, were blocked behind the two decision-361 places: disposition MECHANISM_REFUTED_212. The rule is
    retired; nothing was promoted.
    Next: an owner decision on shelving the T9 line and on an offline re-selection of the next tactical family.
    **Owner decision (2026-10-06)**: T9 is SHELVED (hypothesis register above); Sprint 18 is an offline re-selection of
    the next tactical family, with no engine session.
18. **Done (Sprint 18)**: the offline frontier reset (`docs/SPRINT18_FRONTIER_RESET.md`), no engine session. A
    supplemental census of all usable historical captures (the replay corpus, Sprint 12's head-to-head timelines, the
    Sprint 16 and 17 timelines, 1,618 records) reproduced every published consistency figure and showed where
    `baseline-v2` loses: moving ground units take most of the damage, almost always from attackers already in view, and
    the force lost against acting opponents is a median 0.81 to 0.85 of its value. Three new families were admitted
    (T10, T11, T12), every candidate was scored on one concrete next increment under a rubric registered before scoring,
    and the outcome is NEXT_FAMILY_SELECTED: T6, first experiment T6-G (threat-entry gate), robust in 24 of 25 variants.
    Next: the T6-G offline shadow study, then a two-session probe for the owner's approval.
19. **Done (Sprint 19)**: the T6-G offline shadow study (`docs/SPRINT19_T6G_SHADOW.md`), no engine session. The gate,
    its hold state machine and every threshold were frozen and pushed before the replay; the replay reproduced every
    Sprint 18 figure and found that the gate never fires: every threat-exposed `baseline-v2` move in the replay corpus
    and the head-to-head captures started inside a visible enemy's envelope, none entered one from outside.
    Disposition T6_G_OFFLINE_INADEQUATE_OPPORTUNITY; the timing branch of T6 is closed, nothing was promoted.
    Next: T11's registered offline step (the kill-first target rule replayed on the same populations), for the owner's
    approval.
20. **Done (Sprint 20)**: the T11-O1 offline replay (`docs/SPRINT20_T11_REPLAY.md`), no engine session. The kill-first
    rule, its same-step reservation semantics and every threshold were frozen and pushed before the replay; a reading of
    the public rules found the immediate-kill probability undefined without unsupported assumptions, so the disposition
    is T11_OFFLINE_MODEL_UNAVAILABLE and nothing was promoted. The replay reproduced every Sprint 18 anchor; the rule
    changes only shot targets, mostly to lower attack levels on targets of blood 1, often fortifications or aircraft.
    Next: an offline audit of the direct-fire adjudication semantics in the existing judge records, for the owner's
    approval; otherwise T2.
21. **Done (Sprint 21)**: the offline direct-fire adjudication-semantics audit (`docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md`),
    no engine session. The corpus rule, pairing, the K2 to K6 rules and the sufficiency rule were frozen and pushed
    before the audit; on 18 full-step games the listed attack level equals the adjudicated one in all 975 paired
    shots and the ground result tables reproduce every numeric cell, but the probability law of the draw is stated
    nowhere the project may use, so the disposition is DIRECT_FIRE_SEMANTICS_UNDERIDENTIFIED and T11-O1 is closed;
    nothing was promoted. Next: T2, transport and infantry defence, for the owner's approval.
22. **Done (Sprint 22)**: the T2-P1 transport mechanism probe (`docs/SPRINT22_T2_TRANSPORT_PROBE.md`), one engine
    session (2796). The semantics audit, the witness-selection rule and the candidate were frozen and pushed before the
    search and the session; the complete chain embark, carry, disembark ran for the registered pair with the documented
    75-step transitions and no fidelity finding, so the disposition is T2_P1_MECHANISM_SUPPORTED; nothing was promoted.
    Next: an offline design of the smallest T2 exploratory policy and screen, for the owner's approval; no engine use.
23. **Done (Sprint 23)**: the offline T2 policy design (`docs/SPRINT23_T2_POLICY_DESIGN.md`), no engine session. The
    proposed multi-pair candidate, its readiness rule and the opportunity study's inputs were frozen and pushed before
    the study; the trigger fires only at the opening, and the carrier hold that disembark needs competes with
    `baseline-v2`'s onward routing in 25 of 30 episodes, so the disposition is T2_UNRESOLVED_INTERACTION_RISK; no screen
    was proposed and nothing was promoted. Next: an offline frontier re-selection for the owner; no engine use.

A tactic that earns ADVANCE gets a confirmatory design sized from its screen's noise; one that does not is recorded
with its disposition and left. Platform evidence runs alongside: the canary first, then each candidate that a local
screen supports.

## Process deviations

| Date (UTC+8) | Where | What happened | Consequence |
|---|---|---|---|
| 2026-10-03 | T7 mechanism probe | the proposal and the sprint brief said the shadow's first orders were at decision 717 to 4 units; the replay gives 2 units at 717 and 2 at 736 | corrected by a dated note in the proposal before registration; the registration names both decisions, and the probe game matched them |
| 2026-10-02 | PS-1 engine probe | the registration commit's protocol document used two phrases the documentation policy reserves for the retired engine installation, so the full suite at that commit fails two policy subtests (the probe's own suites passed; the document was untracked when the full suite last ran) | reworded after the games; the registered rules, in the manifest and the issue, are unchanged |
| 2026-10-02 | PS-1 engine probe | the registered arbitration (T-d) and re-wait (T-c) rules judged contenders by the lowest indices and end-of-step occupancy, ignoring units leaving the hex in the same step; they refuted claims that an order-aware reading of the same events supports | the registered REFUTED verdicts stand; the order-aware reading is reported as post hoc only (`docs/PS1_ENGINE_PROBE.md`, section 16) |
| 2026-10-02 | PS-1 design study | the registered movement model failed its fidelity check on the split game; amendment 1 replaced it before any counterfactual was computed, and the replacement then failed fidelity and its independent check too | G3 fails as registered; a third, post-hoc model is reported only as a hypothesis for the probe (`docs/PS1_DESIGN.md`) |
| 2026-10-02 | PS-1 design study | the certificates' assumption lists named the registered model although they ran under amendment 1's | relabelled before publication; the regenerated summary differed from the earlier one only in those labels |
| 2026-10-02 | screen 1 smoke analysis | the first run read zero splits because the engine rewrites a deployment split's type from 314 to 14 in place before the capture serialises it; the records contradicted it | fixed, tested and pushed before the A/B; the analysis now refuses to run when capture and record disagree; the registered rule and the verdict on these data are unchanged (`docs/SCREEN_DEPLOYMENT_SPLIT.md`) |

## Platform canary and feedback loop

* `scripts/build_platform_package.py` builds `dist/<name>.zip`: one top-level `ai` package, the frozen policy's
  modules vendored byte for byte (standard library only), a generated `Agent`, a deterministic stored archive, a
  forbidden-content scan, and an isolated-interpreter smoke against the repository agent. The archive is never
  committed.
* Canary status: **READY FOR PLATFORM CANARY**. `miaosuan-baseline-v2-canary.zip`, 107,646 bytes, SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, byte-identical when built on the workstation and
  on the server; the packaged agent's actions equal the repository agent's on synthetic games and on all 33,696 steps
  of the 8-game replay corpus under CPython 3.10.20 with NumPy 1.26.2. The upload is a manual step on the platform;
  nothing is uploaded from this repository.
* For each meaningful platform loss, a failure ledger entry: deployment, reconnaissance, movement, fire allocation,
  indirect fire, transport, objective timing, survival, special equipment, or unknown. Repeated patterns become
  preregistered hypotheses; nothing is patched silently after a loss.

| Date | Platform game | Opponent | Result | Category | Observation | Hypothesis |
|---|---|---|---|---|---|---|
| (none yet) | | | | | | |

## BOKE-2026 holdout

The Fifth Miaosuan Cup scenario (user-supplied: "城镇居民26-波克 / 波克的阵线") is not in the local SDK data: the
archive's nested `Data.zip` holds 50 scenarios and 16 map folders, none named `map_26`, and no file mentions the
scenario (checked 2026-10-02 against the archive whose digest the local checksum list pins, entry names and file
contents in UTF-8, GBK and UTF-16; a name search of the development workstation found no competition asset either).
When its assets become available: audit compatibility; do not tune; first run the frozen generalist agent and record
its external performance; only then begin profile-specific work, behind a competition profile.

## Not now

No reinforcement learning, deep learning or online LLM policy: the accelerated online clock and the unknown online
runtime make a deterministic hierarchical doctrine the near-term target. Learned models may come later for enemy
motion, value estimation or opponent modelling, once strong behavioural baselines and replay data exist.
