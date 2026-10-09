# Sprint 28: T12-O1 objective-zone dispersion offline qualification

**REGISTERED — OFFLINE — NO ENGINE SESSION — TRIGGER, LEGAL-ACTION AND ONWARD-MOVEMENT QUALIFICATION, NOT EVIDENCE THAT DISPERSION WORKS — NOTHING PROMOTED**

On 2026-10-09 the owner accepted Sprint 27's registered result `T6S_P1_MECHANISM_NOT_SUPPORTED`, closed the T6-S
stagger increment without repair, and approved the next eligible increment of Sprint 24's frozen ranking: **T12-O1,
objective-zone dispersion**. This sprint is offline. It asks whether the frozen T12 trigger occurs on the recorded
`baseline-v2` trajectories, whether the proposed one-hex relocations can be specified as legal MOVEs from the current
`valid_actions` and the documented movement contract, and how the dispersed units would interact with `baseline-v2`'s
onward movement. No engine session is authorized and session 2798 is not opened; no executable candidate, run card or
promotion follows from this sprint. The same day the owner set a standing CPU policy for the shared evaluation server
(section 2). Dates are business dates in UTC+8.

Sections 1 to 24, the code they name, the frozen `protocol.json` and `inputs.json`, the tests and the mutation record
are committed and pushed before the target analysis is run. Results follow in a separate section; no registered section
is edited afterwards.

## 1. Starting state and the owner's decisions

| Item | Identity |
|---|---|
| Repository | `main` `f7bdd72a0dfb4fce4711a99da9ee6e879d9f5a7f`, tree `b45252c073696ffe89bbeeeaa06c217ef462c2ac`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | read-only verify at the start of the sprint: 2,797 sessions opened and closed, none unclosed, state chain continuous, the last event the close of session 2797; ledger file SHA-256 `70ae38f21e0ac2c0d9c2772a8fe73b5b3a6dbdcc8f4e62af8dbc4443d4df8036`; session 2798 not authorized |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Privacy baseline | the 106 accepted hit lines of `local/diagnostics/s25/privacy-baseline-106.txt`, compared exactly |

The historical dispositions stand unchanged and are not repaired by renaming: T6-S `T6S_P1_MECHANISM_NOT_SUPPORTED`
(Sprint 27: only session 2797 ran, session 2798 did not open, P1 triggered with the candidate's blue E4 9,708 against
the frozen limit 9,592.5, P2 did not trigger, no policy promoted; the post-hoc observation that 6,523 of the 9,708 E4
unit-decisions fell outside every stagger-episode window rescues nothing and defines no candidate); T6-G closed; T9
SHELVED; T13-D1 `T13_D1_NOT_READY`, closed; T2-X1 SHELVED; T2-P1 `T2_P1_MECHANISM_SUPPORTED`; every earlier
disposition. T12 is an independent hypothesis: it is not a T13 garrison repair, not T9 claimant allocation, not
objective reassignment, not a remedy for the PS-1 deadlocks and not a route planner.

## 2. The shared-server CPU policy and this sprint's allocation

The owner's standing policy is recorded in `docs/SERVER_RESOURCE_POLICY.md` (and in the README's constraints). The
inspection at the start of this sprint (2026-10-09) found: two sockets of 16 physical cores with two SMT threads each,
**32 physical cores and 64 logical CPUs**; logical CPUs `i` and `i + 32` are the two threads of one core; NUMA node 0
is logical CPUs 0-15 and 32-47 and NUMA node 1 is 16-31 and 48-63; the login session's affinity and cpuset are 0-63,
and only the memory and pids cgroup controllers are enabled below the root, so a job is isolated by its CPU affinity
alone; CPU, memory and I/O pressure were zero; both people use the same Unix account. A colleague's job was running,
pinned to NUMA node 1, so the server was in **shared mode** and this project's half is NUMA node 0 (16 physical cores,
32 logical CPUs; `taskset -c 0-15,32-47`). The split 0-31 / 32-63 would have given both people one thread of every
core.

This study's work is inherently serial: Sprint 18's census loader reads one game at a time and the analysis is a pure
function of its frames. The structure probe, the smoke run and the target run are therefore one process each, pinned
to node 0; the private test suite runs serially as in every earlier sprint, also pinned to node 0. No engine runs, so
no worker count applies. The mutation runs execute on the workstation.

## 3. Scope, the evidence boundary and disclosure

* Offline only: no engine session, no executable candidate, no run card, no change to `baseline-v2`, the stable core,
  the evaluators, the engine installation or configuration, or any historical output.
* Two populations of different evidence strength, never conflated. **H0** is the 8 replay-corpus games (16
  scenario-sides): the recorded actions are `baseline-v0`'s and `baseline-v2`'s decisions are reconstructed on those
  states. **HH** is the 4 Sprint 12 head-to-head timelines in 2130511121, analysed on the genuine `baseline-v2` seats
  (two openings, each played twice). Both are read through Sprint 18's census loader, unchanged.
* Never used: BOKE-2026, the stopped 360-game prevalence corpus, Sprint 18's HI, S and R populations, any newly opened
  engine session, any unregistered scenario.
* **Disclosure.** Before writing this registration the author read the documents and public files named in the owner's
  brief, the code of Sprints 18, 25, 26 and 27, the project's movement contract (`docs/CONTRACT.md`,
  `decision/gate.py`, `decision/routing.py`, `decision/candidates.py`) and the public rules snapshot
  (`local/source-archives/docs-live-snapshot-20260929`). One structure probe ran on the private inputs
  (`local/diagnostics/s28/structure_probe.py`); it printed no objective, holder, idle, trigger or dispersion figure,
  only these facts: (1) the raw fields `stop`, `move_to_stop_remain_time`, `can_to_move`, `flag_force_stop`,
  `change_state_remain_time`, `get_on_remain_time`, `get_off_remain_time`, `keep` and `weapon_unfold_time` are present on
  every one of the 765,831 own ground unit-decisions of H0 and HH; `flag_force_stop`, `change_state_remain_time`,
  `get_on_remain_time`, `get_off_remain_time` and `weapon_unfold_time` are always 0 there; (2) a unit that is not moving
  in Sprint 18's sense has `stop` 0 in 11,248 unit-decisions, exactly as many as carry a positive
  `move_to_stop_remain_time` (the stop transition), and `stop` 1 in 344,433; (3) only the 201033019601 games carry
  roadblocks (50 hexes), the other H0 games and HH none; (4) action type 1 is always listed with the value `None`; (5)
  in the eight scenario cost graphs every edge of modes 0, 1 and 2 joins two hexes at distance 1, and the infantry
  graph (mode 2) contains every in-map neighbour of every hex, while the vehicle graph lacks 2,436 of the 334,640
  in-map neighbour pairs and the march graph most of them. Probe (2) placed the stop transition in idle level C
  (section 7); probe (5) means the trigger's passability (section 8) never removes a neighbour, which the
  registration states rather than hides. A smoke run of
  the full pipeline with a trigger that cannot fire (section 23) checked the fidelity anchors and printed no T12 figure.
  The author also knew Sprint 24's opportunity figures (40 and 10 ground damage events on stationary stacked units on
  objectives) and Sprint 24's warning that `baseline-v2` moves a vehicle on from a held objective at once in most corpus
  arrivals (107 of 155).

## 4. The frozen hypothesis

Sprint 24's registered entry (`evaluation/s24-tactical-frontier-reselection/experiments.json`, `T12`), pinned by digest
in `inputs.json`, is the hypothesis this sprint qualifies; nothing in it is changed:

* hypothesis: "moving all but one stacked holder of a held objective to free adjacent hexes keeps the objective denied
  and removes the stacked-target correction";
* trigger: "a held objective with two or more idle own ground units on its hex and a passable adjacent hex with fewer
  than four own ground units";
* action change: "a one-hex move for each extra unit; baseline-v2's later moves for dispersed units withheld while the
  objective is held";
* offline stop: "fewer than one trigger per side-game".

The engine benefit and the legality of the full tactic are unverified. No executable T12 candidate is built in this
sprint.

## 5. Populations and inputs

`evaluation/s28-t12-o1/inputs.json` copies Sprint 18's committed H0 and HH pins and pins Sprint 18's `inputs.json`,
`census.json` and `admission.json` and Sprint 24's `experiments.json`; `protocol.json` pins the normalised SHA-256 of
every source the study depends on (the dispersion shadow, the analysis, the driver, Sprint 18's census module, loader
and admission script, the hex distance, the safety gate, the router, the terrain contract, the objective labels and the
sanitizer). `scripts/s28_t12.py run` refuses unless every pin matches. H0's recorded actions are read in a separate pass
of the same pinned files and aligned with Sprint 18's frames by decision; the pass must reproduce Sprint 18's 123
decisions where they differ from `baseline-v2`'s. The raw transition fields of section 7 and the roadblock hexes are
captured through the census loader's frame hook; nothing else of the loader changes.

## 6. Objectives, geometry and the published rules

* **Objective**: a `cities` entry of the seat's observation with an integer hex; the side **holds** it when its flag
  equals the side's colour. Its **centre** is its hex.
* **Neighbours**: the hexes at distance 1 (`evaluation/t7_visibility.hex_distance`, the project's cube-coordinate
  distance over four-digit hexes with odd rows shifted) inside the map; at most six. The function reproduces the example
  of the platform documentation (`Map.get_neighbors`: the neighbours of 0739 are 0740, 0640, 0639, 0738, 0839 and 0840).
* **Own ground unit**: a unit of the seat's own `operators` of type 1 or 2 with an integer hex, artillery included;
  passengers are not operators; aircraft and type 4 are not ground units. Opposing units are the visible enemy
  operators.
* **Published rules** (`rules_rules.txt` of the snapshot), quoted verbatim:
  * stacking: "在同一个六角格内，不可堆叠超过4个本方地面单位。如果六角格内已存在4个本方地面单位，则格外本方地面单位不能再进入或通过该六角格。" (at
    most four own ground units per hex; a full hex can be neither entered nor crossed by another own ground unit);
  * capture: "棋子只要机动（或行军）到夺控点中心，并且夺控点所在格及与其相临的6个六角格内无敌方地面单位，即可执行夺控命令。" (a unit on the
    objective's centre may capture it when the centre and its six neighbours hold no enemy ground unit), and
    "空中单位和炮兵不能执行夺控命令。" (aircraft and artillery cannot capture);
  * the stacked-target correction: "目标单位处于堆叠状态、行军状态，战果作有利修正。" (a stacked or marching target
    gives the shooter a favourable correction).

By the published capture rule an enemy can capture a held objective only when the centre and all six neighbours are
free of the side's ground units. T12 keeps one holder on the centre, so the published rule alone already denies capture
while the holder lives; whether own units on neighbours deny capture after the centre empties is **not** known from any
engine test (section 19, R5), and no claim that off-centre denial works is made.

## 7. Idle, frozen before the census

An own ground unit on a held objective's centre is **idle** when it passes every level below, checked in this order
(`experiments/t12_dispersion_shadow.IDLE_LEVELS`); the first failing level is recorded, and each level's count is
reported as a nested count so that no level silently changes the meaning of "idle":

* **A, physically stationary**: `speed` not positive;
* **B, no ongoing movement path**: empty observed `move_path`;
* **C, no stop or movement transition**: the engine's `stop` flag not 0, and `move_to_stop_remain_time` and
  `change_state_remain_time` not positive;
* **D, no embark or disembark transition**: `get_on_remain_time` and `get_off_remain_time` not positive;
* **E, not suppressed**: `keep` false (the rules forbid suppressed infantry to move);
* **F, no MOVE from `baseline-v2`**: `baseline-v2`'s list at this decision holds no MOVE of the unit;
* **G, no other `baseline-v2` action**: `baseline-v2`'s list holds no action of any type for the unit (the safety
  gate admits one action per unit per step, so any action is incompatible with a dispersion MOVE; this also excludes a
  unit with a combat action).

A missing field counts as the absence of a transition. A stationary unit that `baseline-v2` orders onward fails F and
is not idle; a moving unit fails A or B and never counts as a new trigger. Being otherwise legally blocked is the
legality question of section 9, reported per unit and neighbour.

## 8. The trigger (theoretical tier)

At a play decision (stage 2), for each objective the side holds, in increasing hex order: at least **two** idle own
ground units stand on its centre, none under an active hold of this rule (section 11), and at least one neighbour is
**passable** (a traversable cost-graph neighbour of the centre in at least one ground mode: vehicle, vehicle march or
infantry) and holds **fewer than four** own ground units. This is Sprint 24's trigger read exactly. By structure probe
(5) the infantry graph is complete, so passability removes no neighbour on these maps; the theoretical tier is decided
by the idle units and the stacking count. Units are counted standing on hexes; passengers in carriers are not counted.

## 9. Legal one-hex MOVE (legal tier)

The documented movement contract (`docs/CONTRACT.md`, `decision/semantics.py`, `decision/gate.py`): `valid_actions`
lists action type 1 for a movable unit with the value `None` and does not enumerate routes; the agent constructs the
`move_path` from the setup cost graph; the project's safety gate accepts a constructed path when the unit is not
executing a move, has a documented movement mode, and every hex is a traversable neighbour of the previous one in the
unit's cost mode, never the start hex, never a roadblock for the vehicle modes. A one-hex relocation is therefore a
constructed path of exactly one neighbour, and it is **legally supported** for an idle unit and a neighbour when, first
failing reason recorded (`LEGAL_REASONS`): action type 1 is listed for the unit at this decision (`move_not_listed`);
`decision/routing.move_mode` gives a mode (`no_movement_mode`); the gate's own path check
(`decision/gate._path_problem`, called unchanged) accepts `[neighbour]` from the centre in that mode with the game's
roadblocks (`gate_path_refused`); the neighbour holds fewer than four own ground units (`stack_full`). No MOVE parameter
beyond the documented `move_path` is used. Engine execution of these MOVEs is **not** tested in this sprint.

Every theoretical trigger is reported with and without this construction: theoretical adjacency (section 8) and legal
support are separate counts.

## 10. The holder and the local batch

A legally supported neighbour is **admissible** under the local rule unless (first match, `ADMISSIBLE_REASONS`) it is an
objective hex (a dispersed unit must not capture), holds a visible enemy operator (no close combat), or lies on an own
route: a hex of any own unit's observed `move_path` or of any `baseline-v2` MOVE route at this decision (no dispersed
unit may stand on, or fill, a hex an own unit is about to cross).

**Batch**, per triggered objective in increasing hex order, with one occupancy count shared by all objectives at the
decision:

1. the idle centre units are ordered by (number of admissible destinations, unit id);
2. the first is the **holder**: it is never moved by this rule (a unit with no admissible destination is preferred, so
   the rule does not strand a mobile unit on the centre while moving the only holder that could stay anyway);
3. each other unit, in that order, takes the admissible destination with the fewest own ground units after the moves
   already assigned at this decision, then the lowest entry cost in its mode, then the lowest hex, while the count stays
   within four; with none left it stays (`no_destination_left`, a same-step occupancy conflict); with no admissible
   destination at all it stays (`no_admissible_destination`).

The **legal tier** holds when the batch disperses at least one unit; a **complete** batch disperses every idle unit
but the holder. The rule is local: no cross-objective reassignment, no slot reservation for the future, no traffic
manager. Same-step conflicts are reported (section 15), not repaired.

## 11. The non-executable shadow

`src/miaosuan_agent/experiments/t12_dispersion_shadow.py`, identity `t12-o1-dispersion-shadow`, status **ANALYSIS
SHADOW — NON-EXECUTABLE** (`EXECUTABLE = False`): no agent class, not in `decision.policy.POLICIES`, in no run card,
named only by this sprint's analysis, driver, mutation script and tests. At a decision it keeps `baseline-v2`'s actions
unchanged and in order, removes the MOVEs of units under a hold, and appends one action `{"actor", "obj_id", "type": 1,
"move_path": [destination]}` per dispersed unit. Each dispersed unit enters a **hold** (unit, objective, destination,
start step): every later `baseline-v2` MOVE of the unit is withheld until the objective is no longer held or the unit is
absent (`RELEASE_REASONS`), the frozen reading of "withheld while the objective is held". A held unit is neither an idle
holder nor a dispersal candidate. The holder is not held by this rule.

## 12. Onward movement and the cost of the hold

For every legal episode, on the recorded trajectory after its start (historical cost indicators, never online inputs
and never causal estimates), until the origin objective stops being held (the hold's release; to the end otherwise):

* for each dispersed unit: whether `baseline-v2` emits a MOVE for it and when (steps from the start); that MOVE's
  destination as an objective held, an objective not held, or not an objective; **claimant**: the destination is an
  objective the side does not hold, issued while the origin is held (the hold would withhold an onward capture order,
  Sprint 23's claimant measure); **first owner**: the side's first-ever play-stage ownership of that destination comes
  after the order and the unit stands on it at that decision; whether other own units were first owners; whether the
  destination had been first owned before the order or was never owned; the number of decisions with a `baseline-v2`
  MOVE for the unit while the origin is held (the decisions a hold would suppress); whether the unit is later lost;
* for the episode: whether the hold would last to the end of the recorded game, the steps to its release, and whether
  `baseline-v2` orders the **holder** off the centre while the origin is held (the centre would empty while dispersed
  units are withheld).

A different unit capturing the next objective later is not read as "no cost".

## 13. Historical damage diagnostics

For every damage event on a stationary own ground unit standing on an objective hex (Sprint 18's event rows; the
population of Sprint 18's admission table, 40 + 13 in H0 and 10 + 3 in HH, stacked and alone): the victim's class,
stacked or alone, whether the objective was held at the event, whether the attacker was visible at the event and seen
within Sprint 18's lookback window before it, whether the victim was later lost, whether the trigger and whether the
legal tier held at that objective at an earlier decision of the same holding run, the steps since the latest such legal
decision, and whether it was the side's first divergence. For every legal episode: damage events on its idle centre
units within 300 steps before and after its start. No damage reduction is estimated: the direct-fire kill probability
is unidentified (Sprint 21), and a less stacked formation is not necessarily safer.

## 14. Fidelity first

The run reproduces, before any T12 conclusion: H0 33,696 decisions and 33,680 play decisions; 123 decisions where
reconstructed `baseline-v2` differs from the recorded `baseline-v0` (also by the separate recorded-action pass); HH
11,524 reconstructed `baseline-v2` decisions equal to the recorded seat; 16 and 4 side-games; `baseline-v2`'s 509 and
416 MOVE orders; Sprint 18's admission counts of ground damage events on stationary units on an objective, 40 stacked
and 13 alone in H0 and 10 and 3 in HH, both from the census rows and by this study's own enumeration; 10 H0 side-games
with a stationary stacked hit on an objective; Sprint 18's T6, N4 (objective losses), N5 (idle ground unit-decisions in
Sprint 18's sense) and N6 (first ownership) blocks and the admission table equal to the committed files. Each side also
passes its integrity checks: frame positions equal decision indices; one recorded list and one extras map per decision;
one roadblock set per game; one seat id in the side's actions; the first divergence is the first legal-tier decision;
before it the candidate equals `baseline-v2` and the stateful and stateless evaluations agree there; withheld actions are
MOVEs; every legal episode lies inside a trigger episode; no unit stands on two centres; every legal batch keeps a
holder. Any unexplained discrepancy makes the study `T12_O1_OFFLINE_INVALID`; no definition is changed to fit.

## 15. The opportunity census

Per side-game (`sides.json`), per population and pooled (`census.json`): held objectives; held objective-decisions;
objective-decisions with two or more own ground units on the centre; with two or more passing each idle level in turn
(A, then A and B, ..., then all of A to G = two or more idle); with two or more idle but no passable neighbour with
room; the trigger; the trigger with a legally supported one-hex MOVE for some idle unit; with an admissible destination;
the legal tier; the complete legal tier; idle and legal unit-decisions; the first failing idle level of every centre
unit; the legal and admissibility reasons over unit-neighbour pairs; the batch outcomes; the centre's and the neighbours' own ground counts
at trigger decisions; decisions at which two triggered objectives share a neighbour; triggers with a visible enemy on a
neighbour. These are decision-level counts: a group listed again at the next decision is counted again here and never
as a new episode.

## 16. Episodes and distinct counting

An **episode** is a maximal run of consecutive play decisions at which one objective meets a tier (trigger or legal);
the decisions after the first are repeated listings and are reported as such. Counts are given as raw unit-decisions,
episodes, distinct groups (objective and idle units at the start), distinct objectives, distinct dispersed units, games,
side-games and scenario-sides. **Distinct episodes** across replica games: the same scenario-side, objective, start step
and idle centre units count once (HH plays each opening twice).

## 17. First divergence

The shadow runs on every recorded decision of each side from an empty memory. The **first divergence** is the first
decision at which the candidate's list differs from `baseline-v2`'s; it is necessarily the first legal-tier decision (an
integrity check). At it, a public certificate records whether the objective is held, the number of idle centre units,
whether a holder stays on the centre, the number of dispersed units and of distinct and previously empty destinations,
whether the only added actions are the registered one-hex MOVEs, whether every `baseline-v2` action is preserved in
order, and whether `baseline-v2` gave the dispersed units no action. In HH the recorded prefix is the `baseline-v2`
seat's own trajectory, so the first divergence is a valid on-policy fact; in H0 it is valid only if the recorded
`baseline-v0` actions equal `baseline-v2`'s at every earlier decision of that seat (Sprint 23's boundary), otherwise it is
descriptive. After the first divergence the recorded states are off-policy: later episodes are historical opportunity,
holds replayed after it are synthetic, and no historical outcome after it is presented as a result of T12.

**Independent check.** At every play decision an independent restatement from the frame's fields
(`evaluation/s28_t12.IndependentCheck`) verifies the candidate: `baseline-v2`'s list with some MOVEs removed, then
appended actions; each removal a MOVE of a unit it accepted as dispersed earlier while that objective is still held and
the unit present; each appended action the exact registered MOVE of an idle own ground unit on a held centre with at
least two such idle units, MOVE listed, one neighbour at distance 1 inside the map, traversable in the unit's mode, not a
roadblock for a vehicle, not an objective, without a visible enemy, on no own route, the stacking count kept within four
including this decision's appended moves, and an idle holder left on the centre. Zero unexplained differences are
required.

## 18. The registered opportunity stop

Sprint 24's wording is "fewer than one trigger per side-game". Frozen reading, fixed before the census:

* **Primary (decides the disposition)**: met when any of the four HH side-games has fewer than one trigger episode
  (section 16, theoretical tier, the frozen idle definition), or when the four HH side-games are not all present. The
  first trigger episode of an HH side-game starts at or before its first divergence (a divergence needs a trigger), where
  the candidate still equals `baseline-v2` on the recorded seat's own trajectory, so the primary stop is decided by
  on-policy evidence.
* **H0 (reported only)**: the same count for each of the 16 H0 side-games, under two readings of the wording: the
  each-side-game reading (met when any H0 side-game has none) and the average reading (met when the H0 trigger episodes
  are fewer than the H0 side-games). Neither enters the disposition; H0's trajectories are `baseline-v0`'s.

A merely theoretical adjacent hex is a trigger, not an actionable candidate episode: **actionable** means the legal tier
(section 9 and 10). The brief's disposition `T12_O1_LEGALITY_UNRESOLVED` presupposes that the opportunity stop can pass
while legality fails, which is possible only if the stop counts trigger episodes; legality is therefore its own gate
(section 20). The stop is not reinterpreted after the counts are seen.

## 19. Readiness risks, classified before the census

Recorded whatever the disposition, independently of the opportunity stop (`disposition.json`, `readiness_risks` and
`interaction`):

* **R1, stationary stacks without a dispersal**: objective-decisions with two or more physically stationary (level A)
  centre units, how many reach the legal tier, and why the others do not (fewer than two idle, with the failing level of
  each stationary unit; no passable neighbour with room; a trigger without a dispersed unit).
* **R2, the holder**: the selection is deterministic by construction; holder departures under `baseline-v2` are
  criterion I2.
* **R3, same-step occupancy conflicts**: unit-decisions with `no_destination_left`.
* **R4, onward moves against an indefinite hold**: criterion I1 and the first-owner counts.
* **R5, adjacency denial**: unresolved offline by construction; the published capture rule has never been tested with
  a held objective whose centre is empty while own units stand next to it.
* **R6, H0 prefixes**: H0 first divergences with and without prefix support.

**Interaction criteria** (section 20), each over the distinct legal episodes (the first replica of each key), evaluated
separately in HH, in H0 and pooled, and met when met in any of the three with a non-empty denominator; "a majority"
means strictly more than one half, the convention Sprints 23, 25 and 26 registered for their interaction stops, fixed
here before any count is seen:

* **I1, tactical isolation**: a majority of the dispersed units are claimants (section 12): the units T12 would move
  are mostly units `baseline-v2` would send to capture other objectives while the origin is held;
* **I2, holder ordered off**: in a majority of the episodes `baseline-v2` orders the holder off the centre while the
  origin is held, so the hold would routinely rely on the untested off-centre denial (R5);
* **I3, partial dispersion**: in a majority of the episodes an idle unit other than the holder stays for lack of an
  admissible destination or of room, so the local rule leaves the stack in place.

## 20. Dispositions, first match

* `T12_O1_OFFLINE_INVALID`: an input or source pin fails (the run refuses), a fidelity anchor or block fails, a side's
  integrity check fails, any unexplained action difference, or the public sanitizer refuses a result file (then only
  `disposition.json` is written, with this disposition and no other result).
* `T12_O1_INADEQUATE_OPPORTUNITY`: the opportunity stop (section 18) is met.
* `T12_O1_LEGALITY_UNRESOLVED`: the stop is not met, but some HH side-game has no legal-tier episode (the one-hex MOVE
  cannot be specified from the listed actions and the documented rules where the trigger holds).
* `T12_O1_INTERACTION_NOT_READY`: legality holds in every HH side-game, but any of I1, I2 or I3 is met.
* `T12_O1_READY_FOR_MECHANISM_PROPOSAL`: otherwise.

Nothing is promoted under any disposition, and no engine use follows automatically from any of them.

## 21. Outputs, privacy and checks

* Public, `evaluation/s28-t12-o1/`: `protocol.json` and `inputs.json` (this registration), `mutation.json`, then
  `fidelity.json`, `sides.json` (one summary per side-game), `census.json` (per population and pooled),
  `divergence.json` (certificates), `episodes-H0.json` and `episodes-HH.json` (one sanitised row per legal episode),
  `damage.json` (the summary and one row per section 13 event) and `disposition.json` (the stop, the H0 readings, the
  legality gate, the interaction criteria, the risks and the disposition). A table over 90,000 bytes is split in order
  into numbered parts. Aggregates, steps,
  counts, classes and Sprint 11's objective value labels only; no unit identifier, hex, route or coordinate. Every file
  passes the project sanitizer (forbidden keys anywhere; the private hexes and unit identifiers of the inputs as keys or
  words, numeric leaves masked) and carries no word made only of digits other than a scenario identifier, or the run
  publishes only the invalid disposition; `run --check` regenerates every file byte for byte. A test feeds the public
  builders synthetic rows whose identifiers and hexes are private values and requires the sanitizer to pass, and another
  requires it to catch a planted identifier word.
* Private: `local/diagnostics/s28/study-private.json.gz` on the evaluation server.
* Code: `experiments/t12_dispersion_shadow.py`, `evaluation/s28_t12.py`, `scripts/s28_t12.py`, `scripts/mutate_s28.py`;
  tests `tests/test_t12_dispersion_shadow.py`, `tests/test_s28_t12.py`, `tests/test_s28_driver.py`,
  `tests/test_s28_results.py` (binds the protocol to the sources and, after the run, the results to the rules) and
  `tests/test_real_s28.py` (server regeneration).
* Close-out: deterministic regeneration; mutation; a private documentation gate with planted errors; the current gates;
  the workstation suite, a clean GitHub clone and the server's private suite; the privacy scan compared exactly with the
  106 accepted lines; the platform canary rebuilt; a read-only ledger verify (2,797 sessions, none unclosed, no session
  2798); the workstation, GitHub and the server at one commit and tree.

## 22. If ready, and if not

If ready, a **draft** mechanism-probe plan is written for the owner's review and nothing more: Sprint 24 envisaged one
deterministic game for one-hex dispersion and capture denial, then two head-to-head games for defence, damage and
onward-movement cost; the draft does not authorize all three. It must first show a reproducible natural trigger,
legally listed or documented movement, a holder retained, dispersion completed as planned, correct stacking accounting,
objective denial while adjacent defenders remain, no unexplained `baseline-v2` action change, a bounded hold and the
exact engine-session cost; it is returned to the owner, and session 2798 is not opened. If not ready, T12-O1 is not
patched in this sprint: the idle requirement is not relaxed, and no reassignment, threat filter, combat logic or
formation control is added; the negative finding is recorded and exactly one next research task is recommended. Where
opportunity suffices but an interaction risk is unresolved, the smallest missing mechanism test is named instead of an
engine screen.

## 23. Validation before this registration

* Synthetic tests: the shadow (`tests/test_t12_dispersion_shadow.py`: the documented neighbour example, edges and row
  parity; every idle level, its order and absent fields; the trigger, an unheld objective, a non-play stage, full and
  impassable neighbours, held units, aircraft; every legal reason including a missing vehicle edge, the march graph, a
  roadblock for vehicles only and the stacking boundary; every admissibility exclusion; the holder rule, destination
  order, shared room within an objective and across two objectives, both stay outcomes, the legal tier; appended
  actions, holds, withholding, both releases, a non-play decision, determinism, identity and the files that may name
  the shadow); the analysis (`tests/test_s28_t12.py`: the independent check accepting the shadow and refusing every
  registered violation, maximal runs and replica de-duplication, onward claimant, first owner, holder departure and the
  release boundary, damage rows and windows, the nested census and conflict counters, the H0 prefix, the stop, the H0
  readings, the legality gate, the majority boundary of the interaction criteria, the disposition order, certificates and
  the sanitizer); the driver (`tests/test_s28_driver.py`); the protocol pin (`tests/test_s28_results.py`).
* Mutation (`scripts/mutate_s28.py`, record `evaluation/s28-t12-o1/mutation.json`): the first run killed 82 of 85
  planted defects; the three survivors (a first ownership before the onward order counted as one after it, the
  legality gate ignoring a missing HH side-game, the interaction criteria counting replica episodes) were test gaps,
  each closed with a test that kills it; the final run on the registered tests and sources killed 85 of 85 after the
  unmutated tests passed in the copy.
* Smoke on the evaluation server (node 0, one process, about 315 s each) with a trigger that cannot fire (minimum idle
  units set to a million): every fidelity anchor and block held, every side passed its integrity checks, the shadow
  changed no decision and the candidate equalled `baseline-v2` at every decision; no T12 figure was printed. After the
  last code changes the smoke was repeated with the public files also assembled and sanitised without writing: its
  first repetition stopped at the assembly because `protocol.json` was not yet frozen (the results carry its digest);
  after the freeze the repetition passed, assembled the eight public files and the private rows, and wrote nothing.
* Test counts: the shadow 38, the analysis 32, the driver 11, the protocol pin 1 (with 9 result checks that run after
  the study) and the server regeneration 3.

## 24. Not claimed

No tactic is shown to work or fail. Trigger and legal-tier counts describe recorded trajectories (H0's are
`baseline-v0`'s); a legal episode is an eligible historical target of the registered rule, not a dispersal that
happened; onward and damage labels are historical, not counterfactual; nothing here estimates a score effect, a damage
reduction or the engine's acceptance of a one-hex MOVE, and nothing says that own units next to an empty centre deny
capture.

## Results (2026-10-09)

Every figure below is read from the committed public files of `evaluation/s28-t12-o1/`, which `scripts/s28_t12.py run
--check` regenerates byte for byte on the evaluation server, unless it is labelled post hoc.

### R1. Order of work

The registration (`bf837e7` to `86a62fb0fcfa0a307b7a73221ee4742109b210a0`, tree
`936ad87e1b55d01e5223bff5396e2fd2a332035f`: the two commits of the server CPU policy and twelve registration commits)
was pushed at 2026-10-09T19:10:25+08:00 after the workstation suite passed on it (2,378 tests, 114 skipped) and the
privacy scan of every reachable blob (1,160) matched the 106 accepted lines exactly. A fresh GitHub clone had the same
commit and tree, its 15 registered files were byte-identical, and its suite passed (2,375 tests, 122 skipped). The
evaluation server's main clone was fast-forwarded to it by bundle. The pre-launch check found the server still in shared
mode (the colleague's job pinned to NUMA node 1, no CPU, memory or I/O pressure); `freeze --check` passed in the main
clone and `run` was started once, one process pinned to NUMA node 0; it wrote the eight result files and the private
rows. `run --check` then regenerated every public file and the private rows byte for byte. No engine was called and no
definition, threshold or stop was changed after the run.

### R2. Fidelity

All 18 anchors and the 10 blocks are reproduced exactly (`fidelity.json`): H0 33,696 decisions and 33,680 play
decisions, 123 recorded/`baseline-v2` differences (also by the separate pass); HH 11,524 of 11,524 reconstructions equal
to the recorded seat; 16 and 4 side-games; 509 and 416 `baseline-v2` MOVE orders; ground damage events on stationary
units on an objective 40 stacked and 13 alone in H0, 10 and 3 in HH, from the census rows and by this study's own
enumeration; 10 H0 side-games with a stationary stacked hit on an objective; the T6, N4, N5 and N6 blocks and the
admission table. All 20 side-games pass every integrity check, and there is no unexplained action difference at any
decision.

### R3. The census

Objective-decisions (decision-level counts; a group listed again counts again; `sides.json`, `census.json`):

| | HH p01 blue | HH p02 red | HH p03 blue | HH p04 red | H0 (16 side-games) |
|---|---:|---:|---:|---:|---:|
| held objective-decisions | 16,508 | 857 | 17,316 | 1,697 | 52,825 |
| two or more own ground units on the centre | 5,303 | 241 | 7,542 | 339 | 17,278 |
| two or more through A (stationary) | 4,924 | 34 | 7,231 | 54 | 15,096 |
| through B (no route) | 4,597 | 10 | 4,735 | 14 | 14,634 |
| through C and D (no stop, state or transport transition) | 4,354 | 0 | 4,495 | 0 | 13,716 |
| through E and F (not suppressed, no `baseline-v2` MOVE) | 4,303 | 0 | 4,495 | 0 | 13,387 |
| through G = two or more idle = the trigger | 4,300 | 0 | 4,495 | 0 | 13,346 |
| the legal tier (every batch complete) | 4,300 | 0 | 4,495 | 0 | 13,346 |
| trigger with a visible enemy on a neighbour | 144 | 0 | 1,765 | 0 | 24 |

Level F removed one more H0 objective-decision than level E and none in HH. Passability removed no neighbour (section
8). Every objective-decision with two or more idle units had a passable
neighbour with room, and every trigger decision reached the legal tier with a complete batch: where the trigger holds,
legality does not bind. In the two red HH side-games no objective-decision ever had two units past level C.

### R4. Episodes by side-game

| Side-game | Trigger episodes (= legal episodes) | Repeated listings | Objectives | Dispersed units | First divergence (step) | Prefix supported |
|---|---:|---:|---:|---:|---:|---|
| H0 1910631192 blue | 1 | 922 | 1 | 1 | 877 | no |
| H0 1930331196 red | 2 | 139 | 1 | 1 | 2,737 | no |
| H0 2010131194 blue | 1 | 1,404 | 1 | 1 | 395 | no |
| H0 2010211129 blue | 3 | 2,087 | 2 | 2 | 396 | no |
| H0 2010431153 blue | 7 | 1,190 | 1 | 1 | 597 | no |
| H0 2120531121 blue | 7 | 2,200 | 2 | 5 | 736 | no |
| H0 2130511121 blue | 29 | 5,354 | 4 | 6 | 1,279 | no |
| HH p01 baseline-v2 blue | 5 | 4,295 | 3 | 4 | 1,226 | yes |
| HH p02 baseline-v2 red | 0 | 0 | 0 | 0 | none | |
| HH p03 baseline-v2 blue | 3 | 4,492 | 3 | 3 | 1,115 | yes |
| HH p04 baseline-v2 red | 0 | 0 | 0 | 0 | none | |

The other nine H0 side-games have no episode. In count units: 58 episodes (H0 50, HH 8), 56 distinct (HH p03's episodes
starting at steps 1,227 and 1,803 repeat p01's); 9 side-games; 7 scenario-sides (HH's one scenario-side coincides with
H0's 2130511121 blue); 18 objectives and 24 dispersed units, counted by side-game; 22,083 repeated listings excluded.
Episode lengths: a median of 74 decisions (14 to 1,765), H0 74 and HH 1,309.5.

### R5. Legality, stacking and local conflicts

At trigger decisions the unit-neighbour pairs were legally supported in 379,149 cases and refused only for a full
neighbour (`stack_full`, 2,853, all in H0); MOVE was always listed, every one-hex path passed the gate's check and no
unit lacked a movement mode (the roadblock scenario had no trigger). Of the legal pairs, 35,130 were excluded as own
route hexes and 5,242 for a visible enemy; none was an objective hex. Every idle unit but the holder was dispersed (no
`no_destination_left` and no `no_admissible_destination`; R3 conflicts 0); every dispersal destination was empty before
and held one own ground unit after (72 of 72 dispersed unit-episodes); after the batch the centre held one own ground
unit in 47 of the 58 episodes and two or three in 11 (non-idle units standing there too). No decision had two triggered
objectives sharing a neighbour.

### R6. First divergences

Nine side-games diverge (H0 7, HH 2); the other eleven, both red HH side-games among them, never do. Every certificate
records a held objective, a holder retained on the centre, only the registered one-hex MOVEs appended, every
`baseline-v2` action preserved in order, no `baseline-v2` action for the dispersed units, and distinct, previously empty
destinations. The two HH certificates are on-policy facts: p01 blue at step 1,226 (the 50-point objective C, three idle
vehicles, two dispersed) and p03 blue at step 1,115 (the 80-point objective A, two idle units, one dispersed). All seven
H0 first divergences fall after that side's first recorded/`baseline-v2` difference, so none is a valid action-level
fact.

### R7. Onward movement and the cost of the hold

Over the 72 dispersed unit-episodes of the 58 legal episodes, `baseline-v2` issued no MOVE to a dispersed unit while the
origin was held: no claimant, no first owner, no decision a hold would have suppressed. The holder was never ordered off
the centre, and the origin stayed held to the end of the recorded game in every episode (58 of 58). Four of HH's nine
dispersed unit-episodes concern units that were later lost. The interaction criteria I1, I2 and I3 are 0 in HH, in H0
and pooled; they do not decide the disposition.

### R8. Historical damage diagnostics

| | H0 | HH |
|---|---:|---:|
| ground damage events on stationary units on an objective (stacked, alone) | 53 (40, 13) | 13 (10, 3) |
| objective held by the victim's side at the event | 16 | 13 |
| stacked and held | 14 | 10 |
| of these, with an earlier trigger and legal tier in the same holding run | 9 | 6 |
| attacker visible at the event / seen within the lookback window before it | 47 / 53 | 12 / 13 |
| victim later lost | 48 | 13 |

In each of the 9 and 6 cases the latest legal decision came a median of 1 step before the hit (at most 26 and 52), and
the side's first divergence lies in that holding run before the hit: these hits fall on states the candidate would not
have reached unchanged. Around the legal episodes, idle centre units were damaged within 300 steps after the start in H0
5 times as units (7 events, all on stacked victims) and in HH once (1 event, stacked), and before the start in H0 8 times
(9 events) and in HH never. No damage reduction is estimated.

### R9. The registered stop and the gates

| Rule | Registered quantity | Result | Met |
|---|---|---|---|
| Opportunity stop (primary) | trigger episodes per HH side-game, at least one each | p01 5, p02 0, p03 3, p04 0 | **yes** |
| H0, each-side-game reading (reported only) | every H0 side-game at least one | 9 of 16 without | yes |
| H0, average reading (reported only) | H0 trigger episodes at least the H0 side-games | 50 against 16 | no |
| Legality gate | legal episodes per HH side-game, at least one each | p01 5, p02 0, p03 3, p04 0 | yes (not reached) |
| I1, I2, I3 | majorities of claimants, holder departures, partial dispersions | 0 everywhere | no |

### R10. Disposition: T12_O1_INADEQUATE_OPPORTUNITY

Fidelity is intact, every side passes its integrity checks and no action difference is unexplained, so the study is
valid; the registered opportunity stop is met because neither red HH side-game ever had two idle own ground units on a
held objective. No mechanism probe is drafted, nothing is promoted, and session 2798 is not opened. The T12-O1 increment
is not patched in this sprint.

### R11. Post-hoc facts (read after the disposition; they change nothing)

From `local/diagnostics/s28/posthoc.py` on the evaluation server (aggregates only):

* **The trigger is an end state.** Every one of the 58 legal episodes began at a decision where the side held every
  objective of the game (H0 1 of 1, 2 of 2, 5 of 5 or 7 of 7; HH 7 of 7 in all eight) and `baseline-v2` issued no MOVE
  for any unit. Idle stacks form on held objectives only when nothing is left to capture, which is also why no dispersed
  unit was ever sent on.
* **Red never idles on a held centre.** In both red HH side-games the largest number of idle own ground units on any held
  centre at any decision is 0 (4 in both blue side-games).
* **Stationary units with a route are blocked by the stacking limit.** Of the centre units that pass level A and fail B
  (a route but no speed), the next route hex held four own ground units in 1,688 of 1,703 cases in H0 and 11,413 of
  11,425 in HH: the published stacking block that Sprints 2 and 4 diagnosed (T1-r, PS-1), outside T12's scope.

### R12. What Sprint 28 shows

1. **T12's trigger occurs only in the end state of `baseline-v2`'s games**: idle stacks on held objectives appear once
   the side holds every objective and `baseline-v2` issues no move. In HH only the blue seats reached that state (from
   step 1,115), the red seats never, so the registered stop fails on two of four genuine `baseline-v2` side-games.
2. **Where the trigger holds, the tactic is easy to specify**: every one-hex relocation was listed and passed the gate's
   path check, every batch was complete, every destination empty, and no local conflict arose.
3. **The registered interaction risks were absent for the same reason**: with nothing left to capture, no dispersed unit
   was ever sent on and no holder was ordered off. These are historical labels; they say nothing about a recapture fight.
4. Sprint 24's negative lesson holds in its second form: holders rarely stack idle under `baseline-v2` except after the
   side already holds everything.

### R13. Process notes

* The first mutation run killed 82 of 85 planted defects; the three survivors were test gaps, closed before the
  registration (section 23).
* A patch applied through a shell heredoc consumed a line-continuation backslash and joined two lines of the shadow; the
  code stayed valid and behaved identically, the mutation script's exactly-once anchor check exposed it, and the line was
  rewritten before the registration.
* The pre-registration review moved the per-side summaries out of `census.json` into the splittable `sides.json`, so that
  a public file could not exceed the size limit, which the registration maps to `T12_O1_OFFLINE_INVALID`.
* The second smoke run stopped at the assembly because `protocol.json` did not yet exist; the freeze came first and the
  third smoke run passed. No code changed between the two.

### R14. Recommendation (one)

Prepare, for the owner's approval, the registration of the next eligible increment of Sprint 24's frozen ranking:
**T7-C, the T7-E3b controlled concealment-exit diagnostic** (its entry in
`evaluation/s24-tactical-frontier-reselection/experiments.json`, W 3.70, E 4: at most two deterministic diagnostic
sessions, the first for the move exit), with no session opened until the owner approves. Why this one: Sprint 24's
ranking is frozen and its first three increments have now each been settled by a registered experiment (T13-D1 not
ready, T6-S not supported, T12-O1 inadequate opportunity); T7-C is next and eligible, its offline analysis is already done
(Sprints 7 and 18), and its question, whether a concealed unit's move ends concealment at once as documented, does not
depend on the end-state finding of this sprint. Not recommended: any repair of T12-O1 (forbidden; a trigger confined to
the end state cannot be widened without relaxing the idle requirement), an engine probe of dispersion (the stop is met),
or work on the stacking block of R11 (the shelved T1-r and PS-1 line).

### R15. Close-out

* The results were pushed as `c8017037564f43386b90bf9fa9e7264cb562ad74` (tree `0d8ab0accd16f5cc15dc1adcbf077de908942ea0`)
  at 2026-10-09T19:38:51+08:00; a fresh clone from GitHub had the same commit and tree and byte-identical files. The
  evaluation server's run outputs were confirmed byte-identical to the committed blobs before its main clone was
  fast-forwarded to the commit by bundle. All 18 sprint commits up to the results were audited as a set (author,
  single-line ASCII subjects of at most 72 characters, no body).
* Tests at that commit: the workstation tree ran 2,378 tests (105 skipped) with exit 0; a clean clone from GitHub
  2,375 (113 skipped) with exit 0; the evaluation server's private tree 2,391 (7 skipped; 9,053 s) with
  exit 0, serial and pinned to NUMA node 0, including this sprint's regeneration (`freeze --check`, `run --check`) and
  mutation-record tests, with the ledger file byte-identical before and after.
* Documentation gates: this sprint's private gate (`local/diagnostics/s28/doc_gate.py`) binds the results to the public
  files and the copied logs and catches all its planted errors; all 30 current gates pass with their plants, and
  the four retired `_v1` copies fail as at Sprint 27's close-out.
* Privacy: the scan of every reachable blob at the results commit (1,171 blobs) gives 106 hit lines, identical to
  the accepted set; no line was added or removed, and the 106-line accepted set passed its independent integrity check
  again.
* Platform canary: rebuilt on the workstation and the server, SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, no smoke mismatch on either host.
* Engine ledger: read-only verify after the server suite, 2,797 sessions opened and closed, none unclosed, state
  chain continuous, the last event the close of session 2797; ledger file SHA-256 unchanged from the start of the
  sprint; no session 2798. No engine installation, configuration or historical result was touched, and the server's
  development worktree was removed.
