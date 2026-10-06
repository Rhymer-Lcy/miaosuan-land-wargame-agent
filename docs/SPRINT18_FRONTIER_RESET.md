# Sprint 18: tactical frontier reset and next-family selection

**REGISTERED — OFFLINE — NO ENGINE SESSION — RESEARCH SELECTION, NOT EVIDENCE THAT ANY TACTIC WORKS — NOTHING PROMOTED**

On 2026-10-06 the owner shelved T9 (`docs/TACTICAL_FRONTIER.md`, hypothesis register) and opened Sprint 18: an
offline reset of the tactical frontier that selects the next tactical research family from all evidence available
through Sprint 17. No engine session is authorized; session 2796 is not opened. Dates are business dates in UTC+8.

Sections 1 to 13 are the registration. They are committed and pushed, with the frozen rubric
(`evaluation/s18-frontier-reset/rubric.json`), before any census figure of this sprint is computed and before any
candidate experiment is scored, and are not edited afterwards. Results follow in a separate section.

## 1. Starting state and the owner's decision

| Item | Identity |
|---|---|
| Repository | `main` `cf6ae7c427fa1c5aff8dfb3ad1c751cae16cad7a`, tree `f6168b0029946b401ce26d8966205e563c25636b`, identical on the workstation, GitHub and the evaluation server at the start of the sprint |
| Engine ledger | 2,795 sessions opened and closed, none unclosed, integrity ok, state chain continuous (read-only verify at the start of the sprint); ledger file SHA-256 `65c803504b6f93f6e6d2a7e36892078a9cd116924fbb819a8dbb595a4039e8de` |
| Privacy baseline | the 104 hit lines accepted at Sprint 14's close, reproduced as the same set of lines at the start of this sprint |
| `baseline-v2` | policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae`, unchanged |

The owner's decision is recorded in the frontier's hypothesis register (T9 `SHELVED`, 2026-10-06) by the first commit of
this sprint. It is not a rejection of Sprint 9's registered primary result (+305.47, interval 172.87 to 611.24 in
2130511121), which stands; it pauses the T9 line because no deterministic, seat-local revision found through Sprint 17
both restored the primary redistribution mechanism and avoided the registered adverse mechanisms. No historical result
file is changed by this sprint.

## 2. Scope and the nature of the evidence

* Offline only. Every input is a record, capture or document that exists at the start of the sprint. No engine session,
  no new policy in any run card, no change to `baseline-v2`, the stable core, the registered evaluator or any historical
  output.
* The supplemental census re-reads historical data that earlier sprints have already examined. It is a description of
  capability and opportunity, not an untouched validation set, and nothing here is a test of a tactic.
* The selection prioritises the next research increment. A selected family is a research priority, not a promising
  result; it enters the hypothesis register as `IDEA`, and its first experiment is returned to the owner for approval.
* Engineering restraint: only what the census, the scoring, their reproducibility and privacy-safe output need. No
  experimentation framework, no refactoring of earlier evaluation code, no simulator.
* External sources may inform generic concepts (threat-aware path planning, transport doctrine, fire allocation,
  concealment and the like). Nothing private is sent out: no capture, unit identifier, coordinate, scenario data,
  licensed SDK content, credential or trajectory. Any conceptual influence is recorded in the results; no external code
  is imported.

## 3. Evidence seen before this registration (disclosure)

Before writing sections 1 to 13 the author read: the frontier and every sprint document named in the owner's brief; the
published census and rubric of Sprint 1 (`evaluation/tactical-frontier-1/`); the engine's published rules and action
reference (local copies of the platform documentation, not in the repository); the SDK sample agent's list of action
generators; the field names of a scenario file, a game record, a replay-corpus row and a full-step timeline; and an
inventory of which records and capture formats exist on the evaluation server (folders, record counts by policy pair
and condition, capture file kinds). No count of an outcome, a loss, an opportunity or a listing was computed from
private data for this sprint before this registration. Facts already published by earlier sprints are used as they
stand, notably: Sprint 1's census (action 7, "remove suppression", listed in 1,687 of 33,680 play decisions of the
replay corpus, embark in 77, disembark in 256, guided fire in 1); Sprint 5's T7 audit and A2 trigger (234 activations
of 49 units in the replay corpus); Sprint 6's concealment facts; Sprint 7's finding that no genuine `baseline-v2` seat
re-commands an idle unit after 75 or more idle steps; Sprint 12's finding that the 27 holders behind never-honoured
places were all destroyed en route.

Two documented rules shaped the candidate list before any count: the platform's rules let a concealed unit leave
concealment by moving or firing at no time cost, but concealment does not affect observation by an observer higher than
a target vehicle; and the action reference lists "remove suppression" (type 7) without describing its effect, while the
SDK sample agent issues it at random. Neither is evidence of tactical value.

## 4. Families: excluded, active and new

**Excluded from re-selection** (they may appear in tables only as historical context and are not scored): T1 and T1-r
(shelved: stacking and the unavailable recovery mechanism), PS-1 (shelved), T4 (shelved after its exploratory
artillery results), T9 (shelved by the owner's decision above).

**Active candidates** (each scored on its best next increment, section 8): T2 transport and infantry defence; T3
reconnaissance and enemy belief; T5 guided fire and correction; T6 threat-aware movement; T7-C concealment of idle
stationary units (scored on its next increment, not as an untouched family); T8 specialised assets; TO-1 target
ownership (backlogged; scored on its registered next step).

**New families** (section 7): any family admitted by the structured scan gets the next free identifier from T10 on, in
the order of admission, and is scored with the same frozen rubric.

## 5. Populations and inputs

All inputs are pinned by SHA-256 in `evaluation/s18-frontier-reset/inputs.json` by `scripts/s18_census.py freeze`
before the census runs; the census refuses to run on any input whose digest differs.

| Id | Population | Use |
|---|---|---|
| S | the 50 historical scenarios of the SDK 4.1.0 archive and the 8 frozen scenarios among them (the archive's digest as pinned by the local checksum list) | capability presence (generality G) and starting configuration (for example infantry starting on board) |
| H0 | the 8 replay-corpus games (`baseline-v0` against itself, C1, both seats, every decision's seat observation; pinned in `evaluation/routing-remediation-1/corpus.json`) | the main active-opponent population: 16 scenario sides; `baseline-v2`'s decision is reconstructed seat-locally on every recorded observation with its own memory, as Sprint 5 did, so behaviour figures are `baseline-v2`'s decisions on `baseline-v0` trajectories |
| HH | the 4 full-step timelines of Sprint 12 (`s12-v3-primary-1`, 2130511121, `baseline-v2` against v3, both seat orders) | the only full-step captures with a genuine `baseline-v2` seat against an acting opponent; the analysed side is the `baseline-v2` seat, the v3 seat is the opponent |
| HI | the 5 full-step timelines of Sprints 16 and 17 (v3 or its v6 variant against the inert control) | listing, starting-configuration and movement-timing figures only; no threat or loss figure (the inert side never acts) |
| R | every completed game record under the evaluation server's record folders, except the 360 records of `baseline-v2-target-ownership-prevalence-1`, whose registered stop keeps its data unexamined | issued action types by policy; final-score composition of `baseline-v2` games against an acting opponent (C1 mirrors and head-to-head) |

Capture formats that keep only event windows or sampled steps (Sprints 2, 4, 6 and 10, the 516 diagnostic and the
split-screen smoke) are not used: they cannot support per-step counts. The census reports which folders it read and
which it left out, and why.

## 6. Census definitions (fixed now)

Common definitions. A side's own units are the units of its colour in its own seat observation (`operators`); units on
board are those in `passengers`. A damage event is a `judge_info` record whose `damage` is a positive number; records
are de-duplicated across seats by their full content, and an event is placed at the first decision whose observation
carries it. The victim's state at an event is read from the victim side's own observation at that decision: moving
(non-empty `move_path` or positive `speed`), stationary, on an objective hex (its `cur_hex` is a city coordinate),
stacked (`stack` truthy), in close combat (`close_combat` truthy), on board, aircraft (type 3). An attacker is seen
before an event when its identifier appears among the victim side's visible enemy operators at any decision within the
300 steps (`cur_step`) before the event, and seen at the event when it appears at that decision. A unit is lost when it
leaves both `operators` and `passengers` of its own seat observation for the rest of the game. Hex distance is the
project's cube-coordinate distance (`evaluation/t7_visibility.hex_distance`); published weapon ranges and observation
distances are those already coded in `evaluation/t7_candidates.py`.

Per family, on H0 (both seats), on HH (the `baseline-v2` seat) and, where stated, on HI and S:

| Family | Figures |
|---|---|
| T7-C | the A2 trigger (Sprint 5's `t7_idle_concealment` shadow, unchanged) as unit-decisions and units; damage events on a triggered unit at least 75 steps after its first trigger while it still has no move path ("concealable damage"), split by attacker class (ground or aircraft), by whether the event `distance` exceeds half the attacker's published observation distance for the target class, and by whether `ele_diff` is 0; units `baseline-v2` orders to move or shoot 75 or more steps after their first trigger (E3b exposure); the published Sprint 5 figures (234 activations, 49 units) reproduced on H0 as a consistency check |
| T2 | infantry starting on board versus on the ground (S, H0 and HI first play decision); decisions and unit-decisions listing embark (3) or disembark (4), by actor class; actions 3 and 4 issued by `baseline-v2`; infantry squads still on board at the end; damage events whose victim is on board; for every `baseline-v2` infantry move order, the free-flow travel time along its route (Sprint 11's lower bound, hex time `720 / basic_speed * cost`) against the steps left, and the same for vehicles; infantry units that never stand on an objective hex |
| T6 | damage events and lost units by victim state; for events on moving ground units, whether the attacker was seen before (300 steps) and seen at the event; units lost while they had a move path; `baseline-v2` move orders issued while a visible enemy's published weapon range covers the mover's hex or any of the first 5 hexes of the route it is then given ("threat-exposed orders"), and how many of those movers took damage within 300 steps; the distribution of event distances by judgement type |
| T3 | for every visible enemy unit, the episodes in which it disappears from view and reappears (count, median gap); damage events whose attacker was not seen at the event but was seen within the 300 steps before (a short memory would have known it) versus never seen before |
| T5 | decisions and unit-decisions listing guided fire (9) and correction radar (17); units with `guide_ability`; actions issued |
| T8 | decisions and unit-decisions listing merge (15), split (14), altitude (16), fortification entry or exit (18, 19), lay mine (20); presence of the corresponding archetypes in S; actions issued |
| TO-1 | no new figure: its registered next step is the `-2` rerun of the prevalence diagnostic (`docs/TACTICAL_FRONTIER.md`, TO-1 row; `docs/OWNERSHIP_PREVALENCE_DIAGNOSTIC.md`), scored as published |

Opportunity per scenario side, for criterion P (H0, 16 sides; a side counts when it has at least one):

| Family | A side has an opportunity when |
|---|---|
| T7-C | the A2 trigger fires at least once |
| T2 | embark or disembark is listed for an own unit at least once |
| T6 | an own moving ground unit takes a damage event from an attacker seen before |
| T3 | an own unit takes a damage event from an attacker not seen at the event but seen before |
| T5 | guided fire is listed for an own unit at least once |
| T8 | altitude, fortification or mine-laying is listed for an own unit at least once |
| TO-1 | as published by the ownership design study (S1 components, by game) |
| T10+ | defined in the family's admission entry from the census figure that motivates it, before it is scored |

Generality per family, for criterion G (S, share of the 50 scenarios with the capability): T2 infantry and infantry
fighting vehicles both present; T3 and T6 every scenario; T5 an operator with `guide_ability` and an infantry fighting
vehicle both present; T7-C a ground vehicle or infantry present; T8 the archetype of the sub-asset its increment uses;
TO-1 every scenario; T10+ defined in the admission entry.

## 7. Failure patterns and the new-family scan

The census also reports, on H0 and HH, what `baseline-v2` repeatedly leaves on the table, without regard to any
existing family:

| Scan item | Figures |
|---|---|
| N1 unused legal actions | per action type: decisions and unit-decisions listing it (H0, HH, HI); issued by `baseline-v2` (R: every `baseline-v2` seat's `actions_by_type`, and H0 reconstructed) |
| N2 suppression | onsets of suppression (`keep` from 0 to 1) on own units by class, `keep_remain_time` at onset, damage events on infantry already suppressed, unit-decisions listing remove-suppression (7) with `keep` 1 and with `keep` 0, scenario sides with a listing |
| N3 direct-fire choice | `baseline-v2` shoot decisions whose shooter had two or more distinct targets listed; of those, how often a target with lower `blood` than the chosen one was listed |
| N4 objective defence | objectives the side held and later lost; whether an own unit stood on the objective at the decision before the loss |
| N5 idle assets | own ground units with no `baseline-v2` action, no move path, not on board: unit-decisions with and without a visible enemy, by class |
| N6 timing | as T2's travel-time figures, and the decision at which each objective is first owned |
| N7 close combat | own unit-decisions in close combat; damage events at distance 0 |
| N8 aircraft | damage events and losses of own aircraft by class, and whether the aircraft was moving |
| N9 stacking | damage events whose victim was stacked |

A new family is admitted only if all five hold, each with the census figure or engine fact that shows it: (1) the
information it needs is observable seat-locally; (2) the action it needs is listed in `valid_actions` or has a small,
specific mechanism probe; (3) it is general (no scenario id, map id, unit id or fixed coordinate); (4) it has a
measurable tactical mechanism; (5) its first increment needs no large engine campaign. Admission entries are written in
the results before the family is scored; a family is not invented to fill the table.

## 8. The next increment of each family

Each candidate, including any admitted new family, is scored on ONE concrete next experiment, written before scoring
with: the tactical hypothesis; the exact observable trigger; the exact action or change; the expected mechanism; the
smallest useful offline analysis; the smallest engine mechanism probe if one is needed; the estimated engine sessions;
the main safety risk; the stop condition; what a negative result would teach; the evidence that would justify an
exploratory A/B. The increment chosen for a family is the one the author judges most informative per engine session
among those that respect the family's own history (for T7-C, its open E3b question and its benefit channel; for TO-1, its
registered next step). The results answer, for T7-C, whether a controlled deterministic diagnostic can replace the wait
for a natural witness, what such a probe would and would not support, and whether it is cheaper or more informative than
starting another family.

## 9. Frozen rubric (fixed now, `rubric.json`)

The seven criteria and weights of `tactical-frontier-1` are kept (G 0.20, L 0.25, O 0.15, I 0.10, M 0.10, R 0.10,
P 0.10; weighted score W), and Sprint 1's scores are not changed. Here each criterion scores the next increment and the
tactic it serves, with these anchors (integers 0 to 5):

| Criterion | 5 | 4 | 3 | 2 | 1 | 0 |
|---|---|---|---|---|---|---|
| G generality of the tactic (computed, section 6) | capability in at least 90% of the 50 scenarios | at least 75% | at least 50% | at least 25% | under 25% | absent |
| L leverage of the tactic if the increment's mechanism holds (judgement, citing the census stake) | can change the combat power or objective control of the whole force in most games | changes the effective force of most operators, with known offsetting costs | a local advantage for a subset of operators or situations | occasional advantage | marginal | none expected |
| O observability of the trigger | entirely from the seat's observation and legal actions, cheap | plus simple bookkeeping of what was seen | needs a belief over partially observed enemies | needs a model of hidden enemy behaviour | needs information the seat lacks | not decidable online |
| I isolation of the increment and its tactic | changes no `baseline-v2` decision: acts only on units `baseline-v2` leaves idle, or only with action types it never issues | one new behaviour for one archetype, `baseline-v2`'s selection untouched | changes `baseline-v2`'s selection for a subset of units | changes shared machinery (routing, ordering, the gate) | touches every unit's behaviour | a rewrite |
| M measurability of the increment's result | its endpoint is a field or record of one deterministic game | directly observed fields, but they need events an acting opponent produces (several per game expected) | needs a full-step capture plus a derived quantity or model | needs a new observer and an interpretation model | visible only through scores | not measurable |
| R engine and rule risk, reversed | listed and already executed on engine 4.1.0 with known semantics, simple parameters | listed and documented, never executed, simple | listed, but its effect is undocumented, or documented with untested interactions | rarely listed, or complex parameters with unknown effects | undocumented or never observed listed | known incompatible |
| P opportunity (computed, section 6) | every H0 scenario side | at least 75% of them | at least 50% | at least 25% | under 25% | none |

**E, expected information per engine session** (secondary; integers 0 to 5), scored on the increment's engine step (for
an increment answered offline, on the engine step it leads to):

| E | Anchor |
|---|---|
| 5 | one session answers the increment's mechanism question with a directly observed, deterministic endpoint, the trigger is already fixed offline, and a negative result removes the family's main branch |
| 4 | one or two sessions answer it with directly observed endpoints, but the endpoint needs events an acting opponent produces, or a negative result removes only one of several branches |
| 3 | three to six sessions, or an endpoint that needs a derived model |
| 2 | more than six sessions, or an endpoint that is a score difference with known noise |
| 1 | only a scored A/B of tens of games can answer anything |
| 0 | no engine session can answer the question |

Every judgement score (L, O, I, M, R, E) carries a one-line reason citing a census figure, a published fact or a rule;
G and P are computed by `scripts/s18_select.py` from the census, never typed.

## 10. Eligibility, selection and outcome (mechanical)

1. **Eligibility.** A scored candidate is eligible when O >= 3, M >= 3, R >= 2 and E >= 2, it is not an excluded family,
   and (for T10+) it was admitted under section 7.
2. **Ranking.** Eligible candidates by W, highest first.
3. **Tie band.** If the second eligible candidate's W is within 0.15 of the first's (difference at most 0.15), E decides
   between the first and every candidate within the band: the highest E is selected. If two or more share that highest
   E, the outcome is FRONTIER_TIE.
4. **Robustness.** The sensitivity variants (section 11) are applied to the eligible candidates with the same tie rule
   (within the band, higher E, then higher L, then higher R, then identifier). If the selected candidate is first in
   fewer than 17 of the 25 variants, the outcome is FRONTIER_TIE between it and the candidate first in the most other
   variants.
5. **Outcome.** NO_READY_FAMILY if no candidate is eligible (the results then name the smallest census or mechanism
   study that would make one ready); FRONTIER_TIE as in 3 or 4 (the results then name the offline diagnostic that
   separates the tied candidates); otherwise NEXT_FAMILY_SELECTED.

The 0.15 band is one point on observability; a one-point difference on any 0.10 criterion is inside it and a one-point
difference on generality or leverage is outside it. The rule, the band and the threshold 17 are fixed now and are not
changed after scoring.

## 11. Sensitivity variants (25)

Equal weights (1/7 each); each of the seven weights raised and lowered by 0.05 in turn, the others rescaled to keep the
sum at 1 (14); each criterion left out in turn, the others rescaled (7); leverage 0.40, the others rescaled (1); E added
as an eighth weighted criterion at 0.10 and at 0.20, the seven others rescaled (2). Eligibility is not recomputed in the
variants. Reported: the first candidate of each variant and whether the selected one stays first.

## 12. Outputs, privacy and checks

* Public: `evaluation/s18-frontier-reset/` `rubric.json` (this registration), `inputs.json` (digests, counts, the
  record inventory digest), `census.json` (aggregates only: counts and distributions per population and family, no
  unit identifier, coordinate, hex, path, observation or per-unit row), `experiments.json`, `scores.json` (every score
  with its reason), `selection.json`. Every public file passes the project's privacy sanitizer
  (`evaluation/s12_screen.privacy_problems` with the private identifiers of the inputs) and is regenerated byte for
  byte by `--check`.
* Private (evaluation server, git-ignored): the per-event rows behind the census.
* Checks before the close: deterministic census regeneration; rubric, scoring, eligibility, tie-band, E tie-break and
  robustness tests with planted values; input pinning; the sanitizer; byte-for-byte regeneration of every public file;
  a private documentation gate binding the results' numbers to these files with planted errors; every earlier sprint's
  documentation gates; the full non-engine suites on the workstation tree, a clean clone and the server's private tree;
  the privacy scan compared as a set with the 104 accepted hit lines; the platform canary rebuilt; a read-only ledger
  verify showing 2,795 sessions and none unclosed.

## 13. Not claimed

No tactic is shown to work or fail here. A family's selection says where the next engine sessions are best spent, under
a frozen prioritisation rubric; a family not selected keeps its state. Census figures from H0 describe `baseline-v2`'s
decisions on `baseline-v0` trajectories, and HH has four games in one scenario.

## Results (2026-10-06 and 2026-10-07)

### R1. Order of work and implementation readings

The owner's decision was recorded first (`6200db5`, T9 `SHELVED` in the frontier register, Sprint 9's result and every
later disposition kept). Sections 1 to 13, the rubric, the input freeze and `inputs.json` (`1642790` to `6df3b90`) were
pushed at 2026-10-06T23:35:34+08:00 and fetched back byte-identical before any census code existed. The census
(`evaluation/s18_census.py`, driver `scripts/s18_census.py`) was then written and run on the evaluation server. Its
first run stopped at the privacy sanitizer and wrote nothing (a key named `units`, and aggregate counts equal to some
hex numbers); the key was renamed and the sanitizer applied as described below, and the second run wrote the census.
Later edits changed no output: `run --check` reproduces it byte for byte.

Implementation readings, disclosed here because sections 6 and 12 did not fix them:

* **Sanitizer.** `privacy_problems` compares numbers too, but hexes and unit identifiers overlap the range of
  ordinary counts (Sprint 13 met the same overlap with unit identifiers). The census therefore applies it twice: once
  as it stands (forbidden keys), and once with every numeric leaf masked and the private hexes and unit identifiers as
  forbidden keys and words. Every numeric leaf of the census is an aggregate by construction.
* **"Already suppressed"** (N2) is read from the victim's state at the decision before the event; at the event's own
  decision the hit itself has set `keep`.
* **Threat-exposed orders** (T6) are counted only when at least one visible enemy has a weapon with a published range
  against the mover's class; orders with only unarmed or unlisted enemies in view are counted as unreadable (96 of 509
  in H0, 90 of 416 in HH).
* **Input check.** `run` verifies every pinned file and the private record inventory against their digests rather than
  rebuilding the live folder listing, so records added by later sprints cannot break the regeneration (the frozen
  inventory lesson of Sprint 6).
* **Admission tables.** The cross-tabulations behind the new families (`admission.json`, `scripts/s18_admission.py`)
  were defined after the census had run and before any score; they are labelled post hoc relative to the census.

### R2. Census integrity

Every consistency check against a published figure holds (`census.json`, `consistency`, 10 of 10): H0 33,696 decisions
and 33,680 play decisions; `baseline-v2` reconstructed on H0 differs from the recorded `baseline-v0` actions in 123
decisions (Sprint 5); the A2 shadow orders 234 concealments to 49 units (Sprint 5); decisions listing embark, disembark,
remove-suppression and guided fire are 77, 256, 1,687 and 1 (Sprint 1); and on HH the census's own `baseline-v2`
reconstruction equals the recorded seat actions in 11,524 of 11,524 decisions. Populations read: H0 8 games (16 scenario
sides), HH 4 games (11,524 decisions, the 4 `baseline-v2` seats), HI 5 games (14,405 decisions), R 1,618 completed
records (the prevalence study's 360 left out), S 50 scenarios (8 frozen). Event-window captures (Sprints 2, 4, 6 and 10,
the 516 diagnostic and the split-screen smoke) were not read.

### R3. Supplemental capability and opportunity census

Figures are H0 / HH unless marked; "sides" are the 16 H0 scenario sides with at least one opportunity.

| Family | Capability (S, of 50) | What the census shows | Executed in engine | Sides |
|---|---|---|---|---|
| T2 transport | infantry and infantry fighting vehicles in 47; infantry start on board in 10 scenarios (74 units, none in the 8 frozen) | no infantry starts on board in H0, HH or HI; embark listed in 77 / 937 decisions, disembark in 256 / 2 (HI: 3,812 and 3,932, mostly vehicles carrying unmanned vehicles); `baseline-v2` issued neither; infantry move orders: median free-flow time 2,304 / 1,584 steps against 140 / 120 for vehicles, 20 of 51 / 8 of 32 unable to arrive before the end (vehicles 0); 21 of 41 / 10 of 28 infantry never stand on an objective | never | 12 |
| T3 belief | every scenario | 211 / 103 disappear-and-reappear episodes (median gap 41 / 21 steps); damage events by an attacker in view at the event 188 / 154, out of view but seen within 300 steps 15 / 4, never seen before 2 / 0 | not applicable | 12 |
| T5 guided fire | guide-capable unit and infantry fighting vehicle in 47 | guided fire listed in 1 / 0 decisions, correction radar in 2 / 4, although 61 / 40 guide-capable units are present at the first play decision | never | 1 |
| T6 threat-aware movement | every scenario | of 205 / 158 damage events, 124 / 117 hit moving ground units, attacker seen before in 120 / 117; 60 of 128 / 55 of 89 lost units were ground units with a move path; 230 / 200 move orders threat-exposed, 88 / 101 of them followed by damage to the mover within 300 steps | moves and holds: always | 12 |
| T7-C concealment | ground units in every scenario | 234 / 35 trigger orders (49 / 29 units); damage on a concealable unit: 0 / 4 events (2 units, 5 damage, 2 lost), none by a ground attacker beyond half its observation distance; E3b exposure 1 unit (6 actions) / 0 | concealment yes (Sprint 6); exit never | 11 |
| T8 specialised | helicopters in 26, mine layers in 7, fortifications in 4 | change altitude listed in 6,957 / 9,731 decisions, lay mine in 1 / 2, fortification never; aircraft damage events 13 / 3, all while not moving, every damaged aircraft lost | never | 4 |

Action semantics already known (engine facts table of the frontier) are not repeated. The census pins every input and
regenerates byte for byte; it is a description of historical play, not a validation set.

### R4. What `baseline-v2` repeatedly leaves on the table

* **Force is lost, not kept.** Against acting opponents `baseline-v2` ends with a median of 0.81 (mirrors, 318 side-games)
  to 0.85 (against other acting policies, 105 side-games) of its force value lost; the final score is occupy + attack +
  remain in 423 of 423 such side-games, so every surviving point is a score point.
* **Moving units take most of the damage** (T6 above), almost always from attackers the side could see. Of the 177 / 130
  ground damage events, 112 / 70 hit a stacked victim; 57 / 40 were stacked units moving off objectives (columns) and
  40 / 10 stacked holders standing on an objective (`admission.json`).
* **Close combat** (distance 0) accounts for 71 / 55 damage events, every attacker seen before; in H0 49 of the 71 hit
  units on an objective, in HH 45 of the 55 hit moving units.
* **Objectives are lost after capture**: 40 / 26 losses of held objectives (7 of 16 sides). By the capture rule none can
  happen with an own unit on the hex, and none did.
* **Suppression**: 89 / 65 onsets on own units (infantry 15 / 4), with `keep_remain_time` 149 (median) and at most 150
  at onset; remove
  suppression is listed only while suppressed (1,709 / 700 unit-decisions, all with `keep` 1) and never issued.
* **Fire choice**: 368 of 432 / 267 of 319 `baseline-v2` shots had two or more targets listed, and in 127 / 97 a target
  with lower blood than the chosen one.
* **Unused actions** (R, every `baseline-v2` seat): only move, shoot, occupy and the end of deployment are ever issued;
  embark, disembark, change state, remove suppression, guided fire, stop, lock, split, merge, altitude, radar and
  mine-laying are listed and never used.
* **Idle units with an enemy in view** are mostly artillery (102,024 H0 unit-decisions; T4 is shelved) and vehicles
  (23,224), many of them holders on taken objectives.

### R5. External sources (generic concepts only)

Two web searches, with no private content: threat-aware route planning that treats an observed enemy's weapon range as
an exposure envelope and accepts longer or later movement to reduce exposure, and Lanchester-type focus fire (the
square law's assumption that fire shifts to a new target after a kill). They shaped the wording of T6's trigger
(envelopes from published ranges) and T11's hypothesis; no code, data or parameter was taken from them.

### R6. New families (admission entries in `experiments.json`)

Admitted under all five conditions: **T10** suppression relief (remove suppression, action 7, for suppressed own
infantry), **T11** direct-fire target priority (prefer the listed target most likely to be destroyed; distinct from
TO-1, which assigns one target among colliding shooters), **T12** objective-zone dispersion (spread stacked holders of a
held objective over adjacent hexes; it inherits T9's withholding interaction). Not admitted, with reasons: close-combat
avoidance (a route-entry case of T6), aircraft stand-off (one archetype, rare), idle units with an enemy in view (no
separate mechanism) and objective losses (T12's denial question).

### R7. One concrete next experiment per family

Full entries, with every field of section 8, are in `experiments.json`.

| Family | Next increment | Engine sessions | Main risk | Stop |
|---|---|---|---|---|
| T2 | transport mechanism probe: embark at co-location, carry, disembark at the objective | 2 (1 deterministic, a second only if needed) | the stacking limit voids a disembark silently | embark or disembark refused or voided |
| T3 | short threat memory as an input of T6's gate | 0 of its own | phantom threats | already met: fewer than one event per side-game |
| T5 | guided-fire availability | none can produce a listing | rare, complex | already met: no listing |
| T6 | **T6-G threat-entry gate**: offline shadow, then a two-session head-to-head mechanism probe | 2 | bounded T9-like withholding | under 10 gates per side-game, gated units hit at or above the HH rate, or a later first ownership |
| T7-C | controlled E3b exit diagnostic in the P-A configuration | 2 (move exit in 1; fire exit may need a second configuration) | an injected sequence, silent on benefit | move refused or concealment kept |
| T8 | helicopter altitude probe | 2 | altitude effect undocumented for attack helicopters | transition refused or without effect |
| TO-1 | registered `-2` prevalence rerun | 360 | campaign size | as registered |
| T10 | remove-suppression probe | 3 | an undocumented cost | refused or `keep` unchanged |
| T11 | kill-first target rule: offline replay, then two head-to-head sessions | 2 | lower attack level per shot | under 10 changed shots per side-game or no gain in kills per shot |
| T12 | objective-zone dispersion: offline count, one deterministic and two head-to-head sessions | 3 | T9's withholding interaction | a capture next to a dispersed holder |

### R8. T7-C, answered

* **Can the next experiment be a controlled deterministic diagnostic?** Yes. The P-A configuration (1910631192 C3,
  candidate blue against the inert control) reproduced exactly in Sprint 6, so a hook can order a one-hex move for a
  concealed vehicle at a fixed decision after its concealment has completed.
* **Can it validly answer whether move or fire exits concealment?** For the move, yes: `move_state` and the order's
  acceptance are fields of a deterministic game. For fire, only where a concealed unit lists a target, which did not
  happen in the P-A game; a configuration in which `baseline-v2` fires at the inert side would be needed.
* **Would it inject a sequence `baseline-v2` would not produce?** Yes: the move is a diagnostic command, and Sprint 7
  and this census show that `baseline-v2` almost never commands a unit after the trigger (1 unit in H0, none in HH).
* **What it supports and what stays unknown.** It would establish the engine's exit semantics for the probed unit
  types. It says nothing about frequency on policy or about benefit, and the census finds the benefit channel empty:
  no damage to a concealable unit in H0, and in HH 4 events, none by a ground attacker beyond half its observation
  distance.
* **Cheaper or more informative than starting another family?** Cheaper (one deterministic session) but less
  informative: closing E3b cannot create the benefit the census does not show. T7-C scores L 1 and is fifth.

### R9. Scores (frozen rubric; G and P computed, the rest with reasons in `scores.json`)

| Candidate | Increment | G | L | O | I | M | R | P | W | E | Eligible |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T6 | T6-G threat-entry gate | 5 | 4 | 5 | 3 | 4 | 5 | 4 | **4.35** | 4 | yes |
| T11 | T11-O1 kill-first target rule | 5 | 3 | 5 | 3 | 4 | 5 | 4 | 4.10 | 4 | yes |
| T2 | T2-P1 transport mechanism probe | 5 | 3 | 5 | 3 | 5 | 3 | 4 | 4.00 | 5 | yes |
| T12 | T12-O1 objective-zone dispersion | 5 | 3 | 5 | 3 | 4 | 4 | 3 | 3.90 | 3 | yes |
| T7-C | T7-E3b controlled exit diagnostic | 5 | 1 | 5 | 5 | 5 | 4 | 3 | 3.70 | 4 | yes |
| T10 | T10-P1 remove-suppression probe | 5 | 2 | 5 | 5 | 4 | 3 | 2 | 3.65 | 3 | yes |
| TO-1 | TO-1 registered next step | 5 | 2 | 5 | 3 | 4 | 5 | 2 | 3.65 | 1 | no (E) |
| T3 | T3-O1 short threat memory | 5 | 2 | 4 | 3 | 3 | 5 | 4 | 3.60 | 2 | yes |
| T5 | T5-O1 guided-fire availability | 5 | 2 | 5 | 5 | 4 | 2 | 1 | 3.45 | 1 | no (E) |
| T8 | T8-A helicopter altitude probe | 3 | 2 | 5 | 4 | 5 | 3 | 2 | 3.25 | 4 | yes |

Computed sources: G from the scenario census (T11 from Sprint 1's tank presence, 50 of 50); P from the H0 side flags
(T12 from the admission table, 10 of 16; TO-1 from the ownership design study, 2 of 8 games).

### R10. Sensitivity and robustness

No other eligible candidate is within the 0.15 band of T6 (T11 is 0.25 behind), so E does not enter the main
selection. T6 is first in 24 of the 25 variants (`selection.json`); the exception is E as an eighth criterion at 0.20,
where T2 (E 5) comes within the band (4.20 against T6's 4.28) and wins on E. Without leverage T7-C scores 4.60 and T6
and T11 4.47: all three are within the band, E is equal (4), and T6 is first on L. The rule needs 17. One property found while testing the rule, not a change of it: at a gap of
exactly 0.15 the rescaled variants split, so two candidates exactly one observability point apart end as a tie under
the robustness rule; the committed selection is far from that edge. The selection rule was mutation-tested
(`local/diagnostics/s18/mutate_s18_selection.py`, private): 16 of 16 mutants killed; the first run killed 12, and the four
survivors were test gaps (the variant band edge, R in the tie order, the exact robustness threshold, the challenger
choice), closed before this section was written.

### R11. Outcome: NEXT_FAMILY_SELECTED, T6 threat-aware movement

**Selected first experiment: T6-G, the threat-entry gate.** A `baseline-v2` move is withheld for one decision when it
would carry a ground unit from outside every visible enemy's published direct-fire envelope into one within the first
five hexes of its route; a hold episode lasts at most 150 steps, and a released unit is not gated again for 300 steps.
No new action type, routes unchanged. First the gate runs offline as a shadow on H0 and HH (gated orders, units, holds,
how many gated units were the eventual capturers, the damage that followed gated orders on the recorded trajectories);
then a registered two-session head-to-head mechanism probe in 2130511121, both seat orders, mechanism endpoints only.

**Why it beats T11.** Both have entirely seat-local triggers on executed actions and need an acting opponent to show
an effect; they differ only on leverage. T6 targets the dominant loss mode (moving ground units: 124 of 205 and 117 of
158 damage events; 60 of 128 and 55 of 89 lost units), while T11's changed shots are 127 of 432 and 97 of 319 and trade attack
level for kill probability. T2 is the most information-efficient (one deterministic session) but its tactic is narrower
and its disembark carries the stacking-limit risk that silently voided T1's splits.

**Engine cost of the next step.** None for the offline shadow; two sessions for the probe, after the owner's approval of
its registration.

**Evidence that would stop the line.** In the shadow: the gate fires fewer than 10 times per side-game in HH-like play,
or most gated units are the eventual capturers. In the probe: gated units damaged at or above the HH rate (101 of 200
threat-exposed orders followed by damage within 300 steps), or any objective first owned later than in all four HH
games. Either closes the timing branch of T6; route choice and formation would remain open questions, not
automatic next steps.

### R12. Process notes

* Two hex distances in a synthetic test were typed by hand and were wrong (1040 to 1020 is 20, not within 18; 1020 to
  5045 is 45); the test now asserts the distances it relies on, computed by the project's function.
* A heredoc patch to the mutation script failed on the backslash escape layer before writing anything; the script was
  rewritten with the editor tool.
* The first mutation run imported the unmutated package because the test package puts the repository's `src` first;
  the script now runs each mutant in a copied tree and requires the unmutated copy to pass first.
