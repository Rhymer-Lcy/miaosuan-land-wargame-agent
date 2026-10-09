# Sprint 26: T6-S stacked-column stagger, offline shadow study

**REGISTERED — OFFLINE — NO ENGINE SESSION — A SHADOW ON HISTORICAL STATES, NOT EVIDENCE THAT STAGGERING REDUCES DAMAGE — NOTHING PROMOTED**

Sprint 25 ended `T13_D1_NOT_READY`, and the owner accepted that disposition. On 2026-10-08 the owner approved the
runner-up experiment Sprint 24 selected prospectively: T6-S, stacked-column movement staggering
(`evaluation/s24-tactical-frontier-reselection/experiments.json`, entry T6). This sprint is its offline mechanism and
opportunity study. No engine session is authorized and session 2797 is not opened; no executable candidate, run card
or promotion follows from it. If the registered study passes, one DRAFT two-session mechanism-probe proposal is written
for the owner and not executed. Dates are business dates in UTC+8.

Sections 1 to 22, the code they name, the frozen `protocol.json` and `inputs.json`, the tests and the mutation record are
committed and pushed before the target analysis is run. Results follow in a separate section; no registered section is
edited afterwards.

## 1. Starting state

| Item | Identity |
|---|---|
| Repository | `main` `9c3e4c333ae87aa110fe6ddeaf49b7e179f85d72`, tree `628c92513bae46b224666530a642494e26a5c5c9`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | read-only verify at the start of the sprint: 2,796 sessions opened and closed, none unclosed, integrity ok, state chain continuous; ledger file SHA-256 `eaae02bb0b1805a6ee0cf757f96fa39ec8e443f821835b6feb994dee55230bea`; session 2797 not authorized |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |
| Platform canary | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Privacy baseline | the 106 accepted hit lines of `local/diagnostics/s25/privacy-baseline-106.txt` (below) |

**Privacy baseline.** The accepted set was loaded from its file and checked independently of the Sprint 25 script that
wrote it (`local/diagnostics/s26/privacy_baseline_check.py`, read-only): the file parses (106 hit lines, equal to its
total); as multisets it is Sprint 24's 104-line start scan plus exactly two lines and minus none; each added line names
the Sprint 24 document at line 464 or 484 under the one rule the owner's decision covers, its text equals that line of
the registered blob read from the git objects, each blob is the document's blob at the registered commit, and the line is
absent from the file at the commit before; the Sprint 25 adjudication record names both commits and both blobs. Four
planted defects in the checker (a wrong blob, a wrong line number, a wrong file digest, the registered commit given as
its own predecessor) each made it refuse. The start-of-sprint scan of every reachable blob (1,092 blobs) gives 106 hit
lines, identical to the accepted set as a multiset. Comparison stays exact; no count-based allowance is used.

The historical dispositions stand unchanged: T6-G `T6_G_OFFLINE_INADEQUATE_OPPORTUNITY`; T13-D1 `T13_D1_NOT_READY`; T9
SHELVED; T2-X1 SHELVED; T2-P1 `T2_P1_MECHANISM_SUPPORTED`; Sprint 24's selection and every earlier disposition. None of
those increments is repaired here. T6-S is a distinct formation-timing hypothesis; it is not a group-garrison
replacement for T13 and must show its own co-location, route and threat conditions.

## 2. Scope, the evidence boundary and disclosure

* Offline only: no engine session, no executable candidate, no run card, no change to `baseline-v2`, the stable core,
  the evaluators, the engine installation or configuration, or any historical output.
* Two populations of different evidence strength, never conflated (Sprint 24's registered populations). **H0** is the 8
  replay-corpus games, both seats (16 scenario-sides): the recorded actions are `baseline-v0`'s, and `baseline-v2`'s
  decisions are reconstructed on those states. **HH** is the 4 Sprint 12 head-to-head timelines in 2130511121, analysed
  on the genuine `baseline-v2` seats (two openings, each played twice). Both are read through Sprint 18's census loader,
  unchanged.
* Never used: BOKE-2026, the stopped 360-game prevalence study, any new game. No other historical capture enters this
  study, not even descriptively.
* **Disclosure.** Before writing this registration the author read: the documents of Sprints 19, 24 and 25 in full;
  Sprint 24's T6 entry and its evidence items in `experiments.json`; Sprint 23's evidence-boundary section; the
  frontier's T6 and T13 rows; PS-1's design (the documented contract and formal model) and its engine probe's results
  (sections 14 to 18); the T1-r diagnosis; the code of Sprints 18, 19 and 25; the published observation reference (`stack` "whether stacked"; `speed` the current movement speed;
  `passenger_ids` on carriers) and the published rules (at most four own ground units on a hex; the adverse result
  correction for a stacked or moving target). The author knew Sprint 25's post-hoc finding that its 28 multi-defender
  order-vacating losses had all their last defenders stacked, and Sprint 18's published stacking and movement figures.
  One structure probe was run on the private inputs (`local/diagnostics/s26/structure_probe.py`, on the evaluation
  server); it computed and printed nothing about co-located movers, shared route hexes, threats or any stagger rule.
  It found: (1) the engine's `stack` field is set at every own-ground unit-decision on a hex shared with another own
  ground unit (0 exceptions among 200,067 such unit-decisions in H0 and HH) and also at 1,563 unit-decisions without
  such co-location; (2) `baseline-v2` never gives one unit more than one MOVE at a decision; (3) it never gives a MOVE
  to a unit with a non-empty observed route or a positive speed, never with an empty, unreadable or non-adjacent route,
  and never without action type 1 listed for the unit; (4) every own ground operator carries a `passenger_ids` field;
  (5) of the 302 HH ground MOVEs, 259 had the unit observed on the route's first hex exactly one documented hex time
  after the order (the unit's `cur_hex` changes when it enters the next hex), 6 one to three steps later, 19 later
  still, and 18 were never observed on that hex. A known-answer smoke run with a never-firing shadow (section 21) checked
  every fidelity anchor and printed no T6-S figure.

## 3. Scientific question

Sprint 24 registered the hypothesis that `baseline-v2` sometimes orders co-located ground units along the same first
route hex at the same decision, that they then move stacked inside an observed enemy's direct-fire envelope, and that
staggering their departure could reduce stacked movement exposure at the cost of delaying some movers. Sprint 25's
observations (59 of 66 held-objective losses followed ordered departures; 28 involved several final defenders; all 81
last-defender instances of those were stacked; 27 of the 28 were ordered out together) motivate the question; they are
not evidence that T6-S would trigger or succeed.

The question here: **does the frozen stagger rule have repeated, general opportunity on `baseline-v2`'s own decisions,
and are the units it would delay so often the first owners of their destinations that its cost would be confounded with
its benefit?** It is a mechanism and opportunity study. It does not estimate a damage reduction: the direct-fire
probability law is unidentified (Sprint 21), no expected-damage model is constructed, and historical outcomes after a
withholding are not the candidate's outcomes.

## 4. Populations and inputs

`evaluation/s26-t6s-shadow/inputs.json` copies Sprint 18's committed H0 and HH pins and pins Sprint 18's `inputs.json`,
`census.json` and `admission.json`, Sprint 19's `disposition.json` and Sprint 25's private loss rows (read only for the
descriptive intersection of section 16). `protocol.json` pins the normalised SHA-256 of every source the study depends on
(the stagger shadow, the analysis, the driver, Sprint 18's census module and loader, the published range and distance
code, the free-flow relation and its routing modes, the frozen T6-G gate and Sprint 19's analysis (for one fidelity
anchor), the objective labels and the sanitizer). `scripts/s26_t6s.py run` refuses unless every pin matches. H0's
recorded actions are read in a separate pass of the same pinned files and aligned with Sprint 18's frames by decision;
the pass must reproduce Sprint 18's 123 decisions where the recorded actions differ from `baseline-v2`'s.

## 5. Definitions and the frozen trigger

* **Own ground unit**: a unit of the seat's own `operators` of type 1 or 2 (artillery included) with a readable hex;
  passengers are not operators; aircraft are not ground units.
* **Route** of a `baseline-v2` MOVE (action type 1): its `move_path`, the hexes after the unit's current hex up to the
  destination; its **first hex** is `move_path[0]` (always adjacent to the current hex, section 2).
* **Threat exposure** of a MOVE: Sprint 18's threat-exposed order predicate, which Sprint 24's entry names: a currently
  visible enemy operator of any class with a readable hex and a published direct-fire range against the mover's type
  (`evaluation/t7_candidates.weapon_range` over its `carry_weapon_ids`: personnel for type 1, vehicles for type 2) whose
  distance (`evaluation/t7_visibility.hex_distance`) to the mover's current hex, or to one of the first five route hexes,
  is at most that range. The shadow restates it so that the rule imports no analysis module; the run checks the
  restatement against Sprint 18's function on every `baseline-v2` MOVE.
* **Hex time** and **free-flow arrival**: the project's free-flow relation (`experiments/t9_batch.path_times`): per hex
  `round(720 / basic_speed * cost)` steps, with the movement mode of the unit's type and `move_state` and the cost of
  entering that hex in the setup cost graph. A unit's hex time is the first entry (current hex to first route hex);
  its free-flow arrival is the sum over its ordered route.
* **Stacked** (exposure analysis): the engine's `stack` field truthy, Sprint 18's definition.

**Mover eligibility.** A `baseline-v2` MOVE at a play decision is eligible when all of these hold, checked in this order
(the first failure is reported): the unit is an own ground unit with a readable hex; it has exactly one MOVE in this
decision's list; it is not already moving (empty observed route and no positive speed: withholding a new MOVE cannot stop
an existing movement, and a dropped MOVE is never assumed to stop a moving unit); `baseline-v2` gives it no embark or
disembark at this decision; action type 1 is listed for it in this decision's `valid_actions`; its route is non-empty
and readable; its per-hex free-flow times are readable; it is not a member of an active episode; it is re-armed
(section 8).

**Trigger.** The eligible movers of a decision are grouped by (current hex, first hex). A group of at least two movers
starts an episode when at least one member's MOVE is threat-exposed. This is Sprint 24's trigger: MOVEs for two or more
own ground units in the same hex whose routes share their first hex, a visible enemy's published range covering the
movers' hex or one of the first five route hexes, every selected action legal with a readable route, and no active or
completed episode for those units. Co-located movers with different first hexes, and movers with the same first hex
from different hexes, are not grouped.

**Action change.** At the triggering decision the leader's MOVE passes and every other member's MOVE is withheld
(dropped). No new action type, no stop command, no route redesign, no objective reassignment, no change to any shot or
other action, no global capacity reservation; the remaining actions keep their order.

## 6. The timing ambiguity, resolved before any T6-S figure

Sprint 24's entry describes the stagger twice: the followers move "one hex time later" (hypothesis), and each follower's
MOVE is withheld "until the released unit has left the shared first hex (one hex time)" (action change); its mechanism
sentence says co-located movers "enter each hex one hex time apart".

* **Documented hex time.** Under the documented movement model (PS-1, validated there on every unimpeded entry and
  again in section 2 on 259 of 302 HH ground MOVEs), a unit's `cur_hex` becomes the next hex when it enters it,
  `tau = round(720 / basic_speed * cost)` steps after its order (or after entering its current hex). One hex time for
  the leader is therefore its hex time from the shared hex to the shared first hex.
* **Formulation A** ("one hex time later"): the followers are released one hex time after the leader's order, when the
  unimpeded leader enters the shared first hex.
* **Formulation B** ("until the released unit has left the shared first hex"), read with "first hex" in the sense of the
  trigger sentence (the route's first hex): the leader leaves that hex when it enters the second route hex, two hex times
  after its order. Read as the hex the movers share at the start, it is the leader's entry into the first route hex: one
  hex time, the same event as A.
* **Agreement.** Under the first reading A and B never agree for a leader that continues beyond the first hex (the second
  hex time is positive), and B never occurs for a leader whose destination is the first hex. Under the second reading
  they are one event.
* **Frozen reading.** The second reading. Three of the four statements in the entry fix the stagger at one hex time,
  including the parenthesis attached to formulation B itself; only the first reading of B would double it. The
  registered stagger length is preserved.
* **Executable release event.** The next follower is released at the first play decision at which the **reference**
  unit (initially the leader) is absent from the own operators or is observed on a readable hex other than the shared
  start hex. Under the documented model this is the leader's entry into the shared first hex, one hex time after its
  order when unimpeded; it is state-driven, so it also waits while the leader is delayed, which a fixed clock would not.
  Relationship to Sprint 24: the same stagger length, measured by an observed event instead of an assumed clock; the
  two-hex-time reading of B is recorded and not adopted.
* **Wait bound.** When the reference has not left and `cur_step - reference release step > 2 * reference hex time + 10`
  (PS-1's stall definition, `s > 2 * tau + 10`, declared there before any data), every pending member is released at
  once. The rule then falls back to `baseline-v2`: its MOVEs pass, the members move or wait as `baseline-v2` makes them,
  and they are not held again on that hex (section 8). No stop command and no deadlock recovery is used.
* **A leader that cannot advance** (a full first hex, suppression, any other cause) is handled by the wait bound only.
  PS-1's engine probe found that a unit moving toward a hex holding four own ground units waits in place, and that a
  stop issued to such a unit is registered but never takes effect while the hex stays full; the rule issues no stop.
* **Legality at release.** The candidate never constructs or edits a MOVE. A released follower's MOVE is the one
  `baseline-v2` emits on that decision's own observation, which always carries a route with action type 1 listed for the
  unit (section 2); a MOVE with a different route or destination than at the trigger passes unchanged and is reported. If
  `baseline-v2` emits no MOVE for the follower at its release, none is manufactured and the outcome is recorded.

## 7. Leader and chain order

The members of a triggered group are ordered by (free-flow arrival, route cost, route length, unit id), all computed from
the decision's own observation: the route is the member's `baseline-v2` MOVE, the start is its observed hex, the mode
follows its type and `move_state`, the speed is its `basic_speed`, the costs are the setup cost graph. The first is the
**leader** (Sprint 24: "the mover with the earliest free-flow arrival"); the order is the release order. A member whose
free-flow times are unreadable is not eligible (it fails closed and the group is formed without it). No future death,
capture or damage enters the choice; there is no scenario-specific exception.

## 8. Multi-unit episode semantics

* **Two movers**: the leader passes; the follower is released one hex time later (section 6).
* **Three or four movers** (four own ground units at most on a hex): a chain. A follower released with a MOVE becomes
  the new reference, so the next follower waits until it has left the shared hex; unimpeded, follower `i` leaves `i` hex
  times after the leader (each predecessor's own hex time). Followers are released together only by the wait bound.
* **Independent groups** at one decision (different start hexes, or different first hexes): independent episodes,
  examined in order of (start hex, first hex).
* **Several groups entering one first hex** from different start hexes: independent episodes; no coordination between
  groups is built, and such decisions are counted.
* **Overlapping membership**: a unit belongs to at most one active episode; a member of an active episode (pending or
  released) is not eligible for another. A pending member's every MOVE is withheld until its release; its other actions
  pass.
* **One episode per stay on a hex**: when an episode completes, each member is spent at the shared start hex and cannot
  join a new episode until it has been observed on a readable hex other than that one. A co-departure that `baseline-v2`
  lists again at later decisions without the units having moved is therefore never counted as a new episode.
* **Shared routes that later diverge, different speeds**: neither changes the rule; the shared route prefix, the
  members' hex times and their historical co-location along the route are reported. An initial stagger is not assumed
  to keep the members apart (a faster follower can close the gap).
* **Passengers**: a carrier is an ordinary member; withholding it delays its passengers; carriers with passengers are
  counted.
* **Suppression changes**: not a condition of the rule; a reference that stops moving is bounded by the wait bound.
* **Disappearance**: a reference absent from the own operators releases the next follower (reason `reference_absent`);
  a pending member that is absent or observed on another hex leaves the queue (`follower_absent`, `follower_left`).
* **Game end**: an episode still open at the side's last decision is closed there with `open_at_end`.

## 9. Episode lifecycle

**Start**: the triggering decision; the leader's MOVE passes and the followers' MOVEs are withheld. **Leader release**:
at the start. **Follower release**: the release event (section 6), or the wait bound. **Completion**: the queue is
empty. **Limit**: one episode per unit per stay on a hex (section 8). Every step is a deterministic function of the
decision's own observation and the episode's recorded steps; non-play decisions pass unchanged.

## 10. The frozen shadow

`src/miaosuan_agent/experiments/t6s_stagger_shadow.py`, identity `t6s-column-stagger-shadow`, status **ANALYSIS SHADOW —
NON-EXECUTABLE** (`EXECUTABLE = False`): no agent class, not in `decision.policy.POLICIES`, in no run card, imported only
by this sprint's analysis, driver, mutation script and tests. It filters an action list that `baseline-v2` has already
produced.

## 11. Fidelity first

Before any T6-S conclusion the run reproduces, exactly, from the same loaders on the pinned inputs: H0 33,696 decisions
and 33,680 play decisions; 123 decisions where reconstructed `baseline-v2` differs from the recorded `baseline-v0` (also
by the separate recorded-action pass); HH 11,524 of 11,524 reconstructed decisions equal to the recorded seat; ground
damage events on a stacked victim H0 112 of 177 and HH 70 of 130; damage events on moving ground units H0 124 of 205
and HH 117 of 158, attacker seen before 120 and 117; `baseline-v2` move orders 509 and 416; threat-exposed move orders
230 and 200, followed by mover damage within the lookback window in 88 and 101; ground events on stacked units moving
off objectives 57 and 40 (Sprint 18's admission table, recomputed from the census rows, equal as a whole table); 13 of
the 16 H0 scenario-sides with a stacked ground victim; the frozen T6-G gate's episodes in the four HH side-games 0, 0, 0
and 0; 16 H0 and 4 HH side-games; Sprint 18's T6, N9 and N6 blocks equal to `census.json`. Each side also passes its
integrity checks: decision positions equal decision indices; one recorded list per decision; the candidate equals
`baseline-v2` before the first divergence and no group triggers before it; only MOVEs are withheld; withheld actions
equal start withholdings plus repeats; every episode keeps its leader's MOVE and withholds its followers' MOVEs; no unit
is in two overlapping episodes; the shadow's threat restatement equals Sprint 18's predicate on every MOVE. Any
discrepancy makes the study `T6_S_INVALID`; no definition is changed to fit.

## 12. Trigger census (per side-game, per population, pooled)

Decision-level counts over play decisions (a co-departure listed again at a later decision counts again; these are not
episodes): `baseline-v2` MOVE orders; ground MOVE orders; same-hex co-departure groups (two or more ground MOVEs from one
hex) and their MOVEs; same-hex groups whose MOVEs all share one first hex; groups sharing a first hex; those with a
threat-exposed member. The shadow's mover checks and group outcomes. **Episodes** (the frozen trigger under the state
machine), those at the first divergence and after it; distinct units, leaders and followers; group sizes; projected
follower waits (section 15); member classes, hex times and whether they differ; members stacked at the start and own
ground units on the start hex; carriers with passengers; shared route prefix; destination kinds (objective held, not
held, not an objective); decisions with two triggered groups into one first hex; side-games, games, scenario-sides and
distinct starting setups (scenario and colour; HH's two openings are H0's 2130511121 sides) with an episode.

## 13. Exposure analysis (historical, descriptive)

Over play decisions: moving own ground unit-decisions (Sprint 18's `moving`: a non-empty route or a positive speed),
stacked and alone, and of each those inside an applicable envelope (a visible enemy's published range against the unit's
type covers its hex); damage events on moving ground units, stacked victims against alone (Sprint 18's admission rows).
For each episode whose members' recorded actions at the start contain their `baseline-v2` MOVEs (followed on the
record; always in HH, in H0 only where the recorded stream did the same), within the follow-up window of 300 steps:
whether two members were co-located while moving on a hex other than the start hex (stayed stacked farther along the
route) or not (separated after the start hex); on how many such hexes and decisions; moving stacked member
unit-decisions inside applicable envelopes; the leader's recorded departure from the start hex. Member damage events
within 75, 150 and 300 steps of the start. The results then state whether staggering would have a plausible mechanical
opportunity to reduce stacked moving exposure, as a description of these figures. No causal damage reduction and no
expected-damage model is computed.

## 14. First divergence and the action-level check

The shadow runs on every recorded decision of each analysed side from an empty memory, on `baseline-v2`'s list. The
**first divergence** is the first decision at which the candidate's list differs from `baseline-v2`'s, the side's first
episode start. Its certificate (public without identities, hexes or routes) states the decision and step, the episodes
started, their group sizes and classes, the action types before and after, and three verified facts: only follower MOVEs
were withheld, the leaders' MOVEs were kept, and every unrelated action is unchanged and in order. In HH the recorded
prefix is the `baseline-v2` seat's own trajectory, so the first divergence is a valid action-level fact. In H0 it is valid
only if the recorded `baseline-v0` actions equal `baseline-v2`'s at every earlier decision of that seat (Sprint 23's
boundary); otherwise it is descriptive and is not called an on-policy `baseline-v2` witness. Episodes after the first
divergence are replays on off-policy recorded states; on HH the followers moved on the record at the trigger, so replay
releases and waits describe the record, not the candidate, and are reported apart.

**Independent check** (zero unexplained differences required at every decision): the candidate list must be
`baseline-v2`'s with some actions removed and the rest in order; each removed action must be a MOVE of an own ground unit
with a readable hex that is not moving; a unit's first removal must have, at that decision, a kept MOVE of another own
ground unit on the same hex with the same first hex, a threat-exposed MOVE among those same-hex, same-first-hex MOVEs
by Sprint 18's own function, and readable free-flow times for the removed MOVE; later removals of the unit must occur
while it stays on that hex and within `(n - 1) * (2 * t + 11)` steps of its first removal (`n` those MOVEs, `t` the
largest readable hex time among them); a unit cannot be held twice on a hex it has not left. This restatement uses
Sprint 18's predicate and its own bookkeeping, not the shadow's state.

## 15. Onward-capture cost

For every withheld follower (registered for stop C, descriptive otherwise), from the historical trajectory: its MOVE's
destination (the route's last hex) as an objective the side holds, does not hold, or not an objective; whether the side's
first-ever play-stage ownership of that objective comes after the episode start and the follower stands on its hex at
that decision (**historical first owner**, Sprint 23's measure); the steps from the start to that first ownership;
whether other own units were also first owners; whether the objective was first owned before the start or never; the
**projected wait** (the sum of the hex times of the members released before it, a free-flow lower bound); its free-flow
arrival; whether the projected wait would carry its free-flow arrival past the game's end (`arrival <= steps left <
arrival + wait`), reported separately, and whether it could not arrive even at free flow; whether it was lost later in the
recorded game. These are historical risk labels. No claim is made that the candidate would delay a first ownership by
any amount.

## 16. Relation to Sprint 25 (descriptive, outside the stops)

For each of Sprint 25's multi-defender order-vacating losses (its private rows; 28 expected, a mismatch voids this
intersection only), first match: ordered at several decisions; ordered at one decision from different hexes; same hex,
different first route hexes; no qualifying visible threat; `baseline-v2` did not emit the same MOVEs (H0); the frozen
trigger, evaluated statelessly on `baseline-v2`'s list at that decision, does not group at least two of those defenders;
the trigger holds at a valid first divergence; the trigger holds after a divergence or without prefix support. No claim
is made that staggering keeps a garrison, and T13's failure is not read as evidence for T6-S.

## 17. Stop conditions

Sprint 24's three offline stops, with their denominators fixed now:

* **STOP A, HH opportunity**: met when any of the four registered HH side-games has fewer than 10 episodes, or when the
  four are not all present. Episodes are counted over every recorded decision of the side-game under the frozen state
  machine, Sprint 19's reading of the identical "fewer than 10 per side-game" item for T6-G; after the first divergence
  they are historical opportunity on recorded states, not candidate behaviour, and are reported apart. (Counting only
  first divergences would make the stop unpassable by construction, since a side-game has one; Sprint 23's readiness
  rule, which read first-divergence episodes only, had no per-side-game minimum.) A failing side-game is not rescued by
  a pooled total.
* **STOP B, H0 generality**: met when episodes occur in fewer than four distinct H0 scenario-sides (H0's 16 side-games
  are 16 distinct scenario-sides; no replica is counted twice).
* **STOP C, onward-capture conflict**: an episode is **at first-owner risk** when at least one withheld follower is a
  historical first owner of its ordered destination (section 15); each episode counts once. Denominator: the episodes of
  H0 and HH together (Sprint 24: "more than half of the episodes"), replicas de-duplicated by scenario-side, start step,
  start hex, first hex, members and routes, an identical episode being at risk if it is at risk in any replica. Met when
  there is no episode, or when `2 * at-risk episodes > episodes` (strictly more than one half; exactly one half passes).
  H0-only and HH-only shares and unit-level counts are reported beside it.

Every stop is computed and reported whatever decides the disposition. Thresholds are not changed after the run.

## 18. Dispositions (first match)

1. `T6_S_INVALID`: an input or source pin, a fidelity anchor or block, a side's integrity check, the action-level check
   (any unexplained difference) or the run's public-output gate fails.
2. `T6_S_INADEQUATE_OPPORTUNITY`: STOP A or STOP B met.
3. `T6_S_ONWARD_CAPTURE_RISK`: opportunity passes and STOP C is met.
4. `T6_S_OFFLINE_PASS`: all integrity requirements hold and no stop is met. It means only that a small engine mechanism
   probe may be proposed; it does not establish reduced damage, improved survival or a better score.

## 19. Afterwards

**If `T6_S_OFFLINE_PASS`**: a DRAFT registration of a two-session head-to-head mechanism probe (2130511121, both seat
orders, the T6-S rule as an add-on on `baseline-v2` against frozen `baseline-v2`, the candidate's own on-policy
observations at every decision) is written for the owner, with observable endpoints under consistent denominators
(episodes executed, actual waits, leader/follower separation, stacked moving unit-steps inside applicable envelopes,
damage to exposed movers, deaths while waiting, onward first-ownership timing, unexplained non-T6 differences), no score
as a rescue criterion, and no reading of reduced stacked movement alone as improved survival. It is not executed and
session 2797 is not opened. **Otherwise** T6-S is not repaired in this sprint (no smarter routing, objective-aware
priority, enemy prediction, dynamic rearrangement, capacity assignment, group garrison or learned damage weights); the
negative result is recorded, only this formation-stagger increment of T6 is closed (T6's route-choice branches stay
open), and exactly one next task is recommended.

## 20. Outputs, privacy and checks

* Public, `evaluation/s26-t6s-shadow/`: `protocol.json` and `inputs.json` (this registration), `mutation.json`, then
  `fidelity.json`, `census.json` (side summaries, population and pooled tables, moving-damage table), `divergence.json`
  (certificates), `episodes-H0.json` and `episodes-HH.json` (one sanitised row per episode; a table over 90,000 bytes is
  split in order into numbered parts), `intersection.json` (section 16) and `disposition.json`. Aggregates, steps,
  distances, classes and labels only. Every file passes the project sanitizer (forbidden keys anywhere; the private
  hexes and unit identifiers of the inputs as keys or words, numeric leaves masked) and carries no word made only of
  digits other than a scenario identifier, or the run writes nothing. `run --check` regenerates every file byte for byte.
* Private: `local/diagnostics/s26/study-private.json.gz` on the evaluation server.
* Code: `experiments/t6s_stagger_shadow.py`, `evaluation/s26_t6s.py`, `scripts/s26_t6s.py`, `scripts/mutate_s26.py`;
  tests `tests/test_t6s_stagger_shadow.py`, `tests/test_s26_t6s.py`, `tests/test_s26_driver.py`,
  `tests/test_s26_results.py` (binds the protocol to the sources and, after the run, the results to the rules) and
  `tests/test_real_s26.py` (server regeneration).
* Close-out: deterministic regeneration; mutation; a private documentation gate with planted errors; the earlier current
  gates; the workstation suite, a clean GitHub clone and the server's private suite; the privacy scan compared exactly
  with the 106 accepted lines; the platform canary rebuilt; a read-only ledger verify (2,796 sessions, none unclosed, no
  session 2797).

## 21. Validation before this registration

* Synthetic tests: the shadow (35 tests: co-located movers sharing the first hex; the same hex with different first
  hexes; different hexes with the same next hex; no MOVE; one MOVE; no visible threat, an unpublished range and an
  indirect weapon; the envelope boundary on the start hex and on the fifth route hex, and a threat covering only the
  sixth; one exposed member; several threats; every mover check; non-play decisions; independent groups; unchanged
  non-MOVE actions; the leader by free-flow arrival rather than by first-hex time; different speeds; every tie level;
  the frozen free-flow relation over a stand-in cost graph; the exact release boundary; three followers released one
  hex time apart; a follower without a MOVE at release, not manufactured; a disappearing leader; the exact timeout and
  its measurement from the reference's release; followers absent or gone; repeats while pending; an unreadable
  reference hex; membership of an active episode; one episode per stay on a hex and re-arming; a bounded hold over the
  next 399 decisions; identity, frozen parameters, the files that may name the shadow and labels without number words); the
  analysis (33 tests: first divergence, release and the action-level check on a replay; follow-up on and off the
  record; onward first-owner risk, first ownership before the start or by others only, a destination that is not an
  objective, the end-of-game projection; damage windows; H0 prefix-fidelity failure and HH exact reconstruction; later
  episodes as post-divergence; every independent-check refusal, including an excluded unreadable co-mover that must not
  count as unexplained; stop A at exactly ten and a missing side-game; stop B at exactly four and a repeated
  scenario-side; stop C at exactly one half, above it, with no episode and across replicas; disposition precedence; the
  decision-level census and exposure counts; every Sprint 25 category; the public outputs with private-like identifiers
  below fifty and hexes on the same row, a planted number word caught, no private field name, registered labels
  without number words); the driver (11 tests: the recorded-action pass, labels, the file split, every input pin, the
  anchors against the published Sprint 18, 19 and 25 files, the protocol's frozen values and its labels, the fidelity
  rule on a stand-in loader with nine planted differences, the moving-damage table); the protocol pin and the result
  checks that run after the study (`tests/test_s26_results.py`); the server regeneration (`tests/test_real_s26.py`).
* Mutation (`scripts/mutate_s26.py`, record `evaluation/s26-t6s-shadow/mutation.json`): the first run killed 59 of 59
  planted defects; every mutant compiles, and a sample of six was confirmed killed by the targeted assertion, not by an
  import error. A review afterwards found a defect of the analysis itself: the independent check would have called a
  correct withholding unexplained when a co-located mover the shadow had excluded for unreadable free-flow times sat in
  the group (it required every group member's times). It now requires only the removed MOVE's own times; a test of that
  case and a sixtieth mutant were added. The final run on the registered tests and sources killed 60 of 60 after the
  unmutated tests passed in the copy.
* Smoke on the evaluation server with a never-firing shadow (the minimum group size set out of reach): every fidelity
  anchor (27) and block (8) held, all 20 side-games passed their integrity checks, nothing was withheld, the candidate
  equalled `baseline-v2` at every decision and there was no unexplained difference.
* `protocol.json` and `inputs.json` were written by `freeze` on the evaluation server from these sources; the protocol pin
  test passes on the workstation, so both hosts derive the same protocol.

## 22. Not claimed

No tactic is shown to work or fail. An episode is an eligible historical target of the registered rule, not a delay the
candidate made; replay waits describe recorded states; onward labels are historical, not counterfactual; nothing here
estimates a damage, survival or score effect.

## Results (2026-10-09)

Every figure below is read from the committed public files of `evaluation/s26-t6s-shadow/`, which `scripts/s26_t6s.py
run --check` regenerates byte for byte on the evaluation server, unless it is labelled post hoc.

### R1. Order of work

The registration (`c3fc731` to `20453dcafa870313ec4b9fe2e9f04f2b116ddf99`, tree
`2e6703c616a6f7dac5ff5f87e54456fb2afd49d3`, twelve commits) was pushed at 2026-10-09T00:00:57+08:00 after the
workstation suite passed on it (2,191 tests, 105 skipped) and the privacy scan of every reachable blob (1,105) matched
the 106 accepted lines exactly. A fresh GitHub clone had the same commit and tree, its 13 registered files were
byte-identical, and its suite passed (2,188 tests, 113 skipped). The evaluation server's main clone was fast-forwarded
to it by bundle, `freeze --check` passed there, and `run` was started once; it wrote the nine result files and the
private rows (finishing at 16:15:24Z by the server's clock). `run --check` then regenerated every public file and the
private rows byte for byte. No engine was called and no definition, threshold or stop was changed after the run.

### R2. Fidelity

All 27 anchors and the 8 blocks are reproduced exactly (`fidelity.json`): H0 33,696 decisions and 33,680 play
decisions, 123 recorded/`baseline-v2` differences (also by the separate pass); HH 11,524 of 11,524 reconstructions equal
to the recorded seat; stacked ground victims 112 of 177 and 70 of 130; moving ground damage 124 of 205 and 117 of 158,
attacker seen before 120 and 117; move orders 509 and 416; threat-exposed orders 230 and 200, then damaged 88 and 101;
stacked units moving off objectives 57 and 40 (the whole admission table equal); 13 of 16 H0 scenario-sides with a
stacked ground victim; T6-G gate episodes 0, 0, 0 and 0; 16 and 4 side-games; the T6, N9 and N6 blocks. All 20
side-games pass every integrity check, and there is no unexplained action difference at any decision.

### R3. Trigger census

Decision-level counts (a co-departure listed again counts again; `census.json`):

| | H0 | HH |
|---|---:|---:|
| `baseline-v2` MOVE orders | 509 | 416 |
| ground MOVE orders | 391 | 302 |
| same-hex co-departure groups (their MOVEs) | 113 (271) | 78 (186) |
| of which all MOVEs share one first hex | 99 | 74 |
| groups sharing a first hex | 101 | 76 |
| of which with a threat-exposed member | 65 | 54 |

Every ground MOVE passed the mover checks (the other MOVEs were aircraft: 118 and 114); no MOVE was excluded as already
moving, unlisted, unreadable, in an active episode or not re-armed. The state machine therefore neither added nor
removed anything: in every side-game the episodes equal the threat-exposed groups sharing a first hex.

| Side-game | Episodes | after the first divergence | Distinct units | Followers | Projected wait (median, max) |
|---|---:|---:|---:|---:|---|
| H0 1930331196 red | 15 | 14 | 6 | 34 | 40, 120 |
| H0 1930331196 blue | 9 | 8 | 10 | 9 | 40, 144 |
| H0 2120531121 red | 6 | 5 | 8 | 8 | 20, 40 |
| H0 2120531121 blue | 5 | 4 | 9 | 7 | 20, 40 |
| H0 2130511121 red | 9 | 8 | 13 | 17 | 40, 60 |
| H0 2130511121 blue | 21 | 20 | 13 | 25 | 20, 144 |
| HH p01 baseline-v2 blue | 16 | 15 | 10 | 19 | 20, 120 |
| HH p02 baseline-v2 red | 10 | 9 | 11 | 17 | 20, 60 |
| HH p03 baseline-v2 blue | 14 | 13 | 11 | 16 | 20, 60 |
| HH p04 baseline-v2 red | 14 | 13 | 10 | 24 | 20, 60 |

The other ten H0 side-games (five scenarios, both sides) have no episode: they hold 1 to 14 ground MOVEs each, and
their groups sharing a first hex, where there are any, had no threat-exposed member. In count units: 119 episodes (H0
65, HH 54) in 7 games and 10 side-games; 6 H0 scenario-sides in 3 scenarios; 6 distinct starting setups over both
populations (HH's two openings are H0's 2130511121 sides); 101 distinct units by side-game, 295 member instances, 176
followers. Group sizes: two 72, three 37, four 10. Every member was stacked at the start (295 of 295); 289 were vehicles
and 6 infantry (three infantry-only groups, in H0); within every group the members had equal hex times, the same
destination and identical routes (2 to 15 hexes; three hexes in 68 groups). Carriers with passengers appear in 54
member instances. No decision had two triggered groups converging on one first hex.

### R4. First divergences

Each of the 10 side-games with an episode diverges first at its first episode (`divergence.json`); in every certificate
only follower MOVEs were withheld, the leaders' MOVEs were kept and every unrelated action is unchanged and in order.

| Side-game | Decision | Step | Prefix supported | Group | First-owner risk |
|---|---:|---:|---|---|---|
| H0 1930331196 red | 381 | 380 | yes | vehicle x2 | no |
| H0 1930331196 blue | 682 | 681 | no | vehicle x2 | yes |
| H0 2120531121 red | 282 | 281 | no | vehicle x3 | yes |
| H0 2120531121 blue | 361 | 360 | no | vehicle x2 | yes |
| H0 2130511121 red | 402 | 401 | no | vehicle x3 | no |
| H0 2130511121 blue | 162 | 161 | no | vehicle x2 | yes |
| HH p01 baseline-v2 blue | 162 | 161 | yes | vehicle x2 | yes |
| HH p02 baseline-v2 red | 402 | 401 | yes | vehicle x3 | yes |
| HH p03 baseline-v2 blue | 162 | 161 | yes | vehicle x2 | yes |
| HH p04 baseline-v2 red | 402 | 401 | yes | vehicle x3 | yes |

The four HH certificates are valid action-level facts on the genuine `baseline-v2` seats, at two distinct openings
(blue at step 161, red at step 401, each played twice). In H0 only 1930331196 red's is an on-policy `baseline-v2`
witness; the other five H0 sides had already diverged from `baseline-v2` before their trigger. The remaining 109
episodes are replays on off-policy recorded states.

### R5. Stacked exposure (historical, descriptive)

| | H0 | HH |
|---|---:|---:|
| moving own ground unit-decisions | 174,360 | 134,765 |
| stacked | 67,500 | 60,219 |
| stacked inside an applicable envelope | 45,816 | 51,377 |
| alone | 106,860 | 74,546 |
| alone inside an applicable envelope | 38,283 | 34,099 |
| damage events on moving ground units, stacked victims / alone | 72 / 52 | 60 / 57 |

All 119 episodes were followed on the record (every member's recorded action at the start was its `baseline-v2` MOVE).
Within 300 steps the members were co-located while moving on a hex other than the start hex in 107 (H0 60, HH 47) and
separated after the start hex in 12 (H0 5, HH 7); moving stacked member unit-decisions inside applicable envelopes in
that window sum to 35,080 (H0) and 27,075 (HH), counted per episode. The leader's recorded departure from the start
hex came a median 20 steps after the start (H0 12 to 144, HH 1 to 252). So the columns the rule would stagger did,
historically, travel stacked inside envelopes beyond their start hex in most episodes: staggering has a plausible
mechanical opportunity to reduce stacked moving exposure. Whether it would reduce damage is not measured here.

### R6. Projected delays and historical damage

The projected wait of the 176 followers is a median 20 steps (one vehicle hex time; 20 to 144; H0 median 30, HH 20). No
follower's projected wait would carry its free-flow arrival past the game's end; 2 H0 followers could not arrive even at
free flow. Members damaged within 75, 150 and 300 steps of the start: H0 16, 33 and 54, HH 23, 35 and 61; of the
followers H0 3, 13 and 21, HH 10, 13 and 28. These are historical; a follower that waits stays exposed in place, and no
damage difference is inferred.

### R7. Onward first-owner risk

Every follower was headed to an objective its side did not hold (176 of 176). Historically 37 followers (H0 21, HH 16)
were among the first owners of their destination, a median 81 steps after the start (61 to 301; HH 61 to 81), against a
projected wait of a median 20 (20 to 120); the destination of 66 had been first owned before the start and of 4 never;
in 104 cases other own units were among the first owners; 112 followers were lost later in their game. At the episode
level 26 of the 119 raw episodes are at risk (H0 15 of 65, HH 11 of 54). After replica de-duplication 88 distinct
episodes remain (H0 65; HH 23, its other 31 repeating an earlier episode of a replica game), of which 18 are at risk
(H0 16, one of them at risk only in its HH replica; HH 2).

### R8. Relation to Sprint 25 (descriptive)

Sprint 25's private rows reproduce its figures: 28 multi-defender order-vacating losses, 81 last-defender instances, 27
ordered at one decision (`intersection.json`). First match: ordered at several decisions 1 (HH); no qualifying visible
threat 2 (H0); the frozen trigger holds at a valid first divergence 2 (HH); it holds after a divergence or without
prefix support 23 (H0 18, HH 5). No case was split across hexes or first hexes, and `baseline-v2` emitted the same MOVEs
in every H0 case. The collective departures that emptied held objectives are, almost all, co-departures T6-S acts on;
this does not show that staggering would keep an objective.

### R9. Stop conditions

| Stop | Registered quantity | Result | Met |
|---|---|---|---|
| A, HH opportunity | episodes in each HH side-game (at least 10) | 16, 10, 14, 14 | no |
| B, H0 generality | H0 scenario-sides with an episode (at least 4) | 6 | no |
| C, onward-capture conflict | distinct episodes at first-owner risk (more than one half fails) | 18/88 | no |

STOP A passes at its threshold in HH p02 (exactly 10).

### R10. Disposition: T6_S_OFFLINE_PASS

Fidelity and every integrity check hold, no action difference is unexplained, and no stop is met. This means only that
a small engine mechanism probe may be proposed. It does not establish reduced damage, improved survival or a better
score. Nothing is promoted and session 2797 is not opened. The DRAFT two-session probe proposal is
`docs/SPRINT26_T6S_PROBE_DRAFT.md`, returned to the owner and not executed.

### R11. Post-hoc facts (read after the disposition; they change nothing)

From the committed episode rows:

* **The valid first divergences are all at risk.** Each of the four HH first divergences (two distinct openings)
  withholds a follower that was a historical first owner of its destination, and in all four another own unit was a
  first owner of it too. Every at-risk raw episode starts before step 900. The registered stop reads all episodes and
  passes; on the genuine `baseline-v2` trajectory the first stagger meets a first ownership every time.
* **Co-owners are the rule.** In 24 of the 26 raw at-risk episodes another own unit was also on the objective at its
  first ownership. Whether a 20-step follower delay delays the ownership itself (under the published capture rule one
  unit on the hex can occupy it) is what the probe's first-ownership endpoint measures.
* **The opportunity is concentrated.** H0's episodes come from three of the eight scenarios, the three of 2,880 steps;
  HH's from one scenario.

### R12. What Sprint 26 shows

1. **`baseline-v2` sends stacked columns along identical routes under visible threat, repeatedly.** 119 such
   co-departures in 10 side-games; every member stacked at the start, every column with one route and one destination,
   and most of them historically still stacked inside envelopes beyond their start hex.
2. **The frozen stagger rule can act on them without touching anything else**, with zero unexplained differences and a
   projected cost of about one hex time per follower.
3. **The cost question is open at the opening.** Overall 18 of 88 distinct episodes withhold a historical first owner,
   but every valid first divergence on the genuine `baseline-v2` seats does, with another own unit as a co-owner.

### R13. Process notes

* The first mutation run killed 59 of 59; a review after it found the independent check's over-strict timing condition
  (section 21), fixed before registration with a test and a sixtieth mutant; 60 of 60 since.
* The draft disclosure listed documents not yet read; they were read before registration (the T1-r diagnosis, PS-1's
  engine probe results, Sprint 23's evidence boundary and readiness rule, the frontier rows) and the sentence names
  exactly what was read.
* The protocol's first draft carried words made only of digits in its stop texts; the thresholds became named numeric
  fields before the freeze, and a test refuses such words in the protocol.
* Several hand-written test expectations were wrong and were corrected against the rule before registration (a hex
  inside an envelope, a reordered candidate's single problem, a follow-up count that includes the start hex, a chain
  order, an active-episode scenario).
* A shell heredoc failed to parse while these results were appended; nothing was written by it, and the text was
  appended through a file instead.
* **Errata in the registered text (not edited there).** A check of every quoted span after the run found two that are
  not their sources' exact words. Section 2's "whether stacked" translates the observation reference's description of
  `stack`, which is in Chinese. Section 17's "fewer than 10 per side-game" paraphrases Sprint 19's item, whose words are
  "the gate fires fewer than 10 times per side-game" (Sprint 24's: "fewer than 10 trigger episodes per HH side-game").
  Neither changes a definition, threshold or result.

### R14. Recommendation (one)

Owner review of the DRAFT two-session T6-S mechanism probe (`docs/SPRINT26_T6S_PROBE_DRAFT.md`) and, if approved, its
separate registration: an executable T6-S add-on with its own identity, tests and card, run in 2130511121 in both seat
orders against frozen `baseline-v2`. Why this one: the offline gate the owner set has passed on its registered terms;
the probe is the smallest engine step that measures what this study cannot (actual waits, separation, and the
first-ownership cost at the opening, where every valid first divergence carries the risk); and it needs two sessions.
Session 2797 is not opened without that approval.

### R15. Close-out

* The results were pushed as `a52944f091044014445a573de080e92e201927d5` (tree
  `30ebd6780224b7da17566289b9dcebdb88bddc50`) at 2026-10-09T00:25:32+08:00; a fresh clone from GitHub had the same commit
  and tree and byte-identical files. The evaluation server's run outputs were checked equal to their committed blobs
  before its main clone was fast-forwarded to the commit by bundle. All 17 sprint commits up to the results were audited
  as a set (author, single-line ASCII subjects of at most 72 characters, no body).
* Tests at that commit: the workstation tree ran 2,191 tests (98 skipped) with exit 0; a clean clone from GitHub 2,188
  (106 skipped) with exit 0; the evaluation server's private tree 2,204 (7 skipped; 7,736 s) with exit 0, the exit
  code persisted by the suite's launcher and the tested commit recorded beside it, with the ledger file byte-identical
  before and after. The suite was not repeated: no code or test input changed after it.
* Documentation gates: this sprint's private gate (`local/diagnostics/s26/doc_gate.py`) binds the results and this
  close-out to the public files and the copied logs and catches all its planted errors; all 28 current gates pass with
  their plants, and the four retired `_v1` copies fail as at Sprint 25's close-out.
* Privacy: the 106-line accepted set passed its independent integrity check again, and the scan of every reachable blob
  at the results commit (1,118 blobs) gives 106 hit lines, identical to the accepted set; no line was added or removed.
* Platform canary: rebuilt on the workstation and the server, SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, no smoke mismatch on either host.
* Engine ledger: read-only verify after the server suite, 2,796 sessions opened and closed, none unclosed, integrity
  ok, state chain continuous, the last event the close of session 2796; ledger file SHA-256 unchanged from the start of
  the sprint; no session 2797. No engine installation, configuration or historical result was touched, and the server's
  development worktree was removed.
* The registered disposition stands as `T6_S_OFFLINE_PASS`. The probe in `docs/SPRINT26_T6S_PROBE_DRAFT.md` remains a
  DRAFT, unapproved, unregistered and not executed.
