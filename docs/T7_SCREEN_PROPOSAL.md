# T7 idle concealment: mechanism probe proposal

**PROPOSAL for the owner's approval.** Not a registration and not authorised: no engine session may run under it until
the owner approves, a registration commit with its manifest and code is pushed, and a public registration issue is
verified before the first session. It follows from the Sprint 5 design study (`docs/T7_DESIGN.md`, disposition in
`evaluation/t7-design-1/gates.json`). Times are UTC+8.

## Purpose

The study selected one T7 mechanism, `t7-idle-concealment` (`docs/T7_DESIGN.md`, section 14): order own ground units
that `baseline-v2` leaves idle and stationary, while no enemy is seen, into concealment. Its trigger, action contract
and non-interference were checked offline on 40,180 recorded decisions. What no record contains is a concealment order
or a concealed unit: every effect it relies on is documented, none observed on engine 4.1.0 (endpoints E1 to E6 of
section 14). This probe measures those effects in the smallest number of games before any tactical A/B. It is a
mechanism and safety screen, not an efficacy study: the benefit depends on an opponent observing or firing at idle
units, and an efficacy comparison would need many active-opponent games (the variance study's within-side spread), so
it is out of scope here.

## Policy delta

Exactly the specification of `docs/T7_DESIGN.md` section 14, applied to `baseline-v2` and nothing else:

* `baseline-v2` decides first, unchanged; its actions are emitted unchanged and in its order.
* Each own unit in ascending id that received no `baseline-v2` action, is a ground unit, has action 6 listed with
  `target_state` 4, is not in state 4, has `change_state_remain_time`, `move_to_stop_remain_time`,
  `weapon_unfold_time`, `get_on_remain_time` and `get_off_remain_time` at 0, `stop` 1, an empty move path and `keep` 0,
  while no operator of another faction is in the seat view and the candidate has not ordered it in the last 75 steps,
  is given `{"actor": seat, "obj_id": unit, "type": 6, "target_state": 4}`, after its own check (option listed, exact
  key set, one action per unit).
* No action in deployment; no stop, lock, unfold, march or charge; no use of another seat's view or the all-seeing
  state.

The registered candidate would be a policy module built from `src/miaosuan_agent/experiments/t7_idle_concealment.py`
(today an offline shadow), with its decision trace recording every added order and every skip reason.

## Identities

| Item | Value |
|---|---|
| Baseline | `baseline-v2`, policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Candidate | `baseline-v2` sources plus the candidate module; its digest is fixed in the registration commit |
| Runtime | `baseline-v1-runtime-r2` (`OPENBLAS_NUM_THREADS=1`), CPython 3.10.20, NumPy 1.26.2 |
| Scheduler | `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`, one worker (serial) |
| Engine | `land_wargame_train_env` 4.1.0, the persistent installation, through the project's session API only |
| Control | P-A: Sprint 2 game `b` (session 2459, `baseline-v2` against the inert control, every step captured) |

## Scenarios and seats

* **P-A** (deterministic, 1 session): scenario 1910631192, condition C3: the inert control as red, the candidate as
  blue; the configuration of Sprint 2 game `b`. That game fired no shot and is deterministic; the study's offline
  shadow orders concealment there for the first time at decision 717, to 4 units.
* **P-B** (observation, 2 sessions): scenario 2120531121, head to head: the candidate as red against `baseline-v2` as
  blue, then `baseline-v2` as red against the candidate as blue. In the replay corpus this scenario had the most idle
  units later seen by the opponent (9 of 12 first-activated units, `posthoc.json`), so it is where the observation
  effect can show.

## Sample size

Fixed at 3 games (3 engine sessions), run serially, P-A first. No game is replaced or repeated, whatever its result.

## Capture requirements

Every step: the all-seeing view and both seats' observations (the inert seat included), the actions as submitted
before the engine step (pre-execution copies), the engine's feedback with error codes, the candidate's trace (added
orders and skip reasons), the game record. Private, under the server's `local/` tree; public outputs are aggregates.

## Safety endpoints

* S1: no concealment order draws an engine error.
* S2: no unit loses its listings: no `flag_force_stop`, and no living unit outside a documented transition with an
  empty `valid_actions` entry.
* S3 (P-A): until the first concealment order, every state and decision equals game `b`'s; after it, every
  `baseline-v2` action equals game `b`'s at the same step, and the final scores equal game `b`'s.
* S4 (P-B): no refusal class absent from `baseline-v2`'s registered records; no candidate decision without its trace.

## Mechanism endpoints

* E1: each concealment order is accepted (echoed without error).
* E2: on the next step `change_state_remain_time` is positive; `move_state` becomes 4 after a number of steps whose
  distribution is reported (documented 75).
* E3: a concealed unit keeps its other listings; a later `baseline-v2` move or shot by it is accepted in that step
  and `move_state` leaves 4 without delay.
* E4 (P-B): for every step and every pair of an opposing unit and an own concealed unit with line of sight in the
  setup table, at hex distance `d`: whether the opposing seat lists the unit. Documented expectation: listed only when
  `d` is at most half the unconcealed distance (10 against infantry, 25 against vehicles), except a vehicle lower than
  its observer; the same pairs for unconcealed units of the same games are the comparison; terrain (towns, forest) is
  reported separately because whether its halving stacks with concealment is undocumented.
* E5: any `baseline-v2` order to a unit during its transition, and any suppression then: accepted, refused (code) or
  delayed, as observed.
* E6: nothing else changes: occupation flags, stacking and scores (P-A against game `b`).

## Primary metric

The completion rate of E2: concealment orders that reach `move_state` 4 within 76 steps, over orders issued, in P-A
and P-B together. The mechanism passes only at 100% with S1 to S4 met. Secondary: in P-B, the share of E4 pairs at a
distance above half and at most the full documented distance in which the opposing seat still lists the concealed
unit (documented expectation 0).

## Independent validation checks

* P-A premise: state and decision digests equal to game `b`'s up to the first order (two channels: the all-seeing
  state and the seat observation).
* Order counts three ways: the candidate trace, the engine feedback and the record's issued actions by type.
* The offline shadow re-decides every captured candidate decision and must reproduce the emitted actions exactly.
* The probe analysis runs first on a real record (game `b` itself: zero orders, every endpoint reported as not
  applicable) and on planted errors before the games; it refuses to report when two counts disagree.

## Stopping rules

* P-A runs alone first. If S1, S2 or S3 fails, or E2 fails, the probe stops: P-B is not run and the result is
  reported with the mechanism marked refuted or inconclusive.
* P-B runs its two games only after P-A passes. No third game; a failed or inconclusive outcome authorises nothing.
* Any integrity failure (ledger, engine state, replay mismatch, dirty harness) stops the probe at once.

## What would follow

If E1 to E3, E5 and E6 hold and E4 shows the halving, the next step is a tactical A/B of `baseline-v2` against
`baseline-v2` plus this mechanism under identical runtime and conditions, against active opponents, sized from the
variance study, preregistered separately. If any endpoint fails, the mechanism is recorded with that engine fact and
T7 returns to its pool.
