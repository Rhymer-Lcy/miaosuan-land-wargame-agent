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

None at registration.
