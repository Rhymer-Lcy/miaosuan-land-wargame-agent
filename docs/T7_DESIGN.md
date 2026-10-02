# T7 movement-state micro: design study

**DESIGN STUDY.** No engine session, no production policy, no registration, no promotion, nothing uploaded. This
document is the protocol and the record of Sprint 5, an offline study of the T7 family of `docs/TACTICAL_FRONTIER.md`:
changing movement state (action 6), stopping (action 10) and locking or unfolding weapons (actions 11 and 12). Its goal
is at most one narrow, falsifiable T7 mechanism that a future registered probe could test against `baseline-v2`.
Sections 1 to 12 were written and pushed before any new action-level aggregate or candidate result was computed;
section 13 onwards is written afterwards and says so. An offline protocol committed before analysis is not an
engine-study preregistration, and no registration issue is created for it. Times are UTC+8.

## 1. Questions

1. **T7-A, change state.** Which target states does the engine list for which unit classes and in which situations,
   what does each transition cost and change, and how is its completion observed?
2. **T7-B, stop.** In which situations, other than the stop on a unit waiting in front of a full hex that Sprint 4
   showed to be deferred indefinitely, is a stop listed, and what can the records say about its effect?
3. **T7-C, weapon lock and unfold.** Which units can lock and unfold, under which conditions, with what effect on
   firing, and how does it relate to the march state?
4. How often do these actions have an executable opportunity in the historical records, in how many distinct
   situations, and what did the frozen baselines do instead?
5. Which single T7 mechanism, if any, is general, seat-observable, isolable, safe and measurable enough to deserve a
   bounded engine probe, and what is the smallest probe that would resolve its open engine behaviour?

## 2. Evidence already seen (disclosure)

Before this protocol was written, the following had been read. None of it is a new action-level aggregate or a
candidate result.

* The public census `evaluation/tactical-frontier-1/census.json` (Sprint 1): play decisions listing change state
  23,660, stop 27,220, weapon lock 23,118 of 33,680; deployment decisions listing change state and weapon lock 16 of
  16; weapon unfold never listed; per-archetype unit listings of actions 6, 10 and 11, in which artillery holds most
  change-state and weapon-lock listings. These counts describe listings, not executed actions.
* `docs/BASELINE_V2.md` and the decision code: `baseline-v2` never changes movement state, never stops and never locks
  or unfolds weapons; it orders a unit only when its move path is empty.
* Sprint 4's engine facts (`docs/PS1_ENGINE_PROBE.md`): a stop issued to a unit waiting in front of a full hex is
  echoed without error, sets `flag_force_stop` to 1, withdraws every listed action and is deferred while the next hex
  stays full (four units, one game). A stop on a traversing unit has never been issued in this project.
* Sprint 3's observation audit of the two Sprint 2 games (`docs/PS1_DESIGN.md`, 11.2): in those games `stop` was 0 on
  every blocked and moving unit-step and `flag_force_stop` and `move_state` were 0 everywhere; `valid_actions` listed
  action 10 alone for blocked units.
* The platform's published rules, action and observation references and tutorial (snapshot of 2026-09-29, private
  under `local/source-archives/`), the SDK 4.1.0 action and observation notes and its demo agent (not
  redistributed). Section 3 summarises what they document.
* Metadata of the private datasets (file lists, players, policies, step and snapshot counts, record schemas), used for
  section 4. No observation content of these datasets was read for this sprint.

## 3. The documented contract

Paraphrased from the sources in section 2. Each item is DOCUMENTED, not observed, until section 13 says otherwise.

| Id | Documented rule |
|---|---|
| D1 | Action 6 takes `target_state`: 0 normal, 1 march, 2 first-level charge, 3 second-level charge, 4 concealment, 5 half speed (the observation note lists 0 to 4 for the option and for `move_state`). States are mutually exclusive. |
| D2 | March: vehicles only, entered on a road hex, after the weapons are locked; entering and leaving march each take 75 s; while marching the unit cannot fire, guide fire, embark, disembark or leave the road; march speed is 40, 60 or 90 km/h on the three road classes (normal vehicle speed 36 km/h); a marching unit is blocked by a stopped or non-marching unit in its next hex; a marching target suffers the largest adverse modifier in the direct- and indirect-fire tables. |
| D3 | Charge: infantry only; first level doubles and second level quadruples speed, each charged hex adds one fatigue level; second-level charge is not allowed at fatigue 1 and no movement at fatigue 2; fatigue falls one level per 75 s after movement ends; the charge state persists until changed back. No transition time is documented. |
| D4 | Concealment: entering takes 75 s during which the unit executes no other command (a tank firing interrupts it); suppression prevents it or interrupts it; once concealed, moving or firing ends it at no time cost; a concealed unit is observed at half distance (not for a vehicle lower than its observer); concealment is a favourable target modifier in the direct- and indirect-fire tables. |
| D5 | Half speed: used to cross minefields and open lanes; no other effect documented. |
| D6 | Stop (action 10): the unit completes its current hex, then serves a 75 s move-to-stop transition during which it takes no action; the unexecuted remainder of the move is dropped. Every ground unit stopping after movement serves a 75 s move-to-stop transition; during it the unit may change movement state; firing (except tank main guns), lock, unfold, embarking and other stationary actions wait for its end. `can_to_move` tells a normal stop (movement may resume) from a forced stop (it may not). |
| D7 | Weapon lock (11) and unfold (12): every vehicle starts unfolded; locking is required before march; unfolding takes 75 s and is needed after march before firing; neither can run with another command; the lock state is one field per unit (`weapon_unfold_state`, `weapon_unfold_time`). |
| D8 | Direct fire requires an observed target in range, an unfolded and cooled weapon, and a stopped shooter (tank main guns may fire while moving); a moving shooter suffers an adverse modifier. |
| D9 | Setup data available to a seat: the scenario, the map's basic data (with road classes per hex), the cost graph per mode (0 vehicle, 1 vehicle march, 2 infantry, 3 air; cost = the mode's maximum speed divided by the current speed) and the line-of-sight table. No weapon table is supplied; the weapon id to name mapping and the range tables are published. |
| D10 | One engine step is one second; vehicles at 36 km/h take 20 steps per open hex, infantry at 5 km/h 144 steps (published standard speeds; Sprint 2 observed both). |

## 4. Datasets and populations

Inventory (metadata only; all private, on the evaluation server):

| Id | Dataset | Policies (red / blue) | Scenarios | Seats with observations | Frequency | Use |
|---|---|---|---|---|---|---|
| H0 | replay corpus, pinned by the routing remediation (`evaluation/routing-remediation-1/corpus.json`) | `baseline-v0` / `baseline-v0`, condition C1 | the 8 frozen scenarios, one game each | both | every decision | primary population; the only one with two active sides |
| H1 | Sprint 2 game `b` (`local/evaluation/t1r-diagnosis-1/`) | inert / `baseline-v2` | 1910631192, C3 | blue seat and all-seeing | every step | `baseline-v2` population; two-channel cross-checks |
| H2 | Sprint 2 game `c` and Sprint 4 game P2 (`local/evaluation/ps1-engine-probe-1/`) | inert / split candidate; split candidate / inert | 1910631192 C3; 1930331196 C2 | candidate seat and all-seeing | every step | split-candidate population (its play stage is `baseline-v2`'s) |
| H2r | Sprint 4 game P1 before its first stop (decisions before `k` 533) | inert / probe hook (the split candidate until the trigger) | 1910631192 C3 | hook seat and all-seeing | every step | reproduction channel only: its pre-trigger states equal game `c`'s; never counted twice |
| R | game records of the registered experiments | as registered | as registered | none (aggregates) | per game | issued-action counts by type, an independent record of what the policies emitted |

Exclusions, fixed now: the captures of `baseline-v2-target-ownership-prevalence-1` (unexamined by that study's own
rule); every P1 decision from its first stop onwards (the diagnostic intervention); the sparse snapshots of the Sprint 1
screen smoke and of the residual-516 diagnostic (one snapshot every 200 steps plus event windows: they cannot
establish transitions or durations, and the full-step games of the same policies supersede them); the BOKE-2026
holdout (not available locally). Populations are never pooled across policies: H0 (`baseline-v0`), H1 (`baseline-v2`)
and H2 (split candidate) are reported separately; H0 is the only population with an opponent that moves and fires.

## 5. Evidence levels and missing data

Every claim in the semantics matrix and the audit carries exactly one level and its scope (population, count):

| Level | Meaning |
|---|---|
| DOCUMENTED | stated by the published rules or SDK notes (section 3); not checked against the engine |
| DIRECTLY OBSERVED | present in a seat or all-seeing observation, or in a record, of engine 4.1.0 in the named population |
| DERIVED | follows by stated arithmetic from documented rules and observed fields or setup data |
| HYPOTHESIZED | an expected engine behaviour no record shows; a probe endpoint if a candidate needs it |
| CONTRADICTED | a documented or hypothesised statement that a record contradicts (with the count) |
| UNKNOWN | neither documented nor observable in the available records |

Missing data: a field absent from a unit record, or holding `None`, is counted as missing for that unit-decision and
never imputed. A transition is measured only between consecutive steps (H1, H2) or consecutive decisions of one seat
whose `cur_step` differs by one (H0); a gap makes the episode ambiguous and excludes it from duration measures. An
episode running at the last observation is censored and reported as such. Malformed options (a change-state option
without an integer `target_state`) are counted and excluded, never repaired.

## 6. WP1: action-semantics audit (method)

For each family, every question of the sprint plan is answered with a level from section 5. The observation
evidence is read from H0 (seat views of both sides), H1 and H2 (seat and all-seeing views); records R give issued
actions.

* **T7-A.** Per unit archetype (type, sub_type) and situation (`move_state`, `stop`, move path empty or not,
  `change_state_remain_time` zero or positive, suppressed, on board), the sets of `target_state` options listed; the
  observed values of `move_state`, `target_state`, `change_state_remain_time`, `tire` and `tire_accumulate_time`; every
  observed change of `move_state` or positive `change_state_remain_time` (with its length if not censored). Durations,
  speed and observation effects of a transition are DIRECTLY OBSERVED only if such a transition occurs in a record;
  otherwise DOCUMENTED or UNKNOWN.
* **T7-B.** Per archetype and situation, when action 10 is listed: move path empty or not, `speed` zero or positive,
  in a move-to-stop transition or not. The natural move-to-stop transition at the end of a path (no stop order) is
  observable: the trajectory of `move_to_stop_remain_time`, `can_to_move`, `stop` and `flag_force_stop` from the step
  the move path empties, and the first step at which a shoot or occupy option, or move, is listed again. Stops on
  traversing units: what the records allow, otherwise UNKNOWN with the smallest probe that would establish it.
* **T7-C.** Per archetype and situation, when actions 11 and 12 are listed; the observed values of
  `weapon_unfold_state` and `weapon_unfold_time`; whether one unit can hold different states per weapon (the
  observation has one field per unit); the co-listing of 11 with action 6 option 1 (march).

Deployment-stage listings (the census lists actions 6 and 11 in every deployment decision) are audited separately;
whether a transition ordered during deployment, while `cur_step` stands still, completes before play is UNKNOWN unless
a record shows it, and every candidate of section 8 acts in the play stage only.

The matrix is published as `evaluation/t7-design-1/semantics.json` (version 1) and in section 13. Nothing enters the
trusted action catalogue (`decision/semantics.py`) or the gate.

## 7. WP2: opportunity and behaviour audit (method)

Per family (A: action 6; B: action 10; C: actions 11 and 12), per population, counted independently:

1. decisions in which the action is listed for at least one own unit;
2. unit-decisions listing it, and, for action 6, the options listed (per `target_state`);
3. distinct situations: unit-decisions deduplicated by the structural fingerprint (family, type, sub_type,
   `move_state`, `stop`, move path empty or not, `change_state_remain_time` positive or not, `weapon_unfold_state`,
   suppressed or not, `tire`, an enemy unit present in the seat view or not, the sorted listed option values of the
   family, the sorted other action types listed for the unit); no identifiers, hexes or steps;
4. actions of the family issued (seat actions in H0, submitted batches in H1 and H2, issued-action counts in R);
5. observed state transitions and completions (section 6);
6. what the frozen policy did with the unit in that decision instead (shoot, occupy, move, nothing);
7. listings with no executable opportunity: action 6 with no option different from the current `move_state`; action
   10 with an empty move path, or with `speed` 0 and a non-empty path (a unit waiting in front of a full hex, the
   Sprint 4 case); action 11 with `weapon_unfold_state` already 0; action 12 with `weapon_unfold_state` already 1;
8. missing, malformed, ambiguous and censored records.

Reconciliation: `scripts/tactical_census.py --check` must reproduce the published census byte for byte, and the new
audit's count 1 for the play stage of H0 must equal the census's 23,660, 27,220 and 23,118 exactly.

Independent cross-checks: counts 1 to 3 for H0 are computed twice, once from the raw observation dictionaries and once
through the canonical boundary (`Observation.valid_actions()`, `Observation.operators()`) by separately written code;
for H1 and H2, listings of own units are compared between the seat view and the all-seeing view where the latter lists
them; count 4 is compared between the observations' own actions and R. Any disagreement stops the audit until it is
explained. The analysis is first run on a real record (a fixture cut from one H0 game) before its results are used.
Only sanitised aggregates are published.

## 8. Candidate mechanisms (fixed before any candidate quantity)

Notation: `u` an own ground unit of the seat (type 1 or 2, in `operators`); `opts6(u)` the `target_state` values listed
for `u`; `v2(u)` what `baseline-v2` decides for `u` in the same decision; "enemy seen" means at least one operator of
the other faction in the seat view. Each candidate is a delta on `baseline-v2`. A2, B1, B2 and C0 act only on units to
which `baseline-v2` gives no action in that decision (a moving unit gets none) and never remove or change a
`baseline-v2` action; A1 and A3 replace `baseline-v2`'s move order for the unit by their own sequence, which the
isolation criterion scores. `v2(u)` is obtained by running the frozen `baseline-v2` on the recorded seat observation
(H1 is `baseline-v2` itself; H2's play stage is `baseline-v2`'s; on H0 the decisions are reconstructed by replay as in
`docs/LAUNCHER_DEPENDENCY_COUNTERFACTUAL.md`). Exposure and witnesses are read from the population's own recorded
trajectory (on H0, `baseline-v0`'s), which a candidate would have changed; they are descriptive, not effects.

| Id | Mechanism | Population | Trigger (seat-observable) | Action | Intermediate mechanism | Intended benefit | Direct cost | Failure or irreversible consequence | Must not fire |
|---|---|---|---|---|---|---|---|---|---|
| A1 | road march for a long road journey | vehicles except artillery | `v2(u)` would order a move; the destination is reachable in the march graph (mode 1); the documented time saving `S = T0 - (T1 + 300)` is positive, with `T0 = sum (720 / basic_speed) * cost0` along `baseline-v2`'s path, `T1 = sum 8 * cost1` along the cheapest march path (8 s per hex at 90 km/h, scaled by the documented cost definition), 300 s = lock, enter march, leave march, unfold | 11, then 6 with `target_state` 1, then 1 on the march path, then 12 after arrival | `weapon_unfold_state` 0, then `move_state` 1, arrival step, unfold | earlier arrival at objectives | 300 s of transitions; no fire en route; the largest adverse target modifier while marching | march blocked by any stopped or non-marching unit in the next hex (columns); a multi-step plan interrupted half-way | an enemy is seen; the unit carries passengers; the path leaves the road |
| A2 | concealment of idle stationary units | own ground units, any sub_type | 4 in `opts6(u)`; `move_state` is not 4 and `change_state_remain_time` is 0; `stop` is 1 and the move path is empty; not suppressed (`keep` 0); `v2(u)` is no action; no enemy seen; the candidate has not ordered `u` to change state in the last 75 steps | 6 with `target_state` 4 copied from the listed option | `change_state_remain_time` positive, then `move_state` 4 | halved observation distance against the unit and favourable target modifiers while it stays idle | up to 75 steps in which the unit can take no other command (tanks excepted) | engine refuses or ignores the order; a shot or move delayed by the transition; repeated orders | moving units, units in any transition, suppressed units, units with a `baseline-v2` action, while an enemy is seen, units already concealed |
| A3 | infantry final-approach charge | infantry | 2 in `opts6(u)`; `v2(u)` would order a move of at most two hexes to an objective; `tire` 0 | 6 with `target_state` 2, then the move | `move_state` 2, arrival step, `tire` | arrival at the objective up to 72 steps per hex earlier | the charge transition (length not documented); fatigue | fatigue 2 freezes the unit; an unknown transition delays the move | an enemy is seen; `tire` above 0 |
| B1 | stop to engage | units without move-and-fire capability (observation field `A1` is 0) | the move path is non-empty and `speed` above 0; action 10 listed; an enemy ground unit is seen within the documented range of one of the unit's carried weapons (published weapon id mapping and range tables) | 10 | the unit completes its hex, serves the 75 s transition, then lists a shoot option | shots that a moving unit forgoes | the move is dropped (`baseline-v2` re-orders it after the transition); 75 s penalty | stop deferred or the unit frozen (Sprint 4 analogy); oscillating stop and move | a unit waiting in front of a full hex (`speed` 0 with a path); tanks (they fire while moving) |
| B2 | halt before exposure | moving ground units | the move path is non-empty and `speed` above 0; action 10 listed; the next hex is within the documented observation distance of a seen enemy unit and the current hex is not | 10 | the unit stops one hex short | fewer exposures to seen enemies | the move is dropped; 75 s penalty | stop deferred; the objective is never reached | a unit waiting in front of a full hex |
| C0 | weapon lock or unfold on its own | vehicles | 11 listed and no march planned | 11 | `weapon_unfold_state` 0 | none documented | the unit cannot fire until unfolded (75 s) | weapons locked when an enemy appears | always (no documented benefit; kept to be scored) |

A1 is one causal mechanism although it uses three action types: march requires locked weapons (D2, D7) and firing
after march requires unfolding, so none of its steps has a documented benefit alone; it is scored as one candidate and
never combined with A2, A3, B1 or B2. "Exiting march before an engagement" and "avoiding state changes whose
transition exceeds their benefit" are conditions inside A1 (`baseline-v2` never marches, so they have no population on
their own).

Benefit witnesses: the stated benefit condition each candidate must meet in at least one activation of a recorded
trajectory (counterfactual movement is not simulated):

| Id | Benefit witness in the recorded trajectory |
|---|---|
| A1 | `S` above 0 for the move the frozen policy actually issued (derived from the documented speeds; the arrival itself is not observed) |
| A2 | after the activation, while the unit stays idle and stationary, the opposing seat's view lists the unit (H0 only: the other populations' opponents are inert and uncaptured), or a `judge_info` record targets it |
| A3 | the frozen policy's actual move of at most two hexes, with the documented charge speed giving an earlier arrival |
| B1 | the enemy stays seen and within range for at least the unit's hex time plus 75 steps after the activation |
| B2 | after entering the next hex, the opposing seat's view lists the unit |

Exposure, the share of activations in which the candidate's action costs something the frozen policy did, is
defined per candidate: A2, activations followed within 75 steps by a decision in which the frozen policy gave the unit
an action; B1 and B2, activations on units whose remaining move path ends at an objective, so that the stop delays an
objective arrival; A1, activations with an enemy seen within the 150 steps after the order (lock and enter march,
before the move starts; the transitions at arrival depend on a counterfactual arrival and are not counted); A3, activations with an enemy seen within the 75 steps after the order
(the charge transition is not documented; 75 steps is a working figure and the cell is flagged UNKNOWN). A1 and A3
defer `baseline-v2`'s move rather than remove it.

Activation counts (per candidate, per population, per scenario and archetype), distinct situations, exposure and
benefit witnesses are computed only after this protocol is pushed, for H0 first, then H1 and H2.

## 9. WP4: rubric and selection (fixed before scoring)

`evaluation/t7-design-1/rubric.json` holds the criteria, anchors and weights below and is committed with this protocol.

| Criterion | Weight | 5 | 3 | 1 | 0 |
|---|---|---|---|---|---|
| G generality | 0.15 | activations in all 8 frozen scenarios of H0 and in at least 3 archetypes | in at least 4 scenarios | in 1 scenario | none |
| L leverage | 0.20 | a documented effect on a scoring mechanism (losses, occupation, fire) of at least a 2-point table modifier or a 30% time saving, in most activations | a documented effect conditional on enemy behaviour | marginal | none |
| O observability (mandatory, at least 4) | 0.15 | every trigger input a seat field (class 1) | an input whose semantics is unverified | an input not in the seat view | (score 0 when the trigger needs hidden state) |
| E existing evidence | 0.10 | the effect observed in project records | the action listed for the population (observed) and its effect documented | effect only hypothesised | contradicted |
| I isolation | 0.10 | one action type, only on units `baseline-v2` leaves idle | a two-step sequence of one mechanism | changes several behaviours | inseparable |
| S safety and reversibility (mandatory, at least 3) | 0.10 | documented free reversal, no known unsafe case | a bounded irreversible window (at most 75 s), no known unsafe case | can freeze units | known unsafe |
| C opportunity cost and latency (cheaper scores higher) | 0.10 | exposure at most 1% of activations | at most 15% | above 30% | removes a `baseline-v2` action without carrying it out later, every time |
| M measurability | 0.10 | the intermediate mechanism is a seat-observable field change, measurable per activation by the existing full-step capture | needs new capture fields | needs an unvalidated simulation | not measurable |

Scores 4 and 2 lie between the anchors (4: G at least 6 scenarios; L a documented effect of smaller size or in some
activations; O class 2, derived from seat fields, setup data and documented constants; E action accepted and effect
documented; I one action type replacing nothing but needing memory; S reversal at a bounded cost; C at most 5%; M
needs both seats' views, which the existing capture records. 2: G at least 2 scenarios; L hypothesised only; O an input
reconstructed from history the seat cannot keep; E documented only; I a multi-action sequence; S a known-unsafe case
excluded only by an unverified rule; C at most 30%; M outcome level only). The full anchor set is in `rubric.json`. Each score cites its
evidence. A cell whose decisive evidence is UNKNOWN is capped at 2 and flagged; it is never given a favourable value.

Selection: the candidate with the highest weighted score among those meeting both mandatory conditions; ties by L, then
S, then I, then the order of section 8. Sensitivity (declared now, 28 variants): equal weights; each weight plus or
minus 0.05 with the others rescaled (16); each criterion left out (8); leverage 0.40 (1); every flagged UNKNOWN cell at
0 and at 5 (2). A selection that is first in fewer than 20 variants is reported as fragile. The highest score does not
override a failed mandatory condition, and if no candidate is eligible none is selected.

Minimum evidence to build offline tooling for the selected candidate: its action and parameter values DIRECTLY
OBSERVED as listed options for its population in H0, H1 or H2, and its effect DOCUMENTED. Nothing in this sprint makes
it eligible for an engine game; that needs its own proposal, registration and owner approval.

## 10. WP5: offline checks of the selected candidate (method)

The selected candidate is specified (section 14) before any tool for it is written. The shadow policy lives in a new
module under `src/miaosuan_agent/experiments/`; `baseline-v2` and every earlier candidate stay unchanged. It reads a
captured seat observation and its own memory, and proposes hypothetical actions; it never rewrites a capture, and the
recorded trajectory after a hypothetical action is never read as that action's result. The historical score of a game
is not an estimate of the candidate's effect.

Checks, each on H0, H1 and H2 separately: activation frequency; eligibility and option selection against an
independently written re-implementation of the trigger; action-contract validity (the emitted option is one listed for
the unit at that decision, with the documented key set); determinism (two runs identical; option and unit order
permuted gives the same decisions); no hidden-state dependency (the shadow receives only the seat observation, the
setup data and its memory); baseline equivalence (the composite `baseline-v2` plus candidate emits exactly
`baseline-v2`'s actions on every decision where the trigger is absent, and on trigger decisions differs only by the
added actions for idle units); detection of contradictory or missing observations (refuse, count, never guess);
latency and memory per decision; memory reset at game start and repeated identical observations. Interference with
engagement, occupation, existing move orders and same-step reservations is checked by asserting that no unit receives
two actions and no `baseline-v2` action is removed or changed.

Tests: a real-record test (a fixture cut from an H0 game, private, skipped when absent) before any judged use;
independent count cross-checks; planted-error tests; boundary cases (malformed options, duplicate observations,
interrupted transitions, a unit disappearing, several units triggering in one step, incompatible states, an action no
longer listed). Mutation testing of the trigger and of the analysis; every surviving mutant is killed or documented as
equivalent or as a residual weakness.

## 11. Gates and disposition (fixed before any candidate result)

| Gate | PASS only when | FAIL | UNRESOLVED |
|---|---|---|---|
| G1 evidence integrity | input files match their pinned or recorded SHA-256 digests before and after the study; the census reconciles exactly (section 7); every central count agrees with its independent cross-check; the analysis passed its real-record test before use | any of these fails | never |
| G2 observable and supported mechanism | every input of the selected trigger is class 1 or 2 (seat fields, setup data, documented constants); its action and parameter values are DIRECTLY OBSERVED as listed for its population; its effect is DOCUMENTED; every engine behaviour it relies on that is not DIRECTLY OBSERVED is named as a probe endpoint | an input is not seat-observable | the action or option was never observed listed for the population |
| G3 safety and non-interference | the shadow excludes the known unsafe cases (any stop on a unit waiting in front of a full hex; units in a transition; suppressed units), the composite equals `baseline-v2` on every decision without a trigger, no unit gets two actions, no `baseline-v2` action is removed, and the checks of section 10 pass | any of these fails | never |
| G4 actionable opportunity | the trigger fires in at least 2 of the 8 H0 scenarios, and the candidate's benefit witness (section 8) holds in at least one activation | the trigger never fires | the trigger fires but no record can show the benefit witness, and only a new game could |
| G5 testability | a future probe can isolate the candidate (the same runtime and conditions with and without it, or a mechanism-only screen) and measure its intermediate mechanism directly from captured fields, with a fixed size and stopping rules, without a simulation | no such design | never |

Disposition, evaluated in this order:

1. no candidate meets both mandatory conditions, or the trigger of every eligible candidate never fires:
   `SHELVE_T7_FOR_NOW`;
2. G1 fails: `REVISE`;
3. G2 is UNRESOLVED, or G4 is UNRESOLVED because only a game could show the witness: `NEEDS_ENGINE_PROBE`, naming the
   behaviour and the smallest probe;
4. G4 is UNRESOLVED and existing records could settle it: `NEEDS_MORE_OFFLINE_EVIDENCE`;
5. G2, G3 or G5 fails for a correctable reason: `REVISE`;
6. G1 to G5 all pass: `READY_FOR_MECHANISM_PROBE`, and `docs/T7_SCREEN_PROPOSAL.md` is written.

These are Sprint 5 research dispositions; they do not change the hypothesis register's states by themselves. An offline
legality check never validates an engine mechanism.

## 12. Conditional proposal

Only under `READY_FOR_MECHANISM_PROBE`: `docs/T7_SCREEN_PROPOSAL.md`, a proposal for the owner's approval, specifies the
smallest prospective mechanism test before any tactical A/B: the exact policy delta; runtime, candidate and baseline
identities; scenarios and seats; fixed sample size; capture requirements; safety endpoints; mechanism endpoints;
primary metric; independent validation checks; stopping rules. It compares `baseline-v2` with `baseline-v2` plus
exactly the one mechanism under identical conditions, or proposes a mechanism and safety screen only when an effect
cannot be told from outcome variability at an affordable size. It is not a registration; any engine experiment needs
its own public registration before its first session.

## 13. Results of WP1 to WP4 (written after the protocol was public)

Sections 1 to 12 were pushed in `e753456` at 2026-10-02T20:33:20+08:00 and fetched back unauthenticated at
2026-10-02T20:33:31+08:00, byte-identical. Everything below was computed afterwards by `scripts/t7_study.py` (public
aggregates `evaluation/t7-design-1/audit.json` and `candidates.json`), `scripts/t7_semantics.py` (`semantics.json`),
`scripts/t7_rubric.py` (`scores.json`, `selection.json`) and, after the selection, `scripts/t7_posthoc.py`
(`posthoc.json`, POST HOC).

### 13.1 Evidence integrity

* Before the full run, the audit ran on real records: `tests/test_real_t7_audit.py` (a 900-decision slice of one H0
  game and 400 snapshots of H1) passed its 4 real-record tests: pinned digest, audit against the boundary cross-count
  and an inline census-style count, `baseline-v0` replaying every decision of the slice, seat against all-seeing
  listings.
* Inputs: the 8 H0 games match their pinned digests; the SHA-256 of every H1 and H2 capture file is in `audit.json`,
  and the close-out rebuild (`--check`) reproduces it.
* Census reconciliation: `scripts/tactical_census.py --check` reports "census identical", and the audit's H0 play
  decisions listing change state, stop and weapon lock are 23,660, 27,220 and 23,118, equal to the census.
* `baseline-v0` replays all 33,696 H0 decisions exactly; `baseline-v2` is reconstructed on all 33,696 and differs from
  `baseline-v0` in 123, each difference carrying `baseline-v2`'s own reservation record.
* The boundary cross-count agrees with the audit on counts 1 to 3 in H0, H1 and H2.
* Own-unit T7 listings are identical in the seat and the all-seeing views: 10,800 in H1 and 112,118 in H2.
* H2r: P1's 532 decisions before its trigger list the same T7 actions as game `c`.
* Issued actions: in 1,284 game records (the prevalence study excluded) no frozen policy issued a T7 action; the only
  T7 actions ever issued are P1's 4 stops, counted 4 in its record and 4 in its compact log.
* Process note: the first full run labelled every stop listing with `speed` 0 and a move path as a unit waiting in front
  of a full hex, but 3,704 of the H0 listings belong to aircraft. The label was split into ground and aircraft cases
  and the study rerun before any result was used; no count changed.

### 13.2 Action semantics (WP1)

The versioned matrix is `evaluation/t7-design-1/semantics.json` (version 1, 25 claims). Its observation claims are
computed and asserted from `audit.json`; the script stops if the data contradict a stated level.

| Id | Claim | Level |
|---|---|---|
| A-1 | Listed change-state options: vehicles {4, 5} or {5}, infantry {2, 3, 4}; option 0 (normal) and option 1 (march) never listed | DIRECTLY OBSERVED |
| A-2 | Action 6 is listed only for units without a move path: stationary (180,833 unit-decisions) or in the move-to-stop transition (5,337); never with a move path | DIRECTLY OBSERVED |
| A-3 | A suppressed vehicle is listed half speed only (2,003 unit-decisions), never concealment | DIRECTLY OBSERVED |
| A-4 | Action 6 is listed in every deployment decision; the effect of a deployment-stage change is unknown | DIRECTLY OBSERVED; UNKNOWN |
| A-5 | `move_state` is 0 in every listed own unit and never changes; `change_state_remain_time` is never positive: no state transition occurs in any record | DIRECTLY OBSERVED |
| A-6 | The documented unit field `target_state` is absent from every unit record read | DIRECTLY OBSERVED (contradicts the field list) |
| A-7, A-8 | Concealment: 75 s entry without other commands, interrupted by a tank firing or suppression, ended free by moving or firing; half observation distance and favourable target modifiers | DOCUMENTED |
| A-9, A-10 | March prerequisites, speeds, restrictions and blocking; march hex time 8 s per march cost | DOCUMENTED; DERIVED |
| A-11, A-12 | Charge speed and fatigue (transition time undocumented); half speed for minefields | DOCUMENTED; UNKNOWN |
| A-13 | When option 1 (march) is listed | UNKNOWN |
| B-1 | Action 10 is listed only for units with a move path: 204,629 traversing, 62,859 with `speed` 0 (9,003 of all listings are aircraft); never without a path | DIRECTLY OBSERVED |
| B-2 | At the natural end of a path, `stop` becomes 1 exactly 75 steps after the path empties in every arrival observed to settle (141); movement is listed again at once | DIRECTLY OBSERVED |
| B-3 | After an arrival, non-tank units list a shoot option from 75 steps on; tanks at once | DIRECTLY OBSERVED |
| B-4 | A stop on a unit waiting in front of a full hex is deferred indefinitely (Sprint 4) | DIRECTLY OBSERVED |
| B-5 | A stop on a traversing unit | DOCUMENTED; UNKNOWN on engine 4.1.0 |
| B-6 | `speed` above 0 does not exclude a unit whose next hex fills before it arrives | DIRECTLY OBSERVED |
| C-1 | Action 11 is listed only for stationary, unfolded, unsuppressed vehicles, never in the move-to-stop transition | DIRECTLY OBSERVED |
| C-2 | Every own unit stays unfolded; action 12 is never listed; no lock or unfold occurs | DIRECTLY OBSERVED |
| C-3 | One lock state per unit in the observation; per-weapon engine state unknown | DERIVED; UNKNOWN |
| C-4 | Lock and unfold take 75 s each and exclude other commands; lock before march, unfold after it | DOCUMENTED |
| C-5 | Action 11 is listed in every deployment decision; its effect there is unknown | DIRECTLY OBSERVED; UNKNOWN |
| X-1 | No frozen policy issued a T7 action; only P1's 4 stops | DIRECTLY OBSERVED |

Consequences: no T7 transition has ever been observed on engine 4.1.0, so every duration and effect beyond the natural
move-to-stop transition is DOCUMENTED at best. March cannot be studied from records: its option was never listed and
no unit ever locked. The audit adds nothing to `decision/semantics.py`.

### 13.3 Opportunity and behaviour (WP2)

Play stage, per population; "units" counts unit-decisions; the frozen policy is `baseline-v0` in H0, `baseline-v2` in
H1 and the split candidate in H2.

| Family | Population | Decisions listing | Units | Distinct situations | Issued | Frozen policy gave the unit nothing | No executable opportunity |
|---|---|---|---|---|---|---|---|
| A change state | H0 | 23,660 | 147,895 | 95 | 0 | 147,181 | 0 |
| A change state | H1 | 1,163 | 4,610 | 8 | 0 | 4,598 | 0 |
| A change state | H2 | 2,883 | 33,665 | 19 | 0 | 33,577 | 0 |
| B stop | H0 | 27,220 | 182,925 | 38 | 0 | 182,786 | 18,332 |
| B stop | H1 | 1,799 | 6,190 | 3 | 0 | 6,190 | 0 |
| B stop | H2 | 4,678 | 78,373 | 11 | 0 | 78,373 | 44,527 |
| C weapon lock | H0 | 23,118 | 134,253 | 37 | 0 | 133,968 | 0 |
| C weapon lock | H1 | 1,085 | 4,302 | 4 | 0 | 4,298 | 0 |
| C weapon lock | H2 | 2,881 | 32,299 | 7 | 0 | 32,268 | 0 |

Weapon unfold is listed nowhere. In H0, artillery holds 103,680 of the change-state and 103,680 of the weapon-lock unit
listings. The stop listings without an executable opportunity are those with `speed` 0 and a move path: in H0 14,628
ground and 3,704 aircraft unit-decisions, in H2 44,527 ground (the split games' deadlock). Distinct situations per H0
game range from 5 to 61 (change state), 5 to 34 (stop) and 1 to 22 (weapon lock). No record was missing, malformed or
ambiguous beyond the absent `target_state` field (A-6) and the H0 deployment-to-play step gaps (16, one per seat and
game).

### 13.4 Candidate pool (WP3)

`candidates.json`; "units" counts distinct units; exposure and witnesses as defined in section 8 (descriptive, from the
recorded trajectory).

| Id | Population | Activations | Units | Scenarios | Archetypes | Distinct situations | Exposure | Benefit witness (activations, units) |
|---|---|---|---|---|---|---|---|---|
| A1 | H0, H1, H2 | 0 | 0 | 0 | 0 | 0 | none | none |
| A2 | H0 | 234 | 49 | 8 | 4 | 6 | 4 | 39, 16 (4 scenarios) |
| A2 | H1 | 60 | 4 | 1 | 2 | 2 | 0 | not observable (inert opponent) |
| A2 | H2 | 429 | 16 | 1 | 5 | 6 | 0 | not observable (inert opponent) |
| A3 | H0, H1, H2 | 0 | 0 | 0 | 0 | 0 | none | none |
| B1 | H0 | 33,478 | 72 | 6 | 3 | 7 | 33,478 | 13,553, 54 |
| B2 | H0 | 17,318 | 111 | 5 | 9 | 14 | 17,318 | 10,884, 99 |
| B2 | H2 | 98 | 5 | 1 | 3 | 3 | 98 | not observable |
| C0 | H0, H1, H2 | 0 (never fires by design) | 0 | 0 | 0 | 0 | none | none |

Why A1 and A3 never fire (`posthoc.json`, a diagnostic of the implementation): of `baseline-v2`'s 340 vehicle move
orders in H0, 220 were issued with an enemy seen, 14 by a vehicle carrying passengers and 97 to a destination the march
graph does not reach; the other 9 all lose time once the four transitions are counted (from 510 to 116 s). Of its 51
infantry move orders, 50 are longer than two hexes and 1 has an enemy seen. Every B1 and B2 activation is exposed: each
stopped move ends at an objective.

### 13.5 Scores and selection (WP4)

`scores.json` (every score with its reason; G and C computed from the H0 activations, U marks an UNKNOWN cell capped at
2) and `selection.json`:

| Id | G | L | O | E | I | S | C | M | Weighted | Mandatory conditions |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 road march | 0 | 1 | 4 | 2U | 2 | 1 | 2U | 5 | 2.00 | S fails |
| A2 idle concealment | 5 | 3 | 4 | 3 | 4 | 3 | 4 | 5 | **3.85** | met |
| A3 infantry charge | 0 | 1 | 4 | 3 | 3 | 2U | 2U | 5 | 2.30 | S fails |
| B1 stop to engage | 4 | 3 | 4 | 2U | 5 | 2 | 1 | 5 | 3.30 | S fails |
| B2 halt before exposure | 3 | 2 | 4 | 2U | 5 | 2 | 1 | 4 | 2.85 | S fails |
| C0 lock alone | 0 | 0 | 5 | 3 | 5 | 3 | 2U | 5 | 2.55 | met |

**Selected: A2, concealment of idle stationary units.** It is first in all 28 declared sensitivity variants, and it also
has the highest weighted score of the whole pool, eligible or not, in all 28. Both stop candidates fail safety: the
only engine evidence about stops is Sprint 4's frozen units, and `speed` above 0 does not exclude a unit about to
wait (B-6). March fails safety on its documented blocking rule and never shows a time saving in the records.

POST HOC description of A2 in H0 (`posthoc.json`; it changes no score or gate): each of the 49 first-activated units
then stays idle and stationary for at least 410 steps, 47 of them to the end of the game; all 39 witnessed activations
are witnessed through the opposing view (no `judge_info` record targets an activated unit), 25 of them 75 or more steps
after the activation. DERIVED from the documented distances, assuming unchanged lines of sight and the opponent as
recorded, and ignoring terrain halving: of the 21,196 unit-steps in which the opponent saw one of the 16 observed
units after a 75-step transition would have ended, 2,725 have an opposing unit within the concealed observation
distance; 9 of the 16 units would not have been observable at any of those steps, 7 at every one.

## 14. The selected mechanism: specification (written before any tool for it)

Name `t7-idle-concealment`, a delta on `baseline-v2`, for an offline shadow and a future mechanism probe only.

* **Order of decision.** `baseline-v2` decides first on the seat observation, unchanged. Then each own unit, in
  ascending `obj_id`, that received no `baseline-v2` action is checked against the trigger.
* **Trigger** (all must hold): the unit is an own ground unit (type 1 or 2) listed in `operators`; `valid_actions` lists
  action 6 for it with an option whose `target_state` is 4; `move_state` is not 4; `change_state_remain_time`,
  `move_to_stop_remain_time`, `weapon_unfold_time`, `get_on_remain_time` and `get_off_remain_time` are numbers equal
  to 0; `stop` is 1; `move_path` is an empty list; `keep` is 0; no operator of another faction is in the seat view; the
  candidate has not ordered this unit to change state in the last 75 steps (`cur_step` difference below 75).
* **Action.** `{"actor": seat, "obj_id": unit, "type": 6, "target_state": 4}`, the option copied from the listing.
* **Memory.** `baseline-v2`'s memory plus, per unit, the `cur_step` of the candidate's last change-state order; reset at
  game start; nothing else.
* **Own check.** Action 6 is not in the gate's catalogue (as action 314 was not for the split candidate), so the
  candidate checks its own actions: the option is listed for the unit in this observation, the key set is exactly
  `actor`, `obj_id`, `type`, `target_state`, and no unit receives two actions in the step. A failing check drops the
  action and records why.
* **Never.** It never removes or changes a `baseline-v2` action, never orders a moving, stopping, suppressed or
  transitioning unit, never acts while an enemy is seen, never acts in deployment, never uses another seat's view, the
  all-seeing state or hidden information, and never retries within 75 steps.
* **Fail closed.** A missing or malformed field or option means no trigger, counted by reason.

Engine behaviour it relies on, none of it observed (each a probe endpoint): E1 action 6 with option 4 is accepted from
such a unit without an error; E2 `change_state_remain_time` becomes positive and `move_state` becomes 4 after about 75
steps; E3 a concealed unit keeps its listings (shoot, occupy, move) and a later `baseline-v2` move or shot ends
concealment without delay; E4 an enemy unit beyond half its documented observation distance stops seeing the concealed
unit; E5 an order during the transition (a `baseline-v2` shot or move) is refused or delayed, and suppression
interrupts the transition; E6 concealment changes nothing else (occupation, stacking, scores).

Limitations, stated now: the benefit is conditional on the opponent observing or firing at the idle units, which the
inert control never does; terrain halving and its stacking with concealment are undocumented; H1 and H2 have one and
two games against an inert opponent, so only H0 shows a benefit witness; the historical outcomes say nothing about the
effect, because the recorded trajectories never contained a concealed unit.

## 15. Offline checks of the selected mechanism (WP5)

Sections 13 and 14 were pushed in `4f6fd1c` at 2026-10-02T21:19:48+08:00, before the shadow existed. The shadow is
`src/miaosuan_agent/experiments/t7_idle_concealment.py` (not registered, not packaged, not in the policy registry); the
checks are `scripts/t7_shadow.py` (`evaluation/t7-design-1/shadow.json`). For every recorded decision the shadow
decided on the seat observation while an independent `baseline-v2` instance decided on the same observation.

| Check | H0 | H1 | H2 |
|---|---|---|---|
| Decisions | 33,696 | 1,800 | 4,684 |
| Concealment orders (activations) | 234 | 60 | 429 |
| Units ordered | 49 | 4 | 16 |
| Orders not found by the independent pool predicate, and the reverse | 0, 0 | 0, 0 | 0, 0 |
| Decisions where `baseline-v2`'s actions and trace equal the independent instance's | 33,696 | 1,800 | 4,684 |
| Added orders with the option listed and the exact key set (checked on the raw listing) | 234 | 60 | 429 |
| Decisions with a unit given two actions; orders to a unit `baseline-v2` acted on; orders outside play | 0; 0; 0 | 0; 0; 0 | 0; 0; 0 |
| Recorded play actions reproduced by `baseline-v2` | not applicable | 1,800 of 1,800 (trace too) | 4,680 of 4,680 |

H1 decided a second time, and once with operators, options and `valid_actions` shuffled, gave identical decisions;
deciding every H1 observation twice in a row added no order the second time. No observation in any population had a
missing or malformed field the trigger reads; the fail-closed paths are exercised by the synthetic tests. The shadow's
median added decision time was 0.068 ms in H0 (99th percentile 1.296 ms against 1.238 ms for `baseline-v2` alone) and
its memory never held more than 16 entries. In H0 the most frequent reasons not to order a unit were: change state not
listed (175,256 unit-decisions), an enemy seen (127,250), not a ground unit (55,662), ordered within the repeat window
(14,765), in a transition (3,075) and concealment not listed (1,932).

Tests: `tests/test_t7_audit.py` (18), `tests/test_t7_shadow.py` (13), `tests/test_t7_analysis.py` (9) and
`tests/test_t7_results.py` (9), public; `tests/test_real_t7_audit.py` (8), private, including byte-identical rebuilds
of the audit, candidate, post-hoc, shadow-check and mutation outputs. Mutation testing (`scripts/mutate_t7.py`, `mutation.json`): 55 of 55
mutations killed. The first run killed 49 of 55; four survivors were test gaps (boundary cases of B1's range, B2's
observation band and A3's two-hex limit, and the sensitivity variant's treatment of unknown cells), one was the shadow's
own check, which its trigger makes unreachable (now tested with the trigger disabled), and one mutation was written
equivalent to the original (an odd-row offset expression rewritten into an identical one) and was replaced.

## 16. Gates and disposition

`scripts/t7_gates.py` applies section 11 to the outputs (`gates.json`, every verdict with its evidence):

| Gate | Verdict | Evidence |
|---|---|---|
| G1 evidence integrity | PASS | pinned and recorded digests, census reconciled exactly, cross-count agreement, seat and all-seeing listings identical, P1 reproduction, issued-action counts consistent, real-record test before use, byte-identical rebuilds |
| G2 observable and supported mechanism | PASS | every trigger input is a seat field, the frozen `baseline-v2` decision or the candidate's memory; option 4 listed for the population (A-1, A-2) and present for every order; effects documented (A-7, A-8); unobserved behaviour named as probe endpoints E1 to E6 (section 14) |
| G3 safety and non-interference | PASS | section 15: no stop of any kind, units in transitions and suppressed units refused, `baseline-v2` unchanged on every decision, no unit with two actions, determinism, 55 of 55 mutations killed |
| G4 actionable opportunity | PASS | activations in 8 of 8 H0 scenarios; benefit witness in 39 activations of 16 units |
| G5 testability | PASS | `docs/T7_SCREEN_PROPOSAL.md`: one mechanism added to `baseline-v2`, measured from captured fields by existing tooling, 3 games fixed, stopping rules, no simulation |

**Disposition: `READY_FOR_MECHANISM_PROBE`.** The proposal is for the owner's approval; it is not a registration, and
no engine session was used in this sprint (ledger still ends at 2461). In the hypothesis register the mechanism enters
as an `IDEA`: offline legality and non-interference are established, its engine effects are not.

## 17. Limits

* No T7 transition has been observed on engine 4.1.0. Every effect the mechanism relies on (acceptance, the 75 s
  transition, retained listings, free exit, halved observation distance) is documented, not measured.
* The benefit is conditional on an opponent that observes or fires; the inert control offers neither, and in H1 and H2
  no inert unit saw an activated unit after its transition window.
* The H0 trigger ran on `baseline-v2` decisions reconstructed on `baseline-v0` trajectories; exposure and witnesses are
  read from those trajectories, which a concealed unit would have changed.
* The derived observation share (section 13.5) ignores terrain halving and assumes the opponent as recorded.
* March, charge, stop-based tactics and weapon locking were not selected; their evidence and the reasons are in 13.4
  and 13.5. A stop on a traversing unit remains unobserved; the smallest probe would order one stop on a unit with
  `speed` above 0 whose next hex is not full, in a deterministic game, and record the hex completion, the transition
  length and the re-listing of movement.
