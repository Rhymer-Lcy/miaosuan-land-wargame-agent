# Sprint 35: coalition-aware integrated agent

Date: 2026-10-10 (UTC+8). Track: `EXPLORATORY` (`docs/EXPLORATORY_TRACK.md`). Branch `sprint35-coalition-agent`, created
from the Sprint 34 head `f56123019fccda58431638babe7348e17749340e`; `main`, every earlier sprint branch and the
independently maintained `platform-compat2` branch are not modified. The Sprint 34 package
`src/miaosuan_agent/integrated/` is imported and never edited: its source digest is the identity of the frozen control.

This sprint builds the successor the Sprint 34 disposition called for: an agent that decides, per objective and with
capability-weighted estimates of known force, whether to hold, reinforce, delay or skip, keeps the last defenders of a
threatened objective, and forms coalitions instead of sending detachments one by one. No engine session is authorized
yet; everything below is offline, and the live design (section 11) is a proposal for the owner's approval.

## 1. Authorization and verified state at the start

The owner's Sprint 35 prompt authorizes offline work, archival of the supplied ZIP files and the preparation of a live
experiment; a budget of at most 48 sessions, 2827 to 2874 inclusive, is proposed and is not authorized. State verified
before any work:

| Item | Verified value |
|---|---|
| `main` (workstation, GitHub, evaluation server) | `08aff3fd47c2ec9e505276ff93eaef0ddb09ef85` |
| Sprint 34 branch `sprint34-integrated-agent` (workstation, GitHub, server) | `f56123019fccda58431638babe7348e17749340e` |
| `platform-compat2` | `a909557bb43648c5c879c19ad8f8ba362e8f4892`, untouched |
| `baseline-v2` policy source | `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` (recomputed) |
| Sprint 34 live candidate policy source | `b107d23ecdb57d9efb42610818eae60b64311480529d26dfdb6e2976ebcdad3b` (recomputed) |
| Sprint 34 live card | canonical SHA-256 `4bb778eda0d7aeaed867fdefb06ad98ec9a5c7ee8bb58550c4b007034cfa5304`, rebuilds byte-identically |
| Engine ledger | 2826 sessions opened and closed, none open, integrity ok; SHA-256 `2359e9cf094681c38ac8ddcd14a4a39c7ecafd660a73f07e53b9344c950b624c` |
| Sprint 34 public results | `evaluation/s34-integrated-live-1/results.json` and every stored per-game analysis regenerate byte-identically from the private records |

The shared primary checkout carries another session's uncommitted platform-builder edits; they were left as found and
all Sprint 35 work is in a separate worktree. On the evaluation server Sprint 35 runs in its own worktree on NUMA node 0
(`docs/SERVER_RESOURCE_POLICY.md`).

## 2. Collaborator evidence

### 2.1 Archival

Four ZIP files were found at the repository root, matching the four known SHA-256 values exactly; each passed a ZIP
integrity test, was copied with exclusive creation into the private, git-ignored folder
`local/references/teammate/20261010/` (subfolders `agent-source`, `comparison-replays`, `supplementary-replays`) under a
descriptive name, re-hashed and byte-compared, and only then removed from the root. No member was modified, no existing
file was overwritten, and the preliminary SDK handoff under `local/handoffs/teammate/` was not touched. A provenance
manifest (original name and location, destination, hash, size, scenario, attribution, evidence status, verification)
is kept beside them. None of it is committed.

| Original file | SHA-256 | Kind | Evidence status |
|---|---|---|---|
| `ai.zip` | `fda7decf3d494b0e4c5a908250101e027c2438684e22191d040a8a881a8ec978` | agent source, an earlier version | source supplied, version unverified |
| `replay_1791618567.6015677.zip` | `4a77e34cf11980166998f1c5d2488ea4aef7b2976903abb688076a0a9b89929a` | replay 8567 | owner-designated comparison |
| `replay_1791618700.9385283.zip` | `a111799acb64e06da8a3ad621a301ef8f7f05dc6de0d23d4ec397f0bbd8b07c8` | replay 8700 | owner-designated comparison |
| `replay_1791620047.5100904(1).zip` | `d1d8ef2a795be245fb992075cb49b3db140b02e8ed405d0fae7f0e3e3897dd30` | replay 0047 | supplementary, unattributed |

### 2.2 The source package

The supplied package is the SDK's demonstration agent extended with four modules (artillery, unmanned aerial vehicle,
infantry, infantry fighting vehicle) and setup bookkeeping. Findings against the owner's questions:

* **Entry point (C).** `ai/agent.py` defines `step()` and `step2()`; the four modules are called only from `step2()`, and
  `step()` never calls it. `step()` sends a chat message (action 204) at every step; `step2()` sends graphic markers
  (action 205) for remembered enemies.
* **Deployed package versus the archive (D).** In all three replays the seat the owner attributes to the collaborator
  sends graphic markers (402, 493 and 436) and no chat message; the other seat sends neither. So the executed entry point
  was `step2()` or a modified `step()`, not the archived `step()`. In the archive the markers' list is never filled (the
  code filling it is commented out), so the executed package also differs from the archive in that respect.
  Package identity: **UNVERIFIED**; the archive is an earlier version, as the owner said.
* **Functions enabled (E).** In the archive the infantry fighting vehicle module's priority table has its shot
  commented out, and in all three replays the collaborator's infantry fighting vehicles never emit a direct shot; they
  take part in fire only as the carriers of guided shots. The reported enabling of infantry fighting vehicle attacks is
  therefore not present in these replays.
* **Information used (I).** At setup the package reads `setup_info["state"][-1]["operators"]`. In the SDK's offline
  runner (`run_offline_games.py`) `setup_info["state"]` is the list of the three seats' states and its last element is
  the all-seeing (director) state; the package records every enemy operator's strength, passengers and air-defence
  weapons from it. Whether the competition platform passes the same object is not established; on the SDK runner the
  agent starts with information about the enemy that its own observation does not contain.
* **Randomness (G).** Movement destinations, embark targets and several state changes are drawn with `random`; replays
  8700 and 0047 (collaborator red in both, by the marker evidence) first differ at step 1 in the collaborator seat's own
  orders. A single game of this agent is one draw.
* **Opponent (H).** In the replays the opponent seat sends only moves, occupations and shots, which is consistent with a
  `baseline-v2`-like agent and inconsistent with the SDK demonstration agent (which also sends state changes, stops and
  embarks at random); consistency is not identity, so the opponent of each replay is the owner's designation. The
  screenshot showing red +404 is not any of these replays (their red margins are -780, -360 and +122) and has no
  provenance; it is not used.

### 2.3 The comparison replays (scenario 2020331196, terrain 123)

`scripts/s35_collaborator_replays.py` reads the replays' all-seeing frames and publishes aggregates only
(`evaluation/s35-coalition-agent/collaborator-replays.json`); emitted actions, accepted actions and observed effects are
kept apart. The runner echoes every submitted action, with an error code when the engine refuses it.

| | 8567 (collaborator blue) | 8700 (collaborator red) | 0047 (unattributed; markers from red) |
|---|---|---|---|
| Final margin of the collaborator's seat | +780 | -360 | +122 (red) |
| Deployment-stage embark (emitted, effect within the stage) | 6 squads | 3 squads, 3 unmanned ground vehicles | 3 squads, 3 unmanned ground vehicles |
| Disembark during play (effect) | 6 squads | 6 loitering munitions launched, no squad or vehicle | 6 loitering munitions launched |
| Indirect fire plans / cancellations / refused plans | 159 / 137 / 5 | 234 / 154 / 70 | 162 / 136 / 0 |
| Indirect-fire judge records (with damage) | 21 (6) | 25 (10) | 46 (17) |
| Guided shots emitted / judge records with damage | 0 / 0 | 1 / 1 | 4 / 4 |
| Infantry fighting vehicle direct shots emitted | 0 | 0 | 0 |
| Same-colour judge records | 0 | 0 | 0 |

What the replays establish: on this engine a squad or unmanned ground vehicle can board a carrier during the deployment
stage, with the effect visible before play starts; a guided shot by a guiding unit, with an infantry fighting vehicle's
missile, is accepted and judged; cancelling an indirect-fire plan works (refused only when no plan exists). What they do
not establish: the tactical value of any module, because each is one stochastic game in one asymmetric scenario, and the
module that produced an action is inferred from the archive, which is not the executed package. No head-to-head result
against the collaborator's current agent exists, and none is claimed.

## 3. Sprint 34 reproduced, and its losses read episode by episode

Sprint 34's figures were regenerated first (section 1). Then three post hoc studies of its 16 Stage A games, all
descriptive, from the private records on the evaluation server, published as aggregates:

**Loss episodes** (`scripts/s35_loss_episodes.py`, `evaluation/s35-coalition-agent/loss-episodes.json`). The 57 losses of
a held objective are reproduced: at the last held step every zone held no own ground unit and 2 to 4 enemy ground units
in 42 of them; 150 steps earlier 41 zones held 1 to 3 own units. Following the last own units that stood in the zone
(without a move path) to their end: in 38 episodes they were destroyed, in 18 they were ordered away alive by Sprint 34's
own allocation (to hold another objective 9, to capture one 7, for transport 2), in 1 none had stood there within 1,800
steps. These last defenders were single units: 20 infantry fighting vehicles, 14 tanks, 11 unmanned ground vehicles, 2
squads and 9 others. The seat saw the attackers coming: in all 57 episodes an enemy ground unit was visible within 8
hexes of the objective in the 600 steps before the loss. Over 3,306 sampled held-objective states (every 25 steps), the
rule "more visible enemy ground units within 8 hexes than own ground units in the zone" flagged 446 of the 495 states
lost within 300 steps and 513 of the 2,811 that were not. In 56 of the 57 episodes some own unit could have reached
the objective in time at free-flow speed, but in only 10 was that unit free or in reserve. The objective fell a median
of 41 steps after the first enemy ground unit entered the zone.

**Unit losses** (`scripts/s35_unit_losses.py`, `evaluation/s35-coalition-agent/unit-losses.json`). 156 own ground units
were destroyed in the 16 games: 55 standing in a held objective's zone, 30 aboard a carrier (the transport module's
lift plan covered 29 of them), 28 moving elsewhere. The exchange was unfavourable in 1930331196 (own 24 lost against 11
as red, 25 against 19 as blue) and favourable in 2130511121 (30 against 37 as red, 21 against 48 as blue).

**Capability rates** (`scripts/s35_capability_weights.py`, `evaluation/s35-coalition-agent/capability.json`). Direct-fire
damage dealt per 1,000 alive unit-steps over the 24 live games: tank 2.2945, infantry fighting vehicle 0.5593, unmanned
ground vehicle 0.4242, squad 0.0886. Squads received direct and indirect damage at about a tenth of the vehicles' rate per
unit-step in these games.

Diagnosis. An objective is lost only when no own ground unit is left in its zone, because occupation is not listed while
an enemy ground unit is in it (Sprint 34, section 3). Sprint 34 lost objectives in two ways: by moving the last defender
elsewhere (18), and by leaving one vehicle to face several (38). The first is a decision error a retention rule removes.
The second is a concentration failure, but not one a head count can repair: the defenders were destroyed by tanks and
vehicles whose capability differs fivefold, reinforcements existed but were committed elsewhere, and in many cases no
reinforcement could have been decisive; the right answer is then to keep a survivable, cheap holder and save the
expensive units. Transport cost units: a destroyed carrier took its passenger with it in 30 cases.

## 4. Capability inventory

Listing frequency from both seats' observations in the 24 Sprint 34 live games
(`scripts/s35_capability_inventory.py`, `evaluation/s35-coalition-agent/capability-inventory.json`).

| Capability | Input contract | Listed (Sprint 34 games) | Engine evidence | Status in Sprint 35 |
|---|---|---|---|---|
| Move, occupy, direct fire | Sprint 34 | always | engine-verified (Sprint 34) | IMPLEMENTED, ENGINE-VERIFIED, TACTICALLY EVALUATED (Sprint 34) |
| Embark / disembark in play | Sprint 34 | squads and unmanned ground vehicles with a carrier | engine-verified (Sprints 22, 34) | IMPLEMENTED, ENGINE-VERIFIED; variant B limits it to objectives without a known threat |
| Indirect fire (stationary targets) | weapon option | artillery, every decision | engine-verified (Sprints 8, 34) | IMPLEMENTED, ENGINE-VERIFIED |
| Indirect fire at a predicted arrival hex | weapon option, `jm_pos` | as above | the order is engine-verified; aiming at a predicted position is not | EXPERIMENTAL (variant B, own feature gate) |
| Guided fire (action 9) | target, weapon, guided carrier | 1,309 to 4,148 options per game against the inert control (red: squads and unmanned ground vehicles guiding an infantry fighting vehicle's missile); 4 to 24 in two head-to-head games | accepted and judged with damage in the collaborator replays (5 of 5); never issued by this project | EXPERIMENTAL (variant B, own feature gate) |
| Cancel indirect fire (action 13) | none | while a plan is live | works in the collaborator replays | DISABLED: no rule needs it (orders are never planned on moving targets in variant A) |
| Deployment-stage embark | target carrier | squads and unmanned ground vehicles, all four scenarios | effect within the deployment stage in the collaborator replays | DISABLED: passengers aboard were 30 of 156 own ground losses; starting aboard adds that exposure from step 1 and no evidence of a benefit exists |
| Split (action 14) in deployment | none | 3 of 4 scenarios | Sprint 1: accepted in 3 of 8 scenarios, blocks columns | DISABLED (Sprint 2 diagnosis) |
| Stop, concealment, weapon lock | Sprint 34 | - | mechanism results (Sprints 6, 33) | DISABLED (no measured benefit) |
| Loitering munition launch | disembark of a munition | red in some scenarios | launched in the collaborator replays | UNSUPPORTED: the agent never launches one |

## 5. Evidence to architecture

| Problem | Evidence | Sprint 35 design |
|---|---|---|
| Last defender sent elsewhere | 18 of 57 losses | retention: the standing defenders of a threatened held objective leave the free pool (secure: those reaching the requirement and the best holder; defend and delay: all, unless a justified withdrawal) |
| One vehicle left against several | 38 of 57 losses | capability-weighted threat and defence per objective; reinforcement places only when defenders plus units arriving before the enemy reach the commit ratio; otherwise delay with a cheap holder and withdrawal of the valuable defenders |
| Threats counted against every objective at once | the first draft's model games (section 9) | each known enemy counts against one objective: the one its visible path ends at, else the one it reaches first |
| Detachments sent one by one into a contested objective | Sprint 34 capture slots 1.0 / 0.5 / 0.3 | coalition capture: places for the smallest group reaching the capture ratio, else skip |
| Passengers lost with their carrier | 30 of 156 losses | variant B: lifts only to objectives without a known threat |
| Artillery firing at whatever is stationary | Sprint 34 targeting | variant B: targets threatening a held objective first; arrival fire on the enemy's path end |
| Guided fire unused | listed thousands of times, never issued | variant B: guided fire with exact-option validation |
| Column deadlock | 0 waits in Sprint 34's 24 games | unchanged: every move still goes through Sprint 34's traffic ledger and route planner |

## 6. Architecture

Package `src/miaosuan_agent/coalition/` (Sprint 34's `integrated/` imported, unchanged):

```
observation -> world view (integrated.world) + enemy maximum strength from the observation
            -> memory upkeep: Sprint 34's + class-aware sightings (coalition.memory)
            -> lift life cycle (integrated.transport)
            -> traffic ledger, hazards, threat route costs (integrated.traffic, integrated.fire)
            -> known threats with confidence; attribution of each enemy to one objective (coalition.capability)
            -> objective stances: quiet, secure, defend, delay, capture, coalition, skip (coalition.coalition)
               kept defenders and withdrawing units leave the free pool
            -> allocation over the stance places (coalition.allocator; Sprint 34's greedy solver and lift pairs)
            -> recovery and dispersal (Sprint 34's)
            -> arbitration: occupy > lift order > direct fire > guided fire (B) > move > stay
            -> indirect fire: Sprint 34's rule (A) or stance-driven support and arrival fire (B) (coalition.support)
            -> validation: Sprint 34's validator plus guided fire (coalition.validate)
            -> actions + memory (stances, sightings)
```

The stance rules are in the module docstring of `coalition/coalition.py`; the force estimate in
`coalition/capability.py`. The memory adds one stance record per objective and at most 96 class-aware sightings, each
expiring after 600 steps, so it stays bounded. Any exception other than a contract violation falls back to
`baseline-v2`'s decision, recorded, as in Sprint 34.

| | Variant A `coalition-allocator` (CA) | Variant B `coalition-mission-planner` (CM) |
|---|---|---|
| base | Sprint 34 MO configuration | the same |
| stances, retention, reinforcement, withdrawal, coalition capture, reserve | yes | yes |
| indirect fire | Sprint 34's guarded rule | stance priority + arrival fire, same guards |
| guided fire | no | yes |
| transport | Sprint 34's | only to objectives without a known threat |

Ablations (`coalition/config.py`): each core feature of A switched off alone; each feature of B switched off alone; B
without transport.

## 7. Design choices and their reasons

* Class weights: the damage rates of section 3 divided by the tank's and rounded to 0.05 (tank 1.0, infantry fighting
  vehicle 0.25, unmanned ground vehicle 0.2, squad 0.05; other ground classes 0.15); every own ground unit weighs at
  least 0.05, because any one of them in the zone prevents occupation. Power = weight times remaining strength fraction.
* Remembered sightings lose confidence linearly over 600 steps (Sprint 34's sighting lifetime) and keep the class and
  strength last seen.
* Threat horizon 600 steps of optimistic arrival; attribution to one objective per enemy.
* Defend ratio 1.0: defenders standing still fire first and only tanks fire on the move (Sprint 34 facts), so parity in
  weighted power is taken as enough to hold; commit ratio 0.6: reinforcement is sent only when defenders and arrivals
  together reach most of the threat, so that units are not fed one by one into a fight that is lost anyway.
* Capture ratio 1.2: an attacker must move into the defenders' fire.
* Reinforcement deadline: the enemy's optimistic arrival plus 40 steps (the 41-step median of section 3).
* Withdrawal: only from a delay stance, only when at least half of the threat is visible now (never on memory alone),
  only for a unit worth more than the holder who stays, and only to a held objective not itself in delay.
* Dwell 75 steps before a defend or secure stance may drop to delay; upgrades are immediate.
* Reserve: two places of weight 0.25 at each secure or defend objective.
* Arrival fire window: path end reached between 150 and 375 steps after the order (flight, then within the 225 steps of
  explosion that remain after the 75-step arrival transition starts).

None of these values was tuned on an engine outcome. The first draft counted every enemy against every objective; in the
model world that made the agent skip almost every contested objective (section 9), and attribution was introduced
before any registered comparison.

## 8. Offline comparison protocol and selection rule (registered before the comparison ran)

Rules `src/miaosuan_agent/evaluation/s35_offline.py`, driver `scripts/s35_offline.py`, tests `tests/test_s35_offline.py`.
Agents: `CA`, `CM`, and the control `S34-MO` (the frozen Sprint 34 live candidate). Populations:

* `M-inert`, `M-v2`: every scenario eligible under Sprint 34's registered naming rule, both seats, each agent against
  the inert control and against `baseline-v2`, in Sprint 34's model world (no combat damage); the ablations against
  `baseline-v2` in the five Stage A scenarios of section 11;
* `G`: genuine engine observations - Sprint 34's offline population (the pinned replay corpus, both seats, and sixteen
  full-step timelines) plus the 24 Sprint 34 live games, every seat that is not the inert control - re-decided by each
  agent with its own memory chain;
* `P`: the 57 loss episodes, on the Sprint 34 candidate's recorded observations of the sixteen Stage A games, re-decided
  by each agent over the whole game.

Measured: legality by the agent's validator and by an independent check (the frozen project gate for move, shoot and
occupation; the listing and exact option for embark, disembark, indirect and guided fire), fallbacks, contract errors,
model replay identity, model waits, latency, decisions differing from `S34-MO`'s on the same observation, model
objective value, friendly exposure; in `P`, whether the objective's stance at the decision 150 steps before the loss was
secure, defend or delay (recognised), whether the last defenders Sprint 34 ordered away were kept (no move of that unit
ending outside the zone at that decision), and whether the agent responded in the 300 steps before the loss.

Fidelity condition: `S34-MO`'s re-decisions on its own recorded games must reproduce its recorded actions at every
decision; otherwise `P` is invalid and nothing is selected.

Gates, each required of a candidate: G1 no rejected, refused or independently illegal action; G2 no fallback or contract
error; G3 every model replay check identical; G4 no model wait of 300 steps or more; G5 genuine p99 latency at most
100 ms and maximum at most 1,000 ms, model maximum at most 1,000 ms; G6 decisions differing from `S34-MO` in at least 1%
of genuine play decisions; G7 no model friendly exposure; G8 every population played; G9 threat recognised 150 steps
before the loss in at least half of the episodes; G10 last defenders kept in at least half of the departure episodes;
G11 model objective value at least 90% of `S34-MO`'s in each model population (no collapse of the movement race; the
model has no combat, so this is a floor, never a ranking).

Rule: if both candidates pass every gate, `CM` is selected when its model objective value is at least 98% of `CA`'s in
both model populations, otherwise `CA`; if one passes, it; if neither, nothing (`S35_ENGINEERING_BLOCKED` unless a
corrected revision, documented as such, passes). The 98% clause repeats Sprint 34's reasoning: B's extra modules have
engine-listed or engine-verified mechanisms but no value the model can show, while any movement they cost is
measurable. Ablations are reported, never selected. The model is not used to rank concentration or fire support.

## 9. Adversarial and module tests

`tests/test_s35_coalition.py` (synthetic 12 x 12 states, each expectation computed by hand in the test). Owner's list:

| # | Situation | Test |
|---|---|---|
| 1 | high-value objective held by several enemies | weak force skips it and sends nobody; two tanks form a coalition |
| 2 | enemy mass heading for one of several objectives | the threatened one is skipped, the force goes to the other |
| 3, 4 | objective captured but hard to keep; small force against a larger known one | delay: the only defender is kept, no reinforcement is fed in |
| 5 | unequal capability | three squads do not threaten one tank; one tank does threaten three squads |
| 6 | hidden enemy, stale sighting | threat halves at 300 steps and vanishes at 600 |
| 7 | reserve for one objective without losing another | the free tank reinforces; the other objective's holder stays |
| 8 | two competing reinforcement requests | one unit, one destination, deterministic |
| 9 | infantry-carrier pair with a conflicting task | a kept squad is not lifted |
| 10 | carriers toward a saturated hex | reinforcements stand in the zone, at most two per hex, never a fourth on the objective hex |
| 11 | impact area on a newly planned route | no indirect fire within clearance of a planned stand |
| 12 | target gone before the attack | no target, no order |
| 13 | unit on an irrevocable route | never re-ordered |
| 14 | invalid or missing option | guided options with attack level 0 or a missing weapon are ignored; the validator rejects any changed field |
| 15 | deployment-stage split | the deployment decision emits only the completion |
| 16 | disembarked infantry with no task | stays |
| 17, 18 | few operators; many heterogeneous operators | one unit moves; 40 against 30 units: no fallback, no rejection, at most four planned per hex |
| 19 | no artillery or transport | only moves |
| 20 | online decision-time budget | the 40-unit state decides in under one second |

Further tests: retention against a better-scoring slot (and its ablation), the dwell, withdrawal only on visible threat,
attribution of each enemy to one objective, variant A's indirect fire identical to Sprint 34's, decision purity and
replay, bounded canonical memory, guided-fire target and carrier reservation, arrival-fire window, threat-priority
targeting.

Development history recorded before the registered comparison: the first draft (threat of every known enemy against
every objective) was run once in the model world against `baseline-v2` in the five Stage A scenarios; it skipped almost
every contested objective (as blue in 2130511121 it held 80 objective points where `S34-MO` held 440). Attribution and
the reinforcement grace were introduced, and the same development run then showed the movement race restored. These
development runs are not part of the registered comparison and are not evidence of tactical value.

## 10. Revision 1: registered result, diagnosis and correction

**Registered result.** The comparison of section 8 ran once, on the evaluation server (NUMA node 0, 16 workers), from the
registration commit `0aa2c770055c261db6c0e97730efa38c4221ec5f`; its outputs are kept unchanged in
`evaluation/s35-coalition-agent/revision-1/`. 580 model games, none crashed; 48 genuine games, 203,678 decisions re-decided
per agent; the 57 loss episodes. The control's re-decisions reproduced its recorded actions at all 41,776 decisions.

| Measure | CA (revision 1) | CM (revision 1) | `S34-MO` |
|---|---|---|---|
| M-inert: objective value (80 games; all objectives 22,480) | 21,130 | 21,130 | 22,480 |
| M-v2: objective value of the agent's side (80 games) | 19,490 | 19,490 | 18,300 |
| model: longest wait in front of a full hex (steps) | 40 | 40 | 19 |
| genuine: rejected or independently illegal actions / fallbacks / contract errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| genuine: play decisions differing from `S34-MO` | 71,431 of 203,600 | 71,588 of 203,600 | 0 |
| genuine: latency p99 / maximum (ms) | 36.507 / 235.105 | 36.491 / 235.041 | 35.419 / 238.676 |
| genuine: guided shots | 0 | 4,470 | 0 |
| P: threat recognised 150 steps before the loss | 26 of 57 | 26 of 57 | (no stances) |
| P: last defenders ordered away by Sprint 34 kept | 17 of 18 | 17 of 18 | 0 of 18 |

Both candidates passed G1 to G8, G10 and G11 and failed G9 (26 of 57 is below half). Registered rule: **no candidate
selected**. By the rule this is `S35_ENGINEERING_BLOCKED` unless a corrected revision, documented as such, passes.

**Diagnosis (post hoc).** At the decision 150 steps before the loss the stance was quiet in 22 episodes
(`local/diagnostics/s35/posthoc_quiet.py`, private). In 4 no enemy ground unit was visible within 8 hexes. In the other
18 the visible enemies within 8 hexes were all attributed to another objective: they stood at, or their path ended at,
a neighbouring objective, which their side had usually just taken. Revision 1 counted an enemy against the objective it
can reach first whoever holds it, so an enemy standing on its own objective was a threat only to that objective. But an
objective is captured only by moving onto one the side does not hold, and `baseline-v2` sends idle units from its held
objectives to the nearest one it does not hold: such an enemy threatens the next objective, often the one about to be
lost.

**Correction (revision 2).** `capability.attribute` now counts each enemy against an objective its own side does not hold:
the one its visible path ends at if its side does not hold it, else the one of those it can reach first. Nothing else
changed: the class weights, ratios, horizon, deadlines, dwell, places, fire, transport and every gate and threshold are
the same. The correction was decided after revision 1's population `P` result was seen, and before its model population
had finished; it is a defect correction of the threat model, documented here, not a tuning of a threshold. It carries a
new identity (`s35-coalition-coalition-allocator-2`, `s35-coalition-coalition-mission-planner-2`); revision 1 stays
reproducible as the ablations `ca-r1-attribution` and `cm-r1-attribution`. A test pins the corrected behaviour (an enemy
standing on its side's objective is counted against the own objective six hexes away; revision 1 called that objective
quiet).

**Revision 2 comparison (registered before it ran).** The same driver, rules, populations, gates and selection rule as
section 8, unchanged, applied to the revision 2 candidates; outputs in `evaluation/s35-coalition-agent/`. No revision 2
agent was run on any of the registered populations before this registration. If revision 2 also fails, the disposition is
`S35_ENGINEERING_BLOCKED` and no live card is proposed.

## 11. Live design (a proposal for the owner's approval; registered before any session)

No engine session is authorized. Proposed budget: at most 48 sessions, 2827 to 2874 inclusive, one game per exclusive
session, serially, on NUMA node 0. Rules `src/miaosuan_agent/evaluation/s35_live.py` (`s35-coalition-live-rules-1`),
observer `src/miaosuan_agent/evaluation/s35_capture.py`, card builder `scripts/build_s35_card.py`, runners
`scripts/run_s35.py --position N` and `scripts/run_s35_game.py`, analysis `scripts/s35_analysis.py`, tests
`tests/test_s35_live.py` and `tests/test_s35_card.py`. Position n opens session 2826 + n.

| Batch | Positions | Sessions | Games |
|---|---|---|---|
| A1 | 1 to 20 | 2827 to 2846 | first repetition: in 2130511121, 2120531121, 1930331196, 1910631192, 2010431153, the candidate and the fresh Sprint 34 control each red against `baseline-v2` (H1) and blue against it (H2) |
| A2 | 21 to 40 | 2847 to 2866 | the same twenty configurations, second repetition |
| B1 | 41 to 44 | 2867 to 2870 | the candidate against the inert control: 2120531121 C2 (candidate red), C3 (candidate blue), 1930331196 C2, C3 |
| B2 | 45 to 48 | 2871 to 2874 | the same four configurations, second repetition |

Order inside a scenario's four Stage A games: candidate red, control red, control blue, candidate blue; or control red,
candidate red, candidate blue, control blue; alternating by scenario, and the other way round in the second repetition,
so that neither policy nor seat always comes first. The card's fixed global seed is set before every game as in every
earlier card; it is not claimed to pair the engine's randomness across games (Sprint 26's prefix check failed on
stochastic games), so the comparisons are between independent stochastic runs grouped by scenario and seat.

**References** (`evaluation/s35-coalition-agent/references.json`, Sprint 34's rule plus 2010431153: `baseline-v2`'s own
games of the same scenario, condition and seat, 15 per configuration; the opponent of every Stage A game is the same
`baseline-v2`):

| Configuration | Seat | Margin mean | SD | Min | Max | Objective score mean (min) | Remaining-force score mean (min) |
|---|---|---|---|---|---|---|---|
| 2130511121 C1 | red | -869.9 | 114.66 | -1,055 | -719 | 20.0 (0) | 43.7 (12) |
| 2120531121 C1 | red | -245.0 | 586.60 | -871 | 489 | 112.7 (0) | 51.1 (0) |
| 1930331196 C1 | red | 179.6 | 453.24 | -508 | 756 | 195.3 (0) | 98.9 (12) |
| 1910631192 C1 | red | -85.9 | 233.89 | -334 | 236 | 52.0 (0) | 25.1 (16) |
| 2010431153 C1 | red | -235.1 | 156.49 | -366 | 302 | 8.7 (0) | 9.6 (0) |
| 2120531121 C2 | red | 357.0 | 50.14 | 297 | 457 | 310.0 (310) | 334.0 (334) |
| 2120531121 C3 | blue | 588.3 | 14.86 | 559 | 599 | 310.0 (310) | 407.0 (407) |
| 1930331196 C2 | red | 272.9 | 4.13 | 258 | 274 | 310.0 (310) | 323.0 (323) |
| 1930331196 C3 | blue | 570.0 | 0.00 | 570 | 570 | 310.0 (310) | 407.0 (407) |

In a C1 game the blue margin is the negative of the red one, so the blue reference is the mirror of the red row.
Against the inert control `baseline-v2` never loses a unit, so a Stage B remaining-force score below the minimum means
that the candidate lost a unit.

**Structural stops** (either policy's game; any one closes the study at once; `S35_LIVE_INVALID`): S1 to S6 exactly as in
Sprint 34 (incomplete game; ledger not exactly the schedule so far, closed with integrity ok and state and home unchanged;
a tracked file, the SDK archive or a policy source changed; a contract, in-game replay or observer error; any
reconstruction mismatch or more than 1% fallbacks; more than 2% refused unit actions or more than five refused non-shoot
actions); S7 decision latency p99 above 200 ms or maximum above 3,000 ms (Sprint 34's live p99 at most 24.77 ms,
maximum 988.354 ms; revision 1's offline genuine p99 at most 36.507 ms); S8 any damaging judged attack of the
policy on its own units (Sprint 34: none in 24 games); S9 the policy's memory above 200,000 bytes of canonical JSON at any
decision (bounded by design).

**Severe harm** (candidate games only; closes the gate; `S35_INTEGRATED_REJECT`): after A1, a candidate margin more than
three reference SDs below the reference minimum (Sprint 34's rule); after A2, a configuration whose two candidate margins
are both below the reference minimum (about 1 in 256 per configuration under `baseline-v2`'s own distribution); at any
batch, a candidate ground unit waiting 600 or more consecutive steps in front of a full hex (Sprint 34's candidate: 0 waits
in 24 games; its `baseline-v2` opponents up to 1,798). The A2 gate also closes when `Dbar` is at or below -0.5; Stage B
then does not run.

**Comparison.** `z = (margin - reference mean) / reference SD`. For each of the ten Stage A configurations (scenario and
seat), `d = mean z of the candidate's two games - mean z of the control's two games`; `Dbar` is the mean of the ten `d`,
`d_s` the mean of a scenario's two `d`. A descriptive percentile bootstrap interval of `Dbar` over the ten configurations
is reported.

**Dispositions** (first match): `S35_LIVE_INVALID`; `S35_INTEGRATED_REJECT` (severe harm; `Dbar` at or below -0.5; a Stage
B objective score below the reference minimum in three or more games; a Stage B remaining-force score below the
reference minimum in three or more games); `S35_INTEGRATED_PROMISING` (both stages complete, `Dbar` at least +0.5, `d_s`
positive in at least four of the five scenarios, no `d_s` at or below -1.0, the candidate's own mean `z` over its 20
Stage A games at least +0.5, no Stage B objective score below the reference minimum, a Stage B margin at least the
reference minimum minus 50 in at least seven of eight games); otherwise `S35_INTEGRATED_INCONCLUSIVE`. Before any session
the disposition is `S35_LIVE_NOT_AUTHORIZED`, or `S35_ENGINEERING_BLOCKED` if no candidate could be frozen. Two games per
configuration are exploratory: `PROMISING` means a larger confirmation is justified, never that the candidate is better,
and nothing is promoted, merged or uploaded.

**Measured per game** (descriptive): scores and margin, objectives first owned (and before the opponent), held value,
losses and recaptures, force lost by class, waits, refusals by type and code, judged attacks and friendly damage, module
and stance activity, decisions differing from a shadow `baseline-v2`, reconstruction checks, fallbacks, latency, memory
size.

## 12. Revision 2: registered result and the frozen candidate

The registered comparison (sections 8 and 10) ran once from `834a10a9f301f169739a47d83f967519bd6d8aa1` on the evaluation
server; outputs `evaluation/s35-coalition-agent/{model,genuine,precursors,selection}.json`. 580 model games, none crashed;
48 genuine games, 203,678 decisions re-decided per agent; the 57 loss episodes, with the control reproducing its recorded
actions at all 41,776 decisions.

| Measure | CA | CM | `S34-MO` |
|---|---|---|---|
| M-inert: objective value (80 games; all objectives 22,480) | 21,130 | 21,130 | 22,480 |
| M-v2: objective value of the agent's side (80 games) | 19,650 | 19,730 | 18,300 |
| model: longest wait in front of a full hex (steps) | 35 | 38 | 19 |
| model: replay checks identical | 1,930 of 1,930 | 1,930 of 1,930 | 1,930 of 1,930 |
| genuine: rejected or independently illegal actions / fallbacks / contract errors | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| genuine: play decisions differing from `S34-MO` | 69,912 of 203,600 | 70,071 of 203,600 | 0 |
| genuine: latency p99 / maximum (ms) | 27.672 / 241.791 | 27.022 / 233.981 | 25.726 / 237.182 |
| genuine: guided shots | 0 | 4,470 | 0 |
| P: threat recognised 150 steps before the loss | 33 of 57 | 33 of 57 | (no stances) |
| P: last defenders ordered away by Sprint 34 kept | 18 of 18 | 18 of 18 | 0 of 18 |

Both candidates passed all eleven gates; CM's model objective value is within 2% of CA's in both populations, so the
registered rule selects **CM**. Frozen as `coalition.config.LIVE` (the only change to the compared code is the line that
names it): identity `s35-coalition-coalition-mission-planner-2`, policy source
`ea38c04216385a8aa119d624c9e437c118268a3a8caec682cf98f1834df8400c` (46 files: `baseline-v2`'s frozen sources, the frozen
Sprint 34 package `integrated/` and `coalition/`).

Ablations in the five live scenarios against `baseline-v2` in the model (10 games each; objective value of the agent's
side): CM 2,220 and CA 2,220 against `S34-MO`'s 1,930; without coalition capture 1,880, without retention 1,960, without
the reserve 1,990; without reinforcement, withdrawal, fire support, arrival fire, guided fire, safe transport or transport
2,220. These are movement-race figures of a model without combat: they say which modules change where units go, not
what they are worth in a fight.

Limits stated before any engine result:

* against the inert control the candidates held 21,130 of 22,480 model objective points: in 20 of the 80 scenario-sides an
  objective was not taken because motionless inert units near it count as a threat, and no coalition reached the capture
  ratio (`S34-MO` takes them all, because nothing contests them). None of the 20 is in the five live scenarios, where CM
  held every objective against the inert control in both seats. Against a passive opponent with units near objectives
  the candidate can therefore leave points that an aggressive agent takes; this is a real cost of the threat model;
* the precursor population shows the decision-level intent only: on Sprint 34's recorded trajectories the candidate
  recognised the threat in 33 of 57 episodes and would not have ordered away any of the 18 last defenders, but whether
  that holds the objective is a combat question the replay cannot answer;
* in 20 of the 57 episodes the candidate's stance 150 steps before the loss was delay: it would have kept a holder and
  withdrawn the valuable units, trading the objective's points for the remaining-force score; the live games decide
  whether that trade is worth it.

## 13. Readiness: verification of the candidate and the live machinery

| Check | Result |
|---|---|
| Sprint 35 tests | `tests/test_s35_coalition.py`, `test_s35_offline.py`, `test_s35_live.py`, `test_s35_card.py`, `test_s35_gaps.py`: 70 tests |
| Mutation (`scripts/mutate_s35.py`, `evaluation/s35-coalition-agent/mutation.json`) | 50 of 50 planted defects killed; the first run killed 33 of 50: 15 test gaps closed by `tests/test_s35_gaps.py`, 2 equivalent mutants (a power floor no class weight reaches; places for a skip, which has none) replaced |
| Stand-in rehearsal with the real references (positions 1 to 20, model world behind the engine interface, committed tree) | positions 1 to 19 exit 0; the A1 gate closed on severe harm at position 20 (short model games score far below real ones), exit 5; a replayed position refused; 0 reconstruction mismatches for both policies |
| Stand-in rehearsal with permissive references (a temporary clone; all 48 positions) | gates A1, A2 and B1 open, B2 closed at the end of the schedule, exit 5; a replayed position refused; 0 reconstruction mismatches |
| Card `evaluation/s35-coalition-live-1/manifest.json` | canonical SHA-256 `0b90ae2649f2d6416175495d0b885c04d26611b4842a6356f3d986b0e313d145`, rebuilds byte-identically; rules `b742afa9abb09e3aa2e4c28fa0a9a152026821bdc5e612059bc67645dcebfc45` |
| Pinned policies | `baseline-v2` `7cbaf032...`, Sprint 34 control `b107d23e...` (refused if it differs), candidate `ea38c042...` |
| Platform canary | rebuilt from this branch: `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, smoke 62 steps; independent verifier 8 of 8 planted defects caught |
| Engine | no session opened; ledger 2826 sessions, all closed, SHA-256 `2359e9cf...` unchanged |

The full workstation suite, the clean-clone suite, the server's focused suite, the privacy scan of the published scope and
the document check are run on the final commit; their figures are in the close-out note of the hand-over.

## 14. Collaborator competitiveness benchmark (design only; not part of the 48 sessions)

The owner wants the agent to compete credibly with the SDK demonstration agent and the collaborator's own agent. No such
game is proposed now: the 48 proposed sessions are allocated to Stages A and B, and none of the prerequisites below holds
yet.

Prerequisites, each to be met before a benchmark card is drafted:

1. **The executed package.** The collaborator supplies the exact package that played (a ZIP with its SHA-256 and the
   date), not the earlier archive; it is archived under `local/references/teammate/` like the others and never committed.
2. **The entry point.** The runner that played it, or a statement of which method the runner calls (`step` or `step2`),
   confirmed by a fingerprint in a fresh game (the graphic markers of `step2`, the chat message of `step`).
3. **Equal information.** In the SDK offline runner `setup_info["state"]` carries the all-seeing state; the benchmark
   harness passes each agent only its own seat's state (the platform's behaviour must be checked, not assumed), so that
   neither agent starts with the other side's strengths and passengers.
4. **Isolation.** The third-party package runs from a private directory outside the repository, in its own process,
   through a thin adapter that converts nothing but the action list; its randomness is seeded and recorded per game.
5. **Design.** Each policy in each seat of the same scenarios, interleaved like Stage A; the collaborator's agent is
   stochastic (two replays of the same seat split at step 1), so a game is one draw and several per configuration are
   needed; outcomes attributed per game to the exact package digests.
6. **Authorization.** A separate card and its own session budget, approved by the owner before the first game.

Until then the only head-to-head evidence is the two owner-designated replays (section 2.3), one game per seat in one
scenario against the owner's agent, not against this sprint's candidate.

## 15. Status and the one question

Disposition now: **`S35_LIVE_NOT_AUTHORIZED`**. Sessions opened in Sprint 35: none (the ledger still holds 2826). The
candidate, the control, the schedule, the gates and the dispositions are frozen in the committed card; no rule may change
after a session opens. Nothing was promoted, merged into `main` or uploaded, and `platform-compat2` is untouched.

The one question for the owner: **Authorize up to 48 Sprint 35 engine sessions, 2827–2874, under the frozen gates?**
