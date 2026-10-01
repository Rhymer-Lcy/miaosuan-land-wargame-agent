# Launcher-dependency counterfactual

`launcher-dependency-counterfactual-1` decides whether one narrowly defined shooting rule deserves a registered
A/B experiment. The residual-516 diagnostic (`docs/RESIDUAL_516_DIAGNOSTIC.md`) found that, in scenario 1930331196
under C3, every residual `shoot / 516 / CantShootToDiedBop` refusal came after the same seat's own accepted shot,
earlier in the batch, at the vehicle whose `launcher` relation the refused target named; the engine removed the
launched unmanned ground vehicle with its launcher. The candidate below avoids a shot at a dependent target after a
shot at its launcher has been scheduled in the same step. This work replays it against `baseline-v2` on existing
private states, measures its benefit and its opportunity cost, and preregisters an experiment only if a gate
declared here, before the replay, passes. No engine session is opened.

This document was committed with the candidate, its tests and the replay tooling, before the replay was run.
Results are appended under "Results".

## What is known before the replay

From the SDK's observation notes, the private scenario files of the 8 registered scenarios, the diagnostic's
captures and the baseline-v0 replay corpus (read-only):

| Question | Status | Finding |
|---|---|---|
| Where is the relation? | documented | operator field `launcher`: after a unit dismounts or is launched, the vehicle it came from; on the vehicle, `launch_ids` (launched units) and `passenger_ids` |
| Type and absent value | observed | an operator id (int) or `None`; no other sentinel was seen |
| Which units carry it | observed | launched infantry and unmanned ground vehicles of both factions, pointing at infantry fighting vehicles of their own faction, in 6 of the 8 scenarios; the other 2 have none |
| Stable across steps? | observed | yes, while the launcher exists; when the launcher is destroyed, a surviving launched unit's `launcher` becomes `None` (32 of 32 such changes in the diagnostic) |
| Available after deployment? | observed | yes, from setup to the end of the game |
| Visible in the all-seeing view | observed | yes, for both factions |
| Visible in a seat's own view, own units | observed | yes |
| Visible in a seat's own view, ENEMY units | observed | **no**: every enemy unit's `launcher` is `None` and every enemy vehicle's `launch_ids` and `passenger_ids` are empty, although the all-seeing view holds them. Diagnostic: 183 of 183 views of each red unmanned vehicle and each red infantry fighting vehicle. Replay corpus: 7,174 of 7,174 enemy unmanned-vehicle views, 21,341 of 21,341 enemy-infantry views, 37,274 of 37,274 enemy-vehicle views |
| Why | inferred | the engine masks these fields in the opponent's view, as it shows the opponent a separate ammunition field (`remain_bullet_nums_bk`) |
| Online | unknown | whether the online platform's engine masks them the same way |
| Same field, other semantics? | observed | the field is the same for infantry and unmanned vehicles; the diagnostic found that destroying a launcher removes its unmanned vehicle but not its infantry, so the relation does not imply a common fate |

**Consequence, stated before the replay.** A rule that may read only the seat's own observation never sees an
enemy target's launcher in engine 4.1.0, so the candidate is expected to change no decision on real states. The
replay tests that expectation instead of assuming it, and a separate, explicitly labelled reference measures what
the same rule would do if the relation were observable.

## Candidate

`baseline-v3-candidate-launcher-dependent-shoot-reservation` (`src/miaosuan_agent/experiments/launcher_reservation.py`),
a candidate identity only; nothing is promoted or registered by this work.

* **The one change.** Within one seat and one decision step, the targets of the seat's shoot actions that have
  passed the final safety gate (the same record baseline-v2's shoot-target reservation keeps) are reserved
  launchers. A later unit's shoot option is excluded when its target, in the seat's observation, names a reserved
  launcher in its `launcher` field and is not itself a reserved target. Baseline-v2's logic, its shoot-target
  reservation included, then runs unchanged on the remaining options.
* **Meaning.** "Avoid a dependent-target shot after scheduling a launcher shot", never "the dependent is known to
  be dead": no damage prediction, no assumption that the launcher dies, no future outcome, no all-seeing view, no
  special case for a scenario, terrain, unit, operator id or error code.
* **Lifecycle.** The relation table is read from the observation at the start of each decision and cleared after
  it; reservations exist only within that decision. Only a gate-accepted shot reserves; nothing crosses seats or
  steps.
* **Malformed relations.** `None` or an absent field means no relation; any other non-int value (bools included)
  creates no exclusion and adds a diagnostic after baseline-v2's own.
* **Trace.** `launcher_reserved` lists, per affected unit, every excluded option (target, its launcher, weapon,
  attack level, the unit whose shot reserved the launcher and that shot's position in the seat's proposals), the
  effect (`unchanged`, `alternate-target`, `fallback-occupy`, `fallback-move`, `fallback-none`) and the reason
  `same-step-launcher-target-reserved`; a displaced unit carries the markers `launcher_target_reserved` and
  `launcher_reservation`. The existing records keep their meaning.
* **Tests.** `tests/test_launcher_reservation.py`, synthetic only, covers the 17 registered cases (launcher shot
  earlier; launcher not shot; a launcher option that loses selection; a rejected launcher shot; dependent processed
  first; two dependents of one launcher; alternate-target ranking; fallback to occupation, movement and nothing;
  absent and malformed relations; no leak across steps or seats; the shoot-target reservation unchanged; non-shoot
  actions unchanged; shuffle invariance), a secondary interaction classified C6, the baseline-v2 golden sequence
  unchanged, a generated corpus in which every difference is explained by the oracle, determinism and identity.
  `scripts/mutate_launcher_candidate.py` applies 12 semantic mutations; each must make the tests fail.

## Replay plan

* **D1, exact baseline-v2 states**: the residual-516 diagnostic's 32 games of 1930331196 C3 on runtime-r2. Every
  captured pre-step snapshot of the policy seat (event windows and every 200th decision; observation, memory,
  emitted actions, trace digest), replayed only where baseline-v2 reproduces actions, trace digest and memory
  exactly; and the compact log of every step for the exposure count below.
* **D2, reconstructed baseline-v2 decisions**: the replay corpus pinned by the routing remediation, 8 recorded
  baseline-v0 games (C1, both seats, every scenario), replayed seat by seat with persistent policies and memory.
  A decision is used only where baseline-v0 reproduces the recorded actions and trace digest exactly and every unit
  on which baseline-v2 differs from baseline-v0 carries baseline-v2's own occupation-suppression or
  shoot-reservation record. The trajectories are baseline-v0's, which bounds what their next states can say.
* Excluded states are counted with their reason; no observation is manufactured.
* **Comparison** (`src/miaosuan_agent/evaluation/launcher_counterfactual.py`): an oracle that does not import the
  candidate, baseline-v2 on the observation without the dependent options, must reproduce the candidate's
  actions, memory, records and trace. Each changed decision gets exactly one category: C1 alternate shoot, C2
  occupy, C3 move, C4 no-op (one unit displaced by the rule), C5 two or more units displaced, C6 a secondary
  interaction (an inherited reservation reacting to an earlier changed choice), C7 unexplained.
* **Known H4 events**: the 12 diagnostic refusals are replayable from their event snapshots; the candidate covers
  one when it no longer emits that shot. The 16 residual refusals of the shoot experiment have no captured states
  and are not evaluable.
* **Information-augmented reference, not a candidate**: the same rule deciding on the seat observation with every
  enemy unit's `launcher` taken from a view the seat does not have (D1: the all-seeing snapshot; D2: the opposing
  seat's own view at that step). Its suppressed shots are classified by the launcher's fate in the recorded
  trajectory: O1 removed in that step, O2 survived it, O3 unavailable or not comparable (D2: a decision on which
  baseline-v0's recorded actions differ from baseline-v2's, or no next state). Over every step of D1, the
  baseline-v2 shots the rule would meet are counted with the launcher's and the dependent's fate, and two
  decision-time signals (launcher strength at step start, weapon of the launcher shot) are checked for whether any
  value fixes the outcome. Nothing is fitted.

## Design gate

Declared before the replay. Preregistration needs every condition, evaluated on the faithful candidate:

| Gate | Condition |
|---|---|
| G1 | no C6 decision |
| G2 | no C7 decision and no unexplained state |
| G3 | every replayable diagnostic H4 refusal suppressed |
| G4 | no contract error and no gate rejection in the candidate's decisions |
| G5 | the rule reads only the seat's own observation (by construction; tested) |
| G6 | the opportunity cost is measured (O1, O2, O3 reported), not hidden |
| G7 | a meaningful A/B question remains: the candidate changes at least one decision on real states |

O2 is not required to be 0: it is what a real experiment would trade against. No quantitative threshold on O2 is
declared, because no value of a shot is established that would justify one. If every gate holds, the disposition
is qualitative: "clearly dominated / too broad" when no suppression is O1; "unresolved" when more than half of the
suppressions are O3; otherwise "mechanism-targeted and experimentally worthwhile", which leads to preregistration.

Disposition: BLOCKED when a frozen identity or the corpus fidelity cannot be established; DO NOT PREREGISTER when a
gate fails or the candidate is clearly dominated; PREREGISTERED - DO NOT RUN when every gate holds and the
candidate is worthwhile, after which an experiment is registered and pushed but not run.

## Running

```bash
PYTHON -m unittest tests.test_launcher_reservation
PYTHON scripts/mutate_launcher_candidate.py --check
PYTHON scripts/replay_launcher_counterfactual.py [--check]   # private inputs under local/
```

## Results

None at commit.
