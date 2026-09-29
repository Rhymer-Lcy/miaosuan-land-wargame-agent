# Engine smoke test: verified runtime behaviour

First controlled execution of the SDK engine, 2026-09-29. This document records only what was
observed in that run; the static audit it tests is `docs/COMPATIBILITY.md`. Later sessions run on
the persistent installation (`ENGINE_INSTALL.md`) and read every state through the contract
boundary; the contract verified since then is maintained in `CONTRACT.md`.

**Result: PASS.** The engine imported, reported successful authentication, set up the scenario,
accepted the end-of-deployment action from both seats, and ran the game to its natural end.

## 1. Setup

| Item | Value |
|---|---|
| Engine | `land_wargame_train_env` 4.1.0 (wheel digest in `docs/PROVENANCE.md`) |
| Platform | Linux x86-64 (Ubuntu 22.04, glibc 2.35), CPU only |
| Environment | `miaosuan-runtime`: CPython 3.10.20, numpy 1.26.2, pandas 1.5.3, getmac 0.9.5 (`environments/`) |
| Harness | `scripts/run_engine_smoke_test.sh` at commit `0543f1d` |
| Game | scenario `201033019601` on map `9601`: one heavy tank per side, one objective, `max_time` 1000 |
| Players | seats 1 (red) and 11 (blue), role 1, as in the SDK's single-agent demo runner |
| Agents | `SmokeAgent`: sends end-of-deployment (type 333) once, nothing else |
| Isolation | engine installed with `pip --target` into a fresh run directory; `env -i`; throwaway `HOME`; no user site-packages; no GPU; 900 s timeout; unprivileged user |

**Why this game.** It is the smallest scenario in the SDK (two units, the shortest `max_time`).
Scenario files do not name their map. The pairing with map 9601 rests on a structural match: the
scenario's `landmarks.roadblocks` lists 50 positions that are exactly the 50 cells flagged
`roadblock` in map 9601, the only map carrying such flags, and both units and the objective lie
inside the area those roadblocks enclose. Map 9601 has the same terrain as map 96 in every cell;
it adds only the roadblock flags. The observation's `terrain_id` reported 9601.

## 2. Observed behaviour

| Item | Observation |
|---|---|
| Import | `train_env` imported in 0.16 s and printed `SDK version: 4.1.0` |
| Authentication | the engine printed `did pass authentication`; no failure marker appeared |
| `TrainEnv()` / `setup()` | returned without error; setup took 0.07 s |
| Deployment | `time.stage` was 1 at setup and 2 after the first `step`; both seats' `end_deployment` flags changed from `false` to `true` |
| Game length | 1001 `step` calls: one deployment step (after it `time.cur_step` was still 0) and 1000 play steps; `done` became `True` with `time.cur_step == max_time == 1000` |
| Timing | 1.79 s for the 1001 steps; 7.4 s for the whole harness including staging and installation |
| Final scores | both sides 30 (remaining-unit score only); no combat, no objective control |
| stderr | empty |
| Replay or snapshot | none: the engine wrote no file into the working directory or `HOME` (the SDK's demo runner builds replays itself) |
| Files changed by the engine | exactly one, see section 4 |
| SDK archive | SHA-256 identical before and after the run |

## 3. Interface contract as observed

| Field | Observed |
|---|---|
| Return of `setup()` and first element of `step()` | a **`dict`** with integer keys `0` (red), `1` (blue), `-1` (all-seeing); not a `list` |
| Return of `step()` | a 2-tuple `(state, done)`; `done` is a `bool` |
| Red and blue observation keys (13) | `cities`, `communication`, `jm_points`, `judge_info`, `landmarks`, `operators`, `passengers`, `role_and_grouping_info`, `scenario_id`, `scores`, `terrain_id`, `time`, `valid_actions` |
| All-seeing observation | the same 13 plus `actions` |
| `time` | `cur_step` (int), `tick` (float 1.0), `max_time` (int), `max_step` (int), `stage` (int: 1 deployment, 2 play) |
| `valid_actions` | operator ids as `int` keys, action types as `int` keys, values `None` or a `list` of option dicts; at the start the tank offered types 1, 6 (with `target_state` 4 and 5) and 11 |
| `role_and_grouping_info` | keyed by seat as `int`; each value has `faction`, `role`, `operators` (list of int), `user_id`, `user_name`, `end_deployment` (bool) |
| `communication` | present; an empty list in the three saved observations |
| `landmarks` | `roadblocks` (50 dicts with `id`, `name`, `hex`, `color`, `creator`, `type`), `minefields` and `fortifications` (both empty) |
| `scores` | 12 keys, including `red_remain_max` and `blue_remain_max` |
| `scenario_id`, `terrain_id` | `int` |
| Operators | 84 fields per operator; in the three saved red observations (start, first play step, end) red saw only its own unit |

## 4. Authenticator behaviour

The only file the engine changed was `train_env/env/authenticate/.engine_config` **inside the
installed package**: shipped empty, it held one 52-byte line after the run. `HOME` stayed empty,
and no `~/.engine_config` (or the FAQ's `~/.engin_config`) was created there. No file was deleted. The content was not decoded; it is kept only in the git-ignored run
directory.

The harness of this first probe installed a fresh copy per run, so each run started with an empty
state file. That was a side effect of isolating the first execution, not a way of using the engine,
and the harness has since been replaced by one persistent installation whose state file is created
once and never reset (`ENGINE_INSTALL.md`).

## 5. Comparison with the static audit

| Audit item | Runtime finding |
|---|---|
| 5.1 `role_and_grouping_info`, `communication`, `time.stage` missing from the bundled example | all three are present; the bundled example observation is outdated |
| 5.2 key types of `valid_actions` unknown | integers at both levels, so integer comparisons such as the demo agent's work |
| 5.11 `target_state` 5 undocumented in the observation note | offered by the engine (`target_state` 5 alongside 4) |
| 2 authentication may refuse to run | it passed on first use |
| 3.7 older scenario files may be rejected | this scenario, one of the 13 that carry `landmarks`, loaded with them; the other 37 remain untested |
| 3.4 key survey | corrected in the audit: it had missed `landmarks` and `blueprints` |
| `actions` listed in the documented observation | absent from red and blue observations; present only in the all-seeing one |
| `state` documented as `list[dict]` | it is a `dict` keyed by 0, 1 and -1 |

## 6. Limits of this evidence

One run, one scenario, inert agents. No movement, combat, objective control or action rejection
was exercised, so action validation and error reporting remain unobserved. The run does not show
how the engine behaves when the authenticator's time limit is reached.
