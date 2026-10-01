# Residual code-516 diagnostic

`baseline-v2-residual-516-diagnostic-1` is a registered, read-only engine-mechanism diagnostic. `baseline-v2`
(`docs/BASELINE_V2.md`) emits at most one shot per enemy target in a seat's decision step, which removed same-seat,
same-step repeated fire, but 16 refusals of the class `shoot / 516 / CantShootToDiedBop` remained in the
shoot-reservation experiment (`docs/EVALUATION_SHOOT_RESERVATION.md`). Each came in a step in which the seat had
emitted exactly one shot at the refused target, the target was on the map at the start of the step and gone after
it, and the records held no per-step action log that could say what removed it. 8 of the 9 in C3 were in scenario
1930331196. The question here is what removes those targets.

The diagnostic changes nothing that plays: no policy, routing, garbage-collection, runtime or engine change, and no
policy can be promoted by it. It is not a tactical evaluation, and its games are not a dataset for one.

This document was committed with the manifest, before any diagnostic engine session. The manifest is
`evaluation/baseline-v2-residual-516-diagnostic-1/manifest.json` (canonical SHA-256 `4811f1e8…`), built by
`scripts/build_residual516_manifest.py` from `src/miaosuan_agent/evaluation/residual516.py`; where this text and the
manifest differ, the manifest governs. Results are appended under "Results".

## Frozen identities

| Item | Value |
|---|---|
| Tactical baseline | `baseline-v2` (code identity `baseline-v2-candidate-shoot-target-reservation`), policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, golden trace chain `0d16c814c03909ed89303a776b276b4cc441cd047450a063329009458654910f` |
| Control | `inert-v0`: ends deployment, then never issues a unit action |
| Runtime | `baseline-v1-runtime-r2` (`docs/BASELINE_V1_RUNTIME_R2.md`): runtime-r1's code with `OPENBLAS_NUM_THREADS=1` |
| Scheduler | `miaosuan-game-pool/1@e717be37ab01d6c6018610bfc0af4df5f247a4599bc4c760c69499f04ed8ae90`, the pool the runtime qualification verified; the manifest builder refuses a checkout whose pool computes another identity |
| Execution | `execution.workers` 32, through `scripts/run_evaluation.sh` |

## What is known before registration

Established without an engine session, from the code, the committed records and the documentation.

**Seats and the joint action batch.**

* The registered players are one seat per faction: seat 1 (red) and seat 11 (blue), both with role 1, the
  layout of the SDK's single-agent runner. The SDK also ships a multi-agent runner with three seats per faction (one
  role-1 seat and two role-0 seats), each its own agent instance.
* The engine returns one observation per faction (state slots 0 and 1) and one all-seeing observation (slot -1).
  Every seat of a faction receives its faction's observation; there is no per-seat observation.
* In each step the game loop (`src/miaosuan_agent/evaluation/game.py`) calls each seat's `step()` once, one after
  another in the manifest's player order (seat 1, then seat 11), each with its faction's observation of the state
  before the step. The seats' action lists are concatenated in that order, each list in its policy's output order,
  and the concatenation is passed to one `TrainEnv.step(actions)` call. The engine therefore receives every seat's
  actions in one batch, and the seat order is the same in every step. The SDK's runners build the batch the same
  way.
* Each `baseline-v2` seat controls the units its `role_and_grouping_info` entry lists. Its reservation is local
  to one seat and one decision step; it does not see another seat's actions.
* Consequence for this configuration: under C3 the only seat that issues unit actions is blue's seat 11, so
  same-step fire from another friendly seat needs a second seat of the active faction to act. The registration does
  not presume its absence: the capture records every seat that `role_and_grouping_info` lists and the complete
  batch, and the H1 rule is evaluated on that evidence.

**Engine feedback.**

* The all-seeing observation carries `actions`. In engine 4.1.0 it holds one entry per unit action of the previous
  step, with the action echoed and, when the engine refused it, an `error` with code and message. In the 15
  shoot-experiment games of 1930331196 C3, group C, 977 entries echoed 992 emitted actions; the 15 not echoed are
  the deployment completions, one per game. Whether the order of the entries is the order of resolution is not
  documented; the capture measures how it relates to the batch order.
* Direct fire adds a `judge_info` record. In those 15 games, of 152 shots the 144 the engine accepted each had a
  record naming shooter and target in the next all-seeing observation, and the 8 refused had none. No documentation
  states whether the list holds only the step's records or accumulates them.

**`judge_info` fields.** The SDK's observation notes give each field a name and a short description; nothing about
units, ordering or list lifetime. Status before the capture:

| Field | What is documented | Status |
|---|---|---|
| `att_obj_id`, `target_obj_id` | attacking and target unit | documented; observed naming shooter and target of accepted shots |
| `cur_step` | the step | documented by name; its relation to the observation's `time.cur_step` is unknown and measured |
| `type` | damage type, a string | documented; its values are unknown |
| `guide_obj_id` | guiding unit | documented; its value for direct fire is unknown |
| `wp_id` | weapon | documented |
| `distance`, `ele_diff`, `att_level`, `att_obj_blood`, `align_status`, `offset` | firing geometry, attack level, attacker strength, spotting type, offset | documented by name; not used |
| `random1`, `random2`, `random2_rect` | random draws and their correction | documented by name; not used |
| `ori_damage`, `rect_damage`, `damage` | raw, corrected and final loss | documented by name; that `damage` reduces the target's `blood` and that a unit at 0 is removed is inferred, not documented |
| list lifetime | none | unknown: per step or accumulating, measured by the capture |
| kill or removal | no field | none: removal is read only from a unit's absence from both unit lists after the step |

The diagnostic therefore reads `judge_info` conservatively: a "positive damage record" is a record new in the step
whose `damage` is a number above 0; nothing is read from its other fields.

**Prior inspection of the existing records.** Before registration, the private records of the shoot-reservation
experiment were inspected for the unit class of each residual target. All 10 residual code-516 targets in scenario
1930331196 (8 in C3, 2 in C1) were of one class, an unmanned ground vehicle whose record names a launching vehicle.
That is why the capture watches each unit's `launcher`, `car`, `lose_control` and carried units; the taxonomy and
its rules do not depend on it.

## Plan

* **Configuration.** Scenario 1930331196 under C3: `baseline-v2` as blue (seat 11) against the inert control as red
  (seat 1), unchanged.
* **Games.** Exactly 32, `1930331196.C3.d01` to `.d32`, one wave of 32 workers. 32 games capture mechanisms; they
  estimate no rate. In the shoot experiment, 15 such games produced 8 residual refusals.
* **Courtesy and stopping.** Before the first game, the courtesy check of the concurrency qualification: other
  activity at most 16 logical CPUs over 30 s and at least 16 logical CPUs idle beside the 32 workers, rechecked
  every 300 s up to 6 times. If the host stays busy, the run waits; the worker count is not changed. Dispatch stops
  after 3 consecutive games that do not complete and on any other exit status. No game is retried or replaced; a
  failed game is kept and reported.
* **Capture.** A read-only observer (`residual516.Capture`) that the game loop calls once the agents are set up and
  after every engine step. It writes, privately, for every step: the complete submitted batch in engine order (seat,
  faction, batch position, position in the seat's output, the action); each seat's decision-trace digest and gate
  rejections; the engine's action feedback; the `judge_info` records new in the step and how the list relates to the
  previous one; indirect-fire points; units gone, appeared, boarded or landed; changes of each unit's `blood`,
  `lose_control`, `launcher`, `car`, `on_board`, `alive_remain_time` and `keep`. It also keeps the 5 most recent
  pre-step snapshots (the all-seeing observation, and the policy seat's observation, memory, actions and trace
  digest) and writes them, with the post-step all-seeing observation, only for a step whose feedback carries
  code 516. A snapshot of the policy seat is kept every 200 decisions for the replay check. Capture files go to
  `local/evaluation/<diagnostic>/capture/`, created exclusively.
* **Facts first.** Every code-516 refusal of the policy seat gets a private factual record before any category:
  action type, code, engine message and its class; seat and faction; actor, target and weapon; whether the target
  was on the map at step start, its class and watched fields; whether the shot was listed in the seat's
  start-of-step `valid_actions` and passed the project gate; every action of the batch naming the target, with its
  seat, faction, positions and feedback; shots at the target by the seat, by other seats of its faction, by the
  other faction and in total; target and actor after the step; the `judge_info` records new in the step on the
  target (attacker, whether it shot the target in this batch or in an earlier step) and those of the refused shot's
  actor; the objects linked to the target at step start (its `launcher` or `car`, vehicles listing it) with their
  presence after the step, their damage records and the batch's shots at them; indirect-fire points at the target's
  hex; the target's watched-field changes; and the shots at the target and records on it in the 30 preceding steps.
* **Taxonomy**, evaluated rule by rule on the factual record:

  | Category | Rule |
  |---|---|
  | H1 friendly cross-seat same-step fire | a positive damage record on the target from a shot that another seat of the refused seat's faction issued in the same step and that the engine did not refuse |
  | H2 opposing-seat same-step action | a positive damage record on the target from a unit of the other faction, or an accepted action of the other faction in the step that targets it or boards or unloads it |
  | H3 delayed or prior-step effect | a positive damage record on the target from a unit that did not shoot it in the batch but issued an accepted shot at it in an earlier step, or an indirect-fire point resolving at its hex |
  | H4 indirect, area or automatic engine effect | no positive damage record on the target, and an object linked to it at step start was present then and absent after the step |
  | H5 non-combat removal or state transition | no positive damage record, no linked removal and no opposing action on the target, and the target is a passenger after the step or its `on_board` becomes 1, its `lose_control` 1 or its `alive_remain_time` 0 |
  | H6 engine ordering or adjudication artifact | the target is still on the map after the step, or a record of the refused shot itself appears (one the actor's own earlier accepted shot does not explain) |
  | H7 unresolved | no rule matches, or more than one does |

  Exactly one matching rule gives the category; none, or two or more, give H7 with the matching rules listed.
  Strength: H1 to H3 strong when the attributed records' damage sums to at least the target's `blood` at step start
  and no positive record on it is unattributed; H4 strong when the linked object has a positive damage record and
  the target has no record at all in the step; H5 strong when the target is a passenger after the step; H6 strong
  when the target is on the map after the step; otherwise moderate. Batch position is reported, never used as
  evidence of resolution order.
* **Cross-seat fire.** For every refusal: whether another friendly seat shot the target in the step, how many seats
  and shots, the refused shot's batch position, the records on the target, whether the other faction acted on it,
  whether earlier steps hold shots at it or records on it, and whether its removal is attributed to an observed
  event. Over every captured step: (step, target) pairs shot by two or more seats of one faction, the steps holding
  them, and how many of them carried a code-516 refusal at that target and how many did not; same-seat repeated fire
  (must be 0 under `baseline-v2`); unit actions of the inert seat (must be 0).
* **Instrumentation checks.** Every game passes the independence comparison with the serial reference of
  1930331196 C3 under `baseline-v2` (state and trace digests over the 213-step common prefix of the 15 serial games,
  and a state chain equal to none of theirs); every in-game replay check agrees; offline, in a separate process, a
  fresh `baseline-v2` policy recomputes the decision of every captured snapshot from its observation and memory with
  identical actions and trace digest; observer time is measured and no observer error occurs. If any check fails,
  the diagnostic stops at analysis and reports no classification as valid.
* **Integrity.** One record and one pair of capture files per game, none overwritten; the capture's per-step trace
  digests chain to each seat's recorded trace chain; consecutive sessions, each opened and closed once, with the
  engine state, `home/` and package unchanged; every record names runtime-r2, its variable, 32 workers and the
  registered scheduler; no leftover process.
* **Conclusion**, mechanically: RESIDUAL 516 MECHANISM EXPLAINED when every instrumentation check passes, at least
  one residual refusal occurs and every one is in H1 to H6 with strong evidence; PARTIALLY EXPLAINED when the checks
  pass and at least one, but not every, refusal is in H1 to H6, or not every one with strong evidence; UNRESOLVED
  otherwise, including when no residual refusal occurs.
* **Artifacts.** Public: the module, manifest, scripts, this document and `results.json` with counts and sanitized
  timelines only. Private (git-ignored): records, capture logs and snapshots, factual records.
* **No remediation.** Whatever the first game shows, nothing changes before all 32 are recorded and analysed: no
  faction-wide reservation, communication, shared state, multi-step target memory or damage prediction. A tactical
  change needs its own registration.

## Coordination architecture, read only

Relevant if friendly cross-seat fire is observed; recorded here before any evidence.

| Question | Locally | Online |
|---|---|---|
| Do seats share a process? | yes: the game loop holds every seat's agent in one Python process | not documented per seat; the documented online setup runs the engine and the two agents as three processes, and an upload defines one `Agent` class |
| Does an observation show other friendly seats? | the faction observation lists every seat's `role_and_grouping_info` entry and every visible unit, not the other seats' actions of the same step | the same observation fields are documented; not verified online |
| Is there a documented coordination channel? | the SDK documents a role-1 seat's grouping, task and direction commands (types 100, 200, 201) and a custom message to teammates or all (type 204), which reach observations through `communication` | documented in the SDK notes; delivery timing and online availability are not verified |
| Would shared project memory work? | yes, between agent instances in one process | invalid if seats run in separate processes; not established either way |

> Correction (2026-10-01; text only, every result is unchanged): the second row is inaccurate. In engine 4.1.0 a
> seat's own observation lists only its own seat in `role_and_grouping_info` (16,848 views of each seat in the replay
> corpus and 448 diagnostic views; the all-seeing view lists both seats), as `docs/CONTRACT.md` records. Whether a
> seat would see other friendly seats in multi-seat play was not observed. A seat's view does not show enemy units'
> launcher relations either (`docs/LAUNCHER_DEPENDENCY_COUNTERFACTUAL.md`).

## Running

```bash
PYTHON scripts/build_residual516_manifest.py --check
PYTHON scripts/residual516_diagnostic.py preflight
PYTHON scripts/residual516_diagnostic.py snapshot --label before
bash scripts/run_evaluation.sh --python PYTHON --sdk-archive ZIP --plan residual516 \
    --evaluation baseline-v2-residual-516-diagnostic-1 --workers 32
PYTHON scripts/residual516_diagnostic.py snapshot --label after
PYTHON scripts/residual516_diagnostic.py analyze
```

## Results

All 32 registered games completed, in engine sessions 1866 to 1897, and every integrity and
instrumentation check passed. 12 residual code-516 refusals occurred, one in each of 12 games, and all 12 are
classified H4 with strong evidence. Every figure below comes from
`evaluation/baseline-v2-residual-516-diagnostic-1/results.json` unless a source is named;
`scripts/residual516_diagnostic.py analyze --check` regenerates it from the private records and captures, and
`tests/test_residual516_results.py` checks its counts and its conclusion against the registered rules.

### Execution

* The registration commit `69213fe` was on the public remote, verified at 2026-10-01T17:36:13+08:00, before
  the courtesy check and the first diagnostic session. All games ran at `73441a3` from a clean tree.
* The courtesy check passed at its first attempt: other activity used 0.18 logical CPUs over 30 s, leaving
  31.8 idle beside the 32 workers.
* The 32 games ran in one wave of 32 workers in 127.6 s; each took a median of 116.9 s and at most
  123.9 s. No game failed, was retried or was replaced. The plan was followed without deviation; the
  supplementary checks below were added after the results and are labelled as such.

### Integrity and instrumentation

| Check | Result |
|---|---|
| records, start markers, logs, capture pairs | 32 of 32, none overwritten; each capture matches the digests in its record, and its per-step trace digests chain to each seat's recorded trace chain |
| engine sessions | 32, consecutive, each opened and closed once; engine state, `home/` and package unchanged; 1 engine state throughout |
| execution | every record names `baseline-v1-runtime-r2` with `OPENBLAS_NUM_THREADS=1`, 32 workers and the registered scheduler; 0 leftover processes |
| independence prefix | 32 of 32 games equal the serial reference over the 213-step common prefix |
| in-game replay checks | 928, 0 mismatches |
| offline uninstrumented re-decisions | 506 captured decisions recomputed by a fresh policy, 0 mismatches in actions or trace digest |
| observer errors | 0 |

* The observer took a median of 5.29 s per game (at most 5.48 s), 4.5% of the game's
  wall time (at most 4.6%). The games' median wall time, 116.9 s, compares with 114.7 s for the same
  configuration, runtime and worker count without the observer in the runtime qualification's tier B-w32, a different
  run, so the difference is indicative only.

### Engine step and action architecture

* Each faction has 1 seat in `role_and_grouping_info` and 1 playing seat; all 26 units of each faction are listed
  under its playing seat, identically in every game. Blue's seat 11 plays `baseline-v2`; red's seat 1 the inert control,
  which issued 0 unit actions. Every play-stage batch therefore held seat 11's actions only, in its policy's
  output order.
* Feedback: in all 469 steps with two or more actions the engine's echoes came in batch order. Every action
  was echoed except in the 32 deployment steps, whose actions (deployment completion) are never echoed.
* `judge_info` holds the step's records only. Over the 92,192 engine steps of the 32 games the list was empty after
  91,968, became non-empty 221 times and was replaced by a different non-empty list 3 times; it never
  accumulated. All 297 records carried a `cur_step` equal to the observation's `time.cur_step` before the step.
* In each of the 224 steps with an accepted shot or a record, the records were exactly the accepted shots, by
  shooter and target (297 shots, 297 records; supplementary check). A refused shot left no record.
* Resolution order: the engine exposes no ordering field. Each refusal shows that its target had already been removed
  when the engine evaluated the shot; batch order matched echo order throughout, which is consistent with sequential
  processing in submission order but does not establish it (see the supplementary checks).

### Residual code-516 observations

* 12 refusals, all of the class `shoot / 516 / CantShootToDiedBop`, one in each of 12 of the 32 games. In the shoot
  experiment, 15 games of this configuration produced 8.
* Each was the seat's only shot at its target in its step (12 of 12), listed in the seat's start-of-step `valid_actions`
  (12) and passed by the project gate (12).
* Each target was on the map at step start (12) and in neither unit list after the step (12);
  each shooter was still present (12). Every target was a red unmanned ground vehicle.

### Cross-seat fire

| Measure | Count |
|---|---:|
| residual refusals with another friendly seat shooting the same target in the step | 0 |
| residual refusals without such fire | 12 |
| cross-seat same-target collisions (steps) | 0 (0) |
| collisions with a code-516 refusal / without | 0 / 0 |
| residual refusals with an opposing action on the target | 0 |
| unit actions of the inert seat | 0 |
| same-seat repeated fire | 0 |
| shots of the policy seat | 309 |

No second friendly seat exists in this configuration, so the zero collisions are structural; they say nothing about
play with several seats per faction.

### `judge_info` evidence

* No `judge_info` record named any refused target in its step (0 of 12); none named it, and no shot
  was aimed at it, in the 30 preceding steps (0 and 0); its watched fields did not change (0) and no
  indirect fire was involved (0).
* Every target named a launcher at step start, a red infantry fighting vehicle (12 of 12). In each step that
  vehicle received a positive damage record from an accepted shot of the same seat (12), was in neither unit list
  after the step (12), and that shot preceded the refused shot in the batch (12; the opposite order 0).
* No `judge_info` field names a removal, so kill attribution is indirect: the launcher's destruction is evidenced by its
  record and its absence; the target's removal, by its absence with no record of its own. `judge_info` was sufficient to
  exclude direct damage to the target, not to state the removal rule itself.

### Mechanism classification

| Mechanism | Count | Evidence strength | Notes |
|---|---:|---|---|
| H1 | 0 | n/a | no second friendly seat in this configuration |
| H2 | 0 | n/a | the inert control issued no unit action |
| H3 | 0 | n/a | no earlier shot at or record on any target |
| H4 | 12 | strong 12, moderate 0 | the target's launcher destroyed by the seat's own shot earlier in the batch |
| H5 | 0 | n/a | no state transition or boarding |
| H6 | 0 | n/a | no target on the map after its step |
| H7 | 0 | n/a | none |

### Supplementary checks (after the results; not preregistered)

They change no category and no conclusion. Counts are per game and launching vehicle.

* Each game lost exactly one red infantry fighting vehicle that had launched units (32, each with a positive damage
  record); the other two in each game survived (64).
* When such a vehicle was destroyed, the unmanned ground vehicle it had launched was removed in the same step without a
  record of its own 28 times and had been destroyed earlier, with its own record, 4 times; the infantry it had
  launched survived all 32 times. While it survived, every unit it had launched survived.
* At each of the 12 refusals the target stood in its launcher's hex together with one red infantry unit, which survived
  each time (12), so the removal is not a hex-wide effect.
* Of the 28 steps in which a destroyed vehicle took its unmanned vehicle with it, the seat shot at the unmanned vehicle after
  the shot at its launcher in 12 (each refused with code 516) and not at all in 16. No step held the opposite order, so whether
  the outcome depends on batch order was not tested.

### Representative timeline (H4)

Relative to the refused step, without identifiers:

| Step | Event | Engine |
|---:|---|---|
| 0 | another own unit shot at the target's launcher (batch position 1 of 2) | accepted |
| 0 | judge_info records on the target's launcher | 1 new, 1 with positive damage |
| 0 | the target's launcher after the step | absent |
| 0 | the refused shot at the target (batch position 2 of 2) | refused (516 CantShootToDiedBop) |
| 0 | the target after the step | absent |

### Conclusion

**RESIDUAL 516 MECHANISM EXPLAINED.** Every instrumentation check passed and all 12 residual refusals are classified H4 with strong
evidence: in the same step, and earlier in the same seat's batch, the seat's own accepted shot destroyed the vehicle that
had launched the target, an unmanned ground vehicle; the engine removed that vehicle with no record of damage to it, and
the seat's later shot at it was refused as fired at a destroyed unit. No other seat, no opposing action and no earlier
step was involved.

The finding covers scenario 1930331196 under C3. The other 8 residual refusals of the shoot experiment, 2 in this scenario
under C1 and 6 in other scenarios, were not captured here. The 2 under C1 also targeted unmanned ground
vehicles (the inspection before registration); for none of the 8 is the mechanism established.

### Limitations

* One configuration and 32 games: the diagnostic captures a mechanism; it estimates no rate.
* The removal rule (a launched unmanned vehicle goes with its launcher) is read from co-occurrence; the engine documents
  no such rule, and `judge_info` names no removal.
* Batch-order dependence was not tested, and one seat per faction excludes cross-seat fire by construction.
* `judge_info` semantics were observed on engine 4.1.0 only.
