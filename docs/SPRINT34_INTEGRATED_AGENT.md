# Sprint 34: integrated tactical agent

Date: 2026-10-10 (UTC+8). Track: `EXPLORATORY` (`docs/EXPLORATORY_TRACK.md`). Branch `sprint34-integrated-agent`,
created from `main` at `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`; `main`, the earlier sprint branches and the
independently maintained `platform-compat2` branch are not modified.

This sprint replaces the one-mechanism add-on pattern of Sprints 8 to 33 with a whole-force agent: one decision cycle
that allocates every mobile unit to objectives, plans routes under friendly-traffic capacity, keeps holders, carries
infantry, fires, and validates every action independently. Two architectures were built and compared offline; one is
frozen as the live candidate before any Sprint 34 engine result.

## 1. Authorization and verified state at the start

The owner's Sprint 34 prompt authorizes at most 24 new engine sessions, 2803 to 2826 inclusive, in two pre-registered
stages (section 10). No earlier budget is inherited. State verified before any work:

| Item | Verified value |
|---|---|
| `main` (workstation, GitHub, evaluation server) | `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85`, clean |
| Sprint 33 branch `sprint33-t7-b1-live` | `634976f24dd70bf20f8e5a30cc6610f9bb5e151f` |
| `platform-compat2` | `a909557bb43648c5c879c19ad8f8ba362e8f4892`, untouched |
| Engine ledger | 2802 sessions opened and closed, none open, integrity ok; SHA-256 `b91d0538c96a855513de98226b28d21c4484785cc6dab1dadc5b50d6d3c69dbe` |
| Server load | a colleague's job pinned to NUMA node 1; this sprint uses node 0 (`docs/SERVER_RESOURCE_POLICY.md`) |

The shared primary checkout carries another session's uncommitted platform-builder edits; they were left as found and
all Sprint 34 work is in a separate worktree.

## 2. Evidence-to-architecture matrix

Each row is a tactical problem of `baseline-v2` established by earlier sprints, the earlier attempt and why it failed
or stayed open, and what the integrated design does differently.

| Problem | Root mechanism | Affected units | Evidence | Earlier attempt and outcome | Integrated design | Why the earlier failure does not recur |
|---|---|---|---|---|---|---|
| Column deadlock | more than four own ground units converge on one hex; the occupants are later ordered out through a full neighbour; an issued path cannot be changed; a stop on a waiting unit is deferred indefinitely | ground columns, mostly vehicles | Sprint 2 diagnosis (two captured games), Sprint 3 design, Sprint 4 probe | PS-1B stop and back-off: refuted (stop deferred, G2 failed); T6-S stagger: executed but exposure not halved; T9 caps | a capacity ledger at order time: at most three units planned to stand on an objective hex (including units already on their way), any hex whose planned stand reaches four is closed to new paths, a full first hex holds the order, a free unit standing in a full hex steps aside when an own unit waits to enter it | prevention when moves are issued instead of recovery afterwards; never uses the stop action |
| Herding to the nearest objective | every unit independently picks its cheapest unheld objective | the whole force | Sprint 8 (cap 4 per objective above every control in 2130511121), Sprint 9 (+305.47 registered) | T9-v1 reserved places in emission order (slow infantry took an 80-point objective they could not reach); T9-v2 staging and the batch allocator lost the cross-objective redistribution | whole-force maximum-utility matching of units to objective slots every decision, with free-flow arrival, feasibility before the end, diminishing slot weights and persistence | no emission order; a unit that cannot arrive takes no slot; every free unit is re-evaluated against every objective, so redistribution is built in |
| No garrison | `baseline-v2` sends every idle unit on from a held objective | holders of captured objectives | Sprint 25: 59 of 66 losses of held objectives followed own moves | T13-D1 (single occupant): not ready; K1: no eligible holder; K2 (withhold one move): a 2130511121 opening objective never first-owned | hold slots compete with capture slots inside the same allocation, with persistence and (variant B) an economy preference for low-value holders | the hold is not a veto on someone else's move; the force-level allocation decides who stays and who goes |
| Slow infantry | infantry move one hex per 144 steps against 20 for vehicles | infantry squads | Sprint 18: 20 of 51 infantry move orders could not arrive; Sprint 34: in 2130511121 no red infantry squad reaches any objective in fewer than 2,736 steps of a 2,880-step game | T2-P1 transport mechanism supported (one pair); T2-X1 shelved: the held carrier was one `baseline-v2` wanted to send elsewhere | variant B allocates lift pairs (an infantry squad and a co-located carrier) like units, with a bounded embark-carry-disembark life cycle, re-targeting and unloading on the spot when no slot is left | the carrier's task comes from the same allocation, so there is no second plan to conflict with |
| Idle artillery | `baseline-v2` never issues indirect fire | artillery | Sprint 8: orders accepted, rounds land after 150 steps, hexes explode about 300 steps | T4-v2 damaged enemies but own units entered exploding hexes near objectives; T4-v3 avoided objectives and gained nothing | variant B fires only at stationary visible enemy ground units clear of every own unit, remaining path and planned stand, and the route planner closes live impact zones to own ground movement | firing and movement are planned together; an add-on could not stop the movement layer from walking into its own impacts |
| Exposure while moving | moving ground units take most damage | moving ground units | Sprint 18: 124 of 205 damage events (replay corpus) | T6-G entry gate: no opportunity (every exposed move started inside an envelope) | variant B adds a bounded route cost inside visible enemies' published ranges | a cost on route choice, not a gate on departure |
| Fire coordination | duplicate targets | shooters | `baseline-v2` promotion (code-516 rate cut by 88.7%) | kept | `baseline-v2`'s ranking and same-step target reservation; variant B breaks ties within the top attack level by lower remaining strength | no kill model is assumed (Sprint 21 left it underidentified) |
| Stop to engage | a traversing vehicle can stop, at a cost of the current hex plus 75 steps | vehicles | Sprint 33: 5 of 5 stops exact, 4 of 5 lost the target | mechanism supported | not used | the time cost and the visibility loss outweigh the measured benefit |
| Concealment | concealment of idle units | stationary ground units | Sprints 6 and 18: mechanism supported, benefit channel empty | not selected | not used | no evidence of benefit |

## 3. Engine facts measured in Sprint 34

A read-only probe (`scripts/s34_fact_probe.py`, the executed version, SHA-256
`f73ab65283f3c2caeca98923bcd30c61f32361636b7002991f846228995f925d`) read 14,400 genuine seat decisions of three
full-step captures (Sprint 22's 1930331196 C3 game, Sprint 12's first 2130511121 game, Sprint 31's 1930331196 C2
game). Its output stays on the evaluation server. Aggregates:

* occupation (action 5) was listed in 48 of 48 decisions where an own ground unit stood on an objective its side did not
  hold with no visible enemy ground unit in the objective's zone (46 of them during the post-arrival transition), and in
  0 of 805 decisions with an enemy ground unit in the zone;
* embark (action 3) was listed only for settled infantry squads and unmanned ground vehicles, always with a settled
  infantry fighting vehicle in the same hex (18,930 options); disembark (action 4) only for settled infantry fighting
  vehicles carrying passengers (12,599 unit-decisions);
* only tanks listed a shot while having a move path (52 unit-decisions);
* artillery listed indirect fire in all 86,400 of its unit-decisions and movement in none;
* in the seat's own view, enemy units carry their move path, speed and remaining strength (move path non-empty in
  35,029 of 74,813 enemy records), while their relation fields are masked;
* `valid_passenger_types` lists passenger **sub_types** (2 squad, 4 unmanned ground vehicle, 7 loitering munition),
  not unit types (scenario files; the first draft of the agent read it as unit types and never embarked).

## 4. Architecture

Package `src/miaosuan_agent/integrated/`. One decision (`policy.py`):

```
observation -> world view (world.py)
            -> memory upkeep: sightings, first ownership, live tasks (memory.py)
            -> lift life cycle (transport.py)
            -> traffic ledger (traffic.py), hazards and threat costs (fire.py)
            -> objective pictures and allocation (allocation.py, assignment.py)
            -> recovery and dispersal (policy.py)
            -> per-unit arbitration: occupy > lift order > direct fire > move > stay
            -> indirect fire (fire.py)
            -> independent validation (validate.py)
            -> actions + memory
```

Ownership of decisions: the allocation owns where every free mobile ground unit goes; the lift life cycle owns units
in a lift; the traffic ledger owns whether a planned move may be issued now; the fire module owns shots; arbitration
only orders these by priority; the validator owns legality. Every own unit gets a recorded module and reason in the
trace, acted or not. The memory (`CommanderMemory`) is the only state between decisions: sorted tuples of tasks,
lifts, sightings (expire after 600 steps, at most 96), fire orders, last orders and first ownership. Any exception other
than a contract violation makes the decision `baseline-v2`'s, recorded as a fallback; a contract violation yields no
action, as for `baseline-v2`.

Allocation (`allocation.py`): an objective the side does not hold offers capture slots with weights 1.0, 0.5, 0.3 of its
value when contested (a known enemy ground unit within 4 hexes, or enemy-held) and 1.0, 0.15 otherwise; a held
objective offers a hold slot (0.9 when a known enemy could reach its zone before the end, 0.35 otherwise) and a second
slot while contested. Slots already filled by units on their way, or by units on the hex that cannot take an order, are
not offered, and no objective is offered more than 3 places. A unit's utility for a slot is `weight * value - 0.01 *
arrival steps`, plus 6 for its current target. Units that cannot arrive 20 steps before the end are never offered a
slot. Free units without a slot stay; nothing moves without a slot.

The two architectural variants (`config.py`):

| | Variant A `capacity-traffic` (CT) | Variant B `mission-orchestrator` (MO) |
|---|---|---|
| allocation | exact maximum-utility matching (Hungarian) | greedy by utility, including lift pairs |
| retention | hold slots with persistence | the same, plus a preference for low-value holders and infantry |
| transport | none | lift pairs, bounded life cycle |
| indirect fire | none | guarded, clear of own units, paths and planned stands |
| routes | traffic-capacity constraints | the same plus threat costs inside visible enemies' ranges |
| direct fire | `baseline-v2`'s ranking and reservation | the same with a lower-strength tie-break |

Both share the traffic ledger, recovery, dispersal (a surplus unit steps off a full objective hex into its zone), the
memory, the fallback and the validator. Implemented but not activated in either: the stop action, concealment, guided
fire, launching loitering munitions, artillery cancellation. A disabled feature is not a completed capability.

## 5. Scenario coverage and capability matrix

`scripts/s34_coverage.py` writes `evaluation/s34-integrated-agent/coverage.json` from the pinned SDK archive without the
engine: for each of the 50 scenario files the map named by the registered naming rule, the registered eligibility
verdict, operators by faction and class, objectives, movement modes, which capability modules have something to act
on, the objectives each side can reach before the end, and both variants' first play decision on the model world's
initial state. 40 scenarios on 7 maps are eligible under the old SDK pairing; in them transport applies in 37, indirect
fire in 24, aircraft support in 34. Both variants' first decisions had no rejected action, fallback or contract error
and targeted at least one objective on every eligible side. Only eight scenarios have ever been played on the engine;
no scenario was played to build this matrix.

## 6. Design choices and their reasons

* Destination cap 3: one below the stacking limit keeps an objective hex passable, and fewer stacked units take the
  adverse stacking modifiers (Sprint 18: 112 of 177 ground hits on stacked victims).
* Time cost 0.01 per step: an 80-point objective stays worth taking at 2,000 steps of travel, so distant objectives
  are not ignored, while ties go to the faster unit.
* Arrival margin 20 steps: free-flow time is a lower bound on arrival (Sprint 11).
* Lift gain 150 steps, cooldown 600 steps: a lift costs three 75-step transitions; the cooldown stops a passenger from
  being carried back and forth (an early draft carried six squads 18 times in the model world).
* Indirect-fire clearance 2 hexes and impact zones closed to own movement for 480 steps after an order: flight 150,
  explosion about 300, margin 30.

## 7. The model world

`evaluation/s34_world.py` is a deterministic stand-in engine on the real SDK maps and scenarios, written for engine-free
end-to-end runs. It implements the measured movement, stacking, transition, occupation, embark, disembark and listing
rules, a visibility rule by published observation distance (no line of sight), and no combat damage: shots are listed
and echoed but change nothing, indirect fire records an impact point and damages nothing. It is a model, not the
engine; nothing it produces is engine evidence or a predicted score. Running `baseline-v2` in it reproduces the
column blocks diagnosed in Sprint 2 (units waiting thousands of steps), which the integrated variants avoid.

## 8. Offline comparison protocol and selection rule (registered before the comparison ran)

Populations (`scripts/s34_offline.py`, rules `evaluation/s34_offline.py`):

* `M-inert`: every eligible scenario, both seats, each variant against the inert control, in the model world;
* `M-v2`: the same against `baseline-v2`;
* `G`: genuine engine observations: the eight pinned replay-corpus games (both seats) and sixteen full-step timelines
  (every seat that is not the inert control), each decision re-decided by each variant with its own memory chain, its
  actions checked by the variant's validator and by an independent check (the frozen project gate for move, shoot and
  occupation; the listing and option for embark, disembark and indirect fire), and compared with a fresh `baseline-v2`
  decision on the same observation.

The genuine population can only show action-level facts: after a variant's first divergence the observations come
from a trajectory it did not produce, so nothing in `G` is a counterfactual outcome.

Gates, each required of a variant: G1 no rejected, refused or independently illegal action; G2 no fallback or contract
error; G3 every model replay check identical; G4 no model unit waits 300 or more consecutive steps in front of a full
hex; G5 genuine per-decision latency p99 at most 100 ms and maximum at most 1,000 ms, model maximum at most 1,000 ms;
G6 the variant's actions differ from `baseline-v2`'s in at least 1% of genuine play decisions; G7 no own ground unit in
an own exploding impact hex in the model; G8 every population played.

Rule: if both variants pass every gate, MO is selected when its model objective value (the value of the objectives its
side holds at the end, summed over the population's games) is at least 98% of CT's in both `M-inert` and `M-v2`;
otherwise the variant with the higher total over the two populations (a tie goes to CT). If one variant passes, it is
selected. If neither passes, the disposition is `S34_ENGINEERING_BLOCKED` unless a corrected revision, documented as
such, passes. The 98% clause exists because MO's extra modules (transport, indirect fire, threat costs) have
engine-verified mechanisms but no benefit the model can show (it has no combat), while their cost in movement is
measurable: MO must not lose measurable movement performance to be preferred. Ablations are reported, never selected.

## 9. Offline comparison results and the selected candidate

Run on the evaluation server (NUMA node 0) from commit `598aef7` (the registration of section 8), with the candidate
code unchanged since; outputs `evaluation/s34-integrated-agent/{model,genuine,selection}.json`. 664 model games, none
crashed; 24 genuine games (8 replay-corpus games, 16 timelines), 97,078 decisions re-decided per variant.

| Measure | CT | MO | `baseline-v2` |
|---|---|---|---|
| M-inert: objective value (80 games; all objectives 22,480) | 22,480 | 22,480 | 22,190 |
| M-v2: objective value of the variant's side (80 games) | 18,190 | 18,300 | 8,760 (mirror, 80 games) |
| M-inert: longest wait in front of a full hex (steps) | 20 | 19 | 2,661 |
| M-inert: waiting unit-steps | 271 | 38 | 862,560 |
| M-inert: embark orders / indirect-fire orders | 0 / 0 | 602 / 1,838 | 0 / 0 |
| genuine: rejected or independently illegal actions | 0 | 0 | |
| genuine: fallbacks / contract errors | 0 / 0 | 0 / 0 | |
| genuine: play decisions differing from `baseline-v2` | 58,395 of 97,040 | 58,059 of 97,040 | |
| genuine: latency p99 / maximum (ms) | 5.646 / 214.993 | 23.751 / 208.527 | |
| model replay checks identical | 1,930 of 1,930 | 1,930 of 1,930 | |

Both variants passed all eight gates. MO's model objective value equals CT's against the inert control and exceeds it
against `baseline-v2`, so the registered rule selects **MO**. Frozen as `integrated.config.LIVE`; identity
`s34-integrated-mission-orchestrator-1`, policy source `b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b`
(`baseline-v2`'s frozen sources plus `integrated/`); the only change to the compared code is the line that names it.

Limits of this evidence, stated before any engine result:

* in the genuine replay a variant's own orders never execute (the trajectory is `baseline-v2`'s), so it re-issues
  them at every decision; its move counts there (about 2.5 per decision) are an artefact of replay, not behaviour; in
  the model world, where orders execute, the variants issue tens of moves per game;
* in the eight frozen scenarios against `baseline-v2`, the model ablation without transport held 2,220 objective
  points against MO's 2,140 (16 games each): lifts cost race time in a model that has no combat to reward cheap
  holders; transport stays in the candidate as the registered rule selected, and this cost is a hypothesis the live
  games can contradict;
* the model's `baseline-v2` blocks are model behaviour: the engine's own `baseline-v2` captured every objective in
  the Stage B configurations (references, section 10), so the model overstates its blocks there.

## 10. Live protocol (registered before session 2803)

Card `evaluation/s34-integrated-live-1/manifest.json` (canonical SHA-256
`4bb778eda0d7aeaed867fdefb06ad98ec9a5c7ee8bb58550c4b007034cfa5304`), rules `evaluation/s34_live.py`
(`s34-integrated-live-rules-1`, SHA-256 `7e7e24021a53a0ec5a2176394ae9eb158054117d62545a4082180da5c89b91d2`), runner
`scripts/run_s34.py --position N`, one game per exclusive session, serially, on NUMA node 0.

**Schedule** (fixed before any game; position n opens session 2802 + n):

| Batch | Positions | Sessions | Games |
|---|---|---|---|
| A1 | 1 to 8 | 2803 to 2810 | first repetition: in 2130511121, 2120531121, 1930331196, 1910631192 in that order, the candidate red against `baseline-v2` (H1), then blue against it (H2) |
| A2 | 9 to 16 | 2811 to 2818 | the same eight configurations, second repetition |
| B1 | 17 to 20 | 2819 to 2822 | 2120531121 C2 (candidate red against the inert control), C3 (inert red against the candidate blue), then 1930331196 C2, C3 |
| B2 | 21 to 24 | 2823 to 2826 | the same four configurations, second repetition |

**References** (`evaluation/s34-integrated-agent/references.json`: `baseline-v2`'s own games, same scenario, condition
and seat, 15 per configuration; margin = the seat's `win` score). The comparison is unpaired and historical, never a
paired causal estimate.

| Configuration | Seat | Margin mean | SD | Min | Max | Objective score mean (min) |
|---|---|---|---|---|---|---|
| 2130511121 C1 | red | -869.9 | 114.66 | -1,055 | -719 | 20 (0) |
| 2120531121 C1 | red | -245.0 | 586.60 | -871 | 489 | 112.7 (0) |
| 1930331196 C1 | red | 179.6 | 453.24 | -508 | 756 | 195.3 (0) |
| 1910631192 C1 | red | -85.9 | 233.89 | -334 | 236 | 52 (0) |
| 2120531121 C2 | red | 357.0 | 50.14 | 297 | 457 | 310 (310) |
| 2120531121 C3 | blue | 588.3 | 14.86 | 559 | 599 | 310 (310) |
| 1930331196 C2 | red | 272.9 | 4.13 | 258 | 274 | 310 (310) |
| 1930331196 C3 | blue | 570.0 | 0.00 | 570 | 570 | 310 (310) |

In a C1 game the blue margin is the negative of the red one, so the blue reference is the mirror of the red row
(blue objective scores: 2130511121 mean 420, minimum 390; the other three minimum 0).

**Structural stops** (any one closes the study at once; disposition `S34_LIVE_INVALID`): S1 the game did not
complete; S2 the ledger is not exactly the schedule's games so far, in order, closed with integrity ok and the state
file and home unchanged; S3 a tracked file, the SDK archive or a policy source changed during the game; S4 a contract
error of the candidate, an in-game replay mismatch or an observer error; S5 the observer's fresh reconstruction of any
candidate decision differs from the live one, or more than 1% of the candidate's decisions fell back; S6 the engine
refused more than 2% of the candidate's unit actions, or more than five of its non-shoot actions.

**Severe harm** (Stage A, closes the gate; disposition `S34_INTEGRATED_REJECT`): after A1, a candidate margin more than
three reference standard deviations below the reference minimum; after A2, a configuration whose two candidate
margins are both below the reference minimum (under `baseline-v2`'s own distribution about 1 in 256 per
configuration). An ordinary loss inside the historical range is recorded and analysed, never a stop.

**Gates**: after each game its structural stops; after each batch `s34_live.batch_gate`. Stage B runs only when the
A2 gate is open. No retry, no replacement, no game outside the schedule, no session after 2826.

**Dispositions** (first match): `S34_LIVE_INVALID`; `S34_INTEGRATED_REJECT` (severe harm; or the mean standardized
margin of the 16 Stage A games, `Zbar`, at or below -0.5; or a Stage B objective score below the reference minimum in
three or more of its eight games); `S34_INTEGRATED_PROMISING` (both stages complete, `Zbar` at least +0.5, a positive
mean `z` in at least three of the four scenarios, no Stage B objective score below the reference minimum, and a Stage B
margin at least the reference minimum minus 50 in at least seven of eight games); otherwise
`S34_INTEGRATED_INCONCLUSIVE`. `z = (margin - reference mean) / reference SD` for Stage A games. With two games per
seat the result is exploratory: `PROMISING` means a larger independent confirmation is justified, not that the
candidate is better, and never a promotion or a platform deployment. `S34_ENGINEERING_BLOCKED` would have applied had
no session been opened.

**Measured per game** (descriptive): scores and margin, objectives first owned (and whether before the opponent),
mean held objective value, objectives lost and recaptured, force lost by class, waits in front of full hexes,
refusals by type and code, judged attacks and friendly damage, actions and module activity, decisions differing from
a shadow `baseline-v2` by module, reconstruction checks, fallbacks and latency.

**Rehearsed** before registration on the stand-in engine (the model world behind the engine interface) from the
committed tree: positions 1 to 8 with the real references (the A1 gate closed on severe harm, as 150-step model games
must), and positions 1 to 24 in a copy with permissive references (every gate open, exit 5 at the end of the
schedule, a replayed position refused). Mutation test: 41 of 41 planted defects killed
(`evaluation/s34-integrated-agent/mutation.json`; the first run killed 26 of 41 and the 15 gaps were closed by
`tests/test_s34_gaps.py`, one equivalent mutant replaced).
