# Tactical frontier

The project moves from infrastructure to tactics. Its primary objective is now a competitive, generalisable
land-wargame agent, a fast loop of tactical hypotheses tested locally, and a feedback loop with real platform play.
Engineering correctness stays mandatory and serves that objective; it no longer delays it.

Method, as in the project's other research: hypothesise boldly, preregister before confirmatory measurement, keep
exploration and confirmation apart, keep negative results, freeze experiment identities, never tune on confirmatory
results, and promote only evidence-backed improvements. A tactic is not turned into a multi-day infrastructure study
when a light mechanism check suffices.

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
| T7-C | concealment of idle stationary units: own ground units that `baseline-v2` leaves idle, stationary and unsuppressed while no enemy is seen are ordered into concealment (`docs/T7_DESIGN.md`, section 14) | `IDEA` (2026-10-03): the registered three-game mechanism probe ([issue #3](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/3), `docs/T7_MECHANISM_PROBE.md`) supports acceptance, the 75-step transition (16 of 16), retained listings, non-interference and the halved observation distance for ground observers; exit by a real move or shot is untested; disposition NEEDS_TARGETED_PROBE |
| T2 to T9 | the other families above (T7's march, charge, stop and lock mechanisms: not selected, `docs/T7_DESIGN.md` 13.5) | `IDEA` |

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
6. **T9 intent and task allocation**, the largest lever and the hardest to isolate; T4 (the idle artillery) follows
   by the rubric.

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
