# Sprint 29: platform first, then a faster tactical loop

Dates are business dates in UTC+8 (2026-10-09 to 2026-10-10). **No engine session was opened in this sprint**: the
ledger stays at 2,797 sessions, none unclosed, and session 2798 is unopened. `baseline-v2` and the frozen platform
package are unchanged, no policy was promoted, and no tactical candidate was implemented or played.

## 1. Starting state and the owner's decisions

* Start: `main` at `78a1c4276332c59dba642061808da6ac66274504` on the workstation, GitHub and the evaluation server,
  clean; engine ledger 2,797 sessions, none unclosed; privacy baseline 106 accepted hit lines; canary SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`.
* Sprint 28 is accepted as recorded: disposition `T12_O1_INADEQUATE_OPPORTUNITY` (head-to-head trigger episodes blue 5
  and 3, red 0 and 0, all in end states after every objective was owned). T12-O1 is closed and not patched; every
  earlier result and source digest is preserved.
* Priority change (owner, opening Sprint 29): get the frozen `baseline-v2` canary ready for an immediate manual test in
  an AI-code test slot, and replace long chains of narrow offline gates with a short, decisive live workflow. The
  next-ranked T7-E3b diagnostic is not run automatically. Engine safety, ledger, authorisation and privacy controls are
  unchanged.

## 2. Platform canary: verified identity

| Field | Value |
|---|---|
| File | `dist/miaosuan-baseline-v2-canary.zip` at the repository root (git-ignored; built by `python scripts/build_platform_package.py`) |
| Size | 107,646 bytes, 26 files (22 vendored modules, 4 generated: `ai/__init__.py`, `ai/agent.py`, `ai/base_agent.py`, `ai/PACKAGE.json`) |
| SHA-256 | `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511` |
| Policy | `baseline-v2`, policy source `7cbaf0321131784839a25734eb37fcefb126e675cefecbb8be0a8dc531b3e3ae` |
| Vendored policy modules | the `baseline-v2` lineage only: the core (`agent`, `boundary`, `decision`) and `experiments/occupy_reservation.py` (v1), `routing_bounded.py` (runtime r1), `shoot_reservation.py` (v2); no exploratory or shelved module |
| Imports | standard library only: `abc`, `dataclasses`, `enum`, `hashlib`, `heapq`, `json`, `math`, `re`, `sys`, `types`, `typing` |

Checks (results in the private `local/diagnostics/s29/logs/`):

| Check | Workstation (CPython 3.12.10) | Evaluation server (CPython 3.10.20, the platform's Python) |
|---|---|---|
| Rebuild into a scratch folder, then byte comparison with the frozen zip | identical (SHA above, manifest identical) | identical, and identical to the server's own `dist/` copy |
| Builder's checks: policy source digest, import closure, forbidden content, layout, size | pass | pass |
| Isolated-interpreter smoke (`-I`, no repository on the path): `from ai import Agent`, synthetic game, actions equal the repository agent's | 62 steps, 0 mismatches | 62 steps, 0 mismatches |
| Replay corpus: every recorded observation of the 8 pinned games, packaged against repository agent | not run (the corpus is private to the server) | 8 games, 33,696 steps, 0 mismatches |
| Independent verifier (`local/diagnostics/s29/verify_canary.py`, does not reuse the builder): SHA, single top-level `ai/`, stored entries with fixed timestamps, no links, every vendored file byte-equal to `HEAD`, manifest hashes, lineage-only experiments, `Agent` with `setup`, `step`, `reset`, Python 3.10 syntax, standard-library imports | pass | pass (3.10 standard-library list) |
| The same verifier on 8 planted defects (byte change, second top-level folder, extra experiment, third-party import, Python 3.11 syntax, manifest identity, missing `reset`, compressed entry) | 8 of 8 refused | 8 of 8 refused |

The server run used one serial process pinned to NUMA node 0 (logical CPUs 0-15 and 32-47) in shared mode: at the
pre-launch check the only busy foreign job was pinned to node 1 (`docs/SERVER_RESOURCE_POLICY.md`).

**Status: PLATFORM CANARY READY FOR OWNER UPLOAD.** No platform test has taken place.

### 2.1 Outstanding compatibility uncertainties

None of these can be settled locally; each has a recognisable signature on the platform (section 3.3).

| Id | Uncertainty | What the package does | Signature on the platform |
|---|---|---|---|
| U1 | The platform's engine and SDK version (the live pages describe SDK 5.0.0 or later; everything here ran on 4.1.0) | an observation that violates the project's contract yields no actions for that step (fail-closed) and one stderr line per distinct message, prefixed `[baseline-v2] contract error:` | the agent deploys but issues nothing, or stops acting mid-game; that stderr line in the log |
| U2 | Whether `setup_info` carries `cost_data` (the SDK's own demo agent reads it, together with `seat`, `faction`, `scenario`, `basic_data` and `see_data`) | without `cost_data` the router is absent and no unit is ever ordered to move; shooting and occupation still work; **nothing is printed** | units fire but never move from their start hexes |
| U3 | Whether `setup_info` carries integer `seat` and `faction` | missing or non-integer values raise inside `setup`, which the package does not catch | a start-up error naming `seat` or `faction` |
| U4 | Timing: the online engine advances on its own clock (at 5x, one frame per 200 ms) and does not wait | locally the median decision is under 1 ms; the first play decision of the largest scenario took up to about 0.5 s on the original router and under 0.2 s on runtime r1; the decisions above 1 s were full garbage collections in a process shared with the engine (`docs/LATENCY_DIAGNOSTIC.md`). Online the engine runs in another process, so smaller pauses are expected; this is an inference | invalid or stale actions reported early in play or late in long games |
| U5 | Per-step time budget, memory limit, CPU speed and upload size limit (none published) | 107,646 bytes, standard library only | a slot rejection or a resource error |
| U6 | Exception inside a step | caught, reported once per message (`[baseline-v2] step error:`), answered with no action; the agent keeps playing | that stderr line |
| U7 | Competition scenario BOKE-2026 is not in the local data (`docs/TACTICAL_FRONTIER.md`) | unknown map; no tuning | none expected; record the scenario name |

## 3. Owner handoff: manual upload and the minimum useful test

### 3.1 Upload

1. Check the digest: PowerShell `Get-FileHash dist\miaosuan-baseline-v2-canary.zip`, Linux
   `sha256sum dist/miaosuan-baseline-v2-canary.zip`. It must equal the SHA-256 above.
2. Sign in on the platform: user centre, AI test. Upload the zip, unchanged, to one of the three **AI-code test
   slots** ("AI代码"). Not the official slot ("正式"): it is entered automatically into any competition the account
   has registered for, so a compatibility failure there would cost a real result.

### 3.2 Minimum useful test

1. **Machine against machine, large scenario** (more than 40 units per side), one game; if the slot lets you choose
   the side, a second game on the other side. This is the test that matters: per-step work and the timing risk (U4)
   grow with the force, and the largest local losses are seat-dependent.
2. **Machine against machine, small scenario**, one game: separates a general start-up problem from a size problem.
3. Optional: **human against machine** for a few minutes, to watch whether the agent ends deployment, moves, fires
   and occupies.

### 3.3 What to download and what it tells apart

Download the log and the replay of every game ("日志及复盘下载") and keep them under `local/` (never committed); add a
screenshot of any error. Then classify:

| Observation | Class |
|---|---|
| upload or import rejected; start-up error; `setup_info` named in an error | compatibility (U3, U5) |
| deployment never ends, or no unit action in the whole game | compatibility (U1) |
| units fire and occupy but never leave their start hexes | compatibility (U2) |
| `[baseline-v2] contract error:` or `step error:` lines | compatibility (U1, U6) |
| invalid or stale actions, timeouts | compatibility (U4) |
| the game runs to the end with deployment, movement, fire and occupation, and is lost | tactical: fill in the intake record below |

One platform win confirms nothing, and one loss refutes nothing; platform results stay apart from local evidence.

## 4. Platform feedback intake format

One record per platform game, written after the owner supplies the files. Public fields carry classifications and
counts only; logs, replays, unit identifiers, coordinates and opponent names stay under `local/`.

```text
date (UTC+8):               2026-..-..
slot:                       AI-code test slot (1, 2 or 3)
package SHA-256:            a3d3b022... (must match section 2)
compatibility:              OK | U1 | U2 | U3 | U4 | U5 | U6 | other (describe)
invalid or stale actions:   count, or "not shown"
timeouts / errors:          count, first step seen
scenario:                   name or id; large (>40 units per side) or small
candidate side:             red | blue
opponent:                   platform machine AI (name if shown) | human | another uploaded AI
outcome:                    win | loss | draw | unfinished; final score and its parts (occupy, attack, remain) if shown
first-ownership sequence:   objective value and step of first ownership, both sides, in order
objectives lost:            objective value, step lost, whether own units had just left it
objectives recaptured:      objective value, step
surviving combat power:     own and enemy units (or value) left at the end
missed firing:              situations where an own unit with an enemy in view did not fire (with replay step)
movement failures:          units stuck, blocked or never arriving (with replay step)
other events:               artillery idle, infantry on foot far from objectives, close combat, anything unusual
failure-ledger category:    deployment | reconnaissance | movement | fire allocation | indirect fire | transport |
                            objective timing | survival | special equipment | unknown
```

Each meaningful loss becomes one row of the failure ledger in `docs/TACTICAL_FRONTIER.md`. Platform observations then
re-rank the portfolio of section 7: a weakness seen on the platform outranks one seen only locally, and a
compatibility class blocks tactical work until fixed.

## 5. What `baseline-v2` actually loses

### 5.1 Representative high-loss configurations

Final-score composition of `baseline-v2` in the C1 mirror (`baseline-v2` against itself, 15 games per configuration,
the registered shoot-reservation experiment's group C; means from the game records, aggregated by
`local/diagnostics/s29/c1_split.py`):

| Scenario, seat | Total | Occupy (min-max) | Attack | Remain (share of maximum) |
|---|---:|---:|---:|---:|
| 2130511121 red | 366.5 | 20 (0-50) | 302.9 | 43.7 (0.078) |
| 2130511121 blue | 1,236.5 | 420 (390-440) | 516.3 | 300.1 (0.498) |
| 2120531121 red | 403.0 | 112.7 (0-310) | 239.2 | 51.1 (0.153) |
| 2120531121 blue | 648.0 | 197.3 (0-310) | 282.9 | 167.8 (0.412) |
| 1930331196 red | 609.8 | 195.3 (0-310) | 315.6 | 98.9 (0.306) |
| 1930331196 blue | 430.2 | 114.7 (0-310) | 224.1 | 91.4 (0.225) |

The mirror margin in 2130511121 is -870 for red with a standard deviation of 115 (the smallest among the large
scenarios: 587 in 2120531121, 453 in 1930331196). Against the inert control every large configuration has a constant
occupy score (440, 310 and 310) and a margin standard deviation of at most 50.1 (2120531121 with `baseline-v2` red).

In the four head-to-head timelines of Sprint 12 (2130511121, `baseline-v2` against the T9-v3 candidate), Sprint 25's
public loss rows show the red `baseline-v2` seats losing held objectives 6 and 11 times, objectives worth 230 and 360
points that they had owned, while the opponent ended with 390 of the 440 objective points in both games, so red held
at most 50 at the end.

### 5.2 Diagnosed weaknesses

Evidence classes: **E** documented engine behaviour or the agent's own code; **R** a registered experimental result;
**D** historical descriptive figure (H0 = replay corpus, HH = the four head-to-head timelines); **H** hypothesis.

| Id | Weakness | Evidence |
|---|---|---|
| W1 | **No garrison.** A unit standing on an objective its side holds is a movement candidate like any other: `baseline-v2` sends every idle unit toward the cheapest objective its side does not hold ([candidates.py](../src/miaosuan_agent/decision/candidates.py), `move_candidates`); it waits only on an unheld objective. Held objectives are lost after the side's own units leave | E (code); R: 59 of 66 held-objective losses (HH 20 of 26) followed departures under the side's own MOVEs, 4 followed a destruction in the zone; D: in 27 of 28 multi-defender exits every last defender was ordered at one decision; a qualifying threat was visible at that decision in 45 of 59 (`docs/SPRINT25_T13_D1.md`) |
| W2 | **Moving ground units absorb the damage.** Units that cannot fire on the move are hit in columns and in close combat | E: direct fire needs a stopped shooter except tank guns; after an arrival non-tank units list a shot only after 75 steps (`docs/T7_DESIGN.md`); D: HH 117 of 158 damage events on moving ground units (attacker seen before in 117), 55 of 89 lost units had a move path, 45 of 55 close-combat events hit moving units, 101 of 200 threat-exposed move orders followed by damage to the mover within 300 steps (`docs/SPRINT18_FRONTIER_RESET.md`) |
| W3 | **Infantry contributes little.** Foot routes are slow, transport is never used | E: infantry 1 hex per 144 steps against 20 for vehicles on the diagnosed route; R: embark, carry and disembark work, 75-step transitions (`docs/SPRINT22_T2_TRANSPORT_PROBE.md`); D: HH 8 of 32 infantry move orders cannot arrive before the end, 10 of 28 infantry never stand on an objective |
| W4 | **Units stuck en route.** Columns exceed the four-units-per-hex stacking limit and block each other for the rest of the game | E and R: `docs/T1R_DIAGNOSIS.md`, `docs/PS1_ENGINE_PROBE.md` (a stop on a waiting unit is deferred indefinitely); D: units with a route and zero speed were blocked by a full next hex in 1,688 of 1,703 H0 and 11,413 of 11,425 HH unit-decisions (`docs/SPRINT28_T12_O1.md`) |
| W5 | **Idle assets.** Artillery sits idle; after all objectives are held nothing moves | D: 102,024 H0 idle artillery unit-decisions with an enemy in view; R: T4 versions either hit own units or gained nothing (shelved); T12-O1 found idle stacks only in end states |
| W6 | **Fire choice.** A lower-blood target was listed in 97 of 319 HH shots | D; whether another target would have been destroyed is not identifiable from the public rules (R: `docs/SPRINT21_DIRECT_FIRE_SEMANTICS.md`); no kill probability is claimed |

Interventions already known to damage performance (R): long withholding of many units (T9-v1 missed one objective as
blue against the inert control in 2120531121), artillery fire near objectives (T4 v2 hit own units entering exploding
hexes), and splits that overfill a hex (T1, a deterministic 78 against 158 loss in 1910631192). Each defines a harm check below.

## 6. Leverage at decision level

| | W1 no garrison | W2 moving units hit | W3 infantry idle |
|---|---|---|---|
| Earliest decision that creates the risk | the decision at which `baseline-v2` orders the last stationary unit(s) off a held objective hex (a median 162 steps before the loss for the 31 single-defender departures) | the MOVE order of a ground unit while an enemy that can fire on it is in view, and every later step it spends moving inside that enemy's range | the first MOVE order of an infantry squad onto a foot route longer than the steps left |
| Unit and action class | any ground unit, MOVE (type 1) | non-tank ground units, MOVE; the forgone alternative is stop (type 10) | infantry, MOVE; the forgone alternative is embark (type 3) |
| What `baseline-v2` knows then | the objective's flag, every own unit on the hex and its move path, the visible enemies | the visible enemy, its distance, the unit's own move path and speed | the route length and the steps left; the co-located carriers |
| Legal alternatives | issuing nothing for one unit (always legal) | stop, listed only while a move path exists; its effect on a unit that is still traversing is untested | embark when listed (937 HH decisions), then disembark |
| Effect on other units | removes one unit from the next objective's claimants | none directly; slows the column behind | ties a carrier to the infantry for about 150 steps |
| Scenario-specific? | no: losses on 7 of 16 H0 scenario-sides and all four HH side-games | no: damage on moving units in every acting-opponent population | infantry in 47 of 50 scenarios |
| Recurs? | yes, repeatedly within one game (red lost the same objective up to three times in one HH game) | yes | yes |
| Live A/B | keep-one holder against `baseline-v2` (section 7, H1) | stop-to-engage after a mechanism check (H2) | carry-to-garrison on top of H1 (H3) |

W4 has no engine operation that releases a formed deadlock (stop deferred, moving units cannot be re-ordered); W5's
artillery line (T4) and W6's line (T11) are closed or shelved and are not reopened here.

## 7. Tactical portfolio (at most three; none implemented)

### H1. Keep-one holder (T13-K1) - recommended

* **Weakness**: W1. **Trigger** (every play decision, after `baseline-v2` has decided): an objective whose `cities`
  flag is the side's colour would keep no own ground unit (type 1 or 2) on its hex, because every such unit there either
  has a move path or receives a `baseline-v2` MOVE, and at least one of them receives that MOVE.
* **Action**: withhold exactly one of those MOVEs: the mover with the longest free-flow travel time to its MOVE's
  destination (hex time `720 / basic_speed * cost` along the path, as `t9_batch.path_times`; ties by lower unit id),
  which prefers slow units such as infantry. Nothing else changes. The rule is stateless: it re-applies each decision,
  so the holder is released as soon as another own ground unit stays on the hex, the objective is lost, or the holder
  is gone. Units already moving cannot be stopped and are not touched. It differs from the closed T13-D1 rule in every
  respect that mattered there: it acts on the hex rather than the zone, on collective departures rather than a single
  occupant, and without a threat condition or a 300-step limit.
* **Why it could help**: occupy is scored on the objectives held at the end, and no objective was ever lost with an own
  unit on its hex (0 of 66). Red in 2130511121 owns objectives worth 230 and 360 points during the head-to-head games
  and ends with at most 50; its mirror occupy averages 20 against blue's 420.
* **Largest interaction risk**: the held unit may be the one that would first own the next objective (the T9 failure
  mode), and a lone holder may be destroyed without saving the objective, adding a unit loss to the objective loss. A
  holder also takes one of the four places on the objective hex.
* **Effect on timing and survival**: first ownership of the next objectives may come later (descriptively, the departing last
  defender became the first owner of its next objective in 3 of 31 single-defender departures); fewer units move under
  fire; holders are exposed while stationary.
* **Development cost**: one add-on on `experiments/exploratory_addon.py` (about 150 to 200 lines), unit tests with
  the fake engine, one run card, a mutation check: about one working day, no new infrastructure.
* **Minimum useful sessions**: 8 for the harm screen, 12 for the benefit screen (section 8).
* **Decisive rejection**: harm screen: in any inert configuration, occupy below `baseline-v2`'s constant value, or a
  margin more than 50 below the historical minimum; benefit screen: red's mean margin less than 55 above the historical
  -870 (one standard error of the comparison), or blue's mean margin more than 115 below the historical +870, or no
  trigger as red.

### H2. Stop to engage (T7-B1)

* **Weakness**: W2. **Trigger**: an own ground unit without move-and-fire capability is moving (`move_path` non-empty,
  `speed` above 0), stop is listed, and a visible enemy ground unit is within the published range of one of its
  weapons (Sprint 5's B1 definition, `docs/T7_DESIGN.md`).
* **Action**: stop (type 10); after the transition `baseline-v2` engages, or re-issues the move.
* **Why**: converts moving targets into firing units; attack is the largest score component in all six mirror rows of
  section 5.1.
* **Largest interaction risk**: the engine's response to a stop on a traversing unit is unknown; on a waiting unit it
  was deferred indefinitely (Sprint 4), so units may freeze. Sprint 5 did not select B1 for exactly this safety reason.
* **Timing and survival**: each stop costs at least 75 steps of travel; first ownerships come later.
* **Cost**: about one day for the add-on (weapon ranges exist in `evaluation/t7_candidates.py`), plus the mechanism
  check. **Sessions**: 2 deterministic sessions against the inert control (2130511121, both seats), then 12 as H1.
* **Decisive rejection**: any stopped unit that does not clear its move path within two hex times, or lists no shot
  within 150 steps of a completed stop; then the same benefit thresholds as H1.

### H3. Carry to garrison (T2-G1), only after H1 advances

* **Weakness**: W3. **Trigger**: an infantry squad whose foot route cannot end before the game does, co-located with
  an idle own carrier with room, embark listed. **Action**: embark; the carrier takes it to the nearest objective its
  side holds; disembark there; the infantry becomes H1's holder (H1 already prefers it) and the carrier is released.
* **Why**: puts the force's slowest units where H1 needs a holder, freeing faster units for capture.
* **Largest interaction risk**: the carrier is held about 150 steps for the two transitions, the interaction that
  shelved T2-X1 (25 of 30 held carriers were ones `baseline-v2` sends on); here the hold coincides with H1's.
* **Cost**: two to three days (a state machine; T2-P1's candidate code is reusable). **Sessions**: 2 mechanism, then 12.
* **Decisive rejection**: fewer than half the triggered squads delivered, or no occupy gain over H1 alone.
* Needs the owner's approval as a new T2 increment (T2-X1 stays shelved).

Considered and not proposed: a live test of kill-first targeting (reach small: Sprint 20 counted 15 to 33 changed shots
per HH side-game, mostly toward targets of blood 1 at lower attack levels; it would reopen the closed T11 line); T9
redistribution (the largest registered effect, +305.47 in 2130511121, but shelved by the owner); T4 artillery
(shelved); a deadlock remedy (no engine operation releases it).

## 8. Recommendation and the smallest valid experiment

**Recommended for the owner's approval: H1, keep-one holder (T13-K1).** It addresses the largest controllable score
gap with an action that is always legal, needs no unknown engine semantics, and is cheap to build.

Smallest valid experiment, EXPLORATORY track (`docs/EXPLORATORY_TRACK.md`), one candidate identity, two stages, one
run card per stage committed and pushed before its first game:

| Stage | Games | Sessions | Opponent | Reads | Proceeds when |
|---|---|---:|---|---|---|
| A, harm | 2130511121, 2120531121, 1930331196, 1910631192; both seats | 8 | inert control | occupy, margin, triggers, holders | no rejection in section 7, H1 |
| B, benefit | 2130511121, candidate red 6 and blue 6 | 12 | `baseline-v2` | margin against the 15 historical mirror games per seat, occupy, held-objective losses, first-ownership steps, units lost | ADVANCE: red at least +115 above -870 and blue within 115 of +870; REJECT as in section 7; otherwise INCONCLUSIVE |

**Projected budget: 20 sessions (2798 to 2817), cap 20**, decision after stage A (8) and again after stage B. If
stage B advances, a generalisation stage (2120531121 and 1930331196, 6 games per seat, 24 sessions) and then a
registered confirmatory study are proposed separately. Nothing is promoted from exploration. With 6 games per seat
the comparison's standard error is about 55 points (control standard deviation 115, 15 control games), so a gain of
one standard deviation is about two standard errors.

No engine session is authorised by this document.

## 9. Research velocity

Sprints 18 to 28 (eleven sprints) opened two engine sessions, both mechanism probes, and measured no candidate's
effect on game outcomes. Sprint 8, the one exploratory sprint, used 23 sessions and found the T9 lead that Sprint 9's
registered study then supported (+305.47 in 2130511121). The workflow from here:

| Layer | Use | Needs before the first game | Concludes |
|---|---|---|---|
| Exploratory screen | find a candidate worth confirming | a run card (candidate digest, games, cap, the rejection and advance numbers); the owner approves the session budget once per candidate | ADVANCE, REJECT or INCONCLUSIVE, directional only |
| Registered mechanism finding | only when an engine semantic is unknown and decides safety (H2's stop) | the probe rule frozen and pushed; 1 or 2 deterministic sessions | the mechanism fact |
| Confirmatory study | a performance claim or a promotion | the full registration of earlier sprints, fresh games | confirmed or not |
| Platform observation | compatibility and real opponents | the intake record (section 4) | a ranked weakness; never a confirmation |

* **Testbeds chosen by noise**: inert configurations (constant occupy, margin SD at most 50.1) for harm; 2130511121
  head-to-head (SD 115) for benefit; the noisy large scenarios only after an advance.
* **Rules, not rubrics**: no new family-scoring rubric; a candidate is chosen by the weakness it targets and the cost
  of the decisive test.
* **Offline work only where it is cheaper than a session**, for example a coverage count that can stop a candidate
  before a card is written. Exploratory documents get one script that re-derives every printed number, not a
  clause-by-clause gate.
* **Pipelining**: the next candidate is built while the previous screen runs.
* **Unchanged**: persistent installation and ledger, sprint session caps, clean committed tree, card rebuild check,
  privacy scan before every push, no promotion without a confirmatory study, server CPU policy.

## 10. Tests and checks

* Canary: section 2 (workstation and server builds, smokes, replay corpus, independent verifier with 8 of 8 planted
  defects refused).
* Ledger (read-only `scripts/engine_install.py verify` on the server): 2,797 sessions, none unclosed, integrity ok,
  last event the close of session 2797; ledger file SHA-256 `70ae38f2...` as at the close of Sprints 27 and 28.
* This sprint changed documentation only (this file, `docs/PLATFORM_CANARY.md`, `docs/TACTICAL_FRONTIER.md`,
  `README.md`); the multi-hour server suite was not rerun. Test results, the privacy scan and the final commit are in
  section 12.

## 11. Not claimed

No platform test has taken place. No tactical candidate was implemented, played or scored. The weaknesses are
descriptions of recorded games and of the agent's code; H1 to H3 are hypotheses whose benefit is unknown. No kill or
victory probability is used anywhere.

## 12. Close-out

Recorded in the close-out commit that follows this file.

## 13. Recommended next task (one)

On the owner's approval of H1: build the keep-one holder (T13-K1) as an exploratory add-on with its tests and its
stage A run card, and submit the 20-session budget for approval; no session is played before that approval. The
owner's canary upload (section 3) does not wait for it.
