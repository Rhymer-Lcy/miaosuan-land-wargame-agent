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
