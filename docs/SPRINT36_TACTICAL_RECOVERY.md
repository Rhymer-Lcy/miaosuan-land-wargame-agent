# Sprint 36: tactical recovery and evaluation repair

Date: 2026-10-10 (UTC+8). Track: `EXPLORATORY` (`docs/EXPLORATORY_TRACK.md`). Branch `sprint36-tactical-recovery`,
created from the frozen Sprint 35 head `6717930e4858b7a78829a056c2a23254dd92746d`. OFFLINE ONLY: no engine session is
authorized by this sprint, and none was opened. `main`, every earlier sprint branch, `platform-compat2`, the Sprint 34
package `integrated/` and the Sprint 35 package `coalition/` are imported and never edited; Sprint 35's card,
registration, records, results and disposition are unchanged.

## 1. Verified state at the start

| Item | Verified value |
|---|---|
| `main` (workstation, GitHub, evaluation server) | `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85` |
| Sprint 35 branch `sprint35-coalition-agent` (workstation, GitHub, server) | `6717930e4858b7a78829a056c2a23254dd92746d` |
| `platform-compat2` | `a909557bb43648c5c879c19ad8f8ba362e8f4892`, untouched |
| `baseline-v2` policy source (22 files) | `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` (recomputed) |
| Sprint 34 MO policy source (36 files) | `b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b` (recomputed) |
| Sprint 35 CM revision 2 policy source (46 files) | `ea38c04216385a8aa119d624c9e437c118268a3a8caec682cf98f1834df8400c` (recomputed) |
| Sprint 34 and Sprint 35 live cards | rebuild byte-identically (`4bb778ed...`, `0b90ae26...`) |
| Engine ledger | 2,845 sessions, every one opened and closed, none open; no lock file; SHA-256 `f396b2a137100dedc1c912bffc412a2c92e77ed06fe85988db972feb0919a927` |

The shared primary checkout carries another session's uncommitted platform-builder edits; they are left as found. All
Sprint 36 work is in the worktree `local/worktrees/sprint36` and, on the evaluation server, in a separate worktree whose
`local/` holds links to the main clone's private folders (one engine installation, one ledger), on NUMA node 0
(`docs/SERVER_RESOURCE_POLICY.md`).

## 2. Sprint 35's invalid result, verified and not rewritten

Read from the private records of sessions 2827 to 2845:

* 19 games completed, 19 sessions opened and closed with integrity ok; the ledger audit of Sprint 35's own rules finds
  exactly the first 19 scheduled games in order and no problem; no session after 2845 exists.
* Position 19 (session 2845) was the Sprint 34 control (MO) as blue against `baseline-v2` in 2010431153. It emitted 31
  unit actions (9 moves, 14 shots, 3 embarks, 3 disembarks, 2 occupations; plus the deployment completion, which the
  engine does not echo); the engine echoed 31 entries for the seat. Two shots were refused, no other action.
* The registered S6 (`s34_live.structural`, more than 2% of unit actions refused) read 2 of 31 = 6.5% and fired; the
  registered disposition `S35_LIVE_INVALID` is the correct one under the registered rules and stays.
* **Correction of a description** (no rule or disposition changes): Sprint 35's report described the two refusals as
  "one shot at a unit already destroyed, code 203; one shot refused with code 516". The recorded attribution-2
  evidence (`docs/REFUSAL_TAXONOMY.md`) says the reverse for 203: code 203 `CantControlDiedOperator` was the shooter
  destroyed earlier in the same step (actor on the map at the start of the step, in no unit list after it), and code
  516 `CantShootToDiedBop` was the target destroyed earlier in the same step, with one own shot at it. Both are
  same-step races; neither is a contract or safety failure.
* The original report (`scripts/s35_analysis.py report`) printed `S35_INTEGRATED_INCONCLUSIVE` because it read only
  stored batch gates and none had been stored; the reporting-only correction (`scripts/s35_disposition.py`,
  `evaluation/s35-coalition-live-1/disposition.json`) applied the registered functions and printed `S35_LIVE_INVALID`.
  Both are kept as separate historical facts (section 4 re-derives the disposition independently).

The 19 games are an invalid, incomplete Stage A. They are used below only as development evidence, labelled so, and
never as a comparison of the two policies.

## 3. Refusal taxonomy and the new refusal gate

### 3.1 Population

`scripts/s36_refusal_audit.py` reads every game record on the evaluation server (`miaosuan-game-record/1`): 2,030
records, 4,060 seat-games; 2,669 completed seat-games of a policy under test (not the inert control), 2,521 of them with
refusal facts retained (`miaosuan-refusal-fact/1`; earlier records kept codes only and are counted, not classified). The
denominator is the seat's emitted unit actions (deployment completion excluded); it equals the engine's echoed feedback
count in every reference seat-game (1,427 of 1,427), in all `baseline-v0` and `baseline-v1` games, and differs in the
154 deployment-split screen seat-games (the refused split actions) and one probe game. Output (aggregates only):
`evaluation/s36-tactical-recovery/refusal-audit.json`.

### 3.2 Taxonomy (`s36-refusal-taxonomy-1`, `src/miaosuan_agent/evaluation/s36_refusals.py`)

A class is assigned from the factual record and the attribution-2 label, never from the code alone:

| Class | Definition | Recorded (policy-under-test seats) |
|---|---|---|
| A contract | not gate-passed, or not listed at the start of the step (non-movement), or message `ErrorActionType` | 3,626 split actions (type 14, code 103) of the deployment-split screen |
| B movement or transition | a move, embark, disembark, state change or stop not listed at the start of the step | 0 |
| C dangerous accepted action | damaging attack on an own unit, an undeclared action type emitted (from game facts, not refusals) | 0 in the live games |
| D same-step race | listed and gate-passed; actor (203) or target (516, one own shot at it) no longer alive at resolution | 219 shots and 4 other actions in the reference policies; 75 shots and 2 others in `baseline-v1` |
| R redundant own action | a 516 with two or more own shots at the target in the step, or an occupation of an objective already own or occupied twice (1804) | 0 in the reference policies; 328 shots in `baseline-v1` (no shoot-target reservation) |
| E unexplained | listed and gate-passed, no rule covers the class or the evidence is missing or contradicts it | 4 moves refused with code 404 `CantMoveKeptPeople` (3 in `baseline-v2` games, 1 in `baseline-v1`) |

Code 404 stays unexplained: the moves were listed at the start of the step and the actor was present after it, but no
recorded evidence shows why (the suppression flag before and after the step was not kept). It is counted, not
whitelisted.

### 3.3 Gate (`s36-refusal-gate-1`), applied to each game of a policy under test, never to its opponent

* **Structural** (any one, at once, whatever the game size): an A or B refusal; a C fact; two E refusals in one game or
  three in the study; refusal facts not retained; an echo count different from the emitted count.
* **Systemic** (a pattern): for fire actions (shots and guided shots) and other unit actions separately, at least
  3 race refusals whose upper binomial tail under the calibrated reference race rate is below 1e-6 (or, below 10
  actions of the group, 3 races outright); 2 or more redundant refusals; one unit refused 3 or more times.

Calibration on the complete history (reference = `baseline-v2`, Sprint 34 MO, Sprint 35 CM; 1,427 seat-games, 28,195
fire and 58,199 other unit actions): race rate 219 / 28,195 = 0.00776733 per fire action and 4 / 58,199 = 6.873e-05 per
other action; no redundant refusal. The tail threshold 1e-6 is the largest power of ten at which no reference game of the
history triggers (at 1e-5 one game does: four races in 16 fire actions). Two races are never systemic (Sprint 35's
position 19 had two in 14 fire actions; nine reference games had two in at most nine).

Empirical trigger frequency (seat-games; not a false-positive rate - no external truth classifies these games as
healthy or defective, except the documented defect classes noted):

| Group, scale (unit actions) | Seat-games | Sprint 35 S6 | 3 refusals or more | 2% with at least 100 actions | S36 structural | S36 systemic |
|---|---|---|---|---|---|---|
| reference, up to 30 | 708 | 59 | 0 | 0 | 0 | 0 |
| reference, 31 to 100 | 367 | 14 | 4 | 0 | 0 | 0 |
| reference, 101 to 300 | 351 | 7 | 7 | 7 | 0 | 0 |
| reference, over 300 | 1 | 0 | 0 | 0 | 0 | 0 |
| `baseline-v1` (documented duplicate-fire defect), all | 736 | 93 | 42 | 23 | 0 | 69 |
| deployment-split screen (unsupported action type), all | 154 | 98 | 99 | 10 | 154 | 95 |

By scenario (reference seat-games): Sprint 35's S6 fired in 32 of 161 games of 1910631192, 16 of 144 of 2010211129, 15
of 144 of 201033019601, 13 of 226 of 1930331196, 4 of 150 of 2010431153, 0 in 2010131194, 2120531121 and 2130511121; the
new gate fired in none. S6 fired on 80 of the 1,427 reference seat-games (5.6%), 59 of them among the 708 smallest:
an ordinary refused shot was enough. Boundary cases (tests in `tests/test_s36_refusals.py`): one race in a six-action game
does not stop; one unlisted shot or move in a six-action game stops; 13 races in 300 fire actions are systemic, 12 are
not (the smallest k with a tail below 1e-6 at n = 300); an unknown code passes once and stops at the second in a game or
the third in the study.

## 4. Stopped-study reporting

`src/miaosuan_agent/evaluation/s36_study.py`: a study's state and disposition are derived by one function, `derive`,
from the recorded games and the study's versioned `Rules` (per-game stop, batch gate, final rule, a disposition per stop
kind, rules digest over their source). It walks the registered schedule: after every recorded game the game rule, after
a batch's last game the batch gate; the first stop ends the walk. A game recorded after a stop, a gap, or a foreign
position is a protocol violation (invalid), while the stop itself stays recorded; a study without a stop and with
missing positions is "in progress" and never reported complete; every position gets a status (played, stopped here,
not played after the stop, not played pending, played after the stop). The runner calls the same function before and
after each game; stored gate files are never the authority. `restate` is an independent second reading; `report`
refuses to publish when they disagree; `check_stored` compares a stored report with a fresh derivation (a stopped batch
stored as inconclusive is detected). Tests (`tests/test_s36_study.py`): termination before the first game, after every
ordinary game, inside a batch, exactly at a batch boundary, after severe harm, after a structural failure, after an
agent failure, after futility, at normal completion, and planted reporting errors.

Independent re-derivation of Sprint 35 (`scripts/s36_s35_rederive.py`, `evaluation/s36-tactical-recovery/
s35-rederivation.json`): facts recomputed from the private records by Sprint 35's own analysis, Sprint 35's registered
functions applied through the derivation (`evaluation/s36_s35_rules.py`): `S35_LIVE_INVALID`, structural stop at
position 19 (game, batch A1), finding "S6: 2 refused of 31 unit actions"; beside it, as historical facts, the original
report's `S35_INTEGRATED_INCONCLUSIVE` (0 stored gates) and the reporting-only correction's `S35_LIVE_INVALID`.

Publication policy (`src/miaosuan_agent/evaluation/s36_publish.py`): a public JSON number that matches the pre-push
scan's numeric pattern by accident is written in exponent notation (`ddd.ddd` becomes `d.ddddde+02`), which JSON reads
back as the same number; the rewrite is checked (same values, no match left) and a colliding string or key is refused.
No metric is dropped and the accepted privacy baseline is not changed; the re-derivation publishes every game's mean
held value this way.

## 5. Sprint 35's tactical failures, reconstructed

`scripts/s36_reconstruct.py` re-decides the policy under test of every recorded live game from its recorded
observations with its own memory chain and reads the all-seeing timeline. Fidelity: all 43 games (19 Sprint 35, 24
Sprint 34) reproduce every recorded decision (2,881 or 1,801 per game, 0 differing). Shadows (open loop: a shadow's
decision never changes the recorded trajectory) locate the first decision difference between the two policies.

**Losses of held objectives** (Stage A, both policies' games; "MO" = the Sprint 34 control's 16 Sprint 34 and 10
Sprint 35 games):

| | CM (9 games) | MO (26 games) |
|---|---|---|
| held objectives lost | 33 | 84 |
| last standing defenders destroyed / ordered away alive / none within 1,800 steps | 28 / 5 / 0 | 57 / 26 / 1 |
| CM stance 150 steps before the loss: delay / skip / quiet / defend / capture / secure | 18 / 5 / 5 / 3 / 1 / 1 | (no stances) |
| enemy ground units in the zone at the loss: 1 / 2 / 3 or more | 5 / 10 / 18 | 14 / 22 / 48 |
| own ground units destroyed (all) | 84 | 230 |
| destroyed standing in an objective zone / moving / aboard a carrier | 43 / 30 / 11 | 97 / 91 / 42 |
| of those in a zone, kept there by CM's stance (delay / defend) | 33 / 4 | - |

**1930331196, blue** (CM position 12: margin -502, objective score 0, 17 of 26 units lost; MO position 11: +676, 310,
6 lost). The two games follow the same opening; the first decision difference of the two policies on CM's game is at
step 180 (CM sends a unit to a coalition capture place, MO keeps it in reserve). CM lost two tanks moving (482, 520; MO
lost one moving at 501 and one in a zone at 565), two infantry fighting vehicles with their passengers aboard (601,
781), and two tanks kept in delay zones (821, 876): each was the only unit standing in a held zone the stance judged
untenable. By step 1,875 CM had 9 ground units left and went on to lose every objective, three of them (1,876, 2,177,
2,258) to a single enemy tank entering a held zone with nobody standing in it: the stance was delay, no reinforcement
could reach the commit ratio, and the delay stance sends nobody. Its two remaining squads stood 15 or more hexes away.
Causal limits: combat outcomes are stochastic (the same opening produced different early losses), and the trajectories
diverge from step 180, so later states are not comparable.

**1910631192, blue** (CM position 15: -298, 0, 6 of 6 lost; MO position 16: +222, 130, 2 lost). Both games are identical
(same first-ownership steps) up to step 581, where the only first decision difference occurs: MO sends a tank to hold
the threatened 50-point objective, CM moves it a hex into the 80-point objective's zone (dispersal). CM's stance for
that zone was then "secure" (defence 1.167 to 1.583 against a threat of 1.075 to 1.271; tank 1.0, infantry fighting
vehicle 0.25, unmanned ground vehicle 0.2): one tank left and was destroyed moving (746), the kept tank and infantry
fighting vehicle were destroyed in the zone (800, 801), and the objective fell to a tank, an infantry fighting vehicle and
an unmanned ground vehicle that lost nothing; in MO's game the enemy lost five units. A better decision at 581 is not
established: the stance's force estimate said the zone was held, and the difference is consistent with combat
stochasticity in a six-unit game.

**2130511121, blue** (CM position 4: +765; MO position 3: +1,009). Both held all seven objectives at the end; the margin
difference is units: CM lost 16 (value 103), MO 12 (65). The first decision difference is at step 75 (transport: CM
carries two passengers on, MO disembarks them). Seven of CM's 14 destroyed ground units died standing in zones kept by
its delay stance.

**What the reconstruction shows** (mechanisms, not causes of the final scores):

1. Over-retention: the delay stance keeps every standing defender unless a justified withdrawal is possible, and those
   conditions (visible threat, a cheaper holder, a destination) were rarely all met: 33 of CM's 84 lost ground units died
   kept in delay zones.
2. Passivity in empty held zones: with nobody standing in a held zone and the commit ratio unreachable, the delay stance
   offers no place at all; single enemy units walked in.
3. Over-conservative capture: a coalition of 1.2 times the threat is required whenever a known enemy can reach the zone,
   including motionless ones (section 7).
4. The 107-step "wait" was not traffic (section 8).

## 6. Defence: hold, delay, withdraw, reinforce

Design (`src/miaosuan_agent/tactical/assess.py`, rule 3; Sprint 35's stance computation is called unchanged first):

* **Hold** (`secure`): defenders' capability-weighted power reaches the threat; the units needed and the best holder
  stay (Sprint 35).
* **Reinforce or counterattack** (`defend`, `coalition`): defenders plus free units arriving before the enemy reach the
  commit ratio; reinforcement places with a deadline (Sprint 35). Variant B adds a counterattack bonus on coalition
  places at objectives lost within 600 steps.
* **Delay** (untenable held objective): one *cheap* defender stays to deny occupation - cheap means value at most half
  the side's highest mobile ground value (tank 10: squads 4, unmanned ground vehicles 5); the scenario data's values
  are tank 10, infantry fighting vehicle 7 or 8, squad 4, unmanned ground vehicle 5. Losing a unit costs its value twice
  in margin (own remaining-force score and the enemy's attack score), an objective's points count only at the end, and
  an enemy cannot occupy while any own ground unit stands in the zone: a cheap holder buys time cheaply, an expensive
  one does not.
* **Withdraw or redeploy**: every other defender leaves when at least half the threat is visible now (never on memory
  alone), the earliest enemy arrival is at least 40 steps away (it is not yet under fire: moving units cannot fire
  except tanks) and a destination
  exists: the nearest held objective not in delay, else the nearest reachable hex within 8 hexes, outside every
  objective zone, at least 2 hexes farther from every visible threat member than the unit is now (contact broken - a
  tank's weapons reach 18 to 20 hexes, so leaving its range is rarely possible), with fewer than two own units planned on
  it. A unit that cannot withdraw stays.
* **Empty held zone**: one cheap free unit arriving before the enemy may take a delaying place (allocator rule).
* **End window**: in the last 300 steps every defender stays (only the final ownership is scored).

Every withdrawal is a move routed through Sprint 34's traffic ledger and route planner (capacity, full hexes, hazards,
threat costs); no stop or unlisted action is ever emitted (validator, tests).

## 7. Capture: opportunity before contest

### 7.1 Mechanism of the 20 of 80 model shortfall

Sprint 35's development model runs (`local/diagnostics/s35/offline-r2/model.jsonl`, private) list the 20 scenario-sides:
2010131194 and 2010141294 (both seats), 201033019601, 201033029601, 201033039601 and 211033019601 (both seats),
2010441253 red, 2030111194 (both), 2110431353 red, 2110431553 red, 2120511121 blue, 2130511221 blue, 2130511321 blue. In
each, inert enemy units stand within the threat horizon of an objective but outside its zone (S34 MO takes every
objective, which is impossible while an enemy stands in the zone); with a one-hex-per-cost optimistic arrival they count
as a threat, the capture ratio requires a coalition the side cannot form, and the stance is skip.

### 7.2 Rules (assess rules 1 and 2)

* **Static filter**: an enemy ground unit seen standing on one hex without a move path for at least 75 steps (one
  arrival transition) and outside every objective zone is not a threat. It loses that status the moment it is seen
  moving. Calibration: in the 40 recorded live games against `baseline-v2`, no `baseline-v2` ground unit stood still
  without a path outside an objective zone for more than one step (inside zones: runs up to 2,280 steps), so the filter
  removes no moving attacker of that kind. The rule reads observable behaviour; it never reads the opponent's identity.
* **Opportunity capture**: an objective not held, in skip or coalition, with no known enemy in its zone, is captured
  with Sprint 34's capture places when a free unit's free-flow arrival is at least 10 steps earlier than every remaining
  threat's optimistic arrival. Enemies in the zone still require a coalition (only fire clears them).

## 8. Traffic

Every halted step of an own ground unit (a path and zero speed) in the 43 recorded games was classified from the
seat's observation and the all-seeing rows (`evaluation.s36_capture.wait_cause`): full next hex (four own ground units),
suppression (`keep`), deferred stop (`flag_force_stop`), an enemy on the next hex, or none of these. There are two runs:
MO position 3 of Sprint 35, 34 steps (32 suppressed, 2 unexplained), and CM position 12, 107 steps (105 suppressed, 2
with an enemy on the next hex; the next hex held one enemy unmanned aerial vehicle and no own unit). **No step of any
of the 43 games was a wait in front of a full hex.** Sprint 35's "107 waiting unit-steps in front of full hexes" was
the metric (`s34_live.force_facts`: path and zero speed, any cause), not a traffic regression; the traffic ledger was
not at fault. Sprint 34's traffic subsystem is kept unchanged; the new observer (`S36Timeline`) records the cause of
every halted step and the live rules read only full-hex waits as a deadlock.

## 9. Fire, guided fire and transport

* **Guided fire** was listed for the policy under test in 0 to 2 steps per head-to-head game (red only; 5 listed steps
  in 35 such games), against 2,235 steps per game against the inert control in 2120531121 as red. Sprint 35's candidate
  issued 1 of its 3 listed opportunities; at the other two the guiding unit had a direct shot of higher attack level (7
  against 5 or 4) and its carrier fired directly: arbitration chose the better shot. The low use reflects scarce
  opportunities against a moving opponent, not a strict guard.
* **Artillery** and **transport** are kept as in Sprint 34 (A, C) or Sprint 35's mission planner (B: stance-driven
  targets, arrival fire, lifts only to objectives without a known threat). Passengers lost with their carrier: 11 of
  CM's 84 lost units, 42 of MO's 230.
* No undocumented action type is enabled (enabled set: move, shoot, embark, disembark, occupy, indirect fire, deployment
  completion; guided fire in B). The collaborator's source is not used.

## 10. Three integrated candidates

Package `src/miaosuan_agent/tactical/` (configurations `tactical/config.py`):

| | TA `survival-capture` | TB `mission-coordinator` | TC `guarded-orchestrator` |
|---|---|---|---|
| decision cycle | Sprint 35's stance cycle | Sprint 35's stance cycle | Sprint 34 MO's, then a guard |
| assessment | Sprint 36 (rules 1 to 3) | Sprint 36 + counterattack bonus | Sprint 36, read by the guard |
| fire, transport | Sprint 34's | Sprint 35 mission planner's (fire support, arrival fire, guided fire, safe transport) | Sprint 34's |
| guard (TC) | - | - | drops moves that take a kept unit out of a held zone (retention), drops moves of units that are not cheap into zones judged delay or skip, adds the assessment's withdrawals through the traffic ledger, validates again |

Ablations: TA without the delay holder, withdrawal, static filter, opportunity capture, coalition capture, end window,
traffic repair, or with Sprint 35's revision 1 attribution; TB without reserve, artillery, transport, guided fire,
counterattack; TC without withdrawal, retention. Two equivalence configurations: `ta-as-ca` (every Sprint 36 rule off)
must decide as Sprint 35's CA, and `tc-no-guard` as Sprint 34 MO. Identities `s36-tactical-<name>-1`.

## 11. Pre-engine quality requirements

Exact historical reconstruction (section 5); no unexplained action difference (the two equivalence configurations);
independent legality checks; no fallback; bounded memory (posts and losses capped; 200,000 bytes gate); latency;
no new dangerous action type; both factions; small and large scenarios; objective coverage (the 20 scenario-sides);
first ownership; traffic; fire and transport interactions; recorded adverse episodes; mutation testing. The 19 Sprint
35 games informed this design and are development data wherever they appear.

Development runs before the registration (private; disclosed, not evidence): the reconstruction of section 5; probes
of TA, TB and TC on two of the 19 Sprint 35 games (positions 12 and 15: the equivalence of `ta-as-ca` and `tc-no-guard`,
0 differing decisions, and TA's stance rows); two model smokes of TA, TB, TC against the inert control (the 13 scenarios of the 20 scenario-sides and the five Stage A
scenarios, both seats) and against `baseline-v2` (Stage A): no crash, rejection, fallback or replay mismatch; all 36
scenario-sides against the inert control at Sprint 34 MO's value; the first smoke found TA and TB decisions of up to
2.3 seconds (the fallback-hex search computed a whole-map field per candidate hex, also growing the terrain cache), fixed
by a bounded local search before the second smoke (maximum 0.43 seconds).

## 12. Offline comparison protocol (registered before it runs)

Rules `src/miaosuan_agent/evaluation/s36_offline.py`, driver `scripts/s36_offline.py`, tests `tests/test_s36_offline.py`.
Agents: `TA`, `TB`, `TC`; frozen controls `S34-MO`, `CM`. Populations, each labelled by evidence level:

* `model` (engine-free model world, no combat): every eligible scenario, both seats, against the inert control
  (`M-inert`) and `baseline-v2` (`M-v2`); ablations against `baseline-v2` in the five Stage A scenarios;
* `genuine` (decision-level): Sprint 34's offline corpus (8 pinned replay-corpus games, 16 timelines) and the 43
  recorded live games (67 games), every seat that is not the inert control, each agent and the two equivalence pairs with their own memory
  chains;
* `episodes` (historical descriptive, open loop): the 35 recorded Stage A live games (16 Sprint 34, 19 Sprint 35): every
  held-objective loss and every own ground unit destroyed standing in a held zone, read at each agent's decisions
  (recognised 150 steps before; presence in the last 300 steps; a valuable unit later destroyed ordered out of the zone
  in the 300 steps before; Sprint 34's departures kept), and the controls' fidelity on their own games.

## 13. Gates

Each required of a candidate: G1 legality (genuine: no validator rejection, no independent illegality; model: no
rejection or refusal); G2 no fallback or contract error; G3 model replay identical, no crash; G4 no model wait of 300
steps or more; G5 genuine p99 at most 100 ms and maximum at most 1,000 ms, model maximum at most 1,000 ms; G6 memory at
most 200,000 bytes; G7 against the inert control, in every scenario-side, model objective value at least S34 MO's; G8
against `baseline-v2`, model objective value at least 95% of S34 MO's (a floor, never a ranking: the model has no combat
and withdrawal can only cost there); G9 every population played (genuine 67 games, episodes 35 games, the model counts of
S34 MO); G10 both equivalence pairs identical at every genuine play decision; G11 each frozen control reproduces its own
recorded live decisions exactly; G12 decisions differ from S34 MO's in at least 1% of genuine play decisions.

## 14. Selection rule

Among the candidates passing every gate, the first in the order TC, TA, TB is selected: the least change from the frozen
Sprint 34 control first. Reasons: in the configurations where Sprint 35 regressed the Sprint 34 control did better; no
offline population measures a combat outcome, so a ranking on offline figures would be a ranking on the movement race;
and a live comparison against a fresh Sprint 34 control attributes a difference most clearly when the candidate differs
from it only by named rules. If none passes: `S36_ENGINEERING_BLOCKED`, no live proposal. Episode figures and ablations
are reported, never selected on.

## 15. Registration

The protocol of sections 12 to 14 and the code it names are committed and pushed before any registered population
runs. Before this registration Sprint 36 agents were run only in the development runs of section 11 (two of the 43
recorded games, and part of the model population); the registered populations are run once, from the registration
commit.

## 16. Revision 1: registered result, diagnosis and correction

**Registered result.** The comparison of sections 12 to 14 ran once on the evaluation server (NUMA node 0, 16 workers)
from the registration commit `fe6820ff2d489948c1612c87d4b82e2745225bdf`, 2026-10-11T02:50:13+08:00 to
04:30:09+08:00: 950 model games (none crashed), 67 genuine games (297,920 play decisions re-decided per agent), 35
episode games. Outputs, unchanged: `evaluation/s36-tactical-recovery/revision-1/{model,genuine,episodes,selection}.json`.
Every candidate passed G1 to G9, G11 and G12 and failed **G10**: `ta-as-ca` differed from Sprint 35's CA at 5 genuine
play decisions (`tc-no-guard` against S34 MO: 0). G10 is a property of the code required of every candidate, so the
registered rule selected none: **revision 1 disposition `S36_ENGINEERING_BLOCKED`**, recorded as such.

**Diagnosis.** The 5 decisions lie in three games (two replay-corpus games, one timeline). `TacticalConfig` declared
`counterattack_bonus = 0.25` as its default, so TA and `ta-as-ca` carried the counterattack bonus that section 10 assigns
to TB only; with the bonus set to 0 the same configuration decides as CA at all 5 (private probe
`local/diagnostics/s36/g10_probe.py`). The synthetic tests never put a recently lost objective in memory, so they could
not see it. TC's decisions are unaffected (its guard reads the assessment, not the coalition places); it failed only
because G10 covers both pairs.

**Correction (revision 2).** The default becomes 0.0 (TB keeps 0.25 explicitly); nothing else changes. Every variant
carries revision 2 (identities `s36-tactical-<name>-2`). A test with a recently lost objective where the bonus changes
the allocation (`tests/test_s36_revision2.py`) fails on revision 1 and passes on revision 2. The correction was decided
after revision 1's result was seen; it corrects a declared design (section 10), and no threshold, rule, population, gate
or selection rule changes.

**Revision 2 comparison (registered before it runs).** The driver, rules, populations, gates and selection rule of
sections 12 to 14, unchanged, applied once to the revision 2 agents from the revision 2 registration commit. No revision
2 agent has been run on a registered population before this registration. If revision 2 also selects nothing, the
disposition is `S36_ENGINEERING_BLOCKED` and no live card is proposed.

## 17. Revision 2: registered result

The comparison ran once from the revision 2 registration commit `2822f1db2aea9f85cded2f9286105d80358ffada`,
2026-10-11T11:10:13+08:00 to 12:50:35+08:00 (NUMA node 0, 16 workers): 950 model games, none crashed; 67 genuine games,
297,920 play decisions re-decided per agent; 35 episode games, the frozen controls reproducing their recorded decisions
at all 66,266 (S34 MO) and 22,689 (CM) decisions. Outputs: `evaluation/s36-tactical-recovery/{model,genuine,episodes,
selection}.json`. The public summaries are written with the publication policy of section 4 (two model latencies
collided with the scan's numeric pattern; the values are unchanged, checked against a plain rewrite, and revision 1's
files are byte-identical either way).

| Measure | TA | TB | TC | S34 MO | CM |
|---|---|---|---|---|---|
| model, against the inert control: objective value (80 games; all objectives 22,480) | 22,480 | 22,480 | 22,480 | 22,480 | 21,130 |
| model, against `baseline-v2`: objective value of the agent's side (80 games) | 19,640 | 19,770 | 18,510 | 18,300 | 19,730 |
| model: longest wait in front of a full hex (steps), against the inert control / `baseline-v2` | 19 / 40 | 75 / 31 | 19 / 19 | 19 / 19 | 20 / 38 |
| genuine: rejected or independently illegal actions / fallbacks / contract errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| genuine: play decisions differing from S34 MO (of 297,920) | 58,791 | 63,266 | 19,111 | 0 | 96,355 |
| genuine: latency, largest game p99 / maximum (ms) | 31.655 / 243.123 | 31.026 / 240.867 | 75.705 / 238.922 | 64.289 / 268.52 | 29.894 / 250.672 |
| genuine: largest memory (bytes of canonical JSON) | 2,812 | 2,812 | 2,741 | 1,878 | 2,671 |
| equivalence: `ta-as-ca` against CA / `tc-no-guard` against S34 MO | 0 / 0 | | | | |

TC's guard dropped 25,662 moves (into zones assessed delay or skip, or taking a kept unit out of its zone) and added
1,364 withdrawals over the genuine decisions. Every candidate passed all twelve gates.

**Episodes** (historical descriptive, open loop: each agent's decisions on the recorded states, never an outcome; 117
held-objective losses and 121 own ground units destroyed standing in a held zone, in the 35 recorded Stage A games of
both frozen policies):

| | TA | TB | TC | S34 MO | CM |
|---|---|---|---|---|---|
| threat recognised 150 steps before the loss (of 117) | 67 | 67 | 67 | - | 69 |
| a unit kept or sent in the 300 steps before the loss (of 117) | 111 | 111 | 110 | 110 | 110 |
| last defenders ordered away in the record, kept by the agent (of 31) | 25 | 25 | 26 | 3 | 25 |
| valuable units later destroyed in the zone, ordered out in the 300 steps before (of 88) | 25 | 25 | 19 | 18 | 15 |
| cheap units later destroyed in the zone, ordered out (of 33) | 0 | 0 | 3 | 11 | 0 |

Reading: on the recorded states the Sprint 36 rules keep last defenders as Sprint 35 did (25 or 26 of 31 against S34
MO's 3) and order out more of the valuable units that later died (TA 25 of 88 against CM's 15); TC, which acts only
through its guard, orders out 19. Most valuable units that died were not ordered out by any agent; why, unit by unit
(no visible threat, contact closer than the 40-step lead, no destination), is not measured here. Whether any of this
saves units or objectives is a combat question these figures cannot answer.

## 18. Selection and the frozen candidate

The registered rule (section 14) selects **TC**, the first of TC, TA, TB to pass every gate (all three passed). Frozen as
`tactical.config.LIVE` in a separate commit; identity `s36-tactical-guarded-orchestrator-2`, policy source
`2f74e88f59654f2bef2719b98979212f83561279161c28f28d90e1c9c4210143` (53 files: `baseline-v2`'s frozen sources, the frozen
packages `integrated/` and `coalition/`, and `tactical/`). TC is the Sprint 34 control's decision cycle unchanged, with
a guard that (a) keeps the units its assessment keeps in a held zone (retention), (b) refuses moves of units that are not
cheap into zones assessed untenable or not capturable, and (c) adds withdrawals of valuable defenders from untenable held
zones before contact, all through the traffic ledger and validated again. Against the inert control it equals S34 MO
in every model scenario-side; against `baseline-v2` in the model it holds 210 more objective points (18,510 against
18,300); on genuine observations it decides differently from S34 MO at 6.4% of play decisions.

What TC does not do: TA's and TB's stance-driven allocation (opportunity capture and the delaying place change where TA
and TB send units, not where TC sends them, except through the guard's refusals) and TB's fire support, guided fire and
safe transport. Those stay offline variants.

## 19. Live study proposal (registered as a proposal; no session is authorized)

Rules `src/miaosuan_agent/evaluation/s36_live.py` (`s36-tactical-live-rules-1`, file SHA-256 `f06d9eb5...`, rule-source
digest `f986bbb7...`), derivation `evaluation.s36_study`, observer `evaluation.s36_capture`, card builder
`scripts/build_s36_card.py`, runners `scripts/run_s36.py --position N` and `scripts/run_s36_game.py`, analysis
`scripts/s36_analysis.py`, references `evaluation/s36-tactical-recovery/references.json` (Sprint 34's rule, plus the
held-out and Stage B configurations), tests `tests/test_s36_live.py`, `tests/test_s36_card.py`. Card
`evaluation/s36-tactical-live-1/manifest.json`, canonical SHA-256
`73166e0ea51ca21e183cc11c38903ec4a6b1da05f82937673945bad868fbef26`, rebuilds byte-identically; it records
`authorized: false`, and the runner refuses every position while it does.

**Budget proposed**: at most 51 sessions, 2846 to 2896, one game per exclusive session, serially, on NUMA node 0. The
next unopened session (2846) is not an authorization. Sprint 35's authorized but unopened 2846 to 2874 are not reused:
they lapsed with Sprint 35; the numbers are simply the ledger's next ones, and a new authorization is required.

| Batch | Positions | Games |
|---|---|---|
| A1 | 1 to 23 | five Stage A scenarios (2130511121, 2120531121, 1930331196, 1910631192, 2010431153): candidate and fresh Sprint 34 control, red and blue against `baseline-v2`, interleaved; the frozen Sprint 35 candidate once in each of its three blue regression configurations (replication, never compared) |
| A2 | 24 to 43 | the twenty candidate and control games again, other order |
| H1 | 44 to 47 | held-out scenario 2010211129 (never used to design or tune a Sprint 36 rule): candidate and control, both seats |
| B1 | 48 to 51 | candidate against the inert control in 201033019601 and 2010131194, both seats (two coverage-regression scenarios) |

**Comparison scale**: share of the stake (margin over objective total plus both sides' maximum remaining-force scores,
read from each game's record). Sprint 35's z is reported beside it, never decided on (section 20).

**Calibration** (`scripts/s36_calibration.py`, `evaluation/s36-tactical-recovery/live-calibration.json`, from the
control's 26 recorded Stage A games, ten configurations, 16 degrees of freedom): pooled within-configuration SD of the
share 0.4187; null SD of `Dbar` (two games per policy and configuration, ten configurations) 0.1324; of the A1 `Dbar`
(one game each) 0.1872. Thresholds: unfavourable at or below -0.2595 (1.96 null SDs), promising at or above +0.2595,
early futility after A1 at or below -0.4822 (2.576 null SDs). Severe-harm rule (a margin more than three reference SDs
below the reference minimum): 0 of the control's 26 and 0 of the Sprint 35 candidate's 9 recorded games would have
triggered it. The normal approximation with 16 degrees of freedom is an approximation, stated as such.

**Stops** (per game, from every recorded game, by the same derivation the report uses):

| Category | Disposition | Rule |
|---|---|---|
| invalid experiment | `S36_LIVE_INVALID` | incomplete game; ledger, file, archive or card change (runner); observer error; replay or reconstruction mismatch; refusal facts not retained; echo-count mismatch; any contract or quality finding of a frozen control |
| systemic agent failure | `S36_AGENT_FAILURE` | candidate: contract error; fallbacks above 1%; latency p99 above 200 ms or maximum above 3,000 ms; memory above 200,000 bytes; a damaging attack on an own unit; a structural or systemic refusal finding (`s36-refusal-gate-1`); a wait of 600 or more consecutive steps in front of a full hex |
| severe tactical harm | `S36_SEVERE_HARM` | candidate margin more than three reference SDs below the reference minimum (any game); after A2, a configuration with both candidate margins below the reference minimum; at the end, Stage B objective score below the reference minimum in two or more of four games |
| unfavourable | `S36_UNFAVOURABLE` | after A1, `Dbar` at or below -0.4822; after A2, at or below -0.2595 (H1 and B1 are then not played) |

At the end of the schedule: `S36_PROMISING` (`Dbar` at least +0.2595, `d_s` positive in at least four of five
scenarios, held-out mean `d` at least 0, no Stage B coverage shortfall); `S36_INCONCLUSIVE_UNFAVOURABLE_DIRECTION`
(`Dbar` below 0: ordinary unfavourable stochastic performance); otherwise `S36_INCONCLUSIVE`. A single routine refused
shot never stops the study; a contract violation always does. Nothing is promoted, merged or uploaded whatever the
result.

**Stand-in rehearsals** (the model world behind the engine interface, temporary ledger, committed tree on the server,
`local/diagnostics/s36/standin_rehearsal.py`): with the real references the study stopped at position 4 on severe harm
(150-step model games without combat score far below a real game), exit 5, as designed; with permissive references all
51 positions ran (50 exits 0, the last 5, schedule complete, `S36_INCONCLUSIVE`); in both, a replayed position and an
unauthorized one were refused and every decision of all three policies was reconstructed (0 mismatches).

## 20. Measurement findings outside the gates

* **The z scale.** z against `baseline-v2`'s own games is dominated by configurations whose reference SD is small: one
  Sprint 34 control game in 2130511121 as red scored z = 17.9 (`live-calibration.json`). Sprint 35's statement "mean z
  0.189 against the control's 0.018" compared unpaired means over different configuration sets. Paired by configuration
  (nine configurations, one game each, development data, not a registered comparison), the Sprint 35 candidate's mean
  difference from the control was -0.399 in z and -0.113 in share of the stake.
* **The wait metric** (section 8) and the **refusal share** (section 3) were measurement artefacts that the new
  observer and gate replace.
* **Corrections to earlier text**: Sprint 35's description of the code-203 refusal (section 2); this document's header
  date, which should read 2026-10-11 (UTC+8): the registered text is left as written.

## 21. Readiness, identities, privacy and the ledger

| Check | Result |
|---|---|
| Sprint 36 tests | `tests/test_s36_refusals.py`, `test_s36_study.py`, `test_s36_tactical.py`, `test_s36_offline.py`, `test_s36_live.py`, `test_s36_gaps.py`, `test_s36_revision2.py`, `test_s36_card.py` |
| Workstation suite (final commit) | 2,612 tests, 113 skipped, OK; a clean clone of the final commit: the same |
| Evaluation server (Python 3.10, NUMA node 0) | Sprint 34, 35 and 36 suites: 224 tests OK; every public output regenerates byte-identically (refusal audit, Sprint 35 re-derivation, references, calibration, reconstruction, card) |
| Mutation (`scripts/mutate_s36.py`, `mutation.json`) | 48 of 48 planted defects killed; the first run killed 40 of 47 (5 test gaps closed by `tests/test_s36_gaps.py`, 2 equivalent mutants replaced), the revision 1 counterattack default added as a mutant |
| Per-commit check | every Sprint 36 commit of the registration imports and passes the Sprint 36 tests present at it |
| Document check (private `local/diagnostics/s36/doc_check.py`) | 71 clauses bound to the committed result files; 22 of 22 planted one-figure changes caught |
| Platform canary | rebuilt from the final commit: `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, smoke 62 steps, independent verifier 8 of 8 planted defects caught |
| Privacy | pre-push scan of the published scope (a bare clone, the other session's `platform-compat2` branch excluded as before): 1,444 blobs, 106 hits, identical to the accepted baseline; no metric dropped |
| Engine | no session opened in Sprint 36; ledger 2,845 sessions, all closed, SHA-256 `f396b2a137100dedc1c912bffc412a2c92e77ed06fe85988db972feb0919a927` unchanged; no lock file |

Identities: candidate `s36-tactical-guarded-orchestrator-2` (`2f74e88f...`, 53 files); controls `baseline-v2`
(`7cbaf032...`), S34 MO (`b107d23e...`), S35 CM revision 2 (`ea38c042...`); card `73166e0e...` (unauthorized). Nothing
was promoted, merged into `main` or uploaded; `main`, `platform-compat2` and every earlier branch are untouched.

## 22. Status and the one question

Sprint 35's registered disposition `S35_LIVE_INVALID` stands. Sprint 36 offline: revision 1 `S36_ENGINEERING_BLOCKED`
(G10), revision 2 selected TC; live disposition now `S36_LIVE_NOT_AUTHORIZED`. Sessions opened in Sprint 36: none.

The one question for the owner: **authorize up to 51 Sprint 36 engine sessions, 2846 to 2896, under the frozen card
`73166e0e...` and rules `s36-tactical-live-rules-1`?** An authorization would be recorded by a new commit that sets
`authorized` in the card builder and rebuilds the card (a new card digest, everything else unchanged); until then the
runner refuses every position.
