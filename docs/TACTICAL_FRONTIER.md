# Tactical frontier

The project moves from infrastructure to tactics. Its primary objective is now a competitive, generalisable
land-wargame agent, a fast loop of tactical hypotheses tested locally, and a feedback loop with real platform play.
Engineering correctness stays mandatory and serves that objective; it no longer delays it.

Method, as in the project's other research: hypothesise boldly, preregister before confirmatory measurement, keep
exploration and confirmation apart, keep negative results, freeze experiment identities, never tune on confirmatory
results, and promote only evidence-backed improvements. A tactic is not turned into a multi-day infrastructure study
when a light mechanism check suffices.

## Phase transition (2026-10-02, UTC+8)

* The ownership prevalence diagnostic (`docs/OWNERSHIP_PREVALENCE_DIAGNOSTIC.md`) stays as recorded: blocked by its
  own failed instrumentation check, prevalence withheld, its captures unexamined. It is not rerun now.
* The target-ownership line is **backlogged**, not deleted (`docs/TARGET_OWNERSHIP_DESIGN.md`).
* No historical result, record or registration is changed by this transition.

## Architecture

| Layer | Contents | Rule |
|---|---|---|
| Stable core | observation boundary and contract, legality gate, runtime identities, scheduler, ledger, reproducibility tooling, platform packaging | changes only to fix correctness, reproducibility or platform compatibility, or when a selected tactic is blocked by it |
| General doctrine | capability-driven tactics: what an operator can do, read from its observed fields and legal actions; terrain, objectives, enemy information | no scenario id, map id, unit id or fixed coordinate anywhere; unit-specific doctrine is encouraged ("general first does not mean unit-agnostic") |
| Competition profiles | optional scenario- or map-specific tactics (terrain, chokepoints, timing, force composition) | later stage; behind an explicit profile flag; never silently merged into the general doctrine |

## Research states

Every hypothesis is in exactly one state: `IDEA`, `MECHANISM-VALIDATED`, `EXPLORATORY`, `PREREGISTERED`, `CONFIRMED`,
`REJECTED`, `BLOCKED`. Exploratory findings are never reported as confirmed improvements; only `CONFIRMED` can lead to
a baseline promotion, through its own registered experiment.

The loop: local hypothesis, mechanism smoke, exploratory A/B; then platform AI test (package, upload, run, replay,
inspect compatibility and tactics); then confirmation (a fresh local A/B and external platform evidence); then
competition. Platform results are kept apart as environment-compatibility evidence, tactical result and
opponent-specific result; one human win confirms nothing, but real losses feed new hypotheses.

## Tactical capability census

From `evaluation/tactical-frontier-1/census.json` (`scripts/tactical_census.py`): the 50 historical scenarios of the
SDK 4.1.0 archive and the 8 frozen scenarios (operator archetypes by (type, sub_type) code), and every decision of the
pinned replay corpus (8 games of the frozen scenarios under C1, both seats: 16 deployment and 33,680 play decisions)
for what `valid_actions` lists on engine 4.1.0. Aggregates only.

| Family | Applicable capabilities | Generality | Opportunity | Risk | Leverage |
|---|---|---|---|---|---|
| T1 deployment disaggregation | every ground operator except artillery with 2 or more vehicles or squads: deployment split 314 (not listed in `valid_actions`, as documented), play split 14 | splittable operators in 50 of 50 scenarios; each starts with 3 or 4 | every frozen scenario side (16 of 16); split 14 listed in 1,693 play and 6 deployment decisions; 892 of 2,096 operators start stacked | 314 acceptance, control of the new operators and stacking limits unverified on 4.1.0 | per the live rules each half keeps the full ammunition and acts independently; stacked targets take adverse modifiers |
| T2 transport and infantry defence | infantry in 47 of 50 scenarios; vehicles with passenger capacity (infantry fighting vehicles 47 of 50) | high | embark listed in 77 and disembark in 256 play decisions | moderate: timing, suppression rules | infantry holds objectives and fires guided weapons; mobility via vehicles |
| T3 reconnaissance and enemy belief | every unit observes; UAV in 30, loitering munitions in 42, helicopters in 26 of 50 scenarios | high | an enemy is visible in 19,970 of 33,680 play decisions | low action risk; belief modelling effort | indirect: enables fire and movement decisions |
| T4 indirect artillery fire | artillery: 29 of 50 scenarios, 3 of 8 frozen | medium | indirect fire listed in 17,280 play decisions; artillery lists only change state, indirect fire and weapon lock, and baseline-v2 leaves it idle | target selection, dispersion, flight time, friendly fire unknown | high where artillery exists: an idle weapon system |
| T5 guided fire and correction | operators with guide ability; correction radar (sub_type 10, 5 of 50 scenarios) | low | guided fire listed once, correction radar in 2 play decisions | semantics barely observed | moderate where available |
| T6 threat-aware movement | every moving operator | high | move listed in 21,897 play decisions; an enemy visible in 59% of play decisions | changes the shared router | reduces losses en route; size unknown |
| T7 movement-state micro | change state (23,660 play decisions), stop (27,220), weapon lock (23,118) | high | most decisions of most operators | moderate: timing interactions | concealment and march trade survival against speed |
| T8 specialised assets | mines (sub_type 13, 7 of 50), fortifications (type 4, 2 to 4 of 50), altitude (helicopters), air defence | low | lay mine listed in 1 play decision; altitude in 6,957 | rare, scenario-dependent | local |
| T9 intent and task allocation | the whole force | high | every game | architectural change across all behaviour | potentially largest, hardest to isolate |

T1's open risks were then measured by its screen (`docs/SCREEN_DEPLOYMENT_SPLIT.md`): on engine 4.1.0 deployment
splits were accepted in 3 of the 8 frozen scenarios and refused with code 103 in the other 5; the new operators are
the seat's own and obey orders; the stacking limit voids a split silently.

## Selection rubric (committed before scoring)

`evaluation/tactical-frontier-1/rubric.json` fixes the criteria, their 0 to 5 anchors and the weights before any
family is scored: G generality 0.20, L leverage 0.25, O observability 0.15, I isolation 0.10, M measurability 0.10,
R risk (reversed) 0.10, P opportunity 0.10. The family with the highest weighted score is selected (ties by L, then
R); the sensitivity checks (equal weights, each weight plus or minus 0.05, each criterion left out, leverage 0.40)
are declared with it. The rubric prioritises research; it is not evidence that any tactic works.

## Scores and selection

`evaluation/tactical-frontier-1/scores.json` (each score with its reason) and `selection.json`
(`scripts/tactical_rubric.py`), scored after the rubric was public:

| Family | G | L | O | I | M | R | P | Weighted |
|---|---|---|---|---|---|---|---|---|
| T1 deployment disaggregation | 5 | 4 | 5 | 5 | 5 | 3 | 5 | **4.55** |
| T7 movement-state micro | 5 | 3 | 5 | 3 | 4 | 4 | 5 | 4.10 |
| T9 intent and task allocation | 5 | 5 | 4 | 1 | 2 | 3 | 5 | 3.95 |
| T2 transport and infantry defence | 4 | 3 | 5 | 3 | 3 | 4 | 3 | 3.60 |
| T4 indirect artillery fire | 3 | 4 | 4 | 5 | 4 | 3 | 2 | 3.60 |
| T6 threat-aware movement | 5 | 3 | 3 | 2 | 2 | 4 | 5 | 3.50 |
| T3 reconnaissance and belief | 4 | 3 | 3 | 2 | 2 | 4 | 4 | 3.20 |
| T8 specialised assets | 2 | 2 | 4 | 4 | 3 | 2 | 2 | 2.60 |
| T5 guided fire and correction | 1 | 3 | 4 | 4 | 3 | 2 | 1 | 2.55 |

**Selected: T1**, 0.45 ahead of T7. It stays first in all 23 declared weight variants (equal weights, each weight
plus or minus 0.05, each criterion left out, leverage 0.40); the runner-up is T7, or T9 when leverage, isolation,
measurability or observability is reweighted. Its two judgement scores are not decisive either: with L 3 and R 2,
T1 would score 4.20, still above T7. This is a research priority, not evidence that the tactic works.

## Hypothesis register

| Id | Hypothesis | State |
|---|---|---|
| TO-1 | target ownership by the highest attack level in isolated single-target collisions | `BLOCKED` (prevalence-1 stopped before interpretation); backlogged |
| T1 | deployment disaggregation: split eligible ground operators during deployment | `EXPLORATORY`: screen 1 disposition REVISE BEFORE CONFIRMATION ([issue #1](https://github.com/Rhymer-Lcy/miaosuan-land-wargame-agent/issues/1), `docs/SCREEN_DEPLOYMENT_SPLIT.md`) |
| T1-r | T1 revised: probe once and stop on code 103, skip splits the stacking limit voids, keep the play stage's objectives after splitting; disaggregation pays when the force is large | `IDEA`, next |
| T2 to T9 | the other families above | `IDEA` |

## Roadmap

1. **T1-r**: first diagnose the one deterministic loss of screen 1 (as blue against the inert control in 1910631192 the
   candidate scores 78 where `baseline-v2` scores 158) with two captured diagnostic games, then register the revised
   candidate for a fresh exploratory screen whose analysis keeps only games in which the engine accepted splits.
2. **T7 movement-state micro**, the rubric's runner-up: change state, stop and weapon lock appear in most decisions.
3. **T9 intent and task allocation**, the largest lever and the hardest to isolate; T4 (the idle artillery) follows
   by the rubric.

A tactic that earns ADVANCE gets a confirmatory design sized from its screen's noise; one that does not is recorded
with its disposition and left. Platform evidence runs alongside: the canary first, then each candidate that a local
screen supports.

## Process deviations

| Date (UTC+8) | Where | What happened | Consequence |
|---|---|---|---|
| 2026-10-02 | screen 1 smoke analysis | the first run read zero splits because the engine rewrites a deployment split's type from 314 to 14 in place before the capture serialises it; the records contradicted it | fixed, tested and pushed before the A/B; the analysis now refuses to run when capture and record disagree; the registered rule and the verdict on these data are unchanged (`docs/SCREEN_DEPLOYMENT_SPLIT.md`) |

## Platform canary and feedback loop

* `scripts/build_platform_package.py` builds `dist/<name>.zip`: one top-level `ai` package, the frozen policy's
  modules vendored byte for byte (standard library only), a generated `Agent`, a deterministic stored archive, a
  forbidden-content scan, and an isolated-interpreter smoke against the repository agent. The archive is never
  committed.
* Canary status: **READY FOR PLATFORM CANARY**. `miaosuan-baseline-v2-canary.zip`, 107,646 bytes, SHA-256
  `a3d3b0229118c0a389d379b315a620465624222f93fcf39de115e8e9dde59511`, byte-identical when built on the workstation and
  on the server; the packaged agent's actions equal the repository agent's on synthetic games and on all 33,696 steps
  of the 8-game replay corpus under CPython 3.10.20 with NumPy 1.26.2. The upload is a manual step on the platform;
  nothing is uploaded from this repository.
* For each meaningful platform loss, a failure ledger entry: deployment, reconnaissance, movement, fire allocation,
  indirect fire, transport, objective timing, survival, special equipment, or unknown. Repeated patterns become
  preregistered hypotheses; nothing is patched silently after a loss.

| Date | Platform game | Opponent | Result | Category | Observation | Hypothesis |
|---|---|---|---|---|---|---|
| (none yet) | | | | | | |

## BOKE-2026 holdout

The Fifth Miaosuan Cup scenario (user-supplied: "城镇居民26-波克 / 波克的阵线") is not in the local SDK data: the
archive's nested `Data.zip` holds 50 scenarios and 16 map folders, none named `map_26`, and no file mentions the
scenario (checked 2026-10-02 against the archive whose digest the local checksum list pins, entry names and file
contents in UTF-8, GBK and UTF-16; a name search of the development workstation found no competition asset either).
When its assets become available: audit compatibility; do not tune; first run the frozen generalist agent and record
its external performance; only then begin profile-specific work, behind a competition profile.

## Not now

No reinforcement learning, deep learning or online LLM policy: the accelerated online clock and the unknown online
runtime make a deterministic hierarchical doctrine the near-term target. Learned models may come later for enemy
motion, value estimation or opponent modelling, once strong behavioural baselines and replay data exist.
