# Sprint 32: T7-B1 stop-to-engage, offline mechanism qualification

**OFFLINE DESIGN AND PREFLIGHT ONLY — NO ENGINE SESSION — SESSION 2801 STAYS UNOPENED — NOTHING PROMOTED — NOTHING
UPLOADED**

Dates are business dates in UTC+8 (2026-10-10). Sections 1 to 5 (the semantics, the candidate's rule and the preflight's
method and stop rule) were committed and pushed before the preflight ran; later sections are written afterwards and say
so. No registered section is edited afterwards.

## 1. Starting state and the owner's instruction

| Item | Identity |
|---|---|
| Frozen Sprint 31 branch | `sprint31-t13-k2`, head `dad446a4e215a74ad48ed643d4cf6d06ef031fce`, tree `abfc2405165415494122a56f11968bffff631770`, identical on the workstation and GitHub |
| `main` | `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`, unchanged |
| Engine ledger | 2,800 sessions opened and closed, none unclosed; ledger file SHA-256 `fde702863518b42eb983a206eab2fd3c870966cce338e61b8cfce129e3ebb799` at the Sprint 31 close-out; session 2801 unopened |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, unchanged |
| Privacy baseline | 106 accepted hit lines |

**Sprint 31 closure.** The owner accepted the registered disposition `K2_PILOT_REJECT` without modification. The
reference that the stop compared against came from games against another opponent, so nothing here claims that K2
caused the missed opening objective: K2's garrison executed on the engine and showed no tactical benefit in its only
head-to-head game.

**Authorization.** An offline investigation of T7-B1, stop-to-engage (`docs/SPRINT29_PLATFORM_FIRST.md`, section 7,
H2). No engine session is authorized. The deliverable is a historical feasibility preflight, a separately identified
candidate with its tests, and a proposed two-session mechanism check for the owner to approve or refuse.

## 2. Isolation and server use

The work is on the branch `sprint32-t7-b1`, created from the Sprint 31 head above in a separate workstation worktree,
and in a separate server worktree whose ignored `local/` folder links to the existing private folders (one engine
installation, one ledger). The shared workstation checkout (whose two uncommitted platform-compatibility files belong to
another session), the server checkout (`main`, `08aff3f`), both earlier sprint branches, the canary, its builder and the
adapter are not touched; `main` is not changed; only the new branch is pushed. Server CPU policy
(`docs/SERVER_RESOURCE_POLICY.md`): at the pre-work check one foreign job was running, pinned to NUMA node 1; this
project's jobs run pinned to node 0 (logical CPUs 0-15 and 32-47) with at most 8 worker processes (shared mode). No
engine process is started.

## 3. Research question and the engine semantics it rests on

**Question.** Can an own ground unit that is actively moving be ordered to stop safely, complete the documented
transition, become able to fire, and avoid a movement deadlock? This is a mechanism question, not a tactical one: a
working stop says nothing about combat scores.

### 3.1 Documented contract (platform rules snapshot of 2026-09-29, private under `local/source-archives/`)

The movement rule, verbatim:

> 机动指令一旦下达就不可更改，可以下达停止机动指令，停止机动指令下达后，当前机动指令未执行的部分不再执行，进入机动转停止阶段。

> 可以对机动中的棋子下达停止机动命令，收到停止机动命令后，棋子必须完成当前格的机动后，才能停止，棋子停止后即开始“机动→停止”转换。停止机动命令会导致75秒的惩罚性“机动→停止”转换，在这期间不能进行任何操作。

The fire rule, verbatim: "坦克主炮（大号、中号直瞄炮）具有行进间射击能力，可以在机动中射击。" and, among the conditions
of a shot, "地面棋子处于停止状态（坦克主炮除外），空中棋子处于悬停状态。" The observation reference documents `cur_pos`
as "当前格到下一格的百分比进度", `speed` as "当前机动速度 格/s", `A1` as "是否有行进间射击能力" and `see_enemy_bop_ids`
as "可见敌方算子ID列表". The action reference documents the stop order as the key set `actor`, `obj_id`, `type` 10.

So: a stop drops the rest of the move, the unit first completes the hex it is moving into, then serves a 75-second
transition in which it can do nothing; ground units other than tank main guns fire only when stopped.

### 3.2 Engine facts already recorded (engine 4.1.0)

| Id | Fact | Source |
|---|---|---|
| B-1 | Action 10 is listed only for units with a move path | `docs/T7_DESIGN.md` |
| B-2 | At the natural end of a path `stop` turns 1 exactly 75 steps after the path empties (141 of 141 arrivals); movement is listed again at once | `docs/T7_DESIGN.md` |
| B-3 | After an arrival non-tank units list a shot from 75 steps on, tanks at once | `docs/T7_DESIGN.md` |
| B-4 | A stop issued to a unit waiting in front of a full hex is echoed without error, sets `flag_force_stop` to 1 one step later, withdraws every listed action (even another stop) and keeps the move path for the rest of the game (4 of 4 units, 1,269 steps) | `docs/PS1_ENGINE_PROBE.md` |
| B-5 | A stop on a traversing unit has never been issued in this project: its engine behaviour is unknown | `docs/T7_DESIGN.md`, `docs/PS1_ENGINE_PROBE.md` |
| B-6 | `speed` above 0 does not exclude a unit whose next hex fills before it arrives | `docs/T7_DESIGN.md` |
| B-7 | A unit entering a hex in front of a full hex waits at once (103 of 103); a restart takes a hex time counting the restart step (113 of 113) | `docs/PS1_ENGINE_PROBE.md` |
| B-8 | `baseline-v2` engages before it occupies or moves: a unit with a listed shot fires rather than moves | `decision/policy.py` |

### 3.3 Structure probe (field presence and listing shapes; no trigger evaluated)

Before this section was written, one private probe (`local/diagnostics/s32/structure_probe.py`, log kept beside it)
read the own ground unit-decisions of the play stage of Sprint 23's populations (H0 both seats, HH, HI) and counted
field types and listing shapes only:

| Fact | H0 | HH | HI |
|---|---:|---:|---:|
| unit-decisions with `A1` 0 and no tank main gun (weapon 36 or 37) | 289,697 | 218,699 | 146,880 |
| unit-decisions with `A1` 1 and a tank main gun | 33,591 | 16,890 | 43,200 |
| unit-decisions with `A1` 0 and a tank main gun, or `A1` 1 without one | 0 | 0 | 0 |
| traversing (path, `speed` above 0) with `A1` 0: a shot listed | 0 of 136,771 | 0 of 91,033 | 0 of 53,987 |
| traversing with `A1` 1: a shot listed | 126 of 22,961 | 86 of 8,547 | 13 of 11,805 |
| traversing units listing action 10 | 159,732 of 159,732 | 99,580 of 99,580 | 65,792 of 65,792 |
| action 10 listings whose value is `None` (no parameter) | 174,360 of 174,360 | 134,765 of 134,765 | 97,666 of 97,666 |
| traversing units with `cur_pos` in [0, 1) | 159,732 of 159,732 | 99,580 of 99,580 | 65,792 of 65,792 |
| ids in `see_enemy_bop_ids` that are enemy operators of the seat's view | 654,483 of 654,483 | 984,914 of 984,914 | 77,592 of 77,592 |
| unit-decisions whose listed shot targets are all in the unit's `see_enemy_bop_ids` | 345 of 345 | 211 of 211 | 23 of 23 |

So, on the records: `A1` and the tank main guns agree exactly; a non-tank unit never lists a shot while it traverses;
the stop is always listed parameterless; the per-unit visibility list is well formed and contains every listed shot
target. A separate field probe (`local/diagnostics/s32/field_probe.py`, one H0 game) saw traversing `speed` values of
1/20, 1/40, 1/60 and 1/144 hexes per step and, one step after a move began, `cur_pos` equal to `speed`. Reading `cur_pos`
as the documented progress fraction, the steps a traversing unit needs to complete its current hex are
`ceil((1 - cur_pos) / speed)`, a seat-observable number; that reading is DOCUMENTED and consistent with the probe, and
the mechanism check measures it (section 8).

### 3.4 Data inventory (file metadata only)

Genuine full-step `baseline-v2` seat observations exist for: the four Sprint 12 head-to-head games in 2130511121 (HH),
two later head-to-head games in 2130511121 (sessions 2797 and 2800, the `baseline-v2` seat; HX), and three games against
the inert control (2120531121 C3, 1930331196 C3, 1930331196 C2; HI). **No full-step observation exists of a
2130511121 game against the inert control, in either seat**: the owner's two tentative configurations have only game
records (the registered shoot-reservation experiment's fifteen games per configuration: scores and action counts, no
positions). The preflight therefore reports their status from records as they are (section 4) and cannot count their
triggers.

### 3.5 Event taxonomy for a stop order (definitions; the windows are fixed with the mechanism check)

For a stop submitted at a decision with step `s0` to a unit whose current-hex completion needs `h0 =
ceil((1 - cur_pos) / speed)` steps (read at `s0`):

| Id | Event | Observable |
|---|---|---|
| A | rejected | the engine's feedback for the order carries an error code |
| B | accepted but deferred | `flag_force_stop` 1 with a non-empty path at a later observation (B-4's signature) |
| C | takes effect after entering the next hex | the path empties with `cur_hex` equal to the path's first hex at `s0` |
| C' | takes effect in place | the path empties with `cur_hex` unchanged |
| D | remaining path cleared | `move_path` empty |
| E | transition begins | `move_to_stop_remain_time` positive, `stop` 0 |
| F | transition completes | `stop` 1, timer 0 |
| G | a legal shot becomes available | action 2 listed for the unit |
| H | a shot is emitted and accepted | the composite policy emits action 2 for the unit; its feedback has no error code and a direct-fire judgement names the unit as attacker |
| I | blocked or unable to resume | after F, action 1 not listed again, or every listed action withdrawn, or the unit waiting with a path for the rest of the game |

The documented sequence is C, D, E, F (then G when a target is still observed in range). Deadline arithmetic starts from
the hex completion, not from the order: the path must clear by `s0 + h0` plus a tolerance, and the transition must end
75 steps after the path cleared, plus a tolerance; both tolerances are fixed in the mechanism check (section 8).
Indefinite deferral (B), a path that never clears, and the loss of every listed action are separate adverse outcomes.

## 4. The candidate: `t7-b1-stop-engage-1`

`src/miaosuan_agent/experiments/t7_b1_stop_engage.py`, an add-on on `experiments/exploratory_addon.py`.
`baseline-v2` decides first, unchanged; the add-on appends at most one stop (action 10) per unit, only to units that
`baseline-v2` leaves without an action, after `baseline-v2`'s actions and in ascending unit id; it removes, replaces or
reorders nothing and constructs no other action. Trigger levels, in order (the first failing level is recorded; any
missing, non-numeric or ambiguous field fails closed):

| Level | Passes when |
|---|---|
| A ground, controllable | an operator of the seat's colour, type 1 or 2, listed among the seat's operators in `role_and_grouping_info` |
| B no move-and-fire | `A1` is the integer 0 and no carried weapon is 36 or 37 (tank main guns are excluded) |
| C traversing | a non-empty path of integer hexes, `speed` above 0 (a unit waiting in front of a full hex is excluded), `cur_pos` in [0, 1), an integer `cur_hex` |
| D stop listed | action 10 listed with the value `None`; the order is copied as the documented key set `actor`, `obj_id`, `type` and nothing else |
| E no other state | `stop`, `move_to_stop_remain_time`, `flag_force_stop`, `change_state_remain_time`, `get_on_remain_time`, `get_off_remain_time`, `weapon_unfold_time`, `keep`, `move_state` and `on_board` all numbers equal to 0, `weapon_unfold_state` 1 |
| F route continues | at least two hexes of path (a stop on the last hex drops nothing) |
| G no `baseline-v2` action | `baseline-v2` emits nothing for the unit |
| H not stopped before | the candidate has not stopped this unit earlier in the game (one stop per unit per game: no repeated stop to a pending transition) |
| I target in range | an enemy ground unit in the unit's own `see_enemy_bop_ids` within the published direct-fire range of one of its weapons against that target class, measured from the path's first hex (where the documented stop takes effect) |
| J next-hex room | at most 2 other own ground units stand on the path's first hex, have it in their path, or receive a `baseline-v2` MOVE through it at this decision: the unit cannot be left waiting in front of a full hex by movement already planned (B-6, B-7), and a stopped unit leaves room for one unit passing through |
| K time left | `cur_step + h0 + 75 + 3 <= max_step` (two steps of tolerance and one decision in which to fire) |

Memory: `baseline-v2`'s memory plus the step of each unit's stop. The candidate checks its own edit (action 10 is not in
the project gate's catalogue): `baseline-v2`'s actions first and unchanged, every added action a listed parameterless
stop of this seat with the exact key set, no unit with two actions; any failure or error falls back to `baseline-v2`'s
decision with the error in the trace. Deterministic, seat-local, no randomness, clock or other view. Its change
records keep, per stop, the target, distance, range, stop hex, the count of other units at that hex and `h0` (private,
in the ignored capture folders only).

## 5. Historical feasibility preflight (frozen before it runs)

`scripts/s32_preflight.py` (`freeze`, then `run`) with `src/miaosuan_agent/evaluation/s32_preflight.py`; inputs pinned
in `evaluation/s32-t7-b1/preflight-inputs.json`: Sprint 23's committed jobs and their pins (H0, HH, HI), the two HX jobs
(record and full-step timeline by SHA-256), every source digest and the fifteen group C records of five inert
configurations (2130511121 C2 and C3, 2120531121 C3, 1930331196 C2 and C3).

* **Reading.** Sprint 23's loader and `baseline-v2` reconstruction, unchanged (an HX job goes through its HH timeline
  branch). Fidelity anchors: H0 33,696 decisions, 33,680 play decisions, 123 differences from the recorded `baseline-v0`;
  HH 11,524, HI 8,643 and HX 5,762 decisions, every one equal to the recorded seat; 16, 4, 3 and 2 side-games.
* **Rule replay.** At every play decision the candidate's rule runs on the seat observation and `baseline-v2`'s actions
  twice: with its own memory chained through the side (its stops) and with an empty memory (its eligible units).
* **Measures, per side and per population, never pooled across populations**: unit-decisions by first failing level
  (including waiting units with a path, which level C excludes), eligible unit-decisions, opportunity episodes (a maximal
  run of consecutive play decisions at which one unit is eligible: repeated observations of one unit are one
  opportunity) and distinct units, the stops, and per stop the unit and target classes, the weapon that reaches, the
  distance, `h0`, the hexes of path left and the steps left before the end.
* **First divergence.** A side's first stop: a valid first-divergence fact in HH, HX and HI, and in H0 only when the
  recorded actions equal `baseline-v2`'s at every earlier decision of that seat. Every later stop lies on recorded states
  an engine game with the candidate would not reach (off-policy) and is reported apart.
* **Recorded-trajectory descriptions** (descriptive; what happened without a stop, never an effect of one), over the
  window `h0 + 75 + 3` from the stop: the target stayed in the seat's view within range of the stop hex throughout
  (Sprint 5's B1 witness); the unit was lost or damaged; a shot was listed for it on the record; its path ended at an
  objective its side did not hold, and the side first owned that objective inside the window (a possible conflict with
  objective capture).
* **Independent check.** At every play decision a restatement of the trigger written apart from the candidate's code
  (the T7 study's range table and distance, its own field reading) must select exactly the candidate's stops and its
  eligible units. Any disagreement invalidates the preflight.
* **Record-level description** of the five inert configurations (descriptive): per configuration the `baseline-v2`
  seat's shots and moves per game, the games with a shot and the step of the first shot, occupy and margin. A shot shows
  that some own unit had an enemy in view and in range at some step; it does not show that a moving non-tank unit did.
* **Configuration status**, for each proposed configuration (2130511121 C2 with `baseline-v2` red, 2130511121 C3 with
  `baseline-v2` blue) and each HI configuration: `VERIFIED` (a genuine full-step record with a valid first divergence
  and no independent-check finding), `NO_OPPORTUNITY` (such records without one), `NO_FULL_STEP_RECORD`.
* **Stop, first match**: `S32_PREFLIGHT_INVALID` (an anchor, an integrity check or the independent check fails);
  `S32_PREFLIGHT_PASS` (both proposed configurations `VERIFIED`); `S32_PREFLIGHT_PROPOSED_UNVERIFIED` (a proposed
  configuration is not verified, but verified inert configurations exist for both a red and a blue `baseline-v2` seat:
  the proposal names them as the alternative and the owner chooses); `S32_PREFLIGHT_INADEQUATE` (otherwise: no live test
  is proposed).
* The HH and HX counts are the ones that bear on a later head-to-head use and are reported in full; they do not enter
  the stop rule, which concerns the inert mechanism check only.
* Tests before the run: `tests/test_t7_b1_stop_engage.py` (every level at its boundaries, the order's key set, the
  memory, the own check, permutation determinism, the fail-closed wrapper, the real `baseline-v2` on a synthetic
  observation, the weapon table equal to the T7 study's, the import closure) and `tests/test_s32_preflight.py` (the
  restatement against the candidate on 3,000 random states and against planted defects, episodes, the validity rule, the
  descriptions, every disposition branch, the sanitised public form).
* Mutation (`scripts/mutate_s32.py --phase preflight`, record `evaluation/s32-t7-b1/mutation-preflight.json`): the first
  run caught 34 of 38 planted defects. Three survivors were one test gap (the tests looped over the module's own list of
  zero-valued fields, so a field dropped from that list was dropped from the test as well; the tests now name the ten
  fields themselves) and one mutation was equivalent (admitting aircraft as targets changes nothing, because no aircraft
  range is published) and was replaced by admitting own units as targets. The final run caught 38 of 38.
