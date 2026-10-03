# Sprint 8: accelerated tactical exploration (T4 artillery, T9 force allocation)

Dates are business dates in UTC+8. Sprint 8 ran on 2026-10-03 from main `8dc9a8a` and introduced the `EXPLORATORY`
track (`docs/EXPLORATORY_TRACK.md`). Everything here is exploratory: directional, game-level evidence that never
promotes a baseline. One candidate is proposed for a separately registered confirmatory study
(`docs/T9_CONFIRMATION_PROPOSAL.md`).

## 1. Starting state

* Main `8dc9a8a` identical and clean on the workstation, GitHub and the server.
* Ledger: 2,464 sessions opened and 2,464 closed, the last a `session-close` of 2464, none unclosed; the installation's
  verify reported integrity ok and the state chain continuous.
* Canary `dist/miaosuan-baseline-v2-canary.zip` SHA-256 `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`
  (unchanged; upload instructions in `docs/PLATFORM_CANARY.md`; no platform test has taken place).

## 2. Process change and tooling

* Run cards (`scripts/build_run_card.py`, `evaluation/<card>/manifest.json`): candidate identity, mechanism, controls,
  game configurations, the batch's sessions and the sprint cap, safety checks, intended observations and the rule for
  the next step, committed and pushed before each batch. Cards are only added, never edited after their games began.
* Runner (`scripts/run_explore.sh`, `scripts/run_explore_game.py`): serial, one exclusive diagnostic session per game,
  the registered evaluator's isolation and game loop reused unchanged. The registered evaluator
  (`scripts/run_evaluation.py`, `scripts/run_evaluation.sh`) is not modified: the T7 probe registration pins both
  digests, and a first draft that extended it failed that registration's regeneration test, so the draft was reverted
  before any commit. Before every batch and every game the runner refuses when the sprint's ledger-counted cap (24
  sessions after 2464) would be exceeded.
* Candidates (`experiments/exploratory_addon.py`): `baseline-v2` decides first and unchanged; one add-on rule edits the
  decision, checks its own actions and falls back to `baseline-v2` on any error. The read-only capture
  (`evaluation/exploratory.py`) records indirect-fire orders, feedback, points and judgements, artillery state, waiting
  units and objective commitments; `scripts/explore_report.py` writes `evaluation/<card>/results.json` (aggregates only).
* Controls: `baseline-v2`'s own games of the registered shoot-reservation experiment (group C, 15 per configuration):
  C1 mirror for a head-to-head seat, C2 or C3 against the inert control. Each game is placed against that distribution
  (`z` = (margin - control mean) / control SD; below / above = control games with a smaller / larger margin).

## 3. Sessions

23 of the 24 authorised sessions were used, 2465 to 2487, every game completed, and the installation verified after
each card (integrity ok, state continuous, nothing unclosed). One session was left unused.

| Card | Candidate | Games | Sessions |
|---|---|---|---|
| `s8-t4-v1-mechanism` | `t4-artillery-v1` | 2 | 2465-2466 |
| `s8-t9-v1-mechanism` | `t9-capacity-allocation-v1` | 2 | 2467-2468 |
| `s8-t9-v1-h2h` | `t9-capacity-allocation-v1` | 6 | 2469-2474 |
| `s8-t4-v2-batch` | `t4-artillery-v2` | 7 | 2475-2481 |
| `s8-t4-v3-check` | `t4-artillery-v3` | 2 | 2482-2483 |
| `s8-t9-v1-rep` | `t9-capacity-allocation-v1` | 4 | 2484-2487 |

Before any session, both first candidates decided offline on the 17,286 recorded seat decisions of the three artillery
scenarios' replay corpus games: no add-on error, `baseline-v2`'s own actions unchanged on every decision (T4 only added
indirect fire; T9 changed only move orders), median decision time within 0.2 ms of `baseline-v2`.

## 4. Workstream A: indirect artillery fire (T4)

### Engine facts (4.1.0, this sprint's captures)

| Fact | Evidence |
|---|---|
| `valid_actions` lists indirect fire for artillery as `{8: [{weapon_id: 72}]}` with no target; the order is `{actor, obj_id, type 8, jm_pos, weapon_id}` and was accepted at 15 to 65 hexes | 367 orders in 11 games, none refused |
| After an order `weapon_cool_time` becomes 299 and action 8 leaves the listing until it returns to 0: one round per artillery unit per about 300 steps | artillery state every step |
| A round lands 150 steps after the order (149 steps after its point first appears in `jm_points`); the hex then explodes, usually for exactly 300 steps (longer where rounds on the same hex overlapped; a few shorter, cause not established); units in the hex are judged when it lands, units entering it later are judged on entry | `jm_points` and `judge_info` |
| Scatter shows as a landing hex different from the aimed one; observation by own ground units at landing gives correction (`align_status` 2) and most of the damage; uncorrected rounds at 40 or more hexes mostly scattered | judgements by correction status |
| Ammunition counters of artillery stay 0 throughout; the cooldown is the only limit seen | artillery state |
| Indirect fire damages own units: own units walking into an exploding hex are judged | version 2's games |

The engine's refusal catalogue names no out-of-range class for indirect fire, and none was observed.

### Versions and results

* `t4-artillery-v1`: each idle unit listing action 8 fires at the best hex of currently seen enemy ground units
  (stationary first), never within 2 hexes of an own ground unit or 1 of an own move path, one unit per hex.
* `t4-artillery-v2`: v1 plus remembered stationary enemies (600 steps) and re-fire on exploding hexes, answering v1's
  failure against the inert control (1 order in 2,880 steps: the enemy was out of sight).
* `t4-artillery-v3`: v2 plus no target within 4 hexes of any objective, answering v2's friendly fire: 55 of its 58
  own-unit judgements came from own units entering a still exploding hex, and every such hex lay within 4 hexes of an
  objective (none of the 133 exploding hexes 5 or more hexes away did).

`s8-t4-v1-mechanism`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Orders | Corrected (align 2) | Enemy losses | Own judgements | Own losses | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2120531121 H1 | 2465 | red | +81 | -245.0 (566.7) | 8 / 7 | +0.58 | 24 | 4 | 10 | 0 | 0 | 0 |
| 1930331196 C2 | 2466 | red | +274 | +272.9 (4.0) | 1 / 0 | +0.27 | 1 | 0 | 0 | 0 | 0 | 0 |

`s8-t4-v2-batch`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Orders | Corrected (align 2) | Enemy losses | Own judgements | Own losses | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1930331196 C2 | 2475 | red | +274 | +272.9 (4.0) | 1 / 0 | +0.27 | 5 | 0 | 0 | 0 | 0 | 0 |
| 2120531121 H1 | 2476 | red | -471 | -245.0 (566.7) | 8 / 7 | -0.40 | 34 | 23 | 18 | 0 | 0 | 0 |
| 2120531121 H2 | 2477 | blue | +811 | +245.0 (566.7) | 12 / 3 | +1.00 | 57 | 6 | 13 | 0 | 0 | 0 |
| 1930331196 H1 | 2478 | red | -158 | +179.6 (437.9) | 5 / 10 | -0.77 | 49 | 5 | 1 | 28 | 5 | 0 |
| 1930331196 H2 | 2479 | blue | -780 | -179.6 (437.9) | 0 / 15 | -1.37 | 32 | 1 | 0 | 1 | 0 | 5 |
| 2130511121 H1 | 2480 | red | -369 | -869.9 (110.8) | 15 / 0 | +4.52 | 58 | 34 | 35 | 14 | 2 | 0 |
| 2130511121 H2 | 2481 | blue | +465 | +869.9 (110.8) | 0 / 15 | -3.66 | 39 | 10 | 13 | 15 | 3 | 0 |

`s8-t4-v3-check`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Orders | Corrected (align 2) | Enemy losses | Own judgements | Own losses | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2130511121 H1 | 2482 | red | -873 | -869.9 (110.8) | 7 / 8 | -0.03 | 35 | 0 | 3 | 0 | 0 | 0 |
| 2130511121 H2 | 2483 | blue | +809 | +869.9 (110.8) | 6 / 9 | -0.55 | 33 | 19 | 12 | 0 | 0 | 0 |

Enemy and own losses are vehicles or squads removed by indirect-fire judgements. The 5 refusals in 1930331196 H2 are
code 203 (a shot by a unit destroyed earlier in the step), a known class unrelated to indirect fire.

Reading: the essential action executes every time (367 orders, 0 refused). Version 2 inflicts the most damage (80
enemy losses in its 6 head-to-head games) but judged own units in 4 of those 6 games and destroyed 10 of them, and its
margins scatter to both ends of the control in the least variable scenario (z +4.52 as red, -3.66 as blue). Version 3
removed own judgements in both games of that scenario but also most of the damage, and sat at the control mean. No T4
version shows a consistent margin gain. T4 is not proposed for confirmation.

## 5. Workstream B: capacity-limited objective allocation (T9)

`t9-capacity-allocation-v1` keeps a `baseline-v2` ground move while the destination objective has fewer than 4
commitments (own ground units standing on it, en route to it, or assigned in the step); otherwise it re-assigns the
move to the unheld objective under capacity with the lowest path cost per objective value within twice the original
cost, or withholds it for the step. In the replay corpus `baseline-v2`'s movement rule commits up to 17 ground units to
one objective in the large scenarios, and up to 10 or more ground units wait in front of full hexes.

`s8-t9-v1-mechanism`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Replaced | Withheld unit-steps | Max waiting (own / opponent) | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| 2130511121 C3 | 2467 | blue | +663 | +623.1 (32.0) | 15 / 0 | +1.25 | 21 | 28332 | 0 / 0 | 0 |
| 2120531121 C2 | 2468 | red | +485 | +357.0 (48.4) | 15 / 0 | +2.64 | 10 | 401 | 1 / 0 | 0 |

`s8-t9-v1-h2h`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Replaced | Withheld unit-steps | Max waiting (own / opponent) | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| 2120531121 H1 | 2469 | red | -515 | -245.0 (566.7) | 8 / 7 | -0.48 | 10 | 326 | 2 / 4 | 0 |
| 2120531121 H2 | 2470 | blue | +261 | +245.0 (566.7) | 7 / 8 | +0.03 | 16 | 11522 | 1 / 4 | 0 |
| 1930331196 H1 | 2471 | red | -118 | +179.6 (437.9) | 5 / 10 | -0.68 | 8 | 459 | 0 / 5 | 0 |
| 1930331196 H2 | 2472 | blue | +390 | -179.6 (437.9) | 12 / 3 | +1.30 | 20 | 2704 | 0 / 3 | 0 |
| 2130511121 H1 | 2473 | red | -815 | -869.9 (110.8) | 9 / 6 | +0.50 | 26 | 158 | 0 / 11 | 0 |
| 2130511121 H2 | 2474 | blue | +1133 | +869.9 (110.8) | 15 / 0 | +2.37 | 25 | 16367 | 0 / 2 | 1 |

`s8-t9-v1-rep`

| Game | Session | Side | Margin | Control mean (SD) | Below / above | z | Replaced | Withheld unit-steps | Max waiting (own / opponent) | Refusals |
|---|---|---|---|---|---|---|---|---|---|---|
| 2130511121 H1 | 2484 | red | -621 | -869.9 (110.8) | 15 / 0 | +2.25 | 25 | 1222 | 1 / 11 | 0 |
| 2130511121 H2 | 2485 | blue | +1077 | +869.9 (110.8) | 15 / 0 | +1.87 | 28 | 14764 | 0 / 2 | 0 |
| 2130511121 H1 | 2486 | red | -505 | -869.9 (110.8) | 15 / 0 | +3.29 | 34 | 643 | 1 / 11 | 0 |
| 2130511121 H2 | 2487 | blue | +1297 | +869.9 (110.8) | 15 / 0 | +3.86 | 21 | 23850 | 0 / 2 | 0 |

The one refusal (2130511121 H2, session 2474) is code 516 on a shot, a known class unrelated to movement.

Reading: the mechanism executes as designed (244 moves re-assigned, all accepted; 1 refusal in 12 games, unrelated).
Its own ground units waited in front of a full hex at most 2 at a time, against up to 11 for `baseline-v2` as the
opponent. Against the inert control both games lay above all 15 control games. Head to head, 8 of 10 games lay above
the control mean (mean z 1.43). In 2130511121, the scenario with the least variable control, all 6 lay above the
control mean and 5 above its maximum (mean z 2.36), and the summed margins of the three H1 and H2 pairs, which are 0
in expectation for two equal policies, were +318, +456 and +792. In the other two scenarios, whose controls vary by
438 and 567 points, the 4 games average z 0.04: no signal either way at that noise. These are 12 exploratory games
compared with historical controls, not a test.

What failed or is open: the add-on withholds a unit for the step whenever every objective is at capacity, which
leaves many units at their start for long stretches (up to 28,332 withheld unit-steps in one game); whether that costs
anything against a stronger opponent is untested. Capacity 4 and the detour factor 2 were chosen once and not tuned.

## 6. Comparison and next decision

| Candidate | Attempted | Essential action executed | What failed | Game-level result | Smallest next step |
|---|---|---|---|---|---|
| T4 v1 | fire at seen enemies | 25 of 25 orders accepted | idle when the enemy is out of sight | neutral (2 games) | superseded |
| T4 v2 | v1 + remembered targets, re-fire on exploding hexes | 274 of 274 accepted | friendly fire: own units walk into exploding hexes near objectives | mixed, extreme both ways (7 games) | superseded |
| T4 v3 | v2 without targets near objectives | 68 of 68 accepted | most damage lost with the friendly fire | at the control mean (2 games) | a movement-side guard (route around own exploding hexes) or targets the opponent must cross; shelved for now |
| T9 v1 | capacity-limited objective allocation | 244 of 244 re-assigned moves accepted | long withholding at the start; untested against stronger opponents | above the control in 10 of 12 games; consistent in the largest scenario | the registered confirmatory study proposed in `docs/T9_CONFIRMATION_PROPOSAL.md` |

Selected for confirmation: **T9 v1**, unchanged, in a new and separately registered study with fresh games
(`docs/T9_CONFIRMATION_PROPOSAL.md`, awaiting the owner's approval). The exploratory games are never pooled into it.
T4 is shelved without further process; its engine facts stand.

## 7. T7

The Sprint 6 disposition `NEEDS_TARGETED_PROBE` and the Sprint 7 disposition `E3B_CONFIGURATION_UNCERTAIN` stand. No T7
diagnostic-command experiment was built or run: the session budget went to T4 and T9 as the sprint's priority, and one
remaining session does not make a meaningful separate diagnostic. A deterministic diagnostic-command test (order a
completed concealed unit to move or fire in the P-A configuration) remains the smallest next T7 step, as a diagnostic
engine-mechanism test, not the registered E3b endpoint.

## 8. Platform

The canary is unchanged and ready; the owner's upload and compatibility steps are in `docs/PLATFORM_CANARY.md`. No
platform result exists, so the failure ledger is still empty and no platform observation enters this document.
